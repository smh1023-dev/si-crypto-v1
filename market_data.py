"""
시장 데이터 수집.

원천:
  - CoinGecko: 상위 코인 시세·시총 (원화 직접 지원)
  - Upbit: 한국 원화 시세 (김치프리미엄 계산)
  - yfinance: BTC USD 가격 히스토리, DXY, ETF 가격
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timedelta

import requests
import pandas as pd

log = logging.getLogger(__name__)


# ============================================================
#  CoinGecko - 상위 코인 시세·시총
# ============================================================

def get_top_coins(coin_ids: list[str], vs_currency: str = 'krw') -> dict[str, dict]:
    """
    CoinGecko에서 코인별 현재 시세·시총·거래량·24h 변동률을 받아옴.
    Returns: {symbol_upper: {price, market_cap, vol_24h, change_24h}}
    """
    out = {}
    try:
        r = requests.get(
            'https://api.coingecko.com/api/v3/coins/markets',
            params={
                'vs_currency': vs_currency,
                'ids': ','.join(coin_ids),
                'order': 'market_cap_desc',
                'per_page': len(coin_ids),
                'page': 1,
                'price_change_percentage': '24h,7d,30d',
            },
            timeout=15,
        )
        r.raise_for_status()
        for c in r.json():
            sym = c['symbol'].upper()
            out[sym] = {
                'name': c['name'],
                'id': c['id'],
                'price': c['current_price'],
                'market_cap': c['market_cap'],
                'vol_24h': c['total_volume'],
                'change_24h': c.get('price_change_percentage_24h_in_currency'),
                'change_7d': c.get('price_change_percentage_7d_in_currency'),
                'change_30d': c.get('price_change_percentage_30d_in_currency'),
                'ath': c.get('ath'),
                'ath_change_pct': c.get('ath_change_percentage'),
            }
        log.info("CoinGecko: %d개 코인 수집", len(out))
    except Exception as e:
        log.error("CoinGecko 실패: %s", e)
    return out


def get_btc_history_usd(days: int = 220) -> pd.Series:
    """
    BTC USD 일별 종가 (yfinance). SMA200 등 추세 분석용.
    """
    try:
        import yfinance as yf
        end = datetime.utcnow()
        start = end - timedelta(days=days + 30)
        df = yf.Ticker('BTC-USD').history(start=start, end=end, interval='1d')
        if df.empty:
            return pd.Series(dtype=float)
        return df['Close'].dropna()
    except Exception as e:
        log.error("BTC history 실패: %s", e)
        return pd.Series(dtype=float)


def compute_btc_trend(btc_close: pd.Series) -> dict:
    """BTC 가격 시리즈에서 추세 지표 계산."""
    if btc_close is None or len(btc_close) < 50:
        return {'price': 0, 'sma50': 0, 'sma200': 0, 'volume_5d_avg': 0,
                'volume_20d_avg': 0, 'price_change_5d': 0,
                'golden_cross_recent': False, 'death_cross_recent': False}

    sma50 = btc_close.tail(50).mean()
    sma200 = btc_close.tail(200).mean() if len(btc_close) >= 200 else btc_close.mean()
    price = float(btc_close.iloc[-1])
    change_5d = float(btc_close.iloc[-1] / btc_close.iloc[-6] - 1) if len(btc_close) > 6 else 0

    # 최근 30일 골든/데드크로스 체크
    gc, dc = False, False
    if len(btc_close) >= 200:
        recent_50 = btc_close.rolling(50).mean()
        recent_200 = btc_close.rolling(200).mean()
        diff = recent_50 - recent_200
        last30_signs = (diff.tail(30) > 0).astype(int).diff().dropna()
        if (last30_signs == 1).any():
            gc = True
        if (last30_signs == -1).any():
            dc = True

    return {
        'price': price,
        'sma50': float(sma50),
        'sma200': float(sma200),
        'volume_5d_avg': 0,    # CoinGecko에서 별도 받음
        'volume_20d_avg': 0,
        'price_change_5d': change_5d,
        'golden_cross_recent': gc,
        'death_cross_recent': dc,
    }


# ============================================================
#  Upbit - 김치프리미엄
# ============================================================

def get_upbit_btc_krw() -> float | None:
    """Upbit BTC 원화가."""
    try:
        r = requests.get('https://api.upbit.com/v1/ticker',
                          params={'markets': 'KRW-BTC'}, timeout=10)
        return float(r.json()[0]['trade_price'])
    except Exception as e:
        log.warning("Upbit 실패: %s", e)
        return None


def get_usd_krw() -> float | None:
    """달러-원 환율 (yfinance)."""
    try:
        import yfinance as yf
        h = yf.Ticker('KRW=X').history(period='5d', interval='1d')
        if h.empty:
            return None
        return float(h['Close'].iloc[-1])
    except Exception as e:
        log.warning("USD/KRW 실패: %s", e)
        return None


def compute_kimchi_premium(upbit_btc_krw: float, btc_usd: float, usd_krw: float) -> float | None:
    """김치프리미엄 % = (업비트 - 해외환산) / 해외환산 * 100"""
    if not (upbit_btc_krw and btc_usd and usd_krw):
        return None
    overseas_krw = btc_usd * usd_krw
    return (upbit_btc_krw - overseas_krw) / overseas_krw * 100


# ============================================================
#  yfinance - DXY, ETF 가격
# ============================================================

def get_dxy() -> float | None:
    """달러 인덱스."""
    try:
        import yfinance as yf
        h = yf.Ticker('DX-Y.NYB').history(period='5d', interval='1d')
        if h.empty:
            return None
        return float(h['Close'].iloc[-1])
    except Exception as e:
        log.warning("DXY 실패: %s", e)
        return None


def get_etf_prices(tickers: list[str]) -> dict[str, dict]:
    """ETF 일별 현재가."""
    out = {}
    try:
        import yfinance as yf
        for tk in tickers:
            try:
                h = yf.Ticker(tk).history(period='5d', interval='1d')
                if h.empty:
                    continue
                last = h['Close'].iloc[-1]
                prev = h['Close'].iloc[-2] if len(h) > 1 else last
                out[tk] = {
                    'price_usd': float(last),
                    'change_pct': float((last/prev - 1) * 100) if prev > 0 else 0,
                }
            except Exception:
                continue
        log.info("ETF: %d개 가격 수집", len(out))
    except Exception as e:
        log.error("ETF 가격 실패: %s", e)
    return out
