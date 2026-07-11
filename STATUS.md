# STATUS.md

## Current Phase

P1/P2/P3 governed baseline maintenance, data-contract evolution, and FX
provenance review support. P4/P5 live-vault dry-run and actual-write work remain
separately approval-gated.

## Current State

The repository is a clean baseline for 06_Stock automation, prompts, templates,
and review docs. It is not the live stock vault and must not contain private
broker exports or generated personal investment records.

As of 2026-07-11, `main` at `d13acd2` includes the current July baseline for
Portfolio update/freshness displays, explicit broker snapshot-date preservation,
and the optional private holdings snapshot as-of register.

The as-of register applies only to holdings/balance rows that lack a
broker-provided snapshot date. It preserves broker dates, never promotes a
transaction-history date into current holdings, and labels an applied date as
user-confirmed display/review context rather than broker provenance. The
optional private register was not present for this rebaseline, so `date missing`
remains the expected operator-visible state until separately approved input is
provided.

FX provenance tooling remains candidate/review support. Reviewed
official-FX-unavailable rows and REC-EX-01/REC-EX-12 remain review-gated; this
baseline does not authorize nearby-date substitution, forward fill, today-rate
backfill, or automatic closure.

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

Use `VERIFICATION.md` for the command contract and `ACCEPTANCE_TRACE.md` for the
durable evidence record.

The 2026-07-11 clean-HEAD rebaseline of `d13acd2` recorded:

- holdings snapshot as-of focused tests: 4 passed;
- full pytest: 344 passed;
- quality gate: 19 checks passed with no warning;
- `git diff --check`: passed;
- repository status: clean and synchronized with `origin/main` before the
  docs-only rebaseline edit;
- repo-root `.venv`: absent;
- GitHub Actions runs: none available, so local verification remains the
  operating evidence.

No live-vault dry-run, actual live write, private register creation, provider
network access, or REC closure was performed for this rebaseline.
