from __future__ import annotations

import urllib.error

import pytest

from fx_provenance_fetcher import (
    BOK_API_KEY_ENV,
    BOK_STAT_CODE_ENV,
    BOK_USD_ITEM_CODE_ENV,
    EXIMBANK_API_KEY_ENV,
    FX_ARCHIVE_COLUMNS,
    NETWORK_OPT_IN_ENV,
    BokFxProviderClient,
    FxProviderError,
    KoreaEximFxProviderClient,
    archive_candidate_from_response,
    build_parser,
    eximbank_request_url,
    http_get_text,
    main,
    merge_failure_counts,
    normalize_requirement_row,
    normalize_requirements,
    parse_bok_exchange_response,
    parse_eximbank_exchange_response,
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
    monkeypatch.delenv(NETWORK_OPT_IN_ENV, raising=False)

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


def test_fetch_and_report_only_are_mutually_exclusive():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--requirements-path", "placeholder.csv", "--fetch", "--report-only"])


def test_eximbank_request_uses_yyyymmdd_searchdate():
    url = eximbank_request_url("DUMMY_REDACTION_VALUE_12345", "2026-01-10")

    assert "searchdate=20260110" in url
    assert "data=AP01" in url


def test_write_archive_without_fetch_does_not_create_archive(tmp_path):
    requirements_path = tmp_path / "requirements.csv"
    archive_out = tmp_path / "archive.csv"
    requirements_path.write_text(
        "event_date,currency,use_case,row_count,amount_native_sum,missing_reason,source_file_type,status\n"
        "2026-01-10,USD,income_dividend,1,999999,same-date FX required,transaction_history,fx_missing\n",
        encoding="utf-8",
    )

    assert main(["--requirements-path", str(requirements_path), "--archive-out", str(archive_out), "--write-archive"]) == 0

    assert not archive_out.exists()


def test_canary_mode_does_not_write_archive(tmp_path):
    archive_out = tmp_path / "archive.csv"
    validation_out = tmp_path / "validation.csv"

    assert (
        main(
            [
                "--canary-date",
                "2026-01-10",
                "--archive-out",
                str(archive_out),
                "--validation-out",
                str(validation_out),
                "--write-archive",
            ]
        )
        == 0
    )

    assert not archive_out.exists()
    assert validation_out.exists()


def test_eximbank_valid_same_date_usd_response_builds_candidate():
    normalized = normalize_requirement_row(requirement(), index=1)
    response_text = '[{"cur_unit":"USD","deal_bas_r":"1,350.25","search_date":"2026-01-10"}]'

    candidate = parse_eximbank_exchange_response(
        requirement=normalized,
        response_text=response_text,
        request_date="2026-01-10",
    )

    assert candidate.provider == "eximbank"
    assert candidate.effective_date == "2026-01-10"
    assert candidate.base_currency == "USD"
    assert candidate.quote_currency == "KRW"
    assert candidate.rate == "1350.25"
    assert candidate.source_type == "api_archive"
    assert candidate.status == "available"
    assert candidate.response_sha256 == sha256_text(response_text)
    assert "authkey=<redacted>" in candidate.source_url_template


def test_eximbank_empty_response_is_provider_not_found():
    normalized = normalize_requirement_row(requirement(), index=1)

    with pytest.raises(FxProviderError) as error:
        parse_eximbank_exchange_response(requirement=normalized, response_text="[]", request_date="2026-01-10")

    assert error.value.category == "provider_not_found"
    assert error.value.reason_code == "provider_empty_response"
    assert error.value.diagnostics["response_row_count"] == "0"


def test_eximbank_response_date_mismatch_is_date_mismatch():
    normalized = normalize_requirement_row(requirement(), index=1)
    response_text = '[{"cur_unit":"USD","deal_bas_r":"1,350.25","search_date":"2026-01-09"}]'

    with pytest.raises(FxProviderError) as error:
        parse_eximbank_exchange_response(
            requirement=normalized,
            response_text=response_text,
            request_date="2026-01-10",
        )

    assert error.value.category == "date_mismatch"
    assert error.value.reason_code == "date_mismatch"
    assert error.value.diagnostics["effective_date_match"] == "false"


def test_eximbank_malformed_response_is_provider_error():
    normalized = normalize_requirement_row(requirement(), index=1)

    with pytest.raises(FxProviderError) as error:
        parse_eximbank_exchange_response(requirement=normalized, response_text='{"unexpected": true}', request_date="2026-01-10")

    assert error.value.category == "provider_error"
    assert error.value.reason_code == "provider_schema_mismatch"


def test_eximbank_provider_status_error_is_separated():
    normalized = normalize_requirement_row(requirement(), index=1)

    with pytest.raises(FxProviderError) as error:
        parse_eximbank_exchange_response(
            requirement=normalized,
            response_text='[{"result":"4"}]',
            request_date="2026-01-10",
        )

    assert error.value.category == "provider_error"
    assert error.value.reason_code == "provider_status_error"
    assert error.value.diagnostics["provider_status_category"] == "4"


def test_eximbank_result_3_stays_generic_when_official_mapping_unverified():
    normalized = normalize_requirement_row(requirement(), index=1)

    with pytest.raises(FxProviderError) as error:
        parse_eximbank_exchange_response(
            requirement=normalized,
            response_text='[{"result":"3"}]',
            request_date="2026-01-10",
        )

    assert error.value.category == "provider_error"
    assert error.value.reason_code == "provider_status_error"
    assert error.value.safe_message == "Eximbank returned an unverified provider status"
    assert error.value.diagnostics["provider_status_category"] == "3"


def test_eximbank_numeric_status_code_is_normalized_like_string_code():
    normalized = normalize_requirement_row(requirement(), index=1)

    with pytest.raises(FxProviderError) as error:
        parse_eximbank_exchange_response(
            requirement=normalized,
            response_text='[{"result":3}]',
            request_date="2026-01-10",
        )

    assert error.value.reason_code == "provider_status_error"
    assert error.value.diagnostics["provider_status_category"] == "3"


def test_eximbank_valid_rows_without_usd_are_usd_row_missing():
    normalized = normalize_requirement_row(requirement(), index=1)

    with pytest.raises(FxProviderError) as error:
        parse_eximbank_exchange_response(
            requirement=normalized,
            response_text='[{"cur_unit":"EUR","deal_bas_r":"1,500.25","search_date":"2026-01-10"}]',
            request_date="2026-01-10",
        )

    assert error.value.category == "provider_not_found"
    assert error.value.reason_code == "usd_row_missing"
    assert error.value.diagnostics["usd_candidate_row_count"] == "0"


def test_eximbank_usd_without_valid_rate_is_rate_missing_or_invalid():
    normalized = normalize_requirement_row(requirement(), index=1)

    with pytest.raises(FxProviderError) as error:
        parse_eximbank_exchange_response(
            requirement=normalized,
            response_text='[{"cur_unit":"USD","deal_bas_r":"","search_date":"2026-01-10"}]',
            request_date="2026-01-10",
        )

    assert error.value.category == "provider_error"
    assert error.value.reason_code == "rate_missing_or_invalid"


def test_eximbank_usd_without_date_is_requested_date_missing():
    normalized = normalize_requirement_row(requirement(), index=1)

    with pytest.raises(FxProviderError) as error:
        parse_eximbank_exchange_response(
            requirement=normalized,
            response_text='[{"cur_unit":"USD","deal_bas_r":"1,350.25"}]',
            request_date="2026-01-10",
        )

    assert error.value.category == "provider_not_found"
    assert error.value.reason_code == "requested_date_missing"
    assert error.value.diagnostics["effective_date_match"] == "unknown"


def test_http_error_is_sanitized_provider_error(monkeypatch):
    secret = "DUMMY_REDACTION_VALUE_12345"

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            url=f"https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?authkey={secret}",
            code=500,
            msg="server error",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setenv(EXIMBANK_API_KEY_ENV, secret)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(FxProviderError) as error:
        http_get_text(f"https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?authkey={secret}")

    assert error.value.category == "provider_error"
    assert secret not in str(error.value)
    assert "authkey=" not in str(error.value)


def test_timeout_error_is_sanitized_provider_error(monkeypatch):
    secret = "DUMMY_REDACTION_VALUE_12345"

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError(TimeoutError("timed out while using secret"))

    monkeypatch.setenv(EXIMBANK_API_KEY_ENV, secret)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(FxProviderError) as error:
        http_get_text(f"https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?authkey={secret}")

    assert error.value.category == "provider_error"
    assert secret not in str(error.value)
    assert "authkey=" not in str(error.value)


def test_eximbank_client_redacts_api_key_from_candidate(monkeypatch):
    secret = "DUMMY_REDACTION_VALUE_12345"
    captured_urls = []

    def fake_http_get(url, timeout):
        captured_urls.append(url)
        return '[{"cur_unit":"USD","deal_bas_r":"1,350.25","search_date":"2026-01-10"}]'

    monkeypatch.setenv(NETWORK_OPT_IN_ENV, "1")
    monkeypatch.setenv(EXIMBANK_API_KEY_ENV, secret)
    candidate = KoreaEximFxProviderClient(http_get=fake_http_get).fetch_rate(
        date="2026-01-10",
        base_currency="USD",
        quote_currency="KRW",
        use_case="income_dividend",
    )

    assert secret in captured_urls[0]
    serialized = str(candidate.to_archive_row(include_extra=True))
    assert secret not in serialized
    assert "authkey=<redacted>" in candidate.source_url_template


def test_eximbank_client_trims_api_key_before_urlencoding(monkeypatch):
    secret = "DUMMY REDACTION VALUE"
    captured_urls = []

    def fake_http_get(url, timeout):
        captured_urls.append(url)
        return '[{"cur_unit":"USD","deal_bas_r":"1,350.25","search_date":"2026-01-10"}]'

    monkeypatch.setenv(NETWORK_OPT_IN_ENV, "1")
    monkeypatch.setenv(EXIMBANK_API_KEY_ENV, f"  {secret}\n")
    candidate = KoreaEximFxProviderClient(http_get=fake_http_get).fetch_rate(
        date="2026-01-10",
        base_currency="USD",
        quote_currency="KRW",
        use_case="income_dividend",
    )

    assert "authkey=DUMMY+REDACTION+VALUE" in captured_urls[0]
    assert "  " not in captured_urls[0]
    assert "\n" not in captured_urls[0]
    assert secret not in str(candidate.to_archive_row(include_extra=True))
    assert "authkey=<redacted>" in candidate.source_url_template


def test_eximbank_client_rejects_whitespace_only_api_key(monkeypatch):
    def fake_http_get(url, timeout):
        raise AssertionError("network should not be called with a blank key")

    monkeypatch.setenv(NETWORK_OPT_IN_ENV, "1")
    monkeypatch.setenv(EXIMBANK_API_KEY_ENV, " \n\t ")

    with pytest.raises(FxProviderError) as error:
        KoreaEximFxProviderClient(http_get=fake_http_get).fetch_rate(
            date="2026-01-10",
            base_currency="USD",
            quote_currency="KRW",
            use_case="income_dividend",
        )

    assert error.value.category == "provider_error"
    assert error.value.safe_message == "Korea Eximbank API key is missing"


def test_provider_failure_report_excludes_key_url_and_body(tmp_path):
    normalized = normalize_requirement_row(requirement(), index=1)
    response_text = '[{"cur_unit":"USD","deal_bas_r":"","search_date":"2026-01-10"}]'

    with pytest.raises(FxProviderError) as error:
        parse_eximbank_exchange_response(
            requirement=normalized,
            response_text=response_text,
            request_date="2026-01-10",
        )

    record = provider_error_record(normalized, "eximbank", error.value)
    serialized = str(record)

    assert record["reason_code"] == "rate_missing_or_invalid"
    assert record["response_sha256"] == sha256_text(response_text)
    assert response_text not in serialized
    assert "authkey=" not in serialized
    assert "DUMMY_REDACTION_VALUE_12345" not in serialized


def test_bok_valid_mocked_response_builds_candidate(monkeypatch):
    normalized = normalize_requirement_row(requirement(), index=1)
    response_text = '{"StatisticSearch":{"row":[{"TIME":"20260110","ITEM_CODE1":"USD","DATA_VALUE":"1350.25"}]}}'

    candidate = parse_bok_exchange_response(
        requirement=normalized,
        response_text=response_text,
        request_date="2026-01-10",
        stat_code="TEST_STAT",
        item_code="USD",
    )

    assert candidate.provider == "bok"
    assert candidate.effective_date == "2026-01-10"
    assert candidate.rate == "1350.25"
    assert candidate.source_type == "api_archive"
    assert candidate.response_sha256 == sha256_text(response_text)


def test_bok_malformed_response_is_provider_error():
    normalized = normalize_requirement_row(requirement(), index=1)

    with pytest.raises(FxProviderError) as error:
        parse_bok_exchange_response(
            requirement=normalized,
            response_text='{"StatisticSearch":{"row":{"TIME":"20260110"}}}',
            request_date="2026-01-10",
            stat_code="TEST_STAT",
            item_code="USD",
        )

    assert error.value.category == "provider_error"


def test_bok_series_configuration_missing_is_policy_blocked(monkeypatch):
    monkeypatch.setenv(NETWORK_OPT_IN_ENV, "1")
    monkeypatch.setenv(BOK_API_KEY_ENV, "DUMMY_REDACTION_VALUE_12345")
    monkeypatch.delenv(BOK_STAT_CODE_ENV, raising=False)
    monkeypatch.delenv(BOK_USD_ITEM_CODE_ENV, raising=False)

    with pytest.raises(FxProviderError) as error:
        BokFxProviderClient(http_get=lambda url, timeout: "{}").fetch_rate(
            date="2026-01-10",
            base_currency="USD",
            quote_currency="KRW",
            use_case="income_dividend",
        )

    assert error.value.category == "policy_blocked"
