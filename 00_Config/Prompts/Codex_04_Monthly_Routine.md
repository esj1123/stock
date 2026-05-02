# Codex_04_Monthly_Routine

목적: “월 1회” 루틴을 한 번에 수행합니다.

- (1) 엑셀 임포트 실행  
- (2) 임포트 요약 노트 생성  
- (3) 월말 스냅샷 노트(초안) 생성  

> 월말 스냅샷은 **금액 입력은 사용자(나)**가 나중에 채우는 전제입니다.

---

## Copypaste Prompt (Codex에 그대로 붙여넣기)

```text
00_Config/QuickStart.md를 먼저 읽고, 아래 작업을 QuickStart 흐름에 맞춰 수행하세요.

[1) Import 실행]
- 70_Imports/raw/에 .xlsx가 있는지 확인 (없으면 종료)
- requirements 설치 → `main.py import --dry-run` → `main.py all --create-companies` 순으로 실행
- 명령은 Vault 루트 기준으로 실행:
  - `pip install -r 70_Imports/scripts/requirements.txt`
  - `python 70_Imports/scripts/main.py import --vault-root . --raw-dir 70_Imports/raw --dry-run`
  - `python 70_Imports/scripts/main.py all --vault-root . --raw-dir 70_Imports/raw --create-companies`

[2) Import 요약 노트]
- 70_Imports/logs/Import_Summary_YYYY-MM-DD.md 생성(없으면 폴더 생성)

[3) 월말 스냅샷 노트(초안)]
- 템플릿 파일: 99_Templates/Month_End_Snapshot.md 를 읽어,
- 아래 경로에 새 노트를 생성하세요(없으면 폴더 생성):
  - 50_Journal/Month_End_YYYY-MM.md
- 생성 시 규칙:
  - YAML의 date는 오늘 날짜(YYYY-MM-DD)로 채우기
  - 제목의 YYYY-MM도 오늘 기준으로 채우기
  - portfolio_value/cash_in/cash_out은 0으로 두기(사용자가 나중에 채움)
  - 본문은 템플릿 구조 유지

[작업 완료 보고]
- 실행한 명령 목록
- 생성/변경된 파일 목록
- 내가 바로 확인할 곳 3개:
  1) 10_Dashboard/Import_Review.md
  2) 70_Imports/review/
  3) 50_Journal/Month_End_YYYY-MM.md 경로
```
