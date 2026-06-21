from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlencode

from portfolio_model import FX_RATES_COLUMNS


REQUIREMENT_COLUMNS = [
    "event_date",
    "currency",
    "use_case",
    "row_count",
    "amount_native_sum",
    "missing_reason",
    "source_file_type",
    "status",
]

FX_ARCHIVE_EXTRA_COLUMNS = [
    "archive_id",
    "fetched_at_utc",
    "request_date",
    "rate_type_class",
    "unit_factor",
    "derivation_method",
    "provider_series_key",
    "provider_timestamp",
    "response_sha256",
    "source_url_template",
    "parser_version",
    "rule_version",
    "supersedes_archive_id",
]

FX_ARCHIVE_COLUMNS = FX_RATES_COLUMNS + FX_ARCHIVE_EXTRA_COLUMNS
DEFAULT_QUOTE_CURRENCY = "KRW"
DEFAULT_PARSER_VERSION = "fx_provenance_fetcher_v1"
DEFAULT_RULE_VERSION = "rec_ex_01_a1_same_date_v1"
NETWORK_OPT_IN_ENV = "FX_PROVENANCE_ENABLE_NETWORK"
BOK_API_KEY_ENV = "BOK_ECOS_API_KEY"
EXIMBANK_API_KEY_ENV = "KOREAEXIM_API_KEY"
BOK_STAT_CODE_ENV = "BOK_ECOS_STAT_CODE"
BOK_USD_ITEM_CODE_ENV = "BOK_ECOS_USD_ITEM_CODE"
PROVIDER_TIMEOUT_SECONDS = 15
EXIMBANK_SOURCE_URL_TEMPLATE = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?authkey=<redacted>&searchdate={date}&data=AP01"
BOK_SOURCE_URL_TEMPLATE = "https://ecos.bok.or.kr/api/StatisticSearch/<redacted>/json/kr/1/100/{stat_code}/D/{date}/{date}/{item_code}"
HttpGet = Callable[[str, int], str]
EXIMBANK_VERIFIED_RESULT_CODE_MAP: dict[str, tuple[str, str, str]] = {
    # Keep this map limited to result codes verified from official Korea Eximbank documentation.
    # Unverified codes, including operator-observed result=3, must use the safe generic fallback.
}
PROVIDER_DIAGNOSTIC_COLUMNS = [
    "request_date",
    "http_status_class",
    "content_type_class",
    "response_row_count",
    "usd_candidate_row_count",
    "provider_status_category",
    "effective_date_match",
    "response_sha256",
]
VALIDATION_REPORT_COLUMNS = [
    "requirement_key",
    "decision",
    "reason_code",
    "operator_review_label",
    "provider",
    "use_case",
    *PROVIDER_DIAGNOSTIC_COLUMNS,
    "parser_version",
    "rule_version",
]
OFFICIAL_FX_UNAVAILABLE_LABEL = "official_fx_unavailable_non_business_day"


def text_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "<na>"}:
        return ""
    return text


def normalize_date_text(value: Any) -> str:
    text = text_value(value)
    if not text:
        return ""
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def is_currency_code(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{3}", value))


def looks_like_fx_rate(value: str) -> bool:
    return bool(re.fullmatch(r"\d+(\.\d+)?", value.strip()))


def normalize_use_case(value: Any) -> str:
    text = text_value(value).lower()
    return text or "all"


@dataclass(frozen=True)
class NormalizedFxRequirement:
    requirement_key: str
    event_date: str
    base_currency: str
    quote_currency: str
    use_case: str
    status: str
    fetch_target: bool = True
    invalid_reason: str = ""


def invalid_requirement_key(index: int, reason: str) -> str:
    return f"invalid_requirement_{index}_{reason}"


def make_requirement_key(event_date: str, base_currency: str, use_case: str) -> str:
    return f"{event_date}|{base_currency}|{use_case}"


def normalize_requirement_row(row: dict[str, Any], index: int = 1) -> NormalizedFxRequirement:
    event_date = normalize_date_text(row.get("event_date", ""))
    base_currency = text_value(row.get("currency", "")).upper()
    use_case = normalize_use_case(row.get("use_case", ""))
    status = text_value(row.get("status", "")).lower() or "fx_missing"

    if not event_date:
        return NormalizedFxRequirement(
            requirement_key=invalid_requirement_key(index, "missing_event_date"),
            event_date="",
            base_currency="",
            quote_currency=DEFAULT_QUOTE_CURRENCY,
            use_case=use_case,
            status=status,
            fetch_target=False,
            invalid_reason="invalid_requirement",
        )
    if not is_currency_code(base_currency):
        reason = "invalid_currency"
        if looks_like_fx_rate(base_currency):
            reason = "invalid_currency_fx_rate_value"
        return NormalizedFxRequirement(
            requirement_key=invalid_requirement_key(index, reason),
            event_date=event_date,
            base_currency="",
            quote_currency=DEFAULT_QUOTE_CURRENCY,
            use_case=use_case,
            status=status,
            fetch_target=False,
            invalid_reason=reason,
        )
    if base_currency == DEFAULT_QUOTE_CURRENCY:
        return NormalizedFxRequirement(
            requirement_key=make_requirement_key(event_date, base_currency, use_case),
            event_date=event_date,
            base_currency=base_currency,
            quote_currency=DEFAULT_QUOTE_CURRENCY,
            use_case=use_case,
            status=status,
            fetch_target=False,
            invalid_reason="not_required",
        )
    return NormalizedFxRequirement(
        requirement_key=make_requirement_key(event_date, base_currency, use_case),
        event_date=event_date,
        base_currency=base_currency,
        quote_currency=DEFAULT_QUOTE_CURRENCY,
        use_case=use_case,
        status=status,
    )


def normalize_requirements(rows: Iterable[dict[str, Any]]) -> list[NormalizedFxRequirement]:
    normalized: list[NormalizedFxRequirement] = []
    seen_keys: set[str] = set()
    for index, row in enumerate(rows, start=1):
        requirement = normalize_requirement_row(row, index=index)
        if not requirement.invalid_reason and requirement.requirement_key in seen_keys:
            continue
        if not requirement.invalid_reason:
            seen_keys.add(requirement.requirement_key)
        normalized.append(requirement)
    return normalized


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def redact_secrets(text: str) -> str:
    redacted = text_value(text)
    for env_name in [BOK_API_KEY_ENV, EXIMBANK_API_KEY_ENV]:
        env_value = os.getenv(env_name, "")
        if env_value and len(env_value) >= 4:
            redacted = redacted.replace(env_value, "<redacted>")
    redacted = re.sub(
        r"(?i)(api[_-]?key|auth[_-]?key|token|secret|password)=([^&\s]+)",
        r"\1=<redacted>",
        redacted,
    )
    return redacted


def http_get_text(url: str, timeout: int = PROVIDER_TIMEOUT_SECONDS) -> str:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "06_Stock-fx-provenance/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise FxProviderError("provider_error", f"provider HTTP error: {error.code}") from error
    except urllib.error.URLError as error:
        raise FxProviderError("provider_error", f"provider network error: {type(error.reason).__name__}") from error


def empty_provider_diagnostics() -> dict[str, str]:
    return {column: "" for column in PROVIDER_DIAGNOSTIC_COLUMNS}


def provider_diagnostics(
    *,
    request_date: str,
    response_text: str = "",
    response_row_count: int | str = "",
    usd_candidate_row_count: int | str = "",
    provider_status_category: str = "",
    effective_date_match: str = "",
    http_status_class: str = "",
    content_type_class: str = "",
) -> dict[str, str]:
    diagnostics = empty_provider_diagnostics()
    diagnostics.update(
        {
            "request_date": normalize_date_text(request_date),
            "http_status_class": text_value(http_status_class),
            "content_type_class": text_value(content_type_class),
            "response_row_count": text_value(response_row_count),
            "usd_candidate_row_count": text_value(usd_candidate_row_count),
            "provider_status_category": text_value(provider_status_category),
            "effective_date_match": text_value(effective_date_match),
            "response_sha256": sha256_text(response_text) if response_text else "",
        }
    )
    return diagnostics


def operator_review_label(decision: str, reason_code: str) -> str:
    reason = text_value(reason_code).lower()
    normalized_decision = text_value(decision).lower()
    if reason in {"provider_empty_response", "official_fx_unavailable_same_date"}:
        return OFFICIAL_FX_UNAVAILABLE_LABEL
    if normalized_decision == "candidate_resolved_by_archived_fx":
        return "candidate_archive_review"
    return ""


@dataclass(frozen=True)
class FxArchiveCandidate:
    effective_date: str
    base_currency: str
    quote_currency: str
    rate: str
    source_type: str
    provider: str
    use_case: str
    status: str
    source_note: str
    archive_id: str = ""
    fetched_at_utc: str = ""
    request_date: str = ""
    rate_type_class: str = "official_reference"
    unit_factor: str = "1"
    derivation_method: str = "direct_provider_rate"
    provider_series_key: str = ""
    provider_timestamp: str = ""
    response_sha256: str = ""
    source_url_template: str = ""
    parser_version: str = DEFAULT_PARSER_VERSION
    rule_version: str = DEFAULT_RULE_VERSION
    supersedes_archive_id: str = ""

    def with_archive_metadata(self) -> "FxArchiveCandidate":
        fetched_at = self.fetched_at_utc or utc_now_text()
        request_date = self.request_date or self.effective_date
        response_hash = self.response_sha256
        identity = "|".join(
            [
                self.effective_date,
                self.base_currency,
                self.quote_currency,
                str(self.rate),
                self.provider,
                self.use_case,
                response_hash,
                request_date,
            ]
        )
        archive_id = self.archive_id or sha256_text(identity)[:16]
        return FxArchiveCandidate(
            effective_date=self.effective_date,
            base_currency=self.base_currency.upper(),
            quote_currency=self.quote_currency.upper(),
            rate=str(self.rate),
            source_type=self.source_type,
            provider=self.provider,
            use_case=normalize_use_case(self.use_case),
            status=self.status,
            source_note=redact_secrets(self.source_note),
            archive_id=archive_id,
            fetched_at_utc=fetched_at,
            request_date=request_date,
            rate_type_class=self.rate_type_class,
            unit_factor=str(self.unit_factor),
            derivation_method=self.derivation_method,
            provider_series_key=self.provider_series_key,
            provider_timestamp=self.provider_timestamp,
            response_sha256=response_hash,
            source_url_template=redact_secrets(self.source_url_template),
            parser_version=self.parser_version,
            rule_version=self.rule_version,
            supersedes_archive_id=self.supersedes_archive_id,
        )

    def to_archive_row(self, include_extra: bool = True) -> dict[str, str]:
        candidate = self.with_archive_metadata()
        row = {
            "effective_date": candidate.effective_date,
            "base_currency": candidate.base_currency,
            "quote_currency": candidate.quote_currency,
            "rate": str(candidate.rate),
            "source_type": candidate.source_type,
            "provider": candidate.provider,
            "use_case": candidate.use_case,
            "status": candidate.status,
            "source_note": candidate.source_note,
            "archive_id": candidate.archive_id,
            "fetched_at_utc": candidate.fetched_at_utc,
            "request_date": candidate.request_date,
            "rate_type_class": candidate.rate_type_class,
            "unit_factor": candidate.unit_factor,
            "derivation_method": candidate.derivation_method,
            "provider_series_key": candidate.provider_series_key,
            "provider_timestamp": candidate.provider_timestamp,
            "response_sha256": candidate.response_sha256,
            "source_url_template": candidate.source_url_template,
            "parser_version": candidate.parser_version,
            "rule_version": candidate.rule_version,
            "supersedes_archive_id": candidate.supersedes_archive_id,
        }
        columns = FX_ARCHIVE_COLUMNS if include_extra else FX_RATES_COLUMNS
        return {column: row.get(column, "") for column in columns}


def archive_candidate_from_response(
    *,
    requirement: NormalizedFxRequirement,
    rate: Any,
    provider: str,
    source_type: str,
    status: str,
    source_note: str,
    response_text: str,
    source_url_template: str = "",
    provider_series_key: str = "",
    provider_timestamp: str = "",
) -> FxArchiveCandidate:
    return FxArchiveCandidate(
        effective_date=requirement.event_date,
        base_currency=requirement.base_currency,
        quote_currency=requirement.quote_currency,
        rate=str(rate),
        source_type=source_type,
        provider=provider,
        use_case=requirement.use_case,
        status=status,
        source_note=source_note,
        response_sha256=sha256_text(response_text),
        source_url_template=source_url_template,
        provider_series_key=provider_series_key,
        provider_timestamp=provider_timestamp,
    ).with_archive_metadata()


def parse_decimal_text(value: Any) -> str:
    text = text_value(value).replace(",", "")
    if not text:
        raise FxProviderError("provider_error", "provider response missing FX rate", reason_code="rate_missing_or_invalid")
    try:
        parsed = float(text)
    except ValueError as error:
        raise FxProviderError("provider_error", "provider response has invalid FX rate", reason_code="rate_missing_or_invalid") from error
    if parsed <= 0:
        raise FxProviderError("provider_error", "provider response has non-positive FX rate", reason_code="rate_missing_or_invalid")
    return f"{parsed:.10f}".rstrip("0").rstrip(".")


def eximbank_request_date(date_text: str) -> str:
    normalized = normalize_date_text(date_text)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        raise FxProviderError("provider_error", "invalid request date")
    return normalized.replace("-", "")


def eximbank_request_url(api_key: str, date_text: str) -> str:
    query = urlencode({"authkey": api_key, "searchdate": eximbank_request_date(date_text), "data": "AP01"})
    return f"https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?{query}"


def eximbank_status_error(result_code: Any) -> tuple[str, str, str, str]:
    status_category = text_value(result_code) or "unknown"
    mapping = EXIMBANK_VERIFIED_RESULT_CODE_MAP.get(status_category)
    if mapping:
        category, reason_code, safe_message = mapping
        return category, reason_code, safe_message, status_category
    return (
        "provider_error",
        "provider_status_error",
        "Eximbank returned an unverified provider status",
        status_category,
    )


def parse_eximbank_exchange_response(
    *,
    requirement: NormalizedFxRequirement,
    response_text: str,
    request_date: str,
) -> FxArchiveCandidate:
    expected_date = normalize_date_text(request_date)
    base_diagnostics = provider_diagnostics(request_date=expected_date, response_text=response_text)
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise FxProviderError(
            "provider_error",
            "Eximbank response is not valid JSON",
            reason_code="provider_schema_mismatch",
            diagnostics=base_diagnostics,
        ) from error
    if not isinstance(payload, list):
        raise FxProviderError(
            "provider_error",
            "Eximbank response schema is not a list",
            reason_code="provider_schema_mismatch",
            diagnostics=base_diagnostics,
        )
    if not payload:
        raise FxProviderError(
            "provider_not_found",
            "Eximbank response has no rates for request date",
            reason_code="provider_empty_response",
            diagnostics=provider_diagnostics(request_date=expected_date, response_text=response_text, response_row_count=0, usd_candidate_row_count=0),
        )

    if not all(isinstance(item, dict) for item in payload):
        raise FxProviderError(
            "provider_error",
            "Eximbank response row schema is invalid",
            reason_code="provider_schema_mismatch",
            diagnostics=provider_diagnostics(request_date=expected_date, response_text=response_text, response_row_count=len(payload)),
        )

    status_rows = [item for item in payload if "result" in item and not text_value(item.get("cur_unit"))]
    if status_rows:
        category, reason_code, safe_message, status_category = eximbank_status_error(status_rows[0].get("result"))
        raise FxProviderError(
            category,
            safe_message,
            reason_code=reason_code,
            diagnostics=provider_diagnostics(
                request_date=expected_date,
                response_text=response_text,
                response_row_count=len(payload),
                provider_status_category=status_category,
            ),
        )

    usd_rows = [item for item in payload if text_value(item.get("cur_unit")).upper() == requirement.base_currency]
    row = usd_rows[0] if usd_rows else None
    diagnostics = provider_diagnostics(
        request_date=expected_date,
        response_text=response_text,
        response_row_count=len(payload),
        usd_candidate_row_count=len(usd_rows),
    )
    if row is None:
        raise FxProviderError(
            "provider_not_found",
            "Eximbank response has no matching base currency",
            reason_code="usd_row_missing",
            diagnostics=diagnostics,
        )

    response_date_value = row.get("search_date") or row.get("date") or row.get("base_date")
    if text_value(response_date_value):
        response_date = normalize_date_text(response_date_value)
        if response_date != expected_date:
            raise FxProviderError(
                "date_mismatch",
                "Eximbank response date does not match request date",
                reason_code="date_mismatch",
                diagnostics={**diagnostics, "effective_date_match": "false"},
            )
        source_note = "Korea Eximbank same-date USD/KRW deal_bas_r archive candidate"
    else:
        response_date = expected_date
        source_note = "Korea Eximbank AP01 request-date-backed USD/KRW deal_bas_r archive candidate"

    try:
        rate = parse_decimal_text(row.get("deal_bas_r"))
    except FxProviderError as error:
        raise FxProviderError(
            error.category,
            error.safe_message,
            reason_code="rate_missing_or_invalid",
            diagnostics={**diagnostics, "effective_date_match": "true"},
        ) from error
    return archive_candidate_from_response(
        requirement=requirement,
        rate=rate,
        provider="eximbank",
        source_type="api_archive",
        status="available",
        source_note=source_note,
        response_text=response_text,
        source_url_template=EXIMBANK_SOURCE_URL_TEMPLATE.format(date=eximbank_request_date(request_date)),
        provider_series_key="koreaexim:exchangeJSON:AP01:USD:deal_bas_r",
        provider_timestamp=response_date,
    )


def bok_request_date(date_text: str) -> str:
    normalized = normalize_date_text(date_text)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        raise FxProviderError("provider_error", "invalid request date")
    return normalized.replace("-", "")


def bok_request_url(api_key: str, stat_code: str, item_code: str, date_text: str) -> str:
    request_date = bok_request_date(date_text)
    safe_stat = text_value(stat_code)
    safe_item = text_value(item_code)
    return (
        "https://ecos.bok.or.kr/api/StatisticSearch/"
        f"{api_key}/json/kr/1/100/{safe_stat}/D/{request_date}/{request_date}/{safe_item}"
    )


def parse_bok_exchange_response(
    *,
    requirement: NormalizedFxRequirement,
    response_text: str,
    request_date: str,
    stat_code: str,
    item_code: str,
) -> FxArchiveCandidate:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise FxProviderError("provider_error", "BOK response is not valid JSON") from error
    if not isinstance(payload, dict):
        raise FxProviderError("provider_error", "BOK response schema is not an object")
    rows = payload.get("StatisticSearch", {}).get("row")
    if rows is None:
        raise FxProviderError("provider_not_found", "BOK response has no StatisticSearch rows")
    if not isinstance(rows, list):
        raise FxProviderError("provider_error", "BOK response row schema is not a list")
    if not rows:
        raise FxProviderError("provider_not_found", "BOK response has no rates for request date")

    expected_date = normalize_date_text(request_date)
    matched = None
    for row in rows:
        row_item = text_value(row.get("ITEM_CODE1") or row.get("ITEM_CODE") or row.get("ITEM_NAME1"))
        if row_item in {item_code, ""}:
            matched = row
            break
    if matched is None:
        raise FxProviderError("provider_not_found", "BOK response has no matching USD item")

    response_date = normalize_date_text(matched.get("TIME") or expected_date)
    if response_date != expected_date:
        raise FxProviderError("date_mismatch", "BOK response date does not match request date")

    rate = parse_decimal_text(matched.get("DATA_VALUE"))
    return archive_candidate_from_response(
        requirement=requirement,
        rate=rate,
        provider="bok",
        source_type="api_archive",
        status="available",
        source_note="BOK ECOS configured same-date USD/KRW daily archive candidate",
        response_text=response_text,
        source_url_template=BOK_SOURCE_URL_TEMPLATE.format(stat_code=stat_code, date=bok_request_date(request_date), item_code=item_code),
        provider_series_key=f"bok:StatisticSearch:{stat_code}:D:{item_code}:DATA_VALUE",
        provider_timestamp=expected_date,
    )


class FxProviderError(Exception):
    def __init__(
        self,
        category: str,
        message: str,
        *,
        reason_code: str | None = None,
        diagnostics: dict[str, str] | None = None,
    ) -> None:
        super().__init__(redact_secrets(message))
        self.category = category
        self.safe_message = redact_secrets(message)
        self.reason_code = reason_code or category
        self.diagnostics = {**empty_provider_diagnostics(), **(diagnostics or {})}


class FxProviderClient:
    provider_name = "base"

    def __init__(self, http_get: HttpGet | None = None) -> None:
        self.http_get = http_get or http_get_text

    def fetch_rate(
        self,
        *,
        date: str,
        base_currency: str,
        quote_currency: str,
        use_case: str,
    ) -> FxArchiveCandidate:
        raise FxProviderError("provider_error", "provider adapter is not implemented")


class BokFxProviderClient(FxProviderClient):
    provider_name = "bok"

    def fetch_rate(
        self,
        *,
        date: str,
        base_currency: str,
        quote_currency: str,
        use_case: str,
    ) -> FxArchiveCandidate:
        if quote_currency.upper() != DEFAULT_QUOTE_CURRENCY:
            raise FxProviderError("policy_blocked", "BOK adapter only supports KRW quote currency")
        if os.getenv(NETWORK_OPT_IN_ENV) != "1":
            raise FxProviderError("policy_blocked", "network fetch disabled; set FX_PROVENANCE_ENABLE_NETWORK=1 to opt in")
        api_key = os.getenv(BOK_API_KEY_ENV)
        if not api_key:
            raise FxProviderError("provider_error", "BOK API key is missing")
        stat_code = os.getenv(BOK_STAT_CODE_ENV, "")
        item_code = os.getenv(BOK_USD_ITEM_CODE_ENV, "")
        if not stat_code or not item_code:
            raise FxProviderError("policy_blocked", "BOK ECOS series configuration is missing")
        if base_currency.upper() != "USD":
            raise FxProviderError("provider_not_found", "BOK adapter currently supports USD/KRW only")
        request = NormalizedFxRequirement(
            requirement_key=make_requirement_key(date, base_currency.upper(), use_case),
            event_date=normalize_date_text(date),
            base_currency=base_currency.upper(),
            quote_currency=quote_currency.upper(),
            use_case=normalize_use_case(use_case),
            status="fx_missing",
        )
        response_text = self.http_get(bok_request_url(api_key, stat_code, item_code, date), PROVIDER_TIMEOUT_SECONDS)
        return parse_bok_exchange_response(
            requirement=request,
            response_text=response_text,
            request_date=date,
            stat_code=stat_code,
            item_code=item_code,
        )


class KoreaEximFxProviderClient(FxProviderClient):
    provider_name = "eximbank"

    def fetch_rate(
        self,
        *,
        date: str,
        base_currency: str,
        quote_currency: str,
        use_case: str,
    ) -> FxArchiveCandidate:
        if quote_currency.upper() != DEFAULT_QUOTE_CURRENCY:
            raise FxProviderError("policy_blocked", "Eximbank adapter only supports KRW quote currency")
        if os.getenv(NETWORK_OPT_IN_ENV) != "1":
            raise FxProviderError("policy_blocked", "network fetch disabled; set FX_PROVENANCE_ENABLE_NETWORK=1 to opt in")
        api_key = text_value(os.getenv(EXIMBANK_API_KEY_ENV))
        if not api_key:
            raise FxProviderError("provider_error", "Korea Eximbank API key is missing")
        if base_currency.upper() != "USD":
            raise FxProviderError("provider_not_found", "Eximbank adapter currently supports USD/KRW only")
        request = NormalizedFxRequirement(
            requirement_key=make_requirement_key(date, base_currency.upper(), use_case),
            event_date=normalize_date_text(date),
            base_currency=base_currency.upper(),
            quote_currency=quote_currency.upper(),
            use_case=normalize_use_case(use_case),
            status="fx_missing",
        )
        response_text = self.http_get(eximbank_request_url(api_key, date), PROVIDER_TIMEOUT_SECONDS)
        return parse_eximbank_exchange_response(requirement=request, response_text=response_text, request_date=date)


def provider_client(name: str) -> FxProviderClient:
    key = text_value(name).lower()
    if key in {"bok", "bank_of_korea"}:
        return BokFxProviderClient()
    if key in {"eximbank", "koreaexim", "korea_eximbank"}:
        return KoreaEximFxProviderClient()
    raise FxProviderError("provider_not_found", f"provider not allowlisted: {redact_secrets(name)}")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def provider_error_record(requirement: NormalizedFxRequirement, provider: str, error: FxProviderError) -> dict[str, str]:
    row = {
        "requirement_key": requirement.requirement_key,
        "decision": error.category,
        "reason_code": error.reason_code,
        "operator_review_label": operator_review_label(error.category, error.reason_code),
        "provider": text_value(provider).lower(),
        "use_case": requirement.use_case,
        "parser_version": DEFAULT_PARSER_VERSION,
        "rule_version": DEFAULT_RULE_VERSION,
    }
    row.update(error.diagnostics)
    return row


def merge_failure_counts(report: dict[str, int], failures: list[dict[str, str]]) -> dict[str, int]:
    merged = dict(report)
    for failure in failures:
        key = f"{text_value(failure.get('decision')).lower()}_count"
        if key in merged:
            merged[key] += 1
    return merged


def fetch_candidates(
    requirements: list[NormalizedFxRequirement],
    provider_names: list[str],
) -> tuple[list[FxArchiveCandidate], list[dict[str, str]]]:
    candidates: list[FxArchiveCandidate] = []
    failures: list[dict[str, str]] = []
    for requirement in requirements:
        if not requirement.fetch_target:
            continue
        for provider_name in provider_names:
            try:
                client = provider_client(provider_name)
                candidates.append(
                    client.fetch_rate(
                        date=requirement.event_date,
                        base_currency=requirement.base_currency,
                        quote_currency=requirement.quote_currency,
                        use_case=requirement.use_case,
                    )
                )
                break
            except FxProviderError as error:
                failures.append(provider_error_record(requirement, provider_name, error))
    return candidates, failures


def parse_provider_names(value: str) -> list[str]:
    names = [name.strip().lower() for name in value.split(",") if name.strip()]
    return names or ["bok", "eximbank"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build sanitized FX provenance archive candidates from requirements.")
    parser.add_argument("--requirements-path", help="Private fx_rate_requirements.csv path.")
    parser.add_argument("--archive-in", help="Optional private archive CSV to validate.")
    parser.add_argument("--archive-out", help="Optional private archive output path. Ignored in report-only mode.")
    parser.add_argument("--validation-out", help="Optional private sanitized validation CSV output path.")
    parser.add_argument("--provider", default="bok,eximbank", help="Comma-separated provider names.")
    parser.add_argument("--canary-date", help="Public provider connectivity/parser canary date in YYYY-MM-DD format. Does not use private requirements or write archive.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fetch", action="store_true", help="Explicitly perform provider fetch attempts.")
    mode.add_argument("--report-only", action="store_true", help="Validate existing archive only; do not fetch providers.")
    parser.add_argument("--write-archive", action="store_true", help="Allow writing --archive-out when candidates exist.")
    return parser


def canary_requirement(canary_date: str) -> NormalizedFxRequirement:
    event_date = normalize_date_text(canary_date)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_date):
        raise FxProviderError("provider_error", "invalid canary date", reason_code="provider_schema_mismatch")
    return NormalizedFxRequirement(
        requirement_key=make_requirement_key(event_date, "USD", "provider_canary"),
        event_date=event_date,
        base_currency="USD",
        quote_currency=DEFAULT_QUOTE_CURRENCY,
        use_case="provider_canary",
        status="fx_missing",
    )


def main(argv: list[str] | None = None) -> int:
    from fx_provenance_validator import (
        apply_provider_failure_review_gates,
        build_validation_report,
        validation_result_rows,
        validate_requirements_against_archive,
    )

    args = build_parser().parse_args(argv)
    if args.canary_date:
        requirements = [canary_requirement(args.canary_date)]
    else:
        if not args.requirements_path:
            raise SystemExit("--requirements-path is required unless --canary-date is supplied")
        requirement_rows = read_csv_rows(Path(args.requirements_path))
        requirements = normalize_requirements(requirement_rows)
    provider_names = parse_provider_names(args.provider)

    archive_rows: list[dict[str, str]] = []
    provider_failures: list[dict[str, str]] = []
    if args.archive_in and not args.canary_date:
        archive_rows.extend(read_csv_rows(Path(args.archive_in)))
    fetch_enabled = bool(args.fetch)
    if fetch_enabled:
        candidates, provider_failures = fetch_candidates(requirements, provider_names)
        archive_rows.extend([candidate.to_archive_row(include_extra=True) for candidate in candidates])
        if args.archive_out and args.write_archive and not args.canary_date:
            write_csv_rows(Path(args.archive_out), archive_rows, FX_ARCHIVE_COLUMNS)

    results = validate_requirements_against_archive(requirements, archive_rows)
    if fetch_enabled:
        results = apply_provider_failure_review_gates(results, provider_failures)
    result_rows = validation_result_rows(results) + provider_failures
    report = merge_failure_counts(build_validation_report(results, requirements_total=len(requirements)), provider_failures)

    if args.validation_out:
        write_csv_rows(
            Path(args.validation_out),
            result_rows,
            VALIDATION_REPORT_COLUMNS,
        )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
