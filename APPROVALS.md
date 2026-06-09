# APPROVALS.md

## Purpose

Record explicit approvals for side effects in 06_Stock baseline automation.

## Approval Table

| approval_id | requested action | side effect | approver | status | evidence | notes |
|---|---|---|---|---|---|---|
| APR-STK-20260609-001 | Apply codex-dev-harness root contract layer to `stock` | Local repository documentation write only | Owner request in Codex thread | APPROVED | User requested applying to stock first on 2026-06-09 | Does not approve live-vault writes, raw data access, generated output commits, network calls, trading behavior, push, tag, or release |

## Approval Rules

- Dry-run before live mutation.
- Record expected live-vault changes before actual live writes.
- Do not approve broad or unclear side effects.
- Treat cleanup, deletion, move, rename, merge, and consolidation as side
  effects when they touch live vault, private data, or ambiguous files.
- Treat network provider use for FX provenance as opt-in.
- Keep approval evidence identifier-first; do not paste private raw values into
  this file.

## Actions Requiring Separate Approval

- Actual live-vault write.
- Live-vault cleanup or file movement.
- Raw broker input mutation.
- Generated private output commit.
- Provider network access or credential use.
- CI workflow creation or enablement.
- Push, tag, release, publication, signing, deployment, or artifact upload.
- Trading API, order placement, order password handling, or broker account
  mutation.

## Closeout Requirements

For each approved side effect, closeout must report:

- approval id;
- files changed;
- commands run;
- commands intentionally not run;
- generated artifacts;
- live-vault dry-run or actual-write status;
- safety checks;
- risks and assumptions.
