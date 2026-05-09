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
        vals = [markdown_cell(row.get(col, "")) for col in headers]
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
    return f'<div class="stock-kpi"><span class="stock-kpi-label">{escape(label)}</span><strong>{escape(markdown_cell(value))}</strong>{hint_html}</div>'


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


def portfolio_content(summary: pd.DataFrame, holdings: pd.DataFrame, warning: str) -> str:
    parts = []
    if warning:
        parts.append(warning)
    parts.append(preliminary_reconciliation_warning(summary))
    value_status = metric(summary, "total_portfolio_value_status", "unknown")
    profit_status = metric(summary, "profit_result_status", PROFIT_RESULT_STATUS)
    reconciliation_status = metric(summary, "reconciliation_status", RECONCILIATION_STATUS)
    snapshot = [
        "## Snapshot",
        '<div class="stock-kpi-grid">',
        snapshot_card("Holdings", metric(summary, "holding_count", "0")),
        snapshot_card("Portfolio Cost Basis", metric(summary, "total_cost", "-"), "preliminary; not net external principal"),
        snapshot_card("Total Value", metric(summary, "total_portfolio_value", "-")),
        snapshot_card("Unrealized PnL", metric(summary, "total_unrealized_pnl", "-"), "preliminary"),
        snapshot_card("Return", metric(summary, "pnl_pct", "-"), "preliminary pnl_pct"),
        snapshot_card("Profit Status", profit_status),
        snapshot_card("Recon Status", reconciliation_status),
        snapshot_card("Loss Review", metric(summary, "loss_review_required_count", "0"), "candidate count"),
        snapshot_card("Leveraged ETF", metric(summary, "leveraged_etf_count", "0")),
        snapshot_card("Largest Position", largest_position_label(holdings)),
        snapshot_card("Value Status", value_status),
        "</div>",
    ]
    parts.append("\n".join(snapshot))
    if value_status.lower() == "unknown":
        parts.append("> [!warning] Portfolio value status\n> Total portfolio value status is `unknown`. Add current balance files before relying on value-based summaries.")
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


def cashflow_principal_totals(cash: pd.DataFrame) -> dict[str, float]:
    view = principal_cashflow_rows(cash)
    if view.empty or "transaction_type" not in view.columns:
        return {"deposits": 0.0, "withdrawals": 0.0, "net_principal": 0.0}
    tx = view["transaction_type"].fillna("").astype(str).str.lower()
    amounts = view.apply(lambda row: principal_cashflow_krw_amount(row) or 0.0, axis=1)
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


def cashflow_monthly_activity_table(cash: pd.DataFrame) -> str:
    required = {"trade_date", "transaction_type"}
    view = principal_cashflow_rows(cash)
    if view.empty or not required.issubset(set(view.columns)):
        return EMPTY_DATA
    view["month"] = view["trade_date"].fillna("").astype(str).str.slice(0, 7)
    view = view[view["month"].str.len() == 7].copy()
    if view.empty:
        return EMPTY_DATA
    view["_transaction_type"] = view["transaction_type"].fillna("").astype(str).str.lower()
    view["_amount"] = view.apply(lambda row: principal_cashflow_krw_amount(row) or 0.0, axis=1)
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
    view = cash.copy()
    if not view.empty and "trade_date" in view.columns:
        view["_sort_date"] = pd.to_datetime(view["trade_date"], errors="coerce")
        sort_cols = ["_sort_date"]
        ascending = [False]
        if "trade_time" in view.columns:
            view["_sort_time"] = view["trade_time"].fillna("").astype(str)
            sort_cols.append("_sort_time")
            ascending.append(False)
        view = view.sort_values(sort_cols, ascending=ascending, na_position="last").drop(columns=["_sort_date", "_sort_time"], errors="ignore")
    return markdown_table(view, ["trade_date", "transaction_type", "account_type", "ticker", "security_name", "settlement_amount_krw", "currency"], limit)


def cashflow_content(cash: pd.DataFrame, dividends: pd.DataFrame, summary: pd.DataFrame | None = None) -> str:
    summary = summary if summary is not None else pd.DataFrame()
    principal_cash = principal_cashflow_rows(cash)
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
            snapshot_card("Dividend Rows", len(dividends)),
            snapshot_card("Months", months),
            snapshot_card("Types", tx_types),
            snapshot_card("Net Principal", principal_totals["net_principal"], "preliminary KRW-normalized deposits - withdrawals"),
            snapshot_card("Recon Status", metric(summary, "reconciliation_status", RECONCILIATION_STATUS)),
        ]),
        "## Principal summary",
        cashflow_principal_summary_table(principal_cash),
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


def import_review_content(
    summary: pd.DataFrame,
    sources: pd.DataFrame,
    skipped: pd.DataFrame,
    unclassified: pd.DataFrame,
    warning: str,
    holdings: pd.DataFrame | None = None,
) -> str:
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
    parts.extend([
        "## Snapshot",
        dashboard_kpi_grid([
            snapshot_card("Raw Files", metric(summary, "raw_file_count", "0")),
            snapshot_card("Transaction Files", metric(summary, "transaction_history_file_count", "0")),
            snapshot_card("Balance Files", metric(summary, "holdings_file_count", "0")),
            snapshot_card("Value Status", metric(summary, "total_portfolio_value_status", "unknown")),
            snapshot_card("Unclassified", len(unclassified)),
            snapshot_card("Skipped", skipped_count),
            snapshot_card("Dedupe Excluded", dedupe_excluded),
        ]),
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
    holdings = read_csv(processed_dir / "processed_holdings.csv")
    risk = read_csv(processed_dir / "risk_watchlist.csv")
    review = read_csv(processed_dir / "review_queue.csv")
    history = read_csv(processed_dir / "history_queue.csv")
    cash = read_csv(processed_dir / "processed_cashflows.csv")
    dividends = read_csv(processed_dir / "processed_dividends.csv")
    sources = read_csv(processed_dir / "source_file_index.csv")
    qa = read_csv(processed_dir / "qa_exceptions.csv")
    unclassified = read_csv(processed_dir / "unclassified_rows.csv")
    skipped = read_csv(processed_dir / "skipped_rows.csv")
    warning = balance_data_warning(summary)

    if name == "Portfolio.md":
        return portfolio_content(summary, holdings, warning)
    if name == "Companies.md":
        return companies_content(holdings)
    if name == "Exposure.md":
        return exposure_content(summary, holdings, warning)
    if name == "Cashflows.md":
        return cashflow_content(cash, dividends, summary)
    if name == "Import_Review.md":
        return import_review_content(summary, sources, skipped, unclassified, warning, holdings)
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
    for name in ["Portfolio.md", "Companies.md", "Exposure.md", "Cashflows.md", "Import_Review.md", "Risk_Watchlist.md", "Review_Queue.md", "History_Queue.md", "QA_Exceptions.md"]:
        path = vault_root / "10_Dashboard" / name
        ok, warning = replace_autogenerated_block(path, dashboard_content(name, processed_dir), dry_run=dry_run)
        if not ok:
            warnings.append(warning)
    return warnings
