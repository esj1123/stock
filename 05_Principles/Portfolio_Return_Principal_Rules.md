# Portfolio Return and Principal Rules

This baseline separates current holdings from performance accounting.

## Principal

- Net external principal is `external deposits - external withdrawals`.
- Trading profit, losses, dividends, interest, distributions, fees, and taxes do not change principal.
- Internal transfers and FX exchange events are not external principal.

## Total Performance

- `performance_summary.csv` is the user-facing whole-investment performance summary.
- `portfolio_summary.csv` remains current-holdings-focused.
- `reconciliation_summary.csv` is the audit/status/residual reconciliation layer.
- `total_return_krw` / `total_return_pct` in reconciliation are aliases of `performance_summary.cumulative_return_krw` / `performance_summary.cumulative_return_pct`.
- Further file or metric naming cleanup can remain a follow-up, but the role separation is implemented.
- Current total assets are current cash plus current non-cash holding valuation.
- Total cumulative PnL is `current total assets - net external principal`.
- Total cumulative return is `total cumulative PnL / net external principal`.
- Current holding `pnl_pct` remains a separate current-position metric and is not the same as total cumulative return.
- FX PnL is not modeled yet; unresolved FX effects may remain in `fx_status`, unavailable official values, and residual interpretation.

## Profit Decomposition

- Realized PnL is calculated in a separate FIFO cost-basis ledger from imported buy/sell transaction history.
- If imported transaction history starts mid-position and FIFO buy lots are insufficient, the sell row is kept in the ledger with `lot_missing` review status instead of stopping the pipeline.
- Closed symbols such as sold TSLA/TSLL/RGTZ-like positions stay out of current holdings and appear only in the realized PnL ledger.
- Unrealized PnL is current-holding valuation PnL only.
- Dividends, interest, and distributions are income events.
- Fees and taxes are expense events.
- Unexplained difference is `total cumulative PnL - explained profit`.

## QA and Quality Gate

- QA and quality gate protect the performance accounting layer from schema drift, dashboard label regression, non-KRW KRW provenance errors, fee/tax double counting, and transaction-history/current-holdings mixing.
- QA findings are review controls and must not become investment recommendations or trading automation.
- Current holdings return and whole-investment cumulative return must remain separately labeled.

## Safety

- Transaction history must never be used to create current holdings.
- Raw broker files remain read-only inputs.
- Generated Markdown updates must stay inside `AUTO-GENERATED` blocks.
- The layer does not add trading automation, recommendations, order placement, broker API access, or credential storage.
