from __future__ import annotations

import re
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from nh_importer import canonical_overseas_position_key, is_principal_cashflow_row, principal_cashflow_krw_amount
from portfolio_model import (
    AMOUNT_UNIT_CLASSIFICATION_STATUS,
    CURRENCY_NORMALIZATION_STATUS,
    PRELIMINARY_RECONCILIATION_WARNING,
    PROFIT_RESULT_STATUS,
    RECONCILIATION_STATUS,
)

AUTO_START = "<!-- AUTO-GENERATED:START -->"
AUTO_END = "<!-- AUTO-GENERATED:END -->"
UTF8_BOM = b"\xef\xbb\xbf"
EMPTY_DATA = "_No data to display._"


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    text = str(value).replace(",", "").strip()
    if text.lower() in {"", "nan", "none", "na", "n/a", "<na>", "-", "--"}:
        return None
    try:
        return float(text)
    except Exception:
        return None


def format_number(value: Any, decimals: int | None = None) -> str:
    number = _optional_number(value)
    if number is None:
        return markdown_cell(value)
    if decimals is None:
        decimals = 0 if float(number).is_integer() else 2
    text = f"{number:,.{decimals}f}"
    if decimals > 0:
        text = text.rstrip("0").rstrip(".")
    return text


def format_krw(value: Any) -> str:
    return format_number(value, decimals=0)


def format_usd(value: Any) -> str:
    text = markdown_cell(value)
    match = re.fullmatch(r"(-?[\d,]+(?:\.\d+)?)\s+USD", text, flags=re.IGNORECASE)
    if match:
        return f"{format_number(match.group(1))} USD"
    if text.upper().endswith(" USD"):
        return text
    amount = format_number(value)
    return f"{amount} USD" if amount else ""


def format_pct(value: Any) -> str:
    number = _optional_number(value)
    if number is None:
        return markdown_cell(value)
    decimals = 0 if float(number).is_integer() else 2
    text = f"{number:,.{decimals}f}"
    if decimals > 0:
        text = text.rstrip("0").rstrip(".")
    return text + "%"


def format_currency_prefixed_amounts(value: Any) -> str:
    text = markdown_cell(value)
    if not text:
        return ""

    pattern = re.compile(r"\b([A-Z]{3})\s+(-?[\d,]+(?:\.\d+)?)\b")

    def replace(match: re.Match[str]) -> str:
        return f"{match.group(1).upper()} {format_number(match.group(2))}"

    return pattern.sub(replace, text)


def format_metric_value(metric_name: Any, value: Any, currency: Any = "") -> str:
    text = markdown_cell(value)
    if not text:
        return ""
    key = str(metric_name or "").strip().lower()
    currency_code = str(currency or "").strip().upper()
    if key in {"month", "snapshot_month", "snapshot_date", "trade_date", "trade_time"}:
        return text
    if "status" in key:
        return text
    if "currency" in key or key == "ccy":
        return text
    if any(token in key for token in ["ticker", "symbol", "file", "path", "memo", "reason", "action", "method", "basis", "formula", "treatment", "role", "name"]):
        return text
    if key.endswith("_id") or key == "id":
        return text
    if "pct" in key or "percent" in key or "pnl / net principal" in key:
        return format_pct(value)
    if currency_code == "USD" and "native" in key:
        return f"{format_number(value)} USD"
    if currency_code and currency_code != "KRW" and "native" in key:
        amount = format_number(value)
        return f"{amount} {currency_code}" if amount else ""
    if "usd" in key and any(token in key for token in ["amount", "dividend", "income", "native"]):
        return format_usd(value)
    if (
        "krw" in key
        or any(token in key for token in [
            "amount",
            "principal",
            "deposit",
            "withdrawal",
            "assets",
            "cash",
            "cost",
            "value",
            "pnl",
            "return",
            "profit",
            "income",
            "expense",
            "fee",
            "tax",
            "residual",
        ])
    ):
        return format_krw(value) if "krw" in key else format_number(value)
    if "count" in key or key.endswith("_rows") or key == "rows":
        return format_number(value, decimals=0)
    prefixed_currency_text = format_currency_prefixed_amounts(value)
    if prefixed_currency_text != text:
        return prefixed_currency_text
    return text


def format_snapshot_value(label: str, value: Any, hint: str = "") -> str:
    text = markdown_cell(value)
    if not text:
        return ""
    prefixed_currency_text = format_currency_prefixed_amounts(value)
    if prefixed_currency_text != text:
        return prefixed_currency_text

    format_key = f"{label} {hint}".strip()
    lower_key = format_key.lower()
    if "usd" in lower_key and any(token in lower_key for token in ["amount", "dividend", "income", "native"]):
        return format_usd(value)
    if any(token in format_key for token in ["수익률", "비율"]) or any(token in lower_key for token in ["pct", "percent", "%"]):
        return format_pct(value)
    if any(token in format_key for token in ["건수", "종목", "행수"]) or any(token in lower_key for token in ["count", "rows"]):
        return format_number(value, decimals=0)
    if (
        "KRW" in format_key
        or any(token in format_key for token in [
            "원금",
            "입금",
            "출금",
            "총자산",
            "금액",
            "원가",
            "평가금액",
            "손익",
            "수수료",
            "세금",
            "배당",
            "이자",
            "분배금",
            "원천징수세",
            "환산 가능 수익",
        ])
    ):
        return format_krw(value)
    return format_metric_value(format_key, value)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype={"ticker": str}, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()


def markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("\\", "/").replace("|", "\\|").replace("\n", "<br>").strip()


def markdown_display_cell(row: pd.Series, column: str) -> str:
    if column == "value" and "metric" in row.index:
        return format_metric_value(row.get("metric", ""), row.get(column, ""))
    currency = ""
    for currency_column in ["currency_native", "currency", "ccy"]:
        if currency_column in row.index:
            currency = row.get(currency_column, "")
            if markdown_cell(currency):
                break
    return format_metric_value(column, row.get(column, ""), currency)


def markdown_table(df: pd.DataFrame, columns: list[str] | None = None, limit: int | None = None) -> str:
    if df.empty:
        return EMPTY_DATA
    view = df.copy()
    if columns:
        view = view[[col for col in columns if col in view.columns]]
    if limit:
        view = view.head(limit)
    if view.empty or not list(view.columns):
        return EMPTY_DATA
    headers = list(view.columns)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for _, row in view.iterrows():
        vals = [markdown_display_cell(row, col) for col in headers]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def inline_code(value: Any) -> str:
    text = markdown_cell(value)
    return "`" + text.replace("`", "\\`") + "`" if text else "`-`"


def row_text(row: pd.Series, key: str) -> str:
    value = row.get(key, "")
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def note_or_code(value: Any, alias: str = "") -> str:
    text = markdown_cell(value)
    if not text:
        return "`-`"
    if text.endswith(".md") and "/" in text:
        target = text[:-3]
        display = alias.strip() if alias.strip() else target.split("/")[-2 if target.endswith("/Company") and "/" in target else -1]
        return f"[[{target}|{display}]]"
    return inline_code(text)


def queue_summary(df: pd.DataFrame, label: str) -> str:
    if df.empty:
        return f"> [!summary] {label}\n> Total: 0"
    severity = df["severity"].fillna("").astype(str).str.lower() if "severity" in df.columns else pd.Series("", index=df.index)
    blocking = int((severity == "blocking").sum())
    advisory = int((severity == "advisory").sum())
    return f"> [!summary] {label}\n> Total: {len(df)} | Blocking: {blocking} | Advisory: {advisory}"


def metric(summary: pd.DataFrame, name: str, default: str = "") -> str:
    value = summary_value(summary, name)
    return value if value != "" else default


def status_is_available(status: Any) -> bool:
    return str(status or "").strip().lower() == "available"


def official_kpi_value(status: Any, value: Any, default: str = "-") -> Any:
    if not status_is_available(status):
        return default
    return value if markdown_cell(value) else default


def number_value(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return default


def optional_number_value(value: Any) -> float | None:
    return _optional_number(value)


def metric_sum(summary: pd.DataFrame, metrics: list[str], default: str = "-") -> Any:
    values = [optional_number_value(metric(summary, name)) for name in metrics]
    if any(value is None for value in values):
        return default
    return round(sum(value for value in values if value is not None), 6)


def percent_bar(value: Any, width: int = 20) -> str:
    pct = max(0.0, min(100.0, number_value(value)))
    filled = int(round(pct / 100 * width))
    return "[" + "#" * filled + "-" * (width - filled) + f"] {pct:.2f}%"


def progress_bar(value: Any) -> str:
    pct = max(0.0, min(100.0, number_value(value)))
    return f'<span class="stock-progress" aria-label="{pct:.2f}%"><span style="width: {pct:.2f}%;"></span></span>'


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def current_holding_positions(holdings: pd.DataFrame, exclude_cash: bool = True) -> pd.DataFrame:
    if holdings.empty:
        return holdings
    view = holdings.copy()
    if exclude_cash and "asset_type" in view.columns:
        view = view[view["asset_type"].fillna("").astype(str).str.lower() != "cash"]
    return view


def weight_summary_table(holdings: pd.DataFrame, group_col: str) -> str:
    view = current_holding_positions(holdings)
    if view.empty or group_col not in view.columns or "weight_pct" not in view.columns:
        return "_No allocation data._"
    rows = []
    for name, group in view.groupby(group_col, dropna=False):
        weight = sum(number_value(v) for v in group["weight_pct"])
        label = str(name).strip() if str(name).strip() and str(name).lower() != "nan" else "(blank)"
        rows.append({"bucket": label, "count": len(group), "weight_pct": round(weight, 2), "bar": progress_bar(weight)})
    return markdown_table(pd.DataFrame(rows).sort_values("weight_pct", ascending=False))


def normalized_currency_exposure_table(holdings: pd.DataFrame) -> str:
    view = current_holding_positions(holdings)
    if view.empty:
        return "_No allocation data._"
    currency_col = "currency_native" if "currency_native" in view.columns else "currency"
    if currency_col not in view.columns:
        return "_No allocation data._"
    rows = []
    for currency, group in view.groupby(currency_col, dropna=False):
        label = str(currency).strip().upper()
        if not label or label == "NAN":
            label = "(blank)"
        krw_values = [optional_number_value(value) for value in group["evaluation_amount_krw"]] if "evaluation_amount_krw" in group.columns else []
        krw_total = sum(value for value in krw_values if value is not None)
        missing_krw = sum(1 for value in krw_values if value is None) if "evaluation_amount_krw" in group.columns else 0
        weight = sum(number_value(value) for value in group["weight_pct"]) if "weight_pct" in group.columns else 0.0
        rows.append({
            "currency": label,
            "count": len(group),
            "evaluation_amount_krw_total": round(krw_total, 2) if krw_values and any(value is not None for value in krw_values) else "",
            "missing_krw_count": missing_krw,
            "weight_pct": round(weight, 2),
        })
    return markdown_table(pd.DataFrame(rows).sort_values("weight_pct", ascending=False))


def position_cell(row: pd.Series) -> str:
    ticker = escape(markdown_cell(row.get("ticker", "")))
    name = escape(markdown_cell(row.get("security_name", "")))
    if name and name != ticker:
        return f'<span class="stock-position"><strong>{ticker}</strong><span>{name}</span></span>'
    return f'<span class="stock-position"><strong>{ticker or "-"}</strong></span>'


def risk_tags(row: pd.Series) -> str:
    tags = []
    if bool_value(row.get("is_leveraged", False)):
        tags.append("leveraged ETF")
    if number_value(row.get("pnl_pct")) <= -10:
        tags.append("loss review")
    if number_value(row.get("weight_pct")) >= 15:
        tags.append("high weight")
    if not tags:
        return ""
    return " ".join(f'<span class="stock-tag">{escape(tag)}</span>' for tag in tags)


def compact_position_table(holdings: pd.DataFrame, limit: int | None = None, sort_col: str = "weight_pct", ascending: bool = False) -> str:
    view = current_holding_positions(holdings)
    if view.empty:
        return "_No holding data._"
    view = view.copy()
    if sort_col in view.columns:
        view["_sort"] = view[sort_col].apply(number_value)
        view = view.sort_values("_sort", ascending=ascending)
    if limit:
        view = view.head(limit)
    rows = []
    for _, row in view.iterrows():
        rows.append({
            "position": position_cell(row),
            "account": row_text(row, "account_type"),
            "asset": row_text(row, "asset_type"),
            "ccy": row_text(row, "currency"),
            "weight_pct": row_text(row, "weight_pct"),
            "pnl_pct": row_text(row, "pnl_pct"),
            "tag": risk_tags(row),
        })
    return markdown_table(pd.DataFrame(rows))


def top_weight_table(holdings: pd.DataFrame, limit: int = 8) -> str:
    return compact_position_table(holdings, limit=limit, sort_col="weight_pct", ascending=False)


def worst_pnl_table(holdings: pd.DataFrame, limit: int = 6) -> str:
    return compact_position_table(holdings, limit=limit, sort_col="pnl_pct", ascending=True)


def filtered_position_table(holdings: pd.DataFrame, predicate: str) -> str:
    view = current_holding_positions(holdings)
    if view.empty:
        return "_No candidates._"
    if predicate == "leveraged":
        view = view[view.get("is_leveraged", False).apply(bool_value)] if "is_leveraged" in view.columns else view.iloc[0:0]
    elif predicate == "loss_review":
        view = view[view.get("pnl_pct", 0).apply(number_value) <= -10] if "pnl_pct" in view.columns else view.iloc[0:0]
    if view.empty:
        return "_No candidates._"
    return compact_position_table(view, limit=None, sort_col="weight_pct", ascending=False)


def largest_position_label(holdings: pd.DataFrame) -> str:
    view = current_holding_positions(holdings)
    if view.empty or "weight_pct" not in view.columns:
        return "-"
    row = view.assign(_weight=view["weight_pct"].apply(number_value)).sort_values("_weight", ascending=False).iloc[0]
    ticker = markdown_cell(row.get("ticker", ""))
    weight = number_value(row.get("weight_pct"))
    return f"{ticker} ({weight:.2f}%)"


def snapshot_card(label: str, value: Any, hint: str = "") -> str:
    hint_html = f'<span class="stock-kpi-hint">{escape(markdown_cell(hint))}</span>' if hint else ""
    return f'<div class="stock-kpi"><span class="stock-kpi-label">{escape(label)}</span><strong>{escape(format_snapshot_value(label, value, hint))}</strong>{hint_html}</div>'


def review_reason_summary_table(review: pd.DataFrame) -> str:
    if review.empty or "reason" not in review.columns:
        return "_No review data._"
    rows = []
    for (reason, severity), group in review.groupby(["reason", "severity"], dropna=False):
        rows.append({"reason": reason, "severity": severity, "count": len(group)})
    return markdown_table(pd.DataFrame(rows).sort_values(["severity", "count"], ascending=[True, False]))


def cashflow_monthly_summary(cash: pd.DataFrame) -> str:
    if cash.empty or "trade_date" not in cash.columns or "transaction_type" not in cash.columns:
        return "_No cashflow data._"
    view = cash.copy()
    view["month"] = view["trade_date"].fillna("").astype(str).str.slice(0, 7)
    view = view[view["month"].str.len() == 7]
    if view.empty:
        return "_No cashflow data._"
    rows = []
    for (month, tx_type), group in view.groupby(["month", "transaction_type"], dropna=False):
        rows.append({"month": month, "transaction_type": tx_type, "count": len(group)})
    return markdown_table(pd.DataFrame(rows).sort_values(["month", "transaction_type"]))


def preliminary_reconciliation_warning(summary: pd.DataFrame | None = None) -> str:
    summary = summary if summary is not None else pd.DataFrame()
    warning = metric(summary, "preliminary_reconciliation_warning", PRELIMINARY_RECONCILIATION_WARNING)
    statuses = [
        ("currency_normalization_status", metric(summary, "currency_normalization_status", CURRENCY_NORMALIZATION_STATUS)),
        ("amount_unit_classification_status", metric(summary, "amount_unit_classification_status", AMOUNT_UNIT_CLASSIFICATION_STATUS)),
        ("profit_result_status", metric(summary, "profit_result_status", PROFIT_RESULT_STATUS)),
        ("reconciliation_status", metric(summary, "reconciliation_status", RECONCILIATION_STATUS)),
    ]
    status_text = "; ".join(f"`{name}={markdown_cell(value)}`" for name, value in statuses)
    return "\n".join([
        "> [!warning] Preliminary profit and reconciliation",
        f"> {markdown_cell(warning)}",
        f"> Status: {status_text}",
    ])


def portfolio_content(
    summary: pd.DataFrame,
    holdings: pd.DataFrame,
    warning: str,
    reconciliation: pd.DataFrame | None = None,
    performance_summary: pd.DataFrame | None = None,
    income_summary: pd.DataFrame | None = None,
    performance_history: pd.DataFrame | None = None,
    fx_requirements: pd.DataFrame | None = None,
) -> str:
    reconciliation = reconciliation if reconciliation is not None else pd.DataFrame()
    performance_summary = performance_summary if performance_summary is not None else pd.DataFrame()
    income_summary = income_summary if income_summary is not None else pd.DataFrame()
    performance_history = performance_history if performance_history is not None else pd.DataFrame()
    fx_requirements = fx_requirements if fx_requirements is not None else pd.DataFrame()
    parts = []
    if warning:
        parts.append(warning)
    parts.append(preliminary_reconciliation_warning(summary))
    value_status = metric(summary, "total_portfolio_value_status", "unknown")
    unit_value_status = metric(reconciliation, "total_assets_status", value_status)
    total_return_status = metric(performance_summary, "performance_status", metric(reconciliation, "total_return_status", metric(summary, "reconciliation_status", RECONCILIATION_STATUS)))
    profit_status = metric(summary, "profit_result_status", PROFIT_RESULT_STATUS)
    reconciliation_status = metric(summary, "reconciliation_status", RECONCILIATION_STATUS)
    legacy_value_fallback = metric(summary, "total_portfolio_value", "-") if reconciliation.empty and performance_summary.empty else "-"
    current_value_status = unit_value_status if not reconciliation.empty else value_status
    current_total_assets_value = official_kpi_value(
        unit_value_status,
        metric(performance_summary, "current_total_assets_krw", metric(reconciliation, "total_assets_krw", legacy_value_fallback)),
    )
    unrealized_pnl_value = official_kpi_value(
        unit_value_status,
        metric(performance_summary, "unrealized_pnl_krw", metric(reconciliation, "unrealized_pnl_krw", metric(summary, "total_unrealized_pnl", "-") if reconciliation.empty and performance_summary.empty else "-")),
    )
    holdings_cost_value = official_kpi_value(current_value_status, metric(summary, "total_cost", "-"))
    holdings_value = official_kpi_value(current_value_status, metric(summary, "total_portfolio_value", "-"))
    holdings_unrealized_value = official_kpi_value(current_value_status, metric(summary, "total_unrealized_pnl", "-"))
    holdings_return_value = official_kpi_value(current_value_status, metric(summary, "pnl_pct", "-"))
    usd_dividend_native = native_amount_label(income_summary_native_total(income_summary, "dividend", "USD"), "USD")
    income_fx_missing_rows = plain_number_text(income_summary_field_total(income_summary, "fx_missing_row_count"))
    fx_requirement_rows = plain_number_text(len(fx_requirements))
    performance = [
        "## 전체 투자 성과",
        '<div class="stock-kpi-grid">',
        snapshot_card("순투입원금", metric(performance_summary, "net_external_principal_krw", metric(reconciliation, "net_external_principal_krw", "-")), "external deposits - withdrawals"),
        snapshot_card("현재 총자산", current_total_assets_value, "current cash + current holdings"),
        snapshot_card("전체 누적손익", metric(performance_summary, "cumulative_return_krw", metric(reconciliation, "total_return_krw", "-")), "current assets - net principal"),
        snapshot_card("전체 누적수익률", metric(performance_summary, "cumulative_return_pct", metric(reconciliation, "total_return_pct", "-")), "cumulative PnL / net principal"),
        snapshot_card("실현손익", metric(performance_summary, "realized_trade_pnl_gross_krw", metric(reconciliation, "realized_pnl_krw", "-")), "realized ledger gross PnL"),
        snapshot_card("미실현손익", unrealized_pnl_value, "current holdings unrealized PnL"),
        snapshot_card("KRW 환산 가능 배당/이자/분배금", metric(performance_summary, "income_total_krw", metric_sum(reconciliation, ["dividend_income_krw", "interest_income_krw", "distribution_income_krw"])), "recognized official KRW rows only"),
        snapshot_card("USD 배당", usd_dividend_native, "native USD dividend rows; not KRW converted"),
        snapshot_card("FX 미해결 income row", income_fx_missing_rows),
        snapshot_card("FX coverage", income_fx_coverage_text(income_summary, fx_requirements), "broker KRW > broker raw FX > local fx_rates.csv > API cached"),
        snapshot_card("FX requirements", fx_requirement_rows),
        snapshot_card("현금성 수익 상태", income_summary_status_text(income_summary)),
        snapshot_card("수수료/세금", metric_sum(performance_summary, ["fee_expense_krw", "tax_expense_krw"], metric_sum(reconciliation, ["fee_expense_krw", "tax_expense_krw"]))),
        snapshot_card("설명되지 않은 차이", metric(performance_summary, "reconciliation_residual_krw", metric(reconciliation, "residual_krw", "-")), "total PnL - explained profit"),
        snapshot_card("성과 상태", total_return_status),
        "</div>",
    ]
    current_position_snapshot = [
        "## 현재 보유분",
        '<div class="stock-kpi-grid">',
        snapshot_card("현재 보유종목", metric(summary, "holding_count", "0")),
        snapshot_card("현재 보유분 원가", holdings_cost_value, "current holdings cost basis; not net external principal"),
        snapshot_card("현재 보유분 평가금액", holdings_value),
        snapshot_card("현재 보유분 미실현손익", holdings_unrealized_value, "current holdings only"),
        snapshot_card("현재 보유분 평가수익률", holdings_return_value, "current holdings pnl_pct"),
        snapshot_card("수익 집계 상태", profit_status),
        snapshot_card("대사 상태", reconciliation_status),
        snapshot_card("현재 총자산 상태", unit_value_status),
        snapshot_card("Loss Review", metric(summary, "loss_review_required_count", "0"), "candidate count"),
        snapshot_card("Leveraged ETF", metric(summary, "leveraged_etf_count", "0")),
        snapshot_card("Largest Position", largest_position_label(holdings)),
        snapshot_card("Value Status", value_status),
        "</div>",
    ]
    parts.append("\n".join(performance))
    parts.append(performance_history_section(performance_history))
    parts.append("\n".join(current_position_snapshot))
    if value_status.lower() == "unknown":
        parts.append("> [!warning] Portfolio value status\n> Total portfolio value status is `unknown`. Add current balance files before relying on value-based summaries.")
    if unit_value_status.lower() != "available" or total_return_status.lower() != "available":
        parts.append(
            "> [!warning] Unit-aware reconciliation not official\n"
            f"> Total assets status is `{markdown_cell(unit_value_status)}` and total return status is `{markdown_cell(total_return_status)}`. "
            "Portfolio value and return are not official until FX, currency, and unit issues are resolved."
        )
    data_warning = metric(summary, "data_quality_warning")
    if data_warning:
        parts.append(f"> [!warning] Data quality\n> {markdown_cell(data_warning)}")
    parts.extend([
        "## Allocation Overview",
        "### Account allocation",
        weight_summary_table(holdings, "account_type"),
        "### Asset type allocation",
        weight_summary_table(holdings, "asset_type"),
        "### Currency allocation",
        weight_summary_table(holdings, "currency"),
        "## Normalized Currency Exposure",
        normalized_currency_exposure_table(holdings),
        "## Concentration",
        "### Top positions by weight",
        top_weight_table(holdings),
        "## Risk Review",
        "### Lowest PnL candidates",
        worst_pnl_table(holdings),
        "### Leveraged ETF candidates",
        filtered_position_table(holdings, "leveraged"),
        "### Loss review candidates",
        filtered_position_table(holdings, "loss_review"),
    ])
    parts.append("## Holdings Detail")
    if holdings.empty:
        parts.append("_표시할 데이터가 없습니다._")
    else:
        detail = markdown_table(holdings, ["ticker", "security_name", "account_type", "market", "asset_type", "currency", "evaluation_amount", "unrealized_pnl", "pnl_pct", "weight_pct"], 50)
        parts.append(f"<details>\n<summary>Show all holdings ({len(holdings)})</summary>\n\n{detail}\n\n</details>")
    return "\n\n".join(parts).strip()


def summary_value(summary: pd.DataFrame, metric: str) -> str:
    if summary.empty or "metric" not in summary.columns or "value" not in summary.columns:
        return ""
    rows = summary[summary["metric"].astype(str) == metric]
    if rows.empty:
        return ""
    value = rows["value"].iloc[0]
    if pd.isna(value):
        return ""
    return str(value)


def balance_data_warning(summary: pd.DataFrame) -> str:
    available = summary_value(summary, "balance_data_available").strip().lower()
    if available in {"false", "0", "no"}:
        return (
            "> [!warning] Balance data not loaded\n"
            "> Holdings or overseas balance files are missing, so value, PnL, and return summaries may be unavailable."
        )
    return ""


def dashboard_kpi_grid(cards: list[str]) -> str:
    return "\n".join(["<div class=\"stock-kpi-grid\">", *cards, "</div>"])


def details_block(summary: str, body: str, open_by_default: bool = False) -> str:
    if not body.strip():
        body = EMPTY_DATA
    open_attr = " open" if open_by_default else ""
    return f"<details{open_attr}>\n<summary>{escape(summary)}</summary>\n\n{body.strip()}\n\n</details>"


def chart_number(value: Any) -> float | None:
    return optional_number_value(value)


def svg_line_chart(
    df: pd.DataFrame,
    x_col: str,
    series: list[tuple[str, str, str]],
    *,
    title: str,
    width: int = 760,
    height: int = 280,
) -> str:
    if df.empty or x_col not in df.columns:
        return EMPTY_DATA

    view = df.copy().reset_index(drop=True)
    rows: list[dict[str, Any]] = []
    values: list[float] = []
    for _, row in view.iterrows():
        item: dict[str, Any] = {x_col: markdown_cell(row.get(x_col, ""))}
        has_value = False
        for key, _label, _color in series:
            value = chart_number(row.get(key, ""))
            item[key] = value
            if value is not None:
                values.append(value)
                has_value = True
        if item[x_col] and has_value:
            rows.append(item)
    if not rows or not values:
        return EMPTY_DATA

    min_value = min(values)
    max_value = max(values)
    if abs(max_value - min_value) < 1e-9:
        padding = max(abs(max_value) * 0.1, 1.0)
    else:
        padding = (max_value - min_value) * 0.1
    min_value -= padding
    max_value += padding
    if min_value > 0:
        min_value = 0.0
    if max_value < 0:
        max_value = 0.0

    left = 72
    right = 28
    top = 34
    bottom = 58
    plot_width = width - left - right
    plot_height = height - top - bottom

    def x_pos(index: int) -> float:
        if len(rows) == 1:
            return left + plot_width / 2
        return left + plot_width * index / (len(rows) - 1)

    def y_pos(value: float) -> float:
        return top + (max_value - value) / (max_value - min_value) * plot_height

    parts = [
        f'<svg class="stock-trend-chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}" xmlns="http://www.w3.org/2000/svg">',
        "<style>.axis{stroke:#8a8f98;stroke-width:1}.grid{stroke:#dde2ea;stroke-width:1}.label{fill:#343a40;font:12px sans-serif}.title{fill:#111827;font:600 14px sans-serif}.legend{fill:#343a40;font:12px sans-serif}</style>",
        f'<text class="title" x="{left}" y="20">{escape(title)}</text>',
        f'<line class="axis" x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}"/>',
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}"/>',
    ]
    for ratio in [0, 0.5, 1]:
        y = top + plot_height * ratio
        value = max_value - (max_value - min_value) * ratio
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}"/>')
        parts.append(f'<text class="label" x="8" y="{y + 4:.2f}">{escape(format_krw(value))}</text>')

    label_indexes = set(range(len(rows))) if len(rows) <= 8 else {0, len(rows) - 1}
    for index, row in enumerate(rows):
        if index not in label_indexes:
            continue
        x = x_pos(index)
        parts.append(f'<text class="label" text-anchor="middle" x="{x:.2f}" y="{height - 24}">{escape(str(row[x_col]))}</text>')

    legend_x = left
    for key, label, color in series:
        points = [(x_pos(index), y_pos(row[key])) for index, row in enumerate(rows) if row.get(key) is not None]
        if not points:
            continue
        if len(points) > 1:
            point_text = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
            parts.append(f'<polyline fill="none" stroke="{escape(color)}" stroke-width="2.5" points="{point_text}"/>')
        for x, y in points:
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.5" fill="{escape(color)}"/>')
        parts.append(f'<rect x="{legend_x}" y="{height - 14}" width="10" height="10" fill="{escape(color)}"/>')
        parts.append(f'<text class="legend" x="{legend_x + 14}" y="{height - 5}">{escape(label)}</text>')
        legend_x += max(110, len(label) * 8 + 28)
    parts.append("</svg>")
    return "\n".join(parts)


def cashflow_trend_section(monthly_cashflow: pd.DataFrame) -> str:
    if monthly_cashflow.empty:
        return "\n\n".join(["## 월별 입출금 추이", "_No monthly cashflow summary available._"])
    view = monthly_cashflow.sort_values("month", ascending=True)
    chart = svg_line_chart(
        view,
        "month",
        [
            ("external_deposit_krw", "Deposit", "#2f9e44"),
            ("external_withdrawal_krw", "Withdrawal", "#e03131"),
            ("net_principal_flow_krw", "Net flow", "#1971c2"),
            ("cumulative_principal_krw", "Cumulative principal", "#5f3dc4"),
        ],
        title="Monthly Principal Cashflow Trend",
    )
    return "\n\n".join([
        "## 월별 입출금 추이",
        chart,
        "### Fallback table",
        markdown_table(view),
    ])


def performance_history_section(performance_history: pd.DataFrame) -> str:
    heading = "## 월별 원금/누적수익 추이"
    scope_note = (
        "> [!note] Scope\n"
        "> cumulative_principal_krw is based on monthly external principal flows. "
        "current_total_assets_krw and cumulative_return_* require imported balance snapshots; "
        "historical total assets are not inferred from raw transactions."
    )
    if performance_history.empty:
        return "\n\n".join([
            heading,
            scope_note,
            "> [!note] 추후 import 누적 후 표시\n> snapshot history point가 2개 미만이라 그래프를 표시하지 않습니다.",
            "### Fallback table",
            EMPTY_DATA,
        ])

    view = performance_history.sort_values("snapshot_month", ascending=True)
    graph_points = view[
        view["current_total_assets_krw"].apply(optional_number_value).notna()
        & view["cumulative_return_krw"].apply(optional_number_value).notna()
    ] if {"current_total_assets_krw", "cumulative_return_krw"}.issubset(set(view.columns)) else pd.DataFrame()
    parts = [heading, scope_note]
    if len(graph_points) < 2:
        parts.append("> [!note] 추후 import 누적 후 표시\n> snapshot history point가 2개 미만이라 그래프를 표시하지 않습니다.")
    else:
        parts.append(svg_line_chart(
            graph_points,
            "snapshot_month",
            [
                ("cumulative_principal_krw", "Principal", "#1971c2"),
                ("current_total_assets_krw", "Total assets", "#2f9e44"),
                ("cumulative_return_krw", "Cumulative return", "#e67700"),
            ],
            title="Monthly Principal and Cumulative Return Trend",
        ))
    parts.extend(["### Fallback table", markdown_table(view)])
    return "\n\n".join(parts)


def normalized_text(value: Any, default: str = "-") -> str:
    text = markdown_cell(value)
    return text if text else default


def tag_cell(values: Any) -> str:
    if isinstance(values, str):
        tags = [value.strip() for value in values.split(";") if value.strip()]
    else:
        tags = [str(value).strip() for value in values if str(value).strip()]
    if not tags:
        return ""
    return " ".join(f'<span class="stock-tag">{escape(tag)}</span>' for tag in tags)


def severity_tag(value: Any) -> str:
    severity = normalized_text(value, "other").lower()
    css = re.sub(r"[^a-z0-9_-]+", "-", severity).strip("-") or "other"
    return f'<span class="stock-tag stock-tag-{escape(css)}">{escape(severity)}</span>'


def queue_position_cell(row: pd.Series) -> str:
    ticker = escape(row_text(row, "ticker") or "UNKNOWN")
    name = escape(row_text(row, "security_name") or ticker)
    if name and name != ticker:
        return f'<span class="stock-position"><strong>{ticker}</strong><span>{name}</span></span>'
    return f'<span class="stock-position"><strong>{ticker}</strong></span>'


def queue_snapshot(view: pd.DataFrame, label: str) -> str:
    severity = view["severity"].fillna("").astype(str).str.lower() if "severity" in view.columns else pd.Series("", index=view.index)
    blocking = int((severity == "blocking").sum())
    advisory = int((severity == "advisory").sum())
    other = max(0, len(view) - blocking - advisory)
    return "\n".join([
        "## Snapshot",
        dashboard_kpi_grid([
            snapshot_card(label, len(view), "total rows"),
            snapshot_card("Blocking", blocking),
            snapshot_card("Advisory", advisory),
            snapshot_card("Other", other),
        ]),
    ])


def count_summary_table(view: pd.DataFrame, group_cols: list[str], label_col: str = "bucket") -> str:
    if view.empty or any(col not in view.columns for col in group_cols):
        return EMPTY_DATA
    rows = []
    total = max(1, len(view))
    grouped = view.groupby(group_cols, dropna=False).size().reset_index(name="count")
    for _, row in grouped.iterrows():
        label = " / ".join(normalized_text(row.get(col), "(blank)") for col in group_cols)
        count = int(row.get("count", 0))
        rows.append({label_col: label, "count": count, "weight_pct": round(count / total * 100, 2), "bar": progress_bar(count / total * 100)})
    return markdown_table(pd.DataFrame(rows).sort_values(["count", label_col], ascending=[False, True]))


def review_item_table(rows: pd.DataFrame, limit: int | None = None) -> str:
    if rows.empty:
        return EMPTY_DATA
    view = rows.copy()
    if limit:
        view = view.head(limit)
    out = []
    for _, row in view.iterrows():
        out.append({
            "position": queue_position_cell(row),
            "reason": row_text(row, "reason"),
            "severity": severity_tag(row_text(row, "severity")),
            "action": row_text(row, "suggested_action"),
        })
    return markdown_table(pd.DataFrame(out))


def review_queue_cards(review: pd.DataFrame) -> str:
    if review.empty:
        return "\n\n".join([
            queue_snapshot(pd.DataFrame(columns=["severity"]), "Review Items"),
            "## Reason summary",
            EMPTY_DATA,
        ])
    view = review.copy()
    view["severity"] = view.get("severity", "").fillna("").astype(str)
    parts = [queue_snapshot(view, "Review Items"), "## Reason summary", count_summary_table(view, ["reason", "severity"], "reason")]
    blocking = view[view["severity"].str.lower() == "blocking"]
    advisory = view[view["severity"].str.lower() == "advisory"]
    other = view[~view["severity"].str.lower().isin(["blocking", "advisory"])]
    parts.extend(["## Blocking", review_item_table(blocking)])
    if not advisory.empty:
        parts.extend(["## Advisory", details_block(f"Show advisory items ({len(advisory)})", review_item_table(advisory))])
    if not other.empty:
        parts.extend(["## Other", details_block(f"Show other items ({len(other)})", review_item_table(other))])
    return "\n\n".join(parts).strip()


def risk_item_table(rows: pd.DataFrame, limit: int | None = None) -> str:
    if rows.empty:
        return EMPTY_DATA
    view = rows.copy()
    if "weight_pct" in view.columns:
        view["_sort"] = view["weight_pct"].apply(number_value)
        view = view.sort_values("_sort", ascending=False)
    if limit:
        view = view.head(limit)
    out = []
    for _, row in view.iterrows():
        out.append({
            "position": queue_position_cell(row),
            "account": row_text(row, "account_type"),
            "pnl_pct": row_text(row, "pnl_pct"),
            "weight_pct": row_text(row, "weight_pct"),
            "flags": tag_cell(row_text(row, "risk_flags")),
            "action": row_text(row, "suggested_action"),
        })
    return markdown_table(pd.DataFrame(out))


def risk_flag_summary_table(risk: pd.DataFrame) -> str:
    if risk.empty or "risk_flags" not in risk.columns:
        return EMPTY_DATA
    counts: dict[str, int] = {}
    for value in risk["risk_flags"]:
        flags = [flag.strip() for flag in str(value or "").split(";") if flag.strip()]
        if not flags:
            flags = ["OTHER"]
        for flag in flags:
            counts[flag] = counts.get(flag, 0) + 1
    max_count = max(counts.values()) if counts else 1
    rows = [
        {"risk_flag": tag_cell([flag]), "count": count, "bar": progress_bar(count / max_count * 100)}
        for flag, count in counts.items()
    ]
    return markdown_table(pd.DataFrame(rows).sort_values(["count", "risk_flag"], ascending=[False, True]))


def risk_watchlist_cards(risk: pd.DataFrame) -> str:
    if risk.empty:
        return "\n\n".join([
            "## Snapshot",
            dashboard_kpi_grid([
                snapshot_card("Risk Items", 0, "total rows"),
                snapshot_card("Loss Review", 0),
                snapshot_card("Leveraged ETF", 0),
                snapshot_card("High Weight", 0),
            ]),
            "## Risk flag summary",
            EMPTY_DATA,
        ])
    flags = risk.get("risk_flags", pd.Series("", index=risk.index)).fillna("").astype(str)
    loss_count = int(flags.str.contains("LOSS_REVIEW", case=False, regex=False).sum())
    leveraged_count = int(flags.str.contains("LEVERAGED", case=False, regex=False).sum())
    high_weight_count = int(flags.str.contains("HIGH_WEIGHT", case=False, regex=False).sum())
    parts = [
        "## Snapshot",
        dashboard_kpi_grid([
            snapshot_card("Risk Items", len(risk), "total rows"),
            snapshot_card("Loss Review", loss_count),
            snapshot_card("Leveraged ETF", leveraged_count),
            snapshot_card("High Weight", high_weight_count),
        ]),
        "## Risk flag summary",
        risk_flag_summary_table(risk),
        "## Priority Candidates",
        risk_item_table(risk, limit=12),
    ]
    flag_rows: dict[str, list[pd.Series]] = {}
    for _, row in risk.iterrows():
        row_flags = [flag.strip() for flag in row_text(row, "risk_flags").split(";") if flag.strip()] or ["OTHER"]
        for flag in row_flags:
            flag_rows.setdefault(flag, []).append(row)
    grouped = []
    for flag in sorted(flag_rows):
        grouped.append(f"### {markdown_cell(flag)}\n\n{risk_item_table(pd.DataFrame(flag_rows[flag]))}")
    if grouped:
        parts.extend(["## Flag Details", details_block(f"Show risk flag details ({len(risk)})", "\n\n".join(grouped))])
    return "\n\n".join(parts).strip()


def qa_exception_table(rows: pd.DataFrame, limit: int | None = None) -> str:
    if rows.empty:
        return EMPTY_DATA
    view = rows.copy()
    if limit:
        view = view.head(limit)
    out = []
    for _, row in view.iterrows():
        out.append({
            "exception": inline_code(row_text(row, "exception_id") or "UNKNOWN"),
            "severity": severity_tag(row_text(row, "severity")),
            "file": note_or_code(row_text(row, "file")),
            "issue": row_text(row, "issue"),
            "action": row_text(row, "suggested_fix"),
        })
    return markdown_table(pd.DataFrame(out))


def qa_exception_cards(qa: pd.DataFrame) -> str:
    if qa.empty:
        return "\n\n".join([
            queue_snapshot(pd.DataFrame(columns=["severity"]), "QA Exceptions"),
            "## Exception Summary",
            EMPTY_DATA,
        ])
    view = qa.copy()
    view["severity"] = view.get("severity", "").fillna("").astype(str)
    blocking = view[view["severity"].str.lower() == "blocking"]
    advisory = view[view["severity"].str.lower() == "advisory"]
    other = view[~view["severity"].str.lower().isin(["blocking", "advisory"])]
    parts = [
        queue_snapshot(view, "QA Exceptions"),
        "## Exception Summary",
        count_summary_table(view, ["exception_id", "severity"], "exception"),
        "## Blocking",
        qa_exception_table(blocking),
    ]
    if not advisory.empty:
        parts.extend(["## Advisory", details_block(f"Show advisory exceptions ({len(advisory)})", qa_exception_table(advisory))])
    if not other.empty:
        parts.extend(["## Other", details_block(f"Show other exceptions ({len(other)})", qa_exception_table(other))])
    return "\n\n".join(parts).strip()


def companies_content(holdings: pd.DataFrame) -> str:
    if holdings.empty:
        return "\n\n".join([
            "## Snapshot",
            dashboard_kpi_grid([
                snapshot_card("Positions", 0),
                snapshot_card("Cash Excluded", 0),
                snapshot_card("Leveraged ETF", 0),
            ]),
            "## Current Holdings",
            EMPTY_DATA,
        ])
    view = current_holding_positions(holdings)
    cash_count = len(holdings) - len(view)
    leveraged_count = int(view.get("is_leveraged", pd.Series(False, index=view.index)).fillna(False).apply(bool_value).sum()) if not view.empty else 0
    currencies = int(view["currency"].nunique()) if "currency" in view.columns and not view.empty else 0
    parts = [
        "## Snapshot",
        dashboard_kpi_grid([
            snapshot_card("Positions", len(view)),
            snapshot_card("Cash Excluded", cash_count),
            snapshot_card("Leveraged ETF", leveraged_count),
            snapshot_card("Currencies", currencies),
        ]),
        "## Current Holdings",
        compact_position_table(view, limit=100),
    ]
    return "\n\n".join(parts).strip()


def cashflow_group_table(cash: pd.DataFrame, group_cols: list[str], label_col: str) -> str:
    if cash.empty or any(col not in cash.columns for col in group_cols):
        return EMPTY_DATA
    return count_summary_table(cash, group_cols, label_col)


def principal_cashflow_rows(cash: pd.DataFrame) -> pd.DataFrame:
    if cash.empty:
        return cash.copy()
    return cash[cash.apply(is_principal_cashflow_row, axis=1)].copy()


def cashflow_principal_view(cash: pd.DataFrame) -> pd.DataFrame:
    view = principal_cashflow_rows(cash)
    if view.empty:
        return view
    view = view.copy()
    view["principal_amount_krw"] = view.apply(lambda row: principal_cashflow_krw_amount(row) or 0.0, axis=1)
    return view


def cashflow_principal_totals(cash: pd.DataFrame) -> dict[str, float]:
    view = cashflow_principal_view(cash)
    if view.empty or "transaction_type" not in view.columns:
        return {"deposits": 0.0, "withdrawals": 0.0, "net_principal": 0.0}
    tx = view["transaction_type"].fillna("").astype(str).str.lower()
    amounts = view["principal_amount_krw"].apply(number_value)
    deposits = float(amounts[tx == "deposit"].sum())
    withdrawals = float(amounts[tx == "withdrawal"].sum())
    return {
        "deposits": round(deposits, 2),
        "withdrawals": round(withdrawals, 2),
        "net_principal": round(deposits - withdrawals, 2),
    }


def cashflow_principal_summary_table(cash: pd.DataFrame) -> str:
    totals = cashflow_principal_totals(cash)
    return markdown_table(pd.DataFrame([
        {"item": "deposits", "amount": totals["deposits"]},
        {"item": "withdrawals", "amount": totals["withdrawals"]},
        {"item": "net_principal", "amount": totals["net_principal"]},
    ]))


def cashflow_monthly_summary_frame(cash: pd.DataFrame) -> pd.DataFrame:
    view = cashflow_principal_view(cash)
    if view.empty or "trade_date" not in view.columns or "transaction_type" not in view.columns:
        return pd.DataFrame(columns=[
            "month",
            "external_deposit_krw",
            "external_withdrawal_krw",
            "net_principal_flow_krw",
            "cumulative_principal_krw",
        ])
    view = view.copy()
    view["month"] = view["trade_date"].fillna("").astype(str).str.slice(0, 7)
    view = view[view["month"].str.len() == 7]
    if view.empty:
        return pd.DataFrame(columns=[
            "month",
            "external_deposit_krw",
            "external_withdrawal_krw",
            "net_principal_flow_krw",
            "cumulative_principal_krw",
        ])
    view["_transaction_type"] = view["transaction_type"].fillna("").astype(str).str.lower()
    view["_amount"] = view["principal_amount_krw"].apply(number_value).abs()
    view["external_deposit_krw"] = view.apply(lambda row: row["_amount"] if row["_transaction_type"] == "deposit" else 0.0, axis=1)
    view["external_withdrawal_krw"] = view.apply(lambda row: row["_amount"] if row["_transaction_type"] == "withdrawal" else 0.0, axis=1)
    monthly = (
        view.groupby("month", as_index=False, dropna=False)[["external_deposit_krw", "external_withdrawal_krw"]]
        .sum()
        .sort_values("month", ascending=True)
    )
    monthly["net_principal_flow_krw"] = monthly["external_deposit_krw"] - monthly["external_withdrawal_krw"]
    monthly["cumulative_principal_krw"] = monthly["net_principal_flow_krw"].cumsum()
    return monthly[["month", "external_deposit_krw", "external_withdrawal_krw", "net_principal_flow_krw", "cumulative_principal_krw"]]


def lower_column(df: pd.DataFrame, column: str) -> pd.Series:
    if df.empty or column not in df.columns:
        return pd.Series(dtype=str)
    return df[column].fillna("").astype(str).str.strip().str.lower()


def status_count_across(frames: list[pd.DataFrame], status: str) -> int:
    return sum(int(lower_column(frame, "amount_review_status").eq(status).sum()) for frame in frames)


def cashflow_exclusion_status_table(cash: pd.DataFrame, income: pd.DataFrame, expenses: pd.DataFrame, fx_events: pd.DataFrame) -> str:
    cash_roles = lower_column(cash, "cashflow_role")
    cash_tx = lower_column(cash, "transaction_type")
    income_in_cash = int(cash_roles.str.startswith("income_").sum()) if not cash_roles.empty else 0
    fx_in_cash = int(cash_roles.eq("internal_fx_exchange").sum()) if not cash_roles.empty else 0
    trade_settlements = int((cash_roles.eq("trade_settlement") | cash_tx.isin({"buy", "sell"})).sum()) if not cash.empty else 0
    records = [
        {"item": "income_rows_excluded_from_principal", "count": len(income) if not income.empty else income_in_cash},
        {"item": "fx_exchange_rows_excluded_from_principal", "count": len(fx_events) if not fx_events.empty else fx_in_cash},
        {"item": "trade_settlement_rows_excluded_from_principal", "count": trade_settlements},
        {"item": "fx_missing_rows", "count": status_count_across([cash, income, expenses, fx_events], "fx_missing")},
        {"item": "currency_ambiguous_rows", "count": status_count_across([cash, income, expenses, fx_events], "currency_ambiguous")},
        {"item": "unit_ambiguous_rows", "count": status_count_across([cash, income, expenses, fx_events], "unit_ambiguous")},
    ]
    return markdown_table(pd.DataFrame(records))


def cashflow_monthly_activity_table(cash: pd.DataFrame) -> str:
    required = {"trade_date", "transaction_type"}
    view = cashflow_principal_view(cash)
    if view.empty or not required.issubset(set(view.columns)):
        return EMPTY_DATA
    view["month"] = view["trade_date"].fillna("").astype(str).str.slice(0, 7)
    view = view[view["month"].str.len() == 7].copy()
    if view.empty:
        return EMPTY_DATA
    view["_transaction_type"] = view["transaction_type"].fillna("").astype(str).str.lower()
    view["_amount"] = view["principal_amount_krw"].apply(number_value)
    view["_deposit"] = view.apply(lambda row: row["_amount"] if row["_transaction_type"] == "deposit" else 0.0, axis=1)
    view["_withdrawal"] = view.apply(lambda row: row["_amount"] if row["_transaction_type"] == "withdrawal" else 0.0, axis=1)
    view["_net_principal"] = view["_deposit"] - view["_withdrawal"]
    monthly = view.groupby("month", dropna=False).agg(
        cashflow_rows=("_amount", "size"),
        deposits=("_deposit", "sum"),
        withdrawals=("_withdrawal", "sum"),
        net_principal=("_net_principal", "sum"),
    ).reset_index().sort_values("month", ascending=True)
    monthly["cumulative_principal"] = monthly["net_principal"].cumsum()
    for col in ["deposits", "withdrawals", "net_principal", "cumulative_principal"]:
        monthly[col] = monthly[col].round(2)
    monthly = monthly.sort_values("month", ascending=False)
    return markdown_table(monthly)


def cashflow_detail_table(cash: pd.DataFrame, limit: int | None = None) -> str:
    view = cashflow_principal_view(cash)
    if not view.empty and "trade_date" in view.columns:
        view["_sort_date"] = pd.to_datetime(view["trade_date"], errors="coerce")
        sort_cols = ["_sort_date"]
        ascending = [False]
        if "trade_time" in view.columns:
            view["_sort_time"] = view["trade_time"].fillna("").astype(str)
            sort_cols.append("_sort_time")
            ascending.append(False)
        view = view.sort_values(sort_cols, ascending=ascending, na_position="last").drop(columns=["_sort_date", "_sort_time"], errors="ignore")
    return markdown_table(
        view,
        [
            "trade_date",
            "transaction_type",
            "account_type",
            "principal_amount_krw",
            "settlement_amount_krw",
            "amount_krw",
            "currency",
            "cashflow_role",
            "amount_review_status",
        ],
        limit,
    )


def status_count_table(df: pd.DataFrame, status_col: str, label: str) -> str:
    if df.empty or status_col not in df.columns:
        return EMPTY_DATA
    statuses = df[status_col].fillna("").astype(str).str.strip()
    statuses = statuses[statuses != ""]
    if statuses.empty:
        return EMPTY_DATA
    view = statuses.value_counts(dropna=False).rename_axis(status_col).reset_index(name="count")
    view.insert(0, "scope", label)
    return markdown_table(view)


def status_counts_text(df: pd.DataFrame, status_col: str) -> str:
    if df.empty or status_col not in df.columns:
        return ""
    statuses = df[status_col].fillna("").astype(str).str.strip()
    statuses = statuses[statuses != ""]
    if statuses.empty:
        return ""
    counts = statuses.value_counts(dropna=False).sort_index()
    return "; ".join(f"{status}: {int(count)}" for status, count in counts.items())


def ok_amount_krw_total(view: pd.DataFrame) -> Any:
    if view.empty or "amount_review_status" not in view.columns or "amount_krw" not in view.columns:
        return ""
    ok = view[view["amount_review_status"].fillna("").astype(str).str.lower().eq("ok")]
    values = [optional_number_value(value) for value in ok["amount_krw"]]
    values = [value for value in values if value is not None]
    return round(sum(values), 2) if values else ""


def native_amount_total_if_single_currency(view: pd.DataFrame) -> tuple[str, Any]:
    if view.empty or "currency_native" not in view.columns or "amount_native" not in view.columns:
        return "", ""
    currencies = sorted({
        str(value).strip().upper()
        for value in view["currency_native"].fillna("")
        if str(value).strip()
    })
    if len(currencies) != 1:
        return ("mixed" if len(currencies) > 1 else ""), ""
    values = [optional_number_value(value) for value in view["amount_native"]]
    values = [value for value in values if value is not None]
    return currencies[0], (round(sum(values), 6) if values else "")


def income_summary_table(income: pd.DataFrame) -> str:
    if income.empty or "income_type" not in income.columns:
        return EMPTY_DATA
    if "amount_krw_sum" in income.columns:
        return markdown_table(
            income,
            [
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
            ],
            50,
        )
    records = []
    for income_type, group in income.groupby("income_type", dropna=False, sort=True):
        currency, native_total = native_amount_total_if_single_currency(group)
        status_counts = status_counts_text(group, "amount_review_status")
        status = group["amount_review_status"].fillna("").astype(str).str.lower() if "amount_review_status" in group.columns else pd.Series("", index=group.index)
        records.append({
            "income_type": income_type,
            "count": len(group),
            "amount_krw_ok_total": ok_amount_krw_total(group),
            "native_currency": currency,
            "amount_native_total": native_total,
            "fx_missing_count": int((status == "fx_missing").sum()),
            "amount_review_status_counts": status_counts,
        })
    return markdown_table(pd.DataFrame(records))


def income_summary_field_total(income_summary: pd.DataFrame, field: str, income_type: str | None = None) -> Any:
    if income_summary.empty or field not in income_summary.columns:
        return ""
    view = income_summary
    if income_type is not None and "income_type" in view.columns:
        view = view[view["income_type"].fillna("").astype(str).str.lower().eq(income_type)]
    values = [optional_number_value(value) for value in view[field]]
    values = [value for value in values if value is not None]
    return round(sum(values), 6) if values else ""


def income_summary_native_total(
    income_summary: pd.DataFrame,
    income_type: str,
    currency: str,
    field: str = "amount_native_sum",
) -> Any:
    if income_summary.empty or field not in income_summary.columns:
        return ""
    view = income_summary
    if "income_type" in view.columns:
        view = view[view["income_type"].fillna("").astype(str).str.lower().eq(income_type.lower())]
    if "currency_native" in view.columns:
        view = view[view["currency_native"].fillna("").astype(str).str.upper().eq(currency.upper())]
    values = [optional_number_value(value) for value in view[field]]
    values = [value for value in values if value is not None]
    return round(sum(values), 6) if values else ""


def plain_number_text(value: Any) -> str:
    number = optional_number_value(value)
    if number is None:
        return markdown_cell(value)
    return format_number(number)


def native_amount_label(value: Any, currency: str) -> str:
    amount = format_number(value)
    return f"{amount} {currency.upper()}" if amount else ""


def income_fx_coverage_text(income_summary: pd.DataFrame, fx_requirements: pd.DataFrame | None = None) -> str:
    if income_summary.empty:
        return ""
    total = optional_number_value(income_summary_field_total(income_summary, "row_count")) or 0.0
    missing = optional_number_value(income_summary_field_total(income_summary, "fx_missing_row_count")) or 0.0
    covered = max(total - missing, 0.0)
    requirement_count = len(fx_requirements) if fx_requirements is not None else 0
    return f"covered: {format_number(covered)} / missing: {format_number(missing)} / requirements: {format_number(requirement_count)}"


def income_fx_source_text(income_summary: pd.DataFrame) -> str:
    if income_summary.empty or "fx_source_summary" not in income_summary.columns:
        return ""
    values = [
        markdown_cell(value)
        for value in income_summary["fx_source_summary"].fillna("")
        if markdown_cell(value)
    ]
    return " | ".join(dict.fromkeys(values))


def income_summary_status_text(income_summary: pd.DataFrame) -> str:
    if income_summary.empty or "income_status" not in income_summary.columns:
        return ""
    status = income_summary["income_status"].fillna("").astype(str).str.strip()
    status = status[status.ne("")]
    if status.empty:
        return ""
    counts = status.value_counts(sort=False)
    if len(counts) == 1:
        return str(counts.index[0])
    return " / ".join(f"{index}: {count}" for index, count in counts.items())


def income_summary_group_needs_fx_review(group: pd.DataFrame) -> bool:
    for column in ["fx_missing_row_count", "amount_review_needed_row_count"]:
        if column in group.columns:
            values = [optional_number_value(value) for value in group[column]]
            if sum(value for value in values if value is not None) > 0:
                return True
    if "income_status" in group.columns:
        statuses = group["income_status"].fillna("").astype(str).str.strip().str.lower()
        statuses = statuses[statuses.ne("")]
        if not statuses.empty and any(status not in {"available", "ok"} for status in statuses):
            return True
    return False


def income_summary_native_text(income_summary: pd.DataFrame) -> str:
    if income_summary.empty or "currency_native" not in income_summary.columns or "net_income_native" not in income_summary.columns:
        return ""
    records = []
    for currency, group in income_summary.groupby("currency_native", dropna=False, sort=True):
        currency_text = markdown_cell(currency).upper() if markdown_cell(currency) else "UNKNOWN"
        if currency_text != "KRW" and income_summary_group_needs_fx_review(group):
            records.append(f"{currency_text} FX 검토 필요")
            continue
        values = [optional_number_value(value) for value in group["net_income_native"]]
        values = [value for value in values if value is not None]
        if values:
            records.append(f"{currency_text} {format_number(round(sum(values), 6))}")
    return " / ".join(records)


def cash_income_cards(income_summary: pd.DataFrame, fx_requirements: pd.DataFrame | None = None) -> str:
    return dashboard_kpi_grid([
        snapshot_card("KRW 환산 가능 배당/이자/분배금", income_summary_field_total(income_summary, "amount_krw_sum"), "recognized official KRW rows only"),
        snapshot_card("USD dividend native total", income_summary_native_total(income_summary, "dividend", "USD"), "native USD dividend rows; not KRW converted"),
        snapshot_card("FX 미해결 income row count", income_summary_field_total(income_summary, "fx_missing_row_count")),
        snapshot_card("FX coverage", income_fx_coverage_text(income_summary, fx_requirements), "broker KRW > broker raw FX > local fx_rates.csv > API cached"),
        snapshot_card("FX source", income_fx_source_text(income_summary)),
        snapshot_card("income_status", income_summary_status_text(income_summary)),
        snapshot_card("수집된 배당", income_summary_field_total(income_summary, "amount_krw_sum", "dividend"), "recognized official KRW rows only"),
        snapshot_card("수집된 이자", income_summary_field_total(income_summary, "amount_krw_sum", "interest"), "recognized official KRW rows only"),
        snapshot_card("수집된 분배금", income_summary_field_total(income_summary, "amount_krw_sum", "distribution"), "recognized official KRW rows only"),
        snapshot_card("원천징수세", income_summary_field_total(income_summary, "tax_krw_sum"), "official KRW rows only"),
        snapshot_card("FX 누락 건수", income_summary_field_total(income_summary, "fx_missing_row_count")),
        snapshot_card("native 기준 수익", income_summary_native_text(income_summary)),
        snapshot_card("KRW 환산 가능 수익", income_summary_field_total(income_summary, "net_income_krw"), "status ok rows only"),
    ])


def expense_summary_table(expenses: pd.DataFrame) -> str:
    if expenses.empty or "expense_type" not in expenses.columns:
        return EMPTY_DATA
    records = []
    for expense_type, group in expenses.groupby("expense_type", dropna=False, sort=True):
        status_counts = status_counts_text(group, "amount_review_status")
        status = group["amount_review_status"].fillna("").astype(str).str.lower() if "amount_review_status" in group.columns else pd.Series("", index=group.index)
        records.append({
            "expense_type": expense_type,
            "count": len(group),
            "amount_krw_ok_total": ok_amount_krw_total(group),
            "fx_missing_count": int((status == "fx_missing").sum()),
            "amount_review_status_counts": status_counts,
        })
    return markdown_table(pd.DataFrame(records))


def fx_event_count_for_status(fx_events: pd.DataFrame, statuses: set[str]) -> int:
    if fx_events.empty or "fx_pair_status" not in fx_events.columns:
        return 0
    mask = fx_events["fx_pair_status"].fillna("").astype(str).str.lower().isin(statuses)
    view = fx_events[mask]
    if view.empty:
        return 0
    if "fx_event_id" in view.columns:
        ids = {
            str(value).strip()
            for value in view["fx_event_id"].fillna("")
            if str(value).strip()
        }
        if ids:
            return len(ids)
    return len(view)


def fx_event_summary_table(fx_events: pd.DataFrame) -> str:
    if fx_events.empty:
        return EMPTY_DATA
    event_ids = set()
    if "fx_event_id" in fx_events.columns:
        event_ids = {
            str(value).strip()
            for value in fx_events["fx_event_id"].fillna("")
            if str(value).strip()
        }
    role = fx_events["cashflow_role"].fillna("").astype(str).str.lower() if "cashflow_role" in fx_events.columns else pd.Series("", index=fx_events.index)
    internal_flag = fx_events["is_internal_transfer"].apply(bool_value) if "is_internal_transfer" in fx_events.columns else pd.Series(False, index=fx_events.index)
    needs_review = 0
    if "amount_review_status" in fx_events.columns:
        needs_review += int(fx_events["amount_review_status"].fillna("").astype(str).str.lower().eq("needs_review").sum())
    if "fx_pair_status" in fx_events.columns:
        needs_review += int(fx_events["fx_pair_status"].fillna("").astype(str).str.lower().isin({"unpaired", "needs_review"}).sum())
    records = [
        {"metric": "total_event_ids", "value": len(event_ids) if event_ids else len(fx_events)},
        {"metric": "total_legs", "value": len(fx_events)},
        {"metric": "paired_events", "value": fx_event_count_for_status(fx_events, {"paired"})},
        {"metric": "partial_events", "value": fx_event_count_for_status(fx_events, {"partial"})},
        {"metric": "unpaired_or_needs_review_rows", "value": needs_review},
        {"metric": "internal_transfer_rows", "value": int((role.eq("internal_fx_exchange") | internal_flag).sum())},
    ]
    return markdown_table(pd.DataFrame(records))


def reconciliation_metric_table(reconciliation: pd.DataFrame, metrics: list[str]) -> str:
    if reconciliation.empty:
        return EMPTY_DATA
    records = [{"metric": name, "value": metric(reconciliation, name)} for name in metrics]
    return markdown_table(pd.DataFrame(records))


def realized_pnl_table(realized: pd.DataFrame, limit: int = 50) -> str:
    if realized.empty:
        return EMPTY_DATA
    view = realized.copy()
    if "sell_date" in view.columns:
        view = view.sort_values("sell_date", ascending=False)
    return markdown_table(
        view,
        [
            "sell_date",
            "ticker",
            "security_name",
            "account_type",
            "quantity_sold",
            "proceeds_native",
            "proceeds_krw",
            "cost_basis_native",
            "cost_basis_krw",
            "fee_krw",
            "tax_krw",
            "realized_trade_pnl_gross_krw",
            "realized_trade_pnl_net_krw",
            "realized_result",
            "position_status",
            "cost_basis_method",
            "amount_review_status",
            "fx_status",
        ],
        limit,
    )


def reconciliation_status_warning(reconciliation: pd.DataFrame) -> str:
    total_assets_status = metric(reconciliation, "total_assets_status", "unknown")
    principal_status = metric(reconciliation, "net_external_principal_status", "unknown")
    return_status = metric(reconciliation, "total_return_status", "unknown")
    if total_assets_status == "available" and principal_status == "available" and return_status == "available":
        return ""
    return (
        "> [!warning] Reconciliation not official\n"
        f"> total_assets_status=`{markdown_cell(total_assets_status)}`, "
        f"net_external_principal_status=`{markdown_cell(principal_status)}`, "
        f"total_return_status=`{markdown_cell(return_status)}`. "
        "Do not treat total return as official until unresolved FX, currency, and unit statuses are cleared."
    )


def reconciliation_content(
    reconciliation: pd.DataFrame,
    summary: pd.DataFrame | None = None,
    realized: pd.DataFrame | None = None,
) -> str:
    summary = summary if summary is not None else pd.DataFrame()
    realized = realized if realized is not None else pd.DataFrame()
    parts = []
    warning = reconciliation_status_warning(reconciliation)
    if warning:
        parts.append(warning)
    parts.extend([
        "## Reconciliation Scope",
        reconciliation_metric_table(reconciliation, [
            "reconciliation_summary_role",
            "total_return_alias_of",
            "total_return_pct_alias_of",
            "explained_profit_formula",
            "fee_tax_treatment",
            "fx_pnl_treatment",
        ]),
        "## Audit Totals",
        reconciliation_metric_table(reconciliation, [
            "total_assets_krw",
            "total_assets_status",
            "current_cash_krw",
            "current_holding_assets_krw",
            "net_external_principal_krw",
            "net_external_principal_status",
            "total_return_krw",
            "total_return_pct",
            "total_return_status",
        ]),
        "## Explained Profit Components",
        reconciliation_metric_table(reconciliation, [
            "unrealized_pnl_krw",
            "realized_pnl_krw",
            "realized_trade_pnl_gross_krw",
            "realized_trade_pnl_net_krw",
            "realized_gain_krw",
            "realized_loss_krw",
            "realized_pnl_basis",
            "realized_cost_basis_method",
            "realized_pnl_status",
            "dividend_income_krw",
            "interest_income_krw",
            "distribution_income_krw",
            "fee_expense_krw",
            "tax_expense_krw",
            "fx_pnl_status",
            "explained_profit_krw",
            "explained_profit_status",
        ]),
        "## Residual Status",
        reconciliation_metric_table(reconciliation, ["residual_krw", "residual_status"]),
        "## Realized PnL Ledger (`processed_realized_pnl.csv`)",
        realized_pnl_table(realized),
        "## Unresolved Status Counts",
        reconciliation_metric_table(reconciliation, [
            "fx_missing_row_count",
            "currency_ambiguous_row_count",
            "unit_ambiguous_row_count",
            "amount_review_needed_row_count",
            "realized_pnl_row_count",
            "realized_pnl_unavailable_row_count",
            "realized_closed_position_count",
        ]),
        "## FX Event Counts",
        reconciliation_metric_table(reconciliation, [
            "fx_event_id_count",
            "fx_event_leg_count",
            "fx_paired_event_count",
            "fx_partial_event_count",
            "fx_unpaired_event_count",
            "fx_needs_review_event_count",
            "fx_unpaired_or_needs_review_row_count",
            "fx_internal_transfer_row_count",
        ]),
    ])
    if summary.empty:
        return "\n\n".join(parts).strip()
    parts.extend([
        "## Portfolio Summary Status",
        reconciliation_metric_table(summary, [
            "currency_normalization_status",
            "amount_unit_classification_status",
            "profit_result_status",
            "reconciliation_status",
        ]),
    ])
    return "\n\n".join(parts).strip()


def cashflow_content(
    cash: pd.DataFrame,
    dividends: pd.DataFrame,
    summary: pd.DataFrame | None = None,
    income: pd.DataFrame | None = None,
    income_summary: pd.DataFrame | None = None,
    expenses: pd.DataFrame | None = None,
    fx_events: pd.DataFrame | None = None,
    monthly_cashflow_summary: pd.DataFrame | None = None,
    fx_requirements: pd.DataFrame | None = None,
) -> str:
    summary = summary if summary is not None else pd.DataFrame()
    income = income if income is not None else pd.DataFrame()
    income_summary = income_summary if income_summary is not None else pd.DataFrame()
    expenses = expenses if expenses is not None else pd.DataFrame()
    fx_events = fx_events if fx_events is not None else pd.DataFrame()
    monthly_cashflow_summary = monthly_cashflow_summary if monthly_cashflow_summary is not None else pd.DataFrame()
    fx_requirements = fx_requirements if fx_requirements is not None else pd.DataFrame()
    principal_cash = cashflow_principal_view(cash)
    months = 0
    if not principal_cash.empty and "trade_date" in principal_cash.columns:
        months = principal_cash["trade_date"].fillna("").astype(str).str.slice(0, 7).loc[lambda s: s.str.len() == 7].nunique()
    tx_types = int(principal_cash["transaction_type"].nunique()) if not principal_cash.empty and "transaction_type" in principal_cash.columns else 0
    principal_totals = cashflow_principal_totals(principal_cash)
    parts = [
        preliminary_reconciliation_warning(summary),
        "## Snapshot",
        dashboard_kpi_grid([
            snapshot_card("Cashflow Rows", len(principal_cash)),
            snapshot_card("Income Rows", len(income)),
            snapshot_card("Expense Rows", len(expenses)),
            snapshot_card("FX Legs", len(fx_events)),
            snapshot_card("FX Requirements", len(fx_requirements)),
            snapshot_card("Dividend Rows", len(dividends)),
            snapshot_card("Months", months),
            snapshot_card("Types", tx_types),
            snapshot_card("Net Principal", principal_totals["net_principal"], "preliminary KRW-normalized deposits - withdrawals"),
            snapshot_card("Recon Status", metric(summary, "reconciliation_status", RECONCILIATION_STATUS)),
        ]),
        "## Principal summary",
        cashflow_principal_summary_table(principal_cash),
        cashflow_trend_section(monthly_cashflow_summary if not monthly_cashflow_summary.empty else cashflow_monthly_summary_frame(principal_cash)),
        "## Principal exclusions and unresolved amounts",
        cashflow_exclusion_status_table(cash, income, expenses, fx_events),
        "## 현금성 수익",
        cash_income_cards(income_summary, fx_requirements),
        income_summary_table(income_summary if not income_summary.empty else income),
        "### FX rate requirements",
        markdown_table(fx_requirements, ["event_date", "currency", "use_case", "row_count", "amount_native_sum", "missing_reason", "source_file_type", "status"], 50),
        "### Income status counts",
        status_count_table(income, "amount_review_status", "income"),
        "## Expense summary",
        expense_summary_table(expenses),
        "### Expense status counts",
        status_count_table(expenses, "amount_review_status", "expense"),
        "## FX Events",
        fx_event_summary_table(fx_events),
        "### FX event status counts",
        status_count_table(fx_events, "fx_pair_status", "fx_event"),
        "## Monthly activity",
        cashflow_monthly_activity_table(principal_cash),
        "## Type summary",
        cashflow_group_table(principal_cash, ["transaction_type"], "type"),
        "## Recent Cashflows",
        cashflow_detail_table(principal_cash, limit=20),
        "## Details",
        details_block(f"Show all principal cashflow rows ({len(principal_cash)})", cashflow_detail_table(principal_cash, limit=200)),
        details_block(f"Show dividend rows ({len(dividends)})", markdown_table(dividends, ["trade_date", "ticker", "security_name", "settlement_amount", "currency"], 200)),
    ]
    return "\n\n".join(parts).strip()


def holding_dedupe_summary_table(holdings: pd.DataFrame | None) -> str:
    if holdings is None or holdings.empty or "dedupe_excluded_count" not in holdings.columns:
        return EMPTY_DATA
    view = holdings.copy()
    view["_excluded"] = view["dedupe_excluded_count"].apply(number_value)
    view = view[view["_excluded"] > 0]
    if view.empty:
        return EMPTY_DATA
    columns = [
        "ticker",
        "security_name",
        "account_type",
        "market",
        "currency",
        "preferred_source",
        "dedupe_action",
        "dedupe_reason",
        "dedupe_excluded_count",
        "dedupe_excluded_evaluation_amount",
    ]
    return markdown_table(view.drop(columns=["_excluded"], errors="ignore"), columns, 50)


REQUIRED_OUTPUT_COLUMNS = {
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


def output_availability_table(processed_dir: Path) -> str:
    records = []
    for name, required_columns in REQUIRED_OUTPUT_COLUMNS.items():
        path = processed_dir / name
        df = read_csv(path)
        missing = [col for col in required_columns if col not in df.columns]
        records.append({
            "output": name,
            "exists": path.exists(),
            "rows": len(df),
            "schema": "ok" if not missing else "missing_columns",
            "missing_columns": ", ".join(missing),
        })
    return markdown_table(pd.DataFrame(records))


def unresolved_status_count_table(income: pd.DataFrame, expenses: pd.DataFrame, fx_events: pd.DataFrame, unclassified: pd.DataFrame) -> str:
    records = []
    income_status = income["amount_review_status"].fillna("").astype(str).str.lower() if "amount_review_status" in income.columns else pd.Series(dtype=str)
    expense_status = expenses["amount_review_status"].fillna("").astype(str).str.lower() if "amount_review_status" in expenses.columns else pd.Series(dtype=str)
    fx_pair_status = fx_events["fx_pair_status"].fillna("").astype(str).str.lower() if "fx_pair_status" in fx_events.columns else pd.Series(dtype=str)
    fx_amount_status = fx_events["amount_review_status"].fillna("").astype(str).str.lower() if "amount_review_status" in fx_events.columns else pd.Series(dtype=str)
    records.extend([
        {"status": "income_fx_missing", "count": int(income_status.eq("fx_missing").sum())},
        {"status": "expense_fx_missing", "count": int(expense_status.eq("fx_missing").sum())},
        {"status": "fx_partial", "count": int(fx_pair_status.eq("partial").sum())},
        {"status": "fx_unpaired_or_needs_review", "count": int(fx_pair_status.isin({"unpaired", "needs_review"}).sum() + fx_amount_status.eq("needs_review").sum())},
        {"status": "unclassified_rows", "count": len(unclassified)},
    ])
    return markdown_table(pd.DataFrame(records))


def amount_unit_audit_summary_table(amount_audit: pd.DataFrame, unit_mismatch: pd.DataFrame, income: pd.DataFrame, fx_events: pd.DataFrame) -> str:
    audit_status = lower_column(amount_audit, "amount_review_status")
    if audit_status.empty:
        audit_status = lower_column(unit_mismatch, "amount_normalization_status")
    audit_roles = lower_column(amount_audit, "cashflow_role")
    mismatch_status = lower_column(unit_mismatch, "amount_normalization_status")
    amount_krw = amount_audit["amount_krw"] if "amount_krw" in amount_audit.columns else pd.Series([""] * len(amount_audit), index=amount_audit.index)
    amount_kind = lower_column(amount_audit, "amount_kind")
    quantity_unit = amount_audit["quantity_unit"].fillna("").astype(str).str.strip() if "quantity_unit" in amount_audit.columns else pd.Series([""] * len(amount_audit), index=amount_audit.index)
    price_unit = amount_audit["price_unit"].fillna("").astype(str).str.strip() if "price_unit" in amount_audit.columns else pd.Series([""] * len(amount_audit), index=amount_audit.index)
    raw_not_official = 0
    if not amount_audit.empty:
        raw_not_official = int((audit_status.ne("ok") | amount_krw.fillna("").astype(str).str.strip().eq("")).sum())
    elif not unit_mismatch.empty:
        raw_not_official = len(unit_mismatch)
    records = [
        {"item": "fx_missing_count", "count": int(audit_status.eq("fx_missing").sum() or mismatch_status.eq("fx_missing").sum())},
        {"item": "currency_ambiguous_count", "count": int(audit_status.eq("currency_ambiguous").sum() or mismatch_status.eq("currency_ambiguous").sum())},
        {"item": "unit_ambiguous_count", "count": int(audit_status.eq("unit_ambiguous").sum() or mismatch_status.eq("unit_ambiguous").sum())},
        {"item": "internal_fx_events", "count": len(fx_events) if not fx_events.empty else int(audit_roles.eq("internal_fx_exchange").sum())},
        {"item": "income_excluded_from_principal", "count": len(income) if not income.empty else int(audit_roles.str.startswith("income_").sum())},
        {"item": "trade_settlements_excluded_from_principal", "count": int(audit_roles.eq("trade_settlement").sum())},
        {"item": "raw_amount_rows_not_official_krw", "count": raw_not_official},
        {
            "item": "quantity_price_not_aggregated_as_money",
            "count": int((amount_kind.isin({"quantity", "unit_price"}) | quantity_unit.ne("") | price_unit.ne("")).sum()) if not amount_audit.empty else 0,
        },
    ]
    return markdown_table(pd.DataFrame(records))


def import_review_content(
    summary: pd.DataFrame,
    sources: pd.DataFrame,
    skipped: pd.DataFrame,
    unclassified: pd.DataFrame,
    warning: str,
    holdings: pd.DataFrame | None = None,
    income: pd.DataFrame | None = None,
    expenses: pd.DataFrame | None = None,
    fx_events: pd.DataFrame | None = None,
    amount_audit: pd.DataFrame | None = None,
    unit_mismatch: pd.DataFrame | None = None,
    processed_dir: Path | None = None,
) -> str:
    income = income if income is not None else pd.DataFrame()
    expenses = expenses if expenses is not None else pd.DataFrame()
    fx_events = fx_events if fx_events is not None else pd.DataFrame()
    amount_audit = amount_audit if amount_audit is not None else pd.DataFrame()
    unit_mismatch = unit_mismatch if unit_mismatch is not None else pd.DataFrame()
    parts = []
    if warning:
        parts.append(warning)
    data_warning = metric(summary, "data_quality_warning")
    if data_warning:
        parts.append(f"> [!warning] Data quality\n> {markdown_cell(data_warning)}")
    skipped_count = int(skipped["row_count"].apply(number_value).sum()) if not skipped.empty and "row_count" in skipped.columns else len(skipped)
    dedupe_excluded = int(number_value(metric(summary, "holding_dedupe_excluded_rows", "0")))
    dedupe_retained = int(number_value(metric(summary, "holding_dedupe_retained_rows", "0")))
    dedupe_candidates = int(number_value(metric(summary, "holding_dedupe_candidate_rows", "0")))
    dedupe_excluded_value = metric(summary, "holding_dedupe_excluded_evaluation_amount", "0")
    fx_partial_count = int(fx_events["fx_pair_status"].fillna("").astype(str).str.lower().eq("partial").sum()) if "fx_pair_status" in fx_events.columns else 0
    parts.extend([
        "## Snapshot",
        dashboard_kpi_grid([
            snapshot_card("Raw Files", metric(summary, "raw_file_count", "0")),
            snapshot_card("Transaction Files", metric(summary, "transaction_history_file_count", "0")),
            snapshot_card("Balance Files", metric(summary, "holdings_file_count", "0")),
            snapshot_card("Value Status", metric(summary, "total_portfolio_value_status", "unknown")),
            snapshot_card("Income Rows", len(income)),
            snapshot_card("Expense Rows", len(expenses)),
            snapshot_card("FX Legs", len(fx_events)),
            snapshot_card("FX Partial", fx_partial_count),
            snapshot_card("Unclassified", len(unclassified)),
            snapshot_card("Skipped", skipped_count),
            snapshot_card("Dedupe Excluded", dedupe_excluded),
        ]),
        "## Processed Output Availability",
        output_availability_table(processed_dir) if processed_dir is not None else EMPTY_DATA,
        "## Unresolved Status Counts",
        unresolved_status_count_table(income, expenses, fx_events, unclassified),
        "## Amount/Unit Audit Summary",
        amount_unit_audit_summary_table(amount_audit, unit_mismatch, income, fx_events),
        "## Source Files",
        markdown_table(sources, ["source_file", "source_file_type", "account_type", "size_bytes", "modified_at", "sensitive_data_found"], 20),
    ])
    skipped_view = skipped
    if not skipped.empty and "row_count" in skipped.columns:
        group_cols = [col for col in ["skip_reason", "source_file_type", "account_type", "currency", "fx_rate"] if col in skipped.columns]
        if group_cols:
            skipped_view = skipped.groupby(group_cols, dropna=False)["row_count"].sum().reset_index()
    parts.extend([
        "## Import Quality",
        "### Holding dedupe",
        markdown_table(pd.DataFrame([
            {"dedupe_item": "candidate_rows", "value": dedupe_candidates},
            {"dedupe_item": "retained_rows", "value": dedupe_retained},
            {"dedupe_item": "excluded_rows", "value": dedupe_excluded},
            {"dedupe_item": "excluded_evaluation_amount", "value": dedupe_excluded_value},
        ])),
        holding_dedupe_summary_table(holdings),
        "### Skipped broker helper rows",
        markdown_table(skipped_view, ["skip_reason", "source_file_type", "account_type", "currency", "fx_rate", "row_count"], 20),
        "### Unclassified transaction rows",
        markdown_table(unclassified, limit=20),
        "## Details",
        details_block(f"Show all source rows ({len(sources)})", markdown_table(sources, limit=200)),
        details_block(f"Show all skipped rows ({len(skipped_view)})", markdown_table(skipped_view, limit=200)),
        details_block(f"Show all unclassified rows ({len(unclassified)})", markdown_table(unclassified, limit=200)),
        "## Next Actions",
        "- If unclassified rows remain, review the raw column mapping or transaction type rules.",
        "- If balance-file warnings remain, add holdings or overseas balance files before relying on value and PnL summaries.",
        "- If sensitive-data warnings appear, verify generated Markdown before publishing or syncing.",
    ])
    return "\n\n".join(parts).strip()


def history_item_table(rows: pd.DataFrame, limit: int | None = None) -> str:
    if rows.empty:
        return EMPTY_DATA
    view = rows.copy()
    if limit:
        view = view.head(limit)
    out = []
    for _, row in view.iterrows():
        out.append({
            "position": queue_position_cell(row),
            "account": row_text(row, "account_type"),
            "market": row_text(row, "market"),
            "reason": row_text(row, "history_reason"),
            "destination": row_text(row, "suggested_destination"),
            "action": row_text(row, "suggested_action"),
        })
    return markdown_table(pd.DataFrame(out))


def history_queue_cards(history: pd.DataFrame) -> str:
    if history.empty:
        return "\n\n".join([
            "## Snapshot",
            dashboard_kpi_grid([snapshot_card("History Candidates", 0)]),
            "## Current Candidates",
            EMPTY_DATA,
        ])
    reason_summary = count_summary_table(history, ["history_reason"], "reason") if "history_reason" in history.columns else EMPTY_DATA
    account_summary = count_summary_table(history, ["account_type"], "account") if "account_type" in history.columns else EMPTY_DATA
    parts = [
        "## Snapshot",
        dashboard_kpi_grid([
            snapshot_card("History Candidates", len(history)),
            snapshot_card("Accounts", history["account_type"].nunique() if "account_type" in history.columns else 0),
            snapshot_card("Markets", history["market"].nunique() if "market" in history.columns else 0),
        ]),
        "> [!note] Scope\n> These are past-trade candidates with no current holding signal. They stay outside the primary Review Queue.",
        "## Reason Summary",
        reason_summary,
        "## Account Summary",
        account_summary,
        "## Recent Candidates",
        history_item_table(history, limit=20),
        "## Details",
        details_block(f"Show all history candidates ({len(history)})", history_item_table(history, limit=200)),
    ]
    return "\n\n".join(parts).strip()


def exposure_content(summary: pd.DataFrame, holdings: pd.DataFrame, warning: str) -> str:
    parts = []
    if warning:
        parts.append(warning)
    value_status = metric(summary, "total_portfolio_value_status", "unknown")
    view = current_holding_positions(holdings)
    parts.extend([
        "## Snapshot",
        dashboard_kpi_grid([
            snapshot_card("Positions", len(view)),
            snapshot_card("Value Status", value_status),
            snapshot_card("Leveraged ETF", metric(summary, "leveraged_etf_count", "0")),
            snapshot_card("High Weight", metric(summary, "high_weight_count", "0")),
        ]),
        "## Allocation",
        "### Account",
        weight_summary_table(holdings, "account_type"),
        "### Market",
        weight_summary_table(holdings, "market"),
        "### Asset Type",
        weight_summary_table(holdings, "asset_type"),
        "### Currency",
        weight_summary_table(holdings, "currency"),
        "## Leveraged ETF Exposure",
        filtered_position_table(holdings, "leveraged"),
    ])
    if not view.empty:
        parts.extend(["## Details", details_block(f"Show exposure detail ({len(view)})", compact_position_table(view, limit=200))])
    return "\n\n".join(parts).strip()


def replace_autogenerated_block(path: Path, content: str, dry_run: bool = False) -> tuple[bool, str]:
    had_bom = False
    existing = path.exists()
    if not path.exists():
        text = f"# {path.stem}\n\n{AUTO_START}\n{content.rstrip()}\n{AUTO_END}\n"
    else:
        raw = path.read_bytes()
        had_bom = raw.startswith(UTF8_BOM)
        text = raw.decode("utf-8-sig")
        if AUTO_START not in text or AUTO_END not in text:
            return False, f"{path} has no AUTO-GENERATED markers"
        pattern = re.compile(re.escape(AUTO_START) + r".*?" + re.escape(AUTO_END), re.S)
        replacement = f"{AUTO_START}\n{content.rstrip()}\n{AUTO_END}"
        text = pattern.sub(lambda _m: replacement, text)
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        if existing:
            encoded = text.encode("utf-8")
            path.write_bytes(UTF8_BOM + encoded if had_bom else encoded)
        else:
            path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return True, ""


def bootstrap_autogenerated_block(path: Path, heading: str = "Auto-generated update area", dry_run: bool = False) -> tuple[bool, str]:
    """Insert an empty AUTO-GENERATED block into an explicitly approved note."""
    if not path.exists():
        return False, f"{path} does not exist"
    raw = path.read_bytes()
    had_bom = raw.startswith(UTF8_BOM)
    text = raw.decode("utf-8-sig")
    has_start = AUTO_START in text
    has_end = AUTO_END in text
    if has_start or has_end:
        if has_start and has_end:
            return True, ""
        return False, f"{path} has incomplete AUTO-GENERATED markers"
    match = re.search(r"(?m)^#\s+.+(?:\r?\n|$)", text)
    if not match:
        return False, f"{path} has no top-level heading for marker bootstrap"
    newline = "\r\n" if "\r\n" in text else "\n"
    block = f"{newline}## {heading}{newline}{AUTO_START}{newline}{AUTO_END}{newline}"
    text = text[:match.end()] + block + text[match.end():]
    if not dry_run:
        encoded = text.encode("utf-8")
        path.write_bytes(UTF8_BOM + encoded if had_bom else encoded)
    return True, ""


def dashboard_content(name: str, processed_dir: Path) -> str:
    summary = read_csv(processed_dir / "portfolio_summary.csv")
    reconciliation = read_csv(processed_dir / "reconciliation_summary.csv")
    performance = read_csv(processed_dir / "performance_summary.csv")
    monthly_cashflow = read_csv(processed_dir / "monthly_cashflow_summary.csv")
    performance_history = read_csv(processed_dir / "performance_history.csv")
    realized = read_csv(processed_dir / "processed_realized_pnl.csv")
    holdings = read_csv(processed_dir / "processed_holdings.csv")
    risk = read_csv(processed_dir / "risk_watchlist.csv")
    review = read_csv(processed_dir / "review_queue.csv")
    history = read_csv(processed_dir / "history_queue.csv")
    cash = read_csv(processed_dir / "processed_cashflows.csv")
    dividends = read_csv(processed_dir / "processed_dividends.csv")
    income = read_csv(processed_dir / "processed_income.csv")
    income_summary = read_csv(processed_dir / "income_summary.csv")
    fx_requirements = read_csv(processed_dir / "fx_rate_requirements.csv")
    expenses = read_csv(processed_dir / "processed_expenses.csv")
    fx_events = read_csv(processed_dir / "processed_fx_events.csv")
    sources = read_csv(processed_dir / "source_file_index.csv")
    qa = read_csv(processed_dir / "qa_exceptions.csv")
    unclassified = read_csv(processed_dir / "unclassified_rows.csv")
    skipped = read_csv(processed_dir / "skipped_rows.csv")
    amount_audit = read_csv(processed_dir / "amount_unit_audit.csv")
    unit_mismatch = read_csv(processed_dir / "unit_mismatch_audit.csv")
    warning = balance_data_warning(summary)

    if name == "Portfolio.md":
        return portfolio_content(summary, holdings, warning, reconciliation, performance, income_summary, performance_history, fx_requirements)
    if name == "Reconciliation.md":
        return reconciliation_content(reconciliation, summary, realized)
    if name == "Companies.md":
        return companies_content(holdings)
    if name == "Exposure.md":
        return exposure_content(summary, holdings, warning)
    if name == "Cashflows.md":
        return cashflow_content(cash, dividends, summary, income, income_summary, expenses, fx_events, monthly_cashflow, fx_requirements)
    if name == "Import_Review.md":
        return import_review_content(summary, sources, skipped, unclassified, warning, holdings, income, expenses, fx_events, amount_audit, unit_mismatch, processed_dir)
    if name == "Risk_Watchlist.md":
        return "\n".join([warning, risk_watchlist_cards(risk)]).strip()
    if name == "Review_Queue.md":
        return "\n".join([warning, review_queue_cards(review)]).strip()
    if name == "History_Queue.md":
        return history_queue_cards(history)
    if name == "QA_Exceptions.md":
        return qa_exception_cards(qa)
    return "_Unsupported dashboard._"


def safe_component(value: Any) -> str:
    s = str(value or "").strip() or "UNKNOWN"
    return re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", s).strip("_")


def parse_note_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    meta: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def company_note_identity_key(row: dict[str, Any] | pd.Series) -> str:
    asset_type = str(row.get("asset_type", "") or "").strip().lower()
    if asset_type == "cash":
        return ""
    canonical = canonical_overseas_position_key(row)
    if canonical and not canonical.startswith("CASH:"):
        return canonical
    ticker = str(row.get("ticker", "") or "").strip().upper()
    return f"TICKER:{ticker}" if ticker else ""


def existing_company_note_index(company_root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not company_root.exists():
        return index
    for path in sorted(company_root.glob("*/Company.md")):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception:
            continue
        meta = parse_note_frontmatter(text)
        ticker = str(meta.get("ticker", "") or path.parent.name).strip()
        row = {
            "ticker": ticker,
            "security_name": meta.get("name", ""),
            "market": meta.get("market", ""),
            "asset_type": meta.get("asset_type", ""),
        }
        for key in {
            f"FOLDER:{path.parent.name.upper()}",
            f"TICKER:{ticker.upper()}" if ticker else "",
            company_note_identity_key(row),
        }:
            if key:
                index.setdefault(key, path)
    return index


def new_company_note(row: pd.Series) -> str:
    ticker = str(row.get("ticker", "") or "UNKNOWN")
    name = str(row.get("security_name", "") or ticker)
    asset_type = str(row.get("asset_type", "stock") or "stock")
    is_lev = bool(row.get("is_leveraged", False))
    etf_extra = ""
    if asset_type == "etf" or is_lev:
        etf_extra = """underlying_asset:
leverage_factor:
rebalance_type:
long_term_holding_allowed: false
volatility_decay_risk: true
leveraged_etf_rule_link: "[[05_Principles/Leveraged_ETF_Rules]]"
"""
    return f"""---
type: company
doc_type: company
ticker: "{ticker}"
name: "{name}"
market: "{row.get('market', '')}"
asset_type: "{asset_type}"
account: "{row.get('account_type', '')}"
currency: "{row.get('currency', '')}"
status: "position"
weight_pct: {row.get('weight_pct', '')}
pnl_pct: {row.get('pnl_pct', '')}
is_leveraged: {str(is_lev).lower()}
{etf_extra}review_status: "needs_user_review"
risk_level:
last_review:
next_review:
source_files:
  - "{row.get('source_file', '')}"
tags:
  - investment
  - company
---

# {name} / {ticker}

## 자동 업데이트 영역
{AUTO_START}
- 비중: {row.get('weight_pct', '')}
- 평가손익률: {row.get('pnl_pct', '')}
- 계좌: {row.get('account_type', '')}
- 최근 점검일:
- 리스크 플래그:
- 원천자료: {row.get('source_file', '')}
{AUTO_END}

## 사용자 판단 영역
### 1. 매수 이유
### 2. 계속 보유하려는 이유
### 3. 핵심 확인 지표
### 4. 펀더멘털 훼손 기준
### 5. -10% 하락 시 대응
### 6. 추가매수 조건
### 7. 매도/비중축소 조건

## AI 점검 기록
## 관련 Risk Event
## 관련 Decision
## 원천자료 링크
"""


def write_company_notes(vault_root: Path, processed_dir: Path, create_companies: bool = False, dry_run: bool = False) -> list[str]:
    warnings: list[str] = []
    holdings = read_csv(processed_dir / "processed_holdings.csv")
    if holdings.empty:
        return warnings
    holdings["ticker"] = holdings.get("ticker", "").astype(str)
    holdings = holdings[~holdings["ticker"].str.lower().isin(["", "nan", "none"])].drop_duplicates(subset=["account_type", "ticker"], keep="last")
    if "asset_type" in holdings.columns:
        holdings = holdings[holdings["asset_type"].fillna("").astype(str).str.lower() != "cash"]
    seen_warnings: set[str] = set()
    company_root = vault_root / "20_Companies"
    note_index = existing_company_note_index(company_root)
    for _, row in holdings.iterrows():
        ticker = safe_component(row.get("ticker"))
        expected_path = company_root / ticker / "Company.md"
        path = expected_path
        if not path.exists():
            path = note_index.get(company_note_identity_key(row)) or note_index.get(f"TICKER:{str(row.get('ticker', '')).strip().upper()}") or expected_path
        content = f"- 비중: {row.get('weight_pct', '')}\n- 평가손익률: {row.get('pnl_pct', '')}\n- 계좌: {row.get('account_type', '')}\n- 최근 점검일:\n- 리스크 플래그:\n- 원천자료: {row.get('source_file', '')}"
        if path.exists():
            ok, warning = replace_autogenerated_block(path, content, dry_run=dry_run)
            if not ok:
                warnings.append(warning)
        elif create_companies:
            if not dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new_company_note(row), encoding="utf-8")
                for key in {
                    f"FOLDER:{path.parent.name.upper()}",
                    f"TICKER:{str(row.get('ticker', '')).strip().upper()}",
                    company_note_identity_key(row),
                }:
                    if key:
                        note_index.setdefault(key, path)
        else:
            warning = f"{path} missing; run with --create-companies to create"
            if warning not in seen_warnings:
                warnings.append(warning)
                seen_warnings.add(warning)
    return warnings


def write_dashboards(vault_root: Path, processed_dir: Path | None = None, dry_run: bool = False) -> list[str]:
    processed_dir = processed_dir or vault_root / "70_Imports" / "processed"
    warnings: list[str] = []
    for name in ["Portfolio.md", "Reconciliation.md", "Companies.md", "Exposure.md", "Cashflows.md", "Import_Review.md", "Risk_Watchlist.md", "Review_Queue.md", "History_Queue.md", "QA_Exceptions.md"]:
        path = vault_root / "10_Dashboard" / name
        ok, warning = replace_autogenerated_block(path, dashboard_content(name, processed_dir), dry_run=dry_run)
        if not ok:
            warnings.append(warning)
    return warnings
