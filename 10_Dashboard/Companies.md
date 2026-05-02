# 기업 목록(Companies)

- `20_Companies/<TICKER>/Company.md` 형태의 기업 인덱스 노트만 모아서 보여줍니다.
- `price_now`는 수동 입력(주 1회 업데이트 추천)

```dataview
TABLE ticker as "티커", name as "기업명", status as "상태", sector as "섹터", country as "국가", currency as "통화", price_now as "현재가", price_date as "가격일", conviction as "확신도", last_update as "업데이트"
FROM "20_Companies"
WHERE doc_type = "company"
SORT status ASC, conviction DESC, last_update ASC
```
