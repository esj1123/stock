# Codex_05_Vault_Health_Check

목적: 이 Vault가 “임포트/대시보드/기업 폴더” 운영을 위한 최소 구조를 갖췄는지 빠르게 점검합니다.

> 이 카드는 **실행/생성 없이 점검만** 합니다. (필요하면 “어디가 없고 무엇을 만들어야 하는지”만 보고)

---

## Copypaste Prompt (Codex에 그대로 붙여넣기)

```text
이 Vault의 폴더/핵심 파일이 QuickStart 기준으로 정상인지 점검하세요.
(생성/수정은 하지 말고, 결과만 보고)

[체크 대상(존재 여부)]
- 00_Config/QuickStart.md
- 10_Dashboard/Start_Here.md
- 10_Dashboard/Portfolio.md
- 10_Dashboard/Import_Review.md
- 20_Companies/
- 30_Trades/
- 31_Cashflows/
- 50_Journal/
- 70_Imports/raw/
- 70_Imports/processed/
- 70_Imports/review/
- 70_Imports/scripts/requirements.txt
- 70_Imports/scripts/main.py
- 99_Templates/Month_End_Snapshot.md

[보고 형식]
1) OK 목록
2) 누락 목록(경로)
3) 누락이 있으면, QuickStart 흐름을 깨지 않게 “어떤 폴더/파일이 필요”한지 제안(하지만 생성/수정은 하지 말 것)
```
