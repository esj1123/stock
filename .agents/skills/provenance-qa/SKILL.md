---
name: provenance-qa
description: Use when validating 06_Stock FX archive candidates against fx_rate_requirements for REC-EX-01 review support. Produces sanitized candidate/still-review-gated decisions only; never closes QA, never mutates raw or processed outputs, and never prints private broker values.
---

# Provenance QA

Use this skill to compare private FX archive candidates with private `fx_rate_requirements.csv`.

Hard limits:
- Do not read or modify raw broker files.
- Do not regenerate processed outputs.
- Do not write to the live vault.
- Do not print account, ticker, security name, raw filename, raw row, processed row value, amount, API key, or secret URL.
- Do not apply current/today FX to historical event dates.
- Do not use weekend or holiday previous-business-day substitution.
- Do not mark REC-EX-01 resolved.

Validation workflow:
1. Confirm the task is review support, not QA closure.
2. Use `70_Imports/scripts/fx_provenance_validator.py`.
3. Require exact `effective_date == event_date`.
4. Require `base_currency == requirement.currency` and `quote_currency == KRW`.
5. Require a positive numeric rate, allowlisted provider, usable source type, usable status, non-empty redacted `source_note`, and `response_sha256`.
6. Classify each requirement as `candidate_resolved_by_archived_fx`, `still_review_gated`, `invalid_requirement`, `provider_not_found`, `provider_error`, `policy_blocked`, `date_mismatch`, `rate_type_blocked`, or `insufficient_evidence`.
7. Report only aggregate counts and requirement-key-level decisions.

Decision rule:
- `candidate_resolved_by_archived_fx` means there is a review candidate, not official closure.
- Anything invalid, mismatched, missing, or policy-blocked stays review-gated.
