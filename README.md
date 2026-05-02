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

From a clean clone:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r 70_Imports\scripts\requirements.txt
cd 70_Imports\scripts
..\..\.venv\Scripts\python.exe main.py --help
..\..\.venv\Scripts\python.exe -m pytest
```

On Windows, if `python` resolves to the Microsoft Store alias, use `py -m venv .venv` instead.

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

## Initial Holdings Template

`70_Imports/templates/initial_holdings_template.xlsx` is not committed because spreadsheet files are ignored by default. If you need an initial holdings workbook, create it locally from the instructions in `70_Imports/templates/README.md` and keep it under `70_Imports/raw/` in a private vault.

Adding a blank `.xlsx` template to the repository should be a separate reviewed change with an explicit `.gitignore` exception.

## Safety Notes

- Do not copy `.git/` from the live vault.
- Do not copy broker raw files, processed files, exports, logs, attachments, trade notes, company folders, journal entries, or library materials into this repository.
- Treat ambiguous files as private until reviewed.
- Run `git status --short` and staged-file checks before every commit.
