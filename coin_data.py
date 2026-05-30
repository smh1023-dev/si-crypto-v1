"""상위 10개 코인 메타 + 코인→ETF 매핑."""

# 시총 상위 10개 코인 (분석 대상). CoinGecko ID 기준.
TOP_COINS = [
    {'id': 'bitcoin',    'symbol': 'BTC',  'name': '비트코인',     'upbit': 'KRW-BTC'},
    {'id': 'ethereum',   'symbol': 'ETH',  'name': '이더리움',     'upbit': 'KRW-ETH'},
    {'id': 'solana',     'symbol': 'SOL',  'name': '솔라나',       'upbit': 'KRW-SOL'},
    {'id': 'ripple',     'symbol': 'XRP',  'name': '리플',         'upbit': 'KRW-XRP'},
    {'id': 'binancecoin','symbol': 'BNB',  'name': '바이낸스코인', 'upbit': None},
    {'id': 'dogecoin',   'symbol': 'DOGE', 'name': '도지코인',     'upbit': 'KRW-DOGE'},
    {'id': 'cardano',    'symbol': 'ADA',  'name': '에이다',       'upbit': 'KRW-ADA'},
    {'id': 'avalanche-2','symbol': 'AVAX', 'name': '아발란체',     'upbit': 'KRW-AVAX'},
    {'id': 'chainlink',  'symbol': 'LINK', 'name': '체인링크',     'upbit': 'KRW-LINK'},
    {'id': 'sui',        'symbol': 'SUI',  'name': '수이',         'upbit': 'KRW-SUI'},
]

# 코인 → 살 수 있는 ETF 매핑 (사장님은 ETF로 매매)
COIN_TO_ETF = {
    'BTC': [
        {'ticker': 'IBIT', 'name': 'iShares Bitcoin Trust',     'kind': '현물', 'market': '미국'},
        {'ticker': 'FBTC', 'name': 'Fidelity Wise Origin Bitcoin', 'kind': '현물', 'market': '미국'},
        {'ticker': 'BITB', 'name': 'Bitwise Bitcoin ETF',       'kind': '현물', 'market': '미국'},
        {'ticker': 'GBTC', 'name': 'Grayscale Bitcoin Trust',   'kind': '현물', 'market': '미국'},
    ],
    'ETH': [
        {'ticker': 'ETHA', 'name': 'iShares Ethereum Trust',    'kind': '현물', 'market': '미국'},
        {'ticker': 'ETHE', 'name': 'Grayscale Ethereum Trust',  'kind': '현물', 'market': '미국'},
        {'ticker': 'FETH', 'name': 'Fidelity Ethereum Fund',    'kind': '현물', 'market': '미국'},
    ],
    'SOL': [
        {'ticker': 'SOLZ', 'name': 'Solana Futures ETF',        'kind': '선물', 'market': '미국'},
    ],
}

# 광역 (분산투자용)
BLOCKCHAIN_ETFS = [
    {'ticker': 'BITQ', 'name': 'Bitwise Crypto Industry Innovators ETF', 'kind': '주식', 'market': '미국'},
    {'ticker': 'BLOK', 'name': 'Amplify Transformational Data Sharing',  'kind': '주식', 'market': '미국'},
]

# 다음 BTC 반감기 (2028년 4월 예정 — 추정)
NEXT_HALVING_DATE = '2028-04-15'
LAST_HALVING_DATE = '2024-04-19'
