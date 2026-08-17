# STATUS.md

## Current Phase

P1/P2/P3 governed baseline maintenance, data-contract evolution, and FX
provenance review support. P4/P5 live-vault dry-run and actual-write work remain
separately approval-gated.

## Current State

The repository is a clean baseline for 06_Stock automation, prompts, templates,
and review docs. It is not the live stock vault and must not contain private
broker exports or generated personal investment records.

As of 2026-07-12, the validated implementation at `main` commit `0d7a2c6`
includes the source-index-safe holdings snapshot as-of fallback in addition to
the July Portfolio update/freshness displays and broker snapshot-date
preservation.

The as-of register applies only to holdings/balance rows that lack a
broker-provided snapshot date. It preserves broker dates, never promotes a
transaction-history date into current holdings, and labels an applied date as
user-confirmed display/review context rather than broker provenance.

The approved private register contains three user-confirmed scopes for
`2026-06-30`. Fresh dry-run validation applied the date to all 15 current
holdings rows and all 3 matching source-index rows, with zero transaction-history
applications, zero conflicts, and unchanged non-date holdings values. An
explicitly approved actual live write completed on 2026-07-11 with exit 0. The
post-write aggregate check confirmed the same 15/15 and 3/3 application counts,
zero transaction-history promotion, zero conflicts, and an unchanged raw
metadata fingerprint. The 2026-07-12 Portfolio screen check confirmed the
user-confirmed date label and broker-export disclaimer.

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

The 2026-07-11 implementation and live-apply validation recorded:

- holdings snapshot as-of focused tests: 7 passed;
- full pytest: 347 passed;
- quality gate: 19 checks passed with no warning;
- `git diff --check`: passed;
- fresh live-vault dry-run: exit 0 with OS-local evidence;
- aggregate diagnostic: holdings 15/15, source index 3/3, transaction history 0,
  and conflicts 0;
- dry-run raw, live processed, and dashboard Markdown metadata: unchanged;
- explicitly approved actual live write: exit 0;
- post-write aggregate diagnostic: holdings 15/15, source index 3/3,
  transaction history 0, and conflicts 0;
- post-write raw metadata fingerprint: unchanged;
- 2026-07-12 Portfolio screen verification: user-confirmed `2026-06-30` label
  and broker-export disclaimer present;
- repo-root `.venv`: absent;
- GitHub Actions runs: none available, so local verification remains the
  operating evidence.

The dry-run reported one unrelated missing Company note warning; no note was
created. The private register, OS-local evidence, and approved live output now
reflect the user-confirmed date. No provider network access or REC closure was
performed; REC-EX-01 and REC-EX-12 remain review-gated.
