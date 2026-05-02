# 지식 인덱스

`40_Knowledge/` 아래에 쌓인 지식 노트들을 **최근 수정 순**으로 보여줍니다.

```dataview
TABLE file.mtime AS "수정일", file.folder AS "폴더", file.link AS "노트"
FROM "40_Knowledge"
SORT file.mtime DESC
```
