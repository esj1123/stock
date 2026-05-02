# Codex_01_Run_Import

목적: `70_Imports/raw/`에 넣어둔 나무증권 엑셀(.xlsx)을 기준으로 **임포트(원장 DB + 노트 생성)**를 1회 실행합니다.

> 이 카드는 **실행만** 합니다. (분류 규칙/코드 수정은 하지 않음)

---

## Copypaste Prompt (Codex에 그대로 붙여넣기)

```text
00_Config/QuickStart.md를 먼저 읽고, "Step 2) Import 실행" 절차를 그대로 수행하세요.

[사전 점검]
1) 현재 작업 디렉토리가 Vault 루트인지 확인하세요.
2) 아래 파일/폴더가 존재하는지 확인하고, 없으면 중단(왜 중단했는지 보고):
   - 00_Config/QuickStart.md
   - 70_Imports/raw/
   - 70_Imports/scripts/requirements.txt
   - 70_Imports/scripts/namoo_excel_import.py
3) 70_Imports/raw/에 .xlsx 파일이 1개 이상 있는지 확인하세요.
   - 0개면 "임포트할 파일이 없음"으로 종료하고, 사용자가 넣어야 할 위치를 안내하세요.

[실행(원칙)]
- 70_Imports/raw/의 원본 엑셀은 절대 수정/이동/삭제하지 마세요.
- 코드를 수정하지 마세요.
- 가능한 경우, 먼저 --dry-run으로 점검하고, 그 다음 실제 실행하세요.

[실행 절차]
A) (권장) dry-run:
   python 70_Imports/scripts/namoo_excel_import.py --dry-run

B) 의존성 설치(필요 시):
   pip install -r 70_Imports/scripts/requirements.txt

C) 실제 실행(회사 폴더 자동 생성 포함):
   python 70_Imports/scripts/namoo_excel_import.py --create-companies

[사후 점검]
1) 아래 파일/폴더를 확인해 결과를 요약하세요.
   - 70_Imports/processed/ (예: namoo_ledger.csv 생성 여부)
   - 70_Imports/review/ (분류 실패가 모였는지)
   - 30_Trades/ (거래 노트 생성 여부)
   - 31_Cashflows/ (입출금 노트 생성 여부)
   - 20_Companies/ (새 티커 폴더 생성 여부)
2) 요약에 반드시 포함:
   - 처리한 xlsx 파일 개수
   - 생성/변경된 파일/노트 개수(대략적 count라도 OK)
   - UNCLASSIFIED/분류 실패가 있는지(있다면 review 폴더 파일명)
   - 다음에 사용자가 확인해야 할 항목 3개

작업을 실행하고, 위 형식대로 결과만 보고하세요.
```

