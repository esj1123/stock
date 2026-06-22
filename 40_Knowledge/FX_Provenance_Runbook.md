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

The Eximbank key is trimmed before request construction. Whitespace-only keys are blocked before any HTTP request. The normalized key value, key length, fingerprint, full request URL, and raw response body must not be logged or written to reports.

Eximbank AP01 responses are request-date-backed candidates. The official Korea Eximbank API page defines `searchdate` as the requested search date, `AP01` as exchange-rate data, and the response schema does not include a row-level effective-date field. It also states that the exchange-rate API provides daily rate data updated around 11:00 on business days, and that non-business-day data or same-business-day data requested before 11:00 returns null. Under this policy, an Eximbank AP01 USD row without a row-level date can use the requested `searchdate` as the candidate `effective_date` only when the USD row exists, `deal_bas_r` is a valid positive value, and the provider response is not a provider status error. This remains candidate evidence only; it does not close REC-EX-01 and does not approve archive write.

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

Provider canary checks do not use private requirement files and do not write archives:

```bash
FX_PROVENANCE_ENABLE_NETWORK=1 python 70_Imports/scripts/fx_provenance_fetcher.py \
  --canary-date <YYYY-MM-DD> \
  --validation-out <private_fx_validation_result.csv> \
  --provider eximbank \
  --fetch
```

Canary output is parser/connectivity preview only. It does not affect REC-EX-01.

## Provider Diagnostics

Provider fetch preview writes only sanitized diagnostic metadata:

- `provider`
- `request_date`
- `http_status_class`
- `content_type_class`
- `response_row_count`
- `usd_candidate_row_count`
- `provider_status_category`
- `effective_date_match`
- `response_sha256`
- `parser_version`
- `reason_code`

The raw provider response body and full request URL are not stored.

Eximbank not-found/error reasons are separated where possible:

- `provider_empty_response`
- `provider_status_error`
- `provider_schema_mismatch`
- `usd_row_missing`
- `rate_missing_or_invalid`
- `requested_date_missing`
- `date_mismatch`
- `provider_not_found`

When `provider_empty_response` occurs for an Eximbank AP01 same-date request, the sanitized report may add `operator_review_label=official_fx_unavailable_non_business_day`. This label means the requirement is a review-gated exception because the official same-date provider did not return a rate for that date. It is not a provenance resolution, and it must not trigger previous-business-day substitution, today-rate backfill, archive write, or REC-EX-01 closure.

Eximbank provider `result` status codes must be mapped only when the meaning is verified from official Korea Eximbank documentation. Unverified status codes, including operator-observed `result=3` until official meaning is confirmed, remain generic `provider_status_error` with the numeric status preserved only as `provider_status_category`.

Provider status errors are not the same as FX provenance absence. If canary returns a provider status error, keep private requirement preview and archive write blocked until the provider key/status issue is resolved and canary is rerun.

Safe operator checks for Eximbank provider status errors:

1. Confirm whether `KOREAEXIM_API_KEY` is the key issued for the Korea Eximbank Open API, not a generic public-data portal service key.
2. Confirm issuance, approval, activation, and quota status in the official provider portal.
3. Replace copied keys through SecretStore without printing the value:

```powershell
Set-Secret -Name KOREAEXIM_API_KEY
```

Enter the key only in the PowerShell prompt. Do not paste it into Codex, docs, logs, shell history, or report files.
4. Confirm the launcher uses `oapi.koreaexim.go.kr`.
5. Rerun the public canary before any private requirement preview.

## Aggregate Semantics

Validation decisions are requirement-level. These counts should add up by distinct requirement key:

- `candidate_resolved_count`
- `still_review_gated_count`
- `official_fx_unavailable_count`
- `invalid_requirement_count`
- `date_mismatch_count`
- `policy_blocked_count`
- `insufficient_evidence_count`

Provider failure counts are attempt-level during fetch preview:

- `provider_error_count`
- `provider_not_found_count`

For example, if BOK fails for one requirement and Eximbank then succeeds for the same requirement, the report can show both one provider failure attempt and one candidate-resolved requirement. This is expected. Do not interpret provider failure counts as unresolved requirement counts.

`official_fx_unavailable_count` is a supplemental requirement-level count inside the still-review-gated population. It is for known official same-date provider absence such as non-business-day or holiday-like empty Eximbank AP01 responses.

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

Operator-facing labels are explanatory only. For non-business-day or holiday-like empty Eximbank responses, use `official_fx_unavailable_non_business_day` as a review-gated exception label instead of treating the row as an unknown unresolved issue.

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

## Cache Promotion

`70_Imports/scripts/fx_cache_promoter.py` supports an operator-reviewed bridge
from validated archive candidates to a private `fx_rates.csv` cache. It is not
a provider fetcher and it is not a REC-EX-01 closure path.

Default behavior is preview/package generation only. The tool promotes only
validation rows with `candidate_resolved_by_archived_fx` and
`same_date_archived_fx_candidate`. Rows labeled `still_review_gated`,
`official_fx_unavailable_same_date`, provider failures, invalid requirements,
date mismatches, and insufficient evidence are excluded.

Actual private cache mutation requires `--apply` plus an explicit `--cache-path`.
The append step checks existing cache rows first. Equivalent existing rows are
skipped, but conflicting rows with the same date, currency, provider, and
use-case key stop the run before appending. The tool refuses output paths inside
the repository, live vault, synced folders, raw, processed, exports, or logs.
It also rechecks archive candidate provider, source type, status, response hash,
and redacted source URL before packaging.

Example private promotion preview:

```bash
python 70_Imports/scripts/fx_cache_promoter.py \
  --archive-candidates <private_fx_archive_candidates.csv> \
  --validation-report <private_fx_validation_result.csv> \
  --promotion-out <private_fx_rates_promotion_package.csv> \
  --manifest-out <private_fx_rates_promotion_manifest.json> \
  --expected-count <reviewed_candidate_count>
```

Example approved append-only cache update:

```bash
python 70_Imports/scripts/fx_cache_promoter.py \
  --archive-candidates <private_fx_archive_candidates.csv> \
  --validation-report <private_fx_validation_result.csv> \
  --cache-path <private_vault_cache_fx_rates.csv> \
  --apply \
  --expected-count <reviewed_candidate_count>
```

After cache promotion, run a live-vault dry-run before any actual live-vault
write. A reduced `fx_rate_requirements.csv` count is operational evidence only;
it does not close REC-EX-01 by itself.

## REC-EX-01 Review-Gated Exception State

After reviewed same-date Eximbank candidates are promoted into the private FX
cache, a live-vault dry-run and actual-write pass may reduce the requirement
queue while still leaving an official-FX-unavailable exception.

Interpret the post-promotion state this way:

- Promoted cache rows can support official KRW conversion only for their exact
  date, currency, and use-case keys.
- A remaining Eximbank empty same-date response for a non-business-day or
  holiday-like date is `official_fx_unavailable_non_business_day`.
- This state is not `resolved by provenance`; it remains a review-gated
  exception because no same-date official FX row exists.
- Do not substitute the previous business day, do not forward-fill, and do not
  apply today's rate.
- Do not close REC-EX-01 automatically. Keep REC-EX-01 Group A accepted as
  review-gated unless a separate human decision changes the QA closure state.

QA exception wording should preserve the same distinction. Generic `fx_missing`
rows mean same-date FX/KRW provenance is not accepted for official KRW totals.
When operator evidence shows official same-date FX is unavailable for a
non-business-day or holiday-like date, describe it as a review-gated exception,
not as an unknown unresolved issue and not as resolved provenance.

## Keep Review-Gated When

- No same-date official FX candidate exists.
- The official same-date provider returns an empty response for a non-business-day or holiday-like date.
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
