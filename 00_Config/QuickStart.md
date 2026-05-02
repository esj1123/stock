# QuickStart (프로젝트 운영 가이드)

<!-- STOCK-MVP-QUICKSTART:START -->

## 2026 MVP 운영 모델

이 Vault는 **NH투자증권 / NAMUH 엑셀 기반 개인 투자 모니터링 시스템**입니다. 목표는 자동매매가 아니라 포트폴리오 점검, 투자 논리 추적, 리스크 리뷰, 반복 가능한 투자 리뷰 루틴을 만드는 것입니다.

### 1. Vault purpose
- NH/NAMUH Excel 기반 개인 투자 모니터링
- 포트폴리오 대시보드와 계좌/시장/자산군 노출 점검
- 거래와 현금흐름 정규화
- 회사별 투자 논리, 보유 근거, 매도 기준 관리
- 리스크 이벤트, 의사결정, 리뷰 리포트 관리
- 소스 라이브러리와 투자 지식 관리

### 2. Data flow
```text
NH Excel files
→ 70_Imports/raw/
→ Python import
→ 70_Imports/processed/
→ CSV / SQLite
→ Obsidian dashboards and notes
```

### 3. Raw file rule
- `70_Imports/raw/`의 원본 증권사 파일은 불변 자료입니다.
- 다운로드한 파일을 직접 수정, 정렬, 필터, 재저장하지 않습니다.
- `70_Imports/processed/`의 CSV/SQLite는 raw 파일에서 다시 생성할 수 있는 산출물입니다.

### 4. What Obsidian stores
- 회사별 thesis와 보유 근거
- 매수/보유/축소/매도 판단 기준
- 리뷰 노트, 리스크 이벤트, 의사결정 기록
- 원천자료 링크와 Source Note
- AI 또는 Python이 생성한 요약과 점검 큐

### 5. What Obsidian does not store
- 계좌 비밀번호, 주문 비밀번호
- API key, API secret, access token
- 인증서 데이터, 로그인 ID
- 주민등록번호, 전화번호, 주소
- raw transaction table의 유일한 원본

### 6. User operating rule
- **-10% 하락은 자동 매도 규칙이 아니라 mandatory review trigger**입니다.
- 단순 가격 하락보다 펀더멘털 훼손이 더 중요한 축소/매도 기준입니다.
- 레버리지 ETF는 개별 주식과 별도 규칙으로 관리합니다.
- 자동 주문 실행과 실시간 증권 API 주문은 MVP 범위에서 제외합니다.
- 생성 노트와 대시보드는 사용자가 검토한 뒤 판단에 반영합니다.

### 7. Initial workflow
1. NH/NAMUH 엑셀 파일을 `70_Imports/raw/`에 넣습니다.
2. `cd 70_Imports/scripts` 후 dry-run import를 실행합니다.
3. full import를 실행해 `70_Imports/processed/`를 갱신합니다.
4. `10_Dashboard/Import_Review.md`를 확인합니다.
5. `10_Dashboard/Risk_Watchlist.md`를 확인합니다.
6. thesis와 sell criteria가 빠진 보유종목을 채웁니다.
7. QA를 실행합니다.
8. Portfolio, Exposure, Cashflows, Review Queue를 순서대로 봅니다.

<!-- STOCK-MVP-QUICKSTART:END -->


이 문서는 이 Vault를 **“엑셀 → 원장(DB) → 노트 → 대시보드”** 흐름으로 운용하기 위한 빠른 가이드입니다.

- 파일/폴더 이름: **영어**
- 노트 본문(설명/가이드): **한글**

---

## 0) 필수 플러그인

필수:
- Dataview
  - Dataview 설정에서 **Enable JavaScript Queries** 켜기

권장(자동화):
- QuickAdd
  - `00_Config/QuickAdd/README.md` 참고

선택(원하면):
- Templater (템플릿 자동 생성)
- Calendar / Periodic Notes (일지 루틴)
- Tasks (할 일 관리)

---

## 0.5) SETUP (최초 1회 / 환경 점검)

처음 한 번은 아래 문서대로 “체크리스트 방식”으로 세팅하는 것을 추천합니다.
- [[00_Config/Setup_Checklist|Setup Checklist(초기 셋업 체크리스트)]]

Quick 체크리스트:
- [ ] Obsidian → Community plugins 사용 허용
- [ ] Dataview 설치
- [ ] Dataview → **Enable JavaScript Queries** ON
- [ ] (권장) QuickAdd 설치 → `Stock Command Center` 매크로 생성(00_Config/QuickAdd/README 참고)
- [ ] (선택) Templater 설치 → 템플릿 폴더 경로를 `99_Templates/`로 지정
- [ ] (선택) Python 3.x 설치(엑셀 임포트용)
- [ ] (선택) Codex로 자동/반자동 실행하고 싶으면: `00_Config/Codex_Automation.md` 참고

---

## 1) 저장 구조(요약)

> **원본(raw)은 수정 금지**, “정규화(ledger) + 노트”는 자동 생성(권장)입니다.

- 원본 데이터(raw, 수정 금지): `70_Imports/raw/`
- 정규화 DB(검증/감사/이식): `70_Imports/processed/namoo_ledger.csv`
- 분류 실패/점검: `70_Imports/review/`
- 거래 노트(자동 생성): `30_Trades/<TICKER>/`
- 입출금 노트(자동 생성): `31_Cashflows/`
- 기업 폴더(리서치/이벤트): `20_Companies/<TICKER>/`
- 대시보드(“보는 화면”): `10_Dashboard/`
- 투자 원칙(헌법/루틴/환율): `05_Principles/`
- 지식(개념/전략/체크리스트): `40_Knowledge/`
- 자료 요약(Source Note): `60_Library/`
- 첨부(PDF/캡처): `90_Attachments/`
- 템플릿: `99_Templates/`

---

## 2) 기본 운영 루틴(반자동)

### Step 1) 나무증권에서 파일(.xls/.xlsx) 다운로드 → Raw에 저장 (중요)

이 Vault는 **“나무증권에서 내려받은 파일(.xls/.xlsx)”**을 Raw로 보관하고,
그 Raw를 기반으로 정규화(DB) + 노트를 생성합니다.

원칙:
- `70_Imports/raw/`에 넣은 **원본 파일은 수정/정렬/필터/재저장 금지**
- 매번 “최근 N일”을 **겹치게** 내려받아(오버랩) 누락/정산 지연을 흡수

추가 안내:
- [x] 나무에서 내려받은 .xls는 **진짜 엑셀**이 아니라 **HTML 테이블**인 경우가 많습니다(확장자만 xls). 그대로 raw에 넣으면 됩니다.
- [x] 파일명은 **다운로드 그대로** 써도 되며, 계좌를 구분하려면 파일명 **맨 끝**에 `(종합)` / `(ISA)` 같은 태그를 붙여도 됩니다. (단 `(내용)`은 무시)


#### 1) 어떤 엑셀을 내려받아야 하나?
가져올 것(가능한 것부터):
- [x] **종합 거래내역(매수/매도/배당/수수료/세금 포함)**
- [ ] **입출금/이체 내역(입금/출금/이체)**
- [ ] (해외) 해외주식 거래내역
- [ ] (선택) 환전/외화매매 내역(가능하면)

> “보유잔고(현재 보유현황) 엑셀”은 증권사에서 별도 제공되는 경우가 있는데,
> 이 Vault는 우선 **거래내역 기반으로 보유수량/평단을 계산**합니다.
> 과거 내역을 다 받기 어렵다면 `70_Imports/templates/initial_holdings_template.xlsx`로 **초기 잔고**를 넣고 시작할 수 있습니다.

#### 2) 다운로드 방법 A (권장): **나무증권 PC 웹**에서 ‘종합거래내역’ 엑셀 저장

> UI가 조금 바뀌어도 핵심은 동일합니다: **종합거래내역 조회 → 엑셀 저장**

1) PC에서 나무증권 접속/로그인
- 일부 안내에서는 거래내역 조회를 위해 **ID 로그인**을 권장하기도 합니다.

2) 메뉴 이동
- **뱅킹/계좌정보 → 거래내역 → 종합거래내역**

3) 계좌 선택 + 기간 설정
- 계좌번호 선택
- 조회 기간 설정 → 조회

4) 엑셀 저장
- 화면의 **엑셀 저장**(또는 저장/다운로드) 버튼으로 `.xlsx` 저장

5) (자주 발생) 기간 제한이 있으면 분할 다운로드
- 종합거래내역 조회 기간이 **100일 제한**처럼 걸리는 경우가 있어서,
  이때는 3개월 단위 등으로 **쪼개서 여러 번** 내려받으면 됩니다.

6) (선택) 주식만 보고 싶다면 필터
- 외화매매(환전) 등을 빼고 주식만 보고 싶다면, **상세 조건에서 상품 구분을 ‘주식’**으로 선택해서 조회하는 방식이 안내되기도 합니다.


#### 3) 다운로드 방법 B: **나무 HTS(PC 프로그램)**에서 엑셀 저장

PC 웹보다 HTS가 더 편한 분은 이 방법이 안정적입니다.

- 메뉴 예시(국내 종합거래내역):
  - **계좌 → 주식 종합거래내역 → 8203 종합 거래내역 조회**
- 기간/계좌 설정 → 조회
- 화면의 **[출력]** 버튼 → 새 창에서 **엑셀 아이콘** 선택 → 저장

- 해외주식(예시):
  - **해외주식 → 잔고 및 거래내역 → 6062 해외주식 거래내역**


#### 4) 다운로드 방법 C: **MTS(모바일 앱)**에서 조회 후 저장(가능하면)

앱 버전/기기(OS)에 따라 “엑셀 저장”이 없고 PDF/이미지 저장만 있을 수 있습니다.
엑셀이 필요하면 **PC 웹/HTS 방식이 가장 확실**합니다.

- 예시 흐름(입출금/이체내역):
  - 앱 실행 → 로그인 → **MY 또는 계좌** → **이체내역/입출금 내역** → 기간 설정 → 조회 → 저장


#### 5) 저장 위치 + 파일명 규칙(선택)

저장 위치:
- `70_Imports/raw/` (원본은 수정 금지)

파일명은 자유입니다(다운로드 기본 이름 그대로 OK).

(선택) 정리용으로 파일명을 바꾸고 싶다면 예시:
- `namoo_trades_YYYYMMDD-YYYYMMDD.xls` 또는 `.xlsx`
- `namoo_cash_YYYYMMDD-YYYYMMDD.xls` 또는 `.xlsx`
- (해외) `namoo_overseas_trades_YYYYMMDD-YYYYMMDD.xls` 또는 `.xlsx`

(선택) 계좌 구분이 필요하면 파일명 맨 끝에 태그를 붙이세요:
- `...(종합).xls` → account: "종합"
- `...(ISA).xls` → account: "ISA"

#### 6) ‘다운받은 직후’ 10초 점검(중요)

- [x] 확장자가 `.xls` 또는 `.xlsx`인지 확인(둘 다 OK)
- [ ] 첫 행이 “헤더(열 제목)”로 보이는지 확인
- [ ] 날짜/종목코드/구분/수량/단가/금액/수수료/세금/통화 같은 컬럼이 대략 존재하는지 확인
- [ ] 파일을 열어봤다면, **저장/다른 이름으로 저장하지 말고 닫기**(원본 손상 방지)

---

### Step 2) Import 실행 (DB + 노트 생성)

옵션 A(추천): Obsidian 안에서 QuickAdd로 실행
- [ ] Command palette → **Stock Command Center** 실행
- [ ] `A) Import 실행 + 리포트 생성 + 대시보드 열기` 선택
- 기대 결과: `70_Imports/logs/Import_Run_...md` 리포트가 생성되고 자동으로 열림

옵션 B: Vault 루트(터미널)에서 실행:
- [ ] 의존성 설치
  - `pip install -r 70_Imports/scripts/requirements.txt`
- [ ] (테스트) 파일 생성 없이 점검
  - `python 70_Imports/scripts/main.py import --vault-root . --raw-dir 70_Imports/raw --dry-run`
- [ ] 실행
  - `python 70_Imports/scripts/main.py all --vault-root . --raw-dir 70_Imports/raw --create-companies`

> Codex로 “명령만 말해서” 실행하고 싶으면
> - `00_Config/Prompts/` (프롬프트 카드)
> - `00_Config/Codex_Automation.md`
> 를 참고하세요.

---

### Step 3) Import 결과 점검(필수)

- [ ] `10_Dashboard/Import_Review`에서 **UNCLASSIFIED / 누락** 확인
- [ ] `70_Imports/review/`에 모인 행을 보고 **열 이름 매핑/키워드 규칙 튜닝**

---

### Step 4) 기업 메타데이터 최소 입력

각 기업 폴더의 `Company.md`에서(가능한 것부터):
- [ ] `sector` (섹터)
- [ ] `country` (국가)
- [ ] `currency` (KRW/USD 등)
- [ ] `price_now` (선택: 평가액/미실현손익용)
- [ ] `last_update` (선택: 업데이트 큐용)

---

### Step 5) 대시보드 확인(“보는 화면”)

권장 확인 순서:
- `10_Dashboard/Start_Here`
- `10_Dashboard/Portfolio`
- `10_Dashboard/Exposure`
- `10_Dashboard/Cashflows`
- `10_Dashboard/Companies`
- `10_Dashboard/Earnings_Calendar`
- `10_Dashboard/Library_Index`
- `10_Dashboard/Strategy_Performance`

---

## 2.5) 운영 주기(내 기준을 고정)

> 아래는 “내 기준”을 적어두는 섹션입니다. (팀/가족과 공유해도 좋음)

- Import 주기: [ ] 주 1회  [ ] 2주 1회  [ ] 월 1회  [ ] 기타: ______
- 엑셀 다운로드 기간(오버랩): [ ] 30일  [ ] 60일  [ ] 90일  [ ] 기타: ______
- `price_now` 갱신: [ ] 매일  [ ] 주 1회  [ ] 월 1회  [ ] 필요 시
- 환율(FX) 갱신: [ ] 매일  [ ] 주 1회  [ ] 월 1회  [ ] 필요 시
- 실적/이벤트 리뷰: [ ] 실적 전/후  [ ] 월 1회  [ ] 분기 1회

---

## 3) 실적/이벤트 루틴(선택)

- 작성 위치: `20_Companies/<TICKER>/Events/`
- 템플릿: `99_Templates/Earnings_Pre`, `99_Templates/Earnings_Post`
- 확인 화면: `10_Dashboard/Earnings_Calendar`

---

## 4) 자료/지식 쌓기 루틴(선택)

- 자료 요약(Source Note): `60_Library/`
  - Source Note에 `tickers: ["..."]` 형태로 연결(필요 시)
- 지식/체크리스트: `40_Knowledge/`
- 첨부 파일: `90_Attachments/` (PDF/캡처/이미지)

---

## 5) 투자 원칙(헌법) 유지 관리(추천)

- `05_Principles/Investment_Policy_Statement`
- `05_Principles/Risk_Management_Rules`
- `05_Principles/Buy_Sell_Rules`
- `05_Principles/Review_Routine`

리뷰 주기(선택): [ ] 월 1회  [ ] 분기 1회  [ ] 반기 1회  [ ] 연 1회

---

## 6) 튜닝/문제 해결 체크리스트

### 6.1) 분류 실패(UNCLASSIFIED)가 많다
- [ ] 엑셀의 “열 제목(헤더)”이 어떤지 확인
- [ ] `70_Imports/scripts/README.md`와 import pipeline 규칙 튜닝 대상으로 기록

### 6.2) 종목코드(0패딩) / 티커가 깨진다
- [ ] 엑셀에서 종목코드가 숫자로 인식되어 앞자리 0이 사라졌는지 확인
- [ ] 임포트 결과의 ticker 정규화 규칙 확인

### 6.3) 중복이 생긴다 / 중복이 없어야 하는데 생긴다
- [ ] 같은 기간을 여러 번 내려받았는지 확인
- [ ] `import_id` 생성 기준(날짜/금액/메모 등) 확인

### 6.4) 통화(KRW/USD) 합산이 이상하다
- [ ] 같은 표에서 통화를 섞어 보고 있는지 확인
- [ ] `05_Principles/FX_Rates` 값이 비어있는지 확인

---

## 7) 나중에 확장(메모)

- [ ] API 연동(잔고/시세/환율 자동)
- [ ] IRR/TWR 성과 측정(입출금 포함)
- [ ] trade_id 라운드트립 기반 승률/기대값(스케일 인/아웃 포함)

---

마지막 업데이트: 2026-03-02
