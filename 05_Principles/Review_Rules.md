# Review Rules

## 필수 리뷰 트리거
- holding `pnl_pct <= -10`
- weight_pct `>= 15`
- leveraged ETF 보유
- last_review 30일 초과
- thesis 또는 sell criteria 누락
- unclassified transaction 존재
- source link 누락

## 리뷰 산출물
- `50_Journal/Risk_Events/`: 이벤트/하락/뉴스 기반 점검
- `50_Journal/Decisions/`: 매수/매도/보류/축소 결정
- `50_Journal/Reviews/`: 주간/월간 포트폴리오 리뷰
- `10_Dashboard/Review_Queue.md`: 지금 채워야 하는 판단 큐

## 결론 표현
- review required
- risk flag
- thesis missing
- sell criteria missing
- leveraged ETF review required
- high concentration warning
- data quality warning
