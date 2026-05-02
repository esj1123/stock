# Setup Checklist (초기 셋업 체크리스트)

이 문서는 이 Vault를 **처음 세팅할 때**(또는 다른 PC로 옮겼을 때)
체크리스트 형태로 빠르게 점검하기 위한 문서입니다.

> 목표: “엑셀 → Import → 대시보드” 루프가 **최소 1회 정상 동작**하도록 만들기

---

## A. Obsidian 기본

- [ ] ZIP 압축 해제 후, Obsidian에서 **Open folder as vault**로 열었는가?
- [ ] Vault 안 폴더/파일 이름이 그대로 보이는가? (`00_Config/`, `10_Dashboard/` 등)

---

## B. 플러그인

### Dataview (필수)
- [ ] Settings → Community plugins → **Turn on community plugins**
- [ ] Community plugins → Browse → **Dataview** 설치
- [ ] Dataview 설정에서 **Enable JavaScript Queries** ON

### QuickAdd (권장: “한 번에 실행” 자동화)
- [ ] QuickAdd 설치/활성화
- [ ] QuickAdd → Manage Macros → 새 매크로 생성
  - [ ] Choice: **Script**
  - [ ] Script 파일: `00_Config/QuickAdd/Stock_Command_Center.js`
  - [ ] 매크로 이름(예): `Stock Command Center`
- [ ] 기대 결과: 매크로 실행 시 메뉴가 뜨고,
  - [ ] Import 실행 후 `70_Imports/logs/Import_Run_...md` 리포트가 생성되어 자동으로 열린다.

> 참고: QuickAdd로 Import를 실행하는 기능은 데스크탑에서만(외부 명령 실행) 안정적으로 동작합니다.

### (선택) Templater
- [ ] Templater 설치
- [ ] Template folder location을 `99_Templates/`로 지정

---

## C. Import 실행 환경(Python)

### 1) Python 설치
- [ ] Python 3.x가 설치되어 있는가?
- [ ] 터미널에서 `python --version` 또는 `python3 --version`이 동작하는가?

### 2) Vault 루트에서 실행
- [ ] 현재 터미널 경로가 Vault 루트인지 확인했는가?
  - `00_Config/`, `70_Imports/`가 보이는 위치

### 3) 의존성 설치
- [ ] `pip install -r 70_Imports/scripts/requirements.txt`

> Tip: 충돌을 피하려면 가상환경(venv)을 권장합니다.

---

## D. Raw 엑셀 준비(가장 중요)

- [ ] 나무증권에서 내려받은 `.xls` 또는 `.xlsx` 파일이 있는가?
- [ ] 그 파일을 **수정하지 않고** `70_Imports/raw/`에 넣었는가?
- [ ] (권장) 파일명이 구분되게 되어 있는가?
  - 예: (다운로드 파일명 그대로 OK) 또는 정리용으로 `namoo_trades_YYYYMMDD-YYYYMMDD.xls`, `namoo_cash_YYYYMMDD-YYYYMMDD.xls`
  - (선택) 계좌 구분이 필요하면 파일명 맨 끝에 `(종합)`/`(ISA)` 같은 태그를 붙여도 됩니다.

> “엑셀 다운로드 방법”은 `00_Config/QuickStart.md`의 Step 1에 자세히 적어두었습니다.

---

## E. Import 1회 실행(스모크 테스트)

### 방법 1) QuickAdd로 실행(추천)
- [ ] Command palette → `Stock Command Center` 실행
- [ ] `A) Import 실행...` 선택
- [ ] 리포트 노트가 생성/오픈되는지 확인

### 방법 2) 터미널에서 실행
- [ ] 테스트(파일 생성 없이):
  - [ ] `python 70_Imports/scripts/namoo_excel_import.py --dry-run`

- [ ] 실제 실행:
  - [ ] `python 70_Imports/scripts/namoo_excel_import.py --create-companies`

생성/갱신되는 산출물(정상 체크):
- [ ] `70_Imports/processed/namoo_ledger.csv` 생성됨
- [ ] `30_Trades/<TICKER>/...` 거래 노트가 생성됨
- [ ] `31_Cashflows/...` 입출금 노트가 생성됨(입출금 엑셀이 있을 때)
- [ ] `20_Companies/<TICKER>/Company.md` 기업 노트가 생성됨(옵션 `--create-companies`)

---

## F. Import 결과 점검(필수)

- [ ] `10_Dashboard/Import_Review.md`를 열었을 때 표가 보이는가?
- [ ] `70_Imports/review/`에 UNCLASSIFIED 노트가 많이 쌓였는가?
  - [ ] 엑셀 헤더(열 제목) 차이일 가능성이 높음
  - [ ] `70_Imports/scripts/namoo_excel_import.py`의 `COLUMN_SYNONYMS` / 키워드 규칙 튜닝 대상으로 기록

---

## G. 대시보드 렌더링 확인

- [ ] `10_Dashboard/Portfolio.md`에서 종목별 표가 보이는가?
- [ ] `10_Dashboard/Cashflows.md`에서 입출금 요약이 보이는가?
- [ ] `10_Dashboard/Exposure.md`에서 섹터/국가/통화 노출도가 보이는가?

> 현재가(`price_now`)와 섹터/국가/통화는 `20_Companies/<TICKER>/Company.md`에 채워야 더 정확해집니다.

---

## H. (선택) Codex로 반자동 실행

- [ ] `00_Config/Codex_Automation.md`를 읽었는가?
- [ ] `00_Config/Prompts/`의 프롬프트 카드를 확인했는가?

---

## I. (선택) 과거 내역 없이 “현재 보유현황부터” 시작

과거 거래내역을 한 번에 받기 어렵다면:
- [ ] `70_Imports/templates/initial_holdings_template.xlsx`에 보유종목/수량/평단을 입력
- [ ] 저장 후 `70_Imports/raw/`에 넣고 Import 실행
