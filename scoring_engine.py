"""
SI Crypto 점수 엔진.

6개 영역(유동성·반감기·BTC추세·거래량·ETF&온체인·과열심리) 각 -2~+2 점.
합산 -12 ~ +12 → 5단계 판정.
"""
from __future__ import annotations
from datetime import datetime, timedelta
import logging

log = logging.getLogger(__name__)


# ============================================================
#  A. 유동성 (Macro)
# ============================================================

def score_liquidity(macro: dict) -> tuple[int, list[str]]:
    """
    macro = {
        'fed_rate': 4.5,           # 현재 Fed 금리 (%)
        'fed_direction': 'cut',    # 'cut' | 'hold' | 'hike'
        'dxy': 102.5,              # 달러 인덱스
        'm2_growth': 2.5,          # M2 통화량 전년 대비 증가율 (%)
        'qt_active': True,         # QT 진행 중?
    }
    """
    score = 0
    reasons = []

    direction = macro.get('fed_direction', 'hold')
    if direction == 'cut':
        score += 2; reasons.append('Fed 금리 인하 사이클 (+2)')
    elif direction == 'hike':
        score -= 2; reasons.append('Fed 금리 인상 사이클 (-2)')
    else:
        reasons.append('Fed 금리 동결')

    dxy = macro.get('dxy')
    if dxy is not None:
        if dxy < 100:
            score += 1; reasons.append(f'달러 약세 DXY {dxy:.1f} (+1)')
        elif dxy > 105:
            score -= 1; reasons.append(f'달러 강세 DXY {dxy:.1f} (-1)')

    if macro.get('qt_active'):
        score -= 1; reasons.append('QT 진행 중 (-1)')

    m2 = macro.get('m2_growth')
    if m2 is not None and m2 > 3:
        score += 1; reasons.append(f'M2 증가율 {m2:.1f}% (+1)')

    score = max(-2, min(2, score))
    return score, reasons


# ============================================================
#  B. 반감기 사이클
# ============================================================

def score_halving_cycle(last_halving: str = '2024-04-19',
                         today: datetime | None = None) -> tuple[int, list[str]]:
    """마지막 반감기 기준 D+N일에 따라 사이클 단계 판정."""
    today = today or datetime.now()
    last = datetime.strptime(last_halving, '%Y-%m-%d')
    days = (today - last).days

    if days < 0:
        # 반감기 전 매집기 (다음 반감기 기준)
        return 2, [f'반감기 D{days}일 (전 매집기, +2)']
    elif days <= 180:
        return 1, [f'반감기 D+{days}일 (랠리 시작, +1)']
    elif days <= 540:
        return 1, [f'반감기 D+{days}일 (피크 도달기, +1)']
    elif days <= 900:
        return -1, [f'반감기 D+{days}일 (피크 후 조정, -1)']
    else:
        return -2, [f'반감기 D+{days}일 (베어 사이클, -2)']


# ============================================================
#  C. BTC 추세
# ============================================================

def score_btc_trend(btc_data: dict) -> tuple[int, list[str]]:
    """
    btc_data = {
        'price': 95000,        # USD
        'sma50': 92000,
        'sma200': 80000,
        'golden_cross_recent': False,   # 최근 30일내 골든크로스
        'death_cross_recent': False,
    }
    """
    score = 0
    reasons = []

    price = btc_data.get('price', 0)
    sma50 = btc_data.get('sma50', 0)
    sma200 = btc_data.get('sma200', 0)

    if price > 0 and sma200 > 0:
        above_200 = price > sma200
        above_50 = price > sma50
        sma50_above_200 = sma50 > sma200

        if above_200 and above_50 and sma50_above_200:
            score = 2
            reasons.append(f'BTC ${price:,.0f} > 50일선 > 200일선 (강한 상승추세 +2)')
        elif above_200 and sma50_above_200:
            score = 1
            reasons.append(f'BTC > 200일선 & 골든크로스 상태 (+1)')
        elif above_200:
            score = 1
            reasons.append(f'BTC > 200일선 (+1)')
        elif abs(price - sma200) / sma200 < 0.03:
            score = 0
            reasons.append(f'BTC ≈ 200일선 (중립)')
        elif not sma50_above_200:
            score = -2
            reasons.append(f'BTC < 200일선 & 데드크로스 (-2)')
        else:
            score = -1
            reasons.append(f'BTC < 200일선 (-1)')

    if btc_data.get('golden_cross_recent'):
        reasons.append('🌟 최근 골든크로스 발생')
    if btc_data.get('death_cross_recent'):
        reasons.append('⚠ 최근 데드크로스 발생')

    return score, reasons


# ============================================================
#  D. 거래량
# ============================================================

def score_volume(btc_data: dict) -> tuple[int, list[str]]:
    """
    btc_data = {
        'volume_5d_avg': 45_000_000_000,    # 최근 5일 평균
        'volume_20d_avg': 30_000_000_000,   # 최근 20일 평균
        'price_change_5d': 0.05,            # 5일 가격 변동률 (소수)
    }
    """
    vol5 = btc_data.get('volume_5d_avg', 0)
    vol20 = btc_data.get('volume_20d_avg', 0)
    change5 = btc_data.get('price_change_5d', 0)

    if vol5 == 0 or vol20 == 0:
        return 0, ['거래량 데이터 부족']

    ratio = vol5 / vol20
    reasons = [f'5일/20일 거래량비 {ratio:.2f}x']

    if ratio > 1.5 and change5 > 0.03:
        return 2, reasons + ['상승 돌파 + 거래량 폭증 (+2)']
    if ratio > 1.5 and change5 < -0.03:
        return -2, reasons + ['하락 돌파 + 거래량 폭증 (-2)']
    if ratio > 1.2:
        return 1, reasons + ['거래량 증가 추세 (+1)']
    if ratio < 0.8:
        return -1, reasons + ['거래량 감소 추세 (-1)']
    return 0, reasons + ['거래량 평이']


# ============================================================
#  E. ETF · 온체인
# ============================================================

def score_etf_flows(etf_data: dict) -> tuple[int, list[str]]:
    """
    etf_data = {
        'btc_etf_5d_net_inflow_usd': 1_500_000_000,    # 양수=유입, 음수=유출
    }
    """
    net = etf_data.get('btc_etf_5d_net_inflow_usd', 0)
    reasons = []

    if net > 1_000_000_000:
        return 2, [f'BTC ETF 5일 순유입 ${net/1e9:.1f}B (강력 +2)']
    if net > 100_000_000:
        return 1, [f'BTC ETF 5일 순유입 ${net/1e9:.2f}B (+1)']
    if net < -1_000_000_000:
        return -2, [f'BTC ETF 5일 순유출 ${abs(net)/1e9:.1f}B (-2)']
    if net < -100_000_000:
        return -1, [f'BTC ETF 5일 순유출 ${abs(net)/1e9:.2f}B (-1)']
    return 0, [f'BTC ETF 흐름 평이 (${net/1e6:.0f}M)']


# ============================================================
#  F. 과열 심리
# ============================================================

def score_sentiment(fng: int | None, kimchi_premium: float | None) -> tuple[int, list[str]]:
    """
    fng:           Fear & Greed 지수 0~100
    kimchi_premium: 김치프리미엄 % (양수=업비트가 비쌈)
    """
    if fng is None:
        return 0, ['감정 데이터 부족']

    reasons = [f'F&G {fng}']
    score = 0

    if fng <= 20:
        score = 2; reasons.append('극공포 → 역발상 매수 신호 (+2)')
    elif fng <= 40:
        score = 1; reasons.append('공포 (+1)')
    elif fng <= 60:
        score = 0; reasons.append('중립')
    elif fng <= 75:
        score = -1; reasons.append('탐욕 (-1)')
    else:
        score = -2; reasons.append('극탐욕 (-2)')

    if kimchi_premium is not None:
        if kimchi_premium > 5:
            score = max(-2, score - 1)
            reasons.append(f'김치프리미엄 {kimchi_premium:.1f}% 과열 (-1)')
        elif kimchi_premium < -2:
            score = min(2, score + 1)
            reasons.append(f'김치디스카운트 {kimchi_premium:.1f}% (+1, 한국 매수 기회)')
        else:
            reasons.append(f'김치프리미엄 {kimchi_premium:+.1f}%')

    return max(-2, min(2, score)), reasons


# ============================================================
#  종합 판정
# ============================================================

VERDICT_TABLE = [
    (7,  '강한 매수',  'strong_buy',   '🟢', 'BTC ETF 비중 최대치까지 확대. 분할매수 자제하고 적극 진입.'),
    (4,  '분할매수',  'buy',          '🟢', '주차별 분할매수 권장. 시장 추세 우호적.'),
    (1,  '보유',      'hold',         '🟡', '현 비중 유지. 신규매수는 신중.'),
    (-3, '관망',      'wait',         '🟡', '신규매수 보류. 시장 방향성 불분명.'),
    (-99,'현금화',    'cash_out',     '🔴', '비중 축소·현금 확대. 추가 하락 대비.'),
]


def compute_total(scores: dict) -> dict:
    """6개 영역 점수 합산 + 판정 + 등급."""
    keys = ['liquidity', 'halving', 'btc_trend', 'volume', 'etf', 'sentiment']
    total = sum(scores.get(k, 0) for k in keys)

    for threshold, label, code, emoji, advice in VERDICT_TABLE:
        if total >= threshold:
            return {
                'total': total,
                'verdict': label,
                'code': code,
                'emoji': emoji,
                'advice': advice,
            }
    # never reached
    return {'total': total, 'verdict': '현금화', 'code': 'cash_out', 'emoji': '🔴', 'advice': ''}


def grade(score: int) -> str:
    """개별 영역 점수에 따른 색상 코드."""
    if score >= 2: return 'strong-pos'
    if score >= 1: return 'pos'
    if score == 0: return 'neutral'
    if score >= -1: return 'neg'
    return 'strong-neg'
