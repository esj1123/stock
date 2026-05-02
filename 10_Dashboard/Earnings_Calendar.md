# 실적/이벤트 캘린더

- 이벤트 노트는 기업 폴더의 `Events/` 아래에 생성합니다.
- 최소 속성:
  - `doc_type: earnings` (또는 `event`)
  - `ticker`
  - `event_date` (YYYY-MM-DD)
  - `status: planned | done`

## 다가오는 실적/이벤트(60일)
```dataview
TABLE ticker as "티커", event_date as "일자", period as "기간", status as "상태", file.link as "노트"
FROM "20_Companies"
WHERE (doc_type = "earnings" OR doc_type = "event") AND event_date >= date(today) AND event_date <= date(today) + dur(60 days) AND status != "done"
SORT event_date ASC
```

## 지나갔는데 리뷰 미완료
```dataview
TABLE ticker as "티커", event_date as "일자", period as "기간", status as "상태", file.link as "노트"
FROM "20_Companies"
WHERE (doc_type = "earnings" OR doc_type = "event") AND event_date < date(today) AND status != "done"
SORT event_date DESC
```
