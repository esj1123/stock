# AI_HANDOFF.md

## Purpose

Give future Codex sessions a compact handoff for 06_Stock baseline automation.

## Read First

Follow the read order in `AGENTS.md`. The important sequence is:

1. Scope and safety rules.
2. Product and MVP contracts.
3. Current status.
4. Project boundary and data scope.
5. Phase and approval rules.
6. Verification expectations.
7. Acceptance trace.

## Current Approved Work Type

P1/P2/P3 repository baseline, data-contract, and report-only provenance-review
work when explicitly requested and scoped. P4/P5 live-vault work, provider
network access, push/release work, and other external side effects still require
separate approval.

## Current Baseline

- Validated implementation: source-index fallback patch committed at `main`
  commit `0d7a2c6`.
- 2026-07-11 validation: 7 focused holdings snapshot as-of tests passed, full
  pytest passed with 347 tests, and all 19 quality-gate checks passed.
- The private `holdings_snapshot_asof.csv` register fills only missing
  holdings/balance snapshot dates. Broker dates win, transaction-history dates
  are never promoted, and applied dates are labeled as user-confirmed
  display/review context.
- The approved private register contains three scopes for `2026-06-30`. Fresh
  dry-run evidence confirms holdings 15/15 and marketless source index 3/3, with
  zero unexpected applications and zero conflicts.
- An explicitly approved actual live write completed on 2026-07-11 with exit 0.
  Post-write checks confirmed holdings 15/15, marketless source index 3/3, zero
  transaction-history promotion, zero conflicts, and an unchanged raw metadata
  fingerprint. The 2026-07-12 Portfolio screen check confirmed the
  user-confirmed date label and broker-export disclaimer.
- FX candidates and reviewed official-FX-unavailable context do not close
  REC-EX-01 or REC-EX-12 and do not authorize date substitution.

## Work Allowed By Default

- Read repository docs and code.
- Make scoped changes to approved repository files when requested.
- Add or update synthetic tests for behavior changes.
- Run repo-local verification commands when they are in scope.
- Report private-data risks by sanitized summary.

## Work Not Allowed By Default

- Editing the live stock vault.
- Copying live vault files or private broker files into this repository.
- Reading or modifying ignored raw/processed/export/log folders unless the task
  explicitly requires a local verification path and the output stays untracked.
- Storing secrets, credentials, account identifiers, tokens, certificates, or
  order passwords.
- Creating trading, order-placement, broker-account mutation, or recommendation
  behavior.
- Running provider network calls unless opt-in approval is explicit.
- Pushing, tagging, releasing, publishing, deploying, creating CI workflows, or
  uploading artifacts.

## Existing FX Provenance Work To Respect

The repository includes FX provenance review-support work in:

- `05_Principles/FX_Conversion_Rules.md`
- `.agents/skills/`
- `40_Knowledge/FX_Provenance_Runbook.md`
- `70_Imports/scripts/fx_provenance_*.py`
- `70_Imports/scripts/tests/test_fx_provenance_*.py`

Do not revert, overwrite, or promote that work beyond report-only review support
unless the owner explicitly asks.

## No-Touch Summary

- Live stock vault.
- `70_Imports/raw/`.
- `70_Imports/processed/`.
- `70_Imports/exports/`.
- `70_Imports/logs/`.
- Private note folders such as `20_Companies/`, `30_Trades/`, `31_Cashflows/`,
  `50_Journal/`, `60_Library/`, and `90_Attachments/`.
- Local environment and cache folders.

## Verification Handoff

- Use `VERIFICATION.md` for the command set.
- Run focused tests for behavior changes.
- Run `python scripts/quality_gate.py` before closing behavior changes unless
  explicitly out of scope.
- Mark skipped checks as `NOT RUN` with reasons.
- For live writes, require dry-run evidence and explicit live-write intent.
- The 2026-07-11 fallback validation found no repo-root `.venv`, no quality-gate
  warning, and no GitHub Actions run; local pytest and quality-gate results are
  the current repository evidence.
- The private register exists, fresh OS-local dry-run evidence confirmed the
  expected holdings/source-index application, and the separately approved
  actual live write completed with matching post-write aggregates.
- Repeat the dry-run if code, register, or raw input changes. Any future actual
  live write still requires matching evidence review and separate explicit
  approval.

## Closeout Format

Every closeout should include:

- outcome;
- files changed;
- commands run;
- commands intentionally not run;
- safety checks;
- live-vault dry-run and actual-write status;
- unresolved risks or assumptions;
- next recommended step.
