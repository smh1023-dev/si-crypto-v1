"""
시장 데이터 수집 (v2).

변경 이력:
  v1: CoinGecko 단일 의존 → 429 Too Many Requests 빈발
  v2: Upbit(원화 직접) 1차 + CoinPaprika 2차 + CoinGecko 3차 폴백.
      GitHub Actions 환경에서 rate-limit에 강건.
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timedelta

import requests
import pandas as pd

log = logging.getLogger(__name__)


# 코인 심볼 → CoinPaprika ID 매핑 (단순 매핑 테이블)
COINPAPRIKA_IDS = {
    'BTC':  'btc-bitcoin',
    'ETH':  'eth-ethereum',
    'SOL':  'sol-solana',
    'XRP':  'xrp-xrp',
    'BNB':  'bnb-binance-coin',
    'DOGE': 'doge-dogecoin',
    'ADA':  'ada-cardano',
    'AVAX': 'avax-avalanche',
    'LINK': 'link-chainlink',
    'SUI':  'sui-sui',
}

# 한글 이름 매핑 (Upbit에서 못 가져온 코인용)
KR_NAMES = {
    'BTC':  '비트코인',  'ETH':  '이더리움',  'SOL':  '솔라나',  'XRP':  '리플',
    'BNB':  '바이낸스코인','DOGE': '도지코인',  'ADA':  '에이다',  'AVAX': '아발란체',
    'LINK': '체인링크',  'SUI':  '수이',
}


# ============================================================
#  통합 수집 함수 — 메인 진입점
# ============================================================

def get_top_coins(coin_ids: list[str], vs_currency: str = 'krw') -> dict[str, dict]:
    """
    상위 코인 시세를 받아옴. 다층 폴백:
      1) Upbit (원화 + 변동률, KRW 시장 한정)
      2) CoinPaprika (USD → KRW 환산)
      3) CoinGecko (최후 폴백)

    Returns: {symbol: {name, id, price, market_cap, vol_24h,
                       change_24h, change_7d, change_30d, ath, ath_change_pct}}
    """
    # 심볼 추출 (CoinGecko id → 심볼)
    id_to_sym = {
        'bitcoin':'BTC','ethereum':'ETH','solana':'SOL','ripple':'XRP',
        'binancecoin':'BNB','dogecoin':'DOGE','cardano':'ADA',
        'avalanche-2':'AVAX','chainlink':'LINK','sui':'SUI',
    }
    target_symbols = [id_to_sym.get(c, c.upper()) for c in coin_ids]

    out = {}

    # 1차: Upbit (원화 직접)
    try:
        upbit_data = _get_upbit_top_coins(target_symbols)
        out.update(upbit_data)
        log.info("Upbit: %d개 코인 수집", len(upbit_data))
    except Exception as e:
        log.warning("Upbit 실패: %s", e)

    # 2차: CoinPaprika (Upbit에서 못 받은 것 보완)
    missing = [s for s in target_symbols if s not in out]
    if missing:
        try:
            usd_krw = get_usd_krw() or 1380  # 폴백 환율
            cp_data = _get_coinpaprika(missing, usd_krw)
            out.update(cp_data)
            log.info("CoinPaprika: %d개 코인 보완 수집", len(cp_data))
        except Exception as e:
            log.warning("CoinPaprika 실패: %s", e)

    # 3차: CoinGecko (정 안되면)
    still_missing = [s for s in target_symbols if s not in out]
    if still_missing:
        try:
            cg_data = _get_coingecko_fallback(coin_ids, vs_currency)
            for sym, d in cg_data.items():
                if sym not in out:
                    out[sym] = d
            log.info("CoinGecko 폴백: %d개", len(cg_data))
        except Exception as e:
            log.warning("CoinGecko 폴백도 실패: %s", e)

    log.info("최종 코인 데이터: %d개", len(out))
    return out


# ============================================================
#  1) Upbit — 원화 시세 (KRW-XXX 마켓)
# ============================================================

def _get_upbit_top_coins(symbols: list[str]) -> dict[str, dict]:
    """
    Upbit에서 KRW-XXX 마켓 시세 + 캔들 데이터로 7일/30일 변동률 계산.
    BNB 등 Upbit 미상장 코인은 못 받음 (None 반환 안함, 그냥 dict에 없음).
    """
    # 1) 어떤 KRW 마켓이 있는지 확인
    try:
        r = requests.get('https://api.upbit.com/v1/market/all',
                          params={'isDetails': 'false'}, timeout=10)
        markets = r.json()
        krw_set = {m['market'].replace('KRW-','') for m in markets if m['market'].startswith('KRW-')}
    except Exception:
        krw_set = set()

    # 2) 거래 가능한 심볼만
    available = [s for s in symbols if s in krw_set]
    if not available:
        return {}

    market_codes = ','.join(f'KRW-{s}' for s in available)

    # 3) 현재가 + 변동률 한번에
    try:
        r = requests.get('https://api.upbit.com/v1/ticker',
                          params={'markets': market_codes}, timeout=15)
        tickers = r.json()
    except Exception:
        return {}

    out = {}
    for t in tickers:
        sym = t['market'].replace('KRW-', '')
        change_24h = float(t.get('signed_change_rate', 0)) * 100
        out[sym] = {
            'name': KR_NAMES.get(sym, sym),
            'id': sym.lower(),
            'price': float(t.get('trade_price', 0)),
            'market_cap': 0,  # Upbit는 시총 안 줌
            'vol_24h': float(t.get('acc_trade_price_24h', 0)),
            'change_24h': change_24h,
            'change_7d': None,
            'change_30d': None,
            'ath': float(t.get('highest_52_week_price', 0)),
            'ath_change_pct': None,
        }

    # 4) 7일/30일 변동률은 일봉으로 별도 계산 (각 코인당 1회 호출)
    for sym in available:
        try:
            time.sleep(0.1)  # rate limit 방어
            r = requests.get('https://api.upbit.com/v1/candles/days',
                              params={'market': f'KRW-{sym}', 'count': 31}, timeout=10)
            candles = r.json()
            if not candles or len(candles) < 8:
                continue
            today = candles[0]['trade_price']
            d7 = candles[7]['trade_price'] if len(candles) > 7 else today
            d30 = candles[30]['trade_price'] if len(candles) > 30 else d7

            if sym in out:
                if d7 > 0:
                    out[sym]['change_7d'] = (today / d7 - 1) * 100
                if d30 > 0:
                    out[sym]['change_30d'] = (today / d30 - 1) * 100
                # ATH 대비 등락률 (52주 고가 기준 근사)
                if out[sym].get('ath', 0) > 0:
                    out[sym]['ath_change_pct'] = (today / out[sym]['ath'] - 1) * 100
        except Exception:
            continue

    return out


# ============================================================
#  2) CoinPaprika — USD 시세 (KRW 환산)
# ============================================================

def _get_coinpaprika(symbols: list[str], usd_krw: float) -> dict[str, dict]:
    """CoinPaprika /tickers/{id} per-coin 조회 (rate limit 관대)."""
    out = {}
    for sym in symbols:
        cp_id = COINPAPRIKA_IDS.get(sym)
        if not cp_id:
            continue
        try:
            time.sleep(0.15)
            r = requests.get(f'https://api.coinpaprika.com/v1/tickers/{cp_id}',
                              params={'quotes': 'USD'}, timeout=10)
            if r.status_code != 200:
                continue
            d = r.json()
            q = d.get('quotes', {}).get('USD', {})
            price_usd = q.get('price', 0)
            out[sym] = {
                'name': KR_NAMES.get(sym, d.get('name', sym)),
                'id': cp_id,
                'price': price_usd * usd_krw,  # 원화 환산
                'market_cap': q.get('market_cap', 0) * usd_krw,
                'vol_24h': q.get('volume_24h', 0) * usd_krw,
                'change_24h': q.get('percent_change_24h'),
                'change_7d': q.get('percent_change_7d'),
                'change_30d': q.get('percent_change_30d'),
                'ath': (d.get('quotes', {}).get('USD', {}).get('ath_price', 0) or 0) * usd_krw,
                'ath_change_pct': q.get('percent_from_price_ath'),
            }
        except Exception:
            continue
    return out


# ============================================================
#  3) CoinGecko 폴백 (옵션)
# ============================================================

def _get_coingecko_fallback(coin_ids: list[str], vs_currency: str) -> dict[str, dict]:
    """원래 CoinGecko 로직 (rate-limit 위험 있으므로 최후 폴백)."""
    out = {}
    try:
        r = requests.get(
            'https://api.coingecko.com/api/v3/coins/markets',
            params={'vs_currency': vs_currency, 'ids': ','.join(coin_ids),
                    'order': 'market_cap_desc', 'per_page': len(coin_ids), 'page': 1,
                    'price_change_percentage': '24h,7d,30d'},
            timeout=15,
        )
        r.raise_for_status()
        for c in r.json():
            sym = c['symbol'].upper()
            out[sym] = {
                'name': KR_NAMES.get(sym, c['name']), 'id': c['id'],
                'price': c['current_price'], 'market_cap': c['market_cap'],
                'vol_24h': c['total_volume'],
                'change_24h': c.get('price_change_percentage_24h_in_currency'),
                'change_7d': c.get('price_change_percentage_7d_in_currency'),
                'change_30d': c.get('price_change_percentage_30d_in_currency'),
                'ath': c.get('ath'), 'ath_change_pct': c.get('ath_change_percentage'),
            }
    except Exception:
        pass
    return out


# ============================================================
#  유틸리티 (BTC USD 히스토리, DXY 등)
# ============================================================

def get_btc_history_usd(days: int = 220) -> pd.Series:
    """BTC USD 일별 종가 (yfinance)."""
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
    if btc_close is None or len(btc_close) < 50:
        return {'price': 0, 'sma50': 0, 'sma200': 0, 'volume_5d_avg': 0,
                'volume_20d_avg': 0, 'price_change_5d': 0,
                'golden_cross_recent': False, 'death_cross_recent': False}

    sma50 = btc_close.tail(50).mean()
    sma200 = btc_close.tail(200).mean() if len(btc_close) >= 200 else btc_close.mean()
    price = float(btc_close.iloc[-1])
    change_5d = float(btc_close.iloc[-1] / btc_close.iloc[-6] - 1) if len(btc_close) > 6 else 0

    gc, dc = False, False
    if len(btc_close) >= 200:
        recent_50 = btc_close.rolling(50).mean()
        recent_200 = btc_close.rolling(200).mean()
        diff = recent_50 - recent_200
        last30_signs = (diff.tail(30) > 0).astype(int).diff().dropna()
        if (last30_signs == 1).any(): gc = True
        if (last30_signs == -1).any(): dc = True

    return {'price': price, 'sma50': float(sma50), 'sma200': float(sma200),
            'volume_5d_avg': 0, 'volume_20d_avg': 0, 'price_change_5d': change_5d,
            'golden_cross_recent': gc, 'death_cross_recent': dc}


def get_upbit_btc_krw() -> float | None:
    try:
        r = requests.get('https://api.upbit.com/v1/ticker',
                          params={'markets': 'KRW-BTC'}, timeout=10)
        return float(r.json()[0]['trade_price'])
    except Exception as e:
        log.warning("Upbit BTC 실패: %s", e)
        return None


def get_usd_krw() -> float | None:
    try:
        import yfinance as yf
        h = yf.Ticker('KRW=X').history(period='5d', interval='1d')
        if h.empty: return None
        return float(h['Close'].iloc[-1])
    except Exception as e:
        log.warning("USD/KRW 실패: %s", e)
        return None


def compute_kimchi_premium(upbit_btc_krw: float, btc_usd: float, usd_krw: float) -> float | None:
    if not (upbit_btc_krw and btc_usd and usd_krw):
        return None
    overseas_krw = btc_usd * usd_krw
    return (upbit_btc_krw - overseas_krw) / overseas_krw * 100


def get_dxy() -> float | None:
    try:
        import yfinance as yf
        h = yf.Ticker('DX-Y.NYB').history(period='5d', interval='1d')
        if h.empty: return None
        return float(h['Close'].iloc[-1])
    except Exception as e:
        log.warning("DXY 실패: %s", e)
        return None


def get_etf_prices(tickers: list[str]) -> dict[str, dict]:
    out = {}
    try:
        import yfinance as yf
        for tk in tickers:
            try:
                h = yf.Ticker(tk).history(period='5d', interval='1d')
                if h.empty: continue
                last = h['Close'].iloc[-1]
                prev = h['Close'].iloc[-2] if len(h) > 1 else last
                out[tk] = {'price_usd': float(last),
                           'change_pct': float((last/prev - 1) * 100) if prev > 0 else 0}
            except Exception:
                continue
        log.info("ETF: %d개 가격 수집", len(out))
    except Exception as e:
        log.error("ETF 가격 실패: %s", e)
    return out
