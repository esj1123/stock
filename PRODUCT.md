# PRODUCT.md

## Product Name

06_Stock Baseline Automation.

## Product Category

Governed Obsidian vault automation baseline for private stock records.

## Purpose

Provide a reviewable baseline for stock-vault import code, templates, prompts,
QA checks, and operating guides without exposing private broker data or live
vault contents.

This repository is the development and review surface. The live stock vault is
a separate private target and must not be treated as the repository output
folder.

## Target Users

- The repository owner operating a private stock Obsidian vault.
- Future Codex sessions making scoped baseline changes.
- Reviewers checking import, QA, FX provenance, and live-write safety behavior.

## Core Value

- Keep private broker inputs and generated investment records out of Git.
- Preserve user-written Markdown outside approved auto-generated markers.
- Separate current holdings, cashflows, income, expenses, FX requirements,
  realized PnL, performance, and reconciliation status.
- Require tests, quality gate checks, dry-run evidence, and explicit approval
  before any live-vault write.
- Support report-only FX provenance review without closing review gates too
  early.

## Non-Goals

- Store raw broker exports, account identifiers, generated CSVs, database files,
  Excel workbooks, attachments, or private notes in this repository.
- Operate as the live Obsidian vault.
- Place orders, automate trading, store order passwords, or connect to broker
  trading APIs.
- Generate investment advice, buy/sell recommendations, thesis text, or sell
  criteria automatically.
- Publish releases, push branches, or run external services without separate
  approval.
