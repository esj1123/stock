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
]

HISTORY_COLUMNS = NORMALIZED_COLUMNS + ["history_reason", "suggested_destination", "suggested_action"]

SKIPPED_ROWS_COLUMNS = [
    "source_file", "source_file_type", "account_type", "skip_reason",
    "currency", "fx_rate", "amount_kind", "row_count",
]

OVERSEAS_CASHFLOW_AMOUNT_ONLY_SKIP_REASON = "OVERSEAS_CASHFLOW_AMOUNT_ONLY_NO_IDENTITY"

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
    "US88160R1014": "TSLA",
    "US67066G1040": "NVDA",
    "US02079K3059": "GOOGL",
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


def normalize_currency_and_fx_rate(raw_currency: Any, raw_fx_rate: Any = "", source_type: str = "") -> tuple[str, Any]:
    default_currency = "USD" if "overseas" in str(source_type).lower() else "KRW"
    fx_rate = fx_rate_from_text(raw_fx_rate)
    currency = currency_code_from_text(raw_currency)
    currency_fx_rate = fx_rate_from_text(raw_currency)
    if not currency:
        if fx_rate is None and currency_fx_rate is not None:
            fx_rate = currency_fx_rate
        currency = default_currency
    return currency, (fx_rate if fx_rate is not None else pd.NA)


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

    skipped = pd.DataFrame(skipped_records, columns=SKIPPED_ROWS_COLUMNS)
    group_cols = [col for col in SKIPPED_ROWS_COLUMNS if col != "row_count"]
    skipped = skipped.groupby(group_cols, dropna=False, as_index=False)["row_count"].sum()
    return df[~skip_mask].copy(), skipped[SKIPPED_ROWS_COLUMNS]


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
    normalized = {col: normalize_key(col) for col in columns}
    for alias in COLUMN_ALIASES.get(canonical, []):
        alias_norm = normalize_key(alias)
        for col, col_norm in normalized.items():
            if alias_norm and alias_norm in col_norm:
                return col
    return None


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
    cashflow_signals = ["입출금내역", "입출금", "예수금", "출금가능금액", "cashflow", "cash flow", "cash_flow"]
    overseas_balance_signals = ["해외증권잔고조회", "해외증권잔고", "외화평가금액", "해외잔고"]
    holdings_signals = [
        "종합잔고", "잔고조회", "계좌잔고", "보유잔고", "보유현황",
        "평가금액", "평가손익", "평가손익률", "평균단가", "현재가",
    ]
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
        flat.columns = [" ".join([str(x) for x in col if str(x) != "nan"]).strip() for col in flat.columns]
    flat.columns = [str(c).strip() for c in flat.columns]
    columns = list(flat.columns)
    source_type = infer_source_file_type(source_path, sheet_name, flat)
    account_type = infer_account_type(source_path.name, sheet_name)
    source_file = safe_source_name(source_path)
    unknown_columns = [str(c) for c in columns if not any(find_column(columns, key) == c for key in COLUMN_ALIASES)]

    cols = {key: find_column(columns, key) for key in COLUMN_ALIASES}
    rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    for idx, raw in flat.iterrows():
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
        is_balance_source = source_type in {"holdings", "overseas_balance"}
        balance_quantity_value = parse_korean_number(raw.get(cols["balance_quantity"])) if cols.get("balance_quantity") is not None else (quantity if is_balance_source else 0.0)
        trade_amount = parse_korean_number(raw.get(cols["trade_amount"])) if cols.get("trade_amount") is not None else 0.0
        settlement_amount = parse_korean_number(raw.get(cols["settlement_amount"])) if cols.get("settlement_amount") is not None else trade_amount
        evaluation_amount_value = parse_korean_number(raw.get(cols["evaluation_amount"])) if cols.get("evaluation_amount") is not None else 0.0
        unrealized_pnl_value = parse_korean_number(raw.get(cols["unrealized_pnl"])) if cols.get("unrealized_pnl") is not None else 0.0
        pnl_pct_value = parse_korean_percent(raw.get(cols["pnl_pct"])) if cols.get("pnl_pct") is not None else pd.NA
        balance_quantity = balance_quantity_value if is_balance_source else pd.NA
        evaluation_amount = evaluation_amount_value if is_balance_source else pd.NA
        unrealized_pnl = unrealized_pnl_value if is_balance_source else pd.NA
        pnl_pct = pnl_pct_value if is_balance_source else pd.NA
        raw_currency = raw.get(cols["currency"]) if cols.get("currency") is not None else ""
        raw_fx_rate = raw.get(cols["exchange_rate"]) if cols.get("exchange_rate") is not None else ""
        currency, fx_rate = normalize_currency_and_fx_rate(raw_currency, raw_fx_rate, source_type)
        asset_type = infer_asset_type(name, ticker)
        if asset_type == "cash":
            currency = normalize_cash_currency(name, ticker, currency)
        fx_rate_for_stable = "" if pd.isna(fx_rate) else fx_rate

        if not any([date, ticker, name, raw_type, trade_amount, settlement_amount, evaluation_amount_value, balance_quantity_value]):
            continue

        stable = {
            "source_file_type": source_type, "account_type": account_type, "ticker": ticker,
            "security_name": name, "trade_date": date, "trade_time": normalize_time(raw.get(cols["trade_time"])) if cols.get("trade_time") is not None else "",
            "transaction_type": tx_type, "quantity": quantity, "price": parse_korean_number(raw.get(cols["price"])) if cols.get("price") is not None else 0.0,
            "trade_amount": trade_amount, "settlement_amount": settlement_amount,
            "fee": parse_korean_number(raw.get(cols["fee"])) if cols.get("fee") is not None else 0.0,
            "tax": parse_korean_number(raw.get(cols["tax"])) if cols.get("tax") is not None else 0.0,
            "currency": currency, "fx_rate": fx_rate_for_stable, "raw_memo": memo,
        }
        import_id = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        row = {
            "import_id": import_id,
            "source_file": source_file,
            "source_file_type": source_type,
            "account_type": account_type,
            "market": infer_market(ticker, name, source_type),
            "asset_type": asset_type,
            "ticker": ticker,
            "security_name": redact_sensitive(name),
            "trade_date": date,
            "trade_time": stable["trade_time"],
            "transaction_type": tx_type,
            "quantity": quantity,
            "price": stable["price"],
            "trade_amount": trade_amount,
            "settlement_amount": settlement_amount,
            "fee": stable["fee"],
            "tax": stable["tax"],
            "currency": currency,
            "fx_rate": fx_rate,
            "balance_quantity": balance_quantity,
            "evaluation_amount": evaluation_amount,
            "unrealized_pnl": unrealized_pnl,
            "pnl_pct": pnl_pct,
            "raw_memo": redact_sensitive(memo),
        }
        rows.append(row)
        audit_rows.append({"import_id": import_id, "source_file": source_file, "sheet": sheet_name, "row_number": int(idx) + 1, "raw_json": raw_json})

    return pd.DataFrame(rows, columns=NORMALIZED_COLUMNS), pd.DataFrame(audit_rows), unknown_columns


def empty_outputs(processed_dir: Path) -> dict[str, pd.DataFrame]:
    return {
        "processed_transactions.csv": pd.DataFrame(columns=NORMALIZED_COLUMNS),
        "processed_holdings.csv": pd.DataFrame(columns=NORMALIZED_COLUMNS),
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
    }


def remove_overlapping_overseas_holdings(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "ticker" not in df.columns:
        return df.copy()
    work = df.copy()
    source_type = work["source_file_type"].fillna("").astype(str) if "source_file_type" in work.columns else pd.Series("", index=work.index)
    canonical_keys = work.apply(canonical_overseas_position_key, axis=1)
    is_overseas = work.apply(is_overseas_position_row, axis=1)
    overseas_balance_keys = set(canonical_keys[source_type.eq("overseas_balance") & is_overseas & canonical_keys.ne("")])
    if not overseas_balance_keys:
        return work.reset_index(drop=True)
    drop_mask = source_type.eq("holdings") & is_overseas & canonical_keys.isin(overseas_balance_keys)
    return work[~drop_mask].reset_index(drop=True)


def collapse_holding_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS)
    work = df.copy()
    work["ticker"] = work.get("ticker", "").astype(str)
    work = work[~work["ticker"].str.lower().isin(["", "nan", "none"])]
    if work.empty:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS)
    work = remove_overlapping_overseas_holdings(work)
    if "trade_date" in work:
        work["_sort_date"] = pd.to_datetime(work["trade_date"], errors="coerce")
        work = work.sort_values(["account_type", "ticker", "_sort_date"], na_position="first")
    group_cols = [c for c in ["account_type", "ticker"] if c in work.columns]
    collapsed = work.groupby(group_cols, dropna=False, as_index=False).tail(1).drop(columns=["_sort_date"], errors="ignore")
    return collapsed.reset_index(drop=True)


def split_current_history_holdings(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS), pd.DataFrame(columns=HISTORY_COLUMNS)
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
    if not combined.empty:
        combined = combined.drop_duplicates(subset=["import_id"], keep="last").reset_index(drop=True)
    summary.duplicate_rows_removed = before - len(combined)
    combined, skipped_rows = split_skipped_broker_helper_rows(combined)
    outputs["skipped_rows.csv"] = skipped_rows
    summary.unclassified_rows = int((combined.get("transaction_type", pd.Series(dtype=str)) == "unknown").sum()) if not combined.empty else 0
    summary.unknown_columns = len(unknown_columns)

    transaction_source_types = {"transaction_history", "transactions", "cashflow"}
    outputs["processed_transactions.csv"] = combined[combined["source_file_type"].isin(transaction_source_types)].copy() if not combined.empty else outputs["processed_transactions.csv"]
    holding_candidates = combined[combined["source_file_type"].isin(["holdings", "overseas_balance"])].copy() if not combined.empty else outputs["processed_holdings.csv"]
    collapsed_holdings = collapse_holding_rows(holding_candidates)
    current_holdings, history_holdings = split_current_history_holdings(collapsed_holdings)
    outputs["processed_holdings.csv"] = current_holdings
    outputs["history_queue.csv"] = history_holdings
    outputs["post_mortem_candidates.csv"] = history_holdings
    tx_rows = outputs["processed_transactions.csv"]
    outputs["processed_cashflows.csv"] = tx_rows[tx_rows["transaction_type"].isin(["deposit", "withdrawal", "exchange", "transfer", "interest"])].copy() if not tx_rows.empty else outputs["processed_cashflows.csv"]
    outputs["processed_dividends.csv"] = tx_rows[tx_rows["transaction_type"].eq("dividend")].copy() if not tx_rows.empty else outputs["processed_dividends.csv"]
    outputs["unclassified_rows.csv"] = tx_rows[tx_rows["transaction_type"].eq("unknown")].copy() if not tx_rows.empty else outputs["unclassified_rows.csv"]
    source_index_columns = list(outputs["source_file_index.csv"].columns)
    if any("error" in row for row in source_rows):
        source_index_columns.append("error")
    outputs["source_file_index.csv"] = pd.DataFrame(source_rows, columns=source_index_columns)
    outputs["raw_rows_audit.csv"] = pd.concat(audit, ignore_index=True) if audit else outputs["raw_rows_audit.csv"]

    if unknown_columns:
        outputs["unknown_columns.csv"] = pd.DataFrame(unknown_columns)

    if dry_run:
        return summary

    processed_dir.mkdir(parents=True, exist_ok=True)
    for name, df in outputs.items():
        df.to_csv(processed_dir / name, index=False, encoding="utf-8-sig")
    write_sqlite(processed_dir, outputs)
    return summary
