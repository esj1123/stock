# DATA_SCOPE.md

## Purpose

Define data classes and handling rules for 06_Stock baseline automation.

## Data Classes

| data class | allowed in Git | storage | notes |
|---|---|---|---|
| Repository docs and policy | yes | root and approved docs folders | Must avoid private values |
| Synthetic test fixtures | yes | `70_Imports/scripts/tests/` | Preferred for tests and examples |
| Prompt and template baselines | yes | `00_Config/`, `99_Templates/`, `70_Imports/templates/` | Must not contain private account data |
| Private broker raw files | no | private live vault only | Read-only input; never commit or paste values |
| Processed CSV outputs | no by default | private generated folders | Generated evidence only; keep ignored unless separately approved |
| Dry-run evidence | no by default | outside repo and outside live vault | Preferred under local app data |
| FX rate work queues or archives | no by default | private local operator path | Commit only blank schemas or sanitized templates |
| Secrets and credentials | no | environment or external secret store only | Never store in repo or docs |
| Live-vault Markdown | no by default | live vault only | Use dry-run and explicit approval before mutation |

## Forbidden Material

- Broker passwords, order passwords, certificates, tokens, API keys, account
  identifiers, or personal identifiers.
- Raw broker Excel, CSV, export, statement, transaction, balance, or cashflow
  files.
- Generated processed CSVs, dashboards, database files, exports, logs, or local
  report artifacts.
- Company notes, trade notes, cashflow notes, journal entries, attachments, and
  generated Obsidian output from the live vault.
- Investment advice, automatic buy/sell recommendations, automatic thesis text,
  or automatic sell criteria.

## Handling Rules

- Use synthetic fixtures for tests.
- Keep private raw files read-only.
- Preserve user-written Markdown outside `AUTO-GENERATED` markers.
- Do not paste matched secret or private-data values into closeout.
- Record only filenames, counts, statuses, digests, schemas, or sanitized
  summaries when evidence is needed.
- Use environment variables for provider credentials; do not store provider
  secrets in config files.
- Treat provider network access as opt-in and approval-bound.

## Review Checklist

- Private broker input absent from tracked changes.
- Generated outputs absent from tracked changes unless explicitly approved.
- Secrets and account identifiers absent from tracked changes.
- Live-vault path writes were not performed, or explicit dry-run evidence and
  live-write intent were recorded.
- Tests use synthetic fixtures or private-free schemas.
- New docs do not broaden trading, advice, network, or live-write permission.
