#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
나무증권(NH투자증권) 다운로드 파일(.xls/.xlsx) 내역을 옵시디언 Vault 구조로 변환하는 임포터

✅ 지원 포맷
- .xlsx : 일반 엑셀(Excel OpenXML)
- .xls  : 나무증권에서 내려받는 "엑셀"은 실제로는 HTML 테이블(.xls 확장자)인 경우가 많음
         → 본 스크립트는 HTML(.xls)도 자동 감지해서 파싱합니다.
         → (추가) 진짜 BIFF .xls도 가능한 경우 읽기를 시도합니다.

목표
- 원본 파일(raw)은 그대로 보관(수정 금지)
- 행을 정규화(ledger.csv)하여 DB로 축적
- 거래(BUY/SELL/DIV) 노트와 입출금(CASH_IN/CASH_OUT) 노트를 자동 생성
- 분류 실패/기타(FX/INTEREST/OTHER)는 review 폴더로 분리(데이터는 버리지 않음)

중요: 파일명 규칙 강제 없음
- 나무증권 기본 파일명(예: "종합거래내역(상세)_... .xls") 그대로 넣어도 동작합니다.
- 파일명 마지막 괄호 태그를 계좌 구분에 활용할 수 있습니다.
  - 예: ...(종합).xls  → account: "종합"
  - 예: ...(ISA).xls   → account: "ISA"
  - 예: ...(내용).xls  → account: "" (무시)

실행 예시 (Vault 루트에서)
    pip install -r 70_Imports/scripts/requirements.txt
    python 70_Imports/scripts/namoo_excel_import.py --create-companies

테스트 실행(파일 생성 없이)
    python 70_Imports/scripts/namoo_excel_import.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# =========================
# 설정: 폴더 경로(상대경로)
# =========================
DEFAULT_RAW_DIR = Path("70_Imports/raw")
DEFAULT_PROCESSED_DIR = Path("70_Imports/processed")
DEFAULT_REVIEW_DIR = Path("70_Imports/review")

DEFAULT_TRADES_DIR = Path("30_Trades")
DEFAULT_CASHFLOWS_DIR = Path("31_Cashflows")
DEFAULT_COMPANY_DIR = Path("20_Companies")

LEDGER_FILENAME = "namoo_ledger.csv"
UNCLASSIFIED_FILENAME = "unclassified.csv"


# =========================
# 컬럼 유사어(필요시 튜닝)
# =========================
# 열 제목이 아래 유사어 중 하나를 포함하면 매칭(대소문자/공백/특수문자 무시)
COLUMN_SYNONYMS: Dict[str, List[str]] = {
    "date": [
        "거래일", "거래일자", "일자", "매매일", "체결일", "처리일자", "날짜", "거래일(현지)", "정산일",
    ],
    "ticker": [
        "종목코드", "단축코드", "코드", "티커", "종목",
    ],
    "name": [
        "종목명", "종목명칭", "명칭", "종목명(한글)", "종목명(영문)", "종목명(약칭)",
    ],
    "type": [
        "매매구분", "거래구분", "구분", "내용", "적요", "거래내용", "입출금구분", "구분명",
        "거래유형", "상세내용",
    ],
    "qty": [
        "수량", "매매수량", "체결수량", "수량(주)", "주수",
    ],
    "price": [
        "단가", "매매단가", "체결단가", "가격", "체결가",
    ],
    "amount": [
        "금액", "거래금액", "정산금액", "입금액", "출금액", "배당금", "현금배당", "원화금액", "외화금액",
    ],
    "fee": [
        "수수료", "제수수료", "수수료합", "매매수수료",
    ],
    "tax": [
        "세금", "제세금", "거래세", "원천징수세", "제세금합",
    ],
    "currency": [
        "통화", "통화코드", "거래통화", "결제통화",
    ],
    "memo": [
        "비고", "메모", "상세", "적요", "내용", "거래내역메모",
    ],
}


# =========================
# 키워드 기반 분류(필요시 튜닝)
# =========================
BUY_KEYWORDS = ["매수", "buy", "매입"]
SELL_KEYWORDS = ["매도", "sell"]
DIV_KEYWORDS = ["배당", "div", "분배", "현금배당"]

CASH_IN_KEYWORDS = ["입금", "대체입금", "예수금입금", "현금입금", "cash in"]
CASH_OUT_KEYWORDS = ["출금", "이체", "현금출금", "cash out"]

FX_KEYWORDS = ["환전", "외화매수", "외화매도", "환전매수", "환전매도"]
INTEREST_KEYWORDS = ["이자"]


# =========================
# 데이터 클래스
# =========================
@dataclass
class LedgerRow:
    import_id: str
    date: str                     # YYYY-MM-DD
    ticker: str                   # 예: 005930, AAPL, USXXXXXXXXXXXX(표준코드)
    name: str
    type: str                     # BUY/SELL/DIV/CASH_IN/CASH_OUT/FX/INTEREST/OTHER
    qty: float
    price: float
    amount: float
    fee: float
    tax: float
    currency: str
    strategy: str
    account: str
    memo: str
    source_file: str
    sheet: str
    raw_type: str
    raw_memo: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "import_id": self.import_id,
            "date": self.date,
            "ticker": self.ticker,
            "name": self.name,
            "type": self.type,
            "qty": self.qty,
            "price": self.price,
            "amount": self.amount,
            "fee": self.fee,
            "tax": self.tax,
            "currency": self.currency,
            "strategy": self.strategy,
            "account": self.account,
            "memo": self.memo,
            "source_file": self.source_file,
            "sheet": self.sheet,
            "raw_type": self.raw_type,
            "raw_memo": self.raw_memo,
        }


# =========================
# 헬퍼
# =========================
def normalize_key(s: str) -> str:
    """열 이름 비교를 위해 공백/특수문자를 제거하고 소문자로 통일"""
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(s)).lower()


def safe_path_component(s: str) -> str:
    """폴더/파일명에 위험한 문자를 '_'로 치환"""
    return re.sub(r"[^0-9A-Za-z가-힣\.\-_]+", "_", s).strip("_")


def to_float(x: Any) -> float:
    try:
        if pd.isna(x):
            return 0.0
        if isinstance(x, str):
            x = x.replace(",", "").strip()
            if x == "":
                return 0.0
        return float(x)
    except Exception:
        return 0.0


def to_str(x: Any) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return str(x).strip()


def parse_date(x: Any) -> Optional[str]:
    """엑셀 날짜/문자열을 YYYY-MM-DD로 변환"""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None

    # 1) pandas 파서 우선
    try:
        dt = pd.to_datetime(x)
        if not pd.isna(dt):
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    # 2) 문자열 패턴(YYYY.MM.DD / YYYYMMDD)
    s = to_str(x)

    # 시간/괄호 제거: "2026.03.02 (10:00:00)" 같은 경우
    s = re.sub(r"\(.*?\)", "", s).strip()

    m = re.match(r"^(\d{4})[.\-/ ]?(\d{1,2})[.\-/ ]?(\d{1,2})$", s)
    if m:
        yyyy, mm, dd = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        return f"{yyyy}-{mm}-{dd}"

    m2 = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"

    return None


def pad_korean_ticker(ticker: str) -> str:
    """한국 종목코드 6자리 맞추기 (예: '5930' -> '005930')"""
    t = ticker.strip()
    if re.fullmatch(r"\d{1,6}", t):
        return t.zfill(6)
    return t.upper()


def classify(raw_text: str) -> str:
    """거래/입출금 구분 키워드 기반 분류"""
    s = (raw_text or "").lower()

    def has_any(keywords: List[str]) -> bool:
        return any(k.lower() in s for k in keywords)

    if has_any(BUY_KEYWORDS):
        return "BUY"
    if has_any(SELL_KEYWORDS):
        return "SELL"
    if has_any(DIV_KEYWORDS):
        return "DIV"
    if has_any(CASH_IN_KEYWORDS):
        return "CASH_IN"
    if has_any(CASH_OUT_KEYWORDS):
        return "CASH_OUT"
    if has_any(FX_KEYWORDS):
        return "FX"
    if has_any(INTEREST_KEYWORDS):
        return "INTEREST"
    return "OTHER"


def compute_import_id(payload: Dict[str, Any]) -> str:
    """중복 방지를 위한 해시(내용 기반)"""
    stable = {
        "date": payload.get("date", ""),
        "ticker": payload.get("ticker", ""),
        "type": payload.get("type", ""),
        "qty": round(float(payload.get("qty", 0) or 0), 6),
        "price": round(float(payload.get("price", 0) or 0), 6),
        "amount": round(float(payload.get("amount", 0) or 0), 6),
        "fee": round(float(payload.get("fee", 0) or 0), 6),
        "tax": round(float(payload.get("tax", 0) or 0), 6),
        "currency": payload.get("currency", ""),
        "raw_type": payload.get("raw_type", ""),
        "raw_memo": payload.get("raw_memo", ""),
        "account": payload.get("account", ""),
    }
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def find_best_column(columns: List[str], canon: str) -> Optional[str]:
    """canonical field(canon)에 대해 columns에서 가장 적절한 열 이름을 찾는다."""
    normalized = {c: normalize_key(c) for c in columns}
    synonyms = COLUMN_SYNONYMS.get(canon, [])
    syn_norm = [normalize_key(s) for s in synonyms]

    for c, cn in normalized.items():
        for s in syn_norm:
            if s and s in cn:
                return c
    return None


def ensure_dir(path: Path, dry_run: bool) -> None:
    if dry_run:
        return
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def infer_account_from_filename(filename: str) -> str:
    """파일명 마지막 괄호 태그로 계좌 구분(종합/ISA 등) 추정. (내용)은 무시"""
    # 예: 종합거래내역(상세)_..._2026.03.02(ISA).xls → ISA
    m = re.search(r"\(([^()]+)\)\.[^.]+$", filename)
    if not m:
        return ""
    tag = m.group(1).strip()
    tag_upper = tag.upper()

    if tag_upper == "ISA":
        return "ISA"
    if tag == "종합":
        return "종합"
    if tag == "내용":
        return ""  # 사용자가 '내용' 태그를 붙인 경우 무시

    # 그 외 사용자 태그는 그대로 반환(필요하면)
    return tag


def detect_html_encoding(raw: bytes) -> str:
    """<meta charset=...> 기반 간단 인코딩 감지"""
    head = raw[:3000].decode("ascii", errors="ignore")
    m = re.search(r"charset\s*=\s*([A-Za-z0-9_\-]+)", head, re.I)
    if m:
        enc = m.group(1).strip().lower()
        # 흔한 표기 normalize
        if enc in ("euc-kr", "euckr"):
            return "euc-kr"
        if enc in ("cp949", "ms949"):
            return "cp949"
        return enc
    return "euc-kr"  # 나무 엑셀은 EUC-KR이 흔함


def is_html_xls(raw: bytes) -> bool:
    head = raw[:200].decode("ascii", errors="ignore").lower()
    return ("<html" in head) or ("<!doctype" in head) or ("<table" in head)


def load_excel(path: Path) -> Dict[str, pd.DataFrame]:
    """파일 확장자/내용 기반으로 시트(또는 테이블)들을 DataFrame으로 로드"""
    suf = path.suffix.lower()

    if suf == ".xlsx":
        # sheet_name=None -> 모든 시트 읽기
        return pd.read_excel(path, sheet_name=None, engine="openpyxl")

    if suf == ".xls":
        raw = path.read_bytes()

        # 나무 'xls'는 HTML인 경우가 많음
        if is_html_xls(raw):
            enc = detect_html_encoding(raw)
            try:
                html = raw.decode(enc, errors="ignore")
            except Exception:
                # 폴백
                html = raw.decode("cp949", errors="ignore")

            # pandas.read_html은 앞으로 literal html을 금지 예정이라 StringIO로 감싸기
            tables = pd.read_html(StringIO(html), flavor="bs4")
            if not tables:
                return {}
            if len(tables) == 1:
                return {"table_0": tables[0]}
            return {f"table_{i}": t for i, t in enumerate(tables)}

        # 진짜 BIFF .xls인 경우 시도
        try:
            return pd.read_excel(path, sheet_name=None, engine="xlrd")
        except Exception:
            # 최후 폴백: 그냥 1개 시트로 시도
            return {"sheet_0": pd.read_excel(path, engine="xlrd")}

    # 알 수 없는 확장자
    return {}


# =========================
# 노트 생성
# =========================
def make_trade_note(row: LedgerRow) -> str:
    title = f"{row.date} {row.type} {row.ticker}"
    company_link = f"[[20_Companies/{safe_path_component(row.ticker)}/Company|Company]]"
    amount_line = ""
    if row.type == "DIV":
        amount_line = f"- 배당금: **{row.amount} {row.currency}**\n"
    return f"""\
---
date: {row.date}
ticker: "{row.ticker}"
type: "{row.type}"
qty: {row.qty}
price: {row.price}
amount: {row.amount}
fee: {row.fee}
tax: {row.tax}
currency: "{row.currency}"
strategy: "{row.strategy}"
account: "{row.account}"
import_id: "{row.import_id}"
source_file: "{row.source_file}"
memo: "{row.memo}"
---

# {title}

{amount_line}## 한 줄 요약
- {row.memo}

## 원본 정보(참고)
- 원본 구분: {row.raw_type}
- 원본 메모: {row.raw_memo}
- 파일: {row.source_file} / 시트: {row.sheet}

## 링크
- 회사: {company_link}
"""


def make_cashflow_note(row: LedgerRow) -> str:
    title = f"{row.date} {row.type} {row.amount} {row.currency}"
    sign = "입금" if row.type == "CASH_IN" else "출금"
    return f"""\
---
date: {row.date}
type: "{row.type}"
amount: {row.amount}
currency: "{row.currency}"
account: "{row.account}"
import_id: "{row.import_id}"
source_file: "{row.source_file}"
memo: "{row.memo}"
---

# {title}

- 구분: {sign}
- 메모: {row.memo}

## 원본 정보(참고)
- 원본 구분: {row.raw_type}
- 원본 메모: {row.raw_memo}
- 파일: {row.source_file} / 시트: {row.sheet}
"""


def make_unclassified_note(row: LedgerRow) -> str:
    return f"""\
---
date: {row.date}
source_file: "{row.source_file}"
sheet: "{row.sheet}"
raw_type: "{row.raw_type}"
raw_memo: "{row.raw_memo}"
hint: "열 이름/키워드 규칙을 보완하세요 (70_Imports/scripts/namoo_excel_import.py)"
import_id: "{row.import_id}"
---

# 분류 실패 (UNCLASSIFIED)

## 원본
- 일자: {row.date}
- 구분: {row.raw_type}
- 메모: {row.raw_memo}

## 스크립트가 읽은 값(참고)
- ticker: {row.ticker}
- name: {row.name}
- qty: {row.qty}
- price: {row.price}
- amount: {row.amount}
- fee: {row.fee}
- tax: {row.tax}
- currency: {row.currency}
- account: {row.account}
"""


def ensure_company_folder(ticker: str, dry_run: bool) -> None:
    t = safe_path_component(ticker)
    folder = DEFAULT_COMPANY_DIR / t
    company_md = folder / "Company.md"
    notes_dir = folder / "Notes"
    events_dir = folder / "Events"

    if company_md.exists():
        return

    ensure_dir(notes_dir, dry_run)
    ensure_dir(events_dir, dry_run)

    now = datetime.now().strftime("%Y-%m-%d")
    template = f"""\
---
doc_type: company
ticker: "{ticker}"
name: ""
market: ""
country: ""
sector: ""
industry: ""
currency: "KRW"
status: "watch"
conviction: 3
time_horizon: ""
last_update: {now}
price_now: 0
price_date: {now}
target_pct: 0
max_pct: 0
---

# {ticker}

## 0) 한 줄 투자 아이디어
- 

## 1) 투자 논리(Thesis)
- 

## 2) 관찰 포인트
- 

## 3) 리스크 + 대응
- 

## 4) 업데이트 로그
- {now}: (자동 생성)

---

## 관련 거래(자동)
```dataview
TABLE date as "일자", type as "구분", qty as "수량", price as "단가", amount as "배당", fee as "수수료", tax as "세금", file.link as "노트"
FROM "30_Trades"
WHERE ticker = this.ticker
SORT date DESC
```
"""
    write_text(company_md, template, dry_run)
    write_text(notes_dir / "README.md", "# Notes\n\n- 리서치/메모를 여기에 작성하세요.\n", dry_run)
    write_text(events_dir / "README.md", "# Events\n\n- 실적/이벤트 노트를 여기에 작성하세요.\n", dry_run)


# =========================
# 나무 '종합거래내역(상세)'(.xls HTML) 전용 파서
# =========================
def is_namoo_detail_table(df: pd.DataFrame) -> bool:
    if df is None or df.empty:
        return False
    if not isinstance(df.columns, pd.MultiIndex):
        return False

    # 1) 첫 번째 레벨에 '실거래일자/거래유형/상세내용'이 있는지
    lvl0 = [to_str(c[0]) for c in df.columns]
    need = ["실거래일자", "거래유형", "상세내용"]
    if not all(any(n in h for h in lvl0) for n in need):
        return False

    # 2) ('수량','단가') 구조가 있는지
    for c in df.columns:
        if "수량" in to_str(c[0]) and "단가" in to_str(c[1]):
            return True
    return False


def extract_code_and_name(name_field: str) -> Tuple[str, str]:
    """종목명 셀에서 코드(표준코드/종목코드 등)와 이름 분리"""
    s = re.sub(r"\s+", " ", to_str(name_field)).strip()
    if not s or s.lower() in ("nan", "-"):
        return "", ""

    # 1) ISIN(12) like "US46092D1037"
    m = re.search(r"\b([A-Z]{2}[A-Z0-9]{10})\b", s)
    if m:
        code = m.group(1)
        name = re.sub(r"\b" + re.escape(code) + r"\b", "", s).strip(" -")
        return code, name

    # 2) Korean 6-digit code
    m = re.search(r"\b(\d{6})\b", s)
    if m:
        code = m.group(1)
        name = re.sub(r"\b" + re.escape(code) + r"\b", "", s).strip(" -")
        return code, name

    # 3) Fallback: name only → pseudo code
    pseudo = "NAME_" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]
    return pseudo, s


def infer_currency(detail: str, code: str) -> str:
    d = to_str(detail)
    c = to_str(code).upper()

    if "외화" in d:
        return "USD"
    if c.startswith("US"):
        return "USD"
    if re.fullmatch(r"\d{6}", c):
        return "KRW"
    return "KRW"


def find_mi_col(df: pd.DataFrame, top_contains: str, bottom_contains: Optional[str] = None) -> Optional[Tuple[Any, Any]]:
    """MultiIndex 컬럼에서 (top,bottom) 매칭"""
    for col in df.columns:
        top = to_str(col[0])
        bot = to_str(col[1])
        if top_contains in top:
            if bottom_contains is None or bottom_contains in bot:
                return col
    return None


def parse_namoo_detail_table(df: pd.DataFrame, source_file: str, sheet: str, account_hint: str) -> List[LedgerRow]:
    rows: List[LedgerRow] = []
    if df is None or df.empty:
        return rows

    # 컬럼 찾기
    col_date = find_mi_col(df, "실거래일자")
    col_kind = find_mi_col(df, "거래유형")
    col_detail = find_mi_col(df, "상세내용")
    col_name = find_mi_col(df, "종목명")
    col_qty_price = find_mi_col(df, "수량", "단가")
    col_amt_settle = find_mi_col(df, "거래금액", "정산금액")
    col_fee_tax = find_mi_col(df, "수수료", "세금")
    col_memo = find_mi_col(df, "받는통장표시내용", "거래내역메모")

    n = len(df)
    if n == 0:
        return rows

    # 두 줄이 1건인 구조가 일반적. 혹시 홀수면 마지막은 단독 처리.
    step = 2

    for i in range(0, n, step):
        top = df.iloc[i]
        bottom = df.iloc[i + 1] if i + 1 < n else None

        date_raw = top.get(col_date) if col_date else None
        date = parse_date(date_raw)
        if not date:
            continue

        raw_kind = to_str(top.get(col_kind)) if col_kind else ""
        raw_detail = to_str(top.get(col_detail)) if col_detail else ""

        # 종목명/코드
        name_field = to_str(top.get(col_name)) if col_name else ""
        code, name = extract_code_and_name(name_field)
        ticker = pad_korean_ticker(code) if code else ""

        # 수량/단가/정산금액/수수료/세금
        qty = to_float(top.get(col_qty_price)) if col_qty_price else 0.0
        price = to_float(bottom.get(col_qty_price)) if (bottom is not None and col_qty_price) else 0.0

        # 금액은 '정산금액'이 더 일관적이어서 bottom 값을 우선
        amount = 0.0
        if col_amt_settle:
            if bottom is not None:
                amount = to_float(bottom.get(col_amt_settle))
            else:
                amount = to_float(top.get(col_amt_settle))

        fee = to_float(top.get(col_fee_tax)) if col_fee_tax else 0.0
        tax = to_float(bottom.get(col_fee_tax)) if (bottom is not None and col_fee_tax) else 0.0

        memo_text = ""
        if col_memo:
            # bottom이 거래내역메모에 해당
            memo_text = to_str(bottom.get(col_memo)) if bottom is not None else to_str(top.get(col_memo))

        # 분류
        cls_text = " ".join([raw_kind, raw_detail, name, ticker, memo_text]).strip()
        typ = classify(cls_text)

        currency = infer_currency(raw_detail, ticker)

        # 메모는 상세내용을 기본으로
        memo = raw_detail or raw_kind or memo_text
        raw_memo = " / ".join([t for t in [raw_detail, memo_text] if t]).strip()

        payload = {
            "date": date,
            "ticker": ticker,
            "type": typ,
            "qty": qty,
            "price": price,
            "amount": amount,
            "fee": fee,
            "tax": tax,
            "currency": currency,
            "raw_type": raw_kind,
            "raw_memo": raw_memo,
            "account": account_hint,
        }
        import_id = compute_import_id(payload)

        rows.append(
            LedgerRow(
                import_id=import_id,
                date=date,
                ticker=ticker,
                name=name,
                type=typ,
                qty=qty,
                price=price,
                amount=amount,
                fee=fee,
                tax=tax,
                currency=currency,
                strategy="",
                account=account_hint,
                memo=memo,
                source_file=source_file,
                sheet=sheet,
                raw_type=raw_kind,
                raw_memo=raw_memo,
            )
        )

    return rows


# =========================
# Generic 엑셀 파서(.xlsx 등)
# =========================
def parse_generic_sheet(df: pd.DataFrame, source_file: str, sheet: str, account_hint: str) -> List[LedgerRow]:
    rows: List[LedgerRow] = []
    if df is None or df.empty:
        return rows

    columns = [str(c).strip() for c in df.columns.tolist()]

    col_date = find_best_column(columns, "date")
    col_ticker = find_best_column(columns, "ticker")
    col_name = find_best_column(columns, "name")
    col_type = find_best_column(columns, "type")
    col_qty = find_best_column(columns, "qty")
    col_price = find_best_column(columns, "price")
    col_amount = find_best_column(columns, "amount")
    col_fee = find_best_column(columns, "fee")
    col_tax = find_best_column(columns, "tax")
    col_currency = find_best_column(columns, "currency")
    col_memo = find_best_column(columns, "memo")

    for _, r in df.iterrows():
        date = parse_date(r.get(col_date) if col_date else None)
        if not date:
            continue

        raw_ticker = to_str(r.get(col_ticker)) if col_ticker else ""
        ticker = pad_korean_ticker(raw_ticker) if raw_ticker else ""

        name = to_str(r.get(col_name)) if col_name else ""
        raw_type = to_str(r.get(col_type)) if col_type else ""
        raw_memo = to_str(r.get(col_memo)) if col_memo else ""

        cls_text = " ".join([raw_type, raw_memo, name, ticker]).strip()
        typ = classify(cls_text)

        qty = to_float(r.get(col_qty)) if col_qty else 0.0
        price = to_float(r.get(col_price)) if col_price else 0.0
        amount = to_float(r.get(col_amount)) if col_amount else 0.0
        fee = to_float(r.get(col_fee)) if col_fee else 0.0
        tax = to_float(r.get(col_tax)) if col_tax else 0.0

        currency = to_str(r.get(col_currency)) if col_currency else ""
        currency = currency.upper() if currency else "KRW"

        memo = raw_memo or raw_type

        payload = {
            "date": date,
            "ticker": ticker,
            "type": typ,
            "qty": qty,
            "price": price,
            "amount": amount,
            "fee": fee,
            "tax": tax,
            "currency": currency,
            "raw_type": raw_type,
            "raw_memo": raw_memo,
            "account": account_hint,
        }
        import_id = compute_import_id(payload)

        rows.append(
            LedgerRow(
                import_id=import_id,
                date=date,
                ticker=ticker,
                name=name,
                type=typ,
                qty=qty,
                price=price,
                amount=amount,
                fee=fee,
                tax=tax,
                currency=currency,
                strategy="",
                account=account_hint,
                memo=memo,
                source_file=source_file,
                sheet=sheet,
                raw_type=raw_type,
                raw_memo=raw_memo,
            )
        )

    return rows


def parse_sheet(df: pd.DataFrame, source_file: str, sheet: str, account_hint: str) -> List[LedgerRow]:
    # 나무 '종합거래내역(상세)' HTML 테이블이면 전용 파서
    if is_namoo_detail_table(df):
        return parse_namoo_detail_table(df, source_file, sheet, account_hint)

    # 그 외 일반 엑셀
    return parse_generic_sheet(df, source_file, sheet, account_hint)


# =========================
# Ledger / I/O
# =========================
def read_existing_import_ids(ledger_path: Path) -> set:
    if not ledger_path.exists():
        return set()
    try:
        df = pd.read_csv(ledger_path, dtype=str)
        return set(df.get("import_id", pd.Series(dtype=str)).dropna().astype(str).tolist())
    except Exception:
        return set()


def append_ledger(ledger_path: Path, new_rows: List[LedgerRow], dry_run: bool) -> None:
    ensure_dir(ledger_path.parent, dry_run)
    if dry_run:
        return

    cols = list(LedgerRow.__annotations__.keys())
    exists = ledger_path.exists()

    with ledger_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        if not exists:
            writer.writeheader()
        for row in new_rows:
            writer.writerow(row.__dict__)


def write_unclassified_csv(path: Path, rows: List[LedgerRow], dry_run: bool) -> None:
    if not rows:
        return
    ensure_dir(path.parent, dry_run)
    if dry_run:
        return

    df = pd.DataFrame([r.to_dict() for r in rows])
    df.to_csv(path, index=False, encoding="utf-8-sig")


# =========================
# 메인
# =========================
def main() -> None:
    parser = argparse.ArgumentParser(description="나무 다운로드(.xls/.xlsx) -> 옵시디언 노트/원장 생성")
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR), help="원본 파일 폴더 (기본: 70_Imports/raw)")
    parser.add_argument("--processed-dir", default=str(DEFAULT_PROCESSED_DIR), help="정규화 출력 폴더 (기본: 70_Imports/processed)")
    parser.add_argument("--review-dir", default=str(DEFAULT_REVIEW_DIR), help="분류 실패 노트 폴더 (기본: 70_Imports/review)")
    parser.add_argument("--dry-run", action="store_true", help="파일을 생성하지 않고 로그만 출력")
    parser.add_argument("--create-companies", action="store_true", help="새 티커가 나오면 기업 폴더를 자동 생성")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    processed_dir = Path(args.processed_dir)
    review_dir = Path(args.review_dir)

    ledger_path = processed_dir / LEDGER_FILENAME
    unclassified_path = processed_dir / UNCLASSIFIED_FILENAME

    if not raw_dir.exists():
        print(f"[오류] raw 폴더가 없습니다: {raw_dir}")
        return

    # 파일명 규칙 강제 없음: .xls/.xlsx 모두 처리
    patterns = ["*.xlsx", "*.xls"]
    excel_files: List[Path] = []
    for pat in patterns:
        excel_files.extend([p for p in raw_dir.glob(pat) if not p.name.startswith("~$")])
    excel_files = sorted(set(excel_files), key=lambda p: p.name)

    if not excel_files:
        print(f"[안내] 처리할 xls/xlsx 파일이 없습니다. {raw_dir}에 파일을 넣어주세요.")
        return

    existing_ids = read_existing_import_ids(ledger_path)
    print(f"[정보] 기존 ledger import_id 수: {len(existing_ids)}")

    created_trade_notes = 0
    created_cash_notes = 0
    created_review_notes = 0
    new_ledger_rows: List[LedgerRow] = []
    unclassified_rows: List[LedgerRow] = []

    for xf in excel_files:
        account_hint = infer_account_from_filename(xf.name)
        print(f"\n[처리] {xf.name}  (account hint: '{account_hint}')")

        try:
            sheets = load_excel(xf)
        except Exception as e:
            print(f"  - [실패] 파일 읽기 오류: {e}")
            continue

        if not sheets:
            print("  - [스킵] 테이블/시트를 찾지 못했습니다.")
            continue

        for sheet_name, df in sheets.items():
            rows = parse_sheet(df, source_file=xf.name, sheet=str(sheet_name), account_hint=account_hint)
            if not rows:
                continue

            new_in_this_sheet = 0

            for row in rows:
                # import_id 기반 중복 제거
                if row.import_id in existing_ids:
                    continue

                new_in_this_sheet += 1

                # 회사 폴더 자동 생성
                if args.create_companies and row.ticker:
                    ensure_company_folder(row.ticker, args.dry_run)

                # 분류별 파일 생성
                if row.type in ("BUY", "SELL", "DIV") and row.ticker:
                    ticker_folder = DEFAULT_TRADES_DIR / safe_path_component(row.ticker)
                    ensure_dir(ticker_folder, args.dry_run)

                    fname = f"{row.date}_{row.type}_{row.import_id[:8]}.md"
                    note_path = ticker_folder / fname
                    if not note_path.exists():
                        write_text(note_path, make_trade_note(row), args.dry_run)
                        created_trade_notes += 1

                    new_ledger_rows.append(row)
                    existing_ids.add(row.import_id)

                elif row.type in ("CASH_IN", "CASH_OUT"):
                    ensure_dir(DEFAULT_CASHFLOWS_DIR, args.dry_run)

                    fname = f"{row.date}_{row.type}_{row.import_id[:8]}.md"
                    note_path = DEFAULT_CASHFLOWS_DIR / fname
                    if not note_path.exists():
                        write_text(note_path, make_cashflow_note(row), args.dry_run)
                        created_cash_notes += 1

                    new_ledger_rows.append(row)
                    existing_ids.add(row.import_id)

                else:
                    # OTHER/FX/INTEREST 등은 review로 보관
                    ensure_dir(review_dir, args.dry_run)

                    fname = f"UNCLASSIFIED_{row.date}_{row.import_id[:8]}.md"
                    note_path = review_dir / fname
                    if not note_path.exists():
                        write_text(note_path, make_unclassified_note(row), args.dry_run)
                        created_review_notes += 1

                    unclassified_rows.append(row)
                    new_ledger_rows.append(row)
                    existing_ids.add(row.import_id)

            print(f"  - 시트 '{sheet_name}': 신규 {new_in_this_sheet}행")

    # ledger append
    if new_ledger_rows:
        append_ledger(ledger_path, new_ledger_rows, args.dry_run)
        write_unclassified_csv(unclassified_path, unclassified_rows, args.dry_run)

    print("\n[완료]")
    print(f"- 신규 ledger 행: {len(new_ledger_rows)}")
    print(f"- 생성된 거래 노트: {created_trade_notes}")
    print(f"- 생성된 입출금 노트: {created_cash_notes}")
    print(f"- 생성된 review 노트: {created_review_notes}")
    if args.dry_run:
        print("  (dry-run 모드: 파일이 실제로 생성되지 않았습니다.)")
    else:
        print(f"- ledger.csv: {ledger_path}")
        if unclassified_rows:
            print(f"- unclassified.csv: {unclassified_path}")
        print("- Obsidian에서 대시보드를 열어 확인하세요: 10_Dashboard/Start_Here.md")


if __name__ == "__main__":
    main()
