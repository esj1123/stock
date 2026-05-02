# Codex로 Import 자동/반자동 실행하기 (옵션)

> 목적: 이 Vault에서 **나무 엑셀 → Import 실행 → 결과 점검(Import Review) → 커밋(선택)** 과정을
> **한 번의 명령** 또는 **스케줄(자동)**로 돌릴 수 있게 하는 운영 가이드입니다.

---

## 0) 전제

- 이 Vault 루트에 `70_Imports/` 폴더가 있고, 아래 스크립트가 존재해야 합니다.
  - `70_Imports/scripts/main.py`
  - `70_Imports/scripts/requirements.txt`
- 나무에서 내려받은 `.xlsx` 파일은 `70_Imports/raw/`에 넣습니다.
- **권장:** Vault를 Git 저장소로 운영 (`git init`)

---

## 1) 반자동(가장 쉬움): Codex CLI에서 “명령 1줄”로 실행

### 1-1) 설치 (최초 1회)
- Codex CLI 설치: `npm i -g @openai/codex`
- 최초 실행: `codex` (로그인)

### 1-2) 실행 방법(예시)
Vault 루트에서:

- 인터랙티브 모드:
  - `codex`
  - 프롬프트 예시:
    - “`70_Imports/raw/`에 있는 새 엑셀을 기준으로 import 실행해줘.
       `python 70_Imports/scripts/main.py all --vault-root . --raw-dir 70_Imports/raw --create-companies` 실행하고,
       `10_Dashboard/Import_Review.md`에서 확인할 항목을 요약해줘.”

---

## 2) 완전 자동(스케줄): OS 스케줄러 + 스크립트

### 2-1) macOS / Linux
- `scripts/run_import.sh`를 실행하도록 cron(또는 Launchd) 등록

### 2-2) Windows
- `scripts/run_import.ps1`을 작업 스케줄러(Task Scheduler)에 등록

> 참고: “Codex를 스케줄로 돌리기”가 필요하면 `codex exec`를 사용할 수 있습니다.
> 다만, 단순 Import 실행만 목적이면 **Codex 없이 스크립트만 스케줄링**하는 게 가장 안정적입니다.

---

## 3) Import 스크립트(권장): venv 포함 실행

이 패치에는 아래 실행 스크립트가 포함됩니다.

- macOS/Linux: `scripts/run_import.sh`
- Windows: `scripts/run_import.ps1`

동작:
1) `.venv`가 없으면 생성
2) requirements 설치/업데이트
3) `70_Imports/scripts/main.py` 실행

---

## 4) 안전 운영 팁

- Import는 Vault 파일을 대량으로 생성/수정할 수 있습니다.
  - **권장:** Git을 사용해 변경사항(diff) 확인 → 커밋
- 자동화(스케줄)는 권한을 최소로 유지하세요.
- 민감한 파일(계좌번호/개인정보)이 포함된 원본 엑셀은 `70_Imports/raw/`에만 보관하고,
  외부 공유/업로드는 피하세요.

---

---

<!-- STOCK-MVP-AUTOMATION:START -->

## 현대화된 안전 자동화 규칙

### Safe update rule
- Codex와 Python 자동화는 `<!-- AUTO-GENERATED:START -->`와 `<!-- AUTO-GENERATED:END -->` 사이만 갱신합니다.
- 기존 파일에 자동 생성 마커가 없으면 덮어쓰지 않고 QA 예외로 기록합니다.
- 회사 노트의 `사용자 판단 영역`은 자동화가 수정하지 않습니다.
- raw 파일은 읽기 전용으로 취급하며 수정하지 않습니다.

### Commands
`70_Imports/scripts`에서 실행합니다.

```bash
python main.py import --vault-root ../.. --raw-dir ../raw --dry-run
python main.py import --vault-root ../.. --raw-dir ../raw
python main.py report --vault-root ../..
python main.py qa --vault-root ../..
python main.py all --vault-root ../.. --raw-dir ../raw
```

### Useful options
- `--dry-run`: 파일 쓰기 없이 파싱/점검만 수행
- `--no-note-write`: CSV/DB만 갱신하고 Obsidian 노트 쓰기는 생략
- `--create-companies`: 새 ticker가 있으면 `20_Companies/<TICKER_OR_SAFE_NAME>/Company.md` 생성
- `--force-reindex`: 기존 processed 결과와 관계없이 raw 파일을 다시 인덱싱
- `--verbose`: 파일/시트별 처리 내용을 자세히 출력

### Troubleshooting
- import 결과가 비어 있으면 `70_Imports/raw/`에 `.xls` 또는 `.xlsx`가 있는지 확인합니다.
- `.xls`가 실제 HTML 테이블인 경우도 자동 처리하지만, 표 헤더가 깨지면 `Import_Review`의 unknown columns를 확인합니다.
- `unclassified_rows.csv`가 생기면 거래유형/상세내용 키워드가 새 형식인지 확인합니다.
- 대시보드가 갱신되지 않으면 대상 파일에 AUTO-GENERATED 마커가 있는지 확인합니다.
- 민감정보 경고가 뜨면 raw는 그대로 두고 generated note/dashboard에서만 redaction이 적용됐는지 확인합니다.

<!-- STOCK-MVP-AUTOMATION:END -->
