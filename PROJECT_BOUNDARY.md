# PROJECT_BOUNDARY.md

## Purpose

Define the working boundary for 06_Stock baseline automation.

## In Scope

- Repository-level governance docs and handoff records.
- Safe prompt, template, dashboard, and operating guide baselines under
  `00_Config/`, `05_Principles/`, `10_Dashboard/`, `40_Knowledge/`, and
  `99_Templates/`.
- Import pipeline code and synthetic tests under `70_Imports/scripts/`.
- Import template instructions under `70_Imports/templates/`.
- Root helper scripts under `scripts/`.
- Review-only FX provenance candidate tooling when it stays private-data-safe,
  report-only, and approval-gated for network use.

## Out Of Scope By Default

- Live stock vault mutation.
- Broker order placement or broker trading API integration.
- Investment advice, buy/sell recommendations, automatic thesis, or automatic
  sell criteria generation.
- Private raw broker input, generated processed output, generated dashboards,
  database files, Excel workbooks, attachments, and private notes.
- Secrets, credentials, certificates, account identifiers, tokens, API keys, or
  order passwords.
- Release publication, tag movement, CI activation, artifact upload, deployment,
  RAG, embeddings, vector databases, or external automation.

## No-Touch Zones

| zone | reason | approval path |
|---|---|---|
| Live Obsidian stock vault | Private live target and final note destination | Dry-run evidence review plus explicit live-write intent |
| `70_Imports/raw/` | Private broker exports | Read-only input only; do not commit or modify |
| `70_Imports/processed/` | Generated personal outputs | Generated locally only; do not commit |
| `70_Imports/exports/` | Generated exports | Generated locally only; do not commit |
| `70_Imports/logs/` | Local run logs | Generated locally only; do not commit |
| `20_Companies/` | Private company notes | Live vault only unless a synthetic fixture is explicitly approved |
| `30_Trades/` | Private trade notes | Live vault only unless a synthetic fixture is explicitly approved |
| `31_Cashflows/` | Private cashflow notes | Live vault only unless a synthetic fixture is explicitly approved |
| `50_Journal/` | Private journal notes | Live vault only |
| `60_Library/` | Private library material | Live vault only |
| `90_Attachments/` | Private attachments | Live vault only |
| `.venv/`, `.pytest_cache/`, `.tmp_pytest*/`, `pytest-cache-files-*` | Local execution artifacts | Do not use as source material; cleanup requires approval when ambiguous |

## Approval-Required Changes

- Any actual write to the live vault or a Google Drive synced vault.
- Any deletion, move, rename, merge, or cleanup of private-looking or ambiguous
  files.
- Any command that uses provider network access for FX provenance.
- Any creation of `.csv`, `.db`, `.sqlite`, `.sqlite3`, `.xls`, or `.xlsx`
  artifacts intended for commit.
- Any workflow, CI, release, push, tag, publication, or deployment behavior.
- Any external service integration, credential handling, or trading API behavior.

## Boundary Notes

When in doubt, treat a file as private until a repo-local synthetic fixture or
explicit approval proves otherwise.
