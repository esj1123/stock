from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nh_importer import import_raw_dir
from obsidian_writer import write_company_notes, write_dashboards
from portfolio_model import generate_reports
from qa_checker import build_qa_exception_rollup, run_qa


DEFAULT_LIVE_VAULT_ROOT = Path(r"C:\Users\KSLV-II\Desktop\Obsidian\ESJ\06_Stock")
LIVE_VAULT_ROOT_ENV = "STOCK_LIVE_VAULT_ROOT"
EVIDENCE_DIR_ENV = "STOCK_EVIDENCE_DIR"
LIVE_WRITE_CONFIRMATION_TOKEN = "LIVE_06_STOCK_WRITE_REVIEWED"
DRY_RUN_EVIDENCE_SCHEMA_VERSION = 2
DRY_RUN_EVIDENCE_MAX_AGE_SECONDS = 24 * 60 * 60
RAW_FINGERPRINT_ALGORITHM = "sha256:raw-size-mtime-ext-v1"
REQUIRED_QA_ROLLUP_EVIDENCE_COUNTS = (
    "exception_count",
    "qa_exception_count",
    "qa_rollup_row_count",
    "qa_distinct_issue_group_count",
    "qa_blocking_rollup_count",
    "qa_rollup_has_blocking_count",
)
UNSAFE_EVIDENCE_RELATIVE_ROOTS = (
    "70_Imports/raw",
    "70_Imports/processed",
    "70_Imports/exports",
    "70_Imports/logs",
    "20_Companies",
    "30_Trades",
    "31_Cashflows",
    "50_Journal",
    "60_Library",
    "90_Attachments",
)
GOOGLE_DRIVE_PATH_MARKERS = (
    "google drive",
    "googledrive",
    "drivefs",
    "my drive",
    "shared drives",
    "내 드라이브",
    "공유 드라이브",
)
DRY_RUN_CACHE_CONTEXT_FILES = (
    "fx_rates.csv",
    "fx_rates_cached.csv",
    "fx_unavailable_exceptions.csv",
)
DRY_RUN_PROCESSED_CONTEXT_FILES = (
    "performance_history.csv",
)


def default_vault_root() -> Path:
    return Path(__file__).resolve().parents[2]


def normalized_path_key(path: Path | str) -> str:
    return str(Path(path).expanduser().resolve()).rstrip("\\/").casefold()


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def path_identity_hash(path: Path | str) -> str:
    return sha256_text("path:v1:" + normalized_path_key(path))


def path_is_within(path: Path | str, root: Path | str) -> bool:
    candidate = normalized_path_key(path)
    root_key = normalized_path_key(root)
    return candidate == root_key or candidate.startswith(root_key + "\\") or candidate.startswith(root_key + "/")


def configured_live_vault_roots() -> tuple[Path, ...]:
    roots = [DEFAULT_LIVE_VAULT_ROOT]
    configured = os.environ.get(LIVE_VAULT_ROOT_ENV, "").strip()
    if configured:
        roots.append(Path(configured))
    return tuple(roots)


def is_live_vault_path(vault_root: Path, live_roots: tuple[Path, ...] | None = None) -> bool:
    roots = live_roots if live_roots is not None else configured_live_vault_roots()
    for root in roots:
        if path_is_within(vault_root, root):
            return True
    return False


def is_google_drive_synced_path(path: Path | str) -> bool:
    parts = [part.casefold() for part in Path(path).expanduser().parts]
    compact_parts = [part.replace(" ", "").replace("-", "").replace("_", "") for part in parts]
    for marker in GOOGLE_DRIVE_PATH_MARKERS:
        marker_folded = marker.casefold()
        marker_compact = marker_folded.replace(" ", "").replace("-", "").replace("_", "")
        if marker_folded in parts or marker_compact in compact_parts:
            return True
    return False


def default_evidence_dir() -> Path:
    configured = os.environ.get(EVIDENCE_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / "06_Stock" / "dry_run_evidence"
    return Path.home() / ".06_stock" / "dry_run_evidence"


def command_needs_materialized_dry_run_processed(command: str) -> bool:
    return command in {"import", "all"}


def copy_dry_run_cache_context(vault_root: Path, dry_run_import_root: Path) -> None:
    source_cache = vault_root / "70_Imports" / "cache"
    if not source_cache.exists():
        return

    target_cache = dry_run_import_root / "cache"
    for name in DRY_RUN_CACHE_CONTEXT_FILES:
        source = source_cache / name
        if not source.exists() or not source.is_file():
            continue
        target_cache.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target_cache / name)


def copy_dry_run_processed_context(vault_root: Path, dry_run_processed_dir: Path) -> None:
    source_processed = vault_root / "70_Imports" / "processed"
    if not source_processed.exists():
        return

    for name in DRY_RUN_PROCESSED_CONTEXT_FILES:
        source = source_processed / name
        if not source.exists() or not source.is_file():
            continue
        dry_run_processed_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dry_run_processed_dir / name)


def evidence_output_path_guidance() -> str:
    return f"use %{EVIDENCE_DIR_ENV}% or {default_evidence_dir()} outside the repo, live vault, and synced folders"


def dry_run_evidence_output_path_findings(
    evidence_path: Path,
    vault_root: Path,
    repo_root: Path | None = None,
    live_roots: tuple[Path, ...] | None = None,
) -> list[str]:
    repo = (repo_root or default_vault_root()).resolve()
    vault = vault_root.resolve()
    candidate = evidence_path.expanduser().resolve()
    findings: list[str] = []

    if path_is_within(candidate, repo):
        findings.append("dry-run evidence output path is inside repository root")

    roots = live_roots if live_roots is not None else configured_live_vault_roots()
    if any(path_is_within(candidate, root) for root in roots):
        findings.append("dry-run evidence output path is inside configured live vault root")

    if is_google_drive_synced_path(candidate):
        findings.append("dry-run evidence output path appears to be inside a Google Drive synced folder")

    for rel_root in UNSAFE_EVIDENCE_RELATIVE_ROOTS:
        rel_path = Path(rel_root)
        if path_is_within(candidate, repo / rel_path) or path_is_within(candidate, vault / rel_path):
            findings.append(f"dry-run evidence output path is inside restricted folder {rel_root}")

    return list(dict.fromkeys(findings))


def raw_metadata_fingerprint(raw_dir: Path) -> dict[str, Any]:
    files = (
        sorted(
            path
            for path in raw_dir.glob("*")
            if path.is_file() and path.suffix.lower() in {".xls", ".xlsx"} and not path.name.startswith("~$")
        )
        if raw_dir.exists()
        else []
    )
    entries: list[str] = []
    for path in files:
        stat = path.stat()
        entries.append(f"{path.suffix.lower()}:{stat.st_size}:{stat.st_mtime_ns}")
    material = "\n".join(sorted(entries))
    return {
        "algorithm": RAW_FINGERPRINT_ALGORITHM,
        "file_count": len(files),
        "digest": sha256_text(material),
    }


def sanitized_options(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "command": getattr(args, "command", ""),
        "create_companies": bool(getattr(args, "create_companies", False)),
        "force_reindex": bool(getattr(args, "force_reindex", False)),
        "no_note_write": bool(getattr(args, "no_note_write", False)),
    }


def sanitized_options_hash(args: argparse.Namespace) -> str:
    return sha256_text(json.dumps(sanitized_options(args), sort_keys=True, separators=(",", ":")))


def evidence_digest(payload: dict[str, Any]) -> str:
    canonical = dict(payload)
    canonical.pop("evidence_hash", None)
    text = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256_text(text)


def qa_rollup_evidence_counts(qa: Any) -> dict[str, int]:
    rollup = build_qa_exception_rollup(qa)
    if rollup.empty:
        return {
            "exception_count": int(len(qa)),
            "qa_exception_count": int(len(qa)),
            "qa_rollup_row_count": 0,
            "qa_distinct_issue_group_count": 0,
            "qa_blocking_rollup_count": 0,
            "qa_rollup_has_blocking_count": 0,
        }
    severity = rollup.get("severity")
    blocking_count = int(severity.astype(str).str.lower().eq("blocking").sum()) if severity is not None else 0
    has_blocking_count = int(sum(1 for value in rollup.get("has_blocking", []) if value is True or str(value).strip().lower() == "true"))
    return {
        "exception_count": int(len(qa)),
        "qa_exception_count": int(len(qa)),
        "qa_rollup_row_count": int(len(rollup)),
        "qa_distinct_issue_group_count": int(rollup["distinct_issue_group_count"].sum()),
        "qa_blocking_rollup_count": blocking_count,
        "qa_rollup_has_blocking_count": has_blocking_count,
    }


def build_dry_run_evidence(
    args: argparse.Namespace,
    vault_root: Path,
    raw_dir: Path,
    planned_categories: dict[str, Any] | None = None,
    warning_counts: dict[str, int] | None = None,
    created_at_utc: datetime | None = None,
) -> dict[str, Any]:
    timestamp = created_at_utc or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    payload: dict[str, Any] = {
        "schema_version": DRY_RUN_EVIDENCE_SCHEMA_VERSION,
        "created_at_utc": timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": "dry-run" if getattr(args, "dry_run", False) else "actual",
        "action": getattr(args, "command", ""),
        "vault_identity_hash": path_identity_hash(vault_root),
        "raw_identity_hash": path_identity_hash(raw_dir),
        "options_hash": sanitized_options_hash(args),
        "raw_metadata_fingerprint": raw_metadata_fingerprint(raw_dir),
        "planned_categories": planned_categories or {},
        "warning_counts": warning_counts or {},
    }
    payload["evidence_hash"] = evidence_digest(payload)
    return payload


def write_dry_run_evidence(
    path: Path,
    args: argparse.Namespace,
    vault_root: Path,
    raw_dir: Path,
    planned_categories: dict[str, Any],
    warning_counts: dict[str, int],
) -> None:
    payload = build_dry_run_evidence(args, vault_root, raw_dir, planned_categories, warning_counts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def parse_evidence_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def qa_rollup_evidence_count_findings(payload: dict[str, Any], action: str) -> list[str]:
    if action not in {"qa", "all"}:
        return []

    planned_categories = payload.get("planned_categories")
    if not isinstance(planned_categories, dict):
        return ["dry-run evidence planned_categories must be a JSON object"]

    qa_counts = planned_categories.get("qa")
    if not isinstance(qa_counts, dict):
        return ["dry-run evidence missing qa planned category"]

    findings: list[str] = []
    counts: dict[str, int] = {}
    for key in REQUIRED_QA_ROLLUP_EVIDENCE_COUNTS:
        if key not in qa_counts:
            findings.append(f"dry-run evidence missing qa rollup count: {key}")
            continue
        value = qa_counts.get(key)
        if type(value) is not int:
            findings.append(f"dry-run evidence qa rollup count is non-integer: {key}")
            continue
        if value < 0:
            findings.append(f"dry-run evidence qa rollup count is negative: {key}")
            continue
        counts[key] = value

    if set(counts) != set(REQUIRED_QA_ROLLUP_EVIDENCE_COUNTS):
        return findings

    if counts["exception_count"] != counts["qa_exception_count"]:
        findings.append("dry-run evidence exception_count and qa_exception_count disagree")
    if counts["qa_blocking_rollup_count"] > counts["qa_rollup_row_count"]:
        findings.append("dry-run evidence qa_blocking_rollup_count exceeds qa_rollup_row_count")
    if counts["qa_rollup_has_blocking_count"] > counts["qa_rollup_row_count"]:
        findings.append("dry-run evidence qa_rollup_has_blocking_count exceeds qa_rollup_row_count")
    return findings


def dry_run_evidence_findings(
    args: argparse.Namespace,
    vault_root: Path,
    raw_dir: Path,
    now: datetime | None = None,
) -> list[str]:
    evidence_arg = getattr(args, "live_dry_run_evidence", "")
    if not evidence_arg:
        return ["missing --live-dry-run-evidence"]

    evidence_path = Path(evidence_arg)
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"dry-run evidence file not found: {evidence_path}"]
    except json.JSONDecodeError:
        return [f"dry-run evidence is not valid JSON: {evidence_path}"]
    except OSError as exc:
        return [f"dry-run evidence could not be read: {exc}"]

    if not isinstance(payload, dict):
        return ["dry-run evidence must be a JSON object"]

    findings: list[str] = []
    if payload.get("evidence_hash") != evidence_digest(payload):
        findings.append("dry-run evidence hash mismatch")
    if payload.get("schema_version") != DRY_RUN_EVIDENCE_SCHEMA_VERSION:
        findings.append("dry-run evidence schema version mismatch")
    if payload.get("mode") != "dry-run":
        findings.append("dry-run evidence was not produced by --dry-run")
    if payload.get("action") != getattr(args, "command", ""):
        findings.append("dry-run evidence action mismatch")
    if payload.get("vault_identity_hash") != path_identity_hash(vault_root):
        findings.append("dry-run evidence vault mismatch")
    if payload.get("raw_identity_hash") != path_identity_hash(raw_dir):
        findings.append("dry-run evidence raw-dir mismatch")
    if payload.get("options_hash") != sanitized_options_hash(args):
        findings.append("dry-run evidence options mismatch")
    if payload.get("raw_metadata_fingerprint") != raw_metadata_fingerprint(raw_dir):
        findings.append("dry-run evidence raw metadata fingerprint mismatch")
    findings.extend(qa_rollup_evidence_count_findings(payload, getattr(args, "command", "")))

    timestamp = parse_evidence_timestamp(payload.get("created_at_utc"))
    if timestamp is None:
        findings.append("dry-run evidence timestamp is missing or invalid")
    else:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        age_seconds = (current.astimezone(timezone.utc) - timestamp).total_seconds()
        if age_seconds < 0:
            findings.append("dry-run evidence timestamp is in the future")
        elif age_seconds > DRY_RUN_EVIDENCE_MAX_AGE_SECONDS:
            findings.append("dry-run evidence is stale")

    return findings


def live_write_guard_findings(
    args: argparse.Namespace,
    vault_root: Path,
    raw_dir: Path | None = None,
    live_roots: tuple[Path, ...] | None = None,
) -> list[str]:
    if args.dry_run or not is_live_vault_path(vault_root, live_roots=live_roots):
        return []

    findings: list[str] = []
    required_flags = [
        ("live_baseline_updated", "--live-baseline-updated"),
        ("live_tests_passed", "--live-tests-passed"),
        ("live_quality_gate_passed", "--live-quality-gate-passed"),
        ("live_dry_run_reviewed", "--live-dry-run-reviewed"),
        ("live_expected_changes_reviewed", "--live-expected-changes-reviewed"),
    ]
    for attr, flag in required_flags:
        if not getattr(args, attr, False):
            findings.append(f"missing {flag}")

    if getattr(args, "live_write_confirmation", "") != LIVE_WRITE_CONFIRMATION_TOKEN:
        findings.append(f"missing --live-write-confirmation {LIVE_WRITE_CONFIRMATION_TOKEN}")

    evidence_raw_dir = raw_dir or vault_root / "70_Imports" / "raw"
    findings.extend(dry_run_evidence_findings(args, vault_root, evidence_raw_dir))
    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NH/NAMUH Excel -> CSV/SQLite -> Obsidian dashboard pipeline")
    parser.add_argument("command", choices=["import", "report", "qa", "all"], help="action to run")
    parser.add_argument("--vault-root", default=str(default_vault_root()), help="06_Stock vault root")
    parser.add_argument("--raw-dir", default=None, help="raw Excel folder")
    parser.add_argument("--dry-run", action="store_true", help="inspect without writing import, report, or note outputs")
    parser.add_argument("--verbose", action="store_true", help="print detailed import logs")
    parser.add_argument("--no-note-write", action="store_true", help="skip Obsidian note/dashboard writes")
    parser.add_argument("--create-companies", action="store_true", help="create missing company notes for new tickers")
    parser.add_argument("--force-reindex", action="store_true", help="reindex raw files regardless of existing processed output")
    parser.add_argument("--live-baseline-updated", action="store_true", help="confirm the GitHub baseline was updated before a live vault write")
    parser.add_argument("--live-tests-passed", action="store_true", help="confirm pytest passed before a live vault write")
    parser.add_argument("--live-quality-gate-passed", action="store_true", help="confirm scripts/quality_gate.py passed before a live vault write")
    parser.add_argument("--live-dry-run-reviewed", action="store_true", help="confirm a live vault dry-run was completed and reviewed")
    parser.add_argument("--live-expected-changes-reviewed", action="store_true", help="confirm expected live vault changes were reviewed")
    parser.add_argument("--live-write-confirmation", default="", help=f"required token for actual live vault writes: {LIVE_WRITE_CONFIRMATION_TOKEN}")
    parser.add_argument("--dry-run-evidence-out", default="", help="write privacy-safe dry-run evidence JSON to this path when --dry-run is used")
    parser.add_argument("--live-dry-run-evidence", default="", help="privacy-safe dry-run evidence JSON required before actual live vault writes")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    vault_root = Path(args.vault_root).resolve()
    raw_dir = Path(args.raw_dir).resolve() if args.raw_dir else vault_root / "70_Imports" / "raw"
    live_processed_dir = vault_root / "70_Imports" / "processed"

    guard_findings = live_write_guard_findings(args, vault_root, raw_dir)
    if guard_findings:
        print("[blocked] live vault actual-write guard refused this run.")
        print(f"[blocked] vault_root={vault_root}")
        for finding in guard_findings:
            print(f"[blocked] {finding}")
        print("[blocked] run the live vault dry-run first, review expected changes, then pass all live-write confirmation flags and matching evidence.")
        return 2

    evidence_output_path: Path | None = None
    if args.dry_run and args.dry_run_evidence_out:
        evidence_output_path = Path(args.dry_run_evidence_out).expanduser().resolve()
        evidence_path_findings = dry_run_evidence_output_path_findings(evidence_output_path, vault_root)
        if evidence_path_findings:
            print("[blocked] dry-run evidence output path refused.")
            for finding in evidence_path_findings:
                print(f"[blocked] {finding}")
            print(f"[blocked] {evidence_output_path_guidance()}")
            return 2

    print(f"[target vault] {vault_root}")
    print(f"[raw] {raw_dir}")
    if args.dry_run:
        print("[mode] dry-run: no import, report, or note output files will be written.")

    planned_categories: dict[str, Any] = {}
    warning_counts: dict[str, int] = {}

    with ExitStack() as stack:
        processed_dir = live_processed_dir
        dry_run_materialized_processed = False
        if args.dry_run and command_needs_materialized_dry_run_processed(args.command):
            temp_root = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="stock_dry_run_processed_")))
            dry_run_import_root = temp_root / "70_Imports"
            copy_dry_run_cache_context(vault_root, dry_run_import_root)
            processed_dir = dry_run_import_root / "processed"
            copy_dry_run_processed_context(vault_root, processed_dir)
            dry_run_materialized_processed = True

        if args.command in {"import", "all"}:
            import_dry_run = args.dry_run and not dry_run_materialized_processed
            summary = import_raw_dir(
                vault_root,
                raw_dir=raw_dir,
                processed_dir=processed_dir,
                force_reindex=args.force_reindex,
                dry_run=import_dry_run,
                verbose=args.verbose,
            )
            print(
                f"[import] raw_files={summary.raw_files}, parsed_rows={summary.parsed_rows}, "
                f"duplicate_removed={summary.duplicate_rows_removed}, unclassified={summary.unclassified_rows}"
            )
            planned_categories["import"] = {
                "raw_file_count": int(summary.raw_files),
                "parsed_row_count": int(summary.parsed_rows),
                "duplicate_rows_removed_count": int(summary.duplicate_rows_removed),
                "unclassified_row_count": int(summary.unclassified_rows),
                "unknown_column_count": int(summary.unknown_columns),
            }

        if args.command in {"report", "all"}:
            report_dry_run = args.dry_run and not dry_run_materialized_processed
            report_summary = generate_reports(vault_root, processed_dir=processed_dir, dry_run=report_dry_run)
            print(f"[report] {report_summary}")
            planned_categories["report"] = {str(key): int(value) for key, value in report_summary.items()}
            if not args.no_note_write:
                warnings = write_dashboards(vault_root, processed_dir=processed_dir, dry_run=args.dry_run)
                warnings += write_company_notes(vault_root, processed_dir=processed_dir, create_companies=args.create_companies, dry_run=args.dry_run)
                planned_categories["notes"] = {"note_update_category_count": 2}
                warning_counts["note_warning_count"] = len(warnings)
                for warning in warnings:
                    print(f"[warning] {warning}")

        if args.command in {"qa", "all"}:
            qa = run_qa(vault_root, processed_dir=processed_dir, dry_run=args.dry_run)
            print(f"[qa] exceptions={len(qa)}")
            planned_categories["qa"] = qa_rollup_evidence_counts(qa)
            warning_counts["qa_exception_count"] = int(len(qa))

        if args.dry_run and evidence_output_path:
            write_dry_run_evidence(evidence_output_path, args, vault_root, raw_dir, planned_categories, warning_counts)
            print(f"[dry-run-evidence] wrote {evidence_output_path}")

    print("[done] no automated buy/sell orders were executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
