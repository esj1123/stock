# FX Provenance Runbook

## Purpose

This runbook describes the A-1/A-2 proof of concept for REC-EX-01 FX/KRW provenance support.

The goal is not to close REC-EX-01. The goal is to turn historical `fx_rate_requirements.csv` work-queue rows into official same-date FX archive candidates, then validate those candidates before any operator decides whether they can become private archive evidence.

## A-1/A-2 Scope

Included:

- Normalize historical FX requirements by `event_date`, currency, and `use_case`.
- Generate append-only FX archive candidate rows.
- Validate candidates against same-date, KRW quote, provider, source type, status, source note, and response hash rules.
- Produce sanitized validation reports for human review.
- Fetch same-date official FX candidates from configured providers when explicitly requested.
- Keep provider responses as candidate evidence only until operator review.

Excluded:

- Live vault writes.
- Processed output regeneration.
- REC-EX-01 closure.
- Raw broker file scanning.
- Broker portal automation.
- Chrome extension, Computer Use, or browser workflows.
- Broker-header-audit implementation.
- Default integration tests that need real API keys.

## Inputs

Private operator-supplied inputs:

- `fx_rate_requirements.csv`
- Optional existing private FX archive CSV

The repository template schema for private rates is `70_Imports/templates/fx_rates_template.csv`.

Do not commit filled private CSV files.

## Outputs

Private operator-supplied output paths:

- FX archive candidate CSV
- Sanitized validation result CSV

Recommended local output locations are outside this repository, outside the live vault, and outside Google Drive synced folders.

## Provider Environment Variables

Provider network calls are disabled by default.

Use only environment variables for secrets:

- `FX_PROVENANCE_ENABLE_NETWORK=1`
- `BOK_ECOS_API_KEY`
- `KOREAEXIM_API_KEY`
- `BOK_ECOS_STAT_CODE`
- `BOK_ECOS_USD_ITEM_CODE`

Never place API keys in CLI arguments, docs, source files, output CSVs, request URLs, or logs.

The Korea Eximbank adapter uses `KOREAEXIM_API_KEY` and the official HTTPS API host `oapi.koreaexim.go.kr`. It currently accepts only USD/KRW same-date candidates using `deal_bas_r`.

The BOK ECOS adapter is intentionally configuration-gated. It does not guess official series metadata. Set `BOK_ECOS_STAT_CODE` and `BOK_ECOS_USD_ITEM_CODE` only after verifying the official daily USD/KRW series metadata. Without those values, BOK returns `policy_blocked`.

## CLI Pattern

Default report-only validation:

```bash
python 70_Imports/scripts/fx_provenance_fetcher.py \
  --requirements-path <private_fx_rate_requirements.csv> \
  --archive-in <private_fx_archive.csv> \
  --validation-out <private_fx_validation_result.csv> \
  --provider bok,eximbank \
  --report-only
```

Provider fetch attempts require both explicit CLI and environment opt-in:

```bash
FX_PROVENANCE_ENABLE_NETWORK=1 python 70_Imports/scripts/fx_provenance_fetcher.py \
  --requirements-path <private_fx_rate_requirements.csv> \
  --validation-out <private_fx_validation_result.csv> \
  --provider bok,eximbank \
  --fetch
```

Provider preview does not write archive rows unless a separate operation explicitly supplies `--archive-out` and `--write-archive`. Archive write is not approved for REC-EX-01 preview.

`--fetch` and `--report-only` are mutually exclusive. If neither mode is supplied, the CLI defaults to report-only behavior.

## Aggregate Semantics

Validation decisions are requirement-level. These counts should add up by distinct requirement key:

- `candidate_resolved_count`
- `still_review_gated_count`
- `invalid_requirement_count`
- `date_mismatch_count`
- `policy_blocked_count`
- `insufficient_evidence_count`

Provider failure counts are attempt-level during fetch preview:

- `provider_error_count`
- `provider_not_found_count`

For example, if BOK fails for one requirement and Eximbank then succeeds for the same requirement, the report can show both one provider failure attempt and one candidate-resolved requirement. This is expected. Do not interpret provider failure counts as unresolved requirement counts.

## Validation Decisions

Possible decisions:

- `candidate_resolved_by_archived_fx`
- `still_review_gated`
- `invalid_requirement`
- `provider_not_found`
- `provider_error`
- `policy_blocked`
- `date_mismatch`
- `rate_type_blocked`
- `insufficient_evidence`

`candidate_resolved_by_archived_fx` is a review candidate only. It does not close REC-EX-01.

## Strict Matching Rules

A candidate can pass only when all conditions hold:

- `effective_date == event_date`
- `base_currency == requirement.currency`
- `quote_currency == KRW`
- `rate` is numeric and greater than zero
- provider is allowlisted
- source type is usable by the pipeline
- status is usable by the pipeline
- `source_note` is non-empty and redacted
- `response_sha256` is present

Blocked cases:

- Weekend or holiday previous-business-day substitution.
- Today's FX rate applied to a historical event date.
- Forward fill.
- Non-KRW quote currency.
- Missing provider, source note, or response hash.
- API keys or tokens in source URL templates.

## Operator Review Flow

1. Keep REC-EX-01 Group A as `accepted as review-gated`.
2. Review `fx_rate_requirements.csv` as a work queue only.
3. Generate or collect official same-date FX archive candidates in a private path.
4. Run the validator in report-only mode.
5. Review candidate decisions and blocked decisions.
6. Only after human review should private `fx_rates.csv` or cache be updated.
7. Re-run the import pipeline separately after normal dry-run and live-write gates.

## Keep Review-Gated When

- No same-date official FX candidate exists.
- The candidate uses a previous business day.
- The candidate uses today's rate for a historical event date.
- The provider/source/status is not allowlisted.
- The source note or response hash is missing.
- The decision is anything other than `candidate_resolved_by_archived_fx`.

## Future Phases

Future work may add:

- Real BOK/Eximbank parser implementations.
- Broker-header-audit for detecting broker-provided same-date FX/KRW evidence.
- Browser or Computer Use fallback only with a dedicated browser profile or isolated VM, explicit user approval, and human supervision.

Chrome extension, Computer Use, and broker portal automation are intentionally out of scope for A-1.
