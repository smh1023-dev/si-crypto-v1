"""
매크로·온체인·ETF 흐름 데이터 수집.

  - Alternative.me: Fear & Greed 지수
  - FRED API: Fed 금리, M2 (API 키 필요, 없으면 yfinance/스크래핑 폴백)
  - Farside Investors: BTC ETF 순유입 (HTML 스크래핑)
"""
from __future__ import annotations
import logging
import os
import re
from datetime import datetime

import requests

log = logging.getLogger(__name__)


# ============================================================
#  Fear & Greed
# ============================================================

def get_fng() -> dict | None:
    """
    Alternative.me Fear & Greed.
    Returns: {value:int 0-100, classification:str}
    """
    try:
        r = requests.get('https://api.alternative.me/fng/?limit=1', timeout=10)
        d = r.json()['data'][0]
        return {
            'value': int(d['value']),
            'classification': d['value_classification'],
        }
    except Exception as e:
        log.warning("F&G 실패: %s", e)
        return None


# ============================================================
#  매크로 (FRED 또는 폴백)
# ============================================================

def get_fed_rate() -> float | None:
    """현재 Fed 금리. FRED API 키 있으면 사용, 없으면 None."""
    key = os.environ.get('FRED_API_KEY')
    if not key:
        return None
    try:
        # FEDFUNDS = Effective Federal Funds Rate
        r = requests.get(
            'https://api.stlouisfed.org/fred/series/observations',
            params={'series_id': 'DFF', 'api_key': key, 'file_type': 'json',
                    'sort_order': 'desc', 'limit': 1},
            timeout=15,
        )
        obs = r.json()['observations']
        if obs:
            return float(obs[0]['value'])
    except Exception as e:
        log.warning("FRED Fed rate 실패: %s", e)
    return None


def get_m2_growth() -> float | None:
    """M2 통화량 연간 증가율. FRED 키 필요."""
    key = os.environ.get('FRED_API_KEY')
    if not key:
        return None
    try:
        # M2SL = M2 Money Stock (단위: 십억 달러)
        r = requests.get(
            'https://api.stlouisfed.org/fred/series/observations',
            params={'series_id': 'M2SL', 'api_key': key, 'file_type': 'json',
                    'sort_order': 'desc', 'limit': 14},
            timeout=15,
        )
        obs = r.json()['observations']
        if len(obs) >= 13:
            now = float(obs[0]['value'])
            year_ago = float(obs[12]['value'])
            return (now / year_ago - 1) * 100
    except Exception as e:
        log.warning("FRED M2 실패: %s", e)
    return None


def guess_fed_direction() -> str:
    """
    Fed 방향성을 단순 휴리스틱으로 추정.
    실제 정확한 판단은 어려우니, 현재 시점(2026) 기준 '인하 사이클'을 기본값으로.
    추후 사장님이 수동 지정 가능하게 환경변수 FED_DIRECTION 지원.
    """
    env = os.environ.get('FED_DIRECTION', '').lower().strip()
    if env in ('cut', 'hike', 'hold'):
        return env
    # 2024~2026: 인하 사이클로 알려져 있음
    return 'cut'


# ============================================================
#  BTC ETF 순유입 (Farside Investors 스크래핑)
# ============================================================

def get_btc_etf_flows_5d() -> dict:
    """
    Farside Investors의 BTC ETF 일별 흐름 페이지를 가볍게 스크래핑.
    최근 5거래일 누적 순유입(달러).
    실패 시 0 반환.
    """
    try:
        r = requests.get(
            'https://farside.co.uk/bitcoin-etf-flow-all-data/',
            timeout=15,
            headers={'User-Agent': 'Mozilla/5.0'},
        )
        if r.status_code != 200:
            return {'btc_etf_5d_net_inflow_usd': 0, 'note': '데이터 미수신'}

        # Total 컬럼 추출 (간단 정규식 — 표 구조에 따라 조정 필요)
        # 각 행 마지막 셀이 누적 합. 데이터를 단순 파싱.
        text = re.sub(r'<[^>]+>', '|', r.text)  # 태그 제거 → 파이프 구분
        # 패턴: 날짜 / 숫자들 / total
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        # 가장 최근 5개 행에서 마지막 숫자 합산 (단위: million USD)
        recent_totals = []
        date_pattern = re.compile(r'\d{1,2}\s+\w{3}\s+\d{4}')
        for line in lines:
            if date_pattern.search(line):
                # 라인에서 숫자들 추출
                nums = re.findall(r'-?\d+\.?\d*', line.replace(',', ''))
                if nums:
                    try:
                        # 마지막 숫자 = total
                        total = float(nums[-1])
                        recent_totals.append(total)
                        if len(recent_totals) >= 5:
                            break
                    except ValueError:
                        continue
        if recent_totals:
            five_day_sum_million = sum(recent_totals)
            return {
                'btc_etf_5d_net_inflow_usd': five_day_sum_million * 1_000_000,
                'note': f'최근 {len(recent_totals)}일 합산',
            }
    except Exception as e:
        log.warning("Farside ETF flows 실패: %s", e)

    return {'btc_etf_5d_net_inflow_usd': 0, 'note': '데이터 없음'}
