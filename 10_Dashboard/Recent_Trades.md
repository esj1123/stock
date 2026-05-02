# 최근 거래

```dataview
TABLE date as "일자", type as "구분", ticker as "티커", qty as "수량", price as "단가", amount as "배당/현금", fee as "수수료", tax as "세금", strategy as "전략", file.link as "노트"
FROM "30_Trades"
SORT date DESC
LIMIT 50
```
