# SI Crypto Intelligence System

> 매일 새벽 7시 30분(KST) 자동으로 비트코인·알트코인 시장을 분석하고, **ETF 매매 판단 리포트**를 생성합니다.
> 자동매매 없음. 투자 판단 보조만.

## 페이지 구성

| 페이지 | URL | 내용 |
|---|---|---|
| 대시보드 | `/` | 오늘의 시장 점수·판정 (강한매수/분할매수/보유/관망/현금화) |
| 알트 스캐너 | `/scanner.html` | 상위 10개 코인 분석 + 6단계 판정 |
| ETF 가이드 | `/etf_guide.html` | 코인→ETF 매핑, 행동 권고 |
| 리스크 센터 | `/risk_center.html` | Risk On / Neutral / Off 신호등 |
| 저널·백테스트 | `/journal.html` | 일별 판단 기록 + 백테스트 |

## Phase 1 (MVP) — 현재 단계

✅ **포함된 것:**
- Market Dashboard (메인 대시보드)
- 6개 영역 점수 (유동성·반감기·BTC추세·거래량·ETF·심리)
- 종합 판정 (5단계)
- 상위 5개 코인 미리보기
- SQLite 일별 저장 (저널·백테스트 원천)
- ETF 가격 자동 갱신 (포트폴리오 페이지용)

⏳ **다음 단계(Phase 2~4):**
- 알트코인 스캐너 (코인 클릭 시 펼침 + AI 해설)
- ETF 매매 가이드 페이지
- 리스크 센터 페이지
- 저널·백테스트 페이지
- 포트폴리오 (기존 주식과 동일 UX)

## 셋업

### 1) GitHub 저장소 생성

이름: `si-crypto-v1`, **Public**

### 2) 파일 업로드

이 폴더 안 모든 파일을 저장소에 업로드 (zip 해서 한 번에 또는 개별).

`.github/`, `templates/`, `.py`, `.md`, `.txt` 모두 포함.

### 3) GitHub Pages 활성화

`Settings` → `Pages` → **Source: GitHub Actions** 선택

### 4) Actions 권한

`Settings` → `Actions` → `General` → **Read and write permissions** → Save

### 5) (선택) 매크로 데이터 정확도 향상

**FRED API 키 등록 (무료, 5분):**

1. https://fred.stlouisfed.org/docs/api/api_key.html 가입
2. 키 발급
3. GitHub `Settings` → `Secrets and variables` → `Actions` → `New repository secret`
4. Name: `FRED_API_KEY`, Secret: 발급받은 키

키 없어도 작동하지만, Fed 금리·M2 점수 일부는 폴백 값을 씁니다.

### 6) 첫 실행

`Actions` → `Daily SI Crypto Report` → `Run workflow`

1~2분 후 완료. URL: `https://[username].github.io/si-crypto-v1/`

이후 매일 새벽 7시 30분(KST) 자동 실행.

## 점수 시스템

각 영역 **-2 ~ +2점**, 총합 -12 ~ +12.

| 영역 | 데이터 소스 | 핵심 지표 |
|---|---|---|
| A. 유동성 | FRED, Yahoo | Fed 금리, DXY, M2 |
| B. 반감기 | 내부 계산 | 2024-04-19 기준 D+N일 |
| C. BTC 추세 | Yahoo | 50일선/200일선, 골든·데드크로스 |
| D. 거래량 | CoinGecko | 5일 vs 20일 평균 |
| E. ETF·온체인 | Farside | BTC 현물 ETF 순유입 |
| F. 과열 심리 | Alternative.me, Upbit | F&G, 김치프리미엄 |

### 판정 기준

| 합산 | 판정 | 행동 |
|---|---|---|
| **+7 이상** | 🟢 강한 매수 | BTC ETF 비중 최대치 |
| **+4 ~ +6** | 🟢 분할매수 | 주차별 분할매수 |
| **+1 ~ +3** | 🟡 보유 | 현 비중 유지 |
| **-3 ~ 0** | 🟡 관망 | 신규매수 보류 |
| **-4 이하** | 🔴 현금화 | 비중 축소 |

## 분석 대상 코인 (시총 상위 10)

BTC, ETH, SOL, XRP, BNB, DOGE, ADA, AVAX, LINK, SUI

## 코인 → ETF 매핑

| 코인 | 매수 ETF (미국) |
|---|---|
| BTC | IBIT, FBTC, BITB, GBTC |
| ETH | ETHA, ETHE, FETH |
| SOL | SOLZ (선물) |

## 비용

| 항목 | 월 비용 |
|---|---|
| GitHub Pages | 무료 |
| GitHub Actions | 무료 (2000분/월) |
| CoinGecko, Yahoo, Alternative.me, FRED | 무료 |
| **합계** | **0원** |

(Phase 3에서 Claude API 연동 시 약 $1~3/월 추가)

## 면책

- 데이터: CoinGecko, Yahoo Finance, Upbit, FRED, Alternative.me, Farside Investors
- **투자 참고용**. 매수·매도 권유 아님.
- 암호화폐 ETF는 변동성이 매우 큰 자산. 단기간 큰 손실 가능.
- 투자 판단과 손익 책임은 전적으로 투자자 본인.
