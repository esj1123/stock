# Metadata Governance

이 문서는 `06_Stock` Vault에서 Python/CSV/SQLite와 Obsidian 노트가 합의하는 YAML 계약입니다.

## 공통 원칙
- `type`은 필수입니다. 기존 `doc_type`은 읽을 수 있지만 신규 노트는 `type`을 사용합니다.
- 자동화는 YAML과 `AUTO-GENERATED` 블록만 갱신합니다.
- 사용자 판단 섹션은 자동화가 덮어쓰지 않습니다.
- source filename은 generated Markdown에서 sanitize된 이름만 표시합니다.

## Company Note
```yaml
type: company
ticker:
name:
market:
asset_type: stock
account:
currency:
status: watch
weight_pct:
pnl_pct:
is_leveraged: false
review_status:
risk_level:
last_review:
next_review:
source_files: []
tags:
  - investment
  - company
```

## Stock Holding Note
```yaml
type: holding_stock
ticker:
name:
market:
account:
currency:
quantity:
avg_price:
weight_pct:
pnl_pct:
last_review:
next_review:
source_files: []
tags:
  - investment
  - holding
  - stock
```

## ETF Holding Note
```yaml
type: holding_etf
ticker:
name:
market:
account:
currency:
underlying_asset:
leverage_factor:
rebalance_type:
long_term_holding_allowed: false
volatility_decay_risk: true
leveraged_etf_rule_link: "[[05_Principles/Leveraged_ETF_Rules]]"
weight_pct:
pnl_pct:
last_review:
next_review:
source_files: []
tags:
  - investment
  - holding
  - etf
```

## Trade Note
```yaml
type: trade
trade_id:
date:
ticker:
account:
market:
transaction_type: buy
quantity:
price:
trade_amount:
settlement_amount:
fee:
tax:
currency:
source_files: []
tags:
  - investment
  - trade
```

## Cashflow Note
```yaml
type: cashflow
cashflow_id:
date:
account:
cashflow_type: deposit
amount:
currency:
source_files: []
tags:
  - investment
  - cashflow
```

## Risk Event Note
```yaml
type: risk_event
event_id:
date:
related_tickers: []
severity:
status:
trigger:
account:
source_files: []
tags:
  - investment
  - risk_event
```

## Decision Note
```yaml
type: decision
decision_id:
date:
decision_type:
ticker:
account:
status:
confidence:
source_files: []
tags:
  - investment
  - decision
```

## Review Report Note
```yaml
type: review_report
date:
period:
accounts: []
generated_by: python
source_files: []
tags:
  - investment
  - review
```

## Source Note
```yaml
type: source
source_type: brokerage_file
broker: NH
account:
file_name:
file_path:
period_start:
period_end:
import_status:
imported_at:
tags:
  - investment
  - source
```
