# 워치리스트

```dataview
TABLE ticker as "티커", name as "기업명", sector as "섹터", country as "국가", currency as "통화", conviction as "확신도", last_update as "업데이트", price_now as "현재가", price_date as "가격일", file.link as "노트"
FROM "20_Companies"
WHERE doc_type = "company" AND status = "watch"
SORT conviction DESC, last_update ASC
```
