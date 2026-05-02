# 주식 투자 옵시디언 Vault (complete-ko)

이 Vault는 **나무증권(NH투자증권)에서 Excel(엑셀)로 내려받은 내역**을 기반으로,
옵시디언에서 아래를 한 번에 관리할 수 있도록 만든 템플릿/대시보드 세트입니다.

- 거래 원장(매수/매도/배당/수수료/세금) DB화
- 포트폴리오(보유수량/평단/평가액/손익) 대시보드
- 섹터/국가/통화 노출도(Exposure) 대시보드
- 입출금(현금흐름) 기록/요약
- 기업별 폴더(Company folder)로 리서치/이벤트/자료를 묶어서 관리
- 투자 원칙(IPS, 리스크 룰, 매수/매도 룰, 루틴) 문서
- 자료 라이브러리(Source Note) / 지식(개념·전략·체크리스트) 축적

> **파일/폴더 이름은 영어**로 되어 있지만,
> **노트 내용(본문/템플릿/대시보드)은 한글**로 작성되어 있습니다.

---

## 0) 먼저 볼 것

- `00_Config/QuickStart.md` : 프로젝트 전체 운용 흐름(엑셀→DB→노트→대시보드)
  - **나무증권 엑셀 다운로드 절차**도 Step 1에 자세히 정리되어 있습니다.
- `00_Config/Setup_Checklist.md` : 최초 1회 셋업 체크리스트(스모크 테스트)
- `10_Dashboard/Start_Here.md` : 주요 대시보드 바로가기

(옵션)
- `00_Config/Codex_Automation.md` : Codex/스크립트로 Import 자동·반자동 운영
- `00_Config/Prompts/` : Codex에게 “그대로 실행”시키는 프롬프트 카드 모음

---

## 1) 처음 설치(필수)

### (1) Vault 열기
1. ZIP 압축 해제
2. Obsidian → **Open folder as vault** → 이 폴더를 선택

### (2) Dataview 플러그인 설치
대시보드(Portfolio/Exposure 등)는 Dataview가 필요합니다.

1. Settings → Community plugins → **Turn on community plugins**
2. Browse → **Dataview** 설치
3. Dataview 설정에서 **Enable JavaScript Queries** 를 켭니다.

---

## 2) “엑셀로 DB화” 워크플로우(추천)

### (1) 나무에서 Excel 다운로드
- 종합 거래내역(매수/매도/배당 등) Excel
- 입출금(이체/입금/출금) Excel
- 해외주식 하시면 해외주식 거래내역 Excel도 추가

> 자세한 절차/파일명 규칙/기간 오버랩은 `00_Config/QuickStart.md` Step 1 참고

### (2) 원본 Excel 저장 (수정 금지)
다운로드한 xlsx 파일을 아래 폴더에 그대로 넣습니다.

- `70_Imports/raw/`

예)
- `70_Imports/raw/namoo_trades_YYYYMMDD-YYYYMMDD.xlsx`
- `70_Imports/raw/namoo_cash_YYYYMMDD-YYYYMMDD.xlsx`

### (3) Import 실행(노트 자동 생성 + 정규화 CSV 생성)
터미널(명령프롬프트)에서 Vault 루트 폴더로 이동 후 실행:

```bash
pip install -r 70_Imports/scripts/requirements.txt
python 70_Imports/scripts/namoo_excel_import.py --create-companies
```

- `--create-companies` : 엑셀에서 새 티커가 나오면 `20_Companies/<TICKER>/Company.md`를 자동 생성합니다.
- 먼저 테스트만 하고 싶으면:

```bash
python 70_Imports/scripts/namoo_excel_import.py --dry-run
```

### (4) 결과 확인(옵시디언)
- `10_Dashboard/Portfolio.md` : 포트폴리오/손익
- `10_Dashboard/Exposure.md` : 섹터/국가/통화 노출도
- `10_Dashboard/Cashflows.md` : 입출금 요약
- `10_Dashboard/Import_Review.md` : 분류 실패/누락 점검(중요)

> Import는 **중복 실행해도 안전**하도록 `import_id`(해시)로 중복 생성 방지합니다.

---

## 3) “현재 보유현황부터” 시작하고 싶을 때(선택)

과거 거래내역을 전부 가져오기 어렵다면,
`70_Imports/templates/initial_holdings_template.xlsx`로 **초기 잔고(시작점)**를 먼저 입력할 수 있습니다.

- 사용 가이드: `70_Imports/templates/README.md`

---

## 4) 폴더 구조 한눈에 보기

- `00_Config/` : QuickStart/운영 설정/셋업 체크리스트
  - `00_Config/Prompts/` : Codex 프롬프트 카드(옵션)
  - `00_Config/Codex_Automation.md` : 자동/반자동 실행 가이드(옵션)
- `00_Inbox/` : 임시 메모/기사 링크
- `05_Principles/` : 투자 원칙(헌법), 리스크 룰, 루틴, 환율(수동)
- `10_Dashboard/` : 포트폴리오/노출도/현금흐름/임포트 점검 대시보드
- `20_Companies/` : 기업별 폴더 (Company.md + Notes/ + Events/)
- `30_Trades/` : 거래 노트(티커별 하위폴더 지원)
- `31_Cashflows/` : 입출금 노트
- `40_Knowledge/` : 주식/투자 지식(개념/전략/리스크/체크리스트)
- `50_Journal/` : 데일리/위클리/월말 스냅샷/사후분석
- `60_Library/` : 기사/리포트/IR 등 자료 요약(Source Note)
- `70_Imports/` : 엑셀 원본(raw) + 정규화(processed) + 임포트 스크립트
- `90_Attachments/` : PDF/이미지/캡처 등 첨부
- `99_Templates/` : 템플릿 모음

---

## 5) 환율(지금은 수동, API는 나중에)
- `05_Principles/FX_Rates.md`에서 `USD_KRW` 같은 값을 수동으로 적어두면,
대시보드에서 통화 환산(참고용)이 가능합니다.

> 정확한 성과측정(환율 변동까지 포함)은 **거래 시점 환율**이 필요합니다.
> 그 부분은 API/추가 데이터로 다음 단계에서 확장하는 게 좋습니다.

---

## 6) 문의/튜닝 포인트(가장 많이 필요해요)
나무 엑셀은 메뉴/기간/해외주식 여부에 따라 **열 이름이 조금씩 달라질 수** 있습니다.

Import 결과에서 `10_Dashboard/Import_Review.md`에 “분류 안 된 행”이 많이 나오면,
- 엑셀의 **헤더(열 제목)**만(개인정보/금액 제외) 복사해서 공유
- `70_Imports/scripts/namoo_excel_import.py`의 컬럼 매핑(COLUMN_SYNONYMS)/키워드 규칙을 보완

으로 정확도를 크게 올릴 수 있습니다.

---

<!-- STOCK-MVP-README:START -->

## 2026 Modernized Workflow

`06_Stock`은 새 Vault가 아니라 기존 Obsidian 투자관리 Vault입니다. 현재 표준 실행 진입점은 `70_Imports/scripts/main.py`입니다.

```bash
cd 70_Imports/scripts
pip install -r requirements.txt
python main.py all --vault-root ../.. --raw-dir ../raw
pytest
```

기존 `namoo_excel_import.py`는 호환용으로 보존되어 있으며, 신규 파이프라인은 `nh_importer.py`, `portfolio_model.py`, `obsidian_writer.py`, `qa_checker.py`로 분리됩니다.

<!-- STOCK-MVP-README:END -->
