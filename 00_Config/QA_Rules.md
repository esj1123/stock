# QA Rules

QA는 exception-first 방식입니다. 정상 항목을 길게 나열하지 않고 사용자가 조치해야 하는 예외만 기록합니다.

| ID | severity | description | check logic | suggested fix |
|---|---|---|---|---|
| INV-EX-01 | blocking | 필수 YAML `type` 누락 | 투자 관련 Markdown의 frontmatter에 `type`이 없다 | Metadata Governance에 맞춰 `type`을 추가한다 |
| INV-EX-02 | blocking | company/holding note에 ticker 또는 market 누락 | `type`이 company/holding 계열인데 `ticker` 또는 `market`이 비어 있다 | 회사/보유 노트 YAML에 ticker와 market을 채운다 |
| INV-EX-03 | advisory | company/holding note에 thesis 누락 | thesis/매수 이유 섹션이 비어 있거나 placeholder만 있다 | 사용자 판단 영역에 투자 논리를 작성한다 |
| INV-EX-04 | blocking | `pnl_pct <= -10`인데 최근 review 없음 | processed holdings의 손익률이 -10% 이하이고 30일 내 risk/review 기록이 없다 | Risk Event 또는 Review Report를 작성한다 |
| INV-EX-05 | blocking | 레버리지 ETF인데 전용 규칙 링크 없음 | leveraged ETF 감지 항목에 `leveraged_etf_rule_link`가 없다 | `[[05_Principles/Leveraged_ETF_Rules]]` 링크를 추가한다 |
| INV-EX-06 | advisory | `last_review`가 30일 초과 | company/holding note의 last_review가 30일보다 오래됐다 | review report 또는 회사 노트를 갱신한다 |
| INV-EX-07 | advisory | source link 누락 | holding/company/source note에 source_files 또는 원천자료 링크가 없다 | source note 또는 raw file reference를 연결한다 |
| INV-EX-08 | blocking | sell criteria 누락 | 매도/비중축소 조건 또는 sell criteria 섹션이 비어 있다 | 사용자 판단 영역에 축소/매도 기준을 작성한다 |
| INV-EX-09 | blocking | generated note overwrite conflict | 자동화 대상 파일에 AUTO-GENERATED 마커가 없다 | 마커를 추가하거나 수동 파일로 유지한다 |
| INV-EX-10 | advisory | raw brokerage file not indexed | `70_Imports/raw/`의 파일이 source_file_index.csv에 없다 | import를 다시 실행한다 |
| INV-EX-11 | blocking | unclassified transaction rows exist | unclassified_rows.csv에 행이 있다 | 거래유형 매핑 또는 raw 컬럼 매핑을 보완한다 |
| INV-EX-12 | blocking | generated note에 민감정보 후보 발견 | AUTO-GENERATED 블록에서 계좌번호/주민번호/토큰 패턴을 감지했다 | generated output을 redaction하고 raw는 그대로 보관한다 |
