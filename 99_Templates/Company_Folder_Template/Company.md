---
doc_type: company
ticker: "TICKER"
name: "회사명"
market: ""
country: ""
sector: ""
industry: ""
currency: "KRW"        # KRW | USD | JPY ...
status: "watch"        # watch | position | closed
conviction: 3          # 1~5
time_horizon: "6-24m"
last_update: 2026-02-23
price_now: 0
price_date: 2026-02-23
target_pct: 0
max_pct: 0
---

# {{ticker}} - {{name}}

## 0) 한 줄 투자 아이디어
- 

## 1) 투자 논리(Thesis)
- 핵심 가정 1:
- 핵심 가정 2:
- 내가 틀릴 수 있는 지점:

## 2) 관찰 포인트(체크할 지표)
- 실적 지표:
- 경쟁 구도:
- 정책/규제/환율:

## 3) 리스크(Risks) + 대응
- 리스크:
- 대응(축소/중단/손절/헤지):

## 4) 매수/비중 계획
- 신규 편입 조건:
- 추가매수 조건:
- 비중 상한(max_pct) 초과 시:
- 청산 조건:

## 5) 업데이트 로그
- 2026-02-23: 

---

## 관련 거래(자동)
```dataview
TABLE date as "일자", type as "구분", qty as "수량", price as "단가", amount as "배당", fee as "수수료", tax as "세금", file.link as "노트"
FROM "30_Trades"
WHERE ticker = this.ticker
SORT date DESC
```

## 관련 이벤트(자동)
```dataview
TABLE event_date as "일자", period as "기간", status as "상태", file.link as "노트"
FROM "20_Companies"
WHERE (doc_type = "earnings" OR doc_type = "event") AND ticker = this.ticker
SORT event_date DESC
```

## 관련 자료(자동)
```dataview
TABLE date as "날짜", source_type as "유형", status as "상태", file.link as "노트"
FROM "60_Library"
WHERE doc_type = "source" AND contains(tickers, this.ticker)
SORT date DESC
LIMIT 30
```
