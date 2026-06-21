from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

from fx_provenance_fetcher import read_csv_rows, text_value, write_csv_rows
from fx_provenance_validator import (
    ALLOWED_PROVIDERS,
    ALLOWED_SOURCE_TYPES,
    use_case_matches,
    url_template_has_secret,
    valid_response_hash,
)
from portfolio_model import FX_RATES_COLUMNS, USABLE_FX_RATE_STATUSES, normalized_date_text


PROMOTABLE_DECISION = "candidate_resolved_by_archived_fx"
PROMOTABLE_REASON = "same_date_archived_fx_candidate"
MANIFEST_VERSION = "fx_cache_promoter_v1"
DEFAULT_LIVE_VAULT_ROOT = Path(r"C:\Users\KSLV-II\Desktop\Obsidian\ESJ\06_Stock")
LIVE_VAULT_ROOT_ENV = "STOCK_LIVE_VAULT_ROOT"
SYNCED_PATH_MARKERS = {
    "google drive",
    "googledrive",
    "drivefs",
    "my drive",
    "shared drives",
    "onedrive",
}


class FxCachePromotionError(RuntimeError):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def is_relative_to_path(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def configured_live_vault_roots() -> list[Path]:
    roots = [DEFAULT_LIVE_VAULT_ROOT]
    configured = text_value(os.environ.get(LIVE_VAULT_ROOT_ENV))
    if configured:
        roots.append(Path(configured))
    return roots


def path_appears_synced(path: Path) -> bool:
    parts = [part.casefold() for part in path.expanduser().parts]
    compact_parts = [part.replace(" ", "").replace("-", "").replace("_", "") for part in parts]
    for marker in SYNCED_PATH_MARKERS:
        marker_folded = marker.casefold()
        marker_compact = marker_folded.replace(" ", "").replace("-", "").replace("_", "")
        if marker_folded in parts or marker_compact in compact_parts:
            return True
    return False


def path_has_restricted_import_segment(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    for index, part in enumerate(parts[:-1]):
        if part == "70_imports" and index + 1 < len(parts):
            return parts[index + 1] in {"raw", "processed", "exports", "logs"}
    return False


def ensure_safe_output_path(path: Path, *, allow_cache_path: bool = False) -> None:
    if is_relative_to_path(path, repo_root()):
        raise FxCachePromotionError("Output path must be outside the repository.")
    if not allow_cache_path and any(is_relative_to_path(path, root) for root in configured_live_vault_roots()):
        raise FxCachePromotionError("Promotion output path must be outside the live vault.")
    if not allow_cache_path and path_appears_synced(path):
        raise FxCachePromotionError("Promotion output path must be outside synced folders.")
    if path_has_restricted_import_segment(path):
        raise FxCachePromotionError("Output path must not be under raw, processed, exports, or logs.")
    if not allow_cache_path and path.name.lower() == "fx_rates.csv":
        raise FxCachePromotionError("Use --cache-path with --apply for private fx_rates.csv writes.")


def split_requirement_key(requirement_key: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in text_value(requirement_key).split("|")]
    if len(parts) != 3 or not all(parts):
        raise FxCachePromotionError("Promotable validation row has an invalid requirement key.")
    return normalized_date_text(parts[0]), parts[1].upper(), parts[2].lower()


def normalize_rate(value: Any) -> str:
    text = text_value(value).replace(",", "")
    try:
        parsed = float(text)
    except ValueError as exc:
        raise FxCachePromotionError("Archive candidate has an invalid rate.") from exc
    if parsed <= 0:
        raise FxCachePromotionError("Archive candidate rate must be positive.")
    return text


def fx_rate_cache_row(row: dict[str, Any]) -> dict[str, str]:
    output = {column: text_value(row.get(column)) for column in FX_RATES_COLUMNS}
    output["effective_date"] = normalized_date_text(output["effective_date"])
    output["base_currency"] = output["base_currency"].upper()
    output["quote_currency"] = output["quote_currency"].upper()
    output["rate"] = normalize_rate(output["rate"])
    output["source_type"] = output["source_type"].lower()
    output["provider"] = output["provider"].lower()
    output["use_case"] = output["use_case"].lower()
    output["status"] = output["status"].lower()
    if not output["source_note"]:
        raise FxCachePromotionError("Archive candidate source note is required.")
    if output["quote_currency"] != "KRW":
        raise FxCachePromotionError("Only KRW quote currency candidates can be promoted.")
    return output


def validate_promotable_archive_row(row: dict[str, Any]) -> dict[str, str]:
    output = fx_rate_cache_row(row)
    if output["provider"] not in ALLOWED_PROVIDERS:
        raise FxCachePromotionError("Archive candidate provider is not allowlisted.")
    if output["source_type"] not in ALLOWED_SOURCE_TYPES:
        raise FxCachePromotionError("Archive candidate source type is not usable by the pipeline.")
    if output["status"] not in USABLE_FX_RATE_STATUSES:
        raise FxCachePromotionError("Archive candidate status is not usable by the pipeline.")
    if not valid_response_hash(text_value(row.get("response_sha256"))):
        raise FxCachePromotionError("Archive candidate response hash is required.")
    if url_template_has_secret(text_value(row.get("source_url_template"))):
        raise FxCachePromotionError("Archive candidate source URL template must be redacted.")
    return output


def promotion_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    normalized = fx_rate_cache_row(row)
    return (
        normalized["effective_date"],
        normalized["base_currency"],
        normalized["quote_currency"],
        normalized["provider"],
        normalized["use_case"],
    )


def lenient_promotion_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        normalized_date_text(row.get("effective_date")),
        text_value(row.get("base_currency")).upper(),
        text_value(row.get("quote_currency")).upper(),
        text_value(row.get("provider")).lower(),
        text_value(row.get("use_case")).lower(),
    )


def rows_equivalent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_row = fx_rate_cache_row(left)
    right_row = fx_rate_cache_row(right)
    return all(left_row[column] == right_row[column] for column in FX_RATES_COLUMNS)


def candidate_validation_rows(validation_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    candidates = []
    seen: set[str] = set()
    for row in validation_rows:
        if text_value(row.get("decision")) != PROMOTABLE_DECISION:
            continue
        if text_value(row.get("reason_code")) != PROMOTABLE_REASON:
            continue
        requirement_key = text_value(row.get("requirement_key"))
        if requirement_key in seen:
            raise FxCachePromotionError("Duplicate promotable validation key found.")
        seen.add(requirement_key)
        candidates.append(row)
    return candidates


def archive_matches_validation(archive_row: dict[str, str], validation_row: dict[str, str]) -> bool:
    event_date, base_currency, use_case = split_requirement_key(validation_row["requirement_key"])
    candidate = fx_rate_cache_row(archive_row)
    provider = text_value(validation_row.get("provider")).lower()
    return (
        candidate["effective_date"] == event_date
        and candidate["base_currency"] == base_currency
        and candidate["quote_currency"] == "KRW"
        and candidate["provider"] == provider
        and use_case_matches(use_case, candidate["use_case"])
    )


def select_archive_row(
    archive_rows: list[dict[str, str]],
    validation_row: dict[str, str],
) -> dict[str, str]:
    matches = [validate_promotable_archive_row(row) for row in archive_rows if archive_matches_validation(row, validation_row)]
    if not matches:
        raise FxCachePromotionError("Promotable validation row has no matching archive candidate.")
    unique = {
        tuple(row[column] for column in FX_RATES_COLUMNS)
        for row in matches
    }
    if len(unique) != 1:
        raise FxCachePromotionError("Promotable validation row has conflicting archive candidates.")
    return matches[0]


def build_promotion_rows(
    archive_rows: list[dict[str, str]],
    validation_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    candidates = candidate_validation_rows(validation_rows)
    promotion_rows = [select_archive_row(archive_rows, row) for row in candidates]
    unique_rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for row in promotion_rows:
        key = promotion_key(row)
        if key in seen:
            raise FxCachePromotionError("Duplicate promotion cache key found.")
        seen.add(key)
        unique_rows.append(row)
    excluded_rows = len(validation_rows) - len(candidates)
    return unique_rows, {
        "validation_rows": len(validation_rows),
        "candidate_validation_rows": len(candidates),
        "excluded_validation_rows": excluded_rows,
    }


def compare_existing_cache(
    existing_rows: list[dict[str, str]],
    promotion_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], int]:
    rows_to_append: list[dict[str, str]] = []
    skipped_existing = 0
    for new_row in promotion_rows:
        new_key = promotion_key(new_row)
        matches = [row for row in existing_rows if lenient_promotion_key(row) == new_key]
        if not matches:
            rows_to_append.append(new_row)
            continue
        if all(rows_equivalent(existing, new_row) for existing in matches):
            skipped_existing += 1
            continue
        raise FxCachePromotionError("Existing cache has a conflicting row for a promotion key.")
    return rows_to_append, skipped_existing


def append_cache_rows(cache_path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not cache_path.exists() or cache_path.stat().st_size == 0
    with cache_path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FX_RATES_COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def build_manifest(
    *,
    promotion_rows: list[dict[str, str]],
    stats: dict[str, int],
    rows_to_append: list[dict[str, str]],
    skipped_existing: int,
    apply: bool,
) -> dict[str, int | bool | str]:
    return {
        "manifest_version": MANIFEST_VERSION,
        "apply": apply,
        "archive_written": False,
        "cache_write_requested": apply,
        "cache_rows_appended": len(rows_to_append) if apply else 0,
        "cache_rows_skipped_existing": skipped_existing,
        "promotion_rows": len(promotion_rows),
        "validation_rows": stats["validation_rows"],
        "candidate_validation_rows": stats["candidate_validation_rows"],
        "excluded_validation_rows": stats["excluded_validation_rows"],
        "rec_ex_01_status_changed": False,
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Promote reviewed FX archive candidates into a private FX cache.")
    parser.add_argument("--archive-candidates", required=True, help="Private FX archive candidate CSV path.")
    parser.add_argument("--validation-report", required=True, help="Sanitized validation report CSV path.")
    parser.add_argument("--promotion-out", help="Optional private OS-local promotion package CSV path.")
    parser.add_argument("--manifest-out", help="Optional private OS-local promotion manifest JSON path.")
    parser.add_argument("--cache-path", help="Private fx_rates.csv cache path. Required with --apply.")
    parser.add_argument("--expected-count", type=int, help="Abort unless the promotable row count matches this value.")
    parser.add_argument("--apply", action="store_true", help="Append promotion rows to --cache-path after conflict checks.")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    archive_path = Path(args.archive_candidates)
    validation_path = Path(args.validation_report)
    archive_rows = read_csv_rows(archive_path)
    validation_rows = read_csv_rows(validation_path)
    promotion_rows, stats = build_promotion_rows(archive_rows, validation_rows)

    if args.expected_count is not None and len(promotion_rows) != args.expected_count:
        raise FxCachePromotionError("Promotable row count did not match --expected-count.")

    rows_to_append = promotion_rows
    skipped_existing = 0
    if args.promotion_out:
        promotion_out = Path(args.promotion_out)
        ensure_safe_output_path(promotion_out)
        write_csv_rows(promotion_out, promotion_rows, FX_RATES_COLUMNS)

    if args.apply:
        if not args.cache_path:
            raise FxCachePromotionError("--cache-path is required with --apply.")
        cache_path = Path(args.cache_path)
        ensure_safe_output_path(cache_path, allow_cache_path=True)
        existing_rows = read_csv_rows(cache_path) if cache_path.exists() else []
        rows_to_append, skipped_existing = compare_existing_cache(existing_rows, promotion_rows)
        append_cache_rows(cache_path, rows_to_append)
    elif args.cache_path:
        ensure_safe_output_path(Path(args.cache_path), allow_cache_path=True)

    manifest = build_manifest(
        promotion_rows=promotion_rows,
        stats=stats,
        rows_to_append=rows_to_append,
        skipped_existing=skipped_existing,
        apply=bool(args.apply),
    )
    if args.manifest_out:
        manifest_out = Path(args.manifest_out)
        ensure_safe_output_path(manifest_out)
        write_manifest(manifest_out, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = run(args)
    except FxCachePromotionError as exc:
        parser.exit(2, f"fx_cache_promoter: {exc}\n")
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
