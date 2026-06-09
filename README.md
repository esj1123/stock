# Stock Vault Automation Structure

This repository is a safe public/private GitHub structure for Stock Obsidian vault automation code, templates, and operating guides. It is not the live investment vault and it does not include personal investment records.

The live `06_Stock` vault should stay local/private. Use this repository as the clean baseline for scripts, templates, prompts, and documentation that can be reviewed without exposing account activity, holdings, trades, attachments, or generated import outputs.

## What Is Included

- `00_Config/`: setup guides, prompt cards, QA rules, and automation notes
- `05_Principles/`: investment-policy and review-rule templates
- `10_Dashboard/`: safe dashboard/query entry pages only
- `40_Knowledge/`: checklists and general playbook notes
- `70_Imports/scripts/`: import and reporting pipeline code
- `70_Imports/templates/`: template instructions
- `99_Templates/`: Obsidian note templates
- `scripts/`: root-level helper entrypoints

## What Is Not Included

The repository intentionally excludes personal investment data and generated outputs:

- `20_Companies/`
- `30_Trades/`
- `31_Cashflows/`
- `50_Journal/`
- `60_Library/`
- `90_Attachments/`
- `70_Imports/raw/`
- `70_Imports/processed/`
- `70_Imports/exports/`
- `70_Imports/logs/`
- `*.csv`, `*.db`, `*.xlsx`, `*.xls`

These paths are for local vault operation only. They may contain broker exports, normalized ledgers, database files, attachments, generated reports, company notes, trades, cashflows, or other private data.

## Clean Setup Check

From a clean clone, keep the Python virtual environment outside the repository and outside any Google Drive synced vault:

```powershell
$VenvDir = Join-Path $env:LOCALAPPDATA "06_Stock\.venv"
python -m venv $VenvDir
& "$VenvDir\Scripts\python.exe" -m pip install -r 70_Imports\scripts\requirements.txt
cd 70_Imports\scripts
& "$VenvDir\Scripts\python.exe" main.py --help
& "$VenvDir\Scripts\python.exe" -m pytest
```

On Windows, if `python` resolves to the Microsoft Store alias, use `py -m venv $VenvDir` instead.

Expected result:

- `main.py --help` prints the CLI usage.
- `pytest` passes without requiring raw broker files.

## Standard Import Entrypoint

The standard CLI entrypoint is:

```bash
python 70_Imports/scripts/main.py all --vault-root . --raw-dir 70_Imports/raw
```

Convenience wrappers are also provided:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_import.ps1 all --dry-run
```

```bash
bash scripts/run_import.sh all --dry-run
```

If no action is passed to a wrapper, it defaults to `all`. Supported actions are `import`, `report`, `qa`, and `all`.

Do not commit local raw input files or generated outputs. The ignored local folders should be created by the operator only inside a private working vault.

## Performance Accounting Outputs

The pipeline separates current holdings valuation from whole-investment performance accounting:

- `portfolio_summary.csv` remains current-holdings-focused. Its `pnl_pct` is the current holdings valuation return, not whole-investment cumulative return.
- `processed_realized_pnl.csv` is the realized PnL ledger. It records sold-position PnL from imported buy/sell transaction history using FIFO cost basis and must not create current holdings.
- `income_summary.csv` summarizes dividend, interest, and distribution income separately by `income_type` and `currency_native`. Native amounts are preserved; official KRW income uses status-ok KRW rows only.
- `fx_rate_requirements.csv` lists historical FX rates needed before non-KRW income, expenses, or realized PnL rows can become official KRW amounts.
- `performance_summary.csv` is the user-facing whole-investment performance summary. It exposes net external principal, current total assets, cumulative return, realized/unrealized PnL, income, expenses, and residual.
- `monthly_cashflow_summary.csv` summarizes monthly external principal deposits, withdrawals, net flow, and cumulative principal for dashboard trend charts.
- `performance_history.csv` stores import-time performance snapshot rows for monthly principal/assets/return trend charts.
- `reconciliation_summary.csv` is the audit/status/residual layer. It keeps `total_return_krw` / `total_return_pct` as aliases of `performance_summary.cumulative_return_krw` / `performance_summary.cumulative_return_pct`.

Accounting rules:

- Net external principal is external deposits minus external withdrawals. Realized gains, realized losses, dividends, interest, distributions, fees, and taxes do not adjust principal.
- Cumulative return is `current_total_assets_krw - net_external_principal_krw`; cumulative return percent is that value divided by net external principal.
- Explained profit uses gross realized trade PnL plus unrealized PnL plus dividend/interest/distribution income minus fee/tax. Fee/tax must be deducted separately exactly once.
- Residual is `cumulative_return_krw - explained_profit_krw`.
- FX-missing rows must preserve native amounts and must not make official KRW performance available without FX or broker-provided KRW provenance.
- FX provenance priority is broker KRW amount, broker raw FX, local `fx_rates.csv`, API-cached archived rate, then `fx_missing`.
- Historical rows require same-date FX evidence. Do not apply today's rate to older dividends, fees, taxes, trades, or realized PnL.
- USD dividends may become official KRW income when same-date provenance exists. USD realized PnL remains requirement-only until all underlying proceeds, cost basis, fee, and tax KRW values have provenance.
- Transaction-history rows must stay in transaction/realized ledgers and must not be promoted into current holdings.
- Historical total assets and cumulative return trend points require imported balance snapshots. Do not reconstruct past monthly total assets from raw transactions alone.

Repository safety for these outputs:

- Do not commit raw broker files, processed CSVs, generated dashboards, DB files, Excel files, account identifiers, private notes, or live vault outputs.
- Do not edit the live Google Drive vault directly. Modify the baseline, run tests, run the quality gate, run a live-vault dry-run with evidence, review expected changes, then apply an actual live write only with explicit user intent.

## Live Vault Modification Policy

Modify and validate the GitHub baseline first. Do not start by editing the Google Drive live Vault.

Live vault cleanup is also a live Vault write. Treat cache removal, temporary-file cleanup, duplicate-looking file deletion, renames, moves, and template/document consolidation as live-write operations.

Required sequence before any actual live Vault write:

1. Modify and validate the GitHub baseline.
2. Add/update tests.
3. Run pytest.
4. Run `scripts/quality_gate.py`.
5. Run live vault dry-run with `--dry-run-evidence-out`.
6. Review the expected live vault changes and the generated evidence.
7. Apply actual live vault write only after explicit user intent for the actual write.

Dry-run evidence is required before an actual live write. Write it outside this repository, outside the live vault, and outside Google Drive synced folders. Preferred locations are `%LOCALAPPDATA%\06_Stock\dry_run_evidence\` or a path configured with `STOCK_EVIDENCE_DIR`.

Cleanup and ambiguous-file rules:

- Only delete clear cache/system artifacts when explicitly requested, such as `.pyc`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.ipynb_checkpoints`, or an empty `__pycache__`.
- If a cache folder contains unknown non-cache files such as `*.DOCX`, `*.xlsx`, `.tmp.drive*`, or unfamiliar generated-looking names, report filenames only and do not delete the folder or file.
- Do not delete `.tmp.drivedownload` or `.tmp.driveupload` before user confirmation.
- Exclude files with `Personal` or `personal` in the filename from cleanup, merge, rename, and delete decisions.
- Do not delete, merge, rename, or consolidate README or template files before user confirmation, even if they look duplicated.

The standard entrypoint enforces the live-write gate for the configured live vault path and any child path under it. First create a privacy-safe dry-run evidence file:

```bash
python 70_Imports/scripts/main.py all \
  --vault-root "C:\Users\KSLV-II\Desktop\Obsidian\ESJ\06_Stock" \
  --raw-dir "C:\Users\KSLV-II\Desktop\Obsidian\ESJ\06_Stock\70_Imports\raw" \
  --dry-run \
  --dry-run-evidence-out "%LOCALAPPDATA%\06_Stock\dry_run_evidence\live-dry-run.json"
```

Actual live writes through `70_Imports/scripts/main.py` require all confirmation flags and `--live-dry-run-evidence` pointing to the matching valid evidence file:

```bash
python 70_Imports/scripts/main.py all \
  --vault-root "C:\Users\KSLV-II\Desktop\Obsidian\ESJ\06_Stock" \
  --raw-dir "C:\Users\KSLV-II\Desktop\Obsidian\ESJ\06_Stock\70_Imports\raw" \
  --live-baseline-updated \
  --live-tests-passed \
  --live-quality-gate-passed \
  --live-dry-run-reviewed \
  --live-expected-changes-reviewed \
  --live-dry-run-evidence "%LOCALAPPDATA%\06_Stock\dry_run_evidence\live-dry-run.json" \
  --live-write-confirmation LIVE_06_STOCK_WRITE_REVIEWED
```

Use `STOCK_LIVE_VAULT_ROOT` if the live vault path is different on a local machine. Dry-runs against the live vault do not require the actual-write flags, but actual writes are blocked when dry-run evidence is missing, stale, invalid, mismatched to vault/raw/options, or no longer matches raw metadata.

Known normalization rules:

- Do not double-count overseas positions when both comprehensive holdings and `overseas_balance` files contain the same overseas position.
- Overseas duplicate detection uses canonical keys based on parenthesized symbol, known ISIN alias, or normalized name.
- Company note creation reuses existing notes by canonical key to avoid recreating semantic duplicates.
- Store `currency` and `fx_rate` separately; `currency` must contain a currency code only.
- Treat USD cash/예수금 as cash, not stock.
- For cash rows, currency codes in ticker/security name override source-type defaults.
- Exclude cash assets from Company note QA.
- Skip overseas cashflow amount-only helper rows with no date, ticker, name, or memo; record the skip reason in `skipped_rows.csv`.

## Initial Holdings Template

`70_Imports/templates/initial_holdings_template.xlsx` is not committed because spreadsheet files are ignored by default. If you need an initial holdings workbook, create it locally from the instructions in `70_Imports/templates/README.md` and keep it under `70_Imports/raw/` in a private vault.

Adding a blank `.xlsx` template to the repository should be a separate reviewed change with an explicit `.gitignore` exception.

## FX Rates Template

Use `70_Imports/templates/fx_rates_template.csv` as the schema reference for a private local `fx_rates.csv`.

Recommended local paths are `70_Imports/fx_rates.csv` or `70_Imports/raw/fx_rates.csv` in the private vault. Keep filled FX files out of Git if they include broker-derived or private workflow notes.

Required columns:

```text
effective_date,base_currency,quote_currency,rate,source_type,provider,use_case,status,source_note
```

Only archived same-date rows with usable status such as `approved`, `cached`, `official`, or `verified` are eligible for conversion.

## FX Provenance A-1 PoC

`70_Imports/scripts/fx_provenance_fetcher.py` and `70_Imports/scripts/fx_provenance_validator.py` provide a minimal official-FX archive candidate workflow for REC-EX-01 review support.

This workflow is not a live-vault write path and does not close REC-EX-01. It treats `fx_rate_requirements.csv` as a private work queue, generates or validates append-only archive candidates, and emits sanitized validation decisions such as `candidate_resolved_by_archived_fx` or `still_review_gated`.

Default operation is report-only. Provider network attempts require explicit opt-in with `FX_PROVENANCE_ENABLE_NETWORK=1`, and provider secrets must come only from environment variables such as `BOK_ECOS_API_KEY` or `KOREAEXIM_API_KEY`.

See `40_Knowledge/FX_Provenance_Runbook.md` for the operator workflow. Keep private requirement, archive, and validation CSVs outside Git.

## Safety Notes

- Do not copy `.git/` from the live vault.
- Do not copy broker raw files, processed files, exports, logs, attachments, trade notes, company folders, journal entries, or library materials into this repository.
- Treat ambiguous files as private until reviewed.
- Run `git status --short` and staged-file checks before every commit.
