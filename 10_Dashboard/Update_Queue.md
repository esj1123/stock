# 업데이트 큐

> “업데이트가 오래된 기업”을 자동으로 끌어올려서, 리서치/가격/이벤트를 점검하는 화면입니다.

## 1) 논리/노트 업데이트가 오래된 기업(기본: 30일)

```dataview
TABLE ticker as "티커", name as "기업명", status as "상태", conviction as "확신도", last_update as "업데이트", file.link as "노트"
FROM "20_Companies"
WHERE doc_type = "company" AND last_update <= date(today) - dur(30 days)
SORT last_update ASC
```

## 2) 가격 업데이트가 오래되었거나(price_date 7일↑) 현재가가 비어있는 기업

```dataview
TABLE ticker as "티커", name as "기업명", status as "상태", price_now as "현재가", price_date as "가격일", file.link as "노트"
FROM "20_Companies"
WHERE doc_type = "company" AND (price_now = null OR price_date <= date(today) - dur(7 days))
SORT price_date ASC
```
