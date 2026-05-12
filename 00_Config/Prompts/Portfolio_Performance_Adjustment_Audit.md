# Portfolio Performance Adjustment Audit

## Scope Lock / Stage Realignment

### Decision

Keep the current `codex/Portfolio_adjust` implementation and revise it in follow-up stages.

This branch is no longer a pure stage-1 audit branch. It already contains a partial performance accounting layer: realized PnL ledger generation, total return percent, dashboard exposure, QA/quality-gate checks, tests, a principle document, and acceptance trace updates. Reverting that work would create more churn than aligning and hardening it.

### Scope Boundaries

- Do not use `transaction_history` rows to create current holdings.
- Do not merge sold positions back into `processed_holdings.csv`.
- Keep realized PnL as a separate ledger/explanation layer.
- Keep net external principal as external deposits minus external withdrawals.
- Keep current holdings `pnl_pct` separate from total cumulative return.
- Do not touch the live vault, raw broker files, generated outputs, DB files, Excel files, account identifiers, or private notes.
- Do not add broker API access, order placement, buy/sell automation, credential storage, investment opinions, recommendations, thesis generation, or sell-criteria generation.

### Keep / Revise / Missing

| Area | Decision | Follow-up needed |
| --- | --- | --- |
| Realized PnL ledger | Keep | Document FIFO assumptions and limitations before relying on it as official performance accounting. |
| Total return percent | Keep | Ensure dashboard wording makes it distinct from current holdings return. |
| Dashboard `Return` card | Revise | Rename or clarify because it currently means current holdings `pnl_pct`, not total cumulative return. |
| FIFO realized PnL method | Revise | Add documentation for lot matching, partial sells, missing lots, FX gaps, and status gating. |
| Realized PnL schema | Revise | Add fee/tax/native/KRW fields if realized PnL is expected to explain broker-stated net realized results. |
| `processed_income.csv` / `processed_expenses.csv` | Keep | Existing row-level files are useful, but summary-level income output is still missing. |
| `income_summary.csv` | Missing | Add summary output for dividend, interest, distribution, withholding tax, and status counts. |
| `performance_summary.csv` | Missing | Add a dedicated performance-facing summary instead of overloading reconciliation output. |
| `reconciliation_summary.csv` role | Revise | Keep as audit/status reconciliation; separate user-facing performance summary in a later stage. |
| Tests / quality gate / docs | Revise | Add tests and gate checks for the final schema split and dashboard terminology once implemented. |

### Recommended Next Stage

Next stage should be a narrow terminology and documentation pass:

1. Rename dashboard `Return` to current-holdings-specific wording.
2. Document FIFO realized PnL assumptions.
3. Leave schema expansion and new summary outputs for later stages.
