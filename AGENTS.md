# Stock Baseline Agent Rules

## Read Order

Before changing files, read these repository-level contracts in order:

1. `AGENTS.md`
2. `PRODUCT.md`
3. `MVP.md`
4. `STATUS.md`
5. `PROJECT_BOUNDARY.md`
6. `DATA_SCOPE.md`
7. `PHASE_PLAN.md`
8. `APPROVALS.md`
9. `SAFETY_POLICY.md`
10. `VERIFICATION.md`
11. `ACCEPTANCE_TRACE.md`
12. `AI_HANDOFF.md`
13. `README.md`

## Project Scope
- This repository is the clean GitHub baseline for `06_Stock` automation code, templates, prompts, and documentation.
- It is not the live investment vault and it is not the actual Obsidian folder.
- The Codex workspace `C:\Users\KSLV-II\Desktop\Codex\stock` is a baseline/review repository only.
- The actual live/final Obsidian vault is [C:\Users\KSLV-II\Desktop\Obsidian\ESJ\06_Stock](C:/Users/KSLV-II/Desktop/Obsidian/ESJ/06_Stock/).
- The live Google Drive `06_Stock` vault must remain local/private.
- The standard entrypoint is `70_Imports/scripts/main.py`.
- New pipeline work should stay in `70_Imports/scripts/nh_importer.py`, `portfolio_model.py`, `obsidian_writer.py`, and `qa_checker.py` unless the task explicitly expands scope.
- `70_Imports/scripts/namoo_excel_import.py` is compatibility-only; do not extend it for new pipeline behavior unless requested.

## Live Vault Rule
- Never begin by editing the live Google Drive vault.
- First modify and validate this GitHub baseline, then run tests, the quality gate, and a live-vault dry-run.
- All live-vault work and final Obsidian output must be applied under `C:\Users\KSLV-II\Desktop\Obsidian\ESJ\06_Stock`.
- Do not treat `C:\Users\KSLV-II\Desktop\Codex\stock` as the final Obsidian vault or final note destination.
- Actual live-vault writes require an expected dry-run result and explicit user intent for the live write.
- Do not copy live vault files into this repository.

## Hard Safety Rules
- Do not add, copy, commit, print, or expose private broker data, raw Excel files, processed CSV files, SQLite DB files, company notes, trade notes, cashflow notes, attachments, journal entries, or generated outputs.
- Do not store broker passwords, order passwords, certificates, API keys, tokens, or account numbers.
- Do not add automatic order placement, broker API trading, buy/sell automation, or password storage.
- Do not automatically write investment thesis, sell criteria, buy recommendations, sell recommendations, or investment opinions.
- Missing thesis or sell criteria must be reported only through QA/Review Queue artifacts.
- Treat raw broker files as read-only inputs. Import code may read from `70_Imports/raw/` but must never modify files there.

## Data Contracts To Preserve
- `currency` must contain a currency code only, such as `KRW`, `USD`, or `JPY`.
- FX rates must be stored separately from `currency`; values such as `1473.10` must never appear in `currency`.
- Overseas holdings must not be double-counted when both comprehensive `holdings` files and `overseas_balance` files include the same overseas position.
- USD, cash, and `예수금` balances must be normalized as `asset_type=cash`.
- Cash assets are not Company note QA targets and must be excluded from thesis/sell-criteria Company QA.
- Transaction-history rows must not be treated as current holdings.
- AUTO-GENERATED Markdown updates may only replace content between `<!-- AUTO-GENERATED:START -->` and `<!-- AUTO-GENERATED:END -->` markers.
- User-written Markdown outside AUTO-GENERATED markers must remain unchanged.

## Required Checks Before Closeout
- Review the diff for duplicate symbols, unnecessary new files, shared utility pollution, scope creep, and accidental private-data exposure.
- Run `cd 70_Imports/scripts` then `python -m pytest`.
- Run from the repository root: `python scripts/quality_gate.py`.
- Before any live vault write, run the import against the live vault with `--dry-run` and inspect the expected file changes.
- Report changed files, commands run, safety checks, and any unresolved risks.

## Files Allowed To Edit
- Root policy/docs: `AGENTS.md`, `README.md`, `ACCEPTANCE_TRACE.md`.
- Automation docs and prompt/template baselines under `00_Config/`, `05_Principles/`, `10_Dashboard/`, `40_Knowledge/`, and `99_Templates/` when the task asks for baseline documentation/template changes.
- Pipeline code under `70_Imports/scripts/`.
- Import templates under `70_Imports/templates/`.
- Root helper scripts under `scripts/`.
- Ignore/config files such as `.gitignore` when needed for repository hygiene.

## Files And Folders Restricted From Editing Or Committing
- `70_Imports/raw/`
- `70_Imports/processed/`
- `70_Imports/exports/`
- `70_Imports/logs/`
- `20_Companies/`
- `30_Trades/`
- `31_Cashflows/`
- `50_Journal/`
- `60_Library/`
- `90_Attachments/`
- Any private generated `.csv`, `.db`, `.sqlite`, `.sqlite3`, `.xls`, or `.xlsx` file.
- Any local credentials, `.env` files, certificates, tokens, broker exports, or account identifiers.

## Google Drive Live Vault Policy
- Google Drive synced folders are side-effecting live targets.
- Do not create `.venv`, caches, generated outputs, or temporary agent files inside the live vault or synced folder by default.
- Use `STOCK_VENV_DIR` for an explicit virtual environment location; otherwise wrappers must use an OS-local app-data path outside the vault.
- Live vault execution must preserve raw files, preserve user-written Markdown, and summarize `Import_Review`, `Review_Queue`, and `QA_Exceptions` after execution.
