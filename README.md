# 상장사 재무분석 대시보드

OpenDART 재무 데이터를 활용해 국내 상장사의 최근 5개년 재무 흐름과 LTM 값을 시각화하는 Streamlit 대시보드입니다. XBRL 기반 계정 정규화를 통해 회사와 연도마다 달라지는 재무제표 계정명을 안정적으로 비교할 수 있도록 설계했습니다.

## 프로젝트 소개

국내 기업 재무제표는 같은 경제적 의미의 계정이라도 회사, 연도, 재무제표 종류에 따라 표시명이 달라질 수 있습니다. 예를 들어 매출은 `매출액`, `수익(매출액)`, `영업수익`처럼 나타날 수 있고, 당기순이익은 분기·반기 보고서에서 `분기순이익(손실)` 또는 `반기순이익(손실)`처럼 나타날 수 있습니다.

이 프로젝트는 한국어 계정명만 비교하는 방식의 한계를 줄이기 위해 XBRL `account_id`를 우선 매칭합니다. 계정 ID와 허용된 재무제표 섹션을 함께 확인하고, 예외적인 확장 taxonomy나 특수 표기에는 정확한 `account_nm` fallback을 사용합니다.

## 주요 기능

- 3,976개 상장사 검색
- 시장구분, 대표이사, 업종코드, 주소 등 기업 개황 표시
- 연결재무제표(CFS) / 별도재무제표(OFS) 선택
- 최근 5개 사업연도 사업보고서 재무 데이터 수집
- 지원 손익계산서 계정의 LTM 계산
- 20개 표준 재무 계정 정규화
- 여러 계정 동시 선택 및 비교
- Line chart / Bar chart 전환
- 선택형 선형 추세선
- 안정적인 계정별 색상, 커스텀 범례, 한국어 hover tooltip
- 쉼표 포맷 금액 표시
- 따뜻한 크림 톤의 라이트 UI

## 핵심 기술 설계

재무 계정 추출은 두 단계로 동작합니다.

1. `account_id` + 허용된 `sj_nm` + 제외 규칙으로 우선 매칭
2. 필요한 경우 정확한 `account_nm` fallback

예시:

- `매출액`, `수익(매출액)`, `영업수익` → `ifrs-full_Revenue`
- `당기순이익`, `분기순이익`, `반기순이익`, `분기순이익(손실)` → `ifrs-full_ProfitLoss`

이 방식은 회사별 한국어 라벨 차이를 계속 패치하는 방식보다 안정적입니다. 특히 동일한 계정명이 손익계산서, 포괄손익계산서, 현금흐름표 등에 중복 등장하는 경우를 줄이기 위해 재무제표 섹션(`sj_nm`)도 함께 확인합니다.

## LTM 계산 방식

LTM은 다음 방식으로 계산합니다.

```text
LTM =
latest annual amount
+ current interim cumulative amount
- prior-year same-period cumulative amount from the same interim report
```

최신 유효 사업보고서를 찾은 뒤, 그 이후의 최신 분기성 보고서를 `3분기 → 반기 → 1분기` 순서로 확인합니다. 중간 보고서의 사업연도는 최신 사업보고서 연도보다 커야 합니다. LTM은 지원되는 손익계산서 계정에만 적용되며, 감사 수치나 예측 수치가 아닙니다.

## 데이터 흐름

```text
OpenDART API
→ raw JSON
→ XBRL account normalization
→ processed CSV
→ five-year and LTM calculation
→ interactive visualization
```

## 기술 스택

- Python
- Streamlit
- pandas
- Altair
- OpenDART API
- XBRL taxonomy
- python-dotenv

## 프로젝트 구조

```text
.
├─ app.py
├─ requirements.txt
├─ README.md
├─ data/
│  └─ processed/
│     ├─ company_list.csv
│     ├─ company_master.csv
│     └─ financial_statement.csv
└─ src/
   ├─ fetch_company_list.py
   ├─ build_company_master.py
   ├─ enrich_market_classification.py
   ├─ fetch_financial_statement.py
   ├─ extract_accounts.py
   └─ reset_financial_statement.py
```

`data/raw/`의 원본 JSON 파일은 런타임에 생성되며 Git에는 포함하지 않습니다.

## 스크린샷

현재 저장소에는 스크린샷 이미지가 포함되어 있지 않습니다. 배포 후 `docs/images/dashboard-main.png` 같은 경로에 메인 화면 이미지를 추가하는 것을 권장합니다.

## 로컬 실행 방법

1. 저장소를 클론합니다.
2. 가상환경을 생성하고 활성화합니다.
3. 의존성을 설치합니다.
4. `.env` 파일에 OpenDART API 키를 설정합니다.
5. Streamlit 앱을 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

`.env` 예시:

```text
DART_API_KEY=your_api_key
```

실제 API 키는 저장소에 커밋하지 않습니다.

## 데이터 준비

`company_list.csv`와 `company_master.csv`는 앱 실행에 필요한 기본 데이터로 포함되어 있습니다. `financial_statement.csv`는 데모용 초기 재무 데이터이면서, 사용자가 앱에서 재무 데이터를 가져올 때 업데이트됩니다.

원본 재무 JSON 파일은 `재무데이터 가져오기` 버튼을 누르면 `data/raw/` 아래에 생성됩니다. 회사 목록과 기업 마스터를 다시 만들 때는 아래 스크립트를 사용할 수 있습니다.

```bash
python3 src/fetch_company_list.py
python3 src/build_company_master.py
python3 src/enrich_market_classification.py
```

## 배포

Streamlit Community Cloud 배포 설정:

- Main file path: `app.py`
- Dependencies: `requirements.txt`
- Secret / environment variable: `DART_API_KEY`

이 저장소는 배포 준비용 구성을 포함하지만, 배포 자체는 아직 수행하지 않았습니다.

## 한계점

- 많은 호스팅 플랫폼에서 런타임 파일 쓰기는 ephemeral filesystem에 저장됩니다.
- `financial_statement.csv`와 raw JSON 쓰기는 동시 사용자 환경에서 concurrency-safe하지 않습니다.
- 이 프로젝트는 포트폴리오/demo 용도에 맞춘 구조입니다.
- OpenDART API의 가용성, 응답 구조, 호출 제한의 영향을 받습니다.
- 특수한 taxonomy 확장 계정은 표준화 범위 밖일 수 있습니다.
- EBITDA는 구현하지 않았습니다. 안정적인 EBITDA 계산에는 주석 수준 XBRL 파싱 구조가 별도로 필요합니다.

## 개발 과정에서 해결한 문제

1. 삼성전자 현금흐름 계정명이 공백 포함 형태로 제공되어 mapping을 보강했습니다.
2. LG전자 분기 보고서의 총순이익 계정명이 `분기순이익(손실)`로 제공되는 문제를 해결했습니다.
3. 대한항공처럼 연도별로 `매출`과 `영업수익` 계정 표기가 달라지는 사례를 검증했습니다.
4. `account_id` 우선 구조로 반복적인 한국어 라벨 패치를 줄였습니다.
5. LTM 계산을 위해 최신 유효 사업보고서와 중간 보고서 선택 규칙을 명확히 분리했습니다.

## 향후 개선 가능성

- 데이터베이스 또는 사용자별 세션 저장소 도입
- 파일 쓰기 잠금과 atomic write 적용
- 더 넓은 XBRL taxonomy coverage
- 주석 수준 XBRL 파싱
- 자동화 테스트 추가

## 저작권

© 2026 Yoon Seowon. All rights reserved.
