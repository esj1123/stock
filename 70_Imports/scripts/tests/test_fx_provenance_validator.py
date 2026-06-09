from __future__ import annotations

import json
from datetime import date

from fx_provenance_fetcher import normalize_requirement_row, sha256_text
from fx_provenance_validator import (
    archive_export_columns_are_compatible,
    build_validation_report,
    use_case_matches,
    validate_requirements_against_archive,
    validation_result_rows,
)
from fx_provenance_fetcher import FX_ARCHIVE_COLUMNS


def requirement(**overrides):
    row = {
        "event_date": "2026-01-10",
        "currency": "USD",
        "use_case": "income_dividend",
        "row_count": "1",
        "amount_native_sum": "888888",
        "missing_reason": "same-date FX required",
        "source_file_type": "transaction_history",
        "status": "fx_missing",
    }
    row.update(overrides)
    return normalize_requirement_row(row, index=1)


def archive_row(**overrides):
    row = {
        "effective_date": "2026-01-10",
        "base_currency": "USD",
        "quote_currency": "KRW",
        "rate": "1350.25",
        "source_type": "api_cached",
        "provider": "bok",
        "use_case": "income_dividend",
        "status": "cached",
        "source_note": "official same-date archived FX evidence",
        "archive_id": "archive-1",
        "fetched_at_utc": "2026-01-11T00:00:00Z",
        "request_date": "2026-01-10",
        "rate_type_class": "official_reference",
        "unit_factor": "1",
        "derivation_method": "direct_provider_rate",
        "provider_series_key": "USD/KRW",
        "provider_timestamp": "2026-01-10T12:00:00Z",
        "response_sha256": sha256_text("synthetic official response"),
        "source_url_template": "https://official.example/fx?api_key=<redacted>",
        "parser_version": "test_parser_v1",
        "rule_version": "test_rule_v1",
        "supersedes_archive_id": "",
    }
    row.update(overrides)
    return row


def only_decision(req, row):
    return validate_requirements_against_archive([req], [row])[0]


def test_same_date_usd_krw_archived_fx_candidate_resolves():
    result = only_decision(requirement(), archive_row())

    assert result.decision == "candidate_resolved_by_archived_fx"
    assert result.reason_code == "same_date_archived_fx_candidate"


def test_effective_date_mismatch_is_blocked():
    result = only_decision(requirement(), archive_row(effective_date="2026-01-09"))

    assert result.decision == "date_mismatch"
    assert result.reason_code == "effective_date_mismatch"


def test_previous_business_day_substitution_does_not_auto_pass():
    result = only_decision(requirement(event_date="2026-01-12"), archive_row(effective_date="2026-01-09"))

    assert result.decision == "date_mismatch"


def test_today_rate_backfill_to_historical_event_is_blocked():
    result = only_decision(requirement(event_date="2020-01-10"), archive_row(effective_date=date.today().isoformat()))

    assert result.decision == "date_mismatch"
    assert result.reason_code == "today_rate_backfill_blocked"


def test_missing_source_note_or_response_hash_is_insufficient_evidence():
    missing_note = only_decision(requirement(), archive_row(source_note=""))
    missing_hash = only_decision(requirement(), archive_row(response_sha256=""))

    assert missing_note.decision == "insufficient_evidence"
    assert missing_note.reason_code == "source_note_missing"
    assert missing_hash.decision == "insufficient_evidence"
    assert missing_hash.reason_code == "response_hash_missing"


def test_quote_currency_must_be_krw():
    result = only_decision(requirement(), archive_row(quote_currency="USD"))

    assert result.decision == "policy_blocked"
    assert result.reason_code == "quote_currency_not_krw"


def test_zero_or_negative_rate_is_blocked():
    zero = only_decision(requirement(), archive_row(rate="0"))
    negative = only_decision(requirement(), archive_row(rate="-1"))

    assert zero.decision == "policy_blocked"
    assert zero.reason_code == "invalid_rate"
    assert negative.decision == "policy_blocked"
    assert negative.reason_code == "invalid_rate"


def test_use_case_aliases_are_limited_to_expected_scopes():
    assert use_case_matches("income_dividend", "income")
    assert use_case_matches("income_dividend", "income_dividend")
    assert use_case_matches("expense_tax", "expense")
    assert use_case_matches("expense_tax", "expense_tax")
    assert use_case_matches("income_dividend", "all")
    assert use_case_matches("income_dividend", "*")
    assert not use_case_matches("income_dividend", "expense_tax")


def test_use_case_mismatch_stays_review_gated():
    result = only_decision(requirement(), archive_row(use_case="expense_tax"))

    assert result.decision == "still_review_gated"
    assert result.reason_code == "use_case_mismatch"


def test_invalid_currency_requirement_is_invalid_requirement():
    result = validate_requirements_against_archive([requirement(currency="1473.10")], [archive_row()])[0]

    assert result.decision == "invalid_requirement"
    assert result.reason_code == "invalid_currency_fx_rate_value"
    assert "1473.10" not in result.requirement_key


def test_report_excludes_private_amount_ticker_account_and_raw_filename_candidates():
    results = validate_requirements_against_archive([requirement()], [archive_row()])
    report = build_validation_report(results)
    rows = validation_result_rows(results)
    serialized = json.dumps({"report": report, "rows": rows}, sort_keys=True)

    assert "888888" not in serialized
    assert "account" not in serialized.lower()
    assert "ticker" not in serialized.lower()
    assert ".xlsx" not in serialized
    assert report["candidate_resolved_count"] == 1
    assert report["still_review_gated_count"] == 0


def test_archive_export_has_pipeline_compatible_fx_rates_columns():
    assert archive_export_columns_are_compatible(FX_ARCHIVE_COLUMNS)
