from __future__ import annotations

import argparse
import os
from pathlib import Path

from nh_importer import import_raw_dir
from obsidian_writer import write_company_notes, write_dashboards
from portfolio_model import generate_reports
from qa_checker import run_qa


DEFAULT_LIVE_VAULT_ROOT = Path(r"C:\Users\KSLV-II\Desktop\Obsidian\ESJ\06_Stock")
LIVE_VAULT_ROOT_ENV = "STOCK_LIVE_VAULT_ROOT"
LIVE_WRITE_CONFIRMATION_TOKEN = "LIVE_06_STOCK_WRITE_REVIEWED"


def default_vault_root() -> Path:
    return Path(__file__).resolve().parents[2]


def normalized_path_key(path: Path | str) -> str:
    return str(Path(path).expanduser().resolve()).rstrip("\\/").casefold()


def configured_live_vault_roots() -> tuple[Path, ...]:
    roots = [DEFAULT_LIVE_VAULT_ROOT]
    configured = os.environ.get(LIVE_VAULT_ROOT_ENV, "").strip()
    if configured:
        roots.append(Path(configured))
    return tuple(roots)


def is_live_vault_path(vault_root: Path, live_roots: tuple[Path, ...] | None = None) -> bool:
    candidate = normalized_path_key(vault_root)
    roots = live_roots if live_roots is not None else configured_live_vault_roots()
    for root in roots:
        root_key = normalized_path_key(root)
        if candidate == root_key or candidate.startswith(root_key + "\\") or candidate.startswith(root_key + "/"):
            return True
    return False


def live_write_guard_findings(args: argparse.Namespace, vault_root: Path, live_roots: tuple[Path, ...] | None = None) -> list[str]:
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

    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NH/NAMUH Excel -> CSV/SQLite -> Obsidian dashboard pipeline")
    parser.add_argument("command", choices=["import", "report", "qa", "all"], help="실행할 작업")
    parser.add_argument("--vault-root", default=str(default_vault_root()), help="06_Stock Vault root")
    parser.add_argument("--raw-dir", default=None, help="raw Excel folder")
    parser.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 점검만 수행")
    parser.add_argument("--verbose", action="store_true", help="상세 로그 출력")
    parser.add_argument("--no-note-write", action="store_true", help="Obsidian note/dashboard 쓰기 생략")
    parser.add_argument("--create-companies", action="store_true", help="새 ticker 회사 노트 생성")
    parser.add_argument("--force-reindex", action="store_true", help="processed 결과를 새로 인덱싱")
    parser.add_argument("--live-baseline-updated", action="store_true", help="confirm the GitHub baseline was updated before a live vault write")
    parser.add_argument("--live-tests-passed", action="store_true", help="confirm pytest passed before a live vault write")
    parser.add_argument("--live-quality-gate-passed", action="store_true", help="confirm scripts/quality_gate.py passed before a live vault write")
    parser.add_argument("--live-dry-run-reviewed", action="store_true", help="confirm a live vault dry-run was completed and reviewed")
    parser.add_argument("--live-expected-changes-reviewed", action="store_true", help="confirm expected live vault changes were reviewed")
    parser.add_argument("--live-write-confirmation", default="", help=f"required token for actual live vault writes: {LIVE_WRITE_CONFIRMATION_TOKEN}")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    vault_root = Path(args.vault_root).resolve()
    raw_dir = Path(args.raw_dir).resolve() if args.raw_dir else vault_root / "70_Imports" / "raw"
    processed_dir = vault_root / "70_Imports" / "processed"

    guard_findings = live_write_guard_findings(args, vault_root)
    if guard_findings:
        print("[blocked] live vault actual-write guard refused this run.")
        print(f"[blocked] vault_root={vault_root}")
        for finding in guard_findings:
            print(f"[blocked] {finding}")
        print("[blocked] run the live vault dry-run first, review expected changes, then pass all live-write confirmation flags.")
        return 2

    print(f"[대상 Vault] {vault_root}")
    print(f"[Raw] {raw_dir}")
    if args.dry_run:
        print("[모드] dry-run: 파일을 실제로 쓰지 않습니다.")

    if args.command in {"import", "all"}:
        summary = import_raw_dir(vault_root, raw_dir=raw_dir, processed_dir=processed_dir, force_reindex=args.force_reindex, dry_run=args.dry_run, verbose=args.verbose)
        print(f"[import] raw_files={summary.raw_files}, parsed_rows={summary.parsed_rows}, duplicate_removed={summary.duplicate_rows_removed}, unclassified={summary.unclassified_rows}")

    if args.command in {"report", "all"}:
        report_summary = generate_reports(vault_root, processed_dir=processed_dir, dry_run=args.dry_run)
        print(f"[report] {report_summary}")
        if not args.no_note_write:
            warnings = write_dashboards(vault_root, processed_dir=processed_dir, dry_run=args.dry_run)
            warnings += write_company_notes(vault_root, processed_dir=processed_dir, create_companies=args.create_companies, dry_run=args.dry_run)
            for warning in warnings:
                print(f"[주의] {warning}")

    if args.command in {"qa", "all"}:
        qa = run_qa(vault_root, processed_dir=processed_dir, dry_run=args.dry_run)
        print(f"[qa] exceptions={len(qa)}")

    print("[완료] 자동 매수/매도 주문은 실행하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
