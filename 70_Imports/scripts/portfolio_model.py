from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from nh_importer import FX_RATE_REQUIREMENT_COLUMNS, NORMALIZED_COLUMNS, is_leveraged_etf_name, remove_overlapping_overseas_holdings

HISTORY_COLUMNS = [
    "import_id", "source_file", "source_file_type", "account_type", "market", "asset_type",
    "ticker", "security_name", "trade_date", "currency", "fx_rate", "balance_quantity", "evaluation_amount",
    "unrealized_pnl", "pnl_pct", "weight_pct", "history_reason", "suggested_destination", "suggested_action",
]

RISK_COLUMNS = ["ticker", "security_name", "account_type", "risk_flags", "pnl_pct", "weight_pct", "suggested_action"]
REVIEW_COLUMNS = ["ticker", "security_name", "reason", "severity", "suggested_action"]
SUMMARY_COLUMNS = ["metric", "value"]
RECONCILIATION_SUMMARY_COLUMNS = ["metric", "value"]
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
INCOME_TYPES = ["dividend", "interest", "distribution"]
INCOME_SUMMARY_COLUMNS = [
    "income_type",
    "currency_native",
    "amount_native_sum",
    "amount_krw_sum",
    "tax_native_sum",
    "tax_krw_sum",
    "net_income_native",
    "net_income_krw",
    "row_count",
    "fx_missing_row_count",
    "amount_review_needed_row_count",
    "fx_status_summary",
    "fx_source_summary",
    "income_status",
]
FX_RATES_COLUMNS = [
    "effective_date",
    "base_currency",
    "quote_currency",
    "rate",
    "source_type",
    "provider",
    "use_case",
    "status",
    "source_note",
]
PERFORMANCE_SUMMARY_METRICS = [
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
MONTHLY_CASHFLOW_SUMMARY_COLUMNS = [
    "month",
    "external_deposit_krw",
    "external_withdrawal_krw",
    "net_principal_flow_krw",
    "cumulative_principal_krw",
]
PERFORMANCE_HISTORY_COLUMNS = [
    "snapshot_month",
    "snapshot_date",
    "cumulative_principal_krw",
    "current_total_assets_krw",
    "cumulative_return_krw",
    "cumulative_return_pct",
    "performance_status",
]
REALIZED_PNL_COLUMNS = [
    "account_type",
    "market",
    "ticker",
    "security_name",
    "currency_native",
    "sell_date",
    "sell_import_id",
    "quantity_sold",
    "proceeds_native",
    "proceeds_krw",
    "cost_basis_native",
    "cost_basis_krw",
    "fee_native",
    "fee_krw",
    "tax_native",
    "tax_krw",
    "realized_trade_pnl_gross_native",
    "realized_trade_pnl_gross_krw",
    "realized_trade_pnl_net_native",
    "realized_trade_pnl_net_krw",
    "realized_result",
    "position_status",
    "cost_basis_method",
    "amount_review_status",
    "fx_status",
    "amount_review_reason",
    "source_file",
]
BALANCE_SOURCE_TYPES = {"holdings", "overseas_balance"}
REVIEW_NEEDED_STATUSES = {"fx_missing", "partial", "needs_review", "currency_ambiguous", "unit_ambiguous", "unclassified", "lot_missing"}
BROKER_KRW_SOURCES = {"broker_krw", "broker_provided_krw", "broker_krw_amount"}
RAW_FX_SOURCES = {"", "raw", "broker_raw", "broker_raw_fx", "fx_rate_to_krw"}
LOCAL_FX_SOURCE_TYPES = {"local", "manual", "user_provided", "fx_rates_csv"}
API_CACHED_FX_SOURCE_TYPES = {"api_cached", "cached_api", "api_archive", "archived_api"}
USABLE_FX_RATE_STATUSES = {"active", "approved", "available", "cached", "archived", "official", "ok", "verified"}
CURRENCY_NORMALIZATION_STATUS = "pending"
AMOUNT_UNIT_CLASSIFICATION_STATUS = "pending"
PROFIT_RESULT_STATUS = "preliminary"
RECONCILIATION_STATUS = "currency_normalization_pending"
PRELIMINARY_RECONCILIATION_WARNING = (
    "Portfolio/Cashflows differences are not official reconciliation yet. "
    "Raw numeric values may mix KRW and USD. "
    "Raw numeric values may also mix quantity, unit price, total amount, fee, tax, FX rate, dividend, interest, and internal FX transfer. "
    "Final total return should not be considered official until unit/currency-aware processing is complete."
)


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype={"ticker": str}, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()


def normalized_date_text(value: Any) -> str:
    text = text_value(value)
    if not text:
        return ""
    try:
        parsed = pd.to_datetime(text, errors="coerce")
    except Exception:
        return text
    if pd.isna(parsed):
        return text
    return parsed.date().isoformat()


def fx_rate_candidate_paths(processed_dir: Path) -> list[Path]:
    import_root = processed_dir.parent if processed_dir.name.lower() == "processed" else processed_dir
    candidates = [
        import_root / "fx_rates.csv",
        import_root / "raw" / "fx_rates.csv",
        import_root / "cache" / "fx_rates.csv",
        import_root / "fx_rates_cached.csv",
        import_root / "cache" / "fx_rates_cached.csv",
        processed_dir / "fx_rates.csv",
    ]
    return list(dict.fromkeys(candidates))


def load_fx_rates(processed_dir: Path) -> pd.DataFrame:
    """Load local or cached FX rates without making live API calls."""
    frames: list[pd.DataFrame] = []
    for path_index, path in enumerate(fx_rate_candidate_paths(processed_dir)):
        frame = load_csv(path)
        if frame.empty:
            continue
        frame = frame.reindex(columns=FX_RATES_COLUMNS).copy()
        source_hint = "api_cached" if "cache" in path.name.lower() or "cache" in str(path.parent).lower() else "local"
        frame["source_type"] = frame["source_type"].fillna("").astype(str).str.strip().replace("", source_hint)
        frame["_source_path_order"] = path_index
        frame["_source_row_order"] = range(len(frame))
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=FX_RATES_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def fx_source_priority(source_type: str) -> int:
    key = source_type.strip().lower()
    if key in LOCAL_FX_SOURCE_TYPES:
        return 20
    if key in API_CACHED_FX_SOURCE_TYPES:
        return 30
    return 25


def fx_use_case_aliases(use_case: str) -> set[str]:
    key = use_case.strip().lower()
    aliases = {"", "*", "all", key}
    if key.startswith("income_"):
        aliases.update({"income", key.removeprefix("income_")})
    if key.startswith("expense_"):
        aliases.update({"expense", key.removeprefix("expense_")})
    if key.startswith("realized_"):
        aliases.update({"realized_pnl", "trade_settlement", "transaction"})
    return aliases


def usable_fx_rate_rows(fx_rates: pd.DataFrame, event_date: str, currency: str, use_case: str) -> pd.DataFrame:
    if fx_rates.empty:
        return pd.DataFrame(columns=FX_RATES_COLUMNS)
    view = fx_rates.copy()
    for column in FX_RATES_COLUMNS:
        if column not in view.columns:
            view[column] = ""
    event_date = normalized_date_text(event_date)
    currency = currency.strip().upper()
    aliases = fx_use_case_aliases(use_case)
    view["_effective_date"] = view["effective_date"].apply(normalized_date_text)
    view["_base_currency"] = view["base_currency"].fillna("").astype(str).str.strip().str.upper()
    view["_quote_currency"] = view["quote_currency"].fillna("").astype(str).str.strip().str.upper()
    view["_use_case"] = view["use_case"].fillna("").astype(str).str.strip().str.lower()
    view["_status"] = view["status"].fillna("").astype(str).str.strip().str.lower()
    view["_rate"] = pd.to_numeric(view["rate"], errors="coerce")
    if "_source_path_order" not in view.columns:
        view["_source_path_order"] = 0
    if "_source_row_order" not in view.columns:
        view["_source_row_order"] = range(len(view))
    view = view[
        view["_effective_date"].eq(event_date)
        & view["_base_currency"].eq(currency)
        & view["_quote_currency"].eq("KRW")
        & view["_use_case"].isin(aliases)
        & view["_status"].isin(USABLE_FX_RATE_STATUSES)
        & view["_rate"].notna()
        & view["_rate"].gt(0)
    ].copy()
    if view.empty:
        return pd.DataFrame(columns=FX_RATES_COLUMNS)
    view["_source_priority"] = view["source_type"].fillna("").astype(str).apply(fx_source_priority)
    return view.sort_values(["_source_priority", "_source_path_order", "_source_row_order"], na_position="last")


def fx_rate_source_label(source_type: str) -> str:
    key = source_type.strip().lower()
    if key in API_CACHED_FX_SOURCE_TYPES:
        return "api_cached_fx_rates"
    return "local_fx_rates"


def resolve_fx_rate(row: pd.Series | dict[str, Any], fx_rates: pd.DataFrame, use_case: str) -> dict[str, Any]:
    currency = (
        text_value(row.get("currency_native") if isinstance(row, dict) else row.get("currency_native")).upper()
        or text_value(row.get("currency") if isinstance(row, dict) else row.get("currency")).upper()
    )
    event_date = normalized_date_text(
        row.get("event_date") if isinstance(row, dict) else row.get("event_date")
    ) or normalized_date_text(row.get("trade_date") if isinstance(row, dict) else row.get("trade_date")) or normalized_date_text(
        row.get("sell_date") if isinstance(row, dict) else row.get("sell_date")
    )
    amount_native = first_number(pd.Series(row), ["amount_native", "trade_amount_native", "settlement_amount_native", "proceeds_native"])
    existing_krw = first_number(pd.Series(row), ["amount_krw", "trade_amount_krw", "settlement_amount_krw", "proceeds_krw"])
    amount_source = text_value(row.get("amount_krw_source") if isinstance(row, dict) else row.get("amount_krw_source")).lower()
    fx_source = text_value(row.get("fx_rate_source") if isinstance(row, dict) else row.get("fx_rate_source")).lower()
    raw_rate = first_number(pd.Series(row), ["fx_rate_to_krw", "fx_rate"])

    if not currency or len(currency) != 3 or not currency.isalpha():
        return {
            "status": "currency_ambiguous",
            "fx_status": "currency_ambiguous",
            "missing_reason": "event currency is missing or invalid",
        }
    if amount_native is None:
        return {
            "status": "unit_ambiguous",
            "fx_status": "unit_ambiguous",
            "missing_reason": "native amount is missing",
        }
    if currency == "KRW":
        return {
            "status": "ok",
            "fx_status": "not_required",
            "amount_krw": amount_native,
            "fx_rate_to_krw": 1.0,
            "fx_rate_source": "not_required",
            "amount_krw_source": "raw_native",
            "source_type": "not_required",
            "missing_reason": "",
        }
    if abs(amount_native) <= 1e-9:
        return {
            "status": "ok",
            "fx_status": "not_required",
            "amount_krw": 0.0,
            "fx_rate_to_krw": "",
            "fx_rate_source": "not_required",
            "amount_krw_source": "raw_native",
            "source_type": "not_required",
            "missing_reason": "",
        }
    if existing_krw is not None and (amount_source in BROKER_KRW_SOURCES or "broker" in amount_source):
        derived_rate = abs(existing_krw / amount_native) if abs(amount_native) > 1e-9 else ""
        return {
            "status": "ok",
            "fx_status": "available",
            "amount_krw": existing_krw,
            "fx_rate_to_krw": derived_rate,
            "fx_rate_source": amount_source or "broker_krw_amount",
            "amount_krw_source": amount_source or "broker_krw_amount",
            "source_type": "broker_krw_amount",
            "missing_reason": "",
        }
    if raw_rate is not None and raw_rate > 0 and fx_source not in {"local_fx_rates", "api_cached_fx_rates"}:
        return {
            "status": "ok",
            "fx_status": "available",
            "amount_krw": round(amount_native * raw_rate, 6),
            "fx_rate_to_krw": raw_rate,
            "fx_rate_source": fx_source if fx_source in RAW_FX_SOURCES and fx_source else "broker_raw_fx",
            "amount_krw_source": "broker_raw_fx",
            "source_type": "broker_raw_fx",
            "missing_reason": "",
        }

    if not event_date:
        return {
            "status": "fx_missing",
            "fx_status": "fx_missing",
            "missing_reason": "event_date is missing",
        }
    matched = usable_fx_rate_rows(fx_rates, event_date, currency, use_case)
    if matched.empty:
        return {
            "status": "fx_missing",
            "fx_status": "fx_missing",
            "missing_reason": "no same-date archived FX rate found",
        }
    rate_row = matched.iloc[0]
    rate = float(rate_row["_rate"])
    source = fx_rate_source_label(text_value(rate_row.get("source_type")))
    return {
        "status": "ok",
        "fx_status": "available",
        "amount_krw": round(amount_native * rate, 6),
        "fx_rate_to_krw": rate,
        "fx_rate_source": source,
        "amount_krw_source": source,
        "source_type": text_value(rate_row.get("source_type")),
        "provider": text_value(rate_row.get("provider")),
        "source_note": text_value(rate_row.get("source_note")),
        "missing_reason": "",
    }


def income_fx_use_case(row: pd.Series) -> str:
    income_type = text_value(row.get("income_type")).lower()
    return f"income_{income_type}" if income_type else "income"


def expense_fx_use_case(row: pd.Series) -> str:
    expense_type = text_value(row.get("expense_type")).lower()
    return f"expense_{expense_type}" if expense_type else "expense"


def combine_status_reason(existing_reason: Any, extra_reason: str) -> str:
    reasons = [text_value(existing_reason), text_value(extra_reason)]
    return "; ".join(dict.fromkeys(reason for reason in reasons if reason))


def apply_income_fx_rates(income: pd.DataFrame, fx_rates: pd.DataFrame) -> pd.DataFrame:
    if income.empty:
        return income.reindex(columns=income.columns)
    output = income.copy().astype(object)
    for idx, row in output.iterrows():
        use_case = income_fx_use_case(row)
        resolved = resolve_fx_rate(row, fx_rates, use_case)
        current_status = text_value(row.get("amount_review_status")).lower() or "ok"
        terminal_review_status = current_status not in {"ok", "fx_missing", "missing"}
        if resolved.get("status") == "ok":
            output.at[idx, "amount_krw"] = resolved.get("amount_krw", "")
            output.at[idx, "amount_krw_source"] = resolved.get("amount_krw_source", "")
            output.at[idx, "fx_rate_to_krw"] = resolved.get("fx_rate_to_krw", "")
            output.at[idx, "fx_rate_source"] = resolved.get("fx_rate_source", "")
            if not terminal_review_status:
                output.at[idx, "amount_review_status"] = "ok"
                output.at[idx, "amount_review_reason"] = ""
            else:
                output.at[idx, "amount_review_status"] = current_status
            if text_value(resolved.get("amount_krw_source")) in {"local_fx_rates", "api_cached_fx_rates", "broker_raw_fx"}:
                output.at[idx, "amount_basis"] = "derived_krw_from_fx"
                output.at[idx, "amount_confidence"] = "derived"
        elif not terminal_review_status:
            output.at[idx, "amount_review_status"] = resolved.get("status", "fx_missing")
            output.at[idx, "amount_review_reason"] = combine_status_reason(row.get("amount_review_reason"), resolved.get("missing_reason", ""))
            if row_currency(row) != "KRW":
                output.at[idx, "amount_krw"] = ""
                output.at[idx, "amount_krw_source"] = ""

        tax_native = first_number(row, ["tax_native"])
        if tax_native is None:
            continue
        if abs(tax_native) <= 1e-9:
            output.at[idx, "tax_krw"] = 0.0
            continue
        tax_row = row.copy()
        tax_row["amount_native"] = tax_native
        tax_row["amount_krw"] = row.get("tax_krw", "")
        tax_row["amount_krw_source"] = "" if text_value(row.get("amount_krw_source")).lower() in BROKER_KRW_SOURCES else row.get("amount_krw_source", "")
        tax_resolved = resolve_fx_rate(tax_row, fx_rates, f"{use_case}_tax")
        if tax_resolved.get("status") == "ok" and tax_resolved.get("source_type") != "broker_krw_amount":
            output.at[idx, "tax_krw"] = tax_resolved.get("amount_krw", "")
        elif row_currency(row) != "KRW" and not terminal_review_status:
            output.at[idx, "tax_krw"] = ""
    return output.reindex(columns=income.columns)


def apply_expense_fx_rates(expenses: pd.DataFrame, fx_rates: pd.DataFrame) -> pd.DataFrame:
    if expenses.empty:
        return expenses.reindex(columns=expenses.columns)
    output = expenses.copy().astype(object)
    for idx, row in output.iterrows():
        use_case = expense_fx_use_case(row)
        resolved = resolve_fx_rate(row, fx_rates, use_case)
        current_status = text_value(row.get("amount_review_status")).lower() or "ok"
        terminal_review_status = current_status not in {"ok", "fx_missing", "missing"}
        if resolved.get("status") == "ok":
            output.at[idx, "amount_krw"] = resolved.get("amount_krw", "")
            output.at[idx, "fx_rate_to_krw"] = resolved.get("fx_rate_to_krw", "")
            output.at[idx, "fx_rate_source"] = resolved.get("fx_rate_source", "")
            if not terminal_review_status:
                output.at[idx, "amount_review_status"] = "ok"
                output.at[idx, "amount_review_reason"] = ""
            else:
                output.at[idx, "amount_review_status"] = current_status
            if text_value(resolved.get("amount_krw_source")) in {"local_fx_rates", "api_cached_fx_rates", "broker_raw_fx"}:
                output.at[idx, "amount_basis"] = "derived_krw_from_fx"
                output.at[idx, "amount_confidence"] = "derived"
        elif not terminal_review_status:
            output.at[idx, "amount_review_status"] = resolved.get("status", "fx_missing")
            output.at[idx, "amount_review_reason"] = combine_status_reason(row.get("amount_review_reason"), resolved.get("missing_reason", ""))
            if row_currency(row) != "KRW":
                output.at[idx, "amount_krw"] = ""
    return output.reindex(columns=expenses.columns)


def status_counts_summary(values: list[str]) -> str:
    cleaned = [value for value in values if value]
    if not cleaned:
        return ""
    counts: dict[str, int] = {}
    for value in cleaned:
        counts[value] = counts.get(value, 0) + 1
    return " / ".join(f"{key}: {value}" for key, value in counts.items())


def fx_requirement_record(
    row: pd.Series,
    *,
    event_date: Any,
    currency: str,
    use_case: str,
    amount_native: float | None,
    missing_reason: str,
) -> dict[str, Any] | None:
    currency = currency.strip().upper()
    if not currency or currency == "KRW" or amount_native is None or abs(amount_native) <= 1e-9:
        return None
    return {
        "event_date": normalized_date_text(event_date),
        "currency": currency,
        "use_case": use_case,
        "row_count": 1,
        "amount_native_sum": abs(amount_native),
        "missing_reason": missing_reason or "non-KRW row has no same-date archived FX rate",
        "source_file_type": text_value(row.get("source_file_type")),
        "status": "fx_missing",
    }


def income_fx_requirement_records(income: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if income.empty:
        return records
    for _, row in income.iterrows():
        status = row_review_status(row)
        if status != "fx_missing":
            continue
        record = fx_requirement_record(
            row,
            event_date=row.get("trade_date"),
            currency=row_currency(row),
            use_case=income_fx_use_case(row),
            amount_native=first_number(row, ["amount_native"]),
            missing_reason=text_value(row.get("amount_review_reason")),
        )
        if record:
            records.append(record)
    return records


def expense_fx_requirement_records(expenses: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if expenses.empty:
        return records
    for _, row in expenses.iterrows():
        status = row_review_status(row)
        if status != "fx_missing":
            continue
        record = fx_requirement_record(
            row,
            event_date=row.get("trade_date"),
            currency=row_currency(row),
            use_case=expense_fx_use_case(row),
            amount_native=first_number(row, ["amount_native"]),
            missing_reason=text_value(row.get("amount_review_reason")),
        )
        if record:
            records.append(record)
    return records


def realized_fx_requirement_records(transactions: pd.DataFrame, fx_rates: pd.DataFrame | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    trades = sorted_trade_rows(transactions)
    if trades.empty:
        return records
    for _, row in trades.iterrows():
        amount = trade_amounts(row, fx_rates=fx_rates)
        if amount.get("status") != "fx_missing":
            continue
        record = fx_requirement_record(
            row,
            event_date=row.get("trade_date"),
            currency=row_currency(row),
            use_case="realized_pnl_trade_settlement",
            amount_native=amount.get("native"),
            missing_reason=text_value(amount.get("reason")) or "realized PnL trade row needs historical FX before official KRW PnL",
        )
        if record:
            records.append(record)
    return records


def build_fx_rate_requirements(
    income: pd.DataFrame,
    transactions: pd.DataFrame | None = None,
    expenses: pd.DataFrame | None = None,
    fx_rates: pd.DataFrame | None = None,
) -> pd.DataFrame:
    records = income_fx_requirement_records(income)
    if transactions is not None:
        records.extend(realized_fx_requirement_records(transactions, fx_rates=fx_rates))
    if expenses is not None:
        records.extend(expense_fx_requirement_records(expenses))
    if not records:
        return pd.DataFrame(columns=FX_RATE_REQUIREMENT_COLUMNS)
    grouped = (
        pd.DataFrame(records)
        .groupby(["event_date", "currency", "use_case", "missing_reason", "source_file_type", "status"], dropna=False, as_index=False)
        .agg(row_count=("row_count", "sum"), amount_native_sum=("amount_native_sum", "sum"))
    )
    return grouped.reindex(columns=FX_RATE_REQUIREMENT_COLUMNS).sort_values(
        ["event_date", "currency", "use_case", "source_file_type"],
        na_position="last",
    ).reset_index(drop=True)


def parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    meta: dict[str, Any] = {}
    for line in text[3:end].splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        value = value.strip().strip('"').strip("'")
        meta[key.strip()] = value
    return meta


def note_text(vault_root: Path, ticker: str) -> str:
    for path in (vault_root / "20_Companies").glob("*/Company.md"):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception:
            continue
        meta = parse_frontmatter(text)
        if str(meta.get("ticker", "")).upper() == str(ticker).upper() or path.parent.name.upper() == str(ticker).upper():
            return text
    return ""


UNRESOLVED_PLACEHOLDER_PATTERNS = [
    r"(?im)^\s*[-*]?\s*(추가\s*)?(조사|검토|재검토|확인)\s*필요\s*:.*$",
    r"(?im)^\s*[-*]?\s*(핵심\s*가정|내가\s*틀릴\s*수\s*있는\s*지점|관찰\s*포인트|업데이트\s*로그)\s*:\s*$",
    r"\[?\s*확인\s*필요\s*\]?",
    r"조사\s*(및\s*)?(검토|재검토)?\s*필요",
    r"(사용자\s*)?재검토\s*필요",
    r"(추가\s*)?검토\s*필요",
    r"현재\s*(사용자\s*확정\s*)?(thesis|투자\s*논리|매수\s*이유|보유\s*목적)[^.\n]*(미작성|없음|미정)",
    r"현재\s*(명시적\s*)?(매도|비중\s*축소|손실|손절|운영)?[^.\n]*(기준|조건|허용선|기준선)[^.\n]*(없음|미정|두지\s*않)",
    r"명시적\s*(매도|비중\s*축소|손실|손절)?\s*(기준|조건|허용선|기준선)\s*(없음|미정)",
    r"(매도|비중\s*축소|손실|손절|운영)?\s*(기준|조건|허용선|기준선)\s*(없음|미정)",
    r"현재\s*미정",
    r"기준\s*미정",
    r"기준\s*없음",
    r"미작성",
    r"미정",
    r"없음",
    r"(?im)^\s*[-*]?\s*이전\s*AI\s*예시.*$",
    r"이전\s*AI\s*예시[^.\n]*(무효|미작성)",
    r"새\s*사용자\s*판단[^.\n]*미작성",
    r"별도\s*(손실\s*)?(기준|기준선)[^.\n]*(없|두지)",
    r"손실\s*(기준|기준선)[^.\n]*(없|두지)",
    r"현재\s*판단[^.\n]*계속\s*보유[^.\n]*",
    r"계속\s*보유\s*예정",
    r"유망[^.\n]*(기준|조건)[^.\n]*(없음|미정)",
    r"운영\s*기준\s*미정",
    r"사용자\s*판단\s*:",
    r"손실\s*허용선\s*:",
]


def meaningful_section_body(body: str) -> str:
    normalized = body.replace("TODO", "")
    for pattern in UNRESOLVED_PLACEHOLDER_PATTERNS:
        normalized = re.sub(pattern, "", normalized, flags=re.I)
    normalized = re.sub(r"[-\s:_/()0-9.%·,.;\[\]]+", "", normalized)
    return normalized.strip()


def has_filled_section(text: str, names: list[str]) -> bool:
    if not text:
        return False
    for name in names:
        pattern = re.compile(rf"^#+[^\n]*{re.escape(name)}[^\n]*\n(.*?)(?=^#+\s|\Z)", re.M | re.S)
        m = pattern.search(text)
        if m:
            body = meaningful_section_body(m.group(1))
            if len(body) >= 8:
                return True
    return False


def days_since(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        dt = pd.to_datetime(value).date()
    except Exception:
        return None
    return (date.today() - dt).days


def derive_holdings(transactions: pd.DataFrame) -> pd.DataFrame:
    if transactions.empty:
        return pd.DataFrame()
    rows = []
    for (account, ticker), g in transactions.groupby(["account_type", "ticker"], dropna=False):
        qty = 0.0
        cost = 0.0
        name = ""
        market = ""
        currency = ""
        asset_type = ""
        for _, r in g.iterrows():
            tx = str(r.get("transaction_type", ""))
            q = float(r.get("quantity", 0) or 0)
            price = float(r.get("price", 0) or 0)
            if tx == "buy":
                qty += q
                cost += q * price + float(r.get("fee", 0) or 0) + float(r.get("tax", 0) or 0)
            elif tx == "sell":
                avg = cost / qty if qty else 0
                qty -= q
                cost -= q * avg
            name = r.get("security_name", name) or name
            market = r.get("market", market) or market
            currency = r.get("currency", currency) or currency
            asset_type = r.get("asset_type", asset_type) or asset_type
        if abs(qty) > 1e-9:
            rows.append({"account_type": account, "ticker": ticker, "security_name": name, "market": market, "currency": currency, "asset_type": asset_type, "balance_quantity": qty, "evaluation_amount": cost, "unrealized_pnl": 0, "pnl_pct": 0})
    return pd.DataFrame(rows)


def split_current_history_holdings(holdings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if holdings.empty:
        return holdings.copy(), pd.DataFrame(columns=HISTORY_COLUMNS)
    work = holdings.copy()
    has_balance_col = "balance_quantity" in work.columns
    has_evaluation_col = "evaluation_amount" in work.columns
    has_quantity_col = "quantity" in work.columns
    for col in ["balance_quantity", "quantity", "evaluation_amount"]:
        if col not in work.columns:
            work[col] = 0
        work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)
    if "weight_pct" not in work.columns:
        work["weight_pct"] = 0.0
    else:
        work["weight_pct"] = pd.to_numeric(work["weight_pct"], errors="coerce").fillna(0.0)
    current_mask = pd.Series(False, index=work.index)
    if has_balance_col:
        current_mask = current_mask | (work["balance_quantity"].abs() > 1e-9)
    if has_evaluation_col:
        current_mask = current_mask | (work["evaluation_amount"].abs() > 1e-9)
    if not has_balance_col and not has_evaluation_col and has_quantity_col:
        current_mask = current_mask | (work["quantity"].abs() > 1e-9)
    current = work[current_mask].copy()
    history = work[~current_mask].copy()
    if not history.empty:
        history["history_reason"] = "NO_CURRENT_POSITION"
        history["suggested_destination"] = "50_Journal/Post_Mortem 또는 40_Knowledge/Lessons"
        history["suggested_action"] = "현재 보유종목 리뷰 큐에서는 제외. 필요 시 사후분석 후보로 검토."
    return current.reset_index(drop=True), history.reindex(columns=HISTORY_COLUMNS).reset_index(drop=True)


def _position_keys(df: pd.DataFrame) -> set[tuple[str, str]]:
    if df.empty or "ticker" not in df.columns:
        return set()
    account = df["account_type"] if "account_type" in df.columns else ""
    keys = pd.DataFrame({"account_type": account, "ticker": df["ticker"]})
    keys["account_type"] = keys["account_type"].fillna("").astype(str)
    keys["ticker"] = keys["ticker"].fillna("").astype(str).str.upper()
    return set(map(tuple, keys[["account_type", "ticker"]].to_records(index=False)))


def build_transaction_history_candidates(transactions: pd.DataFrame, current_holdings: pd.DataFrame, existing_history: pd.DataFrame) -> pd.DataFrame:
    if transactions.empty or "ticker" not in transactions.columns:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    work = transactions.copy()
    work["ticker"] = work["ticker"].fillna("").astype(str)
    work = work[~work["ticker"].str.lower().isin(["", "nan", "none"])]
    if work.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    current_keys = _position_keys(current_holdings)
    existing_keys = _position_keys(existing_history)
    if "trade_date" in work.columns:
        work["_sort_date"] = pd.to_datetime(work["trade_date"], errors="coerce")
        work = work.sort_values(["account_type", "ticker", "_sort_date"], na_position="first")
    group_cols = [c for c in ["account_type", "ticker"] if c in work.columns]
    if not group_cols:
        group_cols = ["ticker"]

    rows = []
    for _, row in work.groupby(group_cols, dropna=False, as_index=False).tail(1).iterrows():
        key = (str(row.get("account_type", "")), str(row.get("ticker", "")).upper())
        if key in current_keys or key in existing_keys:
            continue
        item = {col: row.get(col, "") for col in HISTORY_COLUMNS}
        item["balance_quantity"] = 0
        item["evaluation_amount"] = 0
        item["unrealized_pnl"] = 0
        item["pnl_pct"] = 0
        item["weight_pct"] = 0
        item["history_reason"] = "TRANSACTION_HISTORY_NO_CURRENT_POSITION"
        item["suggested_destination"] = "50_Journal/Post_Mortem 또는 40_Knowledge/Lessons"
        item["suggested_action"] = "현재 보유종목 리뷰 큐에서는 제외. 필요 시 사후분석/교훈 후보로 검토."
        rows.append(item)
    if not rows:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    return pd.DataFrame(rows).reindex(columns=HISTORY_COLUMNS).reset_index(drop=True)


def source_type_counts(processed_dir: Path) -> tuple[int, int, int]:
    source_index = load_csv(processed_dir / "source_file_index.csv")
    if source_index.empty or "source_file_type" not in source_index.columns:
        return 0, 0, 0
    source_types = source_index["source_file_type"].fillna("").astype(str)
    raw_count = len(source_index)
    transaction_count = int(source_types.isin(["transaction_history", "transactions", "cashflow"]).sum())
    holding_count = int(source_types.isin(BALANCE_SOURCE_TYPES).sum())
    return raw_count, transaction_count, holding_count


def holding_dedupe_metrics(holdings: pd.DataFrame) -> dict[str, Any]:
    if holdings.empty or "dedupe_excluded_count" not in holdings.columns:
        return {
            "candidate_rows": 0,
            "retained_rows": 0,
            "excluded_rows": 0,
            "excluded_evaluation_amount": 0.0,
        }
    excluded_counts = pd.to_numeric(holdings["dedupe_excluded_count"], errors="coerce").fillna(0)
    retained_rows = int((excluded_counts > 0).sum())
    excluded_rows = int(excluded_counts.sum())
    excluded_value = 0.0
    if "dedupe_excluded_evaluation_amount" in holdings.columns:
        excluded_value = float(pd.to_numeric(holdings["dedupe_excluded_evaluation_amount"], errors="coerce").fillna(0).sum())
    return {
        "candidate_rows": retained_rows + excluded_rows,
        "retained_rows": retained_rows,
        "excluded_rows": excluded_rows,
        "excluded_evaluation_amount": excluded_value,
    }


def blank_value(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "nat"}


def text_value(value: Any) -> str:
    return "" if blank_value(value) else str(value).strip()


def number_value(value: Any) -> float | None:
    if blank_value(value):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def first_number(row: pd.Series, fields: list[str]) -> float | None:
    for field in fields:
        if field in row.index:
            value = number_value(row.get(field))
            if value is not None:
                return value
    return None


def first_nonzero_number(row: pd.Series, fields: list[str]) -> float | None:
    fallback = None
    for field in fields:
        if field in row.index:
            value = number_value(row.get(field))
            if value is None:
                continue
            if fallback is None:
                fallback = value
            if abs(value) > 1e-9:
                return value
    return fallback


def truthy_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = text_value(value).lower()
    return text in {"true", "1", "yes", "y"}


def row_currency(row: pd.Series) -> str:
    for field in ["currency_native", "currency"]:
        if field in row.index:
            value = text_value(row.get(field)).upper()
            if value:
                return value
    return ""


def row_review_status(row: pd.Series) -> str:
    for field in ["amount_review_status", "amount_normalization_status", "fx_rate_status"]:
        if field in row.index:
            value = text_value(row.get(field)).lower()
            if value:
                return value
    return ""


def status_from_list(statuses: list[str], default: str = "available") -> str:
    cleaned = [status for status in statuses if status and status != "available"]
    if not cleaned:
        return default
    for status in [
        "currency_ambiguous",
        "unit_ambiguous",
        "fx_missing",
        "lot_missing",
        "transaction_history_missing",
        "balance_missing",
        "currency_normalization_pending",
    ]:
        if status in cleaned:
            return status
    return cleaned[0]


def metric_value(value: Any) -> Any:
    return "" if value is None else value


def summary_metric_rows(values: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"metric": metric, "value": metric_value(value)} for metric, value in values.items()],
        columns=RECONCILIATION_SUMMARY_COLUMNS,
    )


def preferred_krw_series(df: pd.DataFrame, krw_field: str, native_field: str) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    krw_field_present = krw_field in df.columns

    def amount(row: pd.Series) -> float:
        krw_amount = first_number(row, [krw_field])
        if krw_amount is not None:
            return krw_amount
        if krw_field_present and row_currency(row) != "KRW":
            return 0.0
        native_amount = first_number(row, [native_field])
        return native_amount if native_amount is not None else 0.0

    return df.apply(amount, axis=1)


def holding_asset_krw(row: pd.Series) -> tuple[float | None, str]:
    krw_amount = first_number(row, ["evaluation_amount_krw", "amount_krw"])
    if krw_amount is not None:
        return krw_amount, "available"

    currency = row_currency(row)
    native_amount = first_number(row, ["evaluation_amount"])
    quantity = first_number(row, ["balance_quantity", "quantity"])
    price = first_number(row, ["price"])
    if native_amount == 0 and quantity not in {None, 0.0} and price is not None:
        return None, "unit_ambiguous"
    if currency == "KRW" and native_amount is not None:
        return native_amount, "available"
    if not currency or len(currency) != 3 or not currency.isalpha():
        return None, "currency_ambiguous"

    row_status = row_review_status(row)
    if row_status in {"currency_ambiguous", "unit_ambiguous", "fx_missing"}:
        return None, row_status
    if currency != "KRW" and native_amount is not None:
        return None, "fx_missing"
    return None, "unit_ambiguous"


def total_assets_krw(holdings: pd.DataFrame) -> tuple[float | None, str, dict[str, int]]:
    total, _cash, _invested, status, status_counts = total_assets_breakdown_krw(holdings)
    return total, status, status_counts


def total_assets_breakdown_krw(holdings: pd.DataFrame) -> tuple[float | None, float | None, float | None, str, dict[str, int]]:
    status_counts = {"fx_missing": 0, "currency_ambiguous": 0, "unit_ambiguous": 0, "amount_review_needed": 0}
    if holdings.empty:
        return None, None, None, "balance_missing", status_counts

    total = 0.0
    cash_total = 0.0
    invested_total = 0.0
    available_rows = 0
    blocking_statuses: list[str] = []
    for _, row in holdings.iterrows():
        amount, status = holding_asset_krw(row)
        if status == "available" and amount is not None:
            total += amount
            if text_value(row.get("asset_type")).lower() == "cash":
                cash_total += amount
            else:
                invested_total += amount
            available_rows += 1
            continue
        blocking_statuses.append(status)
        explicit_status = row_review_status(row)
        if explicit_status not in REVIEW_NEEDED_STATUSES and explicit_status not in status_counts:
            if status in status_counts:
                status_counts[status] += 1
            if status in REVIEW_NEEDED_STATUSES:
                status_counts["amount_review_needed"] += 1

    if blocking_statuses:
        return None, None, None, status_from_list(blocking_statuses), status_counts
    if available_rows == 0:
        return None, None, None, "balance_missing", status_counts
    return total, cash_total, invested_total, "available", status_counts


def principal_direction(row: pd.Series) -> str:
    tx_type = text_value(row.get("transaction_type")).lower()
    if tx_type in {"deposit", "withdrawal"}:
        return tx_type
    return ""


def net_external_principal_krw(cashflows: pd.DataFrame, source_available: bool = True) -> tuple[float | None, float | None, float | None, str, dict[str, int]]:
    status_counts = {"fx_missing": 0, "currency_ambiguous": 0, "unit_ambiguous": 0, "amount_review_needed": 0}
    if cashflows.empty:
        if not source_available:
            return None, None, None, "balance_missing", status_counts
        return 0.0, 0.0, 0.0, "available", status_counts

    deposits = 0.0
    withdrawals = 0.0
    blocking_statuses: list[str] = []
    candidate_rows = 0
    included_rows = 0

    for _, row in cashflows.iterrows():
        direction = principal_direction(row)
        if not direction:
            continue
        candidate_rows += 1
        role = text_value(row.get("cashflow_role")).lower()
        review_status = row_review_status(row) or "ok"
        amount = first_number(row, ["settlement_amount_krw", "amount_krw"])
        affects_principal = truthy_value(row.get("affects_principal"))
        if role != "external_principal" or not affects_principal or review_status != "ok" or amount is None:
            status = review_status if review_status != "ok" else "unit_ambiguous"
            blocking_statuses.append(status)
            explicit_status = row_review_status(row)
            if explicit_status not in REVIEW_NEEDED_STATUSES and explicit_status not in status_counts:
                if status in status_counts:
                    status_counts[status] += 1
                if status in REVIEW_NEEDED_STATUSES:
                    status_counts["amount_review_needed"] += 1
            continue
        if direction == "deposit":
            deposits += abs(amount)
        else:
            withdrawals += abs(amount)
        included_rows += 1

    if blocking_statuses:
        return (deposits if included_rows else None), (withdrawals if included_rows else None), None, status_from_list(blocking_statuses), status_counts
    if candidate_rows == 0:
        return 0.0, 0.0, 0.0, "available", status_counts
    return deposits, withdrawals, deposits - withdrawals, "available", status_counts


def build_monthly_cashflow_summary(cashflows: pd.DataFrame) -> pd.DataFrame:
    if cashflows.empty or "trade_date" not in cashflows.columns:
        return pd.DataFrame(columns=MONTHLY_CASHFLOW_SUMMARY_COLUMNS)

    records: list[dict[str, Any]] = []
    for _, row in cashflows.iterrows():
        direction = principal_direction(row)
        if not direction:
            continue
        month = text_value(row.get("trade_date"))[:7]
        if len(month) != 7:
            continue
        role = text_value(row.get("cashflow_role")).lower()
        review_status = row_review_status(row) or "ok"
        amount = first_number(row, ["settlement_amount_krw", "amount_krw"])
        if role != "external_principal" or not truthy_value(row.get("affects_principal")) or review_status != "ok" or amount is None:
            continue
        amount = abs(amount)
        records.append({
            "month": month,
            "external_deposit_krw": amount if direction == "deposit" else 0.0,
            "external_withdrawal_krw": amount if direction == "withdrawal" else 0.0,
        })

    if not records:
        return pd.DataFrame(columns=MONTHLY_CASHFLOW_SUMMARY_COLUMNS)

    monthly = (
        pd.DataFrame(records)
        .groupby("month", as_index=False, dropna=False)[["external_deposit_krw", "external_withdrawal_krw"]]
        .sum()
        .sort_values("month", ascending=True)
        .reset_index(drop=True)
    )
    monthly["net_principal_flow_krw"] = monthly["external_deposit_krw"] - monthly["external_withdrawal_krw"]
    monthly["cumulative_principal_krw"] = monthly["net_principal_flow_krw"].cumsum()
    for column in MONTHLY_CASHFLOW_SUMMARY_COLUMNS:
        if column != "month":
            monthly[column] = monthly[column].round(2)
    return monthly.reindex(columns=MONTHLY_CASHFLOW_SUMMARY_COLUMNS)


def ok_amount_sum(df: pd.DataFrame, type_col: str, accepted_types: set[str]) -> float:
    if df.empty or type_col not in df.columns:
        return 0.0
    total = 0.0
    for _, row in df.iterrows():
        row_type = text_value(row.get(type_col)).lower()
        if row_type not in accepted_types:
            continue
        if (row_review_status(row) or "ok") != "ok":
            continue
        amount = first_number(row, ["amount_krw", "settlement_amount_krw"])
        if amount is not None:
            total += abs(amount)
    return total


def sum_optional_amounts(
    rows: list[pd.Series],
    field: str,
    *,
    ok_only: bool = False,
) -> float | None:
    values: list[float] = []
    for row in rows:
        if ok_only and (row_review_status(row) or "ok") != "ok":
            continue
        amount = first_number(row, [field])
        if amount is not None:
            values.append(abs(amount))
    if not values:
        return None
    return float(sum(values))


def income_status_from_rows(rows: list[pd.Series]) -> str:
    statuses = [(row_review_status(row) or "ok") for row in rows]
    blocking = [status for status in statuses if status != "ok"]
    return status_from_list(blocking, default="available")


def build_income_summary(income: pd.DataFrame) -> pd.DataFrame:
    if income.empty or "income_type" not in income.columns:
        return pd.DataFrame(columns=INCOME_SUMMARY_COLUMNS)

    records: list[dict[str, Any]] = []
    view = income.copy()
    view["_income_type"] = view["income_type"].fillna("").astype(str).str.strip().str.lower()
    view["_currency_native"] = (
        view["currency_native"].fillna("").astype(str).str.strip().str.upper()
        if "currency_native" in view.columns
        else ""
    )
    view = view[view["_income_type"].isin(INCOME_TYPES)].copy()
    if view.empty:
        return pd.DataFrame(columns=INCOME_SUMMARY_COLUMNS)

    type_order = {income_type: index for index, income_type in enumerate(INCOME_TYPES)}
    for (income_type, currency), group in view.groupby(["_income_type", "_currency_native"], dropna=False, sort=True):
        rows = [row for _, row in group.iterrows()]
        status = income_status_from_rows(rows)
        status_values = [(row_review_status(row) or "ok") for row in rows]
        fx_missing_count = sum(1 for value in status_values if value == "fx_missing")
        review_needed_count = sum(1 for value in status_values if value in REVIEW_NEEDED_STATUSES)
        amount_native = sum_optional_amounts(rows, "amount_native")
        tax_native = sum_optional_amounts(rows, "tax_native")
        amount_krw = sum_optional_amounts(rows, "amount_krw", ok_only=True)
        tax_krw = sum_optional_amounts(rows, "tax_krw", ok_only=True)
        tax_native_for_net = tax_native if tax_native is not None else (0.0 if amount_native is not None else None)
        tax_krw_for_net = tax_krw if tax_krw is not None else (0.0 if amount_krw is not None else None)
        fx_status_values: list[str] = []
        fx_source_values: list[str] = []
        for row in rows:
            status_value = row_review_status(row) or "ok"
            currency_value = row_currency(row)
            if currency_value == "KRW":
                fx_status_values.append("not_required")
                fx_source_values.append("raw_native")
            elif status_value == "fx_missing":
                fx_status_values.append("fx_missing")
                fx_source_values.append("fx_missing")
            elif status_value == "ok":
                fx_status_values.append("available")
                fx_source_values.append(
                    text_value(row.get("amount_krw_source"))
                    or text_value(row.get("fx_rate_source"))
                    or "unknown"
                )
            else:
                fx_status_values.append(status_value)
                fx_source_values.append(
                    text_value(row.get("amount_krw_source"))
                    or text_value(row.get("fx_rate_source"))
                    or status_value
                )
        records.append({
            "income_type": income_type,
            "currency_native": currency,
            "amount_native_sum": amount_native if amount_native is not None else "",
            "amount_krw_sum": amount_krw if amount_krw is not None else "",
            "tax_native_sum": tax_native_for_net if tax_native_for_net is not None else "",
            "tax_krw_sum": tax_krw_for_net if tax_krw_for_net is not None else "",
            "net_income_native": (amount_native - tax_native_for_net) if amount_native is not None and tax_native_for_net is not None else "",
            "net_income_krw": (amount_krw - tax_krw_for_net) if amount_krw is not None and tax_krw_for_net is not None else "",
            "row_count": len(group),
            "fx_missing_row_count": fx_missing_count,
            "amount_review_needed_row_count": review_needed_count,
            "fx_status_summary": status_counts_summary(fx_status_values),
            "fx_source_summary": status_counts_summary(fx_source_values),
            "income_status": status,
            "_type_order": type_order.get(str(income_type), len(type_order)),
        })

    return (
        pd.DataFrame(records)
        .sort_values(["_type_order", "currency_native"])
        .drop(columns=["_type_order"], errors="ignore")
        .reindex(columns=INCOME_SUMMARY_COLUMNS)
    )


def summary_to_dict(summary: pd.DataFrame) -> dict[str, Any]:
    if summary.empty or "metric" not in summary.columns or "value" not in summary.columns:
        return {}
    return dict(zip(summary["metric"].astype(str), summary["value"]))


def summary_number(metrics: dict[str, Any], name: str) -> float | None:
    return number_value(metrics.get(name))


def summary_status(metrics: dict[str, Any], name: str, default: str = "available") -> str:
    value = text_value(metrics.get(name)).lower()
    return value or default


def income_summary_status(income_summary: pd.DataFrame) -> str:
    if income_summary.empty or "income_status" not in income_summary.columns:
        return "available"
    statuses = [
        text_value(value).lower()
        for value in income_summary["income_status"].fillna("")
        if text_value(value)
    ]
    return status_from_list(statuses, default="available")


def income_summary_total(
    income_summary: pd.DataFrame,
    *,
    income_type: str | None = None,
    field: str = "amount_krw_sum",
) -> float | None:
    if income_summary.empty or field not in income_summary.columns:
        return 0.0
    view = income_summary
    if income_type is not None and "income_type" in view.columns:
        view = view[view["income_type"].fillna("").astype(str).str.lower().eq(income_type)]
    if view.empty:
        return 0.0
    values = [number_value(value) for value in view[field]]
    values = [value for value in values if value is not None]
    if values:
        return float(sum(values))
    row_counts = [number_value(value) for value in view.get("row_count", pd.Series(dtype=float))]
    if any((value or 0.0) > 0 for value in row_counts):
        return None
    return 0.0


def income_summary_field_sum(income_summary: pd.DataFrame, field: str) -> float:
    if income_summary.empty or field not in income_summary.columns:
        return 0.0
    values = [number_value(value) for value in income_summary[field]]
    return float(sum(value for value in values if value is not None))


def income_summary_source_text(income_summary: pd.DataFrame) -> str:
    if income_summary.empty or "fx_source_summary" not in income_summary.columns:
        return ""
    values = [
        text_value(value)
        for value in income_summary["fx_source_summary"].fillna("")
        if text_value(value)
    ]
    return " | ".join(dict.fromkeys(values))


def income_fx_status_from_summary(income_summary: pd.DataFrame) -> str:
    if income_summary_field_sum(income_summary, "fx_missing_row_count") > 0:
        return "fx_missing"
    return "available"


def performance_fx_status(reconciliation_metrics: dict[str, Any]) -> str:
    statuses: list[str] = []
    if (summary_number(reconciliation_metrics, "currency_ambiguous_row_count") or 0.0) > 0:
        statuses.append("currency_ambiguous")
    if (summary_number(reconciliation_metrics, "unit_ambiguous_row_count") or 0.0) > 0:
        statuses.append("unit_ambiguous")
    if (summary_number(reconciliation_metrics, "fx_missing_row_count") or 0.0) > 0:
        statuses.append("fx_missing")
    if (summary_number(reconciliation_metrics, "amount_review_needed_row_count") or 0.0) > 0:
        statuses.append("needs_review")
    return status_from_list(statuses, default="available")


def build_performance_summary(
    reconciliation: pd.DataFrame,
    income_summary: pd.DataFrame | None = None,
    fx_requirements: pd.DataFrame | None = None,
) -> pd.DataFrame:
    income_summary = income_summary if income_summary is not None else pd.DataFrame()
    fx_requirements = fx_requirements if fx_requirements is not None else pd.DataFrame()
    rec = summary_to_dict(reconciliation)
    total_assets_status = summary_status(rec, "total_assets_status", "unavailable")
    principal_status = summary_status(rec, "net_external_principal_status", "unavailable")
    realized_status = summary_status(rec, "realized_pnl_status", "transaction_history_missing")
    income_status = income_summary_status(income_summary)
    income_fx_status = income_fx_status_from_summary(income_summary)
    fx_status = performance_fx_status(rec)

    asset_values_available = total_assets_status == "available"
    current_total_assets = summary_number(rec, "total_assets_krw") if asset_values_available else None
    current_cash = summary_number(rec, "current_cash_krw") if asset_values_available else None
    current_holding_assets = summary_number(rec, "current_holding_assets_krw") if asset_values_available else None
    net_principal = summary_number(rec, "net_external_principal_krw")
    cumulative_status = status_from_list(
        [
            total_assets_status if total_assets_status != "available" else "",
            principal_status if principal_status != "available" else "",
        ],
        default="available",
    )
    cumulative_return = None
    cumulative_return_pct = None
    if cumulative_status == "available" and current_total_assets is not None and net_principal is not None:
        cumulative_return = current_total_assets - net_principal
        cumulative_return_pct = round(cumulative_return / net_principal * 100, 6) if abs(net_principal) > 1e-9 else None

    dividend_income = income_summary_total(income_summary, income_type="dividend")
    interest_income = income_summary_total(income_summary, income_type="interest")
    distribution_income = income_summary_total(income_summary, income_type="distribution")
    income_values = [dividend_income, interest_income, distribution_income]
    income_total = float(sum(value for value in income_values if value is not None)) if all(value is not None for value in income_values) else None

    realized_gross = summary_number(rec, "realized_trade_pnl_gross_krw")
    realized_net = summary_number(rec, "realized_trade_pnl_net_krw")
    realized_gain = summary_number(rec, "realized_gain_krw")
    realized_loss = summary_number(rec, "realized_loss_krw")
    unrealized = summary_number(rec, "unrealized_pnl_krw") if asset_values_available else None
    fee_expense = summary_number(rec, "fee_expense_krw")
    tax_expense = summary_number(rec, "tax_expense_krw")

    explain_status = status_from_list(
        [
            realized_status if realized_status != "available" else "",
            income_status if income_status != "available" else "",
            fx_status if fx_status != "available" else "",
        ],
        default="available",
    )
    explain_inputs = [
        realized_gross,
        unrealized,
        dividend_income,
        interest_income,
        distribution_income,
        fee_expense,
        tax_expense,
    ]
    explained_profit = None
    if explain_status == "available" and all(value is not None for value in explain_inputs):
        explained_profit = (
            realized_gross
            + unrealized
            + dividend_income
            + interest_income
            + distribution_income
            - fee_expense
            - tax_expense
        )
    reconciliation_residual = (
        cumulative_return - explained_profit
        if cumulative_return is not None and explained_profit is not None
        else None
    )
    performance_status = status_from_list(
        [
            cumulative_status if cumulative_status != "available" else "",
            explain_status if explain_status != "available" else "",
        ],
        default="available",
    )

    values = {
        "net_external_principal_krw": net_principal,
        "external_deposit_krw": summary_number(rec, "external_deposit_krw"),
        "external_withdrawal_krw": summary_number(rec, "external_withdrawal_krw"),
        "current_total_assets_krw": current_total_assets,
        "current_cash_krw": current_cash,
        "current_holding_assets_krw": current_holding_assets,
        "cumulative_return_krw": cumulative_return,
        "cumulative_return_pct": cumulative_return_pct,
        "realized_trade_pnl_gross_krw": realized_gross,
        "realized_trade_pnl_net_krw": realized_net,
        "realized_gain_krw": realized_gain,
        "realized_loss_krw": realized_loss,
        "realized_loss_abs_krw": abs(realized_loss) if realized_loss is not None else None,
        "unrealized_pnl_krw": unrealized,
        "dividend_income_krw": dividend_income,
        "interest_income_krw": interest_income,
        "distribution_income_krw": distribution_income,
        "income_total_krw": income_total,
        "fee_expense_krw": fee_expense,
        "tax_expense_krw": tax_expense,
        "explained_profit_krw": explained_profit,
        "reconciliation_residual_krw": reconciliation_residual,
        "performance_status": performance_status,
        "realized_pnl_status": realized_status,
        "income_status": income_status,
        "fx_status": fx_status,
        "income_fx_status": income_fx_status,
        "income_fx_missing_row_count": income_summary_field_sum(income_summary, "fx_missing_row_count"),
        "income_fx_source_summary": income_summary_source_text(income_summary),
        "fx_rate_requirement_row_count": len(fx_requirements),
        "amount_review_needed_row_count": summary_number(rec, "amount_review_needed_row_count") or 0,
    }
    return summary_metric_rows({metric: values.get(metric) for metric in PERFORMANCE_SUMMARY_METRICS})


def build_performance_history(
    performance_summary: pd.DataFrame,
    existing_history: pd.DataFrame | None = None,
    snapshot_date: date | None = None,
) -> pd.DataFrame:
    existing_history = existing_history if existing_history is not None else pd.DataFrame()
    snapshot_date = snapshot_date or date.today()
    metrics = summary_to_dict(performance_summary)
    if not metrics:
        return existing_history.reindex(columns=PERFORMANCE_HISTORY_COLUMNS)

    snapshot_month = snapshot_date.isoformat()[:7]
    current_row = {
        "snapshot_month": snapshot_month,
        "snapshot_date": snapshot_date.isoformat(),
        "cumulative_principal_krw": summary_number(metrics, "net_external_principal_krw"),
        "current_total_assets_krw": summary_number(metrics, "current_total_assets_krw"),
        "cumulative_return_krw": summary_number(metrics, "cumulative_return_krw"),
        "cumulative_return_pct": summary_number(metrics, "cumulative_return_pct"),
        "performance_status": text_value(metrics.get("performance_status")) or "unavailable",
    }

    history = existing_history.copy()
    if history.empty:
        history = pd.DataFrame(columns=PERFORMANCE_HISTORY_COLUMNS)
    else:
        history = history.reindex(columns=PERFORMANCE_HISTORY_COLUMNS)
        if "snapshot_month" in history.columns:
            history = history[history["snapshot_month"].fillna("").astype(str) != snapshot_month]

    history = pd.concat([history, pd.DataFrame([current_row])], ignore_index=True)
    history = history[history["snapshot_month"].fillna("").astype(str).str.len() == 7]
    return history.sort_values(["snapshot_month", "snapshot_date"], ascending=True).reindex(columns=PERFORMANCE_HISTORY_COLUMNS).reset_index(drop=True)


def trade_identity(row: pd.Series) -> tuple[str, str, str]:
    ticker = text_value(row.get("ticker")).upper()
    name = text_value(row.get("security_name")).upper()
    identity = ticker or (f"NAME:{name}" if name else "")
    return (
        text_value(row.get("account_type")).lower(),
        text_value(row.get("market")).upper(),
        identity,
    )


def current_holding_identities(holdings: pd.DataFrame) -> set[tuple[str, str, str]]:
    identities: set[tuple[str, str, str]] = set()
    if holdings.empty:
        return identities
    for _, row in holdings.iterrows():
        if text_value(row.get("asset_type")).lower() == "cash":
            continue
        identity = trade_identity(row)
        if identity[2]:
            identities.add(identity)
    return identities


def trade_amount_krw(row: pd.Series) -> tuple[float | None, str, str]:
    review_status = row_review_status(row) or "ok"
    amount = first_number(row, ["trade_amount_krw", "amount_krw", "settlement_amount_krw"])
    if amount is None and row_currency(row) == "KRW":
        amount = first_number(row, ["trade_amount", "amount_native", "settlement_amount"])
    if review_status != "ok":
        return None, review_status, text_value(row.get("amount_review_reason"))
    if amount is None:
        status = "fx_missing" if row_currency(row) and row_currency(row) != "KRW" else "unit_ambiguous"
        return None, status, "trade amount has no KRW-normalized value"
    return abs(amount), "ok", ""


def trade_money_amounts(
    row: pd.Series,
    native_fields: list[str],
    krw_fields: list[str],
    *,
    default_zero: bool = False,
    fx_rates: pd.DataFrame | None = None,
    use_case: str = "realized_pnl_trade_settlement",
) -> dict[str, Any]:
    currency = row_currency(row)
    review_status = row_review_status(row) or "ok"
    native = first_nonzero_number(row, native_fields)
    krw = first_nonzero_number(row, krw_fields)

    if default_zero and native is None and krw is None:
        native = 0.0
        krw = 0.0
    if native is None and currency == "KRW" and krw is not None:
        native = krw
    if krw is None and currency == "KRW" and native is not None:
        krw = native

    status = "ok"
    reason = ""
    resolved_fx_status = ""
    if (
        fx_rates is not None
        and currency
        and currency != "KRW"
        and native is not None
        and krw is None
        and review_status in {"", "ok", "fx_missing", "missing"}
    ):
        fx_row = row.copy()
        fx_row["amount_native"] = native
        fx_row["amount_krw"] = ""
        resolved = resolve_fx_rate(fx_row, fx_rates, use_case)
        if resolved.get("status") == "ok":
            krw = first_number(pd.Series(resolved), ["amount_krw"])
            resolved_fx_status = text_value(resolved.get("fx_status")) or "available"
            review_status = "ok"
        elif resolved.get("status") == "fx_missing":
            review_status = "fx_missing"
            reason = text_value(resolved.get("missing_reason"))

    if not currency or len(currency) != 3 or not currency.isalpha():
        status = "currency_ambiguous"
        reason = "trade currency is missing or invalid"
    elif native is None and krw is None:
        status = "unit_ambiguous"
        reason = "trade amount has no native or KRW value"
    elif review_status != "ok":
        status = review_status
        reason = text_value(row.get("amount_review_reason"))
    elif currency != "KRW" and krw is None:
        status = "fx_missing"
        reason = "trade amount has no KRW-normalized value"
    if currency != "KRW" and status != "ok" and native not in {None, 0.0} and krw == 0.0:
        krw = None

    if currency == "KRW":
        fx_status = "not_required"
    elif resolved_fx_status:
        fx_status = resolved_fx_status
    elif krw is not None:
        fx_status = "available"
    elif status == "fx_missing":
        fx_status = "fx_missing"
    else:
        fx_status = status

    return {
        "native": abs(native) if native is not None else None,
        "krw": abs(krw) if krw is not None else None,
        "status": status,
        "fx_status": fx_status,
        "reason": reason,
    }


def trade_amounts(row: pd.Series, fx_rates: pd.DataFrame | None = None) -> dict[str, Any]:
    return trade_money_amounts(
        row,
        ["trade_amount_native", "amount_native", "trade_amount", "settlement_amount_native", "settlement_amount"],
        ["trade_amount_krw", "amount_krw", "settlement_amount_krw"],
        fx_rates=fx_rates,
    )


def trade_fee_amounts(row: pd.Series, fx_rates: pd.DataFrame | None = None) -> dict[str, Any]:
    return trade_money_amounts(row, ["fee_native", "fee"], ["fee_krw"], default_zero=True, fx_rates=fx_rates)


def trade_tax_amounts(row: pd.Series, fx_rates: pd.DataFrame | None = None) -> dict[str, Any]:
    return trade_money_amounts(row, ["tax_native", "tax"], ["tax_krw"], default_zero=True, fx_rates=fx_rates)


def fx_status_from_list(statuses: list[str]) -> str:
    cleaned = [status for status in statuses if status and status != "not_required"]
    if not cleaned:
        return "not_required"
    for status in ["currency_ambiguous", "unit_ambiguous", "fx_missing", "available"]:
        if status in cleaned:
            return status
    return cleaned[0]


def native_status_for_amount(amount: dict[str, Any]) -> str:
    status = text_value(amount.get("status")).lower() or "ok"
    if amount.get("native") is None:
        return "unit_ambiguous" if status in {"ok", "fx_missing"} else status
    if status == "fx_missing":
        return "ok"
    return status


def trade_quantity(row: pd.Series) -> float | None:
    quantity = first_number(row, ["quantity"])
    if quantity is None or abs(quantity) <= 1e-9:
        return None
    return abs(quantity)


def sorted_trade_rows(transactions: pd.DataFrame) -> pd.DataFrame:
    if transactions.empty or "transaction_type" not in transactions.columns:
        return pd.DataFrame(columns=transactions.columns)
    view = transactions.copy()
    tx_type = view["transaction_type"].fillna("").astype(str).str.lower()
    role = view.get("cashflow_role", pd.Series("", index=view.index)).fillna("").astype(str).str.lower()
    view = view[tx_type.isin({"buy", "sell"}) & role.isin({"", "trade_settlement"})].copy()
    if view.empty:
        return view
    view["_trade_order"] = range(len(view))
    view["_trade_date_sort"] = pd.to_datetime(view.get("trade_date", ""), errors="coerce")
    view["_trade_time_sort"] = view.get("trade_time", "").fillna("").astype(str) if "trade_time" in view.columns else ""
    return view.sort_values(["_trade_date_sort", "_trade_time_sort", "_trade_order"], na_position="last")


def transaction_history_source_available(processed_dir: Path, transactions: pd.DataFrame) -> bool:
    if not sorted_trade_rows(transactions).empty:
        return True
    source_index = load_csv(processed_dir / "source_file_index.csv")
    if source_index.empty or "source_file_type" not in source_index.columns:
        return False
    source_types = source_index["source_file_type"].fillna("").astype(str).str.lower()
    return bool(source_types.isin({"transaction_history", "transactions"}).any())


def realized_pnl_ledger(transactions: pd.DataFrame, holdings: pd.DataFrame, fx_rates: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build realized PnL with FIFO lot matching from imported buy/sell rows."""
    trades = sorted_trade_rows(transactions)
    if trades.empty:
        return pd.DataFrame(columns=REALIZED_PNL_COLUMNS)

    current_identities = current_holding_identities(holdings)
    records: list[dict[str, Any]] = []
    for _identity, group in trades.groupby(trades.apply(trade_identity, axis=1), sort=False):
        lots: list[dict[str, Any]] = []
        group_records: list[dict[str, Any]] = []
        for _, row in group.iterrows():
            tx_type = text_value(row.get("transaction_type")).lower()
            quantity = trade_quantity(row)
            amount = trade_amounts(row, fx_rates=fx_rates)
            fee = trade_fee_amounts(row, fx_rates=fx_rates)
            tax = trade_tax_amounts(row, fx_rates=fx_rates)
            if tx_type == "buy":
                native_status = native_status_for_amount(amount)
                krw_status = amount["status"] if amount["status"] != "ok" or quantity is None else "ok"
                lots.append({
                    "remaining_qty": quantity or 0.0,
                    "unit_cost_native": (amount["native"] / quantity) if quantity and amount["native"] is not None and native_status == "ok" else None,
                    "unit_cost_krw": (amount["krw"] / quantity) if quantity and amount["krw"] is not None and krw_status == "ok" else None,
                    "native_status": native_status if quantity is not None else "unit_ambiguous",
                    "krw_status": krw_status if quantity is not None else "unit_ambiguous",
                    "fx_status": amount["fx_status"],
                    "reason": amount["reason"] if amount["status"] != "ok" else ("buy quantity missing" if quantity is None else ""),
                })
                continue
            if tx_type != "sell":
                continue

            official_statuses: list[str] = []
            native_statuses: list[str] = []
            fx_statuses: list[str] = []
            reasons: list[str] = []
            matched_cost_native = 0.0
            matched_cost_krw = 0.0
            remaining = quantity or 0.0
            if quantity is None:
                official_statuses.append("unit_ambiguous")
                native_statuses.append("unit_ambiguous")
                reasons.append("sell quantity missing")
            amount_native_status = native_status_for_amount(amount)
            if amount_native_status != "ok":
                native_statuses.append(amount_native_status)
            if amount["status"] != "ok" or amount["krw"] is None:
                official_statuses.append(amount["status"])
            if amount["fx_status"]:
                fx_statuses.append(amount["fx_status"])
            if amount["reason"]:
                reasons.append(amount["reason"])

            for label, extra_amount in [("fee", fee), ("tax", tax)]:
                has_amount = (extra_amount["native"] or 0.0) != 0.0 or (extra_amount["krw"] or 0.0) != 0.0
                native_status = native_status_for_amount(extra_amount)
                if has_amount and native_status != "ok":
                    native_statuses.append(native_status)
                if has_amount and (extra_amount["status"] != "ok" or extra_amount["krw"] is None):
                    official_statuses.append(extra_amount["status"])
                if has_amount and extra_amount["fx_status"]:
                    fx_statuses.append(extra_amount["fx_status"])
                if has_amount and extra_amount["reason"]:
                    reasons.append(f"{label}: {extra_amount['reason']}")

            lot_index = 0
            # Consume buy lots in insertion order; this is the realized PnL cost-basis contract.
            while remaining > 1e-9 and lot_index < len(lots):
                lot = lots[lot_index]
                lot_qty = float(lot.get("remaining_qty") or 0.0)
                if lot_qty <= 1e-9:
                    lot_index += 1
                    continue
                matched_qty = min(remaining, lot_qty)
                if lot.get("unit_cost_native") is None or lot.get("native_status") != "ok":
                    native_statuses.append(text_value(lot.get("native_status")) or "unit_ambiguous")
                    if lot.get("reason"):
                        reasons.append(text_value(lot.get("reason")))
                else:
                    matched_cost_native += float(lot["unit_cost_native"]) * matched_qty
                if lot.get("unit_cost_krw") is None or lot.get("krw_status") != "ok":
                    official_statuses.append(text_value(lot.get("krw_status")) or "unit_ambiguous")
                    if lot.get("fx_status"):
                        fx_statuses.append(text_value(lot.get("fx_status")))
                    if lot.get("reason"):
                        reasons.append(text_value(lot.get("reason")))
                else:
                    matched_cost_krw += float(lot["unit_cost_krw"]) * matched_qty
                lot["remaining_qty"] = lot_qty - matched_qty
                remaining -= matched_qty
                if lot["remaining_qty"] <= 1e-9:
                    lot_index += 1

            if remaining > 1e-9:
                official_statuses.append("lot_missing")
                native_statuses.append("lot_missing")
                reasons.append("sell quantity exceeds matched buy lots in imported transaction history")

            status = status_from_list(official_statuses, default="ok")
            fx_status = fx_status_from_list(fx_statuses)
            proceeds_native = amount["native"]
            proceeds_krw = amount["krw"]
            fee_native = fee["native"] if fee["native"] is not None else 0.0
            fee_krw = fee["krw"] if fee["krw"] is not None else None
            tax_native = tax["native"] if tax["native"] is not None else 0.0
            tax_krw = tax["krw"] if tax["krw"] is not None else None
            native_ready = (
                not native_statuses
                and proceeds_native is not None
                and fee_native is not None
                and tax_native is not None
            )
            krw_ready = status == "ok" and proceeds_krw is not None and fee_krw is not None and tax_krw is not None
            gross_native = proceeds_native - matched_cost_native if native_ready else None
            gross_krw = proceeds_krw - matched_cost_krw if krw_ready else None
            net_native = gross_native - fee_native - tax_native if gross_native is not None else None
            net_krw = gross_krw - fee_krw - tax_krw if gross_krw is not None else None
            result_basis = gross_krw if gross_krw is not None else gross_native
            group_records.append({
                "account_type": row.get("account_type", ""),
                "market": row.get("market", ""),
                "ticker": row.get("ticker", ""),
                "security_name": row.get("security_name", ""),
                "currency_native": row_currency(row),
                "sell_date": row.get("trade_date", ""),
                "sell_import_id": row.get("import_id", ""),
                "quantity_sold": quantity if quantity is not None else "",
                "proceeds_native": proceeds_native if proceeds_native is not None else "",
                "proceeds_krw": proceeds_krw if proceeds_krw is not None else "",
                "cost_basis_native": matched_cost_native if native_ready else "",
                "cost_basis_krw": matched_cost_krw if krw_ready else "",
                "fee_native": fee_native,
                "fee_krw": fee_krw if fee_krw is not None else "",
                "tax_native": tax_native,
                "tax_krw": tax_krw if tax_krw is not None else "",
                "realized_trade_pnl_gross_native": gross_native if gross_native is not None else "",
                "realized_trade_pnl_gross_krw": gross_krw if gross_krw is not None else "",
                "realized_trade_pnl_net_native": net_native if net_native is not None else "",
                "realized_trade_pnl_net_krw": net_krw if net_krw is not None else "",
                "realized_result": "gain" if result_basis is not None and result_basis >= 0 else ("loss" if result_basis is not None else ""),
                "position_status": "",
                "cost_basis_method": REALIZED_COST_BASIS_METHOD,
                "amount_review_status": status,
                "fx_status": fx_status,
                "amount_review_reason": "; ".join(dict.fromkeys(reason for reason in reasons if reason)),
                "source_file": row.get("source_file", ""),
                "_identity": trade_identity(row),
            })

        final_remaining = sum(float(lot.get("remaining_qty") or 0.0) for lot in lots)
        for record in group_records:
            record["position_status"] = (
                "current_or_open"
                if final_remaining > 1e-9 or record["_identity"] in current_identities
                else "closed"
            )
            records.append(record)

    if not records:
        return pd.DataFrame(columns=REALIZED_PNL_COLUMNS)
    return pd.DataFrame(records).drop(columns=["_identity"], errors="ignore").reindex(columns=REALIZED_PNL_COLUMNS)


def realized_pnl_summary(
    ledger: pd.DataFrame,
    transaction_source_available: bool,
) -> dict[str, Any]:
    if ledger.empty:
        if transaction_source_available:
            return {
                "realized_pnl_krw": 0.0,
                "realized_trade_pnl_gross_krw": 0.0,
                "realized_trade_pnl_net_krw": 0.0,
                "realized_gain_krw": 0.0,
                "realized_loss_krw": 0.0,
                "realized_cost_basis_method": REALIZED_COST_BASIS_METHOD,
                "realized_pnl_basis": REALIZED_PNL_BASIS,
                "realized_pnl_status": "available",
                "realized_pnl_row_count": 0,
                "realized_pnl_unavailable_row_count": 0,
                "realized_closed_position_count": 0,
            }
        return {
            "realized_pnl_krw": None,
            "realized_trade_pnl_gross_krw": None,
            "realized_trade_pnl_net_krw": None,
            "realized_gain_krw": None,
            "realized_loss_krw": None,
            "realized_cost_basis_method": REALIZED_COST_BASIS_METHOD,
            "realized_pnl_basis": REALIZED_PNL_BASIS,
            "realized_pnl_status": "transaction_history_missing",
            "realized_pnl_row_count": 0,
            "realized_pnl_unavailable_row_count": 0,
            "realized_closed_position_count": 0,
        }

    status = ledger.get("amount_review_status", pd.Series("", index=ledger.index)).fillna("").astype(str).str.lower()
    unavailable = status.ne("ok")
    if unavailable.any():
        blocking = [value for value in status[unavailable].tolist() if value]
        return {
            "realized_pnl_krw": None,
            "realized_trade_pnl_gross_krw": None,
            "realized_trade_pnl_net_krw": None,
            "realized_gain_krw": None,
            "realized_loss_krw": None,
            "realized_cost_basis_method": REALIZED_COST_BASIS_METHOD,
            "realized_pnl_basis": REALIZED_PNL_BASIS,
            "realized_pnl_status": status_from_list(blocking, default="unavailable"),
            "realized_pnl_row_count": len(ledger),
            "realized_pnl_unavailable_row_count": int(unavailable.sum()),
            "realized_closed_position_count": int(ledger.get("position_status", pd.Series("", index=ledger.index)).fillna("").astype(str).str.lower().eq("closed").sum()),
        }

    gross = pd.to_numeric(ledger.get("realized_trade_pnl_gross_krw", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    net = pd.to_numeric(ledger.get("realized_trade_pnl_net_krw", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    return {
        "realized_pnl_krw": float(gross.sum()),
        "realized_trade_pnl_gross_krw": float(gross.sum()),
        "realized_trade_pnl_net_krw": float(net.sum()),
        "realized_gain_krw": float(gross[gross > 0].sum()),
        "realized_loss_krw": float(gross[gross < 0].sum()),
        "realized_cost_basis_method": REALIZED_COST_BASIS_METHOD,
        "realized_pnl_basis": REALIZED_PNL_BASIS,
        "realized_pnl_status": "available",
        "realized_pnl_row_count": len(ledger),
        "realized_pnl_unavailable_row_count": 0,
        "realized_closed_position_count": int(ledger.get("position_status", pd.Series("", index=ledger.index)).fillna("").astype(str).str.lower().eq("closed").sum()),
    }


def unrealized_pnl_krw(holdings: pd.DataFrame) -> float:
    if holdings.empty:
        return 0.0
    total = 0.0
    krw_field_present = "unrealized_pnl_krw" in holdings.columns
    for _, row in holdings.iterrows():
        amount = first_number(row, ["unrealized_pnl_krw"])
        if amount is None and (not krw_field_present or row_currency(row) == "KRW"):
            amount = first_number(row, ["unrealized_pnl"])
        if amount is not None:
            total += amount
    return total


def review_status_counts(dfs: list[pd.DataFrame], seed_counts: dict[str, int] | None = None) -> dict[str, int]:
    counts = {
        "fx_missing": 0,
        "currency_ambiguous": 0,
        "unit_ambiguous": 0,
        "amount_review_needed": 0,
    }
    if seed_counts:
        for key, value in seed_counts.items():
            counts[key] = counts.get(key, 0) + int(value or 0)
    for df in dfs:
        if df.empty:
            continue
        for _, row in df.iterrows():
            status = row_review_status(row)
            if status in counts:
                counts[status] += 1
            if status in REVIEW_NEEDED_STATUSES:
                counts["amount_review_needed"] += 1
    return counts


def fx_event_key(row: pd.Series, idx: int) -> str:
    event_id = text_value(row.get("fx_event_id"))
    return event_id if event_id else f"__row_{idx}"


def fx_event_counts(fx_events: pd.DataFrame) -> dict[str, int]:
    counts = {
        "fx_event_id_count": 0,
        "fx_event_leg_count": 0,
        "fx_paired_event_count": 0,
        "fx_partial_event_count": 0,
        "fx_unpaired_event_count": 0,
        "fx_needs_review_event_count": 0,
        "fx_unpaired_or_needs_review_row_count": 0,
        "fx_internal_transfer_row_count": 0,
    }
    if fx_events.empty:
        return counts

    event_ids: set[str] = set()
    events_by_status = {
        "paired": set(),
        "partial": set(),
        "unpaired": set(),
        "needs_review": set(),
    }
    unpaired_or_needs_review_rows = 0
    internal_transfer_rows = 0

    for idx, row in fx_events.reset_index(drop=True).iterrows():
        event_key = fx_event_key(row, idx)
        event_ids.add(event_key)
        pair_status = text_value(row.get("fx_pair_status")).lower()
        amount_status = row_review_status(row)
        if pair_status in events_by_status:
            events_by_status[pair_status].add(event_key)
        if pair_status in {"unpaired", "needs_review"} or amount_status == "needs_review":
            unpaired_or_needs_review_rows += 1
        role = text_value(row.get("cashflow_role")).lower()
        if role == "internal_fx_exchange" or truthy_value(row.get("is_internal_transfer")):
            internal_transfer_rows += 1

    counts["fx_event_id_count"] = len(event_ids)
    counts["fx_event_leg_count"] = len(fx_events)
    counts["fx_paired_event_count"] = len(events_by_status["paired"])
    counts["fx_partial_event_count"] = len(events_by_status["partial"])
    counts["fx_unpaired_event_count"] = len(events_by_status["unpaired"])
    counts["fx_needs_review_event_count"] = len(events_by_status["needs_review"])
    counts["fx_unpaired_or_needs_review_row_count"] = unpaired_or_needs_review_rows
    counts["fx_internal_transfer_row_count"] = internal_transfer_rows
    return counts


def build_reconciliation_summary(
    processed_dir: Path,
    holdings: pd.DataFrame,
    realized_ledger: pd.DataFrame | None = None,
    income: pd.DataFrame | None = None,
    expenses: pd.DataFrame | None = None,
    transactions: pd.DataFrame | None = None,
) -> pd.DataFrame:
    cashflows_path = processed_dir / "processed_cashflows.csv"
    cashflows = load_csv(cashflows_path)
    income = income if income is not None else load_csv(processed_dir / "processed_income.csv")
    expenses = expenses if expenses is not None else load_csv(processed_dir / "processed_expenses.csv")
    fx_events = load_csv(processed_dir / "processed_fx_events.csv")
    transactions = transactions if transactions is not None else load_csv(processed_dir / "processed_transactions.csv")

    asset_total, current_cash, current_holding_assets, asset_status, asset_status_counts = total_assets_breakdown_krw(holdings)
    deposits, withdrawals, net_principal, principal_status, principal_status_counts = net_external_principal_krw(cashflows, source_available=cashflows_path.exists())
    if realized_ledger is None:
        realized_ledger = realized_pnl_ledger(transactions, holdings)
    realized_metrics = realized_pnl_summary(
        realized_ledger,
        transaction_source_available=transaction_history_source_available(processed_dir, transactions),
    )

    total_return = None
    total_return_pct = None
    if asset_status == "available" and principal_status == "available" and asset_total is not None and net_principal is not None:
        total_return = asset_total - net_principal
        total_return_pct = round(total_return / net_principal * 100, 6) if abs(net_principal) > 1e-9 else None
        total_return_status = "available"
    elif asset_status != "available":
        total_return_status = asset_status
    else:
        total_return_status = principal_status

    unrealized = unrealized_pnl_krw(holdings)
    dividend_income = ok_amount_sum(income, "income_type", {"dividend"})
    interest_income = ok_amount_sum(income, "income_type", {"interest"})
    distribution_income = ok_amount_sum(income, "income_type", {"distribution"})
    fee_expense = ok_amount_sum(expenses, "expense_type", {"fee"})
    tax_expense = ok_amount_sum(expenses, "expense_type", {"tax"})

    seeded_counts = asset_status_counts.copy()
    for key, value in principal_status_counts.items():
        seeded_counts[key] = seeded_counts.get(key, 0) + int(value or 0)
    counts = review_status_counts([holdings, cashflows, income, expenses, fx_events], seeded_counts)
    if realized_metrics["realized_pnl_status"] in counts:
        counts[realized_metrics["realized_pnl_status"]] += int(realized_metrics["realized_pnl_unavailable_row_count"] or 0)
    if realized_metrics["realized_pnl_status"] in REVIEW_NEEDED_STATUSES:
        counts["amount_review_needed"] += int(realized_metrics["realized_pnl_unavailable_row_count"] or 0)
    fx_counts = fx_event_counts(fx_events)

    realized_pnl = realized_metrics["realized_trade_pnl_gross_krw"]
    explained_status_inputs = [
        realized_metrics["realized_pnl_status"] if realized_metrics["realized_pnl_status"] != "available" else "",
        "currency_ambiguous" if counts["currency_ambiguous"] > 0 else "",
        "unit_ambiguous" if counts["unit_ambiguous"] > 0 else "",
        "fx_missing" if counts["fx_missing"] > 0 else "",
        "needs_review" if counts["amount_review_needed"] > 0 else "",
    ]
    explained_profit = None
    explained_profit_status = status_from_list(explained_status_inputs, default="available")
    explained_inputs = [
        unrealized,
        realized_pnl,
        dividend_income,
        interest_income,
        distribution_income,
        fee_expense,
        tax_expense,
    ]
    if explained_profit_status == "available" and all(value is not None for value in explained_inputs):
        explained_profit = (
            unrealized
            + realized_pnl
            + dividend_income
            + interest_income
            + distribution_income
            - fee_expense
            - tax_expense
        )

    residual = None
    residual_status = "unavailable"
    if total_return is not None and explained_profit_status == "available":
        residual = total_return - explained_profit
        residual_status = "available"

    return summary_metric_rows({
        "reconciliation_summary_role": RECONCILIATION_SUMMARY_ROLE,
        "total_return_alias_of": TOTAL_RETURN_ALIAS_OF,
        "total_return_pct_alias_of": TOTAL_RETURN_PCT_ALIAS_OF,
        "explained_profit_formula": EXPLAINED_PROFIT_FORMULA,
        "fee_tax_treatment": FEE_TAX_TREATMENT,
        "fx_pnl_treatment": FX_PNL_TREATMENT,
        "total_assets_krw": asset_total,
        "total_assets_status": asset_status,
        "current_cash_krw": current_cash,
        "current_holding_assets_krw": current_holding_assets,
        "external_deposit_krw": deposits,
        "external_withdrawal_krw": withdrawals,
        "net_external_principal_krw": net_principal,
        "net_external_principal_status": principal_status,
        "total_return_krw": total_return,
        "total_return_pct": total_return_pct,
        "total_return_status": total_return_status,
        "unrealized_pnl_krw": unrealized,
        "realized_pnl_krw": realized_metrics["realized_pnl_krw"],
        "realized_trade_pnl_gross_krw": realized_metrics["realized_trade_pnl_gross_krw"],
        "realized_trade_pnl_net_krw": realized_metrics["realized_trade_pnl_net_krw"],
        "realized_gain_krw": realized_metrics["realized_gain_krw"],
        "realized_loss_krw": realized_metrics["realized_loss_krw"],
        "realized_cost_basis_method": realized_metrics["realized_cost_basis_method"],
        "realized_pnl_basis": realized_metrics["realized_pnl_basis"],
        "realized_pnl_status": realized_metrics["realized_pnl_status"],
        "realized_pnl_row_count": realized_metrics["realized_pnl_row_count"],
        "realized_pnl_unavailable_row_count": realized_metrics["realized_pnl_unavailable_row_count"],
        "realized_closed_position_count": realized_metrics["realized_closed_position_count"],
        "dividend_income_krw": dividend_income,
        "interest_income_krw": interest_income,
        "distribution_income_krw": distribution_income,
        "fee_expense_krw": fee_expense,
        "tax_expense_krw": tax_expense,
        "fx_pnl_status": "unavailable",
        "explained_profit_krw": explained_profit,
        "explained_profit_status": explained_profit_status,
        "residual_krw": residual,
        "residual_status": residual_status,
        "fx_missing_row_count": counts["fx_missing"],
        "currency_ambiguous_row_count": counts["currency_ambiguous"],
        "unit_ambiguous_row_count": counts["unit_ambiguous"],
        "amount_review_needed_row_count": counts["amount_review_needed"],
        "fx_event_id_count": fx_counts["fx_event_id_count"],
        "fx_event_leg_count": fx_counts["fx_event_leg_count"],
        "fx_paired_event_count": fx_counts["fx_paired_event_count"],
        "fx_partial_event_count": fx_counts["fx_partial_event_count"],
        "fx_unpaired_event_count": fx_counts["fx_unpaired_event_count"],
        "fx_needs_review_event_count": fx_counts["fx_needs_review_event_count"],
        "fx_unpaired_or_needs_review_row_count": fx_counts["fx_unpaired_or_needs_review_row_count"],
        "fx_internal_transfer_row_count": fx_counts["fx_internal_transfer_row_count"],
    })


def portfolio_summary_rows(
    total_value: Any,
    holding_count: int,
    original_holding_count: int,
    history_count: int,
    loss_count: int,
    leveraged_count: int,
    high_weight_count: int,
    raw_file_count: int,
    transaction_file_count: int,
    holdings_file_count: int,
    balance_data_available: bool,
    total_cost: Any = "",
    total_unrealized_pnl: Any = "",
    portfolio_pnl_pct: Any = "",
    leveraged_etf_total_weight_pct: Any = "",
    dedupe_candidate_rows: int = 0,
    dedupe_retained_rows: int = 0,
    dedupe_excluded_rows: int = 0,
    dedupe_excluded_evaluation_amount: float = 0.0,
) -> pd.DataFrame:
    if balance_data_available and holding_count:
        basis = "balance_file_evaluation_amount_sum"
        status = "available"
        estimated = False
        warning = ""
    elif balance_data_available:
        basis = "balance_file_present_but_no_current_holdings"
        status = "empty"
        estimated = False
        warning = "잔고 파일은 감지됐지만 현재 보유종목이 없습니다."
    else:
        basis = "unknown_no_balance_file"
        status = "unknown"
        estimated = False
        warning = "잔고자료 미반영: 종합잔고/ISA잔고/해외증권잔고 파일이 없어 포트폴리오 가치, 평가손익, 수익률을 산출하지 않았습니다."
    return pd.DataFrame([
        {"metric": "total_portfolio_value", "value": total_value},
        {"metric": "total_cost", "value": total_cost},
        {"metric": "total_unrealized_pnl", "value": total_unrealized_pnl},
        {"metric": "pnl_pct", "value": portfolio_pnl_pct},
        {"metric": "leveraged_etf_total_weight_pct", "value": leveraged_etf_total_weight_pct},
        {"metric": "total_portfolio_value_status", "value": status},
        {"metric": "total_portfolio_value_basis", "value": basis},
        {"metric": "currency_normalization_status", "value": CURRENCY_NORMALIZATION_STATUS},
        {"metric": "amount_unit_classification_status", "value": AMOUNT_UNIT_CLASSIFICATION_STATUS},
        {"metric": "profit_result_status", "value": PROFIT_RESULT_STATUS},
        {"metric": "reconciliation_status", "value": RECONCILIATION_STATUS},
        {"metric": "preliminary_reconciliation_warning", "value": PRELIMINARY_RECONCILIATION_WARNING},
        {"metric": "portfolio_summary_estimated", "value": estimated},
        {"metric": "balance_data_available", "value": balance_data_available},
        {"metric": "raw_file_count", "value": raw_file_count},
        {"metric": "transaction_history_file_count", "value": transaction_file_count},
        {"metric": "holdings_file_count", "value": holdings_file_count},
        {"metric": "holding_count", "value": holding_count},
        {"metric": "original_holding_rows_before_current_filter", "value": original_holding_count},
        {"metric": "holding_dedupe_status", "value": "applied" if dedupe_excluded_rows else "none"},
        {"metric": "holding_dedupe_candidate_rows", "value": dedupe_candidate_rows},
        {"metric": "holding_dedupe_retained_rows", "value": dedupe_retained_rows},
        {"metric": "holding_dedupe_excluded_rows", "value": dedupe_excluded_rows},
        {"metric": "holding_dedupe_excluded_evaluation_amount", "value": dedupe_excluded_evaluation_amount},
        {"metric": "history_queue_count", "value": history_count},
        {"metric": "loss_review_required_count", "value": loss_count},
        {"metric": "leveraged_etf_count", "value": leveraged_count},
        {"metric": "high_weight_count", "value": high_weight_count},
        {"metric": "data_quality_warning", "value": warning},
    ], columns=SUMMARY_COLUMNS)


def build_portfolio_outputs(processed_dir: Path, vault_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    holdings = load_csv(processed_dir / "processed_holdings.csv")
    transactions = load_csv(processed_dir / "processed_transactions.csv")
    raw_file_count, transaction_file_count, holdings_file_count = source_type_counts(processed_dir)
    balance_data_available = holdings_file_count > 0 or not holdings.empty
    if holdings.empty:
        summary = portfolio_summary_rows(
            total_value="",
            holding_count=0,
            original_holding_count=0,
            history_count=0,
            loss_count=0,
            leveraged_count=0,
            high_weight_count=0,
            raw_file_count=raw_file_count,
            transaction_file_count=transaction_file_count,
            holdings_file_count=holdings_file_count,
            balance_data_available=balance_data_available,
        )
        return summary, pd.DataFrame(columns=NORMALIZED_COLUMNS), pd.DataFrame(columns=RISK_COLUMNS), pd.DataFrame(columns=REVIEW_COLUMNS), pd.DataFrame(columns=HISTORY_COLUMNS)
    holdings["ticker"] = holdings.get("ticker", "").astype(str)
    holdings = holdings[~holdings["ticker"].str.lower().isin(["", "nan", "none"])].copy()
    holdings = remove_overlapping_overseas_holdings(holdings)
    dedupe_metrics = holding_dedupe_metrics(holdings)
    if holdings.empty:
        summary = portfolio_summary_rows(
            total_value="",
            holding_count=0,
            original_holding_count=0,
            history_count=0,
            loss_count=0,
            leveraged_count=0,
            high_weight_count=0,
            raw_file_count=raw_file_count,
            transaction_file_count=transaction_file_count,
            holdings_file_count=holdings_file_count,
            balance_data_available=balance_data_available,
            dedupe_candidate_rows=dedupe_metrics["candidate_rows"],
            dedupe_retained_rows=dedupe_metrics["retained_rows"],
            dedupe_excluded_rows=dedupe_metrics["excluded_rows"],
            dedupe_excluded_evaluation_amount=dedupe_metrics["excluded_evaluation_amount"],
        )
        return summary, pd.DataFrame(columns=NORMALIZED_COLUMNS), pd.DataFrame(columns=RISK_COLUMNS), pd.DataFrame(columns=REVIEW_COLUMNS), pd.DataFrame(columns=HISTORY_COLUMNS)
    group_cols = [c for c in ["account_type", "ticker"] if c in holdings.columns]
    if not group_cols:
        group_cols = ["ticker"]
    if "trade_date" in holdings:
        holdings["_sort_date"] = pd.to_datetime(holdings["trade_date"], errors="coerce")
        holdings = holdings.sort_values(group_cols + ["_sort_date"], na_position="first")
    holdings = holdings.groupby(group_cols, dropna=False, as_index=False).tail(1).drop(columns=["_sort_date"], errors="ignore").reset_index(drop=True)

    for col in ["evaluation_amount", "unrealized_pnl", "balance_quantity"]:
        if col in holdings.columns:
            holdings[col] = pd.to_numeric(holdings[col], errors="coerce").fillna(0)
    if "pnl_pct" in holdings.columns:
        holdings["pnl_pct"] = pd.to_numeric(holdings["pnl_pct"], errors="coerce")
    original_holding_count = len(holdings)
    current_holdings, history_queue = split_current_history_holdings(holdings)
    if balance_data_available and not current_holdings.empty:
        transaction_history = build_transaction_history_candidates(transactions, current_holdings, history_queue)
        if not transaction_history.empty:
            history_queue = pd.concat([history_queue, transaction_history], ignore_index=True).drop_duplicates(subset=["account_type", "ticker"], keep="first")
    portfolio_values = preferred_krw_series(current_holdings, "evaluation_amount_krw", "evaluation_amount")
    total_value = float(portfolio_values.sum()) if not current_holdings.empty else 0.0
    if current_holdings.empty:
        current_holdings["weight_pct"] = pd.Series(dtype=float)
        current_holdings["is_leveraged"] = pd.Series(dtype=bool)
    else:
        current_holdings["weight_pct"] = portfolio_values.apply(lambda v: round(float(v) / total_value * 100, 4) if total_value else 0)
        current_holdings["is_leveraged"] = current_holdings.apply(lambda r: is_leveraged_etf_name(r.get("security_name", ""), r.get("ticker", "")), axis=1)
    unrealized_values = preferred_krw_series(current_holdings, "unrealized_pnl_krw", "unrealized_pnl")
    total_unrealized_pnl = float(unrealized_values.sum()) if not current_holdings.empty else ""
    total_cost = float(total_value - total_unrealized_pnl) if total_unrealized_pnl != "" else ""
    portfolio_pnl_pct = round(total_unrealized_pnl / total_cost * 100, 4) if total_cost not in {"", 0.0} else ""
    leveraged_weight = (
        round(float(current_holdings.loc[current_holdings["is_leveraged"], "weight_pct"].sum()), 4)
        if "is_leveraged" in current_holdings and "weight_pct" in current_holdings and not current_holdings.empty
        else ""
    )

    risk_rows = []
    review_rows = []
    for _, r in current_holdings.iterrows():
        ticker = str(r.get("ticker", ""))
        asset_type = str(r.get("asset_type", "") or "").strip().lower()
        if asset_type == "cash":
            continue
        text = note_text(vault_root, ticker)
        meta = parse_frontmatter(text)
        flags = []
        pnl_value = pd.to_numeric(pd.Series([r.get("pnl_pct")]), errors="coerce").iloc[0]
        if pd.notna(pnl_value) and float(pnl_value) <= -10:
            flags.append("LOSS_REVIEW_REQUIRED")
            review_rows.append({"ticker": ticker, "security_name": r.get("security_name", ""), "reason": "-10% review required", "severity": "blocking", "suggested_action": "Risk Event 또는 Review Report 작성"})
        if bool(r.get("is_leveraged")):
            flags.append("LEVERAGED_ETF")
            if "leveraged_etf_rule_link" not in meta:
                review_rows.append({"ticker": ticker, "security_name": r.get("security_name", ""), "reason": "leveraged ETF rule missing", "severity": "blocking", "suggested_action": "Leveraged_ETF_Rules 링크 추가"})
        if float(r.get("weight_pct", 0) or 0) >= 15:
            flags.append("HIGH_WEIGHT")
        last_review_days = days_since(meta.get("last_review") or meta.get("last_update"))
        if last_review_days is not None and last_review_days > 30:
            flags.append("REVIEW_OVERDUE")
            review_rows.append({"ticker": ticker, "security_name": r.get("security_name", ""), "reason": "last_review older than 30 days", "severity": "advisory", "suggested_action": "리뷰 노트 갱신"})
        if not has_filled_section(text, ["투자 논리", "Thesis", "매수 이유"]):
            flags.append("THESIS_MISSING")
            review_rows.append({"ticker": ticker, "security_name": r.get("security_name", ""), "reason": "thesis missing", "severity": "advisory", "suggested_action": "사용자 판단 영역에 thesis 작성"})
        if not has_filled_section(text, ["매도", "비중축소", "sell criteria", "청산 조건"]):
            flags.append("SELL_RULE_MISSING")
            review_rows.append({"ticker": ticker, "security_name": r.get("security_name", ""), "reason": "sell criteria missing", "severity": "blocking", "suggested_action": "매도/비중축소 기준 작성"})
        if flags:
            risk_rows.append({"ticker": ticker, "security_name": r.get("security_name", ""), "account_type": r.get("account_type", ""), "risk_flags": ";".join(flags), "pnl_pct": r.get("pnl_pct", 0), "weight_pct": r.get("weight_pct", 0), "suggested_action": "자동 매도 아님. 사용자 리뷰 필요."})
    pnl_series = pd.to_numeric(current_holdings.get("pnl_pct", pd.Series(dtype=float)), errors="coerce")
    summary = portfolio_summary_rows(
        total_value=total_value,
        holding_count=len(current_holdings),
        original_holding_count=original_holding_count,
        history_count=len(history_queue),
        loss_count=int((pnl_series <= -10).sum()),
        leveraged_count=int(current_holdings["is_leveraged"].sum()) if "is_leveraged" in current_holdings else 0,
        high_weight_count=int((current_holdings["weight_pct"] >= 15).sum()) if "weight_pct" in current_holdings else 0,
        raw_file_count=raw_file_count,
        transaction_file_count=transaction_file_count,
        holdings_file_count=holdings_file_count,
        balance_data_available=balance_data_available,
        total_cost=total_cost,
        total_unrealized_pnl=total_unrealized_pnl,
        portfolio_pnl_pct=portfolio_pnl_pct,
        leveraged_etf_total_weight_pct=leveraged_weight,
        dedupe_candidate_rows=dedupe_metrics["candidate_rows"],
        dedupe_retained_rows=dedupe_metrics["retained_rows"],
        dedupe_excluded_rows=dedupe_metrics["excluded_rows"],
        dedupe_excluded_evaluation_amount=dedupe_metrics["excluded_evaluation_amount"],
    )
    risk_df = pd.DataFrame(risk_rows, columns=RISK_COLUMNS).drop_duplicates() if risk_rows else pd.DataFrame(columns=RISK_COLUMNS)
    review_df = pd.DataFrame(review_rows, columns=REVIEW_COLUMNS).drop_duplicates() if review_rows else pd.DataFrame(columns=REVIEW_COLUMNS)
    return summary, current_holdings, risk_df, review_df, history_queue


def build_portfolio(processed_dir: Path, vault_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary, holdings, risk, review, _history = build_portfolio_outputs(processed_dir, vault_root)
    return summary, holdings, risk, review


def generate_reports(vault_root: Path, processed_dir: Path | None = None, dry_run: bool = False) -> dict[str, int]:
    processed_dir = processed_dir or vault_root / "70_Imports" / "processed"
    summary, holdings, risk, review, history = build_portfolio_outputs(processed_dir, vault_root)
    transactions = load_csv(processed_dir / "processed_transactions.csv")
    cashflows = load_csv(processed_dir / "processed_cashflows.csv")
    expenses = load_csv(processed_dir / "processed_expenses.csv")
    fx_rates = load_fx_rates(processed_dir)
    income = apply_income_fx_rates(load_csv(processed_dir / "processed_income.csv"), fx_rates)
    expenses = apply_expense_fx_rates(expenses, fx_rates)
    income_summary = build_income_summary(income)
    realized = realized_pnl_ledger(transactions, holdings, fx_rates=fx_rates)
    fx_requirements = build_fx_rate_requirements(income, transactions=transactions, expenses=expenses, fx_rates=fx_rates)
    reconciliation = build_reconciliation_summary(
        processed_dir,
        holdings,
        realized,
        income=income,
        expenses=expenses,
        transactions=transactions,
    )
    performance = build_performance_summary(reconciliation, income_summary, fx_requirements)
    monthly_cashflow = build_monthly_cashflow_summary(cashflows)
    performance_history = build_performance_history(performance, load_csv(processed_dir / "performance_history.csv"))
    if dry_run:
        return {
            "summary_rows": len(summary),
            "holding_rows": len(holdings),
            "history_rows": len(history),
            "risk_rows": len(risk),
            "review_rows": len(review),
            "realized_rows": len(realized),
            "income_summary_rows": len(income_summary),
            "performance_rows": len(performance),
            "fx_rate_requirement_rows": len(fx_requirements),
            "monthly_cashflow_rows": len(monthly_cashflow),
            "performance_history_rows": len(performance_history),
            "reconciliation_rows": len(reconciliation),
        }
    processed_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(processed_dir / "portfolio_summary.csv", index=False, encoding="utf-8-sig")
    reconciliation.to_csv(processed_dir / "reconciliation_summary.csv", index=False, encoding="utf-8-sig")
    performance.to_csv(processed_dir / "performance_summary.csv", index=False, encoding="utf-8-sig")
    monthly_cashflow.to_csv(processed_dir / "monthly_cashflow_summary.csv", index=False, encoding="utf-8-sig")
    performance_history.to_csv(processed_dir / "performance_history.csv", index=False, encoding="utf-8-sig")
    income.to_csv(processed_dir / "processed_income.csv", index=False, encoding="utf-8-sig")
    expenses.to_csv(processed_dir / "processed_expenses.csv", index=False, encoding="utf-8-sig")
    income_summary.to_csv(processed_dir / "income_summary.csv", index=False, encoding="utf-8-sig")
    fx_requirements.to_csv(processed_dir / "fx_rate_requirements.csv", index=False, encoding="utf-8-sig")
    realized.to_csv(processed_dir / "processed_realized_pnl.csv", index=False, encoding="utf-8-sig")
    holdings.to_csv(processed_dir / "processed_holdings.csv", index=False, encoding="utf-8-sig")
    risk.to_csv(processed_dir / "risk_watchlist.csv", index=False, encoding="utf-8-sig")
    review.to_csv(processed_dir / "review_queue.csv", index=False, encoding="utf-8-sig")
    history.to_csv(processed_dir / "history_queue.csv", index=False, encoding="utf-8-sig")
    history.to_csv(processed_dir / "post_mortem_candidates.csv", index=False, encoding="utf-8-sig")
    return {
        "summary_rows": len(summary),
        "holding_rows": len(holdings),
        "history_rows": len(history),
        "risk_rows": len(risk),
        "review_rows": len(review),
        "realized_rows": len(realized),
        "income_summary_rows": len(income_summary),
        "performance_rows": len(performance),
        "fx_rate_requirement_rows": len(fx_requirements),
        "monthly_cashflow_rows": len(monthly_cashflow),
        "performance_history_rows": len(performance_history),
        "reconciliation_rows": len(reconciliation),
    }
