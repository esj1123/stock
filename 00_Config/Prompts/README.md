# Prompts (Codex용)

이 폴더는 **Codex(Codex CLI / Codex App)**에게 “이 Vault 안의 가이드/스크립트를 **참조만 해서 그대로 실행**”시키기 위한 **프롬프트 카드** 모음입니다.

- 파일/폴더 이름: 영어
- 프롬프트 본문: 한글
- 원칙: **추측 금지 / 새 구조 제안 금지 / Vault 안 문서(QuickStart, 스크립트) 우선 참조**

---

## 사용 방법(추천)

1) 터미널에서 Vault 루트로 이동  
2) Codex 실행  
3) 아래 카드 중 하나를 열고, **코드블록 전체를 그대로 복사**해 Codex에 붙여넣기

예시:
- `Codex_01_Run_Import.md` → 엑셀 임포트 1회 실행
- `Codex_02_Import_And_Summary.md` → 임포트 + 요약 리포트 노트 생성
- `Codex_03_Triage_Unclassified.md` → 분류 실패(UNCLASSIFIED) 점검/원인 분류
- `Codex_04_Monthly_Routine.md` → 월 1회 루틴(임포트 + 월말 스냅샷 초안)

---

## Codex에게 “반드시 참조”시키는 파일

- `00_Config/QuickStart.md`
- `70_Imports/scripts/main.py`
- `70_Imports/scripts/requirements.txt`

---

## 주의(중요)

- `70_Imports/raw/`의 원본 엑셀은 **절대 수정/이동/삭제하지 않기**  
- 코드 변경(임포터 수정 등)은 **반드시 diff 제안**을 먼저 만들고, 내 승인 후 적용  
- 외부 웹 검색/다운로드는 원칙적으로 하지 않기(필요 시 나에게 먼저 물어보기)
