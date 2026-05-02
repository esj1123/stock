# Codex_02_Import_And_Summary

목적: 임포트를 실행한 뒤, 결과를 **Vault 안에 요약 노트로 남깁니다.**  
(나중에 “언제 무엇을 가져왔는지” 추적용)

---

## Copypaste Prompt (Codex에 그대로 붙여넣기)

```text
00_Config/QuickStart.md를 먼저 읽고, "Step 2) Import 실행"과 "Step 3) Import 결과 점검"을 그대로 수행하세요.

[사전 점검]
- 70_Imports/raw/에 .xlsx가 1개 이상인지 확인. 없으면 종료.

[실행]
1) pip install -r 70_Imports/scripts/requirements.txt
2) python 70_Imports/scripts/main.py import --vault-root . --raw-dir 70_Imports/raw --dry-run
3) python 70_Imports/scripts/main.py all --vault-root . --raw-dir 70_Imports/raw --create-companies

[요약 노트 생성]
- 아래 경로에 폴더가 없으면 생성하세요: 70_Imports/logs/
- 아래 파일을 새로 생성(또는 같은 날짜 파일이 있으면 뒤에 _2 같은 접미사)하세요:
  - 70_Imports/logs/Import_Summary_YYYY-MM-DD.md

- 요약 노트에는 아래 섹션을 꼭 포함하세요(값은 확인 가능한 범위에서만, 모르면 '미확인'으로):
  1) 이번 임포트에서 사용한 raw xlsx 파일 목록
  2) 생성/변경된 주요 결과물:
     - 70_Imports/processed/ 내 파일(예: namoo_ledger.csv)
     - 30_Trades/ 신규/변경 파일 수(대략)
     - 31_Cashflows/ 신규/변경 파일 수(대략)
     - 20_Companies/ 신규 기업 폴더 목록(있으면)
  3) 분류 실패/점검:
     - 70_Imports/review/ 파일 목록
     - (가능하면) 분류 실패 행 수(대략)
  4) 다음 액션(사용자 체크리스트) 3~7개

[주의]
- raw 엑셀은 절대 건드리지 마세요.
- 코드 수정은 하지 마세요.

끝나면, 생성한 요약 노트 경로를 마지막 줄에 알려주세요.
```
