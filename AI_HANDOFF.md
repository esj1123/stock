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

Repository baseline work only, unless the user explicitly approves a broader
task. The 2026-06-09 harness seed approved root documentation writes only.

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
