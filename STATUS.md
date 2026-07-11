# STATUS.md

## Current Phase

P1/P2/P3 governed baseline maintenance, data-contract evolution, and FX
provenance review support. P4/P5 live-vault dry-run and actual-write work remain
separately approval-gated.

## Current State

The repository is a clean baseline for 06_Stock automation, prompts, templates,
and review docs. It is not the live stock vault and must not contain private
broker exports or generated personal investment records.

As of 2026-07-11, the validated implementation built on `main` parent `a684ec4` includes the
source-index-safe holdings snapshot as-of fallback in addition to the July
Portfolio update/freshness displays and broker snapshot-date preservation.

The as-of register applies only to holdings/balance rows that lack a
broker-provided snapshot date. It preserves broker dates, never promotes a
transaction-history date into current holdings, and labels an applied date as
user-confirmed display/review context rather than broker provenance.

The approved private register now contains three user-confirmed scopes for
`2026-06-30`. Fresh dry-run validation applied the date to all 15 current
holdings rows and all 3 matching source-index rows, with zero transaction-history
applications, zero conflicts, and unchanged non-date holdings values. Actual
processed/generated live-vault output has not been written.

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

The 2026-07-11 source-index fallback validation recorded:

- holdings snapshot as-of focused tests: 7 passed;
- full pytest: 347 passed;
- quality gate: 19 checks passed with no warning;
- `git diff --check`: passed;
- fresh live-vault dry-run: exit 0 with OS-local evidence;
- aggregate diagnostic: holdings 15/15, source index 3/3, transaction history 0,
  and conflicts 0;
- raw, live processed, and dashboard Markdown metadata: unchanged;
- repo-root `.venv`: absent;
- GitHub Actions runs: none available, so local verification remains the
  operating evidence.

The dry-run reported one unrelated missing Company note warning; no note was
created. The private register and OS-local evidence exist, but no actual
processed/generated live write, provider network access, or REC closure was
performed.
