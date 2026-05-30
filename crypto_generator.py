"""
SI Crypto 일일 리포트 생성 메인.

매일 새벽 GitHub Actions에서 실행됨.
"""
from __future__ import annotations
import argparse
import json
import logging
import shutil
import sqlite3
import sys
import traceback
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from coin_data import TOP_COINS, COIN_TO_ETF, BLOCKCHAIN_ETFS, LAST_HALVING_DATE, NEXT_HALVING_DATE
import market_data as md
import macro_data as mc
import scoring_engine as se
import altcoin_scorer as ac

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s',
                    datefmt='%H:%M:%S')
log = logging.getLogger('si-crypto')


def fmt_krw(v: float | None, digits: int = 0) -> str:
    if v is None or v == 0:
        return '—'
    if v >= 1_000_000:
        return f'₩{v:,.{digits}f}'
    if v >= 1:
        return f'₩{v:,.2f}'
    return f'₩{v:,.4f}'


def fmt_pct(v: float | None) -> str:
    if v is None:
        return '—'
    return f'{"+" if v>=0 else ""}{v:.2f}%'


def fmt_pct_class(v: float | None) -> str:
    if v is None:
        return 'neutral'
    return 'pos' if v >= 0 else 'neg'


def save_to_db(db_path: Path, date_str: str, total_score: int, verdict: str,
                scores: dict, prices: dict, fng: dict | None, dxy: float | None,
                raw_payload: dict):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_judgment (
            date TEXT PRIMARY KEY,
            total_score INTEGER, verdict TEXT,
            btc_price_krw REAL, eth_price_krw REAL,
            score_liquidity INTEGER, score_halving INTEGER,
            score_btc_trend INTEGER, score_volume INTEGER,
            score_etf INTEGER, score_sentiment INTEGER,
            fng_value INTEGER, dxy REAL, raw_json TEXT
        )
    """)
    cur.execute("""
        INSERT OR REPLACE INTO daily_judgment
        (date, total_score, verdict, btc_price_krw, eth_price_krw,
         score_liquidity, score_halving, score_btc_trend, score_volume, score_etf, score_sentiment,
         fng_value, dxy, raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        date_str, total_score, verdict,
        prices.get('BTC', 0), prices.get('ETH', 0),
        scores.get('liquidity', 0), scores.get('halving', 0),
        scores.get('btc_trend', 0), scores.get('volume', 0),
        scores.get('etf', 0), scores.get('sentiment', 0),
        fng.get('value') if fng else None, dxy,
        json.dumps(raw_payload, ensure_ascii=False, default=str),
    ))
    conn.commit()
    conn.close()
    log.info("DB 저장 완료: %s", date_str)


def fetch_history(db_path: Path, limit: int = 90) -> list[dict]:
    """저널 페이지용 최근 N일 판단."""
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("""
        SELECT date, total_score, verdict, btc_price_krw, fng_value
        FROM daily_judgment ORDER BY date DESC LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{'date': r[0], 'total': r[1], 'verdict': r[2],
             'btc_krw': r[3], 'fng': r[4]} for r in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='output')
    parser.add_argument('--templates-dir', default='templates')
    parser.add_argument('--db-path', default='database/journal.db')
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.db_path)

    today = datetime.now()
    date_str = today.strftime('%Y년 %m월 %d일')
    iso_date = today.strftime('%Y-%m-%d')
    timestamp_str = today.strftime('%Y년 %m월 %d일 %H:%M 기준 · 투자 참고용')

    log.info("=" * 60)
    log.info("SI Crypto 리포트 생성 시작 — %s", date_str)
    log.info("=" * 60)

    # 1. 데이터 수집
    log.info("[1/5] 코인 시세 수집...")
    coin_ids = [c['id'] for c in TOP_COINS]
    coins = md.get_top_coins(coin_ids, vs_currency='krw')

    log.info("[2/5] 매크로·온체인 수집...")
    btc_history = md.get_btc_history_usd(days=220)
    btc_trend = md.compute_btc_trend(btc_history)
    # 거래량은 24h 데이터로 단순 계산 (5일 평균은 어려워서 24h 거래량으로 대체)
    btc_coin = coins.get('BTC', {})
    btc_trend['volume_5d_avg'] = btc_coin.get('vol_24h', 0)
    btc_trend['volume_20d_avg'] = btc_coin.get('vol_24h', 0) * 0.85  # 추정

    dxy = md.get_dxy()
    fng = mc.get_fng()
    fed_dir = mc.guess_fed_direction()
    fed_rate = mc.get_fed_rate()
    m2 = mc.get_m2_growth()
    etf_flows = mc.get_btc_etf_flows_5d()

    # 김치프리미엄
    upbit_btc = md.get_upbit_btc_krw()
    usd_krw = md.get_usd_krw()
    btc_usd = btc_trend.get('price', 0)
    kimchi = md.compute_kimchi_premium(upbit_btc, btc_usd, usd_krw)

    # 2. 점수 계산
    log.info("[3/5] 점수 계산...")
    macro = {'fed_direction': fed_dir, 'dxy': dxy, 'fed_rate': fed_rate,
             'm2_growth': m2, 'qt_active': False}
    scores = {}
    reasons = {}
    scores['liquidity'], reasons['liquidity'] = se.score_liquidity(macro)
    scores['halving'], reasons['halving'] = se.score_halving_cycle(LAST_HALVING_DATE)
    scores['btc_trend'], reasons['btc_trend'] = se.score_btc_trend(btc_trend)
    scores['volume'], reasons['volume'] = se.score_volume(btc_trend)
    scores['etf'], reasons['etf'] = se.score_etf_flows(etf_flows)
    scores['sentiment'], reasons['sentiment'] = se.score_sentiment(
        fng.get('value') if fng else None, kimchi)

    result = se.compute_total(scores)
    log.info("  총점 %+d → %s %s",
             result['total'], result['emoji'], result['verdict'])

    # 3. 알트코인 개별 점수
    log.info("[4/5] 알트코인 스캐닝...")
    coin_verdicts = ac.score_all(coins, scores['btc_trend'])

    # 4. ETF 가격
    log.info("[4.5/5] ETF 가격 수집...")
    all_etfs = sorted(
        {e['ticker'] for lst in COIN_TO_ETF.values() for e in lst}
        | {e['ticker'] for e in BLOCKCHAIN_ETFS}
    )
    etf_prices = md.get_etf_prices(all_etfs)

    # ETF 추천 생성 (시장 점수에 따른 행동 권고)
    etf_recommendations = build_etf_recommendations(result, coin_verdicts, etf_prices)

    # 5. DB 저장
    log.info("[5/5] DB 저장 + HTML 렌더링...")
    krw_prices = {sym: data['price'] for sym, data in coins.items()}
    save_to_db(db_path, iso_date, result['total'], result['verdict'],
               scores, krw_prices, fng, dxy,
               {'reasons': reasons, 'btc_trend': btc_trend,
                'etf_flows': etf_flows, 'kimchi': kimchi})

    history = fetch_history(db_path)

    # 백테스트 (단순 — 향후 확장)
    backtest_summary = compute_backtest_summary(history)

    # 포트폴리오용 ETF 가격 JSON
    save_etf_prices_json(output_dir, etf_prices, usd_krw)

    # ★ 포트폴리오 페이지용 통합 가격 JSON (코인 원화 + ETF 달러)
    save_portfolio_prices_json(output_dir, coins, etf_prices, timestamp_str)

    # ★ 포트폴리오 정적 페이지를 output/ 으로 복사 (워크플로가 output/*.html 을 배포)
    copy_portfolio_page(output_dir, args.templates_dir)

    # HTML 렌더링
    env = Environment(loader=FileSystemLoader(args.templates_dir))
    env.filters['fmt_krw'] = fmt_krw
    env.filters['fmt_pct'] = fmt_pct
    env.filters['fmt_pct_class'] = fmt_pct_class

    common_ctx = {
        'timestamp_str': timestamp_str,
        'date_str': date_str,
        'iso_date': iso_date,
    }

    # 1) Dashboard
    dash_html = env.get_template('dashboard.html').render(
        **common_ctx,
        scores=scores, reasons=reasons, result=result,
        btc_trend=btc_trend, fng=fng, dxy=dxy, fed_rate=fed_rate, fed_dir=fed_dir,
        kimchi=kimchi, etf_flows=etf_flows,
        coins=coin_verdicts[:5],  # 메인엔 상위 5개 미리보기
    )
    (output_dir / 'index.html').write_text(dash_html, encoding='utf-8')
    log.info("  ✓ index.html (%d bytes)", len(dash_html))

    # 2) Scanner
    if (Path(args.templates_dir)/'scanner.html').exists():
        sc_html = env.get_template('scanner.html').render(
            **common_ctx, coins=coin_verdicts, result=result, scores=scores)
        (output_dir / 'scanner.html').write_text(sc_html, encoding='utf-8')
        log.info("  ✓ scanner.html (%d bytes)", len(sc_html))

    # 3) ETF Guide
    if (Path(args.templates_dir)/'etf_guide.html').exists():
        eg_html = env.get_template('etf_guide.html').render(
            **common_ctx, recommendations=etf_recommendations,
            etf_prices=etf_prices, coin_to_etf=COIN_TO_ETF,
            result=result, usd_krw=usd_krw)
        (output_dir / 'etf_guide.html').write_text(eg_html, encoding='utf-8')
        log.info("  ✓ etf_guide.html (%d bytes)", len(eg_html))

    # 4) Risk Center
    if (Path(args.templates_dir)/'risk_center.html').exists():
        risk_level, risk_factors = compute_risk_level(scores, fng, kimchi, etf_flows)
        rc_html = env.get_template('risk_center.html').render(
            **common_ctx, risk_level=risk_level, risk_factors=risk_factors,
            scores=scores, fng=fng, dxy=dxy, kimchi=kimchi)
        (output_dir / 'risk_center.html').write_text(rc_html, encoding='utf-8')
        log.info("  ✓ risk_center.html (%d bytes)", len(rc_html))

    # 5) Journal
    if (Path(args.templates_dir)/'journal.html').exists():
        jr_html = env.get_template('journal.html').render(
            **common_ctx, history=history, backtest=backtest_summary)
        (output_dir / 'journal.html').write_text(jr_html, encoding='utf-8')
        log.info("  ✓ journal.html (%d bytes)", len(jr_html))

    log.info("✅ 완료")


def build_etf_recommendations(result: dict, coin_verdicts: list, etf_prices: dict) -> list[dict]:
    """시장 + 코인 점수에 따라 ETF별 행동 권고 생성."""
    recs = []
    code = result['code']

    coin_map = {c['ticker']: c for c in coin_verdicts}

    for coin_sym, etfs in COIN_TO_ETF.items():
        cv = coin_map.get(coin_sym)
        if not cv:
            continue
        # 시장 + 코인 판정 둘 다 보고 권고
        if code in ('strong_buy', 'buy') and cv['code'] in ('strong_buy', 'buy', 'hold'):
            action, tone, msg = '분할매수', 'buy', f'{coin_sym} 추세 우호적. 분할매수 권장.'
        elif code in ('cash_out',) or cv['code'] in ('sell', 'trim'):
            action, tone, msg = '비중 축소', 'sell', f'{coin_sym} 약세 신호. 비중 축소 검토.'
        elif code == 'hold' and cv['code'] == 'hold':
            action, tone, msg = '보유', 'hold', '현 비중 유지.'
        else:
            action, tone, msg = '관망', 'wait', '신규 진입 보류.'

        for etf in etfs:
            recs.append({
                'coin': coin_sym, 'coin_name': cv['name'],
                'etf_ticker': etf['ticker'], 'etf_name': etf['name'],
                'kind': etf['kind'], 'market': etf['market'],
                'action': action, 'tone': tone, 'msg': msg,
                'etf_price_usd': etf_prices.get(etf['ticker'], {}).get('price_usd'),
                'etf_change_pct': etf_prices.get(etf['ticker'], {}).get('change_pct'),
            })
    return recs


def compute_risk_level(scores: dict, fng: dict | None, kimchi: float | None,
                        etf_flows: dict) -> tuple[str, list[dict]]:
    """Risk On/Neutral/Off."""
    factors = []
    risk_points = 0  # 음수=Risk Off

    if fng:
        v = fng['value']
        if v >= 75:
            factors.append({'name':'Fear & Greed','value':f'{v} 극탐욕','status':'red'})
            risk_points -= 2
        elif v >= 60:
            factors.append({'name':'Fear & Greed','value':f'{v} 탐욕','status':'yellow'})
            risk_points -= 1
        elif v <= 25:
            factors.append({'name':'Fear & Greed','value':f'{v} 공포','status':'green'})
            risk_points += 1
        else:
            factors.append({'name':'Fear & Greed','value':f'{v} 중립','status':'neutral'})

    if kimchi is not None:
        if kimchi > 5:
            factors.append({'name':'김치프리미엄','value':f'{kimchi:+.1f}%','status':'red'})
            risk_points -= 1
        elif kimchi < -2:
            factors.append({'name':'김치프리미엄','value':f'{kimchi:+.1f}%','status':'green'})
            risk_points += 1
        else:
            factors.append({'name':'김치프리미엄','value':f'{kimchi:+.1f}%','status':'neutral'})

    net = etf_flows.get('btc_etf_5d_net_inflow_usd', 0)
    if net > 500_000_000:
        factors.append({'name':'BTC ETF 흐름','value':f'+${net/1e9:.2f}B','status':'green'})
        risk_points += 1
    elif net < -500_000_000:
        factors.append({'name':'BTC ETF 흐름','value':f'-${abs(net)/1e9:.2f}B','status':'red'})
        risk_points -= 1
    else:
        factors.append({'name':'BTC ETF 흐름','value':f'${net/1e6:+.0f}M','status':'neutral'})

    # 종합
    total = sum(scores.values())
    if total >= 4 and risk_points >= 0:
        return 'Risk On', factors
    if total <= -4 or risk_points <= -2:
        return 'Risk Off', factors
    return 'Risk Neutral', factors


def compute_backtest_summary(history: list[dict]) -> dict:
    """저널 기반 단순 백테스트 요약."""
    if len(history) < 7:
        return {'note': f'데이터 축적 중 ({len(history)}/30일). 30일 후부터 의미있는 백테스트 가능.',
                'days_accumulated': len(history), 'win_rate': None, 'avg_return': None}
    # +4 이상에서 BTC 매수, -3 이하에서 매도 가정 — 추후 구현
    return {'note': f'{len(history)}일 누적. 백테스트 엔진 v1.0.',
            'days_accumulated': len(history), 'win_rate': None, 'avg_return': None}


def save_etf_prices_json(output_dir: Path, etf_prices: dict, usd_krw: float | None):
    """포트폴리오 페이지가 ./etf_prices.json을 읽도록."""
    out = {'generated_at': datetime.now().isoformat(), 'usd_krw': usd_krw, 'prices': {}}
    for tk, p in etf_prices.items():
        out['prices'][tk] = {
            'price_usd': p.get('price_usd'),
            'price_krw': (p.get('price_usd') or 0) * (usd_krw or 0) if usd_krw else None,
            'change_pct': p.get('change_pct'),
            'currency': 'USD',
        }
    (output_dir / 'etf_prices.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')


def save_portfolio_prices_json(output_dir: Path, coins: dict, etf_prices: dict,
                               timestamp_str: str):
    """
    포트폴리오 페이지(portfolio.html)가 읽는 통합 가격 파일.
    주식 포트폴리오의 portfolio_prices.json 과 동일한 형식:
      { "updatedAt": "...", "prices": [ {ticker,name,assetType,currency,currentPrice,priceFetched}, ... ] }
    - 코인: 원화(KRW)
    - 코인 ETF: 달러(USD)
    """
    # ETF 한글/영문 이름 매핑
    etf_names = {}
    for lst in COIN_TO_ETF.values():
        for e in lst:
            etf_names[e['ticker']] = e['name']
    for e in BLOCKCHAIN_ETFS:
        etf_names[e['ticker']] = e['name']

    prices = []

    # 1) 코인 (원화)
    for sym, d in coins.items():
        px = d.get('price') or 0
        if px <= 0:
            continue
        prices.append({
            'ticker': sym,
            'name': d.get('name', sym),
            'assetType': 'coin',
            'currency': 'KRW',
            'currentPrice': round(px, 2),
            'previousClose': None,
            'changePercent': d.get('change_24h'),
            'priceFetched': True,
        })

    # 2) 코인 ETF (달러)
    for tk, p in etf_prices.items():
        pu = p.get('price_usd')
        if pu is None or pu <= 0:
            continue
        prices.append({
            'ticker': tk,
            'name': etf_names.get(tk, tk),
            'assetType': 'ETF',
            'currency': 'USD',
            'currentPrice': round(pu, 4),
            'previousClose': None,
            'changePercent': p.get('change_pct'),
            'priceFetched': True,
        })

    out = {
        'updatedAt': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'source': 'Upbit/CoinPaprika (coins, KRW) + Yahoo Finance (ETFs, USD)',
        'count': len(prices),
        'prices': prices,
    }
    (output_dir / 'portfolio_prices.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    log.info("  ✓ portfolio_prices.json (%d종목)", len(prices))


def copy_portfolio_page(output_dir: Path, templates_dir: str):
    """
    정적 포트폴리오 페이지(portfolio.html)를 output/ 으로 복사.
    저장소 루트 또는 templates/ 폴더 어디에 있어도 찾아서 복사한다.
    (Jinja 렌더링 없이 그대로 복사 — 페이지 내부는 순수 JS)
    """
    candidates = [Path('portfolio.html'), Path(templates_dir) / 'portfolio.html']
    for src in candidates:
        if src.exists():
            shutil.copy(src, output_dir / 'portfolio.html')
            log.info("  ✓ portfolio.html 복사 (%s)", src)
            return
    log.warning("  ! portfolio.html 을 찾지 못함 (루트/templates 어디에도 없음)")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log.error("실행 실패: %s", e)
        traceback.print_exc()
        sys.exit(1)
