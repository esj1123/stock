# SAFETY_POLICY.md

## Purpose

Define safety rules for Codex and human work in the 06_Stock baseline
repository.

## Safety Invariants

- Baseline repository first; live vault never first.
- Read-only inspection before mutation.
- Dry-run before live-vault writes.
- Private broker data and generated investment records stay out of Git.
- Secrets and account identifiers stay out of Git and out of output.
- User-written Markdown outside `AUTO-GENERATED` markers must be preserved.
- No trading automation, order placement, broker account mutation, or order
  password storage.
- No automatic investment advice, buy/sell recommendation, thesis, or sell
  criteria generation.
- No provider network access unless explicitly approved and configured through
  environment variables.

## Side-Effect Classes

| class | examples | default |
|---|---|---|
| Read-only inspection | `git status`, file listing, docs review | allowed |
| Local docs/code edit | Approved repository docs, scripts, templates, synthetic tests | allowed by scoped task |
| Local generated output | processed CSVs, dry-run evidence, temporary pytest output | approval or explicit verification context required |
| Network access | FX provider calls, external APIs | approval required |
| Live-vault dry-run | read live vault and emit expected changes/evidence | approval required |
| Actual live-vault write | create/update/delete/move live vault files | explicit live-write approval required |
| Trading or broker mutation | orders, account changes, credential storage | forbidden by default |

## Sensitive Data Rules

- Do not print, commit, or persist secrets.
- Do not paste private raw row values into docs or closeout.
- Do not copy live vault files into this repository.
- Report private-data findings by path, class, count, or sanitized summary only.
- Treat ambiguous files as private until reviewed.

## Live Vault Rules

Actual live-vault writes require all of the following:

1. Baseline changes completed in this repository.
2. Tests passed or an approved exception recorded.
3. Quality gate passed or an approved exception recorded.
4. Dry-run evidence generated outside this repository and outside the live vault.
5. Expected changes reviewed.
6. Explicit owner intent for the actual live write.
7. Matching confirmation flags accepted by the entrypoint.

## Forbidden Defaults

- Do not broaden ignored private folders into tracked output.
- Do not add filled `.csv`, `.db`, `.sqlite`, `.sqlite3`, `.xls`, or `.xlsx`
  files.
- Do not create release, CI, deployment, push, tag, or publication behavior.
- Do not use RAG, embeddings, vector databases, model-output capture, or external
  automation for private data without separate approval.
- Do not clean up ambiguous live-vault or local files without confirmation.
