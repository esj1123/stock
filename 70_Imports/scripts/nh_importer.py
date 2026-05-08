from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

NORMALIZED_COLUMNS = [
    "import_id", "source_file", "source_file_type", "account_type", "market", "asset_type",
    "ticker", "security_name", "trade_date", "trade_time", "transaction_type",
    "quantity", "price", "trade_amount", "settlement_amount", "fee", "tax", "currency", "fx_rate",
    "balance_quantity", "evaluation_amount", "unrealized_pnl", "pnl_pct", "raw_memo",
    "quantity_unit", "price_unit", "price_kind", "money_unit_native", "money_unit_krw",
    "amount_kind", "amount_basis", "amount_sign_convention", "amount_confidence",
    "amount_review_status", "amount_review_reason",
    "currency_native", "fx_rate_to_krw", "fx_rate_source", "fx_rate_status",
    "amount_native", "amount_krw", "amount_krw_source",
    "amount_normalization_status", "amount_normalization_reason",
    "trade_amount_native", "trade_amount_krw", "settlement_amount_native", "settlement_amount_krw",
    "fee_native", "fee_krw", "tax_native", "tax_krw",
    "evaluation_amount_native", "evaluation_amount_krw", "unrealized_pnl_native", "unrealized_pnl_krw",
    "cashflow_role", "affects_principal", "affects_profit", "is_internal_transfer",
    "is_valuation_snapshot", "is_trade_settlement", "fx_event_id", "fx_pair_status",
]

INTERNAL_NORMALIZED_COLUMNS = ["_source_sheet", "_raw_row_number"]

HISTORY_COLUMNS = NORMALIZED_COLUMNS + ["history_reason", "suggested_destination", "suggested_action"]

SKIPPED_ROWS_COLUMNS = [
    "source_file", "source_file_type", "account_type", "skip_reason",
    "currency", "fx_rate", "amount_kind", "row_count",
]

OVERSEAS_CASHFLOW_AMOUNT_ONLY_SKIP_REASON = "OVERSEAS_CASHFLOW_AMOUNT_ONLY_NO_IDENTITY"
BROKER_ADJACENT_DUPLICATE_CASHFLOW_SKIP_REASON = "BROKER_ADJACENT_DUPLICATE_CASHFLOW"

HOLDING_DEDUPE_COLUMNS = [
    "dedupe_group_id",
    "dedupe_action",
    "dedupe_reason",
    "preferred_source",
    "dedupe_excluded_count",
    "dedupe_excluded_evaluation_amount",
]

AMOUNT_UNIT_AUDIT_COLUMNS = [
    "source_file", "source_file_type", "account_type", "market", "trade_date", "transaction_type",
    "ticker", "security_name", "raw_quantity", "raw_price", "raw_trade_amount", "raw_settlement_amount",
    "raw_fee", "raw_tax", "quantity_unit", "price_unit", "currency_native", "money_unit_native",
    "fx_rate_to_krw", "fx_rate_source", "amount_kind", "amount_basis", "amount_native", "amount_krw",
    "cashflow_role", "affects_principal", "affects_profit", "is_internal_transfer",
    "amount_confidence", "amount_review_status", "amount_review_reason",
]

UNIT_MISMATCH_AUDIT_COLUMNS = [
    "source_file", "source_file_type", "account_type", "market", "transaction_type", "ticker",
    "currency_native", "amount_normalization_status", "amount_normalization_reason", "cashflow_role",
]

HOLDING_SOURCE_PRIORITY = {
    "overseas_balance": 0,
    "holdings": 10,
}

BALANCE_SOURCE_TYPES = {"holdings", "overseas_balance"}
TRANSACTION_SOURCE_TYPES = {"transaction_history", "transactions", "cashflow"}

HOLDING_QUANTITY_TOLERANCE = 1e-6
HOLDING_AMOUNT_ABS_TOLERANCE = 1.0
HOLDING_AMOUNT_REL_TOLERANCE = 0.001

GENERIC_ACCOUNT_TYPES = {"", "comprehensive", "overseas", "generic"}

TRANSACTION_TYPES = {
    "buy", "sell", "deposit", "withdrawal", "dividend", "interest", "exchange",
    "fee", "tax", "transfer", "split", "rights", "unknown",
}

VALID_CURRENCY_CODES = {
    "KRW", "USD", "JPY", "CNY", "HKD", "EUR", "GBP", "CAD", "AUD", "CHF", "SGD", "TWD",
}

CASH_ASSET_KEYWORDS = [
    "예수금", "현금", "외화예수금", "원화예수금", "cash", "cash balance", "deposit",
    "withdrawable", "출금가능금액",
]

LEVERAGED_ETF_KEYWORDS = [
    "2x", "3x", "2배", "3배", "-2배", "레버리지", "leveraged", "daily 2x", "daily 3x",
    "bull", "bear", "ultra", "graniteshares", "그래닛셰어즈", "direxion", "디렉시온",
    "proshares", "t-rex", "t rex", "티렉스", "tradr", "defiance", "디파이언스",
]

# Static aliases for broker exports where comprehensive holdings use an ISIN-like
# code but overseas balance rows use a display name with the trading symbol.
KNOWN_OVERSEAS_ISIN_SYMBOL_ALIASES = {
    "US00760J1088": "AEHR",
    "US88160R1014": "TSLA",
    "US67066G1040": "NVDA",
    "US02079K3059": "GOOGL",
    "KYG254571055": "CRDO",
    "US36828A1016": "GEV",
    "US46152A5368": "APPX",
    "US38747R8271": "NVDL",
    "US25461A8669": "MSFU",
    "US78433H6751": "QQQI",
}

COLUMN_ALIASES = {
    "trade_date": ["실거래일자", "거래일자", "거래일", "일자", "매매일", "체결일", "정산일"],
    "trade_time": ["거래시간", "시간", "체결시간"],
    "transaction_raw": ["거래유형", "거래구분", "매매구분", "상세내용", "내용", "적요", "구분", "거래내용", "입출금구분"],
    "security_name": ["종목명", "종목명칭", "상품명", "명칭", "종목"],
    "ticker": ["종목코드", "단축코드", "티커", "코드"],
    "quantity": ["수량", "매매수량", "체결수량", "보유수량", "잔고수량"],
    "price": ["단가", "평균단가", "매입단가", "현재가", "체결가", "가격"],
    "trade_amount": ["거래금액", "매매금액", "체결금액", "금액"],
    "settlement_amount": ["정산금액", "결제금액", "잔고금액", "원화금액"],
    "deposit_amount": ["입금액", "입금금액", "입금"],
    "withdrawal_amount": ["출금액", "출금금액", "출금"],
    "fee": ["수수료", "제수수료", "매매수수료"],
    "tax": ["세금", "제세금", "거래세", "원천징수세"],
    "currency": ["통화", "통화코드", "거래통화", "결제통화"],
    "balance_quantity": ["잔고", "잔고수량", "보유수량", "수량"],
    "evaluation_amount": ["평가금액", "평가액", "외화평가금액", "원화평가금액", "잔고금액"],
    "unrealized_pnl": ["평가손익", "손익", "평가손익금액"],
    "pnl_pct": ["수익률", "평가손익률", "손익률"],
    "exchange_rate": ["환율"],
    "cash": ["예수금", "현금", "출금가능금액"],
    "memo": ["비고", "메모", "상세내용", "적요", "받는통장표시내용", "거래내역메모"],
}

SENSITIVE_PATTERNS = [
    re.compile(r"\b(?!20\d{2}-\d{2}-\d{2}\b)\d{2,6}-\d{2,8}-\d{2,8}\b"),
    re.compile(r"\b\d{6}-[1-4]\d{6}\b"),
    re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"),
    re.compile(r"(?i)(api[_-]?key|api[_-]?secret|access[_-]?token|password|주문비밀번호)\s*[:=]\s*\S+"),
]


@dataclass
class ImportSummary:
    raw_files: int = 0
    parsed_rows: int = 0
    duplicate_rows_removed: int = 0
    unclassified_rows: int = 0
    unknown_columns: int = 0


def normalize_key(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(value or "")).lower()


MULTIINDEX_COLUMN_SEPARATOR = " __ "
COLLAPSED_RAW_ROW_NUMBER_COLUMN = "_collapsed_raw_row_number"
STRICT_MULTIINDEX_EXACT_CANONICALS = {
    "quantity",
    "trade_amount",
    "balance_quantity",
}


def flatten_column_name(column: Any) -> str:
    if not isinstance(column, tuple):
        return str(column).strip()
    parts: list[str] = []
    for value in column:
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        text = str(value).strip()
        if not text or text.lower() == "nan" or text.lower().startswith("unnamed:"):
            continue
        if parts and normalize_key(parts[-1]) == normalize_key(text):
            continue
        parts.append(text)
    return MULTIINDEX_COLUMN_SEPARATOR.join(parts).strip()


def column_label_parts(column: Any) -> list[str]:
    return [part.strip() for part in str(column).split(MULTIINDEX_COLUMN_SEPARATOR) if part.strip()]


def canonical_for_header_part(label: Any, preferred: list[str] | None = None) -> str:
    label_norm = normalize_key(label)
    if not label_norm:
        return ""
    preferred = preferred or []

    exact_matches: list[str] = []
    for canonical, aliases in COLUMN_ALIASES.items():
        if any(label_norm == normalize_key(alias) for alias in aliases):
            exact_matches.append(canonical)
    for canonical in preferred:
        if canonical in exact_matches:
            return canonical
    if exact_matches:
        return exact_matches[0]

    partial_matches: list[str] = []
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in sorted(aliases, key=lambda value: len(normalize_key(value)), reverse=True):
            alias_norm = normalize_key(alias)
            if alias_norm and alias_norm in label_norm:
                partial_matches.append(canonical)
                break
    for canonical in preferred:
        if canonical in partial_matches:
            return canonical
    return partial_matches[0] if partial_matches else ""


def paired_column_targets(column: Any) -> tuple[str, str] | None:
    parts = column_label_parts(column)
    if len(parts) < 2:
        return None
    left = canonical_for_header_part(
        parts[0],
        ["quantity", "trade_amount", "balance_quantity", "fee", "transaction_raw"],
    )
    right_preferences = {
        "quantity": ["price"],
        "trade_amount": ["settlement_amount"],
        "balance_quantity": ["evaluation_amount"],
        "fee": ["tax"],
        "transaction_raw": ["memo"],
    }
    right = canonical_for_header_part(parts[1], right_preferences.get(left, []))
    allowed_pairs = {
        ("quantity", "price"),
        ("trade_amount", "settlement_amount"),
        ("balance_quantity", "evaluation_amount"),
        ("fee", "tax"),
        ("transaction_raw", "memo"),
    }
    return (left, right) if (left, right) in allowed_pairs else None


def canonical_output_column(canonical: str) -> str:
    aliases = COLUMN_ALIASES.get(canonical, [])
    return aliases[0] if aliases else canonical


def merge_cell_value(merged: dict[Any, Any], target: Any, value: Any, append: bool = False) -> None:
    if is_blank_text(value):
        return
    current = merged.get(target, "")
    if not append:
        if is_blank_text(current):
            merged[target] = value
        return
    value_text = str(value).strip()
    if is_blank_text(current):
        merged[target] = value_text
        return
    current_parts = [part.strip() for part in str(current).split(";") if part.strip()]
    if value_text not in current_parts:
        merged[target] = f"{current}; {value_text}"


def rows_have_compatible_pair_identity(left: pd.Series, right: pd.Series, identity_cols: list[Any]) -> bool:
    for col in identity_cols:
        if col is None:
            continue
        left_value = left.get(col, "")
        right_value = right.get(col, "")
        if not is_blank_text(right_value) and not normalized_values_equal(left_value, right_value):
            return False
    return True


def collapse_namoo_transaction_pair_rows(df: pd.DataFrame, source_file: str = "", sheet_name: str = "") -> pd.DataFrame:
    if df.empty or len(df) < 2:
        return df

    columns = list(df.columns)
    pair_map = {col: targets for col in columns if (targets := paired_column_targets(col)) is not None}
    if not pair_map:
        return df

    non_pair_columns = [col for col in columns if col not in pair_map]
    identity_cols = [
        find_column(non_pair_columns, "trade_date"),
        find_column(non_pair_columns, "ticker"),
        find_column(non_pair_columns, "security_name"),
    ]
    transaction_col = find_column(non_pair_columns, "transaction_raw")

    collapsed_rows: list[dict[Any, Any]] = []
    records = list(df.reset_index(drop=True).iterrows())
    idx = 0
    while idx < len(records):
        row_number, left = records[idx]
        if idx + 1 >= len(records):
            item = left.to_dict()
            item[COLLAPSED_RAW_ROW_NUMBER_COLUMN] = str(row_number + 1)
            collapsed_rows.append(item)
            break

        next_row_number, right = records[idx + 1]
        left_has_pair_values = any(not is_blank_text(left.get(col, "")) for col in pair_map)
        right_has_pair_values = any(not is_blank_text(right.get(col, "")) for col in pair_map)
        left_has_identity = any(
            col is not None and not is_blank_text(left.get(col, ""))
            for col in identity_cols
        )
        right_has_identity = any(
            col is not None and not is_blank_text(right.get(col, ""))
            for col in identity_cols
        )
        right_has_transaction_marker = transaction_col is not None and not is_blank_text(right.get(transaction_col, ""))
        right_starts_new_transaction = right_has_identity and right_has_transaction_marker
        should_collapse = (
            left_has_pair_values
            and right_has_pair_values
            and left_has_identity
            and not right_starts_new_transaction
            and rows_have_compatible_pair_identity(left, right, identity_cols)
        )

        if not should_collapse:
            item = left.to_dict()
            item[COLLAPSED_RAW_ROW_NUMBER_COLUMN] = str(row_number + 1)
            collapsed_rows.append(item)
            idx += 1
            continue

        merged: dict[Any, Any] = {}
        for col in non_pair_columns:
            merged[col] = left.get(col, "")
            if is_blank_text(merged[col]):
                merged[col] = right.get(col, "")

        memo_col = canonical_output_column("memo")
        transaction_col = canonical_output_column("transaction_raw")
        for col, (left_target, right_target) in pair_map.items():
            for target, value in [(left_target, left.get(col, "")), (right_target, right.get(col, ""))]:
                if target in {"transaction_raw", "memo"}:
                    if target == "transaction_raw" and is_blank_text(merged.get(transaction_col, "")):
                        merge_cell_value(merged, transaction_col, value)
                    merge_cell_value(merged, memo_col, value, append=True)
                    continue
                merge_cell_value(merged, canonical_output_column(target), value)

        merged[COLLAPSED_RAW_ROW_NUMBER_COLUMN] = f"{row_number + 1}-{next_row_number + 1}"
        collapsed_rows.append(merged)
        idx += 2

    return pd.DataFrame(collapsed_rows)


def extract_symbol_from_parentheses(value: Any) -> str:
    if is_blank_text(value):
        return ""
    text = str(value)
    for raw_candidate in re.findall(r"\(([^()]+)\)", text):
        candidate = raw_candidate.strip().upper()
        candidate = re.sub(r"^(NASDAQ|NYSE|AMEX|ARCA|US)\s*[:：]\s*", "", candidate)
        if candidate not in VALID_CURRENCY_CODES and re.fullmatch(r"[A-Z]{1,6}[A-Z0-9.\-]{0,4}", candidate):
            return candidate
    return ""


def extract_isin_like(value: Any) -> str:
    if is_blank_text(value):
        return ""
    text = str(value).upper()
    match = re.search(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b", text)
    return match.group(0) if match else ""


def extract_us_symbol(value: Any) -> str:
    if is_blank_text(value):
        return ""
    parenthesized = extract_symbol_from_parentheses(value)
    if parenthesized:
        return parenthesized
    text = str(value).strip().upper()
    isin = extract_isin_like(text)
    if isin and isin in KNOWN_OVERSEAS_ISIN_SYMBOL_ALIASES:
        return KNOWN_OVERSEAS_ISIN_SYMBOL_ALIASES[isin]
    if text not in VALID_CURRENCY_CODES and re.fullmatch(r"[A-Z]{1,6}[A-Z0-9.\-]{0,4}", text):
        return text
    return ""


def normalize_security_name_for_key(value: Any) -> str:
    if is_blank_text(value):
        return ""
    text = re.sub(r"\([^()]*\)", "", str(value).upper())
    return re.sub(r"[^0-9A-Z가-힣]+", "", text)


def parse_korean_number(value: Any) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "-", "--"}:
        return 0.0
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    if "▲" in s or "△" in s:
        negative = True
    s = s.replace(",", "").replace("%", "").replace("원", "").replace("$", "").replace("USD", "").replace("KRW", "")
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s or s in {"-", ".", "-."}:
        return 0.0
    try:
        num = float(s)
        return -abs(num) if negative else num
    except ValueError:
        return 0.0


def parse_korean_percent(value: Any) -> float:
    return parse_korean_number(value)


def is_blank_text(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    return str(value).strip().lower() in {"", "nan", "none", "na", "n/a", "<na>", "-", "--"}


def parse_optional_korean_number(value: Any) -> float | None:
    if is_blank_text(value):
        return None
    return parse_korean_number(value)


def fx_rate_from_text(value: Any) -> float | None:
    if is_blank_text(value):
        return None
    text = str(value).strip().replace(",", "")
    cleaned = re.sub(r"[^0-9.]", "", text)
    if not cleaned or not re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def currency_code_from_text(value: Any) -> str:
    if is_blank_text(value):
        return ""
    text = str(value).strip().upper()
    if fx_rate_from_text(text) is not None and not re.search(r"[A-Z가-힣]", text):
        return ""
    for raw, code in [
        ("달러", "USD"), ("USD", "USD"), ("$", "USD"),
        ("원화", "KRW"), ("KRW", "KRW"),
        ("엔", "JPY"), ("JPY", "JPY"),
        ("위안", "CNY"), ("CNY", "CNY"),
        ("홍콩", "HKD"), ("HKD", "HKD"),
        ("유로", "EUR"), ("EUR", "EUR"),
    ]:
        if raw in text:
            return code
    match = re.search(r"\b[A-Z]{3}\b", text)
    if match:
        return match.group(0)
    return text if re.fullmatch(r"[A-Z]{3}", text) else ""


def normalize_currency_and_fx_rate(raw_currency: Any, raw_fx_rate: Any = "", source_type: str = "", market: str = "") -> tuple[str, Any]:
    source_key = str(source_type or "").strip().lower()
    market_key = str(market or "").strip().upper()
    default_currency = (
        "USD"
        if "overseas" in source_key or (source_key in {"transaction_history", "transactions"} and market_key == "US")
        else "KRW"
    )
    fx_rate = fx_rate_from_text(raw_fx_rate)
    currency = currency_code_from_text(raw_currency)
    currency_fx_rate = fx_rate_from_text(raw_currency)
    if not currency:
        if fx_rate is None and currency_fx_rate is not None:
            fx_rate = currency_fx_rate
        currency = default_currency
    return currency, (fx_rate if fx_rate is not None else pd.NA)


def normalized_fx_rate_value(value: Any) -> float | None:
    if is_blank_text(value):
        return None
    try:
        return float(value)
    except Exception:
        return fx_rate_from_text(value)


def convert_native_to_krw(amount: float, currency_native: str, fx_rate_to_krw: Any) -> tuple[float, Any, str]:
    currency = str(currency_native or "").strip().upper()
    if currency == "KRW":
        return amount, amount, "raw_native"
    if abs(float(amount or 0)) <= 1e-9 and currency:
        return amount, 0.0, "raw_native"
    fx_rate = normalized_fx_rate_value(fx_rate_to_krw)
    if currency and fx_rate is not None:
        return amount, round(amount * fx_rate, 6), "derived_krw_from_fx"
    return amount, pd.NA, ""


def money_status(currency_native: str, fx_rate_to_krw: Any, amount: float) -> tuple[str, str]:
    currency = str(currency_native or "").strip().upper()
    if not currency:
        return "currency_ambiguous", "native currency could not be inferred"
    if currency == "KRW":
        return "ok", ""
    if abs(float(amount or 0)) <= 1e-9:
        return "ok", ""
    if normalized_fx_rate_value(fx_rate_to_krw) is None:
        return "fx_missing", "non-KRW native amount has no FX rate or broker-provided KRW amount"
    return "ok", ""


def cashflow_role_for(tx_type: str, source_type: str, asset_type: str = "") -> str:
    tx = str(tx_type or "").strip().lower()
    source = str(source_type or "").strip().lower()
    asset = str(asset_type or "").strip().lower()
    if source in BALANCE_SOURCE_TYPES:
        return "valuation_snapshot"
    if asset == "cash" and tx == "unknown":
        return "cash_balance"
    return {
        "deposit": "external_deposit",
        "withdrawal": "external_withdrawal",
        "dividend": "income_dividend",
        "interest": "income_interest",
        "exchange": "internal_fx_exchange",
        "buy": "trade_settlement",
        "sell": "trade_settlement",
        "fee": "expense_fee",
        "tax": "expense_tax",
        "transfer": "internal_transfer",
    }.get(tx, "unknown")


def classify_cashflow_role(row: dict[str, Any] | pd.Series) -> str:
    return cashflow_role_for(
        str(_row_value(row, "transaction_type") or ""),
        str(_row_value(row, "source_file_type") or ""),
        str(_row_value(row, "asset_type") or ""),
    )


def infer_numeric_unit(row: dict[str, Any] | pd.Series, field_name: str) -> str:
    field = str(field_name or "").strip().lower()
    currency = currency_code_from_text(_row_value(row, "currency_native")) or currency_code_from_text(_row_value(row, "currency"))
    asset_type = str(_row_value(row, "asset_type") or "").strip().lower()
    if field == "quantity":
        quantity = parse_korean_number(_row_value(row, "quantity"))
        return "shares" if abs(quantity) > 1e-9 and asset_type != "cash" else ""
    if field == "price":
        price = parse_korean_number(_row_value(row, "price"))
        if abs(price) <= 1e-9:
            return ""
        quantity_unit = infer_numeric_unit(row, "quantity")
        return f"{currency}/share" if currency and quantity_unit == "shares" else currency
    if field == "fx_rate":
        return "KRW/native"
    if field in {"trade_amount", "settlement_amount", "fee", "tax", "evaluation_amount", "unrealized_pnl", "amount"}:
        return currency
    return ""


def infer_amount_currency(row: dict[str, Any] | pd.Series, amount_kind: str = "") -> str:
    explicit = currency_code_from_text(_row_value(row, "currency_native")) or currency_code_from_text(_row_value(row, "currency"))
    if explicit:
        return explicit
    source_type = str(_row_value(row, "source_file_type") or "").strip().lower()
    market = str(_row_value(row, "market") or "").strip().upper()
    account_type = str(_row_value(row, "account_type") or "").strip().lower()
    if market == "US" or "overseas" in source_type or "overseas" in account_type:
        return "USD"
    if market == "KR" or account_type == "isa":
        return "KRW"
    return ""


def amount_kind_for(
    tx_type: str,
    source_type: str,
    asset_type: str,
    trade_amount: float,
    settlement_amount: float,
    fee: float,
    tax: float,
    evaluation_amount: float,
    unrealized_pnl: float,
    quantity: float,
    price: float,
) -> str:
    source = str(source_type or "").strip().lower()
    tx = str(tx_type or "").strip().lower()
    asset = str(asset_type or "").strip().lower()
    if source in BALANCE_SOURCE_TYPES:
        if asset == "cash":
            return "cash_balance"
        if abs(evaluation_amount) > 1e-9:
            return "evaluation_amount"
        if abs(unrealized_pnl) > 1e-9:
            return "unrealized_pnl"
    if tx == "dividend":
        return "dividend"
    if tx == "interest":
        return "interest"
    if tx == "exchange":
        return "fx_exchange_leg"
    if tx == "fee" or (abs(fee) > 1e-9 and not any(abs(v) > 1e-9 for v in [trade_amount, settlement_amount])):
        return "fee"
    if tx == "tax" or (abs(tax) > 1e-9 and not any(abs(v) > 1e-9 for v in [trade_amount, settlement_amount])):
        return "tax"
    if tx in {"buy", "sell"} and abs(trade_amount) > 1e-9:
        return "trade_amount"
    if tx in {"deposit", "withdrawal"} and abs(settlement_amount or trade_amount) > 1e-9:
        return "settlement_amount"
    if abs(trade_amount) > 1e-9:
        return "trade_amount"
    if abs(settlement_amount) > 1e-9:
        return "settlement_amount"
    if abs(price) > 1e-9:
        return "unit_price"
    if abs(quantity) > 1e-9:
        return "quantity"
    return "unknown"


def primary_amount_for_kind(
    amount_kind: str,
    trade_amount: float,
    settlement_amount: float,
    fee: float,
    tax: float,
    evaluation_amount: float,
    unrealized_pnl: float,
    quantity: float,
    price: float,
) -> float:
    return {
        "trade_amount": trade_amount,
        "settlement_amount": settlement_amount,
        "fee": fee,
        "tax": tax,
        "dividend": settlement_amount or trade_amount,
        "interest": settlement_amount or trade_amount,
        "evaluation_amount": evaluation_amount,
        "unrealized_pnl": unrealized_pnl,
        "cash_balance": settlement_amount or trade_amount or evaluation_amount,
        "fx_exchange_leg": settlement_amount or trade_amount,
        "unit_price": price,
        "quantity": quantity,
    }.get(amount_kind, 0.0)


def is_money_amount_kind(amount_kind: str) -> bool:
    return amount_kind not in {"quantity", "unit_price", "fx_rate", "unknown"}


def normalize_amount_fields(row: dict[str, Any] | pd.Series) -> dict[str, Any]:
    tx_type = str(_row_value(row, "transaction_type") or "")
    source_type = str(_row_value(row, "source_file_type") or "")
    asset_type = str(_row_value(row, "asset_type") or "")
    quantity = parse_korean_number(_row_value(row, "quantity"))
    price = parse_korean_number(_row_value(row, "price"))
    trade_amount = parse_korean_number(_row_value(row, "trade_amount"))
    settlement_amount = parse_korean_number(_row_value(row, "settlement_amount"))
    fee = parse_korean_number(_row_value(row, "fee"))
    tax = parse_korean_number(_row_value(row, "tax"))
    evaluation_amount = parse_korean_number(_row_value(row, "evaluation_amount"))
    unrealized_pnl = parse_korean_number(_row_value(row, "unrealized_pnl"))
    amount_kind = amount_kind_for(
        tx_type,
        source_type,
        asset_type,
        trade_amount,
        settlement_amount,
        fee,
        tax,
        evaluation_amount,
        unrealized_pnl,
        quantity,
        price,
    )
    currency_native = infer_amount_currency(row, amount_kind)
    fx_rate_to_krw = _row_value(row, "fx_rate_to_krw")
    if is_blank_text(fx_rate_to_krw):
        fx_rate_to_krw = _row_value(row, "fx_rate")
    amount_native_value = primary_amount_for_kind(
        amount_kind,
        trade_amount,
        settlement_amount,
        fee,
        tax,
        evaluation_amount,
        unrealized_pnl,
        quantity,
        price,
    )
    amount_native, amount_krw, amount_krw_source = convert_native_to_krw(amount_native_value, currency_native, fx_rate_to_krw)
    amount_is_money = is_money_amount_kind(amount_kind)
    amount_review_status, amount_review_reason = (
        money_status(currency_native, fx_rate_to_krw, amount_native_value)
        if amount_is_money
        else ("not_applicable", "")
    )
    if not amount_is_money:
        amount_basis = "not_money" if amount_kind in {"quantity", "unit_price"} else "unknown"
        amount_confidence = "official_raw" if amount_kind in {"quantity", "unit_price"} else "unavailable"
    elif amount_review_status == "ok" and currency_native == "KRW":
        amount_basis = "raw_native"
        amount_confidence = "official_raw"
    elif amount_review_status == "ok":
        amount_basis = "derived_krw_from_fx"
        amount_confidence = "derived"
        amount_krw_source = "fx_rate_to_krw"
    else:
        amount_basis = "raw_native"
        amount_confidence = "unavailable"
    fx_rate_status = (
        "available"
        if normalized_fx_rate_value(fx_rate_to_krw) is not None
        else ("not_required" if currency_native == "KRW" else "missing")
    )
    fx_rate_source = "raw" if fx_rate_status == "available" else ""
    cashflow_role = classify_cashflow_role({**dict(row), "asset_type": asset_type, "transaction_type": tx_type, "source_file_type": source_type})
    affects_principal = cashflow_role in {"external_deposit", "external_withdrawal"} and amount_review_status == "ok"
    affects_profit = cashflow_role in {"income_dividend", "income_interest"} or amount_kind == "unrealized_pnl"
    is_internal_transfer = cashflow_role in {"internal_fx_exchange", "internal_transfer"}
    is_valuation_snapshot = cashflow_role == "valuation_snapshot"
    is_trade_settlement = cashflow_role == "trade_settlement"
    trade_amount_native, trade_amount_krw, _ = convert_native_to_krw(trade_amount, currency_native, fx_rate_to_krw)
    settlement_amount_native, settlement_amount_krw, _ = convert_native_to_krw(settlement_amount, currency_native, fx_rate_to_krw)
    fee_native, fee_krw, _ = convert_native_to_krw(fee, currency_native, fx_rate_to_krw)
    tax_native, tax_krw, _ = convert_native_to_krw(tax, currency_native, fx_rate_to_krw)
    evaluation_amount_native, evaluation_amount_krw, _ = convert_native_to_krw(evaluation_amount, currency_native, fx_rate_to_krw)
    unrealized_pnl_native, unrealized_pnl_krw, _ = convert_native_to_krw(unrealized_pnl, currency_native, fx_rate_to_krw)
    source_type_key = source_type.strip().lower()
    is_balance_source = source_type_key in BALANCE_SOURCE_TYPES
    return {
        "quantity_unit": infer_numeric_unit({**dict(row), "currency_native": currency_native}, "quantity"),
        "price_unit": infer_numeric_unit({**dict(row), "currency_native": currency_native}, "price"),
        "price_kind": "unit_price" if abs(price) > 1e-9 else "",
        "money_unit_native": currency_native if amount_is_money else "",
        "money_unit_krw": "KRW" if amount_is_money else "",
        "amount_kind": amount_kind,
        "amount_basis": amount_basis,
        "amount_sign_convention": "raw_positive_transaction_type_sign",
        "amount_confidence": amount_confidence,
        "amount_review_status": amount_review_status,
        "amount_review_reason": amount_review_reason,
        "currency_native": currency_native,
        "fx_rate_to_krw": fx_rate_to_krw,
        "fx_rate_source": fx_rate_source,
        "fx_rate_status": fx_rate_status,
        "amount_native": amount_native if amount_is_money else pd.NA,
        "amount_krw": amount_krw if amount_is_money else pd.NA,
        "amount_krw_source": amount_krw_source,
        "amount_normalization_status": amount_review_status,
        "amount_normalization_reason": amount_review_reason,
        "trade_amount_native": trade_amount_native,
        "trade_amount_krw": trade_amount_krw,
        "settlement_amount_native": settlement_amount_native,
        "settlement_amount_krw": settlement_amount_krw,
        "fee_native": fee_native,
        "fee_krw": fee_krw,
        "tax_native": tax_native,
        "tax_krw": tax_krw,
        "evaluation_amount_native": evaluation_amount_native if is_balance_source else pd.NA,
        "evaluation_amount_krw": evaluation_amount_krw if is_balance_source else pd.NA,
        "unrealized_pnl_native": unrealized_pnl_native if is_balance_source else pd.NA,
        "unrealized_pnl_krw": unrealized_pnl_krw if is_balance_source else pd.NA,
        "cashflow_role": cashflow_role,
        "affects_principal": affects_principal,
        "affects_profit": affects_profit,
        "is_internal_transfer": is_internal_transfer,
        "is_valuation_snapshot": is_valuation_snapshot,
        "is_trade_settlement": is_trade_settlement,
        "fx_event_id": _row_value(row, "fx_event_id"),
        "fx_pair_status": "unpaired" if cashflow_role == "internal_fx_exchange" else "",
    }


def normalize_date(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, (int, float)) and 20000 < float(value) < 80000:
        try:
            return pd.to_datetime(value, unit="D", origin="1899-12-30").strftime("%Y-%m-%d")
        except Exception:
            pass
    s = str(value).strip()
    s = re.sub(r"\(.*?\)", "", s).strip()
    m = re.match(r"^(\d{4})[.\-/ ]?(\d{1,2})[.\-/ ]?(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    try:
        dt = pd.to_datetime(value)
        if not pd.isna(dt):
            return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""
    return ""


def normalize_time(value: Any) -> str:
    s = str(value or "").strip()
    if not s or s.lower() == "nan":
        return ""
    m = re.match(r"^(\d{1,2}):?(\d{2}):?(\d{2})?$", s)
    if m:
        return f"{m.group(1).zfill(2)}:{m.group(2)}:{m.group(3) or '00'}"
    return s


def classify_transaction_type(text: Any) -> str:
    s = str(text or "").lower()
    english_tokens = set(re.findall(r"[a-z]+", s))
    for name, keys in [
        ("deposit", ["deposit"]),
        ("withdrawal", ["withdrawal", "withdraw"]),
        ("exchange", ["exchange"]),
        ("dividend", ["dividend", "div"]),
        ("interest", ["interest"]),
        ("fee", ["fee"]),
        ("tax", ["tax"]),
    ]:
        if any(k in english_tokens for k in keys):
            return name
    rules = [
        ("buy", ["매수", "buy", "매입"]),
        ("sell", ["매도", "sell"]),
        ("deposit", ["입금", "대체입금", "현금입금"]),
        ("withdrawal", ["출금", "현금출금"]),
        ("dividend", ["배당", "분배금", "dividend", "div"]),
        ("interest", ["이자"]),
        ("exchange", ["환전", "외화매수", "외화매도"]),
        ("fee", ["수수료"]),
        ("tax", ["세금", "제세금", "거래세"]),
        ("transfer", ["이체", "대체"]),
        ("split", ["액면분할", "split"]),
        ("rights", ["권리", "유상", "무상"]),
    ]
    for name, keys in rules:
        if any(k.lower() in s for k in keys):
            return name
    return "unknown"


def is_zero_or_blank_amount(value: Any, tolerance: float = 1e-9) -> bool:
    if is_blank_text(value):
        return True
    return abs(parse_korean_number(value)) <= tolerance


def is_overseas_cashflow_amount_only_helper_row(row: dict[str, Any] | pd.Series, tolerance: float = 1e-9) -> bool:
    source_type = str(_row_value(row, "source_file_type") or "").strip().lower()
    account_type = str(_row_value(row, "account_type") or "").strip().lower()
    transaction_type = str(_row_value(row, "transaction_type") or "").strip().lower()
    if source_type != "cashflow" or account_type != "overseas" or transaction_type != "unknown":
        return False

    for field in ["ticker", "security_name", "trade_date", "raw_memo"]:
        if not is_blank_text(_row_value(row, field)):
            return False

    currency = currency_code_from_text(_row_value(row, "currency"))
    if not currency:
        return False

    fx_rate = _row_value(row, "fx_rate")
    if is_blank_text(fx_rate) and "overseas" not in f"{source_type} {account_type}":
        return False

    trade_amount = parse_korean_number(_row_value(row, "trade_amount"))
    settlement_amount = parse_korean_number(_row_value(row, "settlement_amount"))
    if trade_amount <= 0 or settlement_amount <= 0:
        return False
    if abs(trade_amount - settlement_amount) > tolerance:
        return False

    for field in ["quantity", "price", "fee", "tax"]:
        if not is_zero_or_blank_amount(_row_value(row, field), tolerance=tolerance):
            return False

    keyword_text = " ".join(str(_row_value(row, field) or "") for field in ["ticker", "security_name", "raw_memo"])
    if classify_transaction_type(keyword_text) != "unknown":
        return False

    return True


def is_valid_normalized_date(value: Any) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value or "").strip()))


def boolish_text(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def is_principal_cashflow_row(row: dict[str, Any] | pd.Series, tolerance: float = 1e-9) -> bool:
    tx_type = str(_row_value(row, "transaction_type") or "").strip().lower()
    if tx_type not in {"deposit", "withdrawal"}:
        return False
    role = str(_row_value(row, "cashflow_role") or "").strip().lower()
    if role:
        expected_role = "external_deposit" if tx_type == "deposit" else "external_withdrawal"
        if role != expected_role:
            return False
        if not boolish_text(_row_value(row, "affects_principal")):
            return False
        if str(_row_value(row, "amount_review_status") or "").strip().lower() != "ok":
            return False
    if not is_valid_normalized_date(_row_value(row, "trade_date")):
        return False
    if not is_blank_text(_row_value(row, "ticker")):
        return False
    if not is_zero_or_blank_amount(_row_value(row, "quantity"), tolerance=tolerance):
        return False
    settlement_amount = parse_korean_number(_row_value(row, "settlement_amount"))
    return abs(settlement_amount) > tolerance


def is_position_snapshot_row(row: dict[str, Any] | pd.Series, tolerance: float = 1e-9) -> bool:
    source_type = str(_row_value(row, "source_file_type") or "").strip().lower()
    if source_type in {"transaction_history", "transactions"}:
        return False
    has_identity = not is_blank_text(_row_value(row, "ticker")) or not is_blank_text(_row_value(row, "security_name"))
    if not has_identity:
        return False
    balance_quantity = parse_korean_number(_row_value(row, "balance_quantity"))
    evaluation_amount = parse_korean_number(_row_value(row, "evaluation_amount"))
    quantity = parse_korean_number(_row_value(row, "quantity"))
    if abs(balance_quantity) > tolerance or abs(evaluation_amount) > tolerance:
        return True
    return source_type in BALANCE_SOURCE_TYPES and abs(quantity) > tolerance


def is_transaction_ledger_row(row: dict[str, Any] | pd.Series, tolerance: float = 1e-9) -> bool:
    if is_position_snapshot_row(row, tolerance=tolerance):
        return False
    source_type = str(_row_value(row, "source_file_type") or "").strip().lower()
    if source_type in TRANSACTION_SOURCE_TYPES:
        return True
    tx_type = str(_row_value(row, "transaction_type") or "").strip().lower()
    if tx_type in TRANSACTION_TYPES - {"unknown"} and is_valid_normalized_date(_row_value(row, "trade_date")):
        return True
    amount = parse_korean_number(_row_value(row, "settlement_amount")) or parse_korean_number(_row_value(row, "trade_amount"))
    return tx_type in TRANSACTION_TYPES - {"unknown"} and abs(amount) > tolerance


def is_blankish_or_zeroish(value: Any, tolerance: float = 1e-9) -> bool:
    if is_blank_text(value):
        return True
    return abs(parse_korean_number(value)) <= tolerance


def normalized_values_equal(left: Any, right: Any, tolerance: float = 1e-9) -> bool:
    if is_blank_text(left) and is_blank_text(right):
        return True
    return str(left or "").strip() == str(right or "").strip()


def normalized_numbers_equal(left: Any, right: Any, tolerance: float = 1e-9) -> bool:
    if is_blank_text(left) and is_blank_text(right):
        return True
    return abs(parse_korean_number(left) - parse_korean_number(right)) <= tolerance


def raw_row_start_order_value(value: Any) -> float:
    text = str(value or "").strip()
    if "-" in text:
        text = text.split("-", 1)[0]
    return parse_korean_number(text)


def raw_row_end_order_value(value: Any) -> float:
    text = str(value or "").strip()
    if "-" in text:
        text = text.rsplit("-", 1)[-1]
    return parse_korean_number(text)


def principal_cashflow_import_key_needs_raw_position(row: dict[str, Any]) -> bool:
    return is_principal_cashflow_row(row)


def adjacent_principal_cashflow_duplicate(left: pd.Series, right: pd.Series, tolerance: float = 1e-9) -> bool:
    if not is_principal_cashflow_row(left, tolerance=tolerance) or not is_principal_cashflow_row(right, tolerance=tolerance):
        return False
    if not normalized_values_equal(left.get("source_file", ""), right.get("source_file", "")):
        return False
    if not normalized_values_equal(left.get("_source_sheet", ""), right.get("_source_sheet", "")):
        return False
    left_row = raw_row_end_order_value(left.get("_raw_row_number", ""))
    right_row = raw_row_start_order_value(right.get("_raw_row_number", ""))
    if int(right_row) - int(left_row) != 1:
        return False

    text_fields = [
        "source_file_type", "account_type", "market", "asset_type", "ticker", "security_name",
        "trade_date", "trade_time", "transaction_type", "currency",
    ]
    number_fields = [
        "quantity", "price", "trade_amount", "settlement_amount", "fee", "tax", "fx_rate",
        "balance_quantity", "evaluation_amount", "unrealized_pnl", "pnl_pct",
    ]
    if any(not normalized_values_equal(left.get(field, ""), right.get(field, "")) for field in text_fields):
        return False
    if any(not normalized_numbers_equal(left.get(field, ""), right.get(field, ""), tolerance=tolerance) for field in number_fields):
        return False

    left_memo = left.get("raw_memo", "")
    right_memo = right.get("raw_memo", "")
    return (
        normalized_values_equal(left_memo, right_memo)
        or is_blank_text(left_memo)
        or is_blank_text(right_memo)
    )


def preferred_adjacent_duplicate_keep(left: pd.Series, right: pd.Series) -> str:
    left_memo_blank = is_blank_text(left.get("raw_memo", ""))
    right_memo_blank = is_blank_text(right.get("raw_memo", ""))
    if left_memo_blank and not right_memo_blank:
        return "right"
    return "left"


def broker_adjacent_duplicate_skip_record(row: pd.Series) -> dict[str, Any]:
    fx_rate = row.get("fx_rate", "")
    return {
        "source_file": row.get("source_file", ""),
        "source_file_type": row.get("source_file_type", ""),
        "account_type": row.get("account_type", ""),
        "skip_reason": BROKER_ADJACENT_DUPLICATE_CASHFLOW_SKIP_REASON,
        "currency": currency_code_from_text(row.get("currency", "")),
        "fx_rate": "" if pd.isna(fx_rate) else fx_rate,
        "amount_kind": "adjacent_principal_cashflow_duplicate",
        "row_count": 1,
    }


def group_skipped_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=SKIPPED_ROWS_COLUMNS)
    skipped = pd.DataFrame(records, columns=SKIPPED_ROWS_COLUMNS)
    group_cols = [col for col in SKIPPED_ROWS_COLUMNS if col != "row_count"]
    skipped = skipped.groupby(group_cols, dropna=False, as_index=False)["row_count"].sum()
    return skipped[SKIPPED_ROWS_COLUMNS]


def combine_skipped_rows(*frames: pd.DataFrame) -> pd.DataFrame:
    non_empty = [frame for frame in frames if frame is not None and not frame.empty]
    if not non_empty:
        return pd.DataFrame(columns=SKIPPED_ROWS_COLUMNS)
    combined = pd.concat(non_empty, ignore_index=True)
    group_cols = [col for col in SKIPPED_ROWS_COLUMNS if col != "row_count"]
    return combined.groupby(group_cols, dropna=False, as_index=False)["row_count"].sum()[SKIPPED_ROWS_COLUMNS]


def remove_adjacent_duplicate_principal_cashflows(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty or not set(INTERNAL_NORMALIZED_COLUMNS).issubset(set(df.columns)):
        return df, pd.DataFrame(columns=SKIPPED_ROWS_COLUMNS)

    drop_indices: set[int] = set()
    skipped_records: list[dict[str, Any]] = []
    group_cols = ["source_file", "_source_sheet"]
    for _, group in df.groupby(group_cols, dropna=False, sort=False):
        sorted_group = (
            group.assign(_raw_row_sort=group["_raw_row_number"].map(raw_row_start_order_value))
            .sort_values("_raw_row_sort", kind="stable")
            .drop(columns=["_raw_row_sort"])
        )
        kept_indices: list[int] = []
        for idx, row in sorted_group.iterrows():
            if kept_indices:
                previous_idx = kept_indices[-1]
                previous = df.loc[previous_idx]
                if adjacent_principal_cashflow_duplicate(previous, row):
                    if preferred_adjacent_duplicate_keep(previous, row) == "right":
                        drop_indices.add(previous_idx)
                        skipped_records.append(broker_adjacent_duplicate_skip_record(previous))
                        kept_indices[-1] = idx
                    else:
                        drop_indices.add(idx)
                        skipped_records.append(broker_adjacent_duplicate_skip_record(row))
                    continue
            kept_indices.append(idx)

    if not drop_indices:
        return df, pd.DataFrame(columns=SKIPPED_ROWS_COLUMNS)
    return df.drop(index=sorted(drop_indices)).copy(), group_skipped_records(skipped_records)


def raw_memo_values_compatible_for_cashflow_dedupe(values: pd.Series) -> bool:
    meaningful = {
        str(value).strip()
        for value in values
        if not is_blank_text(value)
    }
    return len(meaningful) <= 1


def has_remaining_rows_between(context_rows: pd.DataFrame, left: pd.Series, right: pd.Series) -> bool:
    if context_rows.empty or not set(INTERNAL_NORMALIZED_COLUMNS).issubset(set(context_rows.columns)):
        return True
    if not normalized_values_equal(left.get("source_file", ""), right.get("source_file", "")):
        return True
    if not normalized_values_equal(left.get("_source_sheet", ""), right.get("_source_sheet", "")):
        return True
    left_row = raw_row_end_order_value(left.get("_raw_row_number", ""))
    right_row = raw_row_start_order_value(right.get("_raw_row_number", ""))
    lower = min(left_row, right_row)
    upper = max(left_row, right_row)
    if upper - lower <= 1:
        return False
    middle = context_rows[
        context_rows["source_file"].fillna("").astype(str).eq(str(left.get("source_file", "")))
        & context_rows["_source_sheet"].fillna("").astype(str).eq(str(left.get("_source_sheet", "")))
        & (context_rows["_raw_row_number"].map(raw_row_start_order_value) > lower)
        & (context_rows["_raw_row_number"].map(raw_row_start_order_value) < upper)
    ]
    return not middle.empty


def dedupe_principal_cashflow_view(cashflows: pd.DataFrame, context_rows: pd.DataFrame | None = None) -> pd.DataFrame:
    if cashflows.empty:
        return cashflows.copy()
    context = context_rows if context_rows is not None else cashflows
    key_cols = ["account_type", "trade_date", "transaction_type", "settlement_amount", "currency"]
    drop_indices: set[int] = set()
    for _, group in cashflows.groupby(key_cols, dropna=False, sort=False):
        if len(group) <= 1:
            continue
        if not raw_memo_values_compatible_for_cashflow_dedupe(group.get("raw_memo", pd.Series(dtype=str))):
            continue
        sorted_group = (
            group.assign(_raw_row_sort=group["_raw_row_number"].map(raw_row_start_order_value))
            .sort_values(["source_file", "_source_sheet", "_raw_row_sort"], kind="stable")
            .drop(columns=["_raw_row_sort"])
        )
        kept = sorted_group.iloc[0]
        for idx, candidate in sorted_group.iloc[1:].iterrows():
            same_source = normalized_values_equal(kept.get("source_file", ""), candidate.get("source_file", ""))
            if not same_source:
                drop_indices.add(idx)
                continue
            if not has_remaining_rows_between(context, kept, candidate):
                drop_indices.add(idx)
    if not drop_indices:
        return cashflows.copy()
    return cashflows.drop(index=sorted(drop_indices)).copy()


def strip_internal_normalized_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=INTERNAL_NORMALIZED_COLUMNS, errors="ignore")


def split_skipped_broker_helper_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return df, pd.DataFrame(columns=SKIPPED_ROWS_COLUMNS)
    skip_mask = df.apply(is_overseas_cashflow_amount_only_helper_row, axis=1)
    if not bool(skip_mask.any()):
        return df, pd.DataFrame(columns=SKIPPED_ROWS_COLUMNS)

    skipped_records = []
    for _, row in df[skip_mask].iterrows():
        fx_rate = row.get("fx_rate", "")
        skipped_records.append({
            "source_file": row.get("source_file", ""),
            "source_file_type": row.get("source_file_type", ""),
            "account_type": row.get("account_type", ""),
            "skip_reason": OVERSEAS_CASHFLOW_AMOUNT_ONLY_SKIP_REASON,
            "currency": currency_code_from_text(row.get("currency", "")),
            "fx_rate": "" if pd.isna(fx_rate) else fx_rate,
            "amount_kind": "trade_amount_equals_settlement_amount",
            "row_count": 1,
        })

    return df[~skip_mask].copy(), group_skipped_records(skipped_records)


def is_leveraged_etf_name(name: Any, metadata: Any = "") -> bool:
    s = f"{name or ''} {metadata or ''}".lower()
    return any(k in s for k in LEVERAGED_ETF_KEYWORDS)


def safe_source_name(path: Path) -> str:
    digest = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:10]
    return f"source_{digest}{path.suffix.lower()}"


def redact_sensitive(text: Any) -> str:
    s = str(text or "")
    for pattern in SENSITIVE_PATTERNS:
        s = pattern.sub("[REDACTED]", s)
    return s


def detect_sensitive(text: Any) -> bool:
    s = str(text or "")
    return any(p.search(s) for p in SENSITIVE_PATTERNS)


def detect_html_encoding(raw: bytes) -> str:
    head = raw[:3000].decode("ascii", errors="ignore")
    m = re.search(r"charset\s*=\s*([A-Za-z0-9_\-]+)", head, re.I)
    if not m:
        return ""
    enc = m.group(1).lower()
    return {"euckr": "euc-kr", "ms949": "cp949"}.get(enc, enc)


def is_html_xls(raw: bytes) -> bool:
    head = raw[:500].decode("ascii", errors="ignore").lower()
    return "<html" in head or "<table" in head or "<!doctype" in head


def decode_html_bytes(raw: bytes) -> str:
    hinted = detect_html_encoding(raw)
    candidates = [hinted] if hinted else []
    candidates.extend(["utf-8", "cp949", "euc-kr"])
    best = ""
    best_score = -1
    for enc in dict.fromkeys([c for c in candidates if c]):
        try:
            decoded = raw.decode(enc, errors="ignore")
        except Exception:
            continue
        score = len(re.findall(r"[가-힣]", decoded))
        if score > best_score:
            best = decoded
            best_score = score
    return best or raw.decode("utf-8", errors="ignore")


def load_workbook_tables(path: Path) -> dict[str, pd.DataFrame]:
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return pd.read_excel(path, sheet_name=None, engine="openpyxl")
    if suffix == ".xls":
        raw = path.read_bytes()
        if is_html_xls(raw):
            html = decode_html_bytes(raw)
            try:
                tables = pd.read_html(StringIO(html), flavor="bs4")
            except Exception:
                tables = pd.read_html(StringIO(html))
            return {f"table_{i}": table for i, table in enumerate(tables)}
        return pd.read_excel(path, sheet_name=None, engine="xlrd")
    return {}


def find_column(columns: list[Any], canonical: str) -> Any | None:
    aliases = COLUMN_ALIASES.get(canonical, [])
    if not aliases:
        return None
    parts_by_column = {col: column_label_parts(col) or [str(col)] for col in columns}

    for alias in aliases:
        alias_norm = normalize_key(alias)
        for col, parts in parts_by_column.items():
            targets = parts[-1:] if len(parts) > 1 else parts
            if alias_norm and any(alias_norm == normalize_key(target) for target in targets):
                return col

    normalized = {col: normalize_key(col) for col in columns}
    for alias in aliases:
        alias_norm = normalize_key(alias)
        for col, col_norm in normalized.items():
            if len(parts_by_column[col]) == 1 and alias_norm and alias_norm == col_norm:
                return col

    for alias in sorted(aliases, key=lambda value: len(normalize_key(value)), reverse=True):
        alias_norm = normalize_key(alias)
        for col, parts in parts_by_column.items():
            if len(parts) > 1 and canonical in STRICT_MULTIINDEX_EXACT_CANONICALS:
                continue
            targets = parts[-1:] if len(parts) > 1 else [str(col)]
            if alias_norm and any(alias_norm in normalize_key(target) for target in targets):
                return col
    return None


def table_has_position_snapshot_columns(columns: list[Any]) -> bool:
    has_identity = find_column(columns, "ticker") is not None or find_column(columns, "security_name") is not None
    has_quantity = find_column(columns, "balance_quantity") is not None or find_column(columns, "quantity") is not None
    has_valuation = (
        find_column(columns, "evaluation_amount") is not None
        or find_column(columns, "price") is not None
        or find_column(columns, "pnl_pct") is not None
    )
    return has_identity and has_quantity and has_valuation


def position_snapshot_source_type(source_type: str, account_type: str, columns: list[Any]) -> str:
    normalized_source_type = str(source_type or "").strip().lower()
    if normalized_source_type in BALANCE_SOURCE_TYPES:
        return normalized_source_type
    if normalized_source_type in {"transaction_history", "transactions"}:
        return ""
    if not table_has_position_snapshot_columns(columns):
        return ""
    column_text = " ".join(str(col) for col in columns).lower()
    if str(account_type or "").strip().lower() == "overseas" or any(keyword in column_text for keyword in ["overseas", "외화", "해외", "시장명"]):
        return "overseas_balance"
    return "holdings"


def infer_account_type(file_name: str, sheet_name: str = "") -> str:
    s = f"{file_name} {sheet_name}".lower()
    if "isa" in s:
        return "ISA"
    if "해외" in s or "oversea" in s or "foreign" in s:
        return "overseas"
    if "종합" in s:
        return "comprehensive"
    return ""


def infer_market(ticker: str, name: str = "", file_type: str = "") -> str:
    t = str(ticker or "").strip().upper()
    if re.fullmatch(r"\d{6}", t):
        return "KR"
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{10}", t):
        return "KR" if t.startswith("KR") else "US"
    if re.fullmatch(r"[A-Z]{1,5}", t) and t not in VALID_CURRENCY_CODES:
        return "US"
    for symbol in [extract_symbol_from_parentheses(ticker), extract_symbol_from_parentheses(name)]:
        symbol_key = str(symbol or "").strip().upper()
        if re.fullmatch(r"[A-Z]{1,5}", symbol_key) and symbol_key not in VALID_CURRENCY_CODES:
            return "US"
    if t.startswith("US") or "overseas" in file_type:
        return "US"
    return ""


def is_cash_asset_name(name: str = "", ticker: str = "") -> bool:
    s = f"{name or ''} {ticker or ''}".lower()
    if any(keyword.lower() in s for keyword in CASH_ASSET_KEYWORDS):
        return True
    ticker_code = str(ticker or "").strip().upper()
    name_code = re.sub(r"[\s\-_]+", "", str(name or "").strip().upper())
    if ticker_code in VALID_CURRENCY_CODES and (not name_code or name_code in VALID_CURRENCY_CODES):
        return True
    return name_code in VALID_CURRENCY_CODES


def normalize_cash_currency(name: str = "", ticker: str = "", currency: Any = "") -> str:
    current = currency_code_from_text(currency)
    if not is_cash_asset_name(name, ticker):
        return current
    ticker_currency = currency_code_from_text(ticker)
    name_currency = currency_code_from_text(name)
    return ticker_currency or name_currency or current


def infer_asset_type(name: str, ticker: str = "") -> str:
    s = f"{name or ''} {ticker or ''}".lower()
    if is_cash_asset_name(name, ticker):
        return "cash"
    if "etf" in s or "etn" in s or is_leveraged_etf_name(s):
        return "etf"
    return "stock"


def _row_value(row: dict[str, Any] | pd.Series, key: str) -> Any:
    if isinstance(row, pd.Series):
        return row.get(key, "")
    return row.get(key, "")


def is_overseas_position_row(row: dict[str, Any] | pd.Series) -> bool:
    source_type = str(_row_value(row, "source_file_type") or "")
    market = str(_row_value(row, "market") or "").upper()
    ticker = str(_row_value(row, "ticker") or "").strip().upper()
    if source_type == "overseas_balance":
        return True
    if market and market != "KR":
        return True
    return bool(ticker) and not bool(re.fullmatch(r"\d{6}", ticker))


def canonical_overseas_position_key(row: dict[str, Any] | pd.Series) -> str:
    ticker = str(_row_value(row, "ticker") or "").strip()
    security_name = str(_row_value(row, "security_name") or "").strip()
    asset_type = str(_row_value(row, "asset_type") or "").strip().lower()
    currency = currency_code_from_text(_row_value(row, "currency"))

    if asset_type == "cash":
        cash_key = currency or normalize_security_name_for_key(ticker) or normalize_security_name_for_key(security_name)
        return f"CASH:{cash_key}" if cash_key else ""
    if not is_overseas_position_row(row):
        return ""

    symbol = extract_us_symbol(ticker) or extract_us_symbol(security_name)
    if symbol:
        return f"US:{symbol}"

    isin = extract_isin_like(ticker) or extract_isin_like(security_name)
    if isin:
        alias = KNOWN_OVERSEAS_ISIN_SYMBOL_ALIASES.get(isin)
        return f"US:{alias}" if alias else f"ISIN:{isin}"

    name_key = normalize_security_name_for_key(security_name or ticker)
    return f"NAME:{name_key}" if len(name_key) >= 2 else ""


def infer_source_file_type(path: Path, sheet_name: str, df: pd.DataFrame) -> str:
    text = " ".join([path.name, sheet_name] + [str(c) for c in df.columns])
    lower = text.lower()
    transaction_signals = [
        "종합거래내역", "거래내역 상세", "거래내역상세", "실거래일자", "거래유형",
        "상세내용", "거래시간", "정산금액", "체결",
    ]
    strong_transaction_file_signals = ["종합거래내역", "거래내역 상세", "거래내역상세"]
    strong_transaction_column_signals = ["실거래일자", "거래유형", "상세내용"]
    cashflow_signals = [
        "입출금내역", "입출금", "예수금", "출금가능금액", "입금액", "입금금액", "출금액", "출금금액",
        "cashflow", "cash flow", "cash_flow",
    ]
    overseas_balance_signals = ["해외증권잔고조회", "해외증권잔고", "외화평가금액", "해외잔고"]
    holdings_signals = [
        "종합잔고", "잔고조회", "계좌잔고", "보유잔고", "보유현황",
        "평가금액", "평가손익", "평가손익률", "평균단가", "현재가",
    ]
    if any(k.lower() in lower for k in strong_transaction_file_signals) or all(k.lower() in lower for k in strong_transaction_column_signals):
        return "transaction_history"
    if any(k.lower() in lower for k in cashflow_signals):
        return "cashflow"
    if any(k.lower() in lower for k in transaction_signals):
        return "transaction_history"
    if any(k.lower() in lower for k in overseas_balance_signals):
        return "overseas_balance"
    if any(k.lower() in lower for k in holdings_signals):
        return "holdings"
    if any(k in text for k in ["해외증권잔고", "외화평가금액", "해외잔고"]):
        return "overseas_balance"
    if any(k in text for k in ["종합잔고", "평가금액", "평가손익률", "잔고금액"]):
        return "holdings"
    if any(k in text for k in ["입출금", "예수금", "출금가능"]):
        return "cashflow"
    if any(k in text for k in ["거래내역", "실거래일자", "거래유형", "체결"]):
        return "transactions"
    return "unknown"


def extract_code_and_name(value: Any) -> tuple[str, str]:
    s = re.sub(r"\s+", " ", str(value or "")).strip()
    if not s or s.lower() == "nan":
        return "", ""
    m = re.search(r"\b([A-Z]{2}[A-Z0-9]{10})\b", s)
    if m:
        code = m.group(1)
        return code, re.sub(re.escape(code), "", s).strip(" -")
    m = re.search(r"\b(\d{1,6})\b", s)
    if m:
        code = m.group(1).zfill(6)
        return code, re.sub(re.escape(m.group(1)), "", s).strip(" -")
    return "", s


def normalize_dataframe(df: pd.DataFrame, source_path: Path, sheet_name: str) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    if df is None or df.empty:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS), pd.DataFrame(), []
    flat = df.copy()
    if isinstance(flat.columns, pd.MultiIndex):
        flat.columns = [flatten_column_name(col) for col in flat.columns]
    else:
        flat.columns = [flatten_column_name(c) for c in flat.columns]
    columns = list(flat.columns)
    source_type = infer_source_file_type(source_path, sheet_name, flat)
    if source_type in {"transaction_history", "transactions"}:
        flat = collapse_namoo_transaction_pair_rows(flat, source_path.name, sheet_name)
        columns = list(flat.columns)
    account_type = infer_account_type(source_path.name, sheet_name)
    snapshot_source_type = position_snapshot_source_type(source_type, account_type, columns)
    source_file = safe_source_name(source_path)
    unknown_columns = [
        str(c)
        for c in columns
        if c != COLLAPSED_RAW_ROW_NUMBER_COLUMN and not any(find_column(columns, key) == c for key in COLUMN_ALIASES)
    ]

    cols = {key: find_column(columns, key) for key in COLUMN_ALIASES}
    rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    for idx, raw in flat.iterrows():
        row_source_type = snapshot_source_type or source_type
        raw_row_number = raw.get(COLLAPSED_RAW_ROW_NUMBER_COLUMN, "")
        if is_blank_text(raw_row_number):
            raw_row_number = int(idx) + 1
        raw_json = json.dumps({str(k): redact_sensitive(v) for k, v in raw.to_dict().items()}, ensure_ascii=False, default=str)
        date = normalize_date(raw.get(cols["trade_date"])) if cols.get("trade_date") is not None else ""
        name = str(raw.get(cols["security_name"]) if cols.get("security_name") is not None else "").strip()
        ticker = str(raw.get(cols["ticker"]) if cols.get("ticker") is not None else "").strip()
        if (not ticker or ticker.lower() == "nan") and name:
            ticker, parsed_name = extract_code_and_name(name)
            name = parsed_name or name
        if re.fullmatch(r"\d{1,6}", ticker):
            ticker = ticker.zfill(6)
        raw_type = str(raw.get(cols["transaction_raw"]) if cols.get("transaction_raw") is not None else "").strip()
        memo = str(raw.get(cols["memo"]) if cols.get("memo") is not None else raw_type).strip()
        tx_type = classify_transaction_type(" ".join([raw_type, memo, name]))
        quantity = parse_korean_number(raw.get(cols["quantity"])) if cols.get("quantity") is not None else 0.0
        is_balance_source = row_source_type in BALANCE_SOURCE_TYPES
        balance_quantity_value = parse_korean_number(raw.get(cols["balance_quantity"])) if cols.get("balance_quantity") is not None else (quantity if is_balance_source else 0.0)
        deposit_amount = parse_korean_number(raw.get(cols["deposit_amount"])) if cols.get("deposit_amount") is not None else 0.0
        withdrawal_amount = parse_korean_number(raw.get(cols["withdrawal_amount"])) if cols.get("withdrawal_amount") is not None else 0.0
        if tx_type == "unknown":
            if deposit_amount and not withdrawal_amount:
                tx_type = "deposit"
            elif withdrawal_amount and not deposit_amount:
                tx_type = "withdrawal"
        trade_amount = parse_korean_number(raw.get(cols["trade_amount"])) if cols.get("trade_amount") is not None else 0.0
        if not trade_amount:
            trade_amount = deposit_amount or withdrawal_amount
        settlement_amount = parse_korean_number(raw.get(cols["settlement_amount"])) if cols.get("settlement_amount") is not None else trade_amount
        price = parse_korean_number(raw.get(cols["price"])) if cols.get("price") is not None else 0.0
        fee = parse_korean_number(raw.get(cols["fee"])) if cols.get("fee") is not None else 0.0
        tax = parse_korean_number(raw.get(cols["tax"])) if cols.get("tax") is not None else 0.0
        evaluation_amount_value = parse_korean_number(raw.get(cols["evaluation_amount"])) if cols.get("evaluation_amount") is not None else 0.0
        unrealized_pnl_value = parse_korean_number(raw.get(cols["unrealized_pnl"])) if cols.get("unrealized_pnl") is not None else 0.0
        pnl_pct_value = parse_korean_percent(raw.get(cols["pnl_pct"])) if cols.get("pnl_pct") is not None else pd.NA
        balance_quantity = balance_quantity_value if is_balance_source else pd.NA
        evaluation_amount = evaluation_amount_value if is_balance_source else pd.NA
        unrealized_pnl = unrealized_pnl_value if is_balance_source else pd.NA
        pnl_pct = pnl_pct_value if is_balance_source else pd.NA
        raw_currency = raw.get(cols["currency"]) if cols.get("currency") is not None else ""
        raw_fx_rate = raw.get(cols["exchange_rate"]) if cols.get("exchange_rate") is not None else ""
        market = infer_market(ticker, name, row_source_type)
        currency, fx_rate = normalize_currency_and_fx_rate(raw_currency, raw_fx_rate, row_source_type, market)
        asset_type = infer_asset_type(name, ticker)
        if asset_type == "cash":
            currency = normalize_cash_currency(name, ticker, currency)
        fx_rate_for_stable = "" if pd.isna(fx_rate) else fx_rate
        currency_native = currency
        fx_rate_to_krw = fx_rate
        quantity_unit = "shares" if abs(quantity) > 1e-9 and asset_type != "cash" else ""
        price_kind = "unit_price" if abs(price) > 1e-9 else ""
        price_unit = f"{currency_native}/share" if price_kind and quantity_unit == "shares" else (currency_native if price_kind else "")
        amount_kind = amount_kind_for(
            tx_type,
            row_source_type,
            asset_type,
            trade_amount,
            settlement_amount,
            fee,
            tax,
            evaluation_amount_value,
            unrealized_pnl_value,
            quantity,
            price,
        )
        amount_native_value = primary_amount_for_kind(
            amount_kind,
            trade_amount,
            settlement_amount,
            fee,
            tax,
            evaluation_amount_value,
            unrealized_pnl_value,
            quantity,
            price,
        )
        amount_native, amount_krw, amount_krw_source = convert_native_to_krw(amount_native_value, currency_native, fx_rate_to_krw)
        amount_is_money = is_money_amount_kind(amount_kind)
        amount_review_status, amount_review_reason = (
            money_status(currency_native, fx_rate_to_krw, amount_native_value)
            if amount_is_money
            else ("not_applicable", "")
        )
        if not amount_is_money:
            amount_basis = "not_money" if amount_kind in {"quantity", "unit_price"} else "unknown"
            amount_confidence = "official_raw" if amount_kind in {"quantity", "unit_price"} else "unavailable"
        elif amount_review_status == "ok" and str(currency_native).upper() == "KRW":
            amount_basis = "raw_native"
            amount_confidence = "official_raw"
        elif amount_review_status == "ok":
            amount_basis = "derived_krw_from_fx"
            amount_confidence = "derived"
            amount_krw_source = "fx_rate_to_krw"
        else:
            amount_basis = "raw_native"
            amount_confidence = "unavailable"
        fx_rate_status = (
            "available"
            if normalized_fx_rate_value(fx_rate_to_krw) is not None
            else ("not_required" if currency_native == "KRW" else "missing")
        )
        fx_rate_source = "raw" if fx_rate_status == "available" else ""
        cashflow_role = cashflow_role_for(tx_type, row_source_type, asset_type)
        affects_principal = cashflow_role in {"external_deposit", "external_withdrawal"} and amount_review_status == "ok"
        affects_profit = cashflow_role in {"income_dividend", "income_interest"} or amount_kind == "unrealized_pnl"
        is_internal_transfer = cashflow_role in {"internal_fx_exchange", "internal_transfer"}
        is_valuation_snapshot = cashflow_role == "valuation_snapshot"
        is_trade_settlement = cashflow_role == "trade_settlement"
        trade_amount_native, trade_amount_krw, _ = convert_native_to_krw(trade_amount, currency_native, fx_rate_to_krw)
        settlement_amount_native, settlement_amount_krw, _ = convert_native_to_krw(settlement_amount, currency_native, fx_rate_to_krw)
        fee_native, fee_krw, _ = convert_native_to_krw(fee, currency_native, fx_rate_to_krw)
        tax_native, tax_krw, _ = convert_native_to_krw(tax, currency_native, fx_rate_to_krw)
        evaluation_amount_native, evaluation_amount_krw, _ = convert_native_to_krw(evaluation_amount_value, currency_native, fx_rate_to_krw)
        unrealized_pnl_native, unrealized_pnl_krw, _ = convert_native_to_krw(unrealized_pnl_value, currency_native, fx_rate_to_krw)
        amount_fields = normalize_amount_fields({
            "source_file_type": row_source_type,
            "account_type": account_type,
            "market": market,
            "asset_type": asset_type,
            "transaction_type": tx_type,
            "quantity": quantity,
            "price": price,
            "trade_amount": trade_amount,
            "settlement_amount": settlement_amount,
            "fee": fee,
            "tax": tax,
            "currency": currency,
            "fx_rate": fx_rate,
            "evaluation_amount": evaluation_amount_value if is_balance_source else pd.NA,
            "unrealized_pnl": unrealized_pnl_value if is_balance_source else pd.NA,
        })
        quantity_unit = amount_fields["quantity_unit"]
        price_unit = amount_fields["price_unit"]
        price_kind = amount_fields["price_kind"]
        amount_kind = amount_fields["amount_kind"]
        amount_basis = amount_fields["amount_basis"]
        amount_confidence = amount_fields["amount_confidence"]
        amount_review_status = amount_fields["amount_review_status"]
        amount_review_reason = amount_fields["amount_review_reason"]
        currency_native = amount_fields["currency_native"]
        fx_rate_to_krw = amount_fields["fx_rate_to_krw"]
        fx_rate_source = amount_fields["fx_rate_source"]
        fx_rate_status = amount_fields["fx_rate_status"]
        amount_native = amount_fields["amount_native"]
        amount_krw = amount_fields["amount_krw"]
        amount_krw_source = amount_fields["amount_krw_source"]
        trade_amount_native = amount_fields["trade_amount_native"]
        trade_amount_krw = amount_fields["trade_amount_krw"]
        settlement_amount_native = amount_fields["settlement_amount_native"]
        settlement_amount_krw = amount_fields["settlement_amount_krw"]
        fee_native = amount_fields["fee_native"]
        fee_krw = amount_fields["fee_krw"]
        tax_native = amount_fields["tax_native"]
        tax_krw = amount_fields["tax_krw"]
        evaluation_amount_native = amount_fields["evaluation_amount_native"]
        evaluation_amount_krw = amount_fields["evaluation_amount_krw"]
        unrealized_pnl_native = amount_fields["unrealized_pnl_native"]
        unrealized_pnl_krw = amount_fields["unrealized_pnl_krw"]
        cashflow_role = amount_fields["cashflow_role"]
        affects_principal = amount_fields["affects_principal"]
        affects_profit = amount_fields["affects_profit"]
        is_internal_transfer = amount_fields["is_internal_transfer"]
        is_valuation_snapshot = amount_fields["is_valuation_snapshot"]
        is_trade_settlement = amount_fields["is_trade_settlement"]
        fx_pair_status = amount_fields["fx_pair_status"]

        if not any([date, ticker, name, raw_type, trade_amount, settlement_amount, evaluation_amount_value, balance_quantity_value]):
            continue

        stable = {
            "source_file_type": row_source_type, "account_type": account_type, "ticker": ticker,
            "security_name": name, "trade_date": date, "trade_time": normalize_time(raw.get(cols["trade_time"])) if cols.get("trade_time") is not None else "",
            "transaction_type": tx_type, "quantity": quantity, "price": price,
            "trade_amount": trade_amount, "settlement_amount": settlement_amount,
            "fee": fee, "tax": tax,
            "currency": currency, "fx_rate": fx_rate_for_stable, "raw_memo": memo,
            "cashflow_role": cashflow_role, "amount_review_status": amount_review_status,
            "affects_principal": affects_principal,
        }
        if principal_cashflow_import_key_needs_raw_position(stable):
            stable["source_sheet"] = sheet_name
            stable["raw_row_number"] = raw_row_number
        import_id = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        fx_event_id = f"FX-{import_id[:12]}" if cashflow_role == "internal_fx_exchange" else ""
        row = {
            "import_id": import_id,
            "source_file": source_file,
            "source_file_type": row_source_type,
            "account_type": account_type,
            "market": market,
            "asset_type": asset_type,
            "ticker": ticker,
            "security_name": redact_sensitive(name),
            "trade_date": date,
            "trade_time": stable["trade_time"],
            "transaction_type": tx_type,
            "quantity": quantity,
            "price": price,
            "trade_amount": trade_amount,
            "settlement_amount": settlement_amount,
            "fee": fee,
            "tax": tax,
            "currency": currency,
            "fx_rate": fx_rate,
            "balance_quantity": balance_quantity,
            "evaluation_amount": evaluation_amount,
            "unrealized_pnl": unrealized_pnl,
            "pnl_pct": pnl_pct,
            "raw_memo": redact_sensitive(memo),
            "quantity_unit": quantity_unit,
            "price_unit": price_unit,
            "price_kind": price_kind,
            "money_unit_native": currency_native if amount_is_money else "",
            "money_unit_krw": "KRW" if amount_is_money else "",
            "amount_kind": amount_kind,
            "amount_basis": amount_basis,
            "amount_sign_convention": "raw_positive_transaction_type_sign",
            "amount_confidence": amount_confidence,
            "amount_review_status": amount_review_status,
            "amount_review_reason": amount_review_reason,
            "currency_native": currency_native,
            "fx_rate_to_krw": fx_rate_to_krw,
            "fx_rate_source": fx_rate_source,
            "fx_rate_status": fx_rate_status,
            "amount_native": amount_native if amount_is_money else pd.NA,
            "amount_krw": amount_krw if amount_is_money else pd.NA,
            "amount_krw_source": amount_krw_source,
            "amount_normalization_status": amount_review_status,
            "amount_normalization_reason": amount_review_reason,
            "trade_amount_native": trade_amount_native,
            "trade_amount_krw": trade_amount_krw,
            "settlement_amount_native": settlement_amount_native,
            "settlement_amount_krw": settlement_amount_krw,
            "fee_native": fee_native,
            "fee_krw": fee_krw,
            "tax_native": tax_native,
            "tax_krw": tax_krw,
            "evaluation_amount_native": evaluation_amount_native if is_balance_source else pd.NA,
            "evaluation_amount_krw": evaluation_amount_krw if is_balance_source else pd.NA,
            "unrealized_pnl_native": unrealized_pnl_native if is_balance_source else pd.NA,
            "unrealized_pnl_krw": unrealized_pnl_krw if is_balance_source else pd.NA,
            "cashflow_role": cashflow_role,
            "affects_principal": affects_principal,
            "affects_profit": affects_profit,
            "is_internal_transfer": is_internal_transfer,
            "is_valuation_snapshot": is_valuation_snapshot,
            "is_trade_settlement": is_trade_settlement,
            "fx_event_id": fx_event_id,
            "fx_pair_status": fx_pair_status,
            "_source_sheet": sheet_name,
            "_raw_row_number": raw_row_number,
        }
        rows.append(row)
        audit_rows.append({"import_id": import_id, "source_file": source_file, "sheet": sheet_name, "row_number": raw_row_number, "raw_json": raw_json})

    return pd.DataFrame(rows, columns=NORMALIZED_COLUMNS + INTERNAL_NORMALIZED_COLUMNS), pd.DataFrame(audit_rows), unknown_columns


def empty_outputs(processed_dir: Path) -> dict[str, pd.DataFrame]:
    return {
        "processed_transactions.csv": pd.DataFrame(columns=NORMALIZED_COLUMNS),
        "processed_holdings.csv": pd.DataFrame(columns=NORMALIZED_COLUMNS + HOLDING_DEDUPE_COLUMNS),
        "processed_cashflows.csv": pd.DataFrame(columns=NORMALIZED_COLUMNS),
        "processed_dividends.csv": pd.DataFrame(columns=NORMALIZED_COLUMNS),
        "portfolio_summary.csv": pd.DataFrame(columns=["metric", "value"]),
        "risk_watchlist.csv": pd.DataFrame(columns=["ticker", "security_name", "account_type", "risk_flags", "pnl_pct", "weight_pct", "suggested_action"]),
        "review_queue.csv": pd.DataFrame(columns=["ticker", "security_name", "reason", "severity", "suggested_action"]),
        "history_queue.csv": pd.DataFrame(columns=HISTORY_COLUMNS),
        "post_mortem_candidates.csv": pd.DataFrame(columns=HISTORY_COLUMNS),
        "qa_exceptions.csv": pd.DataFrame(columns=["exception_id", "severity", "file", "issue", "suggested_fix"]),
        "source_file_index.csv": pd.DataFrame(columns=["source_file", "source_file_type", "account_type", "raw_path_hash", "size_bytes", "modified_at", "imported_at", "sensitive_data_found"]),
        "unclassified_rows.csv": pd.DataFrame(columns=NORMALIZED_COLUMNS),
        "skipped_rows.csv": pd.DataFrame(columns=SKIPPED_ROWS_COLUMNS),
        "raw_rows_audit.csv": pd.DataFrame(columns=["import_id", "source_file", "sheet", "row_number", "raw_json"]),
        "amount_unit_audit.csv": pd.DataFrame(columns=AMOUNT_UNIT_AUDIT_COLUMNS),
        "unit_mismatch_audit.csv": pd.DataFrame(columns=UNIT_MISMATCH_AUDIT_COLUMNS),
    }


def amount_unit_audit_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=AMOUNT_UNIT_AUDIT_COLUMNS)
    view = rows.copy()
    rename_map = {
        "quantity": "raw_quantity",
        "price": "raw_price",
        "trade_amount": "raw_trade_amount",
        "settlement_amount": "raw_settlement_amount",
        "fee": "raw_fee",
        "tax": "raw_tax",
    }
    view = view.rename(columns=rename_map)
    return view.reindex(columns=AMOUNT_UNIT_AUDIT_COLUMNS)


def unit_mismatch_audit_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=UNIT_MISMATCH_AUDIT_COLUMNS)
    status = rows.get("amount_normalization_status", pd.Series("", index=rows.index)).fillna("").astype(str).str.lower()
    currency = rows.get("currency_native", pd.Series("", index=rows.index)).fillna("").astype(str).str.upper()
    role = rows.get("cashflow_role", pd.Series("", index=rows.index)).fillna("").astype(str).str.lower()
    amount_native = pd.to_numeric(rows.get("amount_native", pd.Series(0, index=rows.index)), errors="coerce").fillna(0)
    amount_krw = pd.to_numeric(rows.get("amount_krw", pd.Series(0, index=rows.index)), errors="coerce").fillna(0)
    mask = (
        status.isin({"fx_missing", "currency_ambiguous", "unit_ambiguous", "needs_review"})
        | role.isin({"internal_fx_exchange", "income_dividend", "income_interest"})
        | ((currency != "KRW") & (amount_native.round(6) != amount_krw.round(6)))
    )
    return rows.loc[mask].reindex(columns=UNIT_MISMATCH_AUDIT_COLUMNS)


def normalize_amount_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.reindex(columns=list(dict.fromkeys(list(df.columns) + NORMALIZED_COLUMNS)))
    normalized_rows = []
    for _, row in df.iterrows():
        item = row.to_dict()
        item.update(normalize_amount_fields(item))
        if item.get("cashflow_role") == "internal_fx_exchange":
            import_id = str(item.get("import_id", "") or "")
            item["fx_event_id"] = item.get("fx_event_id") or (f"FX-{import_id[:12]}" if import_id else "")
            item["fx_pair_status"] = item.get("fx_pair_status") or "unpaired"
        else:
            item["fx_event_id"] = ""
            item["fx_pair_status"] = ""
        normalized_rows.append(item)
    columns = list(dict.fromkeys(list(df.columns) + NORMALIZED_COLUMNS))
    return pd.DataFrame(normalized_rows).reindex(columns=columns)


def normalize_holding_identity(row: dict[str, Any] | pd.Series) -> dict[str, str]:
    """Return normalized fields used to compare holding rows."""
    source_type = str(_row_value(row, "source_file_type") or "").strip().lower()
    account_type = str(_row_value(row, "account_type") or "").strip().lower()
    asset_type = str(_row_value(row, "asset_type") or "").strip().lower()
    position_key = canonical_overseas_position_key(row)
    market = str(_row_value(row, "market") or "").strip().upper()
    if not market and position_key.startswith(("US:", "ISIN:")):
        market = "US"
    currency = currency_code_from_text(_row_value(row, "currency"))
    return {
        "source_type": source_type,
        "account_type": account_type,
        "asset_type": asset_type,
        "position_key": position_key,
        "market": market,
        "currency": currency,
    }


def build_holding_dedupe_key(row: dict[str, Any] | pd.Series) -> str:
    """Build a broad grouping key for possible duplicate overseas holdings."""
    identity = normalize_holding_identity(row)
    if identity["asset_type"] == "cash":
        return ""
    if not identity["position_key"] or not is_overseas_position_row(row):
        return ""
    return "|".join(["overseas", identity["position_key"], identity["market"]])


def rank_holding_source(row: dict[str, Any] | pd.Series) -> int:
    """Rank holding sources; lower values are more authoritative."""
    source_type = normalize_holding_identity(row)["source_type"]
    return HOLDING_SOURCE_PRIORITY.get(source_type, 100)


def _dedupe_number(value: Any) -> float | None:
    parsed = parse_optional_korean_number(value)
    if parsed is None:
        return None
    try:
        if pd.isna(parsed):
            return None
    except Exception:
        pass
    return float(parsed)


def _numbers_close(left: Any, right: Any, abs_tol: float, rel_tol: float) -> bool:
    left_num = _dedupe_number(left)
    right_num = _dedupe_number(right)
    if left_num is None or right_num is None:
        return False
    diff = abs(left_num - right_num)
    if diff <= abs_tol:
        return True
    scale = max(abs(left_num), abs(right_num), 1.0)
    return diff <= scale * rel_tol


def _numbers_missing_or_close(left: Any, right: Any, abs_tol: float, rel_tol: float) -> bool:
    left_num = _dedupe_number(left)
    right_num = _dedupe_number(right)
    if left_num is None or right_num is None:
        return True
    return _numbers_close(left_num, right_num, abs_tol, rel_tol)


def _number_missing_or_zero(value: Any) -> bool:
    parsed = _dedupe_number(value)
    return parsed is None or abs(parsed) <= HOLDING_QUANTITY_TOLERANCE


def _meaningful_amounts_close(left: Any, right: Any) -> bool:
    left_num = _dedupe_number(left)
    right_num = _dedupe_number(right)
    if left_num is None or right_num is None:
        return False
    if max(abs(left_num), abs(right_num)) <= HOLDING_AMOUNT_ABS_TOLERANCE:
        return False
    return _numbers_close(left_num, right_num, HOLDING_AMOUNT_ABS_TOLERANCE, HOLDING_AMOUNT_REL_TOLERANCE)


def _accounts_compatible(left: str, right: str) -> bool:
    if left == right:
        return True
    return left in GENERIC_ACCOUNT_TYPES or right in GENERIC_ACCOUNT_TYPES


def _holding_name_key(row: dict[str, Any] | pd.Series) -> str:
    return normalize_security_name_for_key(
        _row_value(row, "security_name") or _row_value(row, "ticker")
    )


def _identity_compatible(left: dict[str, str], right: dict[str, str]) -> bool:
    if left["asset_type"] == "cash" or right["asset_type"] == "cash":
        return False
    if left["position_key"] != right["position_key"]:
        return False
    if left["market"] and right["market"] and left["market"] != right["market"]:
        return False
    if (
        left["currency"]
        and right["currency"]
        and left["currency"] != right["currency"]
        and {left["source_type"], right["source_type"]} != {"holdings", "overseas_balance"}
    ):
        return False
    return _accounts_compatible(left["account_type"], right["account_type"])


def _fallback_identity_compatible(
    left: dict[str, Any] | pd.Series,
    right: dict[str, Any] | pd.Series,
    left_id: dict[str, str],
    right_id: dict[str, str],
) -> bool:
    """Allow broker ISIN/display-name pairs to compare when strict keys differ."""
    if left_id["asset_type"] == "cash" or right_id["asset_type"] == "cash":
        return False
    if {left_id["source_type"], right_id["source_type"]} != {"holdings", "overseas_balance"}:
        return False
    if not (is_overseas_position_row(left) and is_overseas_position_row(right)):
        return False
    if left_id["market"] and right_id["market"] and left_id["market"] != right_id["market"]:
        return False
    if not _accounts_compatible(left_id["account_type"], right_id["account_type"]):
        return False

    left_name = _holding_name_key(left)
    right_name = _holding_name_key(right)
    return bool(left_name and left_name == right_name and len(left_name) >= 2)


def _holding_amounts_match(left: dict[str, Any] | pd.Series, right: dict[str, Any] | pd.Series) -> bool:
    quantity_close = _numbers_close(
        _row_value(left, "balance_quantity"),
        _row_value(right, "balance_quantity"),
        HOLDING_QUANTITY_TOLERANCE,
        HOLDING_QUANTITY_TOLERANCE,
    )
    evaluation_close = _numbers_missing_or_close(
        _row_value(left, "evaluation_amount"),
        _row_value(right, "evaluation_amount"),
        HOLDING_AMOUNT_ABS_TOLERANCE,
        HOLDING_AMOUNT_REL_TOLERANCE,
    )
    if quantity_close and evaluation_close:
        return True
    if (
        (_number_missing_or_zero(_row_value(left, "balance_quantity")) or _number_missing_or_zero(_row_value(right, "balance_quantity")))
        and _numbers_close(
            _row_value(left, "evaluation_amount"),
            _row_value(right, "evaluation_amount"),
            HOLDING_AMOUNT_ABS_TOLERANCE,
            HOLDING_AMOUNT_REL_TOLERANCE,
        )
        and _numbers_missing_or_close(
            _row_value(left, "unrealized_pnl"),
            _row_value(right, "unrealized_pnl"),
            HOLDING_AMOUNT_ABS_TOLERANCE,
            HOLDING_AMOUNT_REL_TOLERANCE,
        )
        and _numbers_missing_or_close(
            _row_value(left, "pnl_pct"),
            _row_value(right, "pnl_pct"),
            0.01,
            HOLDING_AMOUNT_REL_TOLERANCE,
        )
    ):
        return True

    strict_evaluation_close = _numbers_close(
        _row_value(left, "evaluation_amount"),
        _row_value(right, "evaluation_amount"),
        HOLDING_AMOUNT_ABS_TOLERANCE,
        HOLDING_AMOUNT_REL_TOLERANCE,
    )
    cost_close = any(
        _meaningful_amounts_close(_row_value(left, field), _row_value(right, field))
        for field in ["trade_amount", "settlement_amount"]
    )
    return strict_evaluation_close and cost_close


def _same_economic_holding(left: dict[str, Any] | pd.Series, right: dict[str, Any] | pd.Series) -> bool:
    left_id = normalize_holding_identity(left)
    right_id = normalize_holding_identity(right)
    identity_matches = _identity_compatible(left_id, right_id) or _fallback_identity_compatible(left, right, left_id, right_id)
    return identity_matches and _holding_amounts_match(left, right)


def dedupe_holdings(df: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicate overseas holdings while retaining source audit columns."""
    if df.empty or "ticker" not in df.columns:
        empty = df.copy()
        for col in HOLDING_DEDUPE_COLUMNS:
            if col not in empty.columns:
                empty[col] = pd.Series(dtype="object")
        return empty

    original = df.copy().reset_index(drop=True)
    existing_counts = pd.to_numeric(
        original.get("dedupe_excluded_count", pd.Series(0, index=original.index)),
        errors="coerce",
    ).fillna(0)
    existing_has_dedupe = bool((existing_counts > 0).any())
    work = original.copy()
    if "source_file_type" not in work.columns:
        work["source_file_type"] = ""
    work["preferred_source"] = work["source_file_type"].fillna("").astype(str)
    work["dedupe_group_id"] = ""
    work["dedupe_action"] = "retained"
    work["dedupe_reason"] = ""
    work["dedupe_excluded_count"] = 0
    work["dedupe_excluded_evaluation_amount"] = 0.0
    work["_dedupe_key"] = work.apply(build_holding_dedupe_key, axis=1)

    drop_indices: set[int] = set()
    excluded_by_preferred: dict[int, list[int]] = {}

    def record_excluded(preferred_idx: int, excluded_indices: list[int], group_key: str) -> None:
        group_id = hashlib.sha256(str(group_key).encode("utf-8")).hexdigest()[:12]
        excluded_value = sum(_dedupe_number(work.at[idx, "evaluation_amount"]) or 0.0 for idx in excluded_indices)
        work.at[preferred_idx, "dedupe_group_id"] = group_id
        work.at[preferred_idx, "dedupe_action"] = "retained_preferred"
        work.at[preferred_idx, "dedupe_reason"] = "overseas_balance_retained_over_holdings_duplicate"
        work.at[preferred_idx, "preferred_source"] = "overseas_balance"
        work.at[preferred_idx, "dedupe_excluded_count"] = int(work.at[preferred_idx, "dedupe_excluded_count"]) + len(excluded_indices)
        work.at[preferred_idx, "dedupe_excluded_evaluation_amount"] = (
            float(work.at[preferred_idx, "dedupe_excluded_evaluation_amount"]) + excluded_value
        )

    groups = work[work["_dedupe_key"].fillna("").astype(str).ne("")].groupby("_dedupe_key", dropna=False)

    for group_key, group in groups:
        source_types = group.get("source_file_type", pd.Series("", index=group.index)).fillna("").astype(str).str.lower()
        if "overseas_balance" not in set(source_types) or "holdings" not in set(source_types):
            continue
        preferred_indices = [
            idx for idx in group.index
            if str(work.at[idx, "source_file_type"]).strip().lower() == "overseas_balance"
        ]
        preferred_indices = sorted(preferred_indices, key=lambda idx: (rank_holding_source(work.loc[idx]), idx))
        candidate_indices = [
            idx for idx in group.index
            if str(work.at[idx, "source_file_type"]).strip().lower() == "holdings"
        ]
        for candidate_idx in candidate_indices:
            if candidate_idx in drop_indices:
                continue
            candidate = work.loc[candidate_idx]
            for preferred_idx in preferred_indices:
                preferred = work.loc[preferred_idx]
                if _same_economic_holding(preferred, candidate):
                    drop_indices.add(candidate_idx)
                    excluded_by_preferred.setdefault(preferred_idx, []).append(candidate_idx)
                    break

        for preferred_idx, excluded_indices in excluded_by_preferred.items():
            if preferred_idx not in group.index or not excluded_indices:
                continue
            record_excluded(preferred_idx, excluded_indices, str(group_key))

    preferred_indices = sorted(
        [
            idx for idx in work.index
            if idx not in drop_indices
            and str(work.at[idx, "source_file_type"]).strip().lower() == "overseas_balance"
        ],
        key=lambda idx: (rank_holding_source(work.loc[idx]), idx),
    )
    candidate_indices = [
        idx for idx in work.index
        if idx not in drop_indices
        and str(work.at[idx, "source_file_type"]).strip().lower() == "holdings"
    ]
    for candidate_idx in candidate_indices:
        candidate = work.loc[candidate_idx]
        for preferred_idx in preferred_indices:
            preferred = work.loc[preferred_idx]
            if _same_economic_holding(preferred, candidate):
                drop_indices.add(candidate_idx)
                fallback_key = "|".join([
                    "overseas-fallback",
                    str(work.at[preferred_idx, "_dedupe_key"] or normalize_holding_identity(preferred)["position_key"] or _holding_name_key(preferred)),
                    str(work.at[candidate_idx, "_dedupe_key"] or normalize_holding_identity(candidate)["position_key"] or _holding_name_key(candidate)),
                ])
                record_excluded(preferred_idx, [candidate_idx], fallback_key)
                break

    if not drop_indices and existing_has_dedupe:
        for col in HOLDING_DEDUPE_COLUMNS:
            if col not in original.columns:
                original[col] = ""
        return original.reset_index(drop=True)

    result = work[~work.index.isin(drop_indices)].drop(columns=["_dedupe_key"], errors="ignore").reset_index(drop=True)
    for col in HOLDING_DEDUPE_COLUMNS:
        if col not in result.columns:
            result[col] = ""
    return result


def remove_overlapping_overseas_holdings(df: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible wrapper for overseas holding deduplication."""
    return dedupe_holdings(df)


def collapse_holding_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS + HOLDING_DEDUPE_COLUMNS)
    work = df.copy()
    work["ticker"] = work.get("ticker", "").astype(str)
    work = work[~work["ticker"].str.lower().isin(["", "nan", "none"])]
    if work.empty:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS + HOLDING_DEDUPE_COLUMNS)
    work = remove_overlapping_overseas_holdings(work)
    if "trade_date" in work:
        work["_sort_date"] = pd.to_datetime(work["trade_date"], errors="coerce")
        work = work.sort_values(["account_type", "ticker", "_sort_date"], na_position="first")
    group_cols = [c for c in ["account_type", "ticker"] if c in work.columns]
    collapsed = work.groupby(group_cols, dropna=False, as_index=False).tail(1).drop(columns=["_sort_date"], errors="ignore")
    return collapsed.reset_index(drop=True)


def split_current_history_holdings(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS + HOLDING_DEDUPE_COLUMNS), pd.DataFrame(columns=HISTORY_COLUMNS)
    work = df.copy()
    has_balance_col = "balance_quantity" in work.columns
    has_evaluation_col = "evaluation_amount" in work.columns
    has_quantity_col = "quantity" in work.columns
    for col in ["balance_quantity", "quantity", "evaluation_amount"]:
        if col not in work.columns:
            work[col] = 0
        work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)
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
        history["suggested_action"] = "필요 시 사후분석 또는 교훈 후보로 검토"
    return current.reset_index(drop=True), history.reindex(columns=HISTORY_COLUMNS).reset_index(drop=True)


def write_sqlite(processed_dir: Path, outputs: dict[str, pd.DataFrame]) -> None:
    db_path = processed_dir / "investment.db"
    with sqlite3.connect(db_path) as con:
        for csv_name, df in outputs.items():
            table = csv_name.removesuffix(".csv")
            df.to_sql(table, con, if_exists="replace", index=False)


def import_raw_dir(vault_root: Path, raw_dir: Path | None = None, processed_dir: Path | None = None, force_reindex: bool = False, dry_run: bool = False, verbose: bool = False) -> ImportSummary:
    raw_dir = (raw_dir or vault_root / "70_Imports" / "raw").resolve()
    processed_dir = processed_dir or vault_root / "70_Imports" / "processed"
    summary = ImportSummary()
    outputs = empty_outputs(processed_dir)
    all_rows: list[pd.DataFrame] = []
    audit: list[pd.DataFrame] = []
    source_rows: list[dict[str, Any]] = []
    unknown_columns: list[dict[str, Any]] = []

    files = sorted([p for p in raw_dir.glob("*") if p.suffix.lower() in {".xls", ".xlsx"} and not p.name.startswith("~$")]) if raw_dir.exists() else []
    summary.raw_files = len(files)

    for path in files:
        if verbose:
            print(f"[파일] {path.name}")
        sensitive = detect_sensitive(path.name)
        source_name = safe_source_name(path)
        raw_hash = hashlib.sha256(path.name.encode("utf-8")).hexdigest()
        try:
            tables = load_workbook_tables(path)
        except Exception as exc:
            source_rows.append({"source_file": source_name, "source_file_type": "read_error", "account_type": infer_account_type(path.name), "raw_path_hash": raw_hash, "size_bytes": path.stat().st_size, "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"), "imported_at": datetime.now().isoformat(timespec="seconds"), "sensitive_data_found": sensitive, "error": str(exc)})
            continue
        file_type_seen = "unknown"
        for sheet, df in tables.items():
            normalized, raw_audit, unknown = normalize_dataframe(df, path, str(sheet))
            if not normalized.empty:
                file_type_seen = normalized["source_file_type"].dropna().iloc[0]
            all_rows.append(normalized)
            audit.append(raw_audit)
            for col in unknown:
                unknown_columns.append({"source_file": source_name, "sheet": sheet, "unknown_column": col})
        source_rows.append({"source_file": source_name, "source_file_type": file_type_seen, "account_type": infer_account_type(path.name), "raw_path_hash": raw_hash, "size_bytes": path.stat().st_size, "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"), "imported_at": datetime.now().isoformat(timespec="seconds"), "sensitive_data_found": sensitive})

    combined = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame(columns=NORMALIZED_COLUMNS)
    summary.parsed_rows = len(combined)
    before = len(combined)
    combined, adjacent_skipped_rows = remove_adjacent_duplicate_principal_cashflows(combined)
    if not combined.empty:
        combined = combined.drop_duplicates(subset=["import_id"], keep="last").reset_index(drop=True)
    summary.duplicate_rows_removed = before - len(combined)
    combined, helper_skipped_rows = split_skipped_broker_helper_rows(combined)
    outputs["skipped_rows.csv"] = combine_skipped_rows(adjacent_skipped_rows, helper_skipped_rows)
    combined = normalize_amount_dataframe(combined)
    outputs["amount_unit_audit.csv"] = amount_unit_audit_rows(combined)
    outputs["unit_mismatch_audit.csv"] = unit_mismatch_audit_rows(combined)
    summary.unclassified_rows = int((combined.get("transaction_type", pd.Series(dtype=str)) == "unknown").sum()) if not combined.empty else 0
    summary.unknown_columns = len(unknown_columns)

    outputs["processed_transactions.csv"] = combined[combined.apply(is_transaction_ledger_row, axis=1)].copy() if not combined.empty else outputs["processed_transactions.csv"]
    holding_candidates = combined[combined.apply(is_position_snapshot_row, axis=1)].copy() if not combined.empty else outputs["processed_holdings.csv"]
    collapsed_holdings = collapse_holding_rows(holding_candidates)
    current_holdings, history_holdings = split_current_history_holdings(collapsed_holdings)
    outputs["processed_holdings.csv"] = current_holdings
    outputs["history_queue.csv"] = history_holdings
    outputs["post_mortem_candidates.csv"] = history_holdings
    tx_rows = outputs["processed_transactions.csv"]
    principal_cashflows = tx_rows[tx_rows.apply(is_principal_cashflow_row, axis=1)].copy() if not tx_rows.empty else outputs["processed_cashflows.csv"]
    outputs["processed_cashflows.csv"] = dedupe_principal_cashflow_view(principal_cashflows, context_rows=tx_rows)
    outputs["processed_dividends.csv"] = tx_rows[tx_rows["transaction_type"].eq("dividend")].copy() if not tx_rows.empty else outputs["processed_dividends.csv"]
    outputs["unclassified_rows.csv"] = tx_rows[tx_rows["transaction_type"].eq("unknown")].copy() if not tx_rows.empty else outputs["unclassified_rows.csv"]
    source_index_columns = list(outputs["source_file_index.csv"].columns)
    if any("error" in row for row in source_rows):
        source_index_columns.append("error")
    outputs["source_file_index.csv"] = pd.DataFrame(source_rows, columns=source_index_columns)
    outputs["raw_rows_audit.csv"] = pd.concat(audit, ignore_index=True) if audit else outputs["raw_rows_audit.csv"]

    if unknown_columns:
        outputs["unknown_columns.csv"] = pd.DataFrame(unknown_columns)

    for name, frame in list(outputs.items()):
        outputs[name] = strip_internal_normalized_columns(frame)

    if dry_run:
        return summary

    processed_dir.mkdir(parents=True, exist_ok=True)
    for name, df in outputs.items():
        df.to_csv(processed_dir / name, index=False, encoding="utf-8-sig")
    write_sqlite(processed_dir, outputs)
    return summary
