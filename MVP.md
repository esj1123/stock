# MVP.md

## MVP Goal

Maintain a safe, testable baseline for 06_Stock import and review automation
while keeping all private stock data and live-vault writes approval-gated.

## Current Must Have

- Repository-level Codex rules and read order.
- Clear product, scope, data, safety, phase, approval, verification, and handoff
  contracts.
- Import pipeline code under `70_Imports/scripts/`.
- Synthetic or private-free tests for pipeline contracts.
- Root quality gate for import, raw immutability, generated Markdown, processed
  output schema, data contracts, sensitive-pattern checks, and live-write gates.
- Prompt, template, and dashboard baseline files that do not contain private
  broker data.
- Live-vault dry-run evidence before any actual live write.
- Report-only FX provenance candidate workflow that stays outside live writes
  and does not close review records by itself.

## Out Of Scope By Default

- Raw broker files and filled FX files.
- Generated processed CSVs, exports, logs, database files, dashboards, Company
  notes, trade notes, cashflow notes, journal entries, library notes, and
  attachments.
- Broker credentials, certificates, API secrets, tokens, account identifiers,
  or order passwords.
- Live-vault writes without explicit dry-run evidence review and owner intent.
- Automatic trading, broker API order placement, or recommendation generation.
- CI, release publication, tag movement, artifact upload, deployment, RAG,
  embeddings, vector databases, or external automation unless separately
  approved.

## Current Acceptance Criteria

- Root contracts exist and point future Codex work to repository-local rules.
- Private and generated data paths remain ignored and no-touch by default.
- Code changes include focused synthetic tests when behavior changes.
- `python -m pytest` from `70_Imports/scripts` and `python scripts/quality_gate.py`
  pass or are reported as `NOT RUN` with a reason.
- Live-vault actual writes are blocked unless all confirmation flags and matching
  dry-run evidence are present.
- Closeout reports changed files, commands run, commands not run, safety checks,
  risks, and next step.
