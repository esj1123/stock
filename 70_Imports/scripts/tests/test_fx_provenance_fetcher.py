from __future__ import annotations

import pytest

from fx_provenance_fetcher import (
    BOK_API_KEY_ENV,
    FX_ARCHIVE_COLUMNS,
    BokFxProviderClient,
    FxProviderError,
    archive_candidate_from_response,
    merge_failure_counts,
    normalize_requirement_row,
    normalize_requirements,
    provider_error_record,
    redact_secrets,
    sha256_text,
)
from portfolio_model import FX_RATES_COLUMNS


def requirement(**overrides):
    row = {
        "event_date": "2026-01-10",
        "currency": "USD",
        "use_case": "income_dividend",
        "row_count": "2",
        "amount_native_sum": "999999",
        "missing_reason": "same-date FX required",
        "source_file_type": "transaction_history",
        "status": "fx_missing",
    }
    row.update(overrides)
    return row


def test_normalize_requirement_builds_safe_key_without_amount():
    normalized = normalize_requirement_row(requirement(), index=1)

    assert normalized.requirement_key == "2026-01-10|USD|income_dividend"
    assert normalized.event_date == "2026-01-10"
    assert normalized.base_currency == "USD"
    assert normalized.quote_currency == "KRW"
    assert normalized.fetch_target
    assert "999999" not in normalized.requirement_key


def test_krw_requirement_is_not_fetch_target():
    normalized = normalize_requirement_row(requirement(currency="KRW"), index=1)

    assert not normalized.fetch_target
    assert normalized.invalid_reason == "not_required"


def test_numeric_currency_is_invalid_currency_contract():
    normalized = normalize_requirement_row(requirement(currency="1473.10"), index=1)

    assert not normalized.fetch_target
    assert normalized.invalid_reason == "invalid_currency_fx_rate_value"
    assert "1473.10" not in normalized.requirement_key


def test_duplicate_requirement_keys_are_deduped():
    normalized = normalize_requirements([requirement(row_count="1"), requirement(row_count="99")])

    assert len(normalized) == 1
    assert normalized[0].requirement_key == "2026-01-10|USD|income_dividend"


def test_archive_candidate_export_includes_pipeline_fx_rates_columns():
    normalized = normalize_requirement_row(requirement(), index=1)
    candidate = archive_candidate_from_response(
        requirement=normalized,
        rate="1350.25",
        provider="bok",
        source_type="api_cached",
        status="cached",
        source_note="official same-date archived FX evidence",
        response_text="synthetic provider response",
        source_url_template="https://official.example/fx?api_key=<redacted>",
    )
    row = candidate.to_archive_row(include_extra=True)

    assert all(column in row for column in FX_RATES_COLUMNS)
    assert all(column in row for column in FX_ARCHIVE_COLUMNS)
    assert row["response_sha256"] == sha256_text("synthetic provider response")
    assert "api_key=<redacted>" in row["source_url_template"]


def test_provider_network_disabled_is_policy_blocked(monkeypatch):
    monkeypatch.delenv("FX_PROVENANCE_ENABLE_NETWORK", raising=False)

    with pytest.raises(FxProviderError) as error:
        BokFxProviderClient().fetch_rate(
            date="2026-01-10",
            base_currency="USD",
            quote_currency="KRW",
            use_case="income_dividend",
        )

    assert error.value.category == "policy_blocked"


def test_provider_error_does_not_print_api_secret(monkeypatch):
    monkeypatch.setenv(BOK_API_KEY_ENV, "DUMMY_REDACTION_VALUE_12345")
    sanitized = redact_secrets("provider failed with DUMMY_REDACTION_VALUE_12345")
    normalized = normalize_requirement_row(requirement(), index=1)
    record = provider_error_record(normalized, "bok", FxProviderError("provider_error", sanitized))

    serialized = str(record)
    assert "DUMMY_REDACTION_VALUE_12345" not in sanitized
    assert "DUMMY_REDACTION_VALUE_12345" not in serialized
    assert record["decision"] == "provider_error"
    assert record["requirement_key"] == "2026-01-10|USD|income_dividend"


def test_provider_failures_are_counted_in_aggregate_report():
    base_report = {
        "requirements_total": 1,
        "distinct_requirement_keys": 1,
        "candidate_resolved_count": 0,
        "still_review_gated_count": 1,
        "invalid_requirement_count": 0,
        "provider_error_count": 0,
        "provider_not_found_count": 0,
        "policy_blocked_count": 0,
        "date_mismatch_count": 0,
        "rate_type_blocked_count": 0,
        "insufficient_evidence_count": 0,
    }
    merged = merge_failure_counts(base_report, [{"decision": "provider_error"}, {"decision": "policy_blocked"}])

    assert merged["provider_error_count"] == 1
    assert merged["policy_blocked_count"] == 1
    assert base_report["provider_error_count"] == 0
