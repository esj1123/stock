from __future__ import annotations

import argparse
import csv
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

IMPORT_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "70_Imports" / "scripts"
if str(IMPORT_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(IMPORT_SCRIPTS_DIR))

from nh_importer import (
    AMOUNT_UNIT_AUDIT_COLUMNS,
    UNIT_MISMATCH_AUDIT_COLUMNS,
    canonical_overseas_position_key,
    dedupe_holdings,
    is_overseas_cashflow_amount_only_helper_row,
    is_overseas_position_row,
    is_principal_cashflow_row,
)
from obsidian_writer import company_note_identity_key, existing_company_note_index, parse_note_frontmatter, safe_component
import main as pipeline_main


AUTO_START = "<!-- AUTO-GENERATED:START -->"
AUTO_END = "<!-- AUTO-GENERATED:END -->"
BALANCE_SOURCE_TYPES = {"holdings", "overseas_balance"}
TRANSACTION_SOURCE_TYPES = {"transaction_history", "transactions", "cashflow"}
BLANK_VALUES = {"", "nan", "none", "na", "n/a", "<na>"}
COMPANY_QA_EXCEPTION_IDS = {"INV-EX-03", "INV-EX-08"}
CURRENCY_CODE_PATTERN = re.compile(r"^[A-Z]{3}$")
BROKER_KRW_SOURCES = {"broker_krw", "broker_provided_krw", "broker_krw_amount"}
REALIZED_COST_BASIS_METHOD = "fifo"
REALIZED_PNL_BASIS = "gross_trade_pnl_krw_fee_tax_separate"
RECONCILIATION_SUMMARY_ROLE = "audit_status_residual"
TOTAL_RETURN_ALIAS_OF = "performance_summary.cumulative_return_krw"
TOTAL_RETURN_PCT_ALIAS_OF = "performance_summary.cumulative_return_pct"
EXPLAINED_PROFIT_FORMULA = (
    "realized_trade_pnl_gross_krw+unrealized_pnl_krw+dividend_income_krw+"
    "interest_income_krw+distribution_income_krw-fee_expense_krw-tax_expense_krw"
)
FEE_TAX_TREATMENT = "gross_realized_pnl_minus_fee_tax_separate"
FX_PNL_TREATMENT = "not_modeled_residual_context"
REQUIRED_PERFORMANCE_METRICS = [
    "net_external_principal_krw",
    "external_deposit_krw",
    "external_withdrawal_krw",
    "current_total_assets_krw",
    "current_cash_krw",
    "current_holding_assets_krw",
    "cumulative_return_krw",
    "cumulative_return_pct",
    "realized_trade_pnl_gross_krw",
    "realized_trade_pnl_net_krw",
    "realized_gain_krw",
    "realized_loss_krw",
    "realized_loss_abs_krw",
    "unrealized_pnl_krw",
    "dividend_income_krw",
    "interest_income_krw",
    "distribution_income_krw",
    "income_total_krw",
    "fee_expense_krw",
    "tax_expense_krw",
    "explained_profit_krw",
    "reconciliation_residual_krw",
    "performance_status",
    "realized_pnl_status",
    "income_status",
    "fx_status",
    "income_fx_status",
    "income_fx_missing_row_count",
    "income_fx_source_summary",
    "fx_rate_requirement_row_count",
    "amount_review_needed_row_count",
]
PERFORMANCE_MONEY_METRICS = {
    "net_external_principal_krw",
    "external_deposit_krw",
    "external_withdrawal_krw",
    "current_total_assets_krw",
    "current_cash_krw",
    "current_holding_assets_krw",
    "cumulative_return_krw",
    "cumulative_return_pct",
    "realized_trade_pnl_gross_krw",
    "realized_trade_pnl_net_krw",
    "realized_gain_krw",
    "realized_loss_krw",
    "realized_loss_abs_krw",
    "unrealized_pnl_krw",
    "dividend_income_krw",
    "interest_income_krw",
    "distribution_income_krw",
    "income_total_krw",
    "fee_expense_krw",
    "tax_expense_krw",
    "explained_profit_krw",
    "reconciliation_residual_krw",
}
DISALLOWED_CASHFLOW_TYPES = {
    "buy",
    "sell",
    "dividend",
    "interest",
    "distribution",
    "exchange",
    "fee",
    "tax",
    "valuation",
    "valuation_snapshot",
}
AMBIGUOUS_OR_UNRESOLVED_STATUSES = {
    "fx_missing",
    "currency_ambiguous",
    "unit_ambiguous",
    "needs_review",
    "partial",
    "unclassified",
    "lot_missing",
}
INCOME_REVERSAL_KEYWORDS = {
    "reversal",
    "reversed",
    "cancel",
    "canceled",
    "cancelled",
    "cancellation",
    "correction",
    "corrected",
    "refund",
    "refunded",
    "취소",
    "정정",
    "환급",
}

REQUIRED_OUTPUT_SCHEMAS = {
    "processed_income.csv": [
        "source_file", "source_file_type", "account_type", "market", "trade_date", "trade_time",
        "ticker", "security_name", "income_type", "currency_native", "amount_native", "amount_krw",
        "amount_krw_source", "tax_native", "tax_krw", "fx_rate_to_krw", "fx_rate_source",
        "amount_kind", "amount_basis", "amount_confidence", "amount_review_status",
        "amount_review_reason", "affects_principal", "affects_profit", "raw_memo",
    ],
    "income_summary.csv": [
        "income_type", "currency_native", "amount_native_sum", "amount_krw_sum", "tax_native_sum",
        "tax_krw_sum", "net_income_native", "net_income_krw", "row_count", "fx_missing_row_count",
        "amount_review_needed_row_count", "fx_status_summary", "fx_source_summary", "income_status",
    ],
    "fx_rate_requirements.csv": [
        "event_date", "currency", "use_case", "row_count", "amount_native_sum",
        "missing_reason", "source_file_type", "status",
    ],
    "performance_summary.csv": ["metric", "value"],
    "monthly_cashflow_summary.csv": [
        "month",
        "external_deposit_krw",
        "external_withdrawal_krw",
        "net_principal_flow_krw",
        "cumulative_principal_krw",
    ],
    "performance_history.csv": [
        "snapshot_month",
        "snapshot_date",
        "cumulative_principal_krw",
        "current_total_assets_krw",
        "cumulative_return_krw",
        "cumulative_return_pct",
        "performance_status",
    ],
    "processed_expenses.csv": [
        "source_file", "source_file_type", "account_type", "market", "trade_date", "ticker",
        "security_name", "expense_type", "currency_native", "amount_native", "amount_krw",
        "fx_rate_to_krw", "fx_rate_source", "amount_kind", "amount_basis", "amount_confidence",
        "amount_review_status", "amount_review_reason", "affects_principal", "affects_profit",
        "raw_memo",
    ],
    "processed_fx_events.csv": [
        "fx_event_id", "source_file", "source_file_type", "account_type", "trade_date", "trade_time",
        "leg", "from_currency", "to_currency", "currency_native", "amount_native", "amount_krw",
        "fx_rate_to_krw", "fx_rate_source", "fx_pair_status", "cashflow_role", "affects_principal",
        "affects_profit", "is_internal_transfer", "amount_review_status", "amount_review_reason", "raw_memo",
    ],
    "processed_realized_pnl.csv": [
        "account_type", "market", "ticker", "security_name", "currency_native", "sell_date",
        "sell_import_id", "quantity_sold", "proceeds_native", "proceeds_krw", "cost_basis_native",
        "cost_basis_krw", "fee_native", "fee_krw", "tax_native", "tax_krw",
        "realized_trade_pnl_gross_native", "realized_trade_pnl_gross_krw",
        "realized_trade_pnl_net_native", "realized_trade_pnl_net_krw", "realized_result",
        "position_status", "cost_basis_method", "amount_review_status", "fx_status",
        "amount_review_reason", "source_file",
    ],
}

REQUIRED_RECONCILIATION_METRICS = [
    "reconciliation_summary_role",
    "total_return_alias_of",
    "total_return_pct_alias_of",
    "explained_profit_formula",
    "fee_tax_treatment",
    "fx_pnl_treatment",
    "total_assets_krw",
    "total_assets_status",
    "current_cash_krw",
    "current_holding_assets_krw",
    "external_deposit_krw",
    "external_withdrawal_krw",
    "net_external_principal_krw",
    "net_external_principal_status",
    "total_return_krw",
    "total_return_pct",
    "total_return_status",
    "unrealized_pnl_krw",
    "realized_pnl_krw",
    "realized_trade_pnl_gross_krw",
    "realized_trade_pnl_net_krw",
    "realized_gain_krw",
    "realized_loss_krw",
    "realized_cost_basis_method",
    "realized_pnl_basis",
    "realized_pnl_status",
    "realized_pnl_row_count",
    "realized_pnl_unavailable_row_count",
    "realized_closed_position_count",
    "dividend_income_krw",
    "interest_income_krw",
    "distribution_income_krw",
    "fee_expense_krw",
    "tax_expense_krw",
    "fx_pnl_status",
    "explained_profit_krw",
    "explained_profit_status",
    "residual_krw",
    "residual_status",
    "fx_missing_row_count",
    "currency_ambiguous_row_count",
    "unit_ambiguous_row_count",
    "amount_review_needed_row_count",
    "fx_event_id_count",
    "fx_event_leg_count",
    "fx_paired_event_count",
    "fx_partial_event_count",
    "fx_unpaired_event_count",
    "fx_needs_review_event_count",
    "fx_unpaired_or_needs_review_row_count",
    "fx_internal_transfer_row_count",
]

RECONCILIATION_COUNT_METRICS = {
    "fx_missing_row_count",
    "currency_ambiguous_row_count",
    "unit_ambiguous_row_count",
    "amount_review_needed_row_count",
    "realized_pnl_row_count",
    "realized_pnl_unavailable_row_count",
    "realized_closed_position_count",
    "fx_event_id_count",
    "fx_event_leg_count",
    "fx_paired_event_count",
    "fx_partial_event_count",
    "fx_unpaired_event_count",
    "fx_needs_review_event_count",
    "fx_unpaired_or_needs_review_row_count",
    "fx_internal_transfer_row_count",
}

RECONCILIATION_MONEY_METRICS = {
    "total_assets_krw",
    "current_cash_krw",
    "current_holding_assets_krw",
    "external_deposit_krw",
    "external_withdrawal_krw",
    "net_external_principal_krw",
    "total_return_krw",
    "total_return_pct",
    "unrealized_pnl_krw",
    "realized_pnl_krw",
    "realized_trade_pnl_gross_krw",
    "realized_trade_pnl_net_krw",
    "realized_gain_krw",
    "realized_loss_krw",
    "dividend_income_krw",
    "interest_income_krw",
    "distribution_income_krw",
    "fee_expense_krw",
    "tax_expense_krw",
    "explained_profit_krw",
    "residual_krw",
}

SENSITIVE_PATTERNS = [
    re.compile(r"\b(?!20\d{2}-\d{2}-\d{2}\b)\d{2,6}-\d{2,8}-\d{2,8}\b"),
    re.compile(r"\b\d{6}-[1-4]\d{6}\b"),
    re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"),
    re.compile(r"(?i)(api[_-]?key|api[_-]?secret|access[_-]?token|password|order[_-]?password|account[_-]?number|certificate)\s*[:=]\s*\S+"),
]


@dataclass
class GateResult:
    name: str
    status: str
    detail: str


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def is_blank(value: object) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in BLANK_VALUES


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_csv_header(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or [])


def boolish(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def text_value(value: object) -> str:
    return "" if value is None else str(value).strip()


def lower_value(value: object) -> str:
    return text_value(value).lower()


def upper_value(value: object) -> str:
    return text_value(value).upper()


def row_currency(row: dict[str, str]) -> str:
    return upper_value(row.get("currency_native") or row.get("currency"))


def row_status(row: dict[str, str]) -> str:
    return lower_value(
        row.get("amount_review_status")
        or row.get("amount_normalization_status")
        or row.get("fx_rate_status")
    )


def row_type(row: dict[str, str]) -> str:
    return lower_value(
        row.get("transaction_type")
        or row.get("income_type")
        or row.get("expense_type")
        or row.get("cashflow_role")
    )


def write_result(results: list[GateResult], name: str, status: str, detail: str) -> None:
    results.append(GateResult(name=name, status=status, detail=detail))
    print(f"[{status}] {name}: {detail}")


def worst_status(results: Iterable[GateResult]) -> str:
    statuses = [r.status for r in results]
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses:
        return "WARN"
    return "PASS"


def snapshot_raw_files(raw_dir: Path) -> dict[str, tuple[int, int]]:
    if not raw_dir.exists():
        return {}
    snapshot: dict[str, tuple[int, int]] = {}
    for path in sorted(raw_dir.rglob("*")):
        if path.is_file():
            stat = path.stat()
            snapshot[str(path.relative_to(raw_dir))] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def should_skip_markdown_path(path: Path) -> bool:
    skip_names = {".git", ".obsidian", ".venv", ".codex", ".codex-cache"}
    return any(part in skip_names or part.startswith(".tmp_pytest") for part in path.parts)


def strip_auto_generated_blocks(text: str) -> str:
    pattern = re.compile(re.escape(AUTO_START) + r".*?" + re.escape(AUTO_END), re.S)
    return pattern.sub(f"{AUTO_START}\n<AUTO-GENERATED>\n{AUTO_END}", text)


def snapshot_markdown_outside_auto(vault_root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(vault_root.rglob("*.md")):
        rel = path.relative_to(vault_root)
        if should_skip_markdown_path(rel):
            continue
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        normalized = strip_auto_generated_blocks(text)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        snapshot[str(path.relative_to(vault_root))] = digest
    return snapshot


def changed_entries(before: dict[str, object], after: dict[str, object]) -> list[str]:
    changed = []
    for key, old_value in before.items():
        if key not in after:
            changed.append(f"{key} removed")
        elif after[key] != old_value:
            changed.append(key)
    return changed


def run_command(args: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout


def scan_generated_markdown_sensitive(vault_root: Path) -> list[str]:
    findings: list[str] = []
    block_pattern = re.compile(re.escape(AUTO_START) + r"(.*?)" + re.escape(AUTO_END), re.S)
    for path in sorted(vault_root.rglob("*.md")):
        rel = path.relative_to(vault_root)
        if should_skip_markdown_path(rel):
            continue
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        for match in block_pattern.finditer(text):
            block = match.group(1)
            for pattern in SENSITIVE_PATTERNS:
                if pattern.search(block):
                    findings.append(str(path.relative_to(vault_root)))
                    break
    return findings


def dashboard_return_label_findings(vault_root: Path) -> list[str]:
    path = vault_root / "10_Dashboard" / "Portfolio.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    block_pattern = re.compile(re.escape(AUTO_START) + r"(.*?)" + re.escape(AUTO_END), re.S)
    forbidden = [
        '<span class="stock-kpi-label">Return</span>',
        "Portfolio Cost Basis",
        "Total Return %",
    ]
    findings: list[str] = []
    for block in (match.group(1) for match in block_pattern.finditer(text)):
        matches = [label for label in forbidden if label in block]
        if matches:
            findings.append("Portfolio.md generated block contains ambiguous return/cost labels: " + ", ".join(matches))
    return findings


def summary_map(processed_dir: Path) -> dict[str, str]:
    return {row.get("metric", ""): row.get("value", "") for row in read_csv_rows(processed_dir / "portfolio_summary.csv")}


def raw_excel_files(raw_dir: Path) -> list[Path]:
    if not raw_dir.exists():
        return []
    return sorted(path for path in raw_dir.glob("*") if path.suffix.lower() in {".xls", ".xlsx"} and not path.name.startswith("~$"))


def looks_like_fx_rate_value(value: object) -> bool:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return False
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", text))


def is_valid_currency_code(value: object) -> bool:
    text = str(value or "").strip().upper()
    return bool(CURRENCY_CODE_PATTERN.fullmatch(text))


def invalid_currency_findings(holdings: list[dict[str, str]]) -> list[str]:
    findings: list[str] = []
    for idx, row in enumerate(holdings, start=2):
        for field in ["currency", "currency_native"]:
            if field not in row:
                continue
            currency = row.get(field, "")
            if is_blank(currency):
                continue
            if looks_like_fx_rate_value(currency):
                findings.append(f"row {idx} {field} looks like FX rate: {currency}")
            elif not is_valid_currency_code(currency):
                findings.append(f"row {idx} invalid {field}={currency}")
    return findings


def non_krw_amount_without_fx_findings(rows: list[dict[str, str]]) -> list[str]:
    findings: list[str] = []
    for idx, row in enumerate(rows, start=2):
        currency = row_currency(row)
        if is_blank(currency) or currency == "KRW":
            continue
        if is_blank(row.get("amount_krw", "")):
            continue
        fx_rate = row.get("fx_rate_to_krw", "") or row.get("fx_rate", "")
        amount_source = lower_value(row.get("amount_krw_source"))
        amount_basis = lower_value(row.get("amount_basis"))
        has_provenance = (
            not is_blank(fx_rate)
            or amount_source in BROKER_KRW_SOURCES
            or amount_basis in BROKER_KRW_SOURCES
        )
        if not has_provenance:
            findings.append(
                f"row {idx} non-KRW native amount has amount_krw without FX or broker KRW source: "
                f"currency_native={currency} amount_krw={row.get('amount_krw')}"
            )
        native = optional_float(row.get("amount_native"))
        krw = optional_float(row.get("amount_krw"))
        if currency == "USD" and is_blank(fx_rate) and native is not None and krw is not None and abs(native - krw) < 0.0001:
            findings.append(f"row {idx} USD amount_krw equals amount_native while FX rate is blank")
    return findings


def principal_unit_misuse_findings(rows: list[dict[str, str]]) -> list[str]:
    findings: list[str] = []
    for idx, row in enumerate(rows, start=2):
        role = lower_value(row.get("cashflow_role"))
        affects_principal = boolish(row.get("affects_principal", ""))
        if not (affects_principal or role == "external_principal" or is_principal_cashflow_row(row)):
            continue
        amount_kind = lower_value(row.get("amount_kind"))
        quantity = optional_float(row.get("quantity") or row.get("raw_quantity"))
        price = optional_float(row.get("price") or row.get("raw_price"))
        if amount_kind in {"quantity", "unit_price"} or (quantity is not None and abs(quantity) > 1e-9) or (price is not None and abs(price) > 1e-9):
            findings.append(
                f"row {idx} principal row uses quantity/unit_price: "
                f"transaction_type={row.get('transaction_type')} amount_kind={row.get('amount_kind')} "
                f"quantity={row.get('quantity')} price={row.get('price')}"
            )
    return findings


def processed_output_schema_findings(processed_dir: Path) -> list[str]:
    findings: list[str] = []
    for name, required_columns in REQUIRED_OUTPUT_SCHEMAS.items():
        path = processed_dir / name
        if not path.exists():
            findings.append(f"{name} is missing")
            continue
        header = read_csv_header(path)
        missing = [col for col in required_columns if col not in header]
        if missing:
            findings.append(f"{name} missing required columns: {', '.join(missing)}")
    return findings


def realized_pnl_cost_basis_findings(rows: list[dict[str, str]]) -> list[str]:
    findings: list[str] = []
    for idx, row in enumerate(rows, start=2):
        method = lower_value(row.get("cost_basis_method"))
        if method != REALIZED_COST_BASIS_METHOD:
            findings.append(
                f"processed_realized_pnl.csv row {idx} cost_basis_method must be {REALIZED_COST_BASIS_METHOD}: "
                f"{row.get('cost_basis_method')}"
            )

        status = lower_value(row.get("amount_review_status"))
        fx_status = lower_value(row.get("fx_status"))
        if is_blank(status):
            findings.append(f"processed_realized_pnl.csv row {idx} has blank amount_review_status")
        if is_blank(fx_status):
            findings.append(f"processed_realized_pnl.csv row {idx} has blank fx_status")

        gross_krw = optional_float(row.get("realized_trade_pnl_gross_krw"))
        net_krw = optional_float(row.get("realized_trade_pnl_net_krw"))
        if status == "ok":
            official_values = {
                "proceeds_krw": optional_float(row.get("proceeds_krw")),
                "cost_basis_krw": optional_float(row.get("cost_basis_krw")),
                "fee_krw": optional_float(row.get("fee_krw")),
                "tax_krw": optional_float(row.get("tax_krw")),
                "realized_trade_pnl_gross_krw": gross_krw,
                "realized_trade_pnl_net_krw": net_krw,
            }
            missing = [field for field, value in official_values.items() if value is None]
            if missing:
                findings.append(f"processed_realized_pnl.csv row {idx} has status ok but blank official KRW fields: {', '.join(missing)}")
            else:
                expected_gross = official_values["proceeds_krw"] - official_values["cost_basis_krw"]
                expected_net = expected_gross - official_values["fee_krw"] - official_values["tax_krw"]
                if abs(gross_krw - expected_gross) > 0.0001:
                    findings.append(f"processed_realized_pnl.csv row {idx} gross KRW formula mismatch")
                if abs(net_krw - expected_net) > 0.0001:
                    findings.append(f"processed_realized_pnl.csv row {idx} net KRW formula mismatch")
        elif not is_blank(row.get("realized_trade_pnl_gross_krw", "")) or not is_blank(row.get("realized_trade_pnl_net_krw", "")):
            findings.append(
                f"processed_realized_pnl.csv row {idx} has non-ok status but official KRW realized PnL is populated"
            )

        if status == "lot_missing" and (
            not is_blank(row.get("realized_trade_pnl_gross_krw", ""))
            or not is_blank(row.get("realized_trade_pnl_net_krw", ""))
        ):
            findings.append(f"processed_realized_pnl.csv row {idx} has lot_missing status but official KRW realized PnL is populated")
        if fx_status == "fx_missing":
            if status == "ok":
                findings.append(f"processed_realized_pnl.csv row {idx} has fx_missing but amount_review_status is ok")
            if not is_blank(row.get("realized_trade_pnl_gross_krw", "")) or not is_blank(row.get("realized_trade_pnl_net_krw", "")):
                findings.append(f"processed_realized_pnl.csv row {idx} has fx_missing but official KRW realized PnL is populated")
    return findings


def realized_pnl_review_findings(rows: list[dict[str, str]]) -> list[str]:
    findings: list[str] = []
    review_statuses = {
        "fx_missing",
        "lot_missing",
        "needs_review",
        "amount_review_needed",
        "currency_ambiguous",
        "unit_ambiguous",
    }
    for idx, row in enumerate(rows, start=2):
        status = lower_value(row.get("amount_review_status"))
        fx_status = lower_value(row.get("fx_status"))
        reason = lower_value(row.get("amount_review_reason"))
        if status in review_statuses or fx_status == "fx_missing":
            findings.append(f"processed_realized_pnl.csv row {idx} requires review: amount_review_status={status or '<blank>'} fx_status={fx_status or '<blank>'}")
        if status == "lot_missing" or "sell quantity exceeds" in reason:
            findings.append(f"processed_realized_pnl.csv row {idx} sell quantity exceeds matched FIFO buy lots")
    return findings


def official_krw_total_provenance_findings(holdings: list[dict[str, str]], realized: list[dict[str, str]]) -> list[str]:
    findings: list[str] = []
    for idx, row in enumerate(holdings, start=2):
        currency = row_currency(row)
        if is_blank(currency) or currency == "KRW" or is_blank(row.get("evaluation_amount_krw", "")):
            continue
        fx_rate = row.get("fx_rate_to_krw", "") or row.get("fx_rate", "")
        amount_source = lower_value(row.get("amount_krw_source"))
        amount_basis = lower_value(row.get("amount_basis"))
        if is_blank(fx_rate) and amount_source not in BROKER_KRW_SOURCES | {"derived_krw_from_fx"} and amount_basis not in BROKER_KRW_SOURCES | {"derived_krw_from_fx"}:
            findings.append(f"processed_holdings row {idx} non-KRW evaluation_amount_krw lacks FX or broker KRW provenance")
    for idx, row in enumerate(realized, start=2):
        currency = row_currency(row)
        if is_blank(currency) or currency == "KRW":
            continue
        populated = [
            field
            for field in [
                "proceeds_krw",
                "cost_basis_krw",
                "realized_trade_pnl_gross_krw",
                "realized_trade_pnl_net_krw",
            ]
            if not is_blank(row.get(field, ""))
        ]
        if populated and lower_value(row.get("fx_status")) not in {"available", "broker_krw", "not_required"}:
            findings.append(f"processed_realized_pnl.csv row {idx} non-KRW official KRW fields lack available FX/broker status: {', '.join(populated)}")
    return findings


def audit_output_schema_findings(processed_dir: Path) -> list[str]:
    findings: list[str] = []
    required_by_file = {
        "amount_unit_audit.csv": AMOUNT_UNIT_AUDIT_COLUMNS,
        "unit_mismatch_audit.csv": UNIT_MISMATCH_AUDIT_COLUMNS,
    }
    for name, required_columns in required_by_file.items():
        path = processed_dir / name
        if not path.exists():
            findings.append(f"{name} is missing")
            continue
        header = read_csv_header(path)
        missing = [col for col in required_columns if col not in header]
        if missing:
            findings.append(f"{name} missing required columns: {', '.join(missing)}")
    return findings


def optional_float(value: object) -> float | None:
    if is_blank(value):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def summary_status_from_statuses(statuses: list[str]) -> str:
    blocking = [status for status in statuses if status and status != "ok"]
    if not blocking:
        return "available"
    for status in [
        "currency_ambiguous",
        "unit_ambiguous",
        "fx_missing",
        "lot_missing",
        "transaction_history_missing",
        "balance_missing",
        "currency_normalization_pending",
    ]:
        if status in blocking:
            return status
    return blocking[0]


def counts_summary(values: list[str]) -> str:
    cleaned = [value for value in values if value]
    counts: dict[str, int] = {}
    for value in cleaned:
        counts[value] = counts.get(value, 0) + 1
    return " / ".join(f"{key}: {value}" for key, value in counts.items())


def income_fx_status_and_source(row: dict[str, str]) -> tuple[str, str]:
    status = row_status(row) or "ok"
    currency = row_currency(row)
    if currency == "KRW":
        return "not_required", "raw_native"
    if status == "fx_missing":
        return "fx_missing", "fx_missing"
    source = text_value(row.get("amount_krw_source")) or text_value(row.get("fx_rate_source"))
    if status == "ok":
        return "available", source or "unknown"
    return status, source or status


def optional_abs_sum(rows: list[dict[str, str]], field: str, *, ok_only: bool = False) -> float | None:
    values: list[float] = []
    for row in rows:
        if ok_only and (row_status(row) or "ok") != "ok":
            continue
        amount = optional_float(row.get(field))
        if amount is not None:
            values.append(abs(amount))
    if not values:
        return None
    return float(sum(values))


def compare_optional_number(findings: list[str], label: str, actual_value: object, expected: float | None) -> None:
    actual = optional_float(actual_value)
    if expected is None:
        if not is_blank(actual_value):
            findings.append(f"{label} expected blank but found {actual_value}")
        return
    if actual is None:
        findings.append(f"{label} expected {expected} but was blank")
    elif abs(actual - expected) > 0.0001:
        findings.append(f"{label} expected {expected} but found {actual_value}")


def expected_income_summary(income_rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in income_rows:
        income_type = lower_value(row.get("income_type"))
        if income_type not in {"dividend", "interest", "distribution"}:
            continue
        groups.setdefault((income_type, row_currency(row)), []).append(row)

    expected: dict[tuple[str, str], dict[str, object]] = {}
    for key, rows in groups.items():
        statuses = [(row_status(row) or "ok") for row in rows]
        amount_native = optional_abs_sum(rows, "amount_native")
        tax_native = optional_abs_sum(rows, "tax_native")
        amount_krw = optional_abs_sum(rows, "amount_krw", ok_only=True)
        tax_krw = optional_abs_sum(rows, "tax_krw", ok_only=True)
        tax_native_for_net = tax_native if tax_native is not None else (0.0 if amount_native is not None else None)
        tax_krw_for_net = tax_krw if tax_krw is not None else (0.0 if amount_krw is not None else None)
        fx_statuses: list[str] = []
        fx_sources: list[str] = []
        for row in rows:
            fx_status, fx_source = income_fx_status_and_source(row)
            fx_statuses.append(fx_status)
            fx_sources.append(fx_source)
        expected[key] = {
            "amount_native_sum": amount_native,
            "amount_krw_sum": amount_krw,
            "tax_native_sum": tax_native_for_net,
            "tax_krw_sum": tax_krw_for_net,
            "net_income_native": (amount_native - tax_native_for_net) if amount_native is not None and tax_native_for_net is not None else None,
            "net_income_krw": (amount_krw - tax_krw_for_net) if amount_krw is not None and tax_krw_for_net is not None else None,
            "row_count": len(rows),
            "fx_missing_row_count": sum(1 for status in statuses if status == "fx_missing"),
            "amount_review_needed_row_count": sum(1 for status in statuses if status in AMBIGUOUS_OR_UNRESOLVED_STATUSES),
            "fx_status_summary": counts_summary(fx_statuses),
            "fx_source_summary": counts_summary(fx_sources),
            "income_status": summary_status_from_statuses(statuses),
        }
    return expected


def income_summary_contract_findings(summary_rows: list[dict[str, str]], income_rows: list[dict[str, str]]) -> list[str]:
    findings: list[str] = []
    expected = expected_income_summary(income_rows)
    actual_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for idx, row in enumerate(summary_rows, start=2):
        income_type = lower_value(row.get("income_type"))
        currency = row_currency(row)
        key = (income_type, currency)
        if income_type not in {"dividend", "interest", "distribution"}:
            findings.append(f"income_summary.csv row {idx} invalid income_type={row.get('income_type')}")
        if key in actual_by_key:
            findings.append(f"income_summary.csv duplicate row for income_type={income_type} currency_native={currency}")
        actual_by_key[key] = row

        for count_field in ["row_count", "fx_missing_row_count", "amount_review_needed_row_count"]:
            value = optional_float(row.get(count_field))
            if value is None or value < 0 or value != int(value):
                findings.append(f"income_summary.csv row {idx} {count_field} must be a non-negative integer: {row.get(count_field)}")
        status = lower_value(row.get("income_status"))
        if is_blank(status):
            findings.append(f"income_summary.csv row {idx} has blank income_status")
        if status == "available" and optional_float(row.get("amount_review_needed_row_count")) not in {0.0, None}:
            findings.append(f"income_summary.csv row {idx} income_status is available despite review-needed rows")

    missing = sorted(set(expected).difference(actual_by_key))
    unexpected = sorted(set(actual_by_key).difference(expected))
    if missing:
        labels = [f"{income_type}/{currency}" for income_type, currency in missing]
        findings.append("income_summary.csv missing expected rows: " + ", ".join(labels[:5]))
    if unexpected:
        labels = [f"{income_type}/{currency}" for income_type, currency in unexpected]
        findings.append("income_summary.csv has unexpected rows: " + ", ".join(labels[:5]))

    for key, expected_values in expected.items():
        row = actual_by_key.get(key)
        if row is None:
            continue
        label_prefix = f"income_summary.csv {key[0]}/{key[1]}"
        for field in [
            "amount_native_sum",
            "amount_krw_sum",
            "tax_native_sum",
            "tax_krw_sum",
            "net_income_native",
            "net_income_krw",
        ]:
            compare_optional_number(findings, f"{label_prefix} {field}", row.get(field), expected_values[field])
        for field in ["row_count", "fx_missing_row_count", "amount_review_needed_row_count"]:
            actual = optional_float(row.get(field))
            if actual is None or int(actual) != expected_values[field]:
                findings.append(f"{label_prefix} {field} expected {expected_values[field]} but found {row.get(field)}")
        if lower_value(row.get("income_status")) != expected_values["income_status"]:
            findings.append(
                f"{label_prefix} income_status expected {expected_values['income_status']} but found {row.get('income_status')}"
            )
        for field in ["fx_status_summary", "fx_source_summary"]:
            if text_value(row.get(field)) != expected_values[field]:
                findings.append(f"{label_prefix} {field} expected {expected_values[field]} but found {row.get(field)}")
    return findings


def fx_rate_requirements_findings(rows: list[dict[str, str]]) -> list[str]:
    findings: list[str] = []
    for idx, row in enumerate(rows, start=2):
        currency = upper_value(row.get("currency"))
        if not is_valid_currency_code(currency) or currency == "KRW":
            findings.append(f"fx_rate_requirements.csv row {idx} invalid currency={row.get('currency')}")
        if is_blank(row.get("event_date")):
            findings.append(f"fx_rate_requirements.csv row {idx} event_date is blank")
        if is_blank(row.get("use_case")):
            findings.append(f"fx_rate_requirements.csv row {idx} use_case is blank")
        row_count = optional_float(row.get("row_count"))
        if row_count is None or row_count <= 0 or row_count != int(row_count):
            findings.append(f"fx_rate_requirements.csv row {idx} row_count must be a positive integer: {row.get('row_count')}")
        amount_sum = optional_float(row.get("amount_native_sum"))
        if amount_sum is None or amount_sum <= 0:
            findings.append(f"fx_rate_requirements.csv row {idx} amount_native_sum must be positive: {row.get('amount_native_sum')}")
        if lower_value(row.get("status")) != "fx_missing":
            findings.append(f"fx_rate_requirements.csv row {idx} status must be fx_missing: {row.get('status')}")
        if is_blank(row.get("missing_reason")):
            findings.append(f"fx_rate_requirements.csv row {idx} missing_reason is blank")
    return findings


def income_reversal_review_findings(rows: list[dict[str, str]]) -> list[str]:
    suspicious: list[dict[str, str]] = []
    for row in rows:
        income_type = lower_value(row.get("income_type"))
        if income_type not in {"dividend", "interest", "distribution"}:
            continue
        has_negative_amount = any(
            (value := optional_float(row.get(field))) is not None and value < 0
            for field in ["amount_native", "amount_krw", "tax_native", "tax_krw"]
        )
        text = " ".join(
            lower_value(row.get(field))
            for field in ["transaction_type", "cashflow_role", "raw_memo", "amount_review_reason"]
        )
        has_reversal_keyword = any(keyword in text for keyword in INCOME_REVERSAL_KEYWORDS)
        if has_negative_amount or has_reversal_keyword:
            suspicious.append({
                "income_type": income_type,
                "status": row_status(row) or "ok",
                "signal": "negative_amount" if has_negative_amount else "reversal_keyword",
            })

    if not suspicious:
        return []

    income_types = sorted({row["income_type"] for row in suspicious})
    statuses = sorted({row["status"] for row in suspicious})
    signals = sorted({row["signal"] for row in suspicious})
    return [
        "processed_income reversal/refund-like rows need review before relying on absolute income_summary totals: "
        f"row_count={len(suspicious)}; income_types={','.join(income_types)}; "
        f"statuses={','.join(statuses)}; signals={','.join(signals)}"
    ]


def row_has_numeric_value(row: dict[str, str], fields: Iterable[str]) -> bool:
    return any(optional_float(row.get(field)) is not None for field in fields)


def official_total_candidate(row: dict[str, str]) -> bool:
    role = lower_value(row.get("cashflow_role"))
    if role == "external_principal" or boolish(row.get("affects_principal", "")):
        return row_has_numeric_value(row, ["amount_krw", "settlement_amount_krw", "trade_amount_krw"])
    if row_has_numeric_value(row, ["evaluation_amount_krw"]):
        return True
    return False


def unit_classification_findings(rows: list[dict[str, str]]) -> list[str]:
    findings: list[str] = []
    money_fields = [
        "amount_native",
        "amount_krw",
        "trade_amount_native",
        "trade_amount_krw",
        "settlement_amount_native",
        "settlement_amount_krw",
        "evaluation_amount_native",
        "evaluation_amount_krw",
        "unrealized_pnl_native",
        "unrealized_pnl_krw",
        "fee_native",
        "fee_krw",
        "tax_native",
        "tax_krw",
    ]
    for idx, row in enumerate(rows, start=2):
        amount_kind = lower_value(row.get("amount_kind"))
        amount_basis = lower_value(row.get("amount_basis"))
        if amount_kind == "fx_rate" and row_has_numeric_value(row, money_fields):
            findings.append(f"row {idx} FX rate is present in money amount fields")
        if not official_total_candidate(row):
            continue
        currency = row_currency(row)
        status = row_status(row)
        missing = []
        if is_blank(amount_kind) or amount_kind in {"unknown", "quantity", "unit_price", "fx_rate"}:
            missing.append("amount_kind")
        if is_blank(amount_basis) or amount_basis in {"unknown", "not_money"}:
            missing.append("amount_basis")
        if is_blank(currency):
            missing.append("currency_native")
        if is_blank(status):
            missing.append("amount_review_status")
        if missing:
            findings.append(f"row {idx} official total candidate lacks explicit unit/currency classification: {', '.join(missing)}")
    return findings


def processed_cashflows_contract_findings(rows: list[dict[str, str]]) -> list[str]:
    findings: list[str] = []
    for idx, row in enumerate(rows, start=2):
        role = lower_value(row.get("cashflow_role"))
        transaction_type = lower_value(row.get("transaction_type"))
        if role != "external_principal":
            findings.append(f"processed_cashflows row {idx} cashflow_role is not external_principal: {row.get('cashflow_role')}")
        if transaction_type in DISALLOWED_CASHFLOW_TYPES:
            findings.append(f"processed_cashflows row {idx} contains non-principal transaction_type={row.get('transaction_type')}")
        if not is_principal_cashflow_row(row):
            findings.append(
                f"processed_cashflows row {idx} is not a principal cashflow: "
                f"transaction_type={row.get('transaction_type')} ticker={row.get('ticker')} quantity={row.get('quantity')} trade_date={row.get('trade_date')}"
            )
        if is_blank(row.get("settlement_amount_krw")) and is_blank(row.get("amount_krw")):
            findings.append(f"processed_cashflows row {idx} has no KRW-normalized official amount field")
        if not is_blank(row.get("amount_native")) and row_currency(row) != "KRW" and is_blank(row.get("amount_krw")):
            findings.append(f"processed_cashflows row {idx} non-KRW principal amount lacks KRW-normalized amount")
    return findings


def fx_internal_transfer_findings(
    cashflows: list[dict[str, str]],
    transactions: list[dict[str, str]],
    fx_events: list[dict[str, str]],
    processed_dir: Path | None = None,
) -> list[str]:
    findings: list[str] = []
    cashflow_exchange_rows = [
        idx for idx, row in enumerate(cashflows, start=2)
        if lower_value(row.get("transaction_type")) == "exchange" or lower_value(row.get("cashflow_role")) == "internal_fx_exchange"
    ]
    if cashflow_exchange_rows:
        rows = ", ".join(str(idx) for idx in cashflow_exchange_rows[:5])
        findings.append(f"exchange/internal FX rows appear in processed_cashflows at rows {rows}")

    exchange_detected = any(
        lower_value(row.get("transaction_type")) == "exchange" or lower_value(row.get("cashflow_role")) == "internal_fx_exchange"
        for row in [*transactions, *cashflows]
    )
    if exchange_detected:
        fx_file_missing = processed_dir is not None and not (processed_dir / "processed_fx_events.csv").exists()
        if fx_file_missing or not fx_events:
            findings.append("exchange rows are present but processed_fx_events.csv has no FX event rows")
    return findings


def income_expense_separation_findings(
    cashflows: list[dict[str, str]],
    income: list[dict[str, str]],
    expenses: list[dict[str, str]],
) -> list[str]:
    findings: list[str] = []
    for idx, row in enumerate(cashflows, start=2):
        role = lower_value(row.get("cashflow_role"))
        transaction_type = lower_value(row.get("transaction_type"))
        if role.startswith("income_") or transaction_type in {"dividend", "interest", "distribution"}:
            findings.append(f"processed_cashflows row {idx} contains income transaction_type={row.get('transaction_type')}")
        if role.startswith("expense_") or transaction_type in {"fee", "tax"}:
            findings.append(f"processed_cashflows row {idx} contains expense transaction_type={row.get('transaction_type')}")
    for idx, row in enumerate(income, start=2):
        if boolish(row.get("affects_principal", "")):
            findings.append(f"processed_income row {idx} affects principal")
    for idx, row in enumerate(expenses, start=2):
        if boolish(row.get("affects_principal", "")):
            findings.append(f"processed_expenses row {idx} affects principal")
    return findings


def audit_representation_findings(
    rows: list[dict[str, str]],
    amount_audit: list[dict[str, str]],
    unit_mismatch_audit: list[dict[str, str]],
) -> list[str]:
    findings: list[str] = []
    audit_rows = [*amount_audit, *unit_mismatch_audit]

    def source_has_non_krw() -> bool:
        return any((currency := row_currency(row)) and currency != "KRW" for row in rows)

    def source_has_exchange() -> bool:
        return any(lower_value(row.get("transaction_type")) == "exchange" or lower_value(row.get("cashflow_role")) == "internal_fx_exchange" for row in rows)

    def source_has_income() -> bool:
        return any(
            lower_value(row.get("transaction_type")) in {"dividend", "interest", "distribution"}
            or lower_value(row.get("cashflow_role")).startswith("income_")
            or lower_value(row.get("income_type")) in {"dividend", "interest", "distribution"}
            for row in rows
        )

    def source_has_ambiguity() -> bool:
        return any(row_status(row) in AMBIGUOUS_OR_UNRESOLVED_STATUSES for row in rows)

    if source_has_non_krw() and not any((currency := row_currency(row)) and currency != "KRW" for row in audit_rows):
        findings.append("non-KRW rows are not represented in audit outputs")
    if source_has_exchange() and not any(lower_value(row.get("transaction_type")) == "exchange" or lower_value(row.get("cashflow_role")) == "internal_fx_exchange" for row in audit_rows):
        findings.append("exchange/internal FX rows are not represented in audit outputs")
    if source_has_income() and not any(
        lower_value(row.get("transaction_type")) in {"dividend", "interest", "distribution"}
        or lower_value(row.get("cashflow_role")).startswith("income_")
        for row in audit_rows
    ):
        findings.append("income rows are not represented in audit outputs")
    if source_has_ambiguity() and not any(row_status(row) in AMBIGUOUS_OR_UNRESOLVED_STATUSES for row in audit_rows):
        findings.append("ambiguous or unresolved rows are not represented in audit outputs")
    return findings


def reconciliation_summary_findings(rows: list[dict[str, str]]) -> list[str]:
    findings: list[str] = []
    metrics = {str(row.get("metric", "") or "").strip(): row.get("value", "") for row in rows}
    missing = [metric for metric in REQUIRED_RECONCILIATION_METRICS if metric not in metrics]
    if missing:
        findings.append(f"reconciliation_summary.csv missing required metrics: {', '.join(missing)}")
        return findings

    for metric in RECONCILIATION_MONEY_METRICS:
        if not is_blank(metrics.get(metric, "")) and optional_float(metrics.get(metric)) is None:
            findings.append(f"reconciliation_summary.csv metric {metric} is not numeric: {metrics.get(metric)}")
    for metric in RECONCILIATION_COUNT_METRICS:
        value = optional_float(metrics.get(metric))
        if value is None or value < 0 or value != int(value):
            findings.append(f"reconciliation_summary.csv count metric {metric} must be a non-negative integer: {metrics.get(metric)}")

    realized_cost_basis_method = str(metrics.get("realized_cost_basis_method", "") or "").strip().lower()
    if realized_cost_basis_method != REALIZED_COST_BASIS_METHOD:
        findings.append(
            f"reconciliation_summary.csv realized_cost_basis_method must be {REALIZED_COST_BASIS_METHOD}: "
            f"{metrics.get('realized_cost_basis_method')}"
        )
    realized_pnl_basis = str(metrics.get("realized_pnl_basis", "") or "").strip().lower()
    if realized_pnl_basis != REALIZED_PNL_BASIS:
        findings.append(
            f"reconciliation_summary.csv realized_pnl_basis must be {REALIZED_PNL_BASIS}: "
            f"{metrics.get('realized_pnl_basis')}"
        )
    expected_text_metrics = {
        "reconciliation_summary_role": RECONCILIATION_SUMMARY_ROLE,
        "total_return_alias_of": TOTAL_RETURN_ALIAS_OF,
        "total_return_pct_alias_of": TOTAL_RETURN_PCT_ALIAS_OF,
        "explained_profit_formula": EXPLAINED_PROFIT_FORMULA,
        "fee_tax_treatment": FEE_TAX_TREATMENT,
        "fx_pnl_treatment": FX_PNL_TREATMENT,
    }
    for metric, expected in expected_text_metrics.items():
        actual = str(metrics.get(metric, "") or "").strip()
        if actual != expected:
            findings.append(f"reconciliation_summary.csv {metric} must be {expected}: {actual}")

    if str(metrics.get("fx_pnl_status", "")).strip().lower() != "unavailable":
        findings.append("reconciliation_summary.csv fx_pnl_status must remain unavailable")

    assets = optional_float(metrics.get("total_assets_krw"))
    cash_assets = optional_float(metrics.get("current_cash_krw"))
    holding_assets = optional_float(metrics.get("current_holding_assets_krw"))
    principal = optional_float(metrics.get("net_external_principal_krw"))
    total_return = optional_float(metrics.get("total_return_krw"))
    total_return_pct = optional_float(metrics.get("total_return_pct"))
    total_assets_status = str(metrics.get("total_assets_status", "")).strip().lower()
    principal_status = str(metrics.get("net_external_principal_status", "")).strip().lower()
    total_return_status = str(metrics.get("total_return_status", "")).strip().lower()
    realized_status = str(metrics.get("realized_pnl_status", "")).strip().lower()
    explained_status = str(metrics.get("explained_profit_status", "")).strip().lower()
    residual_status = str(metrics.get("residual_status", "")).strip().lower()
    unresolved_counts = {
        metric: optional_float(metrics.get(metric))
        for metric in [
            "fx_missing_row_count",
            "currency_ambiguous_row_count",
            "unit_ambiguous_row_count",
            "amount_review_needed_row_count",
        ]
    }
    active_unresolved = [metric for metric, value in unresolved_counts.items() if value is not None and value > 0]
    if total_assets_status == "available" and assets is None:
        findings.append("reconciliation_summary.csv total_assets_status is available but total_assets_krw is blank")
    if total_assets_status == "available" and all(value is not None for value in [assets, cash_assets, holding_assets]):
        if abs(assets - (cash_assets + holding_assets)) > 0.0001:
            findings.append("reconciliation_summary.csv total_assets_krw formula mismatch")
    if principal_status == "available" and principal is None:
        findings.append("reconciliation_summary.csv net_external_principal_status is available but net_external_principal_krw is blank")
    if realized_status == "available":
        realized_pnl = optional_float(metrics.get("realized_pnl_krw"))
        realized_gross = optional_float(metrics.get("realized_trade_pnl_gross_krw"))
        realized_net = optional_float(metrics.get("realized_trade_pnl_net_krw"))
        if realized_pnl is None:
            findings.append("reconciliation_summary.csv realized_pnl_status is available but realized_pnl_krw is blank")
        if realized_gross is None:
            findings.append("reconciliation_summary.csv realized_pnl_status is available but realized_trade_pnl_gross_krw is blank")
        if realized_net is None:
            findings.append("reconciliation_summary.csv realized_pnl_status is available but realized_trade_pnl_net_krw is blank")
        if realized_pnl is not None and realized_gross is not None and abs(realized_pnl - realized_gross) > 0.0001:
            findings.append("reconciliation_summary.csv realized_pnl_krw must equal realized_trade_pnl_gross_krw")
    if total_return_status == "available":
        if active_unresolved:
            findings.append(
                "reconciliation_summary.csv total_return_status is available despite unresolved official-total rows: "
                + ", ".join(active_unresolved)
            )
        if total_assets_status != "available":
            findings.append("reconciliation_summary.csv total_return_status is available but total_assets_status is not available")
        if principal_status != "available":
            findings.append("reconciliation_summary.csv total_return_status is available but net_external_principal_status is not available")
        if assets is None or principal is None or total_return is None:
            findings.append("reconciliation_summary.csv total_return_status is available but required KRW values are blank")
        elif abs(total_return - (assets - principal)) > 0.0001:
            findings.append("reconciliation_summary.csv total_return_krw formula mismatch")
        if principal not in {None, 0.0} and total_return is not None:
            if total_return_pct is None:
                findings.append("reconciliation_summary.csv total_return_pct is blank despite available non-zero principal")
            elif abs(total_return_pct - (total_return / principal * 100)) > 0.0001:
                findings.append("reconciliation_summary.csv total_return_pct formula mismatch")
    elif residual_status == "available":
        findings.append("reconciliation_summary.csv residual_status must not be available when total_return_status is not available")

    explained_inputs = [
        "unrealized_pnl_krw",
        "realized_trade_pnl_gross_krw",
        "dividend_income_krw",
        "interest_income_krw",
        "distribution_income_krw",
        "fee_expense_krw",
        "tax_expense_krw",
    ]
    explained_values = {metric: optional_float(metrics.get(metric)) for metric in explained_inputs}
    explained = optional_float(metrics.get("explained_profit_krw"))
    if realized_status != "available" and explained_status == "available":
        findings.append("reconciliation_summary.csv explained_profit_status is available but realized_pnl_status is not available")
    if explained_status == "available" and active_unresolved:
        findings.append(
            "reconciliation_summary.csv explained_profit_status is available despite unresolved profit rows: "
            + ", ".join(active_unresolved)
        )
    if explained_status != "available" and explained is not None:
        findings.append("reconciliation_summary.csv explained_profit_krw must be blank when explained_profit_status is not available")
    if explained_status == "available" and all(value is not None for value in explained_values.values()) and explained is not None:
        expected = (
            explained_values["unrealized_pnl_krw"]
            + explained_values["realized_trade_pnl_gross_krw"]
            + explained_values["dividend_income_krw"]
            + explained_values["interest_income_krw"]
            + explained_values["distribution_income_krw"]
            - explained_values["fee_expense_krw"]
            - explained_values["tax_expense_krw"]
        )
        if abs(explained - expected) > 0.0001:
            findings.append("reconciliation_summary.csv explained_profit_krw formula mismatch")

    residual = optional_float(metrics.get("residual_krw"))
    if residual_status != "available" and residual is not None:
        findings.append("reconciliation_summary.csv residual_krw must be blank when residual_status is not available")
    if residual_status == "available":
        if total_return_status != "available":
            findings.append("reconciliation_summary.csv residual_status is available but total_return_status is not available")
        if explained_status != "available":
            findings.append("reconciliation_summary.csv residual_status is available but explained_profit_status is not available")
        if total_return is None or explained is None or residual is None:
            findings.append("reconciliation_summary.csv residual_status is available but required KRW values are blank")
        elif abs(residual - (total_return - explained)) > 0.0001:
            findings.append("reconciliation_summary.csv residual_krw formula mismatch")
    return findings


def reconciliation_summary_file_findings(processed_dir: Path) -> list[str]:
    path = processed_dir / "reconciliation_summary.csv"
    if not path.exists():
        return ["reconciliation_summary.csv is missing"]
    header = read_csv_header(path)
    missing_columns = [column for column in ["metric", "value"] if column not in header]
    if missing_columns:
        return [f"reconciliation_summary.csv missing required columns: {', '.join(missing_columns)}"]
    return reconciliation_summary_findings(read_csv_rows(path))


def metric_rows_to_map(rows: list[dict[str, str]]) -> dict[str, str]:
    return {str(row.get("metric", "") or "").strip(): row.get("value", "") for row in rows}


def performance_summary_findings(
    rows: list[dict[str, str]],
    reconciliation_rows: list[dict[str, str]] | None = None,
) -> list[str]:
    findings: list[str] = []
    metrics = metric_rows_to_map(rows)
    missing = [metric for metric in REQUIRED_PERFORMANCE_METRICS if metric not in metrics]
    if missing:
        findings.append(f"performance_summary.csv missing required metrics: {', '.join(missing)}")
        return findings

    for metric in PERFORMANCE_MONEY_METRICS:
        if not is_blank(metrics.get(metric, "")) and optional_float(metrics.get(metric)) is None:
            findings.append(f"performance_summary.csv metric {metric} is not numeric: {metrics.get(metric)}")

    count_metrics = [
        "amount_review_needed_row_count",
        "income_fx_missing_row_count",
        "fx_rate_requirement_row_count",
    ]
    amount_review_count = optional_float(metrics.get("amount_review_needed_row_count"))
    for count_metric in count_metrics:
        count_value = optional_float(metrics.get(count_metric))
        if count_value is None or count_value < 0 or count_value != int(count_value):
            findings.append(
                f"performance_summary.csv count metric {count_metric} must be a non-negative integer: "
                f"{metrics.get(count_metric)}"
            )

    deposits = optional_float(metrics.get("external_deposit_krw"))
    withdrawals = optional_float(metrics.get("external_withdrawal_krw"))
    principal = optional_float(metrics.get("net_external_principal_krw"))
    assets = optional_float(metrics.get("current_total_assets_krw"))
    cumulative_return = optional_float(metrics.get("cumulative_return_krw"))
    cumulative_return_pct = optional_float(metrics.get("cumulative_return_pct"))
    if all(value is not None for value in [deposits, withdrawals, principal]):
        if abs(principal - (deposits - withdrawals)) > 0.0001:
            findings.append("performance_summary.csv net_external_principal_krw formula mismatch")
    if assets is not None and principal is not None:
        if cumulative_return is None:
            findings.append("performance_summary.csv cumulative_return_krw is blank despite available assets and principal")
        elif abs(cumulative_return - (assets - principal)) > 0.0001:
            findings.append("performance_summary.csv cumulative_return_krw formula mismatch")
        if principal != 0 and cumulative_return is not None:
            if cumulative_return_pct is None:
                findings.append("performance_summary.csv cumulative_return_pct is blank despite available non-zero principal")
            elif abs(cumulative_return_pct - (cumulative_return / principal * 100)) > 0.0001:
                findings.append("performance_summary.csv cumulative_return_pct formula mismatch")
    elif cumulative_return is not None or cumulative_return_pct is not None:
        findings.append("performance_summary.csv cumulative return is populated despite unavailable assets or principal")

    realized_loss = optional_float(metrics.get("realized_loss_krw"))
    realized_loss_abs = optional_float(metrics.get("realized_loss_abs_krw"))
    if realized_loss is not None:
        if realized_loss_abs is None:
            findings.append("performance_summary.csv realized_loss_abs_krw is blank")
        elif abs(realized_loss_abs - abs(realized_loss)) > 0.0001:
            findings.append("performance_summary.csv realized_loss_abs_krw formula mismatch")

    income_values = [
        optional_float(metrics.get("dividend_income_krw")),
        optional_float(metrics.get("interest_income_krw")),
        optional_float(metrics.get("distribution_income_krw")),
    ]
    income_total = optional_float(metrics.get("income_total_krw"))
    if all(value is not None for value in income_values):
        expected_income_total = sum(value for value in income_values if value is not None)
        if income_total is None:
            findings.append("performance_summary.csv income_total_krw is blank despite available income components")
        elif abs(income_total - expected_income_total) > 0.0001:
            findings.append("performance_summary.csv income_total_krw formula mismatch")

    explained_inputs = [
        optional_float(metrics.get("realized_trade_pnl_gross_krw")),
        optional_float(metrics.get("unrealized_pnl_krw")),
        *income_values,
        optional_float(metrics.get("fee_expense_krw")),
        optional_float(metrics.get("tax_expense_krw")),
    ]
    realized_net = optional_float(metrics.get("realized_trade_pnl_net_krw"))
    explained = optional_float(metrics.get("explained_profit_krw"))
    if all(value is not None for value in explained_inputs):
        expected_explained = (
            explained_inputs[0]
            + explained_inputs[1]
            + explained_inputs[2]
            + explained_inputs[3]
            + explained_inputs[4]
            - explained_inputs[5]
            - explained_inputs[6]
        )
        if explained is None:
            findings.append("performance_summary.csv explained_profit_krw is blank despite available components")
        elif abs(explained - expected_explained) > 0.0001:
            findings.append("performance_summary.csv explained_profit_krw formula mismatch")
        if realized_net is not None and explained is not None:
            expected_double_count = (
                realized_net
                + explained_inputs[1]
                + explained_inputs[2]
                + explained_inputs[3]
                + explained_inputs[4]
                - explained_inputs[5]
                - explained_inputs[6]
            )
            if abs(explained - expected_double_count) <= 0.0001 and abs(expected_explained - expected_double_count) > 0.0001:
                findings.append("performance_summary.csv explained_profit_krw appears to double-count fee/tax by using net realized PnL and subtracting fee/tax again")

    residual = optional_float(metrics.get("reconciliation_residual_krw"))
    if cumulative_return is not None and explained is not None:
        if residual is None:
            findings.append("performance_summary.csv reconciliation_residual_krw is blank despite available cumulative return and explained profit")
        elif abs(residual - (cumulative_return - explained)) > 0.0001:
            findings.append("performance_summary.csv reconciliation_residual_krw formula mismatch")

    performance_status = lower_value(metrics.get("performance_status"))
    realized_status = lower_value(metrics.get("realized_pnl_status"))
    income_status = lower_value(metrics.get("income_status"))
    fx_status = lower_value(metrics.get("fx_status"))
    income_fx_status = lower_value(metrics.get("income_fx_status"))
    if is_blank(performance_status):
        findings.append("performance_summary.csv performance_status is blank")
    if performance_status == "available":
        blocking = []
        if cumulative_return is None:
            blocking.append("cumulative_return_krw")
        for label, status in [
            ("realized_pnl_status", realized_status),
            ("income_status", income_status),
            ("fx_status", fx_status),
            ("income_fx_status", income_fx_status),
        ]:
            if status and status != "available":
                blocking.append(label)
        if amount_review_count is not None and amount_review_count > 0:
            blocking.append("amount_review_needed_row_count")
        if blocking:
            findings.append("performance_summary.csv performance_status is available despite unresolved inputs: " + ", ".join(blocking))

    if reconciliation_rows:
        reconciliation = metric_rows_to_map(reconciliation_rows)
        total_assets_status = lower_value(reconciliation.get("total_assets_status"))
        if total_assets_status and total_assets_status != "available":
            for perf_metric in [
                "current_total_assets_krw",
                "current_cash_krw",
                "current_holding_assets_krw",
                "unrealized_pnl_krw",
            ]:
                if optional_float(metrics.get(perf_metric)) is not None:
                    findings.append(
                        f"performance_summary.csv {perf_metric} must be blank when reconciliation_summary.csv total_assets_status is {total_assets_status}"
                    )
        mapping = {
            "current_total_assets_krw": "total_assets_krw",
            "cumulative_return_krw": "total_return_krw",
            "cumulative_return_pct": "total_return_pct",
            "reconciliation_residual_krw": "residual_krw",
        }
        for perf_metric, rec_metric in mapping.items():
            perf_value = optional_float(metrics.get(perf_metric))
            rec_value = optional_float(reconciliation.get(rec_metric))
            if perf_value is not None and rec_value is not None and abs(perf_value - rec_value) > 0.0001:
                findings.append(f"performance_summary.csv {perf_metric} does not match reconciliation_summary.csv {rec_metric}")
    return findings


def performance_summary_file_findings(processed_dir: Path) -> list[str]:
    path = processed_dir / "performance_summary.csv"
    if not path.exists():
        return ["performance_summary.csv is missing"]
    header = read_csv_header(path)
    missing_columns = [column for column in ["metric", "value"] if column not in header]
    if missing_columns:
        return [f"performance_summary.csv missing required columns: {', '.join(missing_columns)}"]
    return performance_summary_findings(read_csv_rows(path), read_csv_rows(processed_dir / "reconciliation_summary.csv"))


def money_event_contract_findings(rows: list[dict[str, str]], label: str, type_col: str, allowed_types: set[str]) -> list[str]:
    findings: list[str] = []
    for idx, row in enumerate(rows, start=2):
        event_type = str(row.get(type_col, "") or "").strip().lower()
        if event_type not in allowed_types:
            findings.append(f"{label} row {idx} invalid {type_col}={row.get(type_col)}")
        if boolish(row.get("affects_principal", "")):
            findings.append(f"{label} row {idx} affects principal")
        if not boolish(row.get("affects_profit", "")):
            findings.append(f"{label} row {idx} does not affect profit")
        status = str(row.get("amount_review_status", "") or "").strip().lower()
        if is_blank(status):
            findings.append(f"{label} row {idx} has blank amount_review_status")
        currency = str(row.get("currency_native", "") or "").strip().upper()
        amount_native = row.get("amount_native", "")
        amount_krw = row.get("amount_krw", "")
        if status == "ok" and not is_blank(amount_native) and is_blank(amount_krw):
            findings.append(f"{label} row {idx} has status ok but blank amount_krw")
        if currency and currency != "KRW" and not is_blank(amount_native) and is_blank(amount_krw) and status != "fx_missing":
            findings.append(f"{label} row {idx} non-KRW amount without KRW conversion is not marked fx_missing")
    return findings


def income_contract_findings(rows: list[dict[str, str]]) -> list[str]:
    return money_event_contract_findings(rows, "processed_income", "income_type", {"dividend", "interest", "distribution"})


def expense_contract_findings(rows: list[dict[str, str]]) -> list[str]:
    return money_event_contract_findings(rows, "processed_expenses", "expense_type", {"fee", "tax"})


def fx_event_contract_findings(rows: list[dict[str, str]]) -> list[str]:
    findings: list[str] = []
    allowed_pair_statuses = {"paired", "partial", "unpaired", "needs_review", ""}
    paired_groups: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for idx, row in enumerate(rows, start=2):
        if boolish(row.get("affects_principal", "")):
            findings.append(f"processed_fx_events row {idx} affects principal")
        if boolish(row.get("affects_profit", "")):
            findings.append(f"processed_fx_events row {idx} affects profit")
        role = str(row.get("cashflow_role", "") or "").strip().lower()
        if role != "internal_fx_exchange" and not boolish(row.get("is_internal_transfer", "")):
            findings.append(f"processed_fx_events row {idx} is not marked as an internal FX transfer")
        pair_status = str(row.get("fx_pair_status", "") or "").strip().lower()
        if pair_status not in allowed_pair_statuses:
            findings.append(f"processed_fx_events row {idx} invalid fx_pair_status={row.get('fx_pair_status')}")
        if not is_blank(row.get("amount_native", "")) and is_blank(row.get("amount_review_status", "")):
            findings.append(f"processed_fx_events row {idx} has amount_native but blank amount_review_status")
        if pair_status == "paired" and is_blank(row.get("fx_event_id", "")):
            findings.append(f"processed_fx_events row {idx} paired leg has blank fx_event_id")
        if pair_status == "paired":
            event_id = str(row.get("fx_event_id", "") or "").strip()
            paired_groups.setdefault(event_id, []).append((idx, row))
    for event_id, group in sorted(paired_groups.items()):
        label = event_id or "<blank>"
        row_numbers = ", ".join(str(idx) for idx, _ in group)
        if len(group) != 2:
            findings.append(f"processed_fx_events paired fx_event_id={label} has {len(group)} rows; expected exactly 2 rows (rows {row_numbers})")
        currencies = [str(row.get("currency_native", "") or "").strip().upper() for _, row in group]
        krw_count = sum(1 for currency in currencies if currency == "KRW")
        non_krw_count = sum(1 for currency in currencies if currency and currency != "KRW")
        if krw_count != 1 or non_krw_count != 1:
            findings.append(f"processed_fx_events paired fx_event_id={label} must have one KRW leg and one non-KRW leg; currencies={currencies}")
        for idx, row in group:
            if str(row.get("cashflow_role", "") or "").strip().lower() != "internal_fx_exchange":
                findings.append(f"processed_fx_events paired fx_event_id={label} row {idx} cashflow_role is not internal_fx_exchange")
            if not boolish(row.get("is_internal_transfer", "")):
                findings.append(f"processed_fx_events paired fx_event_id={label} row {idx} is_internal_transfer is not true")
            if boolish(row.get("affects_principal", "")):
                findings.append(f"processed_fx_events paired fx_event_id={label} row {idx} affects principal")
            if boolish(row.get("affects_profit", "")):
                findings.append(f"processed_fx_events paired fx_event_id={label} row {idx} affects profit")
    return findings


def is_overseas_holding_row(row: dict[str, str]) -> bool:
    return is_overseas_position_row(row)


def duplicate_overseas_holding_findings(holdings: list[dict[str, str]]) -> list[str]:
    if not holdings:
        return []
    original = pd.DataFrame(holdings)
    deduped = dedupe_holdings(original)
    if len(deduped) == len(original):
        by_key: dict[str, set[str]] = {}
        key_rows: dict[str, list[dict[str, str]]] = {}
        for row in holdings:
            if not is_overseas_holding_row(row):
                continue
            key = canonical_overseas_position_key(row)
            if is_blank(key):
                continue
            by_key.setdefault(key, set()).add(str(row.get("source_file_type", "")))
            key_rows.setdefault(key, []).append(row)
        return [
            f"{key} appears in both holdings and overseas_balance"
            for key, source_types in sorted(by_key.items())
            if {"holdings", "overseas_balance"}.issubset(source_types)
            and all(is_blank(row.get("balance_quantity", "")) and is_blank(row.get("evaluation_amount", "")) for row in key_rows.get(key, []))
        ]

    before_counts: dict[str, int] = {}
    after_counts: dict[str, int] = {}
    for _, row in original.iterrows():
        key = canonical_overseas_position_key(row)
        if key:
            before_counts[key] = before_counts.get(key, 0) + 1
    for _, row in deduped.iterrows():
        key = canonical_overseas_position_key(row)
        if key:
            after_counts[key] = after_counts.get(key, 0) + 1
    return [
        f"{key} has {before_counts[key] - after_counts.get(key, 0)} duplicate row(s) excluded by source priority"
        for key in sorted(before_counts)
        if before_counts[key] > after_counts.get(key, 0)
    ]


def cash_company_qa_findings(processed_dir: Path, holdings: list[dict[str, str]]) -> list[str]:
    cash_tickers = {
        str(row.get("ticker", "")).strip().upper()
        for row in holdings
        if str(row.get("asset_type", "")).strip().lower() == "cash" and not is_blank(row.get("ticker", ""))
    }
    if not cash_tickers:
        return []

    findings: list[str] = []
    qa_rows = read_csv_rows(processed_dir / "qa_exceptions.csv")
    for idx, row in enumerate(qa_rows, start=2):
        if row.get("exception_id") not in COMPANY_QA_EXCEPTION_IDS:
            continue
        text = " ".join(str(value).upper() for value in row.values())
        matches = sorted(ticker for ticker in cash_tickers if ticker and ticker in text)
        if matches:
            findings.append(f"qa_exceptions row {idx} reports Company QA for cash ticker(s): {', '.join(matches)}")

    review_rows = read_csv_rows(processed_dir / "review_queue.csv")
    for idx, row in enumerate(review_rows, start=2):
        reason = str(row.get("reason", "")).lower()
        if reason not in {"thesis missing", "sell criteria missing"}:
            continue
        ticker = str(row.get("ticker", "")).strip().upper()
        if ticker in cash_tickers:
            findings.append(f"review_queue row {idx} reports Company review for cash ticker: {ticker}")
    return findings


def skipped_rows_findings(processed_dir: Path, unclassified_rows: list[dict[str, str]]) -> list[str]:
    findings = [
        f"unclassified_rows row {idx} matches broker helper skip pattern"
        for idx, row in enumerate(unclassified_rows, start=2)
        if is_overseas_cashflow_amount_only_helper_row(row)
    ]

    skipped_rows = read_csv_rows(processed_dir / "skipped_rows.csv")
    for idx, row in enumerate(skipped_rows, start=2):
        if is_blank(row.get("skip_reason", "")):
            findings.append(f"skipped_rows row {idx} has blank skip_reason")
    return findings


def active_company_note_targets(vault_root: Path, processed_dir: Path | None = None) -> dict[str, set[str]]:
    """Return active Company note paths keyed by normalized holding identity."""
    processed_dir = processed_dir or vault_root / "70_Imports" / "processed"
    holdings = read_csv_rows(processed_dir / "processed_holdings.csv")
    if not holdings:
        return {}
    company_root = vault_root / "20_Companies"
    note_index = existing_company_note_index(company_root)
    targets: dict[str, set[str]] = {}
    for row in holdings:
        asset_type = str(row.get("asset_type", "") or "").strip().lower()
        ticker = str(row.get("ticker", "") or "").strip()
        if asset_type == "cash" or is_blank(ticker):
            continue
        identity = company_note_identity_key(row)
        if not identity:
            continue
        expected_path = company_root / safe_component(ticker) / "Company.md"
        path = expected_path
        if not path.exists():
            path = (
                note_index.get(identity)
                or note_index.get(f"TICKER:{ticker.upper()}")
                or expected_path
            )
        targets.setdefault(identity, set()).add(str(path.relative_to(vault_root)))
    return targets


def company_note_duplicate_findings(vault_root: Path, processed_dir: Path | None = None) -> list[str]:
    company_root = vault_root / "20_Companies"
    if not company_root.exists():
        return []
    active_targets = active_company_note_targets(vault_root, processed_dir)
    by_key: dict[str, list[Path]] = {}
    for path in sorted(company_root.glob("*/Company.md")):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception:
            continue
        meta = parse_note_frontmatter(text)
        row = {
            "ticker": meta.get("ticker", "") or path.parent.name,
            "security_name": meta.get("name", ""),
            "market": meta.get("market", ""),
            "asset_type": meta.get("asset_type", ""),
        }
        key = company_note_identity_key(row)
        if not key:
            continue
        rel = str(path.relative_to(vault_root))
        if key in active_targets and rel not in active_targets[key]:
            continue
        by_key.setdefault(key, []).append(path)
    return [
        f"{key} has {len(paths)} Company notes"
        for key, paths in sorted(by_key.items())
        if len(paths) > 1
    ]


def check_vault_local_venv(vault_root: Path, results: list[GateResult]) -> None:
    venv_path = vault_root / ".venv"
    if venv_path.exists():
        write_result(results, "vault-root .venv guard", "WARN", f"{venv_path} exists; wrappers now default to an OS-local venv outside Vault/Drive.")
    else:
        write_result(results, "vault-root .venv guard", "PASS", "no .venv exists at vault root.")


def live_vault_actual_write_guard_findings(vault_root: Path) -> list[str]:
    fake_live_vault = vault_root / ".quality_gate_fake_live_vault"
    fake_live_child = fake_live_vault / "70_Imports" / "scripts"
    live_roots = (fake_live_vault,)
    blocked_args = pipeline_main.build_parser().parse_args(["all", "--vault-root", str(fake_live_child)])
    blocked_findings = pipeline_main.live_write_guard_findings(blocked_args, fake_live_child, live_roots=live_roots)
    required_findings = {
        "missing --live-baseline-updated",
        "missing --live-tests-passed",
        "missing --live-quality-gate-passed",
        "missing --live-dry-run-reviewed",
        "missing --live-expected-changes-reviewed",
        f"missing --live-write-confirmation {pipeline_main.LIVE_WRITE_CONFIRMATION_TOKEN}",
    }

    findings: list[str] = []
    missing_findings = sorted(required_findings.difference(blocked_findings))
    if missing_findings:
        findings.append("unguarded live write did not report: " + ", ".join(missing_findings))

    dry_run_args = pipeline_main.build_parser().parse_args(["all", "--vault-root", str(fake_live_child), "--dry-run"])
    if pipeline_main.live_write_guard_findings(dry_run_args, fake_live_child, live_roots=live_roots):
        findings.append("live dry-run was blocked")

    confirmed_args = pipeline_main.build_parser().parse_args([
        "all",
        "--vault-root",
        str(fake_live_child),
        "--live-baseline-updated",
        "--live-tests-passed",
        "--live-quality-gate-passed",
        "--live-dry-run-reviewed",
        "--live-expected-changes-reviewed",
        "--live-write-confirmation",
        pipeline_main.LIVE_WRITE_CONFIRMATION_TOKEN,
    ])
    confirmed_findings = pipeline_main.live_write_guard_findings(confirmed_args, fake_live_child, live_roots=live_roots)
    if confirmed_findings:
        findings.append("fully attested live write was blocked: " + ", ".join(confirmed_findings))

    return findings


def check_processed_integrity(vault_root: Path, results: list[GateResult]) -> None:
    processed_dir = vault_root / "70_Imports" / "processed"
    raw_dir = vault_root / "70_Imports" / "raw"
    source_index = read_csv_rows(processed_dir / "source_file_index.csv")
    transactions = read_csv_rows(processed_dir / "processed_transactions.csv")
    holdings = read_csv_rows(processed_dir / "processed_holdings.csv")
    cashflows = read_csv_rows(processed_dir / "processed_cashflows.csv")
    income = read_csv_rows(processed_dir / "processed_income.csv")
    income_summary = read_csv_rows(processed_dir / "income_summary.csv")
    fx_requirements = read_csv_rows(processed_dir / "fx_rate_requirements.csv")
    expenses = read_csv_rows(processed_dir / "processed_expenses.csv")
    fx_events = read_csv_rows(processed_dir / "processed_fx_events.csv")
    realized = read_csv_rows(processed_dir / "processed_realized_pnl.csv")
    amount_audit = read_csv_rows(processed_dir / "amount_unit_audit.csv")
    unit_mismatch_audit = read_csv_rows(processed_dir / "unit_mismatch_audit.csv")
    unclassified_rows = read_csv_rows(processed_dir / "unclassified_rows.csv")
    summary = summary_map(processed_dir)

    output_schema_findings = processed_output_schema_findings(processed_dir)
    if output_schema_findings:
        write_result(results, "income/expense/FX output schema contract", "FAIL", "; ".join(output_schema_findings[:5]))
    else:
        write_result(results, "income/expense/FX output schema contract", "PASS", "required output files exist with expected columns.")

    audit_schema_findings = audit_output_schema_findings(processed_dir)
    if audit_schema_findings:
        write_result(results, "amount/unit audit output contract", "FAIL", "; ".join(audit_schema_findings[:5]))
    else:
        write_result(results, "amount/unit audit output contract", "PASS", "audit output files exist with expected columns.")

    reconciliation_findings = reconciliation_summary_file_findings(processed_dir)
    if reconciliation_findings:
        write_result(results, "reconciliation_summary metric contract", "FAIL", "; ".join(reconciliation_findings[:5]))
    else:
        write_result(results, "reconciliation_summary metric contract", "PASS", "required reconciliation metrics exist and formulas/statuses are guarded.")

    performance_findings = performance_summary_file_findings(processed_dir)
    if performance_findings:
        write_result(results, "performance_summary metric contract", "FAIL", "; ".join(performance_findings[:5]))
    else:
        write_result(results, "performance_summary metric contract", "PASS", "required performance metrics exist and formulas/statuses are guarded.")

    income_summary_findings = income_summary_contract_findings(income_summary, income)
    if income_summary_findings:
        write_result(results, "income_summary cash income contract", "FAIL", "; ".join(income_summary_findings[:5]))
    else:
        write_result(results, "income_summary cash income contract", "PASS", f"{len(income_summary)} income summary rows preserve native amounts and use status-ok KRW totals.")

    fx_requirement_findings = fx_rate_requirements_findings(fx_requirements)
    if fx_requirement_findings:
        write_result(results, "fx_rate_requirements output contract", "FAIL", "; ".join(fx_requirement_findings[:5]))
    else:
        write_result(results, "fx_rate_requirements output contract", "PASS", f"{len(fx_requirements)} FX requirement rows identify missing historical rates.")

    income_reversal_findings = income_reversal_review_findings(income)
    if income_reversal_findings:
        write_result(results, "income reversal/refund review", "WARN", "; ".join(income_reversal_findings[:5]))
    else:
        write_result(results, "income reversal/refund review", "PASS", "no negative or reversal-like income rows detected.")

    realized_cost_basis_findings = realized_pnl_cost_basis_findings(realized)
    if realized_cost_basis_findings:
        write_result(results, "realized PnL ledger FIFO/gross-net contract", "FAIL", "; ".join(realized_cost_basis_findings[:5]))
    else:
        write_result(
            results,
            "realized PnL ledger FIFO/gross-net contract",
            "PASS",
            f"{len(realized)} processed_realized_pnl.csv ledger rows use FIFO cost basis and gross/net formula guards or no rows are present.",
        )

    realized_review_findings = realized_pnl_review_findings(realized)
    if realized_review_findings:
        write_result(results, "realized PnL ledger review statuses", "WARN", "; ".join(realized_review_findings[:5]))
    else:
        write_result(results, "realized PnL ledger review statuses", "PASS", "no realized PnL ledger rows require amount/FX review.")

    official_krw_provenance = official_krw_total_provenance_findings(holdings, realized)
    if official_krw_provenance:
        write_result(results, "official KRW total provenance", "FAIL", "; ".join(official_krw_provenance[:5]))
    else:
        write_result(results, "official KRW total provenance", "PASS", "non-KRW official KRW totals have FX or broker status/provenance.")

    if not source_index:
        if not raw_excel_files(raw_dir):
            write_result(results, "processed/source_file_index.csv", "PASS", "no raw broker Excel files present in clean baseline; processed integrity checks skipped.")
            return
        write_result(results, "processed/source_file_index.csv", "FAIL", "source_file_index.csv is missing or empty.")
        return

    source_types = [row.get("source_file_type", "") for row in source_index]
    transaction_file_count = sum(1 for value in source_types if value in TRANSACTION_SOURCE_TYPES)
    holdings_file_count = sum(1 for value in source_types if value in BALANCE_SOURCE_TYPES)
    write_result(results, "source type split", "PASS", f"transaction_history={transaction_file_count}, holdings={holdings_file_count}")

    bad_transaction_values = []
    for idx, row in enumerate(transactions, start=2):
        if row.get("source_file_type") in {"transaction_history", "transactions"}:
            for field in ["balance_quantity", "evaluation_amount", "unrealized_pnl", "pnl_pct"]:
                if not is_blank(row.get(field, "")):
                    bad_transaction_values.append(f"row {idx} {field}={row.get(field)}")
                    break
    if bad_transaction_values:
        write_result(results, "transaction rows do not carry balance metrics", "FAIL", "; ".join(bad_transaction_values[:5]))
    else:
        write_result(results, "transaction rows do not carry balance metrics", "PASS", "transaction_history rows keep balance/evaluation/pnl fields blank.")

    bad_holding_rows = []
    for idx, row in enumerate(holdings, start=2):
        if row.get("source_file_type") not in BALANCE_SOURCE_TYPES:
            bad_holding_rows.append(f"row {idx} source_file_type={row.get('source_file_type')}")
            continue
        balance = float(row.get("balance_quantity") or 0)
        evaluation = float(row.get("evaluation_amount") or 0)
        if abs(balance) <= 1e-9 and abs(evaluation) <= 1e-9:
            bad_holding_rows.append(f"row {idx} has no current position signal")
    if bad_holding_rows:
        write_result(results, "processed_holdings current-only contract", "FAIL", "; ".join(bad_holding_rows[:5]))
    else:
        write_result(results, "processed_holdings current-only contract", "PASS", f"{len(holdings)} current holding rows.")

    duplicate_overseas = duplicate_overseas_holding_findings(holdings)
    if duplicate_overseas:
        write_result(results, "duplicate overseas holdings guard", "FAIL", "; ".join(duplicate_overseas[:5]))
    else:
        write_result(results, "duplicate overseas holdings guard", "PASS", "no holdings/overseas_balance overlap detected in processed_holdings.")

    invalid_currencies = invalid_currency_findings(holdings)
    if invalid_currencies:
        write_result(results, "processed_holdings currency code contract", "FAIL", "; ".join(invalid_currencies[:5]))
    else:
        write_result(results, "processed_holdings currency code contract", "PASS", "currency values are 3-letter codes.")

    all_normalized_rows = [*transactions, *holdings, *cashflows, *income, *expenses, *fx_events]
    all_currency_rows = [*all_normalized_rows, *amount_audit, *unit_mismatch_audit]
    invalid_normalized_currencies = invalid_currency_findings(all_currency_rows)
    if invalid_normalized_currencies:
        write_result(results, "normalized currency unit contract", "FAIL", "; ".join(invalid_normalized_currencies[:5]))
    else:
        write_result(results, "normalized currency unit contract", "PASS", "currency and currency_native values are 3-letter codes.")

    non_krw_without_fx = non_krw_amount_without_fx_findings(all_normalized_rows)
    if non_krw_without_fx:
        write_result(results, "non-KRW amount KRW conversion provenance", "FAIL", "; ".join(non_krw_without_fx[:5]))
    else:
        write_result(results, "non-KRW amount KRW conversion provenance", "PASS", "non-KRW amount_krw values have FX or broker KRW source.")

    unit_classification = unit_classification_findings([*all_normalized_rows, *amount_audit])
    if unit_classification:
        write_result(results, "official amount unit classification contract", "FAIL", "; ".join(unit_classification[:5]))
    else:
        write_result(results, "official amount unit classification contract", "PASS", "official amount candidates carry unit, currency, role, and review status.")

    cash_qa_findings = cash_company_qa_findings(processed_dir, holdings)
    if cash_qa_findings:
        write_result(results, "cash assets excluded from Company QA", "FAIL", "; ".join(cash_qa_findings[:5]))
    else:
        write_result(results, "cash assets excluded from Company QA", "PASS", "no cash ticker appears in Company thesis/sell-criteria QA.")

    cashflow_contract = processed_cashflows_contract_findings(cashflows)
    if cashflow_contract:
        write_result(results, "processed_cashflows principal-only contract", "FAIL", "; ".join(cashflow_contract[:5]))
    else:
        write_result(results, "processed_cashflows principal-only contract", "PASS", f"{len(cashflows)} principal cashflow rows.")

    principal_unit_misuse = principal_unit_misuse_findings(cashflows)
    if principal_unit_misuse:
        write_result(results, "principal cashflow amount unit contract", "FAIL", "; ".join(principal_unit_misuse[:5]))
    else:
        write_result(results, "principal cashflow amount unit contract", "PASS", "principal cashflows do not use quantity or unit price as amount.")

    separation_findings = income_expense_separation_findings(cashflows, income, expenses)
    if separation_findings:
        write_result(results, "income/expense separation from principal", "FAIL", "; ".join(separation_findings[:5]))
    else:
        write_result(results, "income/expense separation from principal", "PASS", "income and expense rows are outside processed_cashflows and do not affect principal.")

    income_findings = income_contract_findings(income)
    if income_findings:
        write_result(results, "processed_income non-principal contract", "FAIL", "; ".join(income_findings[:5]))
    else:
        write_result(results, "processed_income non-principal contract", "PASS", f"{len(income)} income rows do not affect principal.")

    expense_findings = expense_contract_findings(expenses)
    if expense_findings:
        write_result(results, "processed_expenses non-principal contract", "FAIL", "; ".join(expense_findings[:5]))
    else:
        write_result(results, "processed_expenses non-principal contract", "PASS", f"{len(expenses)} expense rows do not affect principal.")

    fx_findings = fx_event_contract_findings(fx_events)
    if fx_findings:
        write_result(results, "processed_fx_events internal-transfer contract", "FAIL", "; ".join(fx_findings[:5]))
    else:
        write_result(results, "processed_fx_events internal-transfer contract", "PASS", f"{len(fx_events)} FX event legs are internal transfers.")

    fx_transfer_findings = fx_internal_transfer_findings(cashflows, transactions, fx_events, processed_dir)
    if fx_transfer_findings:
        write_result(results, "FX exchange internal-transfer separation", "FAIL", "; ".join(fx_transfer_findings[:5]))
    else:
        write_result(results, "FX exchange internal-transfer separation", "PASS", "exchange rows stay out of processed_cashflows and are surfaced through FX events when present.")

    audit_representation = audit_representation_findings(all_normalized_rows, amount_audit, unit_mismatch_audit)
    if audit_representation:
        write_result(results, "audit output representation contract", "FAIL", "; ".join(audit_representation[:5]))
    else:
        write_result(results, "audit output representation contract", "PASS", "non-KRW, exchange, income, and unresolved rows are represented in audit outputs when present.")

    skip_findings = skipped_rows_findings(processed_dir, unclassified_rows)
    if skip_findings:
        write_result(results, "broker helper skipped rows contract", "FAIL", "; ".join(skip_findings[:5]))
    else:
        write_result(results, "broker helper skipped rows contract", "PASS", "amount-only broker helper rows are skipped with non-empty reasons.")

    company_note_duplicates = company_note_duplicate_findings(vault_root)
    if company_note_duplicates:
        write_result(results, "Company note semantic duplicate guard", "FAIL", "; ".join(company_note_duplicates[:5]))
    else:
        write_result(results, "Company note semantic duplicate guard", "PASS", "no semantic duplicate Company notes found.")

    if holdings_file_count == 0:
        checks = {
            "processed_holdings empty": len(holdings) == 0,
            "balance_data_available false": summary.get("balance_data_available", "").lower() == "false",
            "total_portfolio_value_status unknown": summary.get("total_portfolio_value_status", "") == "unknown",
            "total_portfolio_value blank": is_blank(summary.get("total_portfolio_value", "")),
        }
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            write_result(results, "no balance file contract", "FAIL", ", ".join(failed))
        else:
            write_result(results, "no balance file contract", "PASS", "holdings unavailable and portfolio value status is unknown.")
    elif summary.get("total_portfolio_value_status") == "available":
        write_result(results, "balance file contract", "PASS", "balance files present and portfolio summary is available.")
    else:
        write_result(results, "balance file contract", "FAIL", f"unexpected status={summary.get('total_portfolio_value_status')}")


def quality_gate(vault_root: Path) -> int:
    scripts_dir = vault_root / "70_Imports" / "scripts"
    raw_dir = vault_root / "70_Imports" / "raw"
    results: list[GateResult] = []

    raw_before = snapshot_raw_files(raw_dir)
    md_before = snapshot_markdown_outside_auto(vault_root)

    check_vault_local_venv(vault_root, results)

    live_guard_findings = live_vault_actual_write_guard_findings(vault_root)
    if live_guard_findings:
        write_result(results, "live vault actual-write guard", "FAIL", "; ".join(live_guard_findings))
    else:
        write_result(results, "live vault actual-write guard", "PASS", "actual live writes require baseline/test/quality-gate/dry-run/review flags and confirmation token.")

    command = [sys.executable, "main.py", "all", "--vault-root", "../..", "--raw-dir", "../raw"]
    code, output = run_command(command, scripts_dir)
    if code == 0:
        detail = output.strip().splitlines()[-1] if output.strip() else "completed"
        write_result(results, "python main.py all --vault-root ../.. --raw-dir ../raw", "PASS", detail)
    else:
        write_result(results, "python main.py all --vault-root ../.. --raw-dir ../raw", "FAIL", output.strip())

    pytest_command = [sys.executable, "-m", "pytest", "tests", "-p", "no:cacheprovider"]
    code, output = run_command(pytest_command, scripts_dir)
    if code == 0:
        detail = output.strip().splitlines()[-1] if output.strip() else "pytest completed"
        write_result(results, "pytest", "PASS", detail)
    else:
        write_result(results, "pytest", "FAIL", output.strip())

    raw_changes = changed_entries(raw_before, snapshot_raw_files(raw_dir))
    if raw_changes:
        write_result(results, "raw immutable mtime/size", "FAIL", "; ".join(raw_changes[:10]))
    else:
        write_result(results, "raw immutable mtime/size", "PASS", f"{len(raw_before)} raw files unchanged.")

    md_changes = changed_entries(md_before, snapshot_markdown_outside_auto(vault_root))
    if md_changes:
        write_result(results, "AUTO-GENERATED outside-block guard", "FAIL", "; ".join(md_changes[:10]))
    else:
        write_result(results, "AUTO-GENERATED outside-block guard", "PASS", "pre-existing Markdown outside AUTO-GENERATED blocks unchanged.")

    check_processed_integrity(vault_root, results)

    sensitive_findings = scan_generated_markdown_sensitive(vault_root)
    if sensitive_findings:
        write_result(results, "generated Markdown sensitive scan", "FAIL", "; ".join(sensitive_findings[:10]))
    else:
        write_result(results, "generated Markdown sensitive scan", "PASS", "no sensitive-data candidates in AUTO-GENERATED blocks.")
    label_findings = dashboard_return_label_findings(vault_root)
    if label_findings:
        write_result(results, "Portfolio dashboard return label contract", "FAIL", "; ".join(label_findings[:5]))
    else:
        write_result(results, "Portfolio dashboard return label contract", "PASS", "Portfolio dashboard does not use legacy ambiguous return/cost labels.")

    final_status = worst_status(results)
    print(f"[{final_status}] quality_gate: {len(results)} checks completed.")
    return 1 if final_status == "FAIL" else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="06_Stock development quality gate")
    parser.add_argument("--vault-root", default=str(repo_root_from_script()), help="06_Stock vault root")
    args = parser.parse_args()
    return quality_gate(Path(args.vault_root).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
