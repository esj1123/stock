# STATUS.md

## Current Phase

Governed baseline maintenance with live-vault writes approval-gated.

## Current State

The repository is a clean baseline for 06_Stock automation, prompts, templates,
and review docs. It is not the live stock vault and must not contain private
broker exports or generated personal investment records.

As of 2026-06-09, a codex-dev-harness root contract layer is being applied to
make future Codex work easier to scope, verify, and hand off. This harness layer
is documentation-only and does not alter import behavior, processed outputs,
live-vault paths, trading behavior, or FX provenance logic.

Existing FX provenance review-support surfaces are part of the current repo
context and are not broadened by this harness layer:

- `05_Principles/FX_Conversion_Rules.md`
- `.agents/skills/fx-official-fetch/SKILL.md`
- `.agents/skills/provenance-qa/SKILL.md`
- `40_Knowledge/FX_Provenance_Runbook.md`
- `70_Imports/scripts/fx_provenance_fetcher.py`
- `70_Imports/scripts/fx_provenance_validator.py`
- `70_Imports/scripts/tests/test_fx_provenance_fetcher.py`
- `70_Imports/scripts/tests/test_fx_provenance_validator.py`

Those files remain governed by the same report-only, review-gated, no-live-write
boundary.

## Current Safety Posture

- Repository baseline first.
- Live vault write never first.
- Dry-run evidence before live write.
- Private broker inputs and generated outputs stay out of Git.
- FX provenance candidates are review support only unless separately promoted by
  approved workflow changes.
- No investment recommendation, automatic thesis, automatic sell criteria, or
  trading automation is approved.

## Latest Verification

This file records repository status, not proof of passing verification. Use
`VERIFICATION.md` for current commands.

Harness seed verification should at minimum run `git status --short --branch`,
`git diff --check`, and a changed-file review. Pipeline tests and the quality
gate should be run for behavior changes or reported as `NOT RUN` for scoped
docs-only work.
