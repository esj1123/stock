---
name: fx-official-fetch
description: Use when generating official same-date FX archive candidates from fx_rate_requirements for 06_Stock REC-EX-01 review. Scope is strict: no raw broker reads, no processed regeneration, no live vault write, no browser or broker automation, and no network unless explicitly opted in through FX_PROVENANCE_ENABLE_NETWORK.
---

# FX Official Fetch

Use this skill for the A-1 official FX archive candidate workflow.

Hard limits:
- Do not read or mutate `70_Imports/raw/`.
- Do not mutate `70_Imports/processed/`, `exports/`, or `logs/`.
- Do not write to the live vault.
- Do not use browser automation, broker portals, broker APIs, Chrome extensions, or Computer Use.
- Do not print raw filenames, account identifiers, tickers, holdings, amounts, raw rows, API keys, or request URLs with secrets.
- Do not close REC-EX-01.

Workflow:
1. Read repository contracts first: `05_Principles/FX_Conversion_Rules.md`, `README.md`, and `ACCEPTANCE_TRACE.md`.
2. Treat `fx_rate_requirements.csv` as a private operator-supplied work queue, not a rate source.
3. Normalize each requirement to `event_date|currency|use_case`; ignore `amount_native_sum` for decisions and reports.
4. Use `70_Imports/scripts/fx_provenance_fetcher.py` for archive candidate generation.
5. Keep default `--report-only` unless the user explicitly requests provider fetch and has opted in with `FX_PROVENANCE_ENABLE_NETWORK=1`.
6. Read provider secrets only from environment variables (`BOK_ECOS_API_KEY`, `KOREAEXIM_API_KEY`) and never echo them.
7. Write archive candidates only to explicit private paths outside the repo and outside the live vault.

Completion rule:
- The output is a candidate archive/report for human review only. REC-EX-01 remains review-gated until a reviewed same-date archived FX row is accepted into the private archive and validated.
