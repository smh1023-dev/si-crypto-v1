"""
알트코인 개별 점수 매겨서 6단계 판정.

판정: 강한매수 / 분할매수 / 보유 / 부분매도 / 관망 / 매도
"""
from __future__ import annotations


def score_one_coin(coin: dict, market_score: int) -> dict:
    """
    coin = {symbol, name, price, change_24h, change_7d, change_30d, vol_24h, ath_change_pct, ...}
    market_score: 시장 종합 점수 (-12 ~ +12). 알트코인 신규매수 제한 등에 사용.

    Returns: {ticker, name, price, change_7d, change_30d, verdict, score, reasons[]}
    """
    sym = coin.get('symbol', '?')
    price = coin.get('price', 0)
    c7 = coin.get('change_7d') or 0
    c30 = coin.get('change_30d') or 0
    ath_chg = coin.get('ath_change_pct') or 0
    vol = coin.get('vol_24h', 0)

    score = 0
    reasons = []

    # 1) 30일 추세 (가중치 큼)
    if c30 >= 30:
        score += 2; reasons.append(f'30일 +{c30:.0f}% 강한 상승')
    elif c30 >= 10:
        score += 1; reasons.append(f'30일 +{c30:.0f}% 상승')
    elif c30 <= -30:
        score -= 2; reasons.append(f'30일 {c30:.0f}% 급락')
    elif c30 <= -15:
        score -= 1; reasons.append(f'30일 {c30:.0f}% 하락')

    # 2) 7일 추세 (모멘텀)
    if c7 >= 15:
        score += 1; reasons.append(f'7일 +{c7:.0f}% 단기 모멘텀 강')
    elif c7 <= -15:
        score -= 1; reasons.append(f'7일 {c7:.0f}% 단기 약세')

    # 3) ATH 대비 위치 (저가매수 vs 고점 위험)
    if ath_chg < -50:
        score += 1; reasons.append(f'ATH 대비 {ath_chg:.0f}% (저가권)')
    elif ath_chg > -5:
        score -= 1; reasons.append(f'ATH 근접 {ath_chg:.0f}% (과열 위험)')

    # 4) 거래량 (충분히 활발한지)
    if vol < 10_000_000_000:  # 100억원 미만은 유동성 부족
        # 원화 기준이 작을 수 있으니 그냥 정보만
        pass

    # 5) 시장 점수 보정 (BTC가 약하면 알트는 더 보수적)
    if market_score < -3 and score > 0:
        reasons.append('⚠ 시장 약세장 — 신규매수 보류')
        score = min(score, 0)

    # 판정
    if score >= 3:
        verdict, code = '강한매수', 'strong_buy'
    elif score >= 2:
        verdict, code = '분할매수', 'buy'
    elif score >= 0:
        verdict, code = '보유', 'hold'
    elif score >= -1:
        verdict, code = '관망', 'wait'
    elif score >= -2:
        verdict, code = '부분매도', 'trim'
    else:
        verdict, code = '매도', 'sell'

    return {
        'ticker': sym,
        'name': coin.get('name', ''),
        'price': price,
        'change_24h': coin.get('change_24h') or 0,
        'change_7d': c7,
        'change_30d': c30,
        'ath_change_pct': ath_chg,
        'vol_24h': vol,
        'market_cap': coin.get('market_cap', 0),
        'verdict': verdict,
        'code': code,
        'score': score,
        'reasons': reasons,
    }


def score_all(coins_dict: dict, market_score: int) -> list[dict]:
    """전체 코인 점수 + 시총 순 정렬."""
    out = []
    for sym, data in coins_dict.items():
        data2 = {'symbol': sym, **data}
        out.append(score_one_coin(data2, market_score))
    # 시총 순
    out.sort(key=lambda x: x.get('market_cap', 0), reverse=True)
    return out
