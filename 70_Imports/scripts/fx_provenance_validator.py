from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from fx_provenance_fetcher import (
    DEFAULT_PARSER_VERSION,
    DEFAULT_QUOTE_CURRENCY,
    DEFAULT_RULE_VERSION,
    FX_ARCHIVE_COLUMNS,
    FxArchiveCandidate,
    NormalizedFxRequirement,
    normalize_date_text,
    normalize_requirements,
    normalize_use_case,
    read_csv_rows,
    redact_secrets,
    text_value,
)
from portfolio_model import API_CACHED_FX_SOURCE_TYPES, LOCAL_FX_SOURCE_TYPES, USABLE_FX_RATE_STATUSES


VALIDATION_DECISIONS = {
    "candidate_resolved_by_archived_fx",
    "still_review_gated",
    "invalid_requirement",
    "provider_not_found",
    "provider_error",
    "policy_blocked",
    "date_mismatch",
    "rate_type_blocked",
    "insufficient_evidence",
}

ALLOWED_SOURCE_TYPES = LOCAL_FX_SOURCE_TYPES | API_CACHED_FX_SOURCE_TYPES
ALLOWED_PROVIDERS = {
    "bok",
    "bank_of_korea",
    "eximbank",
    "koreaexim",
    "korea_eximbank",
    "synthetic_official",
}


@dataclass(frozen=True)
class FxValidationResult:
    requirement_key: str
    decision: str
    reason_code: str
    provider: str = ""
    use_case: str = ""
    parser_version: str = DEFAULT_PARSER_VERSION
    rule_version: str = DEFAULT_RULE_VERSION


def numeric_rate(value: Any) -> float | None:
    text = text_value(value).replace(",", "")
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed


def use_case_aliases(use_case: str) -> set[str]:
    key = normalize_use_case(use_case)
    aliases = {"", "*", "all", key}
    if key.startswith("income_"):
        aliases.update({"income", key.removeprefix("income_")})
    if key.startswith("expense_"):
        aliases.update({"expense", key.removeprefix("expense_")})
    if key.startswith("realized_"):
        aliases.update({"realized_pnl", "trade_settlement", "transaction"})
    return aliases


def use_case_matches(requirement_use_case: str, archive_use_case: str) -> bool:
    return normalize_use_case(archive_use_case) in use_case_aliases(requirement_use_case)


def valid_response_hash(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", text_value(value)))


def source_note_has_secret(value: str) -> bool:
    text = text_value(value)
    if not text:
        return False
    return redact_secrets(text) != text or bool(re.search(r"(?i)(api[_-]?key|token|password|secret)=", text))


def url_template_has_secret(value: str) -> bool:
    text = text_value(value)
    if not text:
        return False
    return redact_secrets(text) != text


def archive_candidate_from_row(row: dict[str, Any]) -> FxArchiveCandidate:
    return FxArchiveCandidate(
        effective_date=normalize_date_text(row.get("effective_date", "")),
        base_currency=text_value(row.get("base_currency", "")).upper(),
        quote_currency=text_value(row.get("quote_currency", "")).upper(),
        rate=text_value(row.get("rate", "")),
        source_type=text_value(row.get("source_type", "")).lower(),
        provider=text_value(row.get("provider", "")).lower(),
        use_case=normalize_use_case(row.get("use_case", "")),
        status=text_value(row.get("status", "")).lower(),
        source_note=redact_secrets(text_value(row.get("source_note", ""))),
        archive_id=text_value(row.get("archive_id", "")),
        fetched_at_utc=text_value(row.get("fetched_at_utc", "")),
        request_date=normalize_date_text(row.get("request_date", "")),
        rate_type_class=text_value(row.get("rate_type_class", "")) or "official_reference",
        unit_factor=text_value(row.get("unit_factor", "")) or "1",
        derivation_method=text_value(row.get("derivation_method", "")) or "direct_provider_rate",
        provider_series_key=text_value(row.get("provider_series_key", "")),
        provider_timestamp=text_value(row.get("provider_timestamp", "")),
        response_sha256=text_value(row.get("response_sha256", "")),
        source_url_template=redact_secrets(text_value(row.get("source_url_template", ""))),
        parser_version=text_value(row.get("parser_version", "")) or DEFAULT_PARSER_VERSION,
        rule_version=text_value(row.get("rule_version", "")) or DEFAULT_RULE_VERSION,
        supersedes_archive_id=text_value(row.get("supersedes_archive_id", "")),
    )


def result(
    requirement: NormalizedFxRequirement,
    decision: str,
    reason_code: str,
    candidate: FxArchiveCandidate | None = None,
) -> FxValidationResult:
    if decision not in VALIDATION_DECISIONS:
        raise ValueError(f"unknown validation decision: {decision}")
    return FxValidationResult(
        requirement_key=requirement.requirement_key,
        decision=decision,
        reason_code=reason_code,
        provider=candidate.provider if candidate else "",
        use_case=requirement.use_case,
        parser_version=candidate.parser_version if candidate else DEFAULT_PARSER_VERSION,
        rule_version=candidate.rule_version if candidate else DEFAULT_RULE_VERSION,
    )


def validate_requirement_candidate(
    requirement: NormalizedFxRequirement,
    candidate: FxArchiveCandidate | None,
) -> FxValidationResult:
    if requirement.invalid_reason and requirement.invalid_reason != "not_required":
        return result(requirement, "invalid_requirement", requirement.invalid_reason, candidate)
    if requirement.invalid_reason == "not_required":
        return result(requirement, "still_review_gated", "krw_requirement_not_fetch_target", candidate)
    if candidate is None:
        return result(requirement, "still_review_gated", "no_archive_candidate")

    effective_date = normalize_date_text(candidate.effective_date)
    if effective_date != requirement.event_date:
        try:
            parsed_effective = date.fromisoformat(effective_date)
            parsed_event = date.fromisoformat(requirement.event_date)
        except ValueError:
            return result(requirement, "date_mismatch", "effective_date_mismatch", candidate)
        if parsed_effective == date.today() and parsed_event < parsed_effective:
            return result(requirement, "date_mismatch", "today_rate_backfill_blocked", candidate)
        return result(requirement, "date_mismatch", "effective_date_mismatch", candidate)

    if candidate.base_currency.upper() != requirement.base_currency:
        return result(requirement, "still_review_gated", "base_currency_mismatch", candidate)
    if candidate.quote_currency.upper() != DEFAULT_QUOTE_CURRENCY:
        return result(requirement, "policy_blocked", "quote_currency_not_krw", candidate)

    rate = numeric_rate(candidate.rate)
    if rate is None or rate <= 0:
        return result(requirement, "policy_blocked", "invalid_rate", candidate)

    if not candidate.provider:
        return result(requirement, "provider_not_found", "provider_missing", candidate)
    if candidate.provider.lower() not in ALLOWED_PROVIDERS:
        return result(requirement, "policy_blocked", "provider_not_allowlisted", candidate)

    if candidate.source_type.lower() not in ALLOWED_SOURCE_TYPES:
        return result(requirement, "policy_blocked", "source_type_not_allowed", candidate)
    if candidate.status.lower() not in USABLE_FX_RATE_STATUSES:
        return result(requirement, "still_review_gated", "status_not_usable", candidate)
    if not use_case_matches(requirement.use_case, candidate.use_case):
        return result(requirement, "still_review_gated", "use_case_mismatch", candidate)

    if not text_value(candidate.source_note):
        return result(requirement, "insufficient_evidence", "source_note_missing", candidate)
    if source_note_has_secret(candidate.source_note):
        return result(requirement, "insufficient_evidence", "source_note_not_redacted", candidate)
    if not valid_response_hash(candidate.response_sha256):
        return result(requirement, "insufficient_evidence", "response_hash_missing", candidate)
    if url_template_has_secret(candidate.source_url_template):
        return result(requirement, "insufficient_evidence", "source_url_template_not_redacted", candidate)

    return result(requirement, "candidate_resolved_by_archived_fx", "same_date_archived_fx_candidate", candidate)


def candidate_sort_key(candidate: FxArchiveCandidate) -> tuple[int, str, str]:
    exact_krw = 0 if candidate.quote_currency.upper() == DEFAULT_QUOTE_CURRENCY else 1
    exact_status = 0 if candidate.status.lower() in USABLE_FX_RATE_STATUSES else 1
    return (exact_krw, exact_status, candidate.archive_id)


def choose_candidate(requirement: NormalizedFxRequirement, candidates: list[FxArchiveCandidate]) -> FxArchiveCandidate | None:
    if not candidates:
        return None
    exact = [
        candidate
        for candidate in candidates
        if candidate.base_currency.upper() == requirement.base_currency
        and use_case_matches(requirement.use_case, candidate.use_case)
        and normalize_date_text(candidate.effective_date) == requirement.event_date
    ]
    if exact:
        return sorted(exact, key=candidate_sort_key)[0]
    nearby = [
        candidate
        for candidate in candidates
        if candidate.base_currency.upper() == requirement.base_currency
        and use_case_matches(requirement.use_case, candidate.use_case)
    ]
    if nearby:
        return sorted(nearby, key=candidate_sort_key)[0]
    same_currency = [candidate for candidate in candidates if candidate.base_currency.upper() == requirement.base_currency]
    if same_currency:
        return sorted(same_currency, key=candidate_sort_key)[0]
    return None


def validate_requirements_against_archive(
    requirements: list[NormalizedFxRequirement],
    archive_rows: Iterable[dict[str, Any]],
) -> list[FxValidationResult]:
    candidates = [archive_candidate_from_row(row) for row in archive_rows]
    results: list[FxValidationResult] = []
    for requirement in requirements:
        candidate = choose_candidate(requirement, candidates) if requirement.fetch_target else None
        results.append(validate_requirement_candidate(requirement, candidate))
    return results


def build_validation_report(
    results: list[FxValidationResult],
    requirements_total: int | None = None,
) -> dict[str, int]:
    requirements_total = len(results) if requirements_total is None else requirements_total
    report = {
        "requirements_total": requirements_total,
        "distinct_requirement_keys": len({row.requirement_key for row in results}),
        "candidate_resolved_count": 0,
        "still_review_gated_count": 0,
        "invalid_requirement_count": 0,
        "provider_error_count": 0,
        "provider_not_found_count": 0,
        "policy_blocked_count": 0,
        "date_mismatch_count": 0,
        "rate_type_blocked_count": 0,
        "insufficient_evidence_count": 0,
    }
    for row in results:
        if row.decision == "candidate_resolved_by_archived_fx":
            report["candidate_resolved_count"] += 1
        else:
            key = f"{row.decision}_count"
            if key in report:
                report[key] += 1
    return report


def validation_result_rows(results: list[FxValidationResult]) -> list[dict[str, str]]:
    return [
        {
            "requirement_key": row.requirement_key,
            "decision": row.decision,
            "reason_code": row.reason_code,
            "provider": row.provider,
            "use_case": row.use_case,
            "parser_version": row.parser_version,
            "rule_version": row.rule_version,
        }
        for row in results
    ]


def write_validation_report_csv(path: Path, results: list[FxValidationResult]) -> None:
    rows = validation_result_rows(results)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["requirement_key", "decision", "reason_code", "provider", "use_case", "parser_version", "rule_version"],
        )
        writer.writeheader()
        writer.writerows(rows)


def validate_requirement_files(requirements_path: Path, archive_path: Path) -> tuple[list[FxValidationResult], dict[str, int]]:
    requirements = normalize_requirements(read_csv_rows(requirements_path))
    archive_rows = read_csv_rows(archive_path)
    results = validate_requirements_against_archive(requirements, archive_rows)
    return results, build_validation_report(results, requirements_total=len(requirements))


def archive_export_columns_are_compatible(columns: Iterable[str]) -> bool:
    present = set(columns)
    return all(column in present for column in FX_ARCHIVE_COLUMNS)
