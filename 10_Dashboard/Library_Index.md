# 자료 라이브러리 인덱스

- 기사/리포트/IR/PDF 등을 읽고 **Source Note(요약 노트)**로 남기는 폴더: `60_Library/`
- Source Note에 `tickers: ["AAPL", "005930"]`처럼 연결해두면,
  기업 노트에서 관련 자료를 자동으로 모아볼 수 있습니다.

## 읽을 것(To Read)
```dataview
TABLE date as "날짜", source_type as "유형", tickers as "티커", file.link as "노트"
FROM "60_Library"
WHERE doc_type = "source" AND (status = "to_read" OR status = "reading")
SORT date DESC
```

## 최근 추가/수정된 자료
```dataview
TABLE file.mtime as "수정일", source_type as "유형", tickers as "티커", file.link as "노트"
FROM "60_Library"
WHERE doc_type = "source"
SORT file.mtime DESC
LIMIT 30
```

## 티커 미지정(미분류)
```dataview
TABLE date as "날짜", source_type as "유형", file.link as "노트"
FROM "60_Library"
WHERE doc_type = "source" AND (tickers = null OR length(tickers) = 0)
SORT date DESC
```
