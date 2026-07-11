# PHASE_PLAN.md

## Purpose

Define phase-gated work for 06_Stock baseline automation.

## Phase Table

| phase | goal | allowed work | verification | exit criteria | status |
|---|---|---|---|---|---|
| P0 | Governance baseline | Root contracts, scope, safety, verification, and handoff docs | Changed-file review and diff hygiene | Future Codex work has clear read order and no-touch zones | active |
| P1 | Baseline maintenance | Docs, prompts, templates, import code, synthetic tests | `python -m pytest`, `python scripts/quality_gate.py` | Tests and quality gate pass or honest NOT RUN reason recorded | active |
| P2 | Data-contract evolution | Changes to import classification, accounting, QA, dashboards, or FX requirements | Focused tests plus full local verification | ACCEPTANCE_TRACE rows updated | active |
| P3 | FX provenance review support | Report-only candidate fetching/validation and sanitized runbooks | Focused FX tests and quality gate | Review-gated decisions remain explicit | active |
| P4 | Live-vault dry-run | Dry-run against live vault with evidence output outside repo/vault | Dry-run evidence review | Expected changes reviewed and recorded | approval required |
| P5 | Actual live-vault write | Apply approved live changes only | Matching dry-run evidence plus confirmation flags | Closeout records actual write scope | approval required |

## Phase Rules

- Do not skip verification silently.
- Do not treat docs-only approval as permission for live writes.
- Do not treat FX candidate evidence as closure of review exceptions.
- Do not create trading, advice, release, CI, RAG, or external automation unless
  a separate phase approval names the files and side effects.
- Record approvals before crossing from repository baseline work to live-vault
  dry-run or actual live write.

## Current Phase

P1/P2/P3 governed baseline maintenance, data-contract evolution, and FX
provenance review support.

The current baseline includes verified import/QA/dashboard contracts and
report-only FX provenance support. P4 live-vault dry-run and P5 actual live-vault
write are not active by default and still require their own evidence and owner
approval. This phase state does not authorize raw mutation, generated-output
commits, trading behavior, provider network calls, release activity, or
downstream publication.

## Next Phase Gate

Before any new behavior change or P4/P5 transition, identify:

- target data contract or safety contract;
- allowed files;
- no-touch folders;
- focused tests;
- full verification commands;
- live-vault dry-run status, if relevant.
