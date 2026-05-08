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
BALANCE_SOURCE_TYPES = {"holdings", "overseas_balance"}
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
    total_value = float(current_holdings["evaluation_amount"].sum()) if "evaluation_amount" in current_holdings and not current_holdings.empty else 0.0
    if current_holdings.empty:
        current_holdings["weight_pct"] = pd.Series(dtype=float)
        current_holdings["is_leveraged"] = pd.Series(dtype=bool)
    else:
        current_holdings["weight_pct"] = current_holdings["evaluation_amount"].apply(lambda v: round(float(v) / total_value * 100, 4) if total_value else 0)
        current_holdings["is_leveraged"] = current_holdings.apply(lambda r: is_leveraged_etf_name(r.get("security_name", ""), r.get("ticker", "")), axis=1)
    total_unrealized_pnl = float(current_holdings["unrealized_pnl"].sum()) if "unrealized_pnl" in current_holdings and not current_holdings.empty else ""
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
    if dry_run:
        return {"summary_rows": len(summary), "holding_rows": len(holdings), "history_rows": len(history), "risk_rows": len(risk), "review_rows": len(review)}
    processed_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(processed_dir / "portfolio_summary.csv", index=False, encoding="utf-8-sig")
    holdings.to_csv(processed_dir / "processed_holdings.csv", index=False, encoding="utf-8-sig")
    risk.to_csv(processed_dir / "risk_watchlist.csv", index=False, encoding="utf-8-sig")
    review.to_csv(processed_dir / "review_queue.csv", index=False, encoding="utf-8-sig")
    history.to_csv(processed_dir / "history_queue.csv", index=False, encoding="utf-8-sig")
    history.to_csv(processed_dir / "post_mortem_candidates.csv", index=False, encoding="utf-8-sig")
    return {"summary_rows": len(summary), "holding_rows": len(holdings), "history_rows": len(history), "risk_rows": len(risk), "review_rows": len(review)}
