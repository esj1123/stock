from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from fx_cache_promoter import FxCachePromotionError, build_parser, main, run
from portfolio_model import FX_RATES_COLUMNS


def write_rows(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def archive_row(**overrides):
    row = {
        "effective_date": "2026-01-10",
        "base_currency": "USD",
        "quote_currency": "KRW",
        "rate": "1350.25",
        "source_type": "api_archive",
        "provider": "eximbank",
        "use_case": "income_dividend",
        "status": "available",
        "source_note": "official same-date request-date-backed FX candidate",
        "response_sha256": "a" * 64,
        "source_url_template": "https://oapi.koreaexim.go.kr/path?authkey=<redacted>",
    }
    row.update(overrides)
    return row


def validation_row(**overrides):
    row = {
        "requirement_key": "2026-01-10|USD|income_dividend",
        "decision": "candidate_resolved_by_archived_fx",
        "reason_code": "same_date_archived_fx_candidate",
        "operator_review_label": "candidate_archive_review",
        "provider": "eximbank",
        "use_case": "income_dividend",
        "parser_version": "test",
        "rule_version": "test",
    }
    row.update(overrides)
    return row


def fixture_paths(tmp_path):
    archive_path = tmp_path / "archive_candidates.csv"
    validation_path = tmp_path / "validation_report.csv"
    archive_rows = [
        archive_row(effective_date="2026-01-10", rate="1350.25"),
        archive_row(effective_date="2026-01-11", rate="1351.25"),
    ]
    validation_rows = [
        validation_row(requirement_key="2026-01-10|USD|income_dividend"),
        validation_row(requirement_key="2026-01-11|USD|income_dividend"),
        validation_row(
            requirement_key="2026-01-12|USD|income_dividend",
            decision="still_review_gated",
            reason_code="official_fx_unavailable_same_date",
            operator_review_label="official_fx_unavailable_non_business_day",
        ),
    ]
    write_rows(archive_path, archive_rows, list(archive_rows[0]))
    write_rows(validation_path, validation_rows, list(validation_rows[0]))
    return archive_path, validation_path


def test_promoter_writes_only_candidate_rows_to_package(tmp_path):
    archive_path, validation_path = fixture_paths(tmp_path)
    promotion_out = tmp_path / "promotion_package.csv"
    manifest_out = tmp_path / "promotion_manifest.json"

    assert (
        main(
            [
                "--archive-candidates",
                str(archive_path),
                "--validation-report",
                str(validation_path),
                "--promotion-out",
                str(promotion_out),
                "--manifest-out",
                str(manifest_out),
                "--expected-count",
                "2",
            ]
        )
        == 0
    )

    rows = read_rows(promotion_out)
    serialized = promotion_out.read_text(encoding="utf-8-sig")
    manifest = json.loads(manifest_out.read_text(encoding="utf-8"))

    assert len(rows) == 2
    assert list(rows[0]) == FX_RATES_COLUMNS
    assert {row["effective_date"] for row in rows} == {"2026-01-10", "2026-01-11"}
    assert "official_fx_unavailable_non_business_day" not in serialized
    assert "authkey=" not in serialized
    assert manifest["promotion_rows"] == 2
    assert manifest["excluded_validation_rows"] == 1
    assert manifest["cache_write_requested"] is False
    assert manifest["rec_ex_01_status_changed"] is False


def test_promoter_does_not_touch_cache_without_apply(tmp_path):
    archive_path, validation_path = fixture_paths(tmp_path)
    cache_path = tmp_path / "cache" / "fx_rates.csv"

    assert (
        main(
            [
                "--archive-candidates",
                str(archive_path),
                "--validation-report",
                str(validation_path),
                "--cache-path",
                str(cache_path),
                "--expected-count",
                "2",
            ]
        )
        == 0
    )

    assert not cache_path.exists()


def test_promoter_apply_appends_once_and_is_idempotent(tmp_path):
    archive_path, validation_path = fixture_paths(tmp_path)
    cache_path = tmp_path / "cache" / "fx_rates.csv"
    parser = build_parser()

    first = run(
        parser.parse_args(
            [
                "--archive-candidates",
                str(archive_path),
                "--validation-report",
                str(validation_path),
                "--cache-path",
                str(cache_path),
                "--apply",
                "--expected-count",
                "2",
            ]
        )
    )
    second = run(
        parser.parse_args(
            [
                "--archive-candidates",
                str(archive_path),
                "--validation-report",
                str(validation_path),
                "--cache-path",
                str(cache_path),
                "--apply",
                "--expected-count",
                "2",
            ]
        )
    )

    assert first["cache_rows_appended"] == 2
    assert second["cache_rows_appended"] == 0
    assert second["cache_rows_skipped_existing"] == 2
    assert len(read_rows(cache_path)) == 2


def test_promoter_conflict_stops_before_append(tmp_path):
    archive_path, validation_path = fixture_paths(tmp_path)
    cache_path = tmp_path / "cache" / "fx_rates.csv"
    conflicting = archive_row(rate="9999.99")
    write_rows(cache_path, [conflicting], FX_RATES_COLUMNS)
    parser = build_parser()

    with pytest.raises(FxCachePromotionError):
        run(
            parser.parse_args(
                [
                    "--archive-candidates",
                    str(archive_path),
                    "--validation-report",
                    str(validation_path),
                    "--cache-path",
                    str(cache_path),
                    "--apply",
                    "--expected-count",
                    "2",
                ]
            )
        )

    rows = read_rows(cache_path)
    assert len(rows) == 1
    assert rows[0]["rate"] == "9999.99"


def test_promoter_expected_count_mismatch_blocks_output(tmp_path):
    archive_path, validation_path = fixture_paths(tmp_path)
    promotion_out = tmp_path / "promotion_package.csv"

    with pytest.raises(SystemExit) as error:
        main(
            [
                "--archive-candidates",
                str(archive_path),
                "--validation-report",
                str(validation_path),
                "--promotion-out",
                str(promotion_out),
                "--expected-count",
                "3",
            ]
        )

    assert error.value.code == 2
    assert not promotion_out.exists()


def test_promoter_rejects_repo_output_paths(tmp_path):
    archive_path, validation_path = fixture_paths(tmp_path)
    repo_root = Path(__file__).resolve().parents[3]
    blocked_output = repo_root / "_tmp_fx_rates_promotion_package.csv"

    with pytest.raises(SystemExit) as error:
        main(
            [
                "--archive-candidates",
                str(archive_path),
                "--validation-report",
                str(validation_path),
                "--promotion-out",
                str(blocked_output),
                "--expected-count",
                "2",
            ]
        )

    assert error.value.code == 2
    assert not blocked_output.exists()


def test_promoter_rejects_live_vault_and_synced_output_paths(tmp_path, monkeypatch):
    archive_path, validation_path = fixture_paths(tmp_path)
    fake_live_root = tmp_path / "live_vault"
    fake_synced_root = tmp_path / "Google Drive"
    monkeypatch.setenv("STOCK_LIVE_VAULT_ROOT", str(fake_live_root))

    for blocked_output in [
        fake_live_root / "fx_rates_promotion_package.csv",
        fake_synced_root / "fx_rates_promotion_package.csv",
    ]:
        with pytest.raises(SystemExit) as error:
            main(
                [
                    "--archive-candidates",
                    str(archive_path),
                    "--validation-report",
                    str(validation_path),
                    "--promotion-out",
                    str(blocked_output),
                    "--expected-count",
                    "2",
                ]
            )

        assert error.value.code == 2
        assert not blocked_output.exists()


def test_promoter_existing_cache_ignores_unrelated_malformed_rows(tmp_path):
    archive_path, validation_path = fixture_paths(tmp_path)
    cache_path = tmp_path / "cache" / "fx_rates.csv"
    malformed_unrelated = archive_row(effective_date="2026-02-01", rate="not-a-rate", source_note="")
    write_rows(cache_path, [malformed_unrelated], FX_RATES_COLUMNS)
    parser = build_parser()

    manifest = run(
        parser.parse_args(
            [
                "--archive-candidates",
                str(archive_path),
                "--validation-report",
                str(validation_path),
                "--cache-path",
                str(cache_path),
                "--apply",
                "--expected-count",
                "2",
            ]
        )
    )

    assert manifest["cache_rows_appended"] == 2
    assert len(read_rows(cache_path)) == 3


def test_promoter_accepts_validator_use_case_alias(tmp_path):
    archive_path = tmp_path / "archive_candidates.csv"
    validation_path = tmp_path / "validation_report.csv"
    archive_rows = [archive_row(use_case="income")]
    validation_rows = [validation_row(requirement_key="2026-01-10|USD|income_dividend")]
    write_rows(archive_path, archive_rows, list(archive_rows[0]))
    write_rows(validation_path, validation_rows, list(validation_rows[0]))
    promotion_out = tmp_path / "promotion_package.csv"

    assert (
        main(
            [
                "--archive-candidates",
                str(archive_path),
                "--validation-report",
                str(validation_path),
                "--promotion-out",
                str(promotion_out),
                "--expected-count",
                "1",
            ]
        )
        == 0
    )

    rows = read_rows(promotion_out)
    assert len(rows) == 1
    assert rows[0]["use_case"] == "income"


def test_promoter_revalidates_archive_candidate_evidence(tmp_path):
    archive_path = tmp_path / "archive_candidates.csv"
    validation_path = tmp_path / "validation_report.csv"
    archive_rows = [archive_row(response_sha256="")]
    validation_rows = [validation_row()]
    write_rows(archive_path, archive_rows, list(archive_rows[0]))
    write_rows(validation_path, validation_rows, list(validation_rows[0]))
    promotion_out = tmp_path / "promotion_package.csv"

    with pytest.raises(SystemExit) as error:
        main(
            [
                "--archive-candidates",
                str(archive_path),
                "--validation-report",
                str(validation_path),
                "--promotion-out",
                str(promotion_out),
                "--expected-count",
                "1",
            ]
        )

    assert error.value.code == 2
    assert not promotion_out.exists()
