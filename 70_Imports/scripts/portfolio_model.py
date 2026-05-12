from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from nh_importer import NORMALIZED_COLUMNS, is_leveraged_etf_name, remove_overlapping_overseas_holdings

HISTORY_COLUMNS = [
    "import_id", "source_file", "source_file_type", "account_type", "market", "asset_type",
    "ticker", "security_name", "trade_date", "currency", "fx_rate", "balance_quantity", "evaluation_amount",
    "unrealized_pnl", "pnl_pct", "weight_pct", "history_reason", "suggested_destination", "suggested_action",
]

RISK_COLUMNS = ["ticker", "security_name", "account_type", "risk_flags", "pnl_pct", "weight_pct", "suggested_action"]
REVIEW_COLUMNS = ["ticker", "security_name", "reason", "severity", "suggested_action"]
SUMMARY_COLUMNS = ["metric", "value"]
RECONCILIATION_SUMMARY_COLUMNS = ["metric", "value"]
REALIZED_PNL_COLUMNS = [
    "account_type",
    "market",
    "ticker",
    "security_name",
    "currency_native",
    "sell_date",
    "sell_import_id",
    "quantity_sold",
    "proceeds_krw",
    "cost_basis_krw",
    "realized_pnl_krw",
    "realized_result",
    "position_status",
    "amount_review_status",
    "amount_review_reason",
    "source_file",
]
BALANCE_SOURCE_TYPES = {"holdings", "overseas_balance"}
REVIEW_NEEDED_STATUSES = {"fx_missing", "partial", "needs_review", "currency_ambiguous", "unit_ambiguous", "unclassified", "lot_missing"}
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


def has_filled_section(text: str, names: list[str]) -> bool:
    if not text:
        return False
    for name in names:
        pattern = re.compile(rf"^#+\s*.*{re.escape(name)}.*$(.*?)(?=^#+\s|\Z)", re.M | re.S)
        m = pattern.search(text)
        if m:
            body = re.sub(r"[-\s:_()0-9.]+", "", m.group(1))
            body = body.replace("TODO", "").replace("미정", "").replace("없음", "")
            if len(body.strip()) >= 8:
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


def realized_pnl_ledger(transactions: pd.DataFrame, holdings: pd.DataFrame) -> pd.DataFrame:
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
            amount, amount_status, amount_reason = trade_amount_krw(row)
            if tx_type == "buy":
                lots.append({
                    "remaining_qty": quantity or 0.0,
                    "unit_cost": (amount / quantity) if quantity and amount is not None else None,
                    "status": amount_status if amount_status != "ok" or quantity is None else "ok",
                    "reason": amount_reason if amount_status != "ok" else ("buy quantity missing" if quantity is None else ""),
                })
                continue
            if tx_type != "sell":
                continue

            statuses: list[str] = []
            reasons: list[str] = []
            matched_cost = 0.0
            remaining = quantity or 0.0
            if quantity is None:
                statuses.append("unit_ambiguous")
                reasons.append("sell quantity missing")
            if amount_status != "ok" or amount is None:
                statuses.append(amount_status)
                if amount_reason:
                    reasons.append(amount_reason)

            lot_index = 0
            while remaining > 1e-9 and lot_index < len(lots):
                lot = lots[lot_index]
                lot_qty = float(lot.get("remaining_qty") or 0.0)
                if lot_qty <= 1e-9:
                    lot_index += 1
                    continue
                matched_qty = min(remaining, lot_qty)
                if lot.get("unit_cost") is None or lot.get("status") != "ok":
                    statuses.append(text_value(lot.get("status")) or "unit_ambiguous")
                    if lot.get("reason"):
                        reasons.append(text_value(lot.get("reason")))
                else:
                    matched_cost += float(lot["unit_cost"]) * matched_qty
                lot["remaining_qty"] = lot_qty - matched_qty
                remaining -= matched_qty
                if lot["remaining_qty"] <= 1e-9:
                    lot_index += 1

            if remaining > 1e-9:
                statuses.append("lot_missing")
                reasons.append("sell quantity exceeds matched buy lots in imported transaction history")

            status = status_from_list(statuses, default="ok")
            proceeds = amount if amount is not None else None
            realized = proceeds - matched_cost if status == "ok" and proceeds is not None else None
            group_records.append({
                "account_type": row.get("account_type", ""),
                "market": row.get("market", ""),
                "ticker": row.get("ticker", ""),
                "security_name": row.get("security_name", ""),
                "currency_native": row_currency(row),
                "sell_date": row.get("trade_date", ""),
                "sell_import_id": row.get("import_id", ""),
                "quantity_sold": quantity if quantity is not None else "",
                "proceeds_krw": proceeds if status == "ok" else "",
                "cost_basis_krw": matched_cost if status == "ok" else "",
                "realized_pnl_krw": realized if realized is not None else "",
                "realized_result": "gain" if realized is not None and realized >= 0 else ("loss" if realized is not None else ""),
                "position_status": "",
                "amount_review_status": status,
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
                "realized_gain_krw": 0.0,
                "realized_loss_krw": 0.0,
                "realized_pnl_status": "available",
                "realized_pnl_row_count": 0,
                "realized_pnl_unavailable_row_count": 0,
                "realized_closed_position_count": 0,
            }
        return {
            "realized_pnl_krw": None,
            "realized_gain_krw": None,
            "realized_loss_krw": None,
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
            "realized_gain_krw": None,
            "realized_loss_krw": None,
            "realized_pnl_status": status_from_list(blocking, default="unavailable"),
            "realized_pnl_row_count": len(ledger),
            "realized_pnl_unavailable_row_count": int(unavailable.sum()),
            "realized_closed_position_count": int(ledger.get("position_status", pd.Series("", index=ledger.index)).fillna("").astype(str).str.lower().eq("closed").sum()),
        }

    pnl = pd.to_numeric(ledger.get("realized_pnl_krw", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    return {
        "realized_pnl_krw": float(pnl.sum()),
        "realized_gain_krw": float(pnl[pnl > 0].sum()),
        "realized_loss_krw": float(pnl[pnl < 0].sum()),
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


def build_reconciliation_summary(processed_dir: Path, holdings: pd.DataFrame, realized_ledger: pd.DataFrame | None = None) -> pd.DataFrame:
    cashflows_path = processed_dir / "processed_cashflows.csv"
    cashflows = load_csv(cashflows_path)
    income = load_csv(processed_dir / "processed_income.csv")
    expenses = load_csv(processed_dir / "processed_expenses.csv")
    fx_events = load_csv(processed_dir / "processed_fx_events.csv")
    transactions = load_csv(processed_dir / "processed_transactions.csv")

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
    realized_pnl = realized_metrics["realized_pnl_krw"] if realized_metrics["realized_pnl_status"] == "available" else 0.0
    explained_profit = unrealized + realized_pnl + dividend_income + interest_income + distribution_income - fee_expense - tax_expense
    explained_profit_status = "available" if realized_metrics["realized_pnl_status"] == "available" else realized_metrics["realized_pnl_status"]

    residual = None
    residual_status = "unavailable"
    if total_return is not None and explained_profit_status == "available":
        residual = total_return - explained_profit
        residual_status = "available"

    seeded_counts = asset_status_counts.copy()
    for key, value in principal_status_counts.items():
        seeded_counts[key] = seeded_counts.get(key, 0) + int(value or 0)
    counts = review_status_counts([holdings, cashflows, income, expenses, fx_events], seeded_counts)
    if realized_metrics["realized_pnl_status"] in counts:
        counts[realized_metrics["realized_pnl_status"]] += int(realized_metrics["realized_pnl_unavailable_row_count"] or 0)
    if realized_metrics["realized_pnl_status"] in REVIEW_NEEDED_STATUSES:
        counts["amount_review_needed"] += int(realized_metrics["realized_pnl_unavailable_row_count"] or 0)
    fx_counts = fx_event_counts(fx_events)

    return summary_metric_rows({
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
        "realized_gain_krw": realized_metrics["realized_gain_krw"],
        "realized_loss_krw": realized_metrics["realized_loss_krw"],
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
    realized = realized_pnl_ledger(transactions, holdings)
    reconciliation = build_reconciliation_summary(processed_dir, holdings, realized)
    if dry_run:
        return {
            "summary_rows": len(summary),
            "holding_rows": len(holdings),
            "history_rows": len(history),
            "risk_rows": len(risk),
            "review_rows": len(review),
            "realized_rows": len(realized),
            "reconciliation_rows": len(reconciliation),
        }
    processed_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(processed_dir / "portfolio_summary.csv", index=False, encoding="utf-8-sig")
    reconciliation.to_csv(processed_dir / "reconciliation_summary.csv", index=False, encoding="utf-8-sig")
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
        "reconciliation_rows": len(reconciliation),
    }
