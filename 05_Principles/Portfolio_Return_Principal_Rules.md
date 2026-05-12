# Portfolio Return and Principal Rules

This baseline separates current holdings from performance accounting.

## Principal

- Net external principal is `external deposits - external withdrawals`.
- Trading profit, losses, dividends, interest, distributions, fees, and taxes do not change principal.
- Internal transfers and FX exchange events are not external principal.

## Total Performance

- Current total assets are current cash plus current non-cash holding valuation.
- Total cumulative PnL is `current total assets - net external principal`.
- Total cumulative return is `total cumulative PnL / net external principal`.
- Current holding `pnl_pct` remains a separate current-position metric and is not the same as total cumulative return.

## Profit Decomposition

- Realized PnL is calculated in a separate ledger from imported buy/sell transaction history.
- Closed symbols such as sold TSLA/TSLL/RGTZ-like positions stay out of current holdings and appear only in the realized PnL ledger.
- Unrealized PnL is current-holding valuation PnL only.
- Dividends, interest, and distributions are income events.
- Fees and taxes are expense events.
- Unexplained difference is `total cumulative PnL - explained profit`.

## Safety

- Transaction history must never be used to create current holdings.
- Raw broker files remain read-only inputs.
- Generated Markdown updates must stay inside `AUTO-GENERATED` blocks.
- The layer does not add trading automation, recommendations, order placement, broker API access, or credential storage.
