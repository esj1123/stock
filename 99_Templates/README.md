# Template Status and Ownership

이 표는 `99_Templates/`의 현재 사용 상태를 찾기 위한 권위다. 상태는 삭제
허가가 아니며, live vault 사용 여부를 확인하지 않은 템플릿은 자동으로
정리하거나 이름을 바꾸지 않는다.

| 상태 | 의미 |
| --- | --- |
| `active-automation` | 현재 baseline 자동화 코드가 경로를 직접 참조한다. |
| `active-manual` | 운영 문서나 Templater에서 사람이 선택해 사용하는 기본 템플릿이다. |
| `compatibility` | 대체·이전 naming과의 호환을 위해 보존하며 신규 자동화의 기본값은 아니다. |
| `review-required` | 사용자 판단을 기록하는 수동 템플릿이며 자동 생성·자동 작성 대상으로 삼지 않는다. |

## Inventory

| 템플릿 | 상태 | 현재 책임/사용 |
| --- | --- | --- |
| `Company.md` | `active-automation` | QuickAdd 기업 폴더 생성과 Company note baseline |
| `Month_End_Snapshot.md` | `active-automation` | QuickAdd 월말 스냅샷 생성 |
| `Cashflow.md` | `active-manual` | 수동 입출금 기록 |
| `Checklist.md` | `active-manual` | 범용 수동 체크리스트 |
| `Daily_Journal.md` | `active-manual` | 일간 투자 일지 |
| `Dividend.md` | `active-manual` | 수동 배당 기록 |
| `Earnings_Pre.md` | `active-manual` | 실적 전 수동 점검; 원칙·playbook에서 링크 |
| `Earnings_Post.md` | `active-manual` | 실적 후 수동 리뷰; 원칙·playbook에서 링크 |
| `Knowledge_Note.md` | `active-manual` | 수동 지식 노트 |
| `Post_Mortem.md` | `active-manual` | 수동 사후 분석 |
| `Source_Note.md` | `active-manual` | 현재 수동 자료 노트 기본형 |
| `Trade.md` | `active-manual` | 수동 거래 기록 |
| `Weekly_Review.md` | `active-manual` | 주간 수동 리뷰 |
| `TPL_Holding_ETF.md` | `compatibility` | `TPL_` holding schema 호환 보존 |
| `TPL_Holding_Stock.md` | `compatibility` | `TPL_` holding schema 호환 보존 |
| `TPL_Source_Note.md` | `compatibility` | `Source_Note.md`와 병존하는 `TPL_` schema 호환 보존 |
| `TPL_Review_Report.md` | `review-required` | 사용자가 검토 결과를 작성하는 수동 보고서 |
| `TPL_Risk_Event.md` | `review-required` | 사용자가 리스크 판단과 최종 판단을 작성하는 기록 |
| `TPL_Trade_Decision.md` | `review-required` | 사용자가 거래 판단 근거와 실행 여부를 작성하는 기록 |

## Change Rules

- `active-automation` 경로 변경은 해당 호출 코드와 테스트를 함께 바꾼다.
- `review-required`의 thesis, sell criteria, 최종 판단, 추천 내용은 자동으로 채우지 않는다.
- `compatibility` 템플릿은 live vault 사용 여부를 별도로 확인하기 전 삭제·병합하지 않는다.
- 실제 live vault의 템플릿 적용 여부 확인은 read-only 승인과 새 증거가 필요하다.