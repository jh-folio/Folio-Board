"""Portfolio management, analytics, and backtesting service."""
import datetime as dt
import hashlib
import json
import os
import re
import threading
import urllib.parse
import urllib.request
import math
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import HTTPException

from features.common.dataframe_ops import aggregate_portfolio
from features.common.instruments.registry import exchange_suffix, infer_market, quote_currency, suffix_currency
from features.common.markets import MarketCode
from features.common.utils import now_iso, kst_date, read_json, write_json
from features.portfolio.schema import expected_revision as parse_expected_revision, portfolio_document, revision
from features.portfolio.decimal_values import (
    DecimalValueError,
    canonical_average_price,
    canonical_decimal,
    canonical_quantity,
    finite_difference,
    finite_float,
    finite_product,
    finite_ratio,
    finite_sum,
    parse_decimal,
)
from features.portfolio.backtest_analysis import (
    ANALYSIS_VERSION,
    RISK_FREE_RATE_ANNUAL,
    TRADING_DAYS_PER_YEAR,
    daily_returns as analysis_daily_returns,
    deterministic_interpretation,
    drawdown_analysis,
    portfolio_metrics as analysis_portfolio_metrics,
)
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = data_dir()
PORTFOLIO_PATH = DATA_DIR / "portfolio.json"
PORTFOLIO_PRESETS_PATH = DATA_DIR / "portfolio-presets.json"
PORTFOLIO_PRICE_CACHE_DIR = DATA_DIR / "portfolio-price-cache"
BACKTESTS_DIR = DATA_DIR / "portfolio-backtests"
BACKTEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_PORTFOLIO_WRITE_LOCK = threading.RLock()
_PORTFOLIO_PRESETS_WRITE_LOCK = threading.RLock()
_PRESET_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,15}$")
_PRESET_BASE_CURRENCIES = {"USD", "KRW"}
_PRESET_TOTAL_TOLERANCE = Decimal("0.000000001")


class PortfolioRevisionConflict(Exception):
    def __init__(self, latest: dict):
        super().__init__("portfolio_revision_conflict")
        self.latest = latest


class PortfolioValidationError(Exception):
    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__("portfolio_validation_failed")


class PresetRevisionConflict(Exception):
    """A preset was changed or removed after the caller last read it."""

    def __init__(self, latest: dict | None):
        super().__init__("preset_revision_conflict")
        self.latest = latest


class BacktestCalculationLimitError(Exception):
    """A finite user input produced an unrepresentable derived float value."""

    code = "backtest_calculation_limit"
    message = "입력 금액과 가격의 조합을 현재 계산 정밀도로 표현할 수 없습니다. 초기 금액 또는 기준을 조정해 다시 실행하세요."


def _raise_on_nonfinite_backtest_value(value):
    """Reject derived non-finite output without treating intentional nulls as zero."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BacktestCalculationLimitError()
        return
    if isinstance(value, dict):
        for item in value.values():
            _raise_on_nonfinite_backtest_value(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _raise_on_nonfinite_backtest_value(item)


def _backtest_analysis_call(callable_, *args, **kwargs):
    try:
        return callable_(*args, **kwargs)
    except BacktestCalculationLimitError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    except (ArithmeticError, OverflowError, ValueError) as exc:
        limit = BacktestCalculationLimitError()
        raise HTTPException(status_code=422, detail={"code": limit.code, "message": limit.message}) from exc


def portfolio_write_lock() -> threading.RLock:
    """Return the single in-process lock used by every Portfolio authority write.

    Broker imports share this lock with the manual save path so an
    ``expectedRevision`` check and its atomic replacement stay one operation.
    """
    return _PORTFOLIO_WRITE_LOCK


def portfolio_storage_path(data_dir: Path | None = None) -> Path:
    return (Path(data_dir) / "portfolio.json") if data_dir is not None else PORTFOLIO_PATH


def write_portfolio_authority(document: dict, *, data_dir: Path | None = None) -> dict:
    """Atomically persist an already validated v3 authority document.

    The caller owns :func:`portfolio_write_lock`; this intentionally does not
    normalize or resolve positions because that would alter a fingerprinted
    import target after it was previewed.
    """
    payload = portfolio_document(document)
    payload.pop("sourceSchemaVersion", None)
    write_json(portfolio_storage_path(data_dir), payload)
    return payload



def _float_value(value, default=0.0):
    try:
        if value in {None, ""}:
            return default
        parsed = float(str(value).replace(",", "").strip())
        return parsed if math.isfinite(parsed) else default
    except Exception:
        return default


def _coerce_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Symbol and market inference
# ---------------------------------------------------------------------------

# A trailing dot means one of two different things. ``BRK.B`` is a US share class,
# which Yahoo writes ``BRK-B``; ``7203.T`` is the Tokyo listing, which Yahoo writes
# with the dot intact. Rewriting the second like the first asks for ``7203-T``,
# which does not exist, and the lookup then falls through to a US/USD default — a
# Toyota holding priced as if it were American.
def portfolio_symbol(ticker: str, market: str = "") -> str:
    raw = str(ticker or "").strip().upper()
    market = str(market or "").strip().upper()
    if not raw:
        return ""
    if re.fullmatch(r"\d{6}", raw):
        return f"{raw}.KQ" if market == "KQ" else f"{raw}.KS"
    if exchange_suffix(raw):
        return raw
    return raw.replace(".", "-")


def portfolio_symbol_candidates(ticker: str, market: str = "") -> list:
    raw = str(ticker or "").strip().upper()
    market = str(market or "").strip().upper()
    if not raw:
        return []
    if re.fullmatch(r"\d{6}", raw):
        primary = f"{raw}.KQ" if market == "KQ" else f"{raw}.KS"
        candidates = [primary, f"{raw}.KS", f"{raw}.KQ"]
    elif exchange_suffix(raw):
        # ".L" and ".T" are also plausible US share classes, so keep the dash form
        # as a second try rather than deciding which reading is right up front.
        candidates = [raw, raw.replace(".", "-")]
    else:
        candidates = [raw.replace(".", "-")]
    seen = set()
    return [item for item in candidates if not (item in seen or seen.add(item))]


_EXCHANGE_MARKET_HINTS = (
    ("KR", ("KOREA", "KOSDAQ", "KSC", "KRX", "KOE")),
    ("US", ("NYSE", "NASDAQ", "NMS", "AMEX", "PCX", "NGM", "NCM", "BATS")),
    ("JP", ("JPX", "TOKYO", "TSE", "OSA")),
    ("EUROPE", ("LSE", "LON", "XETRA", "GER", "FRA", "AMS", "PAR", "MIL", "MCE", "EBS", "BRU", "LIS", "VIE", "STO", "CPH", "OSL", "HEL", "EURONEXT")),
)


def infer_portfolio_market(symbol: str, info=None) -> str:
    symbol = str(symbol or "").upper()
    exchange = str((info or {}).get("exchange") or (info or {}).get("fullExchangeName") or "").upper()
    if exchange:
        for market, hints in _EXCHANGE_MARKET_HINTS:
            if any(hint in exchange for hint in hints):
                return market
    inferred = infer_market(symbol)
    if inferred is not MarketCode.UNKNOWN:
        return inferred.value
    return "KR" if re.match(r"^\d{6}", symbol) else "US"


def fallback_currency(symbol: str) -> str:
    """Currency to assume when the provider did not report one.

    Falls back to USD only for symbols that actually look American. A Tokyo or
    London symbol gets its own currency instead of being valued as dollars.
    """
    return suffix_currency(symbol) or ("KRW" if re.match(r"^\d{6}", str(symbol or "")) else "USD")


ETF_SECTOR_MAP: dict[str, str] = {
    # 주식
    "SPY": "주식(ETF)", "IVV": "주식(ETF)", "VOO": "주식(ETF)", "VTI": "주식(ETF)", "SPYM": "주식(ETF)",
    "DIA": "주식(ETF)", "IWM": "주식(ETF)", "IWB": "주식(ETF)", "MDY": "주식(ETF)",
    "QQQ": "주식(ETF)", "QQQM": "주식(ETF)",
    "SOXX": "주식(ETF)", "SMH": "주식(ETF)", "FTEC": "주식(ETF)", "VGT": "주식(ETF)",
    "ARKK": "주식(ETF)", "ARKG": "주식(ETF)", "ARKW": "주식(ETF)",
    "442580": "주식(ETF)",  # PLUS Global HBM
    "XLK": "주식(ETF)", "XLF": "주식(ETF)", "XLE": "주식(ETF)", "XLV": "주식(ETF)",
    "XLI": "주식(ETF)", "XLY": "주식(ETF)", "XLP": "주식(ETF)",
    "XLU": "주식(ETF)", "XLC": "주식(ETF)", "XLB": "주식(ETF)",
    "EEM": "주식(ETF)", "VWO": "주식(ETF)", "EFA": "주식(ETF)", "VEA": "주식(ETF)",
    "EWJ": "주식(ETF)", "FXI": "주식(ETF)", "KWEB": "주식(ETF)", "EWY": "주식(ETF)", "EWG": "주식(ETF)",
    "VPL": "주식(ETF)",
    # 레버리지/인버스
    "TQQQ": "레버리지/인버스(ETF)", "SQQQ": "레버리지/인버스(ETF)",
    "UPRO": "레버리지/인버스(ETF)", "SPXS": "레버리지/인버스(ETF)",
    "SOXL": "레버리지/인버스(ETF)", "SOXS": "레버리지/인버스(ETF)",
    "LABU": "레버리지/인버스(ETF)", "FNGU": "레버리지/인버스(ETF)",
    "UCO": "레버리지/인버스(ETF)",
    # 채권
    "TLT": "채권(ETF)", "IEF": "채권(ETF)", "SHY": "채권(ETF)", "SGOV": "채권(ETF)",
    "BND": "채권(ETF)", "AGG": "채권(ETF)", "LQD": "채권(ETF)",
    "HYG": "채권(ETF)", "JNK": "채권(ETF)", "TIP": "채권(ETF)", "VTIP": "채권(ETF)",
    # 금/원자재
    "GLD": "금/원자재(ETF)", "IAU": "금/원자재(ETF)", "IAUM": "금/원자재(ETF)", "GDX": "금/원자재(ETF)",
    "SLV": "금/원자재(ETF)", "PPLT": "금/원자재(ETF)",
    "USO": "금/원자재(ETF)", "DBA": "금/원자재(ETF)", "DBB": "금/원자재(ETF)",
    # 배당
    "SCHD": "배당(ETF)", "VYM": "배당(ETF)", "DVY": "배당(ETF)",
    "JEPI": "배당(ETF)", "JEPQ": "배당(ETF)",
    "161510": "배당(ETF)",  # PLUS High Dividend ETF
    # 부동산
    "XLRE": "부동산(ETF)", "VNQ": "부동산(ETF)", "IYR": "부동산(ETF)",
    # 통화
    "UUP": "통화(ETF)",
}

_ETF_NAME_KEYWORDS: list[tuple[str, str]] = [
    # 배당
    ("Dividend", "배당(ETF)"), ("Income", "배당(ETF)"), ("배당", "배당(ETF)"), ("고배당", "배당(ETF)"),
    # 채권
    ("Treasury", "채권(ETF)"), ("Bond", "채권(ETF)"), ("Fixed Income", "채권(ETF)"),
    ("채권", "채권(ETF)"), ("국채", "채권(ETF)"),
    # 금/원자재
    ("Gold", "금/원자재(ETF)"), ("Silver", "금/원자재(ETF)"), ("Metal", "금/원자재(ETF)"),
    ("Commodity", "금/원자재(ETF)"), ("Oil", "금/원자재(ETF)"), ("Crude", "금/원자재(ETF)"),
    # 부동산
    ("Real Estate", "부동산(ETF)"), ("REIT", "부동산(ETF)"),
    # 레버리지/인버스
    ("Leveraged", "레버리지/인버스(ETF)"), ("Ultra", "레버리지/인버스(ETF)"),
    ("Inverse", "레버리지/인버스(ETF)"), ("Bear", "레버리지/인버스(ETF)"),
]


def _etf_sector(info: dict, symbol: str) -> str:
    """Return a broad sector label for ETFs; fall back to equity sector for stocks."""
    symbol_upper = str(symbol or "").upper().split(".")[0]
    # Check explicit map first — covers Korean numeric ETFs that yfinance may misclassify
    mapped = ETF_SECTOR_MAP.get(symbol_upper)
    if mapped:
        return mapped
    asset_class = infer_portfolio_asset_class(info, symbol)
    if asset_class == "ETF":
        fund_name = str(info.get("shortName") or info.get("longName") or "").strip()
        if fund_name:
            for kw, label in _ETF_NAME_KEYWORDS:
                if kw.lower() in fund_name.lower():
                    return label
        return "주식(ETF)"
    return str(info.get("sector") or "Unclassified")


def infer_portfolio_asset_class(info=None, symbol: str = "") -> str:
    info = info or {}
    quote_type = str(info.get("quoteType") or info.get("typeDisp") or "").upper()
    name = str(info.get("shortName") or info.get("longName") or "").upper()
    symbol = str(symbol or "").upper()
    if "ETF" in quote_type or "ETF" in name or "ETN" in name:
        return "ETF"
    if "MUTUAL" in quote_type or "FUND" in quote_type:
        return "Fund"
    if "CRYPTO" in quote_type or "-USD" in symbol:
        return "Crypto"
    if "FUTURE" in quote_type:
        return "Futures"
    if "INDEX" in quote_type:
        return "Index"
    if quote_type == "EQUITY" or symbol:
        return "Equity"
    return "Unknown"


def resolve_portfolio_ticker(ticker: str, market: str = "") -> dict:
    raw = str(ticker or "").strip().upper()
    if not raw:
        return {"ok": False, "ticker": "", "error": "missing ticker"}
    fallback_symbol = portfolio_symbol(raw, market)
    try:
        import yfinance as yf
        for symbol in portfolio_symbol_candidates(raw, market):
            stock = yf.Ticker(symbol)
            info = {}
            fast = {}
            try:
                fast = getattr(stock, "fast_info", {}) or {}
            except Exception:
                fast = {}
            try:
                info = stock.get_info() or {}
            except Exception:
                info = {}
            name = str(info.get("shortName") or info.get("longName") or info.get("displayName") or "").strip()
            currency, quote_scale = quote_currency(info.get("currency") or fallback_currency(symbol))
            price = None
            previous = None
            for field in ("last_price", "lastPrice", "currentPrice", "regularMarketPrice"):
                try:
                    value = getattr(fast, field) if hasattr(fast, field) else fast.get(field) if isinstance(fast, dict) else None
                except Exception:
                    value = None
                if value is None:
                    value = info.get(field)
                try:
                    if value is not None:
                        price = float(value)
                        break
                except Exception:
                    pass
            for field in ("previous_close", "previousClose", "regularMarketPreviousClose"):
                try:
                    value = getattr(fast, field) if hasattr(fast, field) else fast.get(field) if isinstance(fast, dict) else None
                except Exception:
                    value = None
                if value is None:
                    value = info.get(field)
                try:
                    if value is not None:
                        previous = float(value)
                        break
                except Exception:
                    pass
            if name or price is not None or info.get("quoteType"):
                return {
                    "ok": True,
                    "ticker": raw,
                    "symbol": symbol,
                    "name": name or raw,
                    "market": infer_portfolio_market(symbol, info),
                    "currency": currency,
                    "assetClass": infer_portfolio_asset_class(info, symbol),
                    "sector": _etf_sector(info, symbol),
                    "industry": str(info.get("industry") or ""),
                    "country": str(info.get("country") or ""),
                    "exchange": str(info.get("exchange") or info.get("fullExchangeName") or ""),
                    "quoteType": str(info.get("quoteType") or ""),
                    "price": price if price is None else price * quote_scale,
                    "previousClose": previous if previous is None else previous * quote_scale,
                }
    except Exception:
        return {
            "ok": False,
            "ticker": raw,
            "symbol": fallback_symbol,
            "name": raw,
            "market": "KR" if re.fullmatch(r"\d{6}", raw) else "US",
            "currency": fallback_currency(fallback_symbol),
            "assetClass": "Unknown",
            "sector": "Unclassified",
            "error": "quote_provider_unavailable",
        }
    return {
        "ok": False,
        "ticker": raw,
        "symbol": fallback_symbol,
        "name": raw,
        "market": "KR" if re.fullmatch(r"\d{6}", raw) else "US",
        "currency": fallback_currency(fallback_symbol),
        "assetClass": "Unknown",
        "sector": "Unclassified",
        "error": "no ticker match",
    }


def _portfolio_suggestion_from_quote(quote: dict, fallback_query: str = ""):
    quote = quote or {}
    symbol = str(quote.get("symbol") or quote.get("ticker") or "").strip().upper()
    if not symbol:
        return None
    name = str(
        quote.get("shortname") or quote.get("shortName") or quote.get("longname") or quote.get("longName") or quote.get("name") or symbol
    ).strip()
    info = {
        "quoteType": quote.get("quoteType") or quote.get("typeDisp") or "",
        "exchange": quote.get("exchange") or quote.get("exchDisp") or "",
        "fullExchangeName": quote.get("exchDisp") or quote.get("exchange") or "",
        "shortName": name,
        "currency": quote.get("currency") or fallback_currency(symbol),
        "sector": quote.get("sector") or "",
        "industry": quote.get("industry") or "",
    }
    return {
        "ok": True,
        "ticker": symbol.split(".")[0] if symbol.endswith((".KS", ".KQ")) else symbol.replace("-", "."),
        "symbol": symbol,
        "name": name or symbol,
        "market": infer_portfolio_market(symbol, info),
        "currency": str(info.get("currency") or "").upper() or fallback_currency(symbol),
        "assetClass": infer_portfolio_asset_class(info, symbol),
        "sector": str(info.get("sector") or "Unclassified"),
        "industry": str(info.get("industry") or ""),
        "exchange": str(info.get("exchange") or ""),
        "quoteType": str(info.get("quoteType") or ""),
    }


def search_portfolio_tickers(query: str, limit: int = 8) -> dict:
    raw = str(query or "").strip()
    if not raw:
        return {"ok": True, "query": "", "items": [], "errors": []}
    limit = max(1, min(int(limit or 8), 12))
    items = []
    seen = set()
    errors = []

    def add(item):
        if not item:
            return
        symbol = str(item.get("symbol") or item.get("ticker") or "").upper()
        if not symbol or symbol in seen:
            return
        seen.add(symbol)
        items.append(item)

    exact_lookup = bool(re.fullmatch(r"\d{6}", raw) or "." in raw or len(raw) >= 3)
    if exact_lookup:
        exact = resolve_portfolio_ticker(raw)
        if exact.get("ok"):
            add(exact)

    try:
        import yfinance as yf
        search_cls = getattr(yf, "Search", None)
        if search_cls:
            result = search_cls(raw, max_results=limit)
            for quote in (getattr(result, "quotes", None) or []):
                add(_portfolio_suggestion_from_quote(quote, raw))
    except Exception:
        errors.append("yfinance_search_failed")

    if len(items) < limit:
        params = urllib.parse.urlencode({
            "q": raw,
            "quotesCount": limit,
            "newsCount": 0,
            "enableFuzzyQuery": "true",
            "quotesQueryId": "tss_match_phrase_query",
        })
        for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
            try:
                url = f"https://{host}/v1/finance/search?{params}"
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
                    "Accept": "application/json,text/plain,*/*",
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                })
                with urllib.request.urlopen(req, timeout=6) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="ignore"))
                for quote in payload.get("quotes") or []:
                    add(_portfolio_suggestion_from_quote(quote, raw))
                if len(items) >= limit:
                    break
            except Exception:
                errors.append(f"{host}: search_failed")

    return {"ok": True, "query": raw, "items": items[:limit], "errors": errors[:3]}


# ---------------------------------------------------------------------------
# Portfolio CRUD
# ---------------------------------------------------------------------------

def _normalize_portfolio_position_v2(row, resolve: bool = False):
    row = row or {}
    ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
    quantity = _float_value(row.get("quantity"), 0.0)
    average_price = _float_value(row.get("averagePrice"), 0.0)
    target_weight = _coerce_float(row.get("targetWeight"))
    if target_weight is None:
        target_weight = _coerce_float(row.get("targetWeightPct"))
        if target_weight is not None:
            target_weight = target_weight / 100.0
    if target_weight is not None and target_weight > 1:
        target_weight = target_weight / 100.0
    if target_weight is not None:
        target_weight = max(0.0, min(1.0, target_weight))
    resolved = row.get("resolved") if isinstance(row.get("resolved"), dict) else {}
    if resolve and ticker:
        resolved = resolve_portfolio_ticker(ticker, row.get("market") or resolved.get("market") or "")
    name = str(row.get("name") or resolved.get("name") or ticker).strip()
    symbol = str(row.get("symbol") or resolved.get("symbol") or portfolio_symbol(ticker, resolved.get("market", ""))).strip().upper()
    market = str(row.get("market") or resolved.get("market") or infer_portfolio_market(symbol, resolved)).strip().upper()
    currency = str(row.get("currency") or resolved.get("currency") or ("KRW" if market == "KR" else "USD")).strip().upper()
    asset_class = str(row.get("assetClass") or resolved.get("assetClass") or infer_portfolio_asset_class(resolved, symbol)).strip()
    sector = str(row.get("sector") or resolved.get("sector") or "Unclassified").strip()
    normalized_resolved = {
        "ok": bool(resolved.get("ok")),
        "ticker": ticker,
        "symbol": symbol,
        "name": name or ticker,
        "market": market,
        "currency": currency,
        "assetClass": asset_class or "Unknown",
        "sector": sector or "Unclassified",
        "industry": str(row.get("industry") or resolved.get("industry") or ""),
        "country": str(row.get("country") or resolved.get("country") or ""),
        "exchange": str(row.get("exchange") or resolved.get("exchange") or ""),
        "quoteType": str(row.get("quoteType") or resolved.get("quoteType") or ""),
    }
    return {
        "id": str(row.get("id") or hashlib.sha256(f"{ticker}:{quantity}:{average_price}".encode("utf-8")).hexdigest()[:12]),
        "ticker": ticker,
        "symbol": symbol,
        "name": name or ticker,
        "market": market,
        "quantity": quantity,
        "averagePrice": average_price,
        "targetWeight": target_weight,
        "currency": currency,
        "assetClass": normalized_resolved["assetClass"],
        "sector": normalized_resolved["sector"],
        "industry": normalized_resolved["industry"],
        "country": normalized_resolved["country"],
        "exchange": normalized_resolved["exchange"],
        "quoteType": normalized_resolved["quoteType"],
        "resolved": normalized_resolved,
    }


def normalize_portfolio_position(row, resolve: bool = False, *, source_schema_version: int = 3):
    """Project a position with v3 authority decimals while retaining v2 IDs.

    The legacy helper remains intentionally frozen for historical fallback IDs
    and v1 import recovery.  It may coerce values to floats, but only before we
    replace authority fields with their exact decimal strings.
    """
    row = row if isinstance(row, dict) else {}
    legacy = _normalize_portfolio_position_v2(row, resolve=resolve)
    try:
        quantity = canonical_decimal(row.get("quantity"))
    except DecimalValueError:
        quantity = canonical_decimal(legacy["quantity"])
    try:
        average_price = canonical_average_price(row.get("averagePrice"), blank_is_zero=True)
    except DecimalValueError:
        average_price = canonical_decimal(legacy["averagePrice"])
    if row.get("id"):
        position_id = str(row["id"])
    elif source_schema_version <= 2:
        # The old float string digest is a persistent identity contract.
        position_id = legacy["id"]
    else:
        position_id = hashlib.sha256(
            f"{legacy['ticker']}:{quantity}:{average_price}".encode("utf-8")
        ).hexdigest()[:12]
    return {**legacy, "id": position_id, "quantity": quantity, "averagePrice": average_price}


def _is_blank_position_draft(row: dict) -> bool:
    fields = ("id", "ticker", "symbol", "name", "quantity", "averagePrice", "market", "currency", "targetWeight", "targetWeightPct")
    return all(value is None or (isinstance(value, str) and not value.strip()) for value in (row.get(field) for field in fields))


def _strict_positions(value: object) -> list[dict]:
    if not isinstance(value, list):
        raise PortfolioValidationError([{"row": None, "field": "positions", "code": "invalid_positions"}])
    normalized: list[dict] = []
    errors: list[dict] = []
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            errors.append({"row": index, "field": "row", "code": "invalid_position"})
            continue
        if _is_blank_position_draft(row):
            continue
        ticker = str(row.get("ticker") or row.get("symbol") or "").strip()
        if not ticker:
            errors.append({"row": index, "field": "ticker", "code": "required"})
        try:
            quantity = canonical_quantity(row.get("quantity"))
        except DecimalValueError as exc:
            errors.append({"row": index, "field": "quantity", "code": exc.code})
            quantity = None
        try:
            average = canonical_average_price(row.get("averagePrice"), blank_is_zero=True)
        except DecimalValueError as exc:
            errors.append({"row": index, "field": "averagePrice", "code": exc.code})
            average = None
        if ticker and quantity is not None and average is not None:
            normalized.append(normalize_portfolio_position(
                {**row, "ticker": ticker, "quantity": quantity, "averagePrice": average},
                resolve=True,
            ))
    if errors:
        raise PortfolioValidationError(errors)
    return normalized


def get_portfolio(data_dir: Path | None = None):
    path = portfolio_storage_path(data_dir)
    data = read_json(path, {"positions": [], "cash": []})
    if isinstance(data, list):
        data = {"positions": data, "cash": []}
    data = portfolio_document(data)
    source_schema = data["sourceSchemaVersion"]
    if source_schema <= 2:
        positions = [normalize_portfolio_position(row, source_schema_version=source_schema) for row in data.get("positions", []) if isinstance(row, dict)]
    else:
        positions = [normalize_portfolio_position(row) for row in data.get("positions", []) if isinstance(row, dict)]
    cash = []
    for row in data.get("cash", []) if isinstance(data.get("cash", []), list) else []:
        currency = str((row or {}).get("currency") or "").strip().upper()
        amount = _float_value((row or {}).get("amount"), 0.0)
        if currency and amount:
            cash.append({"currency": currency, "amount": amount})
    return {"schemaVersion": 3, "sourceSchemaVersion": source_schema, "revision": data["revision"], "positions": positions, "cash": cash, "updatedAt": data["updatedAt"]}


def legacy_v1_raw_portfolio_view(data_dir: Path) -> dict | None:
    """Return the stored v1/v2 authority shape without coercing a v3 file."""
    raw = read_json(portfolio_storage_path(data_dir), {"positions": [], "cash": []})
    if isinstance(raw, list):
        raw = {"positions": raw, "cash": []}
    if not isinstance(raw, dict):
        return None
    try:
        raw_schema = int(raw.get("schemaVersion") or 1)
    except (TypeError, ValueError):
        return None
    if raw_schema > 2:
        return None
    return {
        "schemaVersion": 2,
        "revision": revision(raw.get("revision")),
        "positions": raw.get("positions") if isinstance(raw.get("positions"), list) else [],
        "cash": raw.get("cash") if isinstance(raw.get("cash"), list) else [],
        "updatedAt": str(raw.get("updatedAt") or ""),
    }


def legacy_v1_portfolio_view(data_dir: Path) -> dict | None:
    """Recreate the old GET projection only when its original v1/v2 bytes exist.

    This is intentionally a recovery-only helper.  A v3 file must never be
    lowered to floats merely to make a stale sidecar hash appear valid.
    """
    data = legacy_v1_raw_portfolio_view(data_dir)
    if data is None:
        return None
    positions = [_normalize_portfolio_position_v2(row) for row in data["positions"] if isinstance(row, dict)]
    cash = []
    for row in data["cash"]:
        currency = str((row or {}).get("currency") or "").strip().upper()
        amount = _float_value((row or {}).get("amount"), 0.0)
        if currency and amount:
            cash.append({"currency": currency, "amount": amount})
    return {"schemaVersion": 2, "revision": data["revision"], "positions": positions, "cash": cash, "updatedAt": data["updatedAt"]}


def save_portfolio(body, *, expected_revision: int | None = None, data_dir: Path | None = None):
    data = body if isinstance(body, dict) else {}
    path = portfolio_storage_path(data_dir)
    expected = parse_expected_revision(data) if expected_revision is None else max(0, int(expected_revision))
    positions = _strict_positions(data.get("positions", []))
    cash_provided = "cash" in data
    cash = []
    if cash_provided:
        for row in data.get("cash", []) if isinstance(data.get("cash", []), list) else []:
            currency = str((row or {}).get("currency") or "").strip().upper()
            amount = _float_value((row or {}).get("amount"), 0.0)
            if currency and amount:
                cash.append({"currency": currency, "amount": amount})
    with _PORTFOLIO_WRITE_LOCK:
        latest = get_portfolio(data_dir)
        if expected is not None and expected != latest["revision"]:
            raise PortfolioRevisionConflict(latest)
        if not cash_provided:
            cash = latest["cash"]
        payload = {"schemaVersion": 3, "revision": latest["revision"] + 1, "positions": positions, "cash": cash, "updatedAt": now_iso()}
        write_json(path, payload)
    return payload


# ---------------------------------------------------------------------------
# Price fetching
# ---------------------------------------------------------------------------

def _pick_quote_value(fast, info, *names):
    for name in names:
        value = None
        try:
            if hasattr(fast, name):
                value = getattr(fast, name)
            elif isinstance(fast, dict):
                value = fast.get(name)
        except Exception:
            value = None
        if value is None and isinstance(info, dict):
            value = info.get(name)
        number = _coerce_float(value)
        if number is not None:
            return number
    return None


def _quote_from_yahoo_chart(symbol: str):
    try:
        from urllib.request import Request, urlopen
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=10d&interval=1d"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = (((payload or {}).get("chart") or {}).get("result") or [None])[0] or {}
        meta = result.get("meta") or {}
        quote = (((result.get("indicators") or {}).get("quote") or [None])[0] or {})
        closes = [value for value in (quote.get("close") or []) if value is not None]
        price = _coerce_float(meta.get("regularMarketPrice")) or (_coerce_float(closes[-1]) if closes else None)
        previous = _coerce_float(meta.get("chartPreviousClose"))
        if previous is None and len(closes) >= 2:
            previous = _coerce_float(closes[-2])
        if price is None:
            return None
        currency, scale = quote_currency(meta.get("currency") or fallback_currency(symbol))
        return {
            "price": price * scale,
            "previousClose": previous if previous is None else previous * scale,
            "currency": currency,
            "exchange": str(meta.get("exchangeName") or ""),
        }
    except Exception:
        return None


def fetch_portfolio_quote(position):
    base_symbol = str(position.get("symbol") or portfolio_symbol(position.get("ticker", ""), position.get("market", ""))).strip().upper()
    candidates = []
    if base_symbol:
        candidates.append(base_symbol)
    candidates.extend(portfolio_symbol_candidates(position.get("ticker", ""), position.get("market", "")))
    seen = set()
    candidates = [item for item in candidates if item and not (item in seen or seen.add(item))]
    if not candidates:
        return {"ok": False, "symbol": "", "error": "missing ticker"}
    errors = []
    try:
        import yfinance as yf
    except Exception:
        yf = None
        errors.append("yfinance_unavailable")
    for symbol in candidates:
        info = {}
        price = None
        previous = None
        # `scale` converts a minor-unit quote (London pence) to its major unit. It is
        # applied once at the end so the history and chart fallbacks below, which read
        # the same pence figures, are covered too.
        currency, scale = quote_currency(position.get("currency") or fallback_currency(symbol))
        if yf:
            try:
                stock = yf.Ticker(symbol)
                try:
                    fast = getattr(stock, "fast_info", {}) or {}
                except Exception:
                    fast = {}
                try:
                    info = stock.get_info() or {}
                except Exception:
                    errors.append(f"{symbol} info_unavailable")
                    info = {}
                price = _pick_quote_value(
                    fast, info,
                    "last_price", "lastPrice", "currentPrice", "regularMarketPrice", "navPrice", "open", "previousClose",
                )
                previous = _pick_quote_value(fast, info, "previous_close", "previousClose", "regularMarketPreviousClose")
                currency, scale = quote_currency(info.get("currency") or currency)
                if price is None:
                    try:
                        hist = stock.history(period="1mo", interval="1d", auto_adjust=False, actions=False)
                        if not hist.empty:
                            close_col = "Close" if "Close" in hist else "Adj Close" if "Adj Close" in hist else None
                            if close_col:
                                closes = hist[close_col].dropna()
                                if len(closes):
                                    price = float(closes.iloc[-1])
                                    if previous is None and len(closes) >= 2:
                                        previous = float(closes.iloc[-2])
                    except Exception:
                        errors.append(f"{symbol} history_unavailable")
            except Exception:
                errors.append(f"{symbol}: quote_unavailable")
        if scale != 1.0:
            price = price if price is None else price * scale
            previous = previous if previous is None else previous * scale
        if price is None:
            # The chart helper already normalizes its own quote, so nothing to scale.
            chart = _quote_from_yahoo_chart(symbol)
            if chart:
                price = chart.get("price")
                previous = previous if previous is not None else chart.get("previousClose")
                currency = chart.get("currency") or currency
                if chart.get("exchange") and not info.get("exchange"):
                    info["exchange"] = chart.get("exchange")
        if price is None:
            continue
        return {
            "ok": True,
            "symbol": symbol,
            "price": price,
            "previousClose": previous,
            "currency": str(currency or "").upper(),
            "name": str(info.get("shortName") or info.get("longName") or position.get("name") or position.get("ticker") or ""),
            "market": infer_portfolio_market(symbol, info),
            "assetClass": infer_portfolio_asset_class(info or position.get("resolved") or {}, symbol),
            "sector": _etf_sector(info, symbol),
            "industry": str(info.get("industry") or position.get("industry") or ""),
        }
    return {"ok": False, "symbol": candidates[0], "error": "; ".join(errors[-3:]) or "no price data"}


def _portfolio_fx_to_usd(currency: str):
    currency = str(currency or "USD").upper()
    if currency == "USD":
        return 1.0, "USD"
    cache_path = DATA_DIR / "portfolio-fx-cache.json"
    cache = read_json(cache_path, {})
    today = kst_date()
    cached = cache.get(currency) if isinstance(cache, dict) else None
    if isinstance(cached, dict) and cached.get("date") == today and _coerce_float(cached.get("rateToUsd")):
        return float(cached["rateToUsd"]), cached.get("source", "cache")

    rate_to_usd = None
    source = ""
    if currency != "KRW":
        direct_symbol = f"{currency}USD=X"
        direct = _quote_from_yahoo_chart(direct_symbol)
        if direct and _coerce_float(direct.get("price")):
            rate_to_usd = float(direct["price"])
            source = direct_symbol
    if rate_to_usd is None:
        inverse_symbol = "KRW=X" if currency == "KRW" else f"{currency}=X"
        inverse = _quote_from_yahoo_chart(inverse_symbol)
        inverse_price = _coerce_float((inverse or {}).get("price"))
        if inverse_price:
            rate_to_usd = 1.0 / inverse_price
            source = inverse_symbol
    if rate_to_usd:
        cache[currency] = {"date": today, "rateToUsd": rate_to_usd, "source": source, "updatedAt": now_iso()}
        write_json(cache_path, cache)
        return rate_to_usd, source
    return None, "unavailable"


def _portfolio_group(rows, key, value_key="marketValueUsd", cost_key="costUsd", pnl_key="pnlUsd"):
    groups = {}
    total = finite_sum(row.get(value_key) for row in rows if row.get(value_key) is not None)
    for row in rows:
        value = _float_value(row.get(value_key), 0.0)
        if value <= 0:
            continue
        label = str(row.get(key) or "Unclassified").strip() or "Unclassified"
        item = groups.setdefault(label, {"label": label, "marketValues": [], "costs": [], "pnls": [], "positions": 0, "baseCurrency": "USD"})
        item["marketValues"].append(value)
        if row.get(cost_key) is not None:
            item["costs"].append(row.get(cost_key))
        if row.get(pnl_key) is not None:
            item["pnls"].append(row.get(pnl_key))
        item["positions"] += 1
    output = []
    for item in groups.values():
        market_value = finite_sum(item.pop("marketValues"))
        cost = finite_sum(item.pop("costs"))
        pnl = finite_sum(item.pop("pnls"))
        unavailable: list[str] = []
        if market_value is None or total is None:
            unavailable.append("market_value_total_unavailable")
        if cost is None:
            unavailable.append("cost_total_unavailable")
        if pnl is None:
            unavailable.append("pnl_total_unavailable")
        weight = finite_ratio(market_value, total)
        pnl_pct = finite_ratio(pnl, cost)
        if market_value is not None and total not in (None, 0.0) and weight is None:
            unavailable.append("weight_unavailable")
        if pnl is not None and cost not in (None, 0.0) and pnl_pct is None:
            unavailable.append("pnl_pct_unavailable")
        output.append({**item, "marketValue": market_value, "cost": cost, "pnl": pnl, "weight": weight, "pnlPct": pnl_pct, "calculationUnavailable": unavailable})
    return sorted(output, key=lambda item: item.get("marketValue") or 0, reverse=True)


def portfolio_summary():
    portfolio = get_portfolio()
    rows = []
    fx_rates = {}
    for position in portfolio["positions"]:
        quote = fetch_portfolio_quote(position)
        quantity = finite_float(position.get("quantity"))
        average_price = position.get("averagePrice")
        try:
            average_price_is_zero = parse_decimal(average_price).is_zero()
        except DecimalValueError:
            average_price_is_zero = None
        price = quote.get("price") if quote.get("ok") else None
        currency = str(quote.get("currency") or position.get("currency") or "USD").upper()
        unavailable: list[str] = []
        market_value = finite_product(position.get("quantity"), price) if price is not None else None
        if price is not None and market_value is None:
            unavailable.append("market_value_unavailable")
        # Multiply the two authority strings before any float projection.  An
        # individually unrepresentable average price may still yield a wholly
        # representable exact cost (for example 1e-300 × 1e400 = 1e100).
        cost = finite_product(position.get("quantity"), average_price) if average_price_is_zero is False else None
        if average_price_is_zero is not True and cost is None:
            unavailable.append("cost_unavailable")
        pnl = finite_difference(market_value, cost) if market_value is not None and cost is not None else None
        if market_value is not None and cost is not None and pnl is None:
            unavailable.append("pnl_unavailable")
        pnl_pct = finite_ratio(pnl, cost) if pnl is not None and cost not in (None, 0.0) else None
        if pnl is not None and cost not in (None, 0.0) and pnl_pct is None:
            unavailable.append("pnl_pct_unavailable")
        day_change = None
        if quote.get("previousClose") and price is not None and quantity is not None:
            day_change = finite_product(finite_difference(price, quote["previousClose"]), position.get("quantity"))
            if day_change is None:
                unavailable.append("day_change_unavailable")
        fx_rate, fx_source = fx_rates.get(currency, (None, ""))
        if currency not in fx_rates:
            fx_rate, fx_source = _portfolio_fx_to_usd(currency)
            fx_rates[currency] = (fx_rate, fx_source)
        market_value_usd = finite_product(market_value, fx_rate) if market_value is not None and fx_rate else None
        cost_usd = finite_product(cost, fx_rate) if cost is not None and fx_rate else None
        pnl_usd = finite_product(pnl, fx_rate) if pnl is not None and fx_rate else None
        day_change_usd = finite_product(day_change, fx_rate) if day_change is not None and fx_rate else None
        if fx_rate and ((market_value is not None and market_value_usd is None) or (cost is not None and cost_usd is None) or (pnl is not None and pnl_usd is None)):
            unavailable.append("usd_conversion_unavailable")
        rows.append({
            **position,
            "name": quote.get("name") or position.get("name") or position.get("ticker"),
            "symbol": quote.get("symbol") or position.get("symbol") or position.get("ticker"),
            "market": quote.get("market") or position.get("market"),
            "assetClass": quote.get("assetClass") or position.get("assetClass") or "Unknown",
            "sector": quote.get("sector") or ETF_SECTOR_MAP.get(str(position.get("ticker") or "").upper().split(".")[0]) or position.get("sector") or "Unclassified",
            "industry": quote.get("industry") or position.get("industry") or "",
            "quoteOk": bool(quote.get("ok")),
            "quoteError": quote.get("error", ""),
            "currentPrice": price,
            "marketValue": market_value,
            "cost": cost,
            "pnl": pnl,
            "pnlPct": pnl_pct,
            "dayChange": day_change,
            "quoteCurrency": currency,
            "fxToUsd": fx_rate,
            "fxSource": fx_source,
            "marketValueUsd": market_value_usd,
            "costUsd": cost_usd,
            "pnlUsd": pnl_usd,
            "dayChangeUsd": day_change_usd,
            "calculationUnavailable": unavailable,
        })
    aggregated = aggregate_portfolio(rows)
    market_values = [row.get("marketValueUsd") for row in aggregated["rows"] if row.get("marketValueUsd") is not None]
    cost_values = [row.get("costUsd") for row in aggregated["rows"] if row.get("costUsd") is not None]
    pnl_values = [row.get("pnlUsd") for row in aggregated["rows"] if row.get("pnlUsd") is not None]
    def has_reason(row, codes):
        return any(code in codes for code in row.get("calculationUnavailable", []))
    market_total_incomplete = any(has_reason(row, {"market_value_unavailable", "usd_conversion_unavailable"}) for row in aggregated["rows"])
    cost_total_incomplete = any(has_reason(row, {"cost_unavailable", "usd_conversion_unavailable"}) for row in aggregated["rows"])
    total_usd = None if market_total_incomplete else finite_sum(market_values)
    cost_usd = None if cost_total_incomplete else finite_sum(cost_values)
    pnl_total_incomplete = total_usd is None or cost_usd is None or any(has_reason(row, {"pnl_unavailable"}) for row in aggregated["rows"])
    pnl_usd = None if pnl_total_incomplete else finite_sum(pnl_values)
    for row in aggregated["rows"]:
        if row.get("marketValueUsd") is not None and total_usd is None:
            reasons = row.setdefault("calculationUnavailable", [])
            if "portfolio_total_unavailable" not in reasons:
                reasons.append("portfolio_total_unavailable")
        row["weight"] = finite_ratio(row.get("marketValueUsd"), total_usd) if total_usd not in (None, 0.0) and row.get("marketValueUsd") is not None else None
        if row.get("marketValueUsd") is not None and total_usd not in (None, 0.0) and row["weight"] is None:
            reasons = row.setdefault("calculationUnavailable", [])
            if "weight_unavailable" not in reasons:
                reasons.append("weight_unavailable")
    summary_unavailable: list[str] = []
    if total_usd is None:
        summary_unavailable.append("market_value_total_unavailable")
    if cost_usd is None:
        summary_unavailable.append("cost_total_unavailable")
    if pnl_usd is None:
        summary_unavailable.append("pnl_total_unavailable")
    pnl_pct_usd = finite_ratio(pnl_usd, cost_usd) if pnl_usd is not None and cost_usd not in (None, 0.0) else None
    if pnl_usd is not None and cost_usd not in (None, 0.0) and pnl_pct_usd is None:
        summary_unavailable.append("pnl_pct_unavailable")
    base_summary = {
        "currency": "USD 기준",
        "marketValue": total_usd,
        "cost": cost_usd,
        "pnl": pnl_usd,
        "pnlPct": pnl_pct_usd,
        "positions": len([row for row in aggregated["rows"] if row.get("marketValueUsd") is not None]),
        "baseCurrency": "USD",
        "calculationUnavailable": summary_unavailable,
    }
    return {
        "positions": aggregated["rows"],
        "summary": [base_summary] + aggregated["summary"],
        "cash": portfolio["cash"],
        "updatedAt": now_iso(),
        "baseCurrency": "USD",
        "fxRates": {key: {"rateToUsd": value[0], "source": value[1]} for key, value in fx_rates.items()},
    }


def _portfolio_target_analysis(rows, total_value):
    items = []
    target_total = 0.0
    has_targets = False
    for row in rows:
        raw_current = row.get("weight")
        current = None if total_value is None else _coerce_float(raw_current)
        raw_target = row.get("targetWeight")
        target = _coerce_float(raw_target)
        if target is None:
            target = 0.0
        else:
            has_targets = True
        target_total += target
        diff = (current - target) if current is not None else None
        items.append({
            "id": row.get("id"),
            "ticker": row.get("ticker"),
            "symbol": row.get("symbol"),
            "name": row.get("name") or row.get("ticker"),
            "currentWeight": current,
            "targetWeight": target,
            "diffWeight": diff,
            "diffAmountUsd": finite_product(diff, total_value) if diff is not None and total_value not in (None, 0.0) else None,
            "marketValueUsd": row.get("marketValueUsd"),
        })
    return {
        "items": sorted(items, key=lambda item: abs(item.get("diffWeight") or 0), reverse=True),
        "targetTotal": target_total,
        "targetGap": 1.0 - target_total,
        "hasTargets": has_targets,
    }


def _apply_preset_targets(rows, preset_id):
    """저장한 목표 프리셋의 비중을 각 포지션의 목표로 얹는다.

    프리셋과 포지션의 `targetWeight`는 서로 모르는 두 개념이었다. 프리셋을 아무리
    만들어도 `hasTargets`가 False라 목표와의 차이 표가 **한 번도 뜨지 않았고**,
    포지션 목표를 넣을 칸은 화면에 없다. 사용자에게 목표란 저장해 둔 프리셋이므로,
    어느 프리셋과 비교할지 골라 받는다.

    프리셋에만 있고 지금 안 들고 있는 종목도 한 줄로 낸다 — "목표에는 있는데 아직
    안 샀다"가 조정에서 가장 중요한 정보다.
    """
    preset = get_portfolio_preset(str(preset_id or "")) or {}
    weights = {}
    for row in preset.get("positions", []):
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker:
            weights[ticker] = _float_value(row.get("weight"), 0.0)
    if not weights:
        return rows, preset

    merged = []
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        merged.append({**row, "targetWeight": weights.pop(ticker, 0.0)})
    for ticker, weight in weights.items():
        merged.append({"ticker": ticker, "name": ticker, "weight": 0.0, "marketValueUsd": 0.0, "targetWeight": weight})
    return merged, preset


def portfolio_analytics(preset_id: str = ""):
    base = portfolio_summary()
    rows = base.get("positions", [])
    valid = [row for row in rows if _float_value(row.get("marketValueUsd"), 0.0) > 0]
    base_reasons = set((base.get("summary") or [{}])[0].get("calculationUnavailable") or [])
    market_total_incomplete = "market_value_total_unavailable" in base_reasons
    cost_total_incomplete = "cost_total_unavailable" in base_reasons
    pnl_total_incomplete = "pnl_total_unavailable" in base_reasons
    total_value = None if market_total_incomplete else finite_sum(row.get("marketValueUsd") for row in valid)
    total_cost = None if cost_total_incomplete else finite_sum(row.get("costUsd") for row in valid)
    total_pnl = None if pnl_total_incomplete else finite_sum(row.get("pnlUsd") for row in valid)
    ranked = sorted(valid, key=lambda row: _float_value(row.get("marketValueUsd"), 0.0), reverse=True)
    pnl_ranked = sorted(valid, key=lambda row: abs(_float_value(row.get("pnlUsd"), 0.0)), reverse=True)
    top1 = finite_ratio(ranked[0].get("marketValueUsd"), total_value) if ranked else None
    top3 = finite_ratio(finite_sum(row.get("marketValueUsd") for row in ranked[:3]), total_value)
    top5 = finite_ratio(finite_sum(row.get("marketValueUsd") for row in ranked[:5]), total_value)
    sector_weights = _portfolio_group(valid, "sector")
    market_weights = _portfolio_group(valid, "market")
    currency_weights = _portfolio_group(valid, "quoteCurrency")
    asset_weights = _portfolio_group(valid, "assetClass")
    def mask_incomplete_groups(groups):
        for group in groups:
            unavailable = group.setdefault("calculationUnavailable", [])
            if market_total_incomplete:
                group["marketValue"] = None
                group["weight"] = None
                if "market_value_total_unavailable" not in unavailable:
                    unavailable.append("market_value_total_unavailable")
            if cost_total_incomplete:
                group["cost"] = None
                if "cost_total_unavailable" not in unavailable:
                    unavailable.append("cost_total_unavailable")
            if pnl_total_incomplete:
                group["pnl"] = None
                group["pnlPct"] = None
                if "pnl_total_unavailable" not in unavailable:
                    unavailable.append("pnl_total_unavailable")
    for groups in (sector_weights, market_weights, currency_weights, asset_weights):
        mask_incomplete_groups(groups)
    # With an arithmetic-incomplete USD total, keep every authority position
    # in the comparison.  Passing only ``ranked`` would recreate the omitted
    # holding as a fake 0%-weight "not held" row.
    target_rows, target_preset = _apply_preset_targets(rows if total_value is None else ranked, preset_id)
    target_analysis = _portfolio_target_analysis(target_rows, total_value)
    target_analysis["presetId"] = str(target_preset.get("id") or "")
    target_analysis["presetName"] = str(target_preset.get("name") or "")
    comments = []
    if not valid:
        comments.append({"level": "info", "title": "평가 가능한 포지션 없음", "body": "티커, 수량, 평균단가를 입력하고 저장/평가를 누르면 현재 포트폴리오 분석이 생성됩니다."})
    else:
        total_pnl_pct = finite_ratio(total_pnl, total_cost)
        if total_pnl is None or total_cost is None or (total_cost not in (None, 0.0) and total_pnl_pct is None):
            comments.append({"level": "info", "title": "USD 기준 총 평가손익", "body": "합계 또는 수익률이 표시 가능한 숫자 범위를 벗어났습니다. 포지션별 계산 불가 사유를 확인하세요."})
        else:
            comments.append({"level": "info", "title": "USD 기준 총 평가손익", "body": f"평가 가능한 {len(valid)}개 포지션 기준 총 손익은 USD {total_pnl:,.0f}이며, 원금 대비 수익률은 {(total_pnl_pct or 0) * 100:.1f}%입니다. 비중과 차트는 원화/달러 자산을 모두 USD로 환산해 계산합니다."})
        if top1 is not None and top1 >= 0.35:
            comments.append({"level": "warn", "title": "단일 종목 집중", "body": f"가장 큰 포지션인 {ranked[0].get('name') or ranked[0].get('ticker')} 비중이 USD 환산 기준 {top1 * 100:.1f}%입니다. 단일 이벤트가 포트폴리오 손익을 크게 좌우할 수 있습니다."})
        if top3 is not None and top3 >= 0.65:
            comments.append({"level": "warn", "title": "상위 종목 집중", "body": f"상위 3개 포지션 비중이 USD 환산 기준 {top3 * 100:.1f}%입니다. 의도한 집중투자인지, 리스크 분산이 필요한지 확인할 구간입니다."})
        if sector_weights and sector_weights[0].get("weight") is not None and sector_weights[0]["weight"] >= 0.45:
            comments.append({"level": "warn", "title": "섹터 편중", "body": f"{sector_weights[0]['label']} 섹터가 USD 환산 기준 {sector_weights[0]['weight'] * 100:.1f}%로 가장 큽니다. 같은 업황 변수에 여러 종목이 동시에 반응할 수 있습니다."})
        if market_weights and market_weights[0].get("weight") is not None and market_weights[0]["weight"] >= 0.75:
            comments.append({"level": "info", "title": "시장 노출", "body": f"{market_weights[0]['label']} 시장 노출이 USD 환산 기준 {market_weights[0]['weight'] * 100:.1f}%입니다. 환율과 해당 시장 휴장일, 금리 이벤트 영향이 커질 수 있습니다."})
        if currency_weights and currency_weights[0].get("weight") is not None and currency_weights[0]["weight"] >= 0.75:
            comments.append({"level": "info", "title": "통화 노출", "body": f"{currency_weights[0]['label']} 표시 자산이 USD 환산 기준 {currency_weights[0]['weight'] * 100:.1f}%입니다. 원화 기준 성과는 종목 수익률과 환율 변동을 분리해서 봐야 합니다."})
        if target_analysis.get("hasTargets"):
            gap = target_analysis.get("targetGap") or 0.0
            if abs(gap) >= 0.005:
                comments.append({"level": "warn", "title": "목표 비중 합계", "body": f"입력된 목표 비중 합계가 {target_analysis.get('targetTotal', 0) * 100:.1f}%입니다. 목표 비중은 100%에 가깝게 맞춰야 현재 비중과 차이를 해석하기 쉽습니다."})
            else:
                comments.append({"level": "info", "title": "목표 비중", "body": "목표 비중 합계가 100%에 가깝습니다. 아래 목표 비중 표에서 현재 비중과 목표 비중의 차이를 확인할 수 있습니다."})
        if pnl_ranked:
            top_pnl = pnl_ranked[0]
            direction = "기여" if _float_value(top_pnl.get("pnlUsd"), 0.0) >= 0 else "손실"
            comments.append({"level": "info", "title": "손익 기여도", "body": f"현재 USD 기준 손익 변동은 {top_pnl.get('name') or top_pnl.get('ticker')}의 {direction} 영향이 가장 큽니다. 포트폴리오 판단 시 비중과 손익 기여도를 함께 확인하세요."})
    base["analytics"] = {
        "baseCurrency": "USD",
        "totalMarketValue": total_value,
        "totalCost": total_cost,
        "totalPnl": total_pnl,
        "totalPnlPct": finite_ratio(total_pnl, total_cost),
        "positionWeights": ranked,
        "sectorWeights": sector_weights,
        "marketWeights": market_weights,
        "currencyWeights": currency_weights,
        "assetClassWeights": asset_weights,
        "pnlContributors": pnl_ranked,
        "targetWeights": target_analysis,
        "concentration": {"top1": top1, "top3": top3, "top5": top5, "holdings": len(valid)},
        "calculationUnavailable": sorted(base_reasons),
        "comments": comments,
    }
    return base


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def _slugify(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z가-힣._-]+", "-", str(value or "").strip()).strip("-")
    return text[:80] or "portfolio"


def normalize_portfolio_weight(value):
    weight = _coerce_float(value)
    if weight is None:
        return 0.0
    if weight > 1:
        weight = weight / 100.0
    return max(0.0, min(1.0, weight))


def normalize_preset_position(row, resolve: bool = False):
    row = row or {}
    ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
    weight = normalize_portfolio_weight(row.get("weight", row.get("targetWeight")))
    resolved = row.get("resolved") if isinstance(row.get("resolved"), dict) else {}
    if resolve and ticker:
        resolved = resolve_portfolio_ticker(ticker, row.get("market") or resolved.get("market") or "")
    symbol = str(row.get("symbol") or resolved.get("symbol") or portfolio_symbol(ticker, resolved.get("market", ""))).strip().upper()
    market = str(row.get("market") or resolved.get("market") or infer_portfolio_market(symbol, resolved)).strip().upper()
    currency = str(row.get("currency") or resolved.get("currency") or ("KRW" if market == "KR" else "USD")).strip().upper()
    return {
        "ticker": ticker,
        "symbol": symbol,
        "name": str(row.get("name") or resolved.get("name") or ticker).strip() or ticker,
        "weight": weight,
        "market": market,
        "currency": currency,
        "assetClass": str(row.get("assetClass") or resolved.get("assetClass") or infer_portfolio_asset_class(resolved, symbol)).strip() or "Unknown",
        "sector": str(row.get("sector") or resolved.get("sector") or "Unclassified").strip() or "Unclassified",
        "resolved": {
            "ok": bool(resolved.get("ok")),
            "ticker": ticker,
            "symbol": symbol,
            "name": str(row.get("name") or resolved.get("name") or ticker).strip() or ticker,
            "market": market,
            "currency": currency,
            "assetClass": str(row.get("assetClass") or resolved.get("assetClass") or infer_portfolio_asset_class(resolved, symbol)).strip() or "Unknown",
            "sector": str(row.get("sector") or resolved.get("sector") or "Unclassified").strip() or "Unclassified",
        },
    }


def _normalize_preset_weights(positions):
    total = sum(_float_value(row.get("weight"), 0.0) for row in positions)
    if total > 0:
        for row in positions:
            row["weight"] = _float_value(row.get("weight"), 0.0) / total
    return positions


def _preset_error(field: str, code: str, message: str, row: int | None = None) -> dict:
    return {"row": row, "field": field, "code": code, "message": message}


def _preset_revision(value: object) -> int:
    return revision(value)


def _project_preset(value: dict) -> dict:
    """Add the per-preset revision to a read response without migrating disk data."""
    projected = dict(value)
    projected["revision"] = _preset_revision(value.get("revision"))
    return projected


def _read_portfolio_presets_raw(*, for_write: bool = False) -> list[dict]:
    """Read the user-owned list without treating malformed data as an empty list.

    Reads remain backward-compatible, but a write must not turn a corrupt file
    or an unexpected list member into an apparently successful empty rewrite.
    """
    try:
        raw = PORTFOLIO_PRESETS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError:
        if for_write:
            raise PortfolioValidationError([_preset_error(
                "presets", "preset_storage_unreadable", "저장된 프리셋 목록을 읽을 수 없어 변경하지 않았습니다."
            )])
        return []
    try:
        presets = json.loads(raw)
    except (TypeError, ValueError):
        if for_write:
            raise PortfolioValidationError([_preset_error(
                "presets", "preset_storage_invalid", "저장된 프리셋 목록 형식이 올바르지 않아 변경하지 않았습니다."
            )])
        return []
    if not isinstance(presets, list) or any(not isinstance(item, dict) for item in presets):
        if for_write:
            raise PortfolioValidationError([_preset_error(
                "presets", "preset_storage_invalid", "저장된 프리셋 목록 형식이 올바르지 않아 변경하지 않았습니다."
            )])
        return [item for item in presets if isinstance(item, dict)] if isinstance(presets, list) else []
    return presets


def _legacy_preset_weight_percent(row: dict) -> object:
    """Accept the old fraction-or-percent field only for callers predating U.2."""
    if "weightPercent" in row:
        return row.get("weightPercent")
    value = row.get("weight", row.get("targetWeight"))
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return value
    if not parsed.is_finite():
        return parsed
    return parsed * 100 if parsed <= 1 else parsed


def _validated_preset_payload(body: object) -> tuple[str, str, list[dict], bool]:
    data = body if isinstance(body, dict) else {}
    errors: list[dict] = []

    raw_name = data.get("name")
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    if not name:
        errors.append(_preset_error("name", "required", "프리셋 이름을 입력하세요."))

    raw_currency = data.get("baseCurrency", "USD")
    base_currency = str(raw_currency or "").strip().upper()
    if base_currency not in _PRESET_BASE_CURRENCIES:
        errors.append(_preset_error("baseCurrency", "unsupported_currency", "기준 통화는 USD 또는 KRW여야 합니다."))

    normalize_requested = data.get("normalizeWeights", False)
    if not isinstance(normalize_requested, bool):
        errors.append(_preset_error("normalizeWeights", "invalid_boolean", "자동 정규화 값은 true 또는 false여야 합니다."))
    normalize_requested = normalize_requested is True

    raw_positions = data.get("positions", [])
    if not isinstance(raw_positions, list):
        errors.append(_preset_error("positions", "invalid_positions", "종목 목록은 배열이어야 합니다."))
        raw_positions = []

    checked: list[tuple[dict, Decimal]] = []
    seen: set[str] = set()
    for index, row in enumerate(raw_positions):
        if not isinstance(row, dict):
            errors.append(_preset_error("position", "invalid_position", "각 종목은 입력 객체여야 합니다.", index))
            continue
        ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
        if (
            not ticker
            or not _PRESET_TICKER_RE.fullmatch(ticker)
            or ticker.endswith((".", "-"))
            or any(fragment in ticker for fragment in ("..", "--", ".-", "-."))
        ):
            errors.append(_preset_error("ticker", "invalid_ticker", "티커 형식을 확인하세요.", index))
        else:
            ticker_key = portfolio_symbol(ticker, str(row.get("market") or ""))
            if ticker_key in seen:
                errors.append(_preset_error("ticker", "duplicate_ticker", "같은 종목은 한 번만 넣을 수 있습니다.", index))
            seen.add(ticker_key)

        raw_weight = _legacy_preset_weight_percent(row)
        try:
            weight_percent = Decimal(str(raw_weight).strip())
        except (InvalidOperation, ValueError):
            weight_percent = None
        if weight_percent is None or not weight_percent.is_finite():
            errors.append(_preset_error("weightPercent", "invalid_weight", "비중은 유한한 숫자여야 합니다.", index))
        elif weight_percent < 0:
            errors.append(_preset_error("weightPercent", "negative_weight", "비중은 0% 이상이어야 합니다.", index))
        elif abs(weight_percent.adjusted()) > 300:
            errors.append(_preset_error("weightPercent", "unsupported_precision", "이 비중은 현재 저장 형식에서 정확히 표현할 수 없습니다.", index))
        else:
            checked.append(({**row, "ticker": ticker}, weight_percent))

    if errors:
        raise PortfolioValidationError(errors)

    try:
        total_percent = sum((weight for _, weight in checked), Decimal("0"))
    except (InvalidOperation, OverflowError):
        raise PortfolioValidationError([_preset_error(
            "weightTotal", "invalid_weight", "비중 합계를 계산할 수 없습니다."
        )]) from None
    total_is_hundred = abs(total_percent - Decimal("100")) <= _PRESET_TOTAL_TOLERANCE
    if checked and not total_is_hundred:
        if not normalize_requested:
            raise PortfolioValidationError([_preset_error(
                "weightTotal", "weight_total_not_100", "목표 비중 합계는 100%여야 합니다. 자동 정규화를 선택하거나 비중을 수정하세요."
            )])
        if total_percent <= 0:
            raise PortfolioValidationError([_preset_error(
                "weightTotal", "weight_total_zero", "0% 합계는 자동 정규화할 수 없습니다."
            )])

    positions: list[dict] = []
    symbols: dict[str, int] = {}
    for index, (row, weight_percent) in enumerate(checked):
        fraction = weight_percent / total_percent if checked and normalize_requested and not total_is_hundred else weight_percent / Decimal("100")
        try:
            projected_weight = float(fraction)
        except (OverflowError, ValueError):
            projected_weight = None
        if projected_weight is None or not math.isfinite(projected_weight) or (fraction and projected_weight == 0.0):
            raise PortfolioValidationError([_preset_error(
                "weightPercent", "unsupported_precision", "이 비중은 현재 저장 형식에서 정확히 표현할 수 없습니다.", index
            )])
        position = _normalized_preset_position(row, projected_weight)
        position["weight"] = projected_weight
        canonical_symbol = str(position.get("symbol") or "").strip().upper()
        if canonical_symbol in symbols:
            errors.append(_preset_error(
                "ticker", "duplicate_symbol", "같은 거래 종목은 한 번만 넣을 수 있습니다.", index
            ))
        else:
            symbols[canonical_symbol] = index
        positions.append(position)
    if errors:
        raise PortfolioValidationError(errors)
    return name, base_currency, positions, bool(checked and normalize_requested and not total_is_hundred)


def _required_preset_expected_revision(data: dict) -> int | None:
    value = data.get("expectedRevision")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _new_preset_id(existing_ids: set[str]) -> str:
    while True:
        preset_id = uuid.uuid4().hex
        if preset_id not in existing_ids:
            return preset_id


def _normalized_preset_position(row: dict, weight: float) -> dict:
    """Derive persisted identity metadata from the current ticker only."""
    ticker = str(row.get("ticker") or "").strip().upper()
    supplied_market = str(row.get("market") or "").strip().upper()
    # For six-digit Korean tickers, KQ is the only useful supplemental hint.
    # Any other client metadata may be stale from a previously edited row.
    market_hint = "KQ" if re.fullmatch(r"\d{6}", ticker) and supplied_market == "KQ" else ""
    position = normalize_preset_position(
        {"ticker": ticker, "market": market_hint, "weight": weight}, resolve=True
    )
    resolved = position.get("resolved") if isinstance(position.get("resolved"), dict) else {}
    canonical_ticker = str(resolved.get("ticker") or ticker).strip().upper() or ticker
    resolved_symbol = str(resolved.get("symbol") or position.get("symbol") or "").strip().upper()
    # An explicit exchange suffix is an unambiguous user choice and must not
    # be replaced by a stale/default provider fallback.
    canonical_symbol = ticker if exchange_suffix(ticker) else resolved_symbol or portfolio_symbol(canonical_ticker, market_hint)
    canonical_name = str(resolved.get("name") or position.get("name") or canonical_ticker).strip() or canonical_ticker
    position["ticker"] = canonical_ticker
    position["symbol"] = canonical_symbol
    position["name"] = canonical_name
    position["resolved"] = {**resolved, "ticker": canonical_ticker, "symbol": canonical_symbol, "name": canonical_name}
    return position


def list_portfolio_presets():
    # Legacy rows are projected to revision 0 in memory.  Opening this endpoint
    # must never migrate or rewrite the user-owned list file.
    return [_project_preset(item) for item in _read_portfolio_presets_raw()]


def save_portfolio_preset(body):
    data = body if isinstance(body, dict) else {}
    supplied_id = "id" in data
    # Surface a stale/deleted edit as a conflict even when its draft is also
    # incomplete; the UI must reload rather than validate against a dead base.
    if supplied_id:
        with _PORTFOLIO_PRESETS_WRITE_LOCK:
            existing = next(
                (row for row in _read_portfolio_presets_raw(for_write=True) if str(row.get("id") or "") == str(data.get("id") or "").strip()),
                None,
            )
            expected = _required_preset_expected_revision(data)
            if existing is None:
                raise PresetRevisionConflict(None)
            if expected is None or expected != _preset_revision(existing.get("revision")):
                raise PresetRevisionConflict(_project_preset(existing))

    name, base_currency, positions, normalized = _validated_preset_payload(data)
    with _PORTFOLIO_PRESETS_WRITE_LOCK:
        presets = _read_portfolio_presets_raw(for_write=True)
        existing_ids = {str(row.get("id") or "") for row in presets}
        if supplied_id:
            preset_id = str(data.get("id") or "").strip()
            existing = next((row for row in presets if str(row.get("id") or "") == preset_id), None)
            if existing is None:
                raise PresetRevisionConflict(None)
            expected = _required_preset_expected_revision(data)
            if expected is None or expected != _preset_revision(existing.get("revision")):
                raise PresetRevisionConflict(_project_preset(existing))
            next_revision = _preset_revision(existing.get("revision")) + 1
            presets = [row for row in presets if row is not existing]
        else:
            preset_id = _new_preset_id(existing_ids)
            next_revision = 1
        preset = {
            "id": preset_id,
            "name": name,
            "baseCurrency": base_currency,
            "positions": positions,
            "weightTotal": sum(_float_value(row.get("weight"), 0.0) for row in positions),
            "revision": next_revision,
            "updatedAt": now_iso(),
        }
        if normalized:
            preset["normalizedWeights"] = True
        presets.insert(0, preset)
        write_json(PORTFOLIO_PRESETS_PATH, presets)
        return _project_preset(preset)


def delete_portfolio_preset(preset_id, body: dict | None = None):
    data = body if isinstance(body, dict) else {}
    with _PORTFOLIO_PRESETS_WRITE_LOCK:
        presets = _read_portfolio_presets_raw(for_write=True)
        existing = next((row for row in presets if str(row.get("id") or "") == str(preset_id)), None)
        if existing is None:
            raise PresetRevisionConflict(None)
        expected = _required_preset_expected_revision(data)
        if expected is None or expected != _preset_revision(existing.get("revision")):
            raise PresetRevisionConflict(_project_preset(existing))
        write_json(PORTFOLIO_PRESETS_PATH, [row for row in presets if row is not existing])
        return {"deleted": True, "id": str(preset_id)}


def get_portfolio_preset(preset_id):
    for preset in list_portfolio_presets():
        if preset.get("id") == preset_id:
            return preset
    return None


def preset_from_current_portfolio(name="현재 포트폴리오 목표 비중"):
    """지금 보유 비중을 그대로 목표 프리셋으로 만든다.

    예전에는 `targetWeight`가 이미 있는 포지션만 담았다. 그 값은 화면 어디에서도
    넣을 수 없어서(보유 표에 칸이 없다) 결과가 **항상 빈 프리셋**이었다 — 실측으로
    보유 3종목에서 positions=[]가 나왔다. 게다가 목표가 이미 있다면 그것을 다시
    베끼는 일에는 쓸모가 없다.

    "현재 포트폴리오에서"가 뜻할 수 있는 것은 하나다. 지금 평가액 비중을 목표로 삼는
    것이다. 비중은 `portfolio_summary()`가 환율까지 반영해 계산해 둔 값을 쓴다.
    """
    snapshot = portfolio_summary()
    positions = []
    warnings = []
    for row in snapshot.get("positions", []):
        # A preset made from current holdings means current valuation weights,
        # never an older targetWeight that happened to be stored on the row.
        weight = row.get("weight")
        # 시세를 못 받은 종목은 비중을 계산할 수 없다. 0으로 넣으면 목표에서 빠진
        # 것처럼 보이므로 아예 담지 않고, 담긴 것들끼리 정규화된다.
        if weight is None:
            warnings.append({
                "code": "position_weight_unavailable",
                "ticker": str(row.get("ticker") or ""),
                "message": "현재 평가 비중을 계산할 수 없어 이 종목은 초안에 넣지 않았습니다.",
            })
            continue
        if not weight:
            continue
        positions.append({
            "ticker": row.get("ticker"),
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "market": row.get("market"),
            "currency": row.get("currency"),
            "assetClass": row.get("assetClass"),
            "sector": row.get("sector"),
            "weight": weight,
            "resolved": row.get("resolved") or {},
        })
    # This is deliberately only a draft: choosing "from current" must not
    # create a durable preset before the user has reviewed and edited it.
    draft = {
        "draft": True,
        "name": str(name or "현재 포트폴리오 목표 비중").strip() or "현재 포트폴리오 목표 비중",
        "baseCurrency": "USD",
        "positions": positions,
        "weightTotal": sum(_float_value(row.get("weight"), 0.0) for row in positions),
    }
    if warnings:
        draft["warnings"] = warnings
    return draft


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

def _series_cache_path(symbol: str, start: str, end: str) -> Path:
    safe = re.sub(r"[^0-9A-Za-z._=-]+", "_", f"{symbol}_{start}_{end}")
    safe = re.sub(r"\.{2,}", "_", safe)
    return PORTFOLIO_PRICE_CACHE_DIR / f"{safe}.json"


def _download_adjusted_close(symbol: str, start: str, end: str):
    cache_path = _series_cache_path(symbol, start, end)
    cached = read_json(cache_path, None, root=PORTFOLIO_PRICE_CACHE_DIR)
    if isinstance(cached, dict) and cached.get("series"):
        return cached["series"], cached.get("source", "cache")
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(start=start, end=end, interval="1d", auto_adjust=True, actions=False)
        if hist.empty or "Close" not in hist:
            raise ValueError(f"{symbol} 가격 데이터가 비어 있습니다.")
        series = {}
        for index, value in hist["Close"].dropna().items():
            date = index.date().isoformat() if hasattr(index, "date") else str(index)[:10]
            number = _coerce_float(value)
            if number is not None and number > 0:
                series[date] = number
        if not series:
            raise ValueError(f"{symbol} 종가 데이터가 없습니다.")
        PORTFOLIO_PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        write_json(
            cache_path,
            {"symbol": symbol, "start": start, "end": end, "series": series, "source": "yfinance", "updatedAt": now_iso()},
            root=PORTFOLIO_PRICE_CACHE_DIR,
        )
        return series, "yfinance"
    except Exception as exc:
        if isinstance(cached, dict) and cached.get("series"):
            return cached["series"], "stale-cache"
        raise ValueError(f"{symbol} price data is unavailable") from exc


def _fx_symbol_for_currency(currency: str):
    """Yahoo's ``XXX=X`` is uniformly USD/XXX — units of XXX per one dollar."""
    currency = str(currency or "USD").upper()
    return None if currency == "USD" else f"{currency}=X"


def _benchmark_currency_hint(ticker: str) -> str:
    """Best guess at a benchmark's currency before it is resolved, for FX prefetch."""
    return fallback_currency(portfolio_symbol(ticker))


def _fx_series_for_currencies(currencies, start, end) -> dict:
    """Daily USD/XXX series for each non-dollar currency in play."""
    rates = {}
    for currency in sorted({str(item or "USD").upper() for item in currencies}):
        symbol = _fx_symbol_for_currency(currency)
        if not symbol:
            continue
        series, _source = _download_adjusted_close(symbol, start, end)
        if series:
            rates[currency] = series
    return rates


def _convert_price_series(series, currency: str, base_currency: str, fx_by_currency=None, *, with_metadata=False):
    """Restate a price series in the base currency, routed through USD.

    Every leg is a USD/XXX rate, so a foreign price divides into dollars and a
    dollar price multiplies into a foreign base. The old version only knew the
    KRW and USD pair and passed anything else through untouched, which let a JPY
    backtest run on yen figures labelled as dollars — off by about 150x with no
    warning. A currency whose rate could not be fetched now yields nothing rather
    than an unconverted number.
    """
    currency = str(currency or "USD").upper()
    base_currency = str(base_currency or "USD").upper()
    if currency == base_currency:
        converted = dict(series)
        metadata = {
            "required": False, "fromCurrency": currency, "toCurrency": base_currency,
            "observedDays": 0, "forwardFilledDays": 0, "trailingForwardFilledDays": 0,
            "coverage": None, "unavailableReason": None,
        }
        return (converted, metadata) if with_metadata else converted
    fx_by_currency = fx_by_currency or {}
    from_series = fx_by_currency.get(currency) if currency != "USD" else {}
    into_series = fx_by_currency.get(base_currency) if base_currency != "USD" else {}
    if (currency != "USD" and not from_series) or (base_currency != "USD" and not into_series):
        metadata = {
            "required": True, "fromCurrency": currency, "toCurrency": base_currency,
            "observedDays": 0, "forwardFilledDays": 0, "trailingForwardFilledDays": 0,
            "coverage": None, "unavailableReason": "fx_series_unavailable",
        }
        return ({}, metadata) if with_metadata else {}
    converted = {}
    last_from = None
    last_into = None
    from_points = sorted((str(date), _coerce_float(value, None)) for date, value in (from_series or {}).items())
    into_points = sorted((str(date), _coerce_float(value, None)) for date, value in (into_series or {}).items())
    from_index = 0
    into_index = 0
    observed_days = 0
    forward_filled_days = 0
    for date in sorted(series.keys()):
        # Advance through every known FX observation up to this price date;
        # checking only exact price dates can use a stale rate even when a more
        # recent FX close exists on an intervening market holiday.
        while from_index < len(from_points) and from_points[from_index][0] <= date:
            _date, from_rate = from_points[from_index]
            if from_rate is not None and from_rate > 0:
                last_from = from_rate
            from_index += 1
        while into_index < len(into_points) and into_points[into_index][0] <= date:
            _date, into_rate = into_points[into_index]
            if into_rate is not None and into_rate > 0:
                last_into = into_rate
            into_index += 1
        if (currency != "USD" and last_from is None) or (base_currency != "USD" and last_into is None):
            continue
        price = _coerce_float(series.get(date), None)
        if price is None:
            continue
        usd = price if currency == "USD" else price / last_from
        converted[date] = usd if base_currency == "USD" else usd * last_into
        direct_from = currency == "USD" or _coerce_float((from_series or {}).get(date), None) not in (None, 0)
        direct_into = base_currency == "USD" or _coerce_float((into_series or {}).get(date), None) not in (None, 0)
        if direct_from and direct_into:
            observed_days += 1
        else:
            forward_filled_days += 1
    metadata = {
        "required": True,
        "fromCurrency": currency,
        "toCurrency": base_currency,
        "observedDays": observed_days,
        "forwardFilledDays": forward_filled_days,
        "trailingForwardFilledDays": 0,
        "coverage": (observed_days / len(converted)) if converted else None,
        "unavailableReason": None if converted else "fx_has_no_convertible_price_dates",
    }
    return (converted, metadata) if with_metadata else converted


def _aligned_price_rows(asset_series):
    dates = sorted(set().union(*(set(item["series"].keys()) for item in asset_series)))
    last_values = {item["symbol"]: None for item in asset_series}
    rows = []
    for date in dates:
        row = {"date": date}
        ok = False
        for item in asset_series:
            symbol = item["symbol"]
            value = _coerce_float(item["series"].get(date), None)
            if value is not None:
                last_values[symbol] = value
            row[symbol] = last_values[symbol]
            if last_values[symbol] is not None:
                ok = True
        if ok:
            rows.append(row)
    complete = [row for row in rows if all(row.get(item["symbol"]) is not None for item in asset_series)]
    return complete


def _aligned_native_price_rows_with_fx(asset_series, base_currency, fx_by_currency, *, simulation_dates=None):
    """Carry native closes first, then mark each simulation date with as-of FX.

    Simulation dates remain the union of local asset-price dates.  An FX-only
    date never creates a valuation row, but an FX update on an existing other
    asset date changes a foreign asset's base-currency value even when its local
    market is closed.
    """
    dates = [str(date) for date in simulation_dates] if simulation_dates is not None else sorted(set().union(*(set((item.get("series") or {}).keys()) for item in asset_series)))
    local_last = {item["symbol"]: None for item in asset_series}
    price_points = {
        item["symbol"]: sorted((str(date), _coerce_float(value, None)) for date, value in (item.get("series") or {}).items())
        for item in asset_series
    }
    price_indexes = {symbol: 0 for symbol in price_points}
    price_last_date = {symbol: None for symbol in price_points}
    fx_points = {
        currency: sorted((str(date), _coerce_float(value, None)) for date, value in series.items())
        for currency, series in (fx_by_currency or {}).items()
    }
    fx_indexes = {currency: 0 for currency in fx_points}
    fx_last = {currency: None for currency in fx_points}
    fx_last_date = {currency: None for currency in fx_points}
    rows = []
    per_date_meta = []
    base_currency = str(base_currency or "USD").upper()
    required_currencies = {str(item.get("currency") or "USD").upper() for item in asset_series} | {base_currency}
    for date in dates:
        for currency in required_currencies:
            if currency == "USD":
                continue
            points = fx_points.get(currency, [])
            index = fx_indexes.get(currency, 0)
            while index < len(points) and points[index][0] <= date:
                source_date, value = points[index]
                if value is not None and value > 0:
                    fx_last[currency] = value
                    fx_last_date[currency] = source_date
                index += 1
            fx_indexes[currency] = index
        row = {"date": date}
        date_meta = {}
        complete = True
        for item in asset_series:
            symbol = item["symbol"]
            points = price_points[symbol]
            index = price_indexes[symbol]
            while index < len(points) and points[index][0] <= date:
                source_date, local_value = points[index]
                if local_value is not None:
                    local_last[symbol] = local_value
                    price_last_date[symbol] = source_date
                index += 1
            price_indexes[symbol] = index
            currency = str(item.get("currency") or "USD").upper()
            from_rate = 1.0 if currency == "USD" else fx_last.get(currency)
            into_rate = 1.0 if base_currency == "USD" else fx_last.get(base_currency)
            if local_last[symbol] is None or from_rate is None or into_rate is None:
                complete = False
                row[symbol] = None
            else:
                usd = local_last[symbol] if currency == "USD" else local_last[symbol] / from_rate
                row[symbol] = usd if base_currency == "USD" else usd * into_rate
            date_meta[symbol] = {
                "nativeObserved": price_last_date[symbol] == date,
                "nativeSourceDate": price_last_date[symbol],
                "fromFxSourceDate": None if currency == "USD" else fx_last_date.get(currency),
                "intoFxSourceDate": None if base_currency == "USD" else fx_last_date.get(base_currency),
            }
        if complete:
            rows.append(row)
            per_date_meta.append(date_meta)
    coverage = {}
    simulation_dates = [row["date"] for row in rows]
    for item in asset_series:
        symbol = item["symbol"]
        currency = str(item.get("currency") or "USD").upper()
        price = _series_coverage(item.get("series"), simulation_dates)
        fx_required = currency != base_currency
        observed_days = forward_filled_days = trailing_forward_filled_days = 0
        from_observed = from_carried = into_observed = into_carried = 0
        from_last_date = fx_points.get(currency, [])[-1][0] if currency != "USD" and fx_points.get(currency) else None
        into_last_date = fx_points.get(base_currency, [])[-1][0] if base_currency != "USD" and fx_points.get(base_currency) else None
        for date, date_meta in zip(simulation_dates, per_date_meta):
            meta = date_meta[symbol]
            from_source = meta.get("fromFxSourceDate")
            into_source = meta.get("intoFxSourceDate")
            from_direct = currency == "USD" or from_source == date
            into_direct = base_currency == "USD" or into_source == date
            if currency != "USD":
                if from_direct:
                    from_observed += 1
                else:
                    from_carried += 1
            if base_currency != "USD":
                if into_direct:
                    into_observed += 1
                else:
                    into_carried += 1
            if fx_required:
                if from_direct and into_direct:
                    observed_days += 1
                else:
                    forward_filled_days += 1
                if (from_last_date is not None and date > from_last_date) or (into_last_date is not None and date > into_last_date):
                    trailing_forward_filled_days += 1
        coverage[symbol] = {
            "required": fx_required, "fromCurrency": currency, "toCurrency": base_currency,
            "observedDays": observed_days, "forwardFilledDays": forward_filled_days,
            "trailingForwardFilledDays": trailing_forward_filled_days,
            "coverage": (observed_days / (observed_days + forward_filled_days)) if (observed_days + forward_filled_days) else None,
            "unavailableReason": None,
            "legObservations": {
                "from": {"observedDays": from_observed, "forwardFilledDays": from_carried},
                "into": {"observedDays": into_observed, "forwardFilledDays": into_carried},
            },
            "nativePrice": {key: price[key] for key in ("observedDays", "forwardFilledDays", "trailingForwardFilledDays", "coverage")},
        }
    return rows, coverage


def _series_on_dates(series, dates):
    """Carry a single converted series onto simulation dates after first quote.

    Returned rows begin only once the benchmark has an observable close.  The
    caller then slices the portfolio to these exact dates so benchmark metrics
    never compare different intervals.
    """
    points = sorted((str(date), _coerce_float(value, None)) for date, value in (series or {}).items())
    point_index = 0
    carried = None
    carried_date = None
    rows = []
    for date in dates:
        while point_index < len(points) and points[point_index][0] <= date:
            source_date, value = points[point_index]
            if value is not None:
                carried = value
                carried_date = source_date
            point_index += 1
        if carried is not None:
            rows.append({"date": date, "value": carried, "sourceDate": carried_date, "forwardFilled": carried_date != date})
    return rows


def _is_rebalance_date(previous_date, current_date, frequency):
    if not previous_date:
        return True
    if frequency == "none":
        return False
    prev = dt.date.fromisoformat(previous_date)
    curr = dt.date.fromisoformat(current_date)
    if frequency == "monthly":
        return (prev.year, prev.month) != (curr.year, curr.month)
    if frequency == "quarterly":
        return (prev.year, (prev.month - 1) // 3) != (curr.year, (curr.month - 1) // 3)
    if frequency == "yearly":
        return prev.year != curr.year
    return False


def _run_weight_backtest(price_rows, weights, initial_value, rebalance_frequency, *, include_increments=False):
    """Simulate target weights without erasing a rebalance-boundary return.

    Each date is first marked to that date's close, then rebalanced at that
    same close.  Reversing those operations reprices the old portfolio at the
    new weights and silently drops the boundary day's move.
    """
    if not price_rows:
        return ([], []) if include_increments else []
    symbols = list(weights.keys())
    shares = {symbol: 0.0 for symbol in symbols}
    values = []
    increments = []
    portfolio_value = float(initial_value or 10000)
    previous_date = ""
    previous_prices = None

    def allocate(symbol, price, value):
        target_weight = _coerce_float(weights.get(symbol), None)
        if target_weight is None or target_weight < 0 or not math.isfinite(target_weight):
            raise BacktestCalculationLimitError()
        if target_weight == 0:
            return 0.0
        if price is None or price <= 0 or not math.isfinite(price) or value is None or value <= 0 or not math.isfinite(value):
            raise BacktestCalculationLimitError()
        shares_value = value * target_weight / price
        # Do not turn a tiny fractional holding into zero or an enormous one
        # into infinity: either outcome fabricates subsequent performance.
        if not math.isfinite(shares_value) or shares_value == 0.0:
            raise BacktestCalculationLimitError()
        return shares_value

    for index, row in enumerate(price_rows):
        date = row["date"]
        if index == 0:
            for symbol in symbols:
                price = _coerce_float(row.get(symbol), None)
                shares[symbol] = allocate(symbol, price, portfolio_value)
            date_amounts = {symbol: 0.0 for symbol in symbols}
        else:
            # Mark the positions held over the interval before changing shares.
            date_amounts = {
                symbol: shares[symbol] * (_coerce_float(row.get(symbol), 0.0) - _coerce_float(previous_prices.get(symbol), 0.0))
                for symbol in symbols
            }
            position_values = []
            for symbol in symbols:
                price = _coerce_float(row.get(symbol), None)
                position_value = shares[symbol] * price if price is not None else None
                if position_value is None or not math.isfinite(position_value) or position_value <= 0:
                    raise BacktestCalculationLimitError()
                position_values.append(position_value)
            portfolio_value = sum(position_values)
            if not math.isfinite(portfolio_value) or portfolio_value <= 0:
                raise BacktestCalculationLimitError()
            if _is_rebalance_date(previous_date, date, rebalance_frequency):
                for symbol in symbols:
                    price = _coerce_float(row.get(symbol), None)
                    shares[symbol] = allocate(symbol, price, portfolio_value)
        values.append({"date": date, "value": portfolio_value})
        increments.append({
            "date": date,
            "amounts": date_amounts,
            "contributions": {
                symbol: (amount / float(initial_value)) if float(initial_value) else None
                for symbol, amount in date_amounts.items()
            },
        })
        previous_date = date
        previous_prices = row
    return (values, increments) if include_increments else values


def _daily_returns(values):
    returns = []
    previous = None
    previous_date = None
    for row in values:
        value = _coerce_float(row.get("value"), None)
        if previous and value is not None:
            returns.append({"startDate": previous_date, "date": row["date"], "return": (value / previous) - 1.0})
        previous = value
        previous_date = row["date"]
    return returns


def _aligned_return_pairs(values, benchmark_values):
    portfolio_returns = {(row.get("startDate"), row["date"]): row["return"] for row in _daily_returns(values)}
    benchmark_returns = {(row.get("startDate"), row["date"]): row["return"] for row in _daily_returns(benchmark_values or [])}
    pairs = []
    for date in sorted(set(portfolio_returns) & set(benchmark_returns)):
        p_return = _coerce_float(portfolio_returns.get(date))
        b_return = _coerce_float(benchmark_returns.get(date))
        if p_return is not None and b_return is not None:
            pairs.append((p_return, b_return))
    return pairs


def _mean(items):
    values = [item for item in items if item is not None]
    return sum(values) / len(values) if values else None


def _sample_variance(items):
    values = [item for item in items if item is not None]
    if len(values) < 2:
        return None
    avg = sum(values) / len(values)
    return sum((item - avg) ** 2 for item in values) / (len(values) - 1)


def _sample_covariance(left, right):
    pairs = [(a, b) for a, b in zip(left, right) if a is not None and b is not None]
    if len(pairs) < 2:
        return None
    left_avg = sum(a for a, _ in pairs) / len(pairs)
    right_avg = sum(b for _, b in pairs) / len(pairs)
    return sum((a - left_avg) * (b - right_avg) for a, b in pairs) / (len(pairs) - 1)


def _drawdown_stats(values):
    if not values:
        return {"maxDrawdown": None, "averageDrawdown": None, "maxDrawdownDays": 0}
    peak = _float_value(values[0].get("value"), 0.0)
    drawdowns = []
    current_days = 0
    max_days = 0
    max_drawdown = 0.0
    for row in values:
        value = _float_value(row.get("value"), 0.0)
        if value >= peak:
            peak = value
            current_days = 0
        else:
            current_days += 1
            max_days = max(max_days, current_days)
        drawdown = value / peak - 1.0 if peak else 0.0
        drawdowns.append(drawdown)
        max_drawdown = min(max_drawdown, drawdown)
    negative = [item for item in drawdowns if item < 0]
    return {
        "maxDrawdown": max_drawdown,
        "averageDrawdown": sum(negative) / len(negative) if negative else 0.0,
        "maxDrawdownDays": max_days,
    }


def _var_stats(returns, confidence=0.95):
    values = sorted([item for item in returns if item is not None])
    if not values:
        return {"var95": None, "cvar95": None}
    index = max(0, min(len(values) - 1, int((1 - confidence) * len(values))))
    var = values[index]
    tail = values[:index + 1]
    return {"var95": var, "cvar95": sum(tail) / len(tail) if tail else var}


def _capture_ratio(pairs, direction):
    if direction == "up":
        selected = [(p, b) for p, b in pairs if b > 0]
    else:
        selected = [(p, b) for p, b in pairs if b < 0]
    if not selected:
        return None
    p_sum = sum(p for p, _ in selected)
    b_sum = sum(b for _, b in selected)
    return p_sum / b_sum if b_sum else None


def _period_returns(values, period="year"):
    """Period returns include the boundary interval and mark incomplete first bins.

    A month whose first in-period value already reflects a move from the prior
    month needs that prior close as its baseline.  At the start of a requested
    run no prior value exists, so the partial first period is explicitly null
    rather than reported as a fabricated 0% return.
    """
    groups = {}
    previous = None
    for row in values:
        date = dt.date.fromisoformat(row["date"])
        key = str(date.year) if period == "year" else f"{date.year}-{date.month:02d}"
        bucket = groups.setdefault(key, {"baseline": previous or row, "baselineDate": previous.get("date") if previous else row.get("date"), "end": None, "endDate": None, "observations": 0, "hasPreceding": previous is not None})
        bucket["end"] = row["value"]
        bucket["endDate"] = row["date"]
        bucket["observations"] += 1
        previous = row
    ordered = sorted(groups.items())
    output = []
    for index, (key, bucket) in enumerate(ordered):
        end_date = dt.date.fromisoformat(bucket["endDate"])
        if period == "year":
            ends_calendar_period = (end_date.month, end_date.day) == (12, 31)
        else:
            next_month = end_date.replace(day=28) + dt.timedelta(days=4)
            ends_calendar_period = end_date.day == (next_month - dt.timedelta(days=next_month.day)).day
        partial_end = index == len(ordered) - 1 and not ends_calendar_period
        output.append({
            "period": key,
            "return": (bucket["end"] / bucket["baseline"]["value"] - 1.0) if bucket["baseline"] and _coerce_float(bucket["baseline"].get("value"), None) not in (None, 0) and (bucket["hasPreceding"] or bucket["observations"] > 1) else None,
            "baselineDate": bucket["baselineDate"],
            "partial": (not bucket["hasPreceding"]) or partial_end,
            "partialStart": not bucket["hasPreceding"],
            "partialEnd": partial_end,
            "observations": bucket["observations"],
        })
    return output


def _portfolio_metrics_legacy(values, benchmark_values=None):
    if not values:
        return {}
    start_value = _float_value(values[0].get("value"), 0.0)
    end_value = _float_value(values[-1].get("value"), 0.0)
    start_date = dt.date.fromisoformat(values[0]["date"])
    end_date = dt.date.fromisoformat(values[-1]["date"])
    days = max((end_date - start_date).days, 1)
    total_return = (end_value / start_value - 1.0) if start_value else None
    cagr = ((end_value / start_value) ** (365.25 / days) - 1.0) if start_value and end_value > 0 else None
    daily_rows = _daily_returns(values)
    returns = [row["return"] for row in daily_rows]
    avg = sum(returns) / len(returns) if returns else 0.0
    variance = sum((item - avg) ** 2 for item in returns) / (len(returns) - 1) if len(returns) > 1 else 0.0
    volatility = (variance ** 0.5) * (252 ** 0.5) if returns else None
    annualized_return = avg * 252 if returns else None
    sharpe = (avg * 252 / volatility) if volatility else None
    downside = [min(0.0, item) for item in returns]
    downside_var = sum(item ** 2 for item in downside) / len(downside) if downside else 0.0
    downside_volatility = (downside_var ** 0.5) * (252 ** 0.5) if downside_var else None
    sortino = (avg * 252 / downside_volatility) if downside_volatility else None
    drawdown = _drawdown_stats(values)
    max_drawdown = drawdown["maxDrawdown"]
    monthly = _period_returns(values, "month")
    yearly = _period_returns(values, "year")
    best_year = max((row.get("return") for row in yearly if row.get("return") is not None), default=None)
    worst_year = min((row.get("return") for row in yearly if row.get("return") is not None), default=None)
    positive_years = [row for row in yearly if row.get("return") is not None]
    positive_year_ratio = (sum(1 for row in positive_years if row.get("return") > 0) / len(positive_years)) if positive_years else None
    worst_month = min((row.get("return") for row in monthly if row.get("return") is not None), default=None)
    var_stats = _var_stats(returns)
    benchmark_total = None
    excess_return = None
    beta = None
    alpha = None
    correlation = None
    r_squared = None
    information_ratio = None
    treynor = None
    up_capture = None
    down_capture = None
    tracking_error = None
    if benchmark_values:
        b_start = _float_value(benchmark_values[0].get("value"), 0.0)
        b_end = _float_value(benchmark_values[-1].get("value"), 0.0)
        benchmark_total = b_end / b_start - 1.0 if b_start else None
        if total_return is not None and benchmark_total is not None:
            excess_return = total_return - benchmark_total
        pairs = _aligned_return_pairs(values, benchmark_values)
        if len(pairs) > 1:
            p_returns = [item[0] for item in pairs]
            b_returns = [item[1] for item in pairs]
            p_avg = sum(p_returns) / len(p_returns)
            b_avg = sum(b_returns) / len(b_returns)
            covariance = sum((p - p_avg) * (b - b_avg) for p, b in pairs) / (len(pairs) - 1)
            b_variance = sum((b - b_avg) ** 2 for b in b_returns) / (len(b_returns) - 1)
            p_variance = sum((p - p_avg) ** 2 for p in p_returns) / (len(p_returns) - 1)
            beta = covariance / b_variance if b_variance else None
            correlation = covariance / ((p_variance ** 0.5) * (b_variance ** 0.5)) if p_variance and b_variance else None
            r_squared = correlation ** 2 if correlation is not None else None
            b_annual = b_avg * 252
            alpha = (avg * 252) - (beta * b_annual) if beta is not None else None
            active_returns = [p - b for p, b in pairs]
            tracking_error = (_sample_variance(active_returns) ** 0.5) * (252 ** 0.5) if _sample_variance(active_returns) else None
            information_ratio = ((avg - b_avg) * 252 / tracking_error) if tracking_error else None
            treynor = (avg * 252 / beta) if beta else None
            up_capture = _capture_ratio(pairs, "up")
            down_capture = _capture_ratio(pairs, "down")
    calmar = (cagr / abs(max_drawdown)) if cagr is not None and max_drawdown else None
    return {
        "startValue": start_value, "endValue": end_value, "totalReturn": total_return, "cagr": cagr,
        "annualizedReturn": annualized_return, "bestYear": best_year, "worstYear": worst_year,
        "positiveYearRatio": positive_year_ratio, "worstMonth": worst_month, "volatility": volatility,
        "downsideVolatility": downside_volatility, "maxDrawdown": max_drawdown,
        "averageDrawdown": drawdown["averageDrawdown"], "maxDrawdownDays": drawdown["maxDrawdownDays"],
        "var95": var_stats["var95"], "cvar95": var_stats["cvar95"], "sharpe": sharpe, "sortino": sortino,
        "calmar": calmar, "informationRatio": information_ratio, "treynor": treynor,
        "benchmarkTotalReturn": benchmark_total, "excessReturn": excess_return, "beta": beta, "alpha": alpha,
        "correlation": correlation, "rSquared": r_squared, "trackingError": tracking_error,
        "upCapture": up_capture, "downCapture": down_capture, "days": days, "observations": len(values),
    }


def _portfolio_metrics(values, benchmark_values=None):
    """Compatibility projection over the U.3 metric engine.

    Comparison values require an identical series of dated portfolio and
    benchmark observations; direct callers may not have performed this slice.
    """
    comparable_portfolio = values
    comparable_benchmark = benchmark_values or []
    if benchmark_values:
        common_dates = {str(row.get("date")) for row in values} & {str(row.get("date")) for row in benchmark_values}
        comparable_portfolio = [row for row in values if str(row.get("date")) in common_dates]
        comparable_benchmark = [row for row in benchmark_values if str(row.get("date")) in common_dates]
    metrics = analysis_portfolio_metrics(comparable_portfolio, comparable_benchmark)
    yearly = _period_returns(comparable_portfolio, "year")
    monthly = _period_returns(comparable_portfolio, "month")
    yearly_values = [row.get("return") for row in yearly if row.get("return") is not None]
    monthly_values = [row.get("return") for row in monthly if row.get("return") is not None]
    daily_values = [row.get("return") for row in _daily_returns(comparable_portfolio) if row.get("return") is not None]
    legacy = {
        "bestYear": max(yearly_values) if yearly_values else None,
        "worstYear": min(yearly_values) if yearly_values else None,
        "positiveYearRatio": (sum(1 for value in yearly_values if value > 0) / len(yearly_values)) if yearly_values else None,
        "worstMonth": min(monthly_values) if monthly_values else None,
        **_var_stats(daily_values),
    }
    for name in ("bestYear", "worstYear", "positiveYearRatio", "worstMonth", "var95", "cvar95"):
        metrics[name] = legacy.get(name)
        if metrics[name] is None:
            metrics.setdefault("metricUnavailableReasons", {}).setdefault(name, "insufficient_period_or_daily_return_observations")
    return metrics


def _asset_contributions(asset_series, weights, initial_value):
    items = []
    for item in asset_series:
        symbol = item["symbol"]
        series = item["series"]
        if not series:
            continue
        dates = sorted(series.keys())
        start = _float_value(series.get(dates[0]), 0.0)
        end = _float_value(series.get(dates[-1]), 0.0)
        asset_return = end / start - 1.0 if start else None
        contribution = (weights.get(symbol, 0.0) * asset_return) if asset_return is not None else None
        items.append({
            "ticker": item.get("ticker"),
            "symbol": symbol,
            "name": item.get("name"),
            "weight": weights.get(symbol, 0.0),
            "return": asset_return,
            "contribution": contribution,
            "contributionAmount": contribution * initial_value if contribution is not None else None,
        })
    return sorted(items, key=lambda row: abs(row.get("contribution") or 0.0), reverse=True)


def _actual_asset_contributions(asset_series, increments, initial_value, price_rows=None):
    """Attribute simulated P/L increments, including drift and rebalance timing.

    This is deliberately not the old initial-weight/start-to-end shortcut: the
    sum of amounts reconciles to final value minus initial value (within float
    precision) because every interval uses the shares actually held.
    """
    totals = {item["symbol"]: 0.0 for item in asset_series}
    for row in increments:
        for symbol, amount in (row.get("amounts") or {}).items():
            if symbol in totals:
                totals[symbol] += _coerce_float(amount, 0.0)
    items = []
    denominator = _coerce_float(initial_value, None)
    for item in asset_series:
        symbol = item["symbol"]
        amount = totals.get(symbol, 0.0)
        common_start = _coerce_float((price_rows or [{}])[0].get(symbol), None) if price_rows else None
        common_end = _coerce_float((price_rows or [{}])[-1].get(symbol), None) if price_rows else None
        items.append({
            "ticker": item.get("ticker"),
            "symbol": symbol,
            "name": item.get("name"),
            "weight": item.get("weight"),
            "return": (common_end / common_start - 1.0) if common_start not in (None, 0) and common_end is not None else None,
            "contribution": amount / denominator if denominator not in (None, 0) else None,
            "contributionAmount": amount,
        })
    return sorted(items, key=lambda row: abs(row.get("contribution") or 0.0), reverse=True)


def _series_coverage(series, simulation_dates):
    """Describe observed versus carried values over the returned run dates."""
    observed_dates = sorted(str(date) for date, value in (series or {}).items() if _coerce_float(value, None) is not None)
    sim_dates = [str(date) for date in simulation_dates]
    observed = set(observed_dates)
    actual_start = observed_dates[0] if observed_dates else None
    actual_end = observed_dates[-1] if observed_dates else None
    forward_filled = 0
    trailing = 0
    # An observation before the returned simulation window is a valid carried
    # baseline.  Do not label the first returned days as leading-missing merely
    # because that baseline date itself is outside ``simulation_dates``.
    last_seen = next((date for date in reversed(observed_dates) if sim_dates and date < sim_dates[0]), None)
    for date in sim_dates:
        if date in observed:
            last_seen = date
        elif last_seen is not None:
            forward_filled += 1
            if actual_end is not None and date > actual_end:
                trailing += 1
    return {
        "actualStart": actual_start,
        "actualEnd": actual_end,
        "observedDays": sum(1 for date in sim_dates if date in observed),
        "forwardFilledDays": forward_filled,
        "trailingForwardFilledDays": trailing,
        "coverage": (sum(1 for date in sim_dates if date in observed) / len(sim_dates)) if sim_dates else None,
    }


def _strict_common_observation_window(asset_series):
    observed_sets = [
        {str(date) for date, value in (item.get("series") or {}).items() if _coerce_float(value, None) is not None}
        for item in asset_series
    ]
    common = set.intersection(*observed_sets) if observed_sets else set()
    dates = sorted(common)
    return {"strictCommonObservedStart": dates[0] if dates else None, "strictCommonObservedEnd": dates[-1] if dates else None, "strictCommonObservedDays": len(dates)}


def _asset_daily_return_rows(price_rows, symbols):
    rows = []
    previous = None
    for row in price_rows:
        if previous is None:
            previous = row
            continue
        out = {"date": row["date"]}
        ok = False
        for symbol in symbols:
            prev = _coerce_float(previous.get(symbol), None)
            curr = _coerce_float(row.get(symbol), None)
            value = (curr / prev - 1.0) if prev and curr is not None else None
            out[symbol] = value
            ok = ok or value is not None
        if ok:
            rows.append(out)
        previous = row
    return rows


def _asset_risk_contributions(asset_series, price_rows, weights, benchmark_values=None):
    symbols = [item["symbol"] for item in asset_series]
    return_rows = _asset_daily_return_rows(price_rows, symbols)
    if not return_rows:
        return []
    portfolio_returns = []
    asset_returns = {symbol: [] for symbol in symbols}
    for row in return_rows:
        total = 0.0
        ok = False
        for symbol in symbols:
            value = _coerce_float(row.get(symbol), None)
            asset_returns[symbol].append(value)
            if value is not None:
                total += weights.get(symbol, 0.0) * value
                ok = True
        portfolio_returns.append(total if ok else None)
    portfolio_variance = _sample_variance(portfolio_returns)
    portfolio_vol = (portfolio_variance ** 0.5) if portfolio_variance is not None else None
    benchmark_returns_by_interval = {
        (row.get("startDate"), row["date"]): row["return"]
        for row in _daily_returns(benchmark_values or [])
    }
    benchmark_returns = [
        benchmark_returns_by_interval.get((row.get("startDate"), row["date"]))
        for row in return_rows
    ]
    benchmark_variance = _sample_variance(benchmark_returns)
    items = []
    for item in asset_series:
        symbol = item["symbol"]
        returns = asset_returns.get(symbol, [])
        asset_var = _sample_variance(returns)
        asset_vol = (asset_var ** 0.5) * (252 ** 0.5) if asset_var is not None else None
        cov_with_portfolio = _sample_covariance(returns, portfolio_returns)
        marginal_risk = cov_with_portfolio / portfolio_vol if cov_with_portfolio is not None and portfolio_vol else None
        volatility_contribution = weights.get(symbol, 0.0) * marginal_risk * (252 ** 0.5) if marginal_risk is not None else None
        volatility_share = (volatility_contribution / (portfolio_vol * (252 ** 0.5))) if volatility_contribution is not None and portfolio_vol else None
        cov_with_benchmark = _sample_covariance(returns, benchmark_returns)
        asset_beta = cov_with_benchmark / benchmark_variance if cov_with_benchmark is not None and benchmark_variance else None
        beta_contribution = weights.get(symbol, 0.0) * asset_beta if asset_beta is not None else None
        items.append({
            "ticker": item.get("ticker"),
            "symbol": symbol,
            "name": item.get("name"),
            "weight": weights.get(symbol, 0.0),
            "assetVolatility": asset_vol,
            "volatilityContribution": volatility_contribution,
            "volatilityShare": volatility_share,
            "assetBeta": asset_beta,
            "betaContribution": beta_contribution,
        })
    return sorted(items, key=lambda row: abs(row.get("volatilityContribution") or 0.0), reverse=True)


def _rolling_metrics(values, benchmark_values=None, window=252):
    daily = _daily_returns(values)
    benchmark = {
        (row.get("startDate"), row["date"]): row["return"]
        for row in _daily_returns(benchmark_values or [])
    }
    rows = []
    for index in range(window - 1, len(daily)):
        chunk = daily[index - window + 1:index + 1]
        returns = [row["return"] for row in chunk if row.get("return") is not None]
        if not returns:
            continue
        total_return = 1.0
        for value in returns:
            total_return *= (1.0 + value)
        variance = _sample_variance(returns)
        volatility = (variance ** 0.5) * (252 ** 0.5) if variance is not None else None
        beta = None
        b_returns = [benchmark.get((row.get("startDate"), row["date"])) for row in chunk]
        b_variance = _sample_variance(b_returns)
        covariance = _sample_covariance(returns, b_returns)
        if covariance is not None and b_variance:
            beta = covariance / b_variance
        rows.append({
            "date": chunk[-1]["date"],
            "rollingReturn": total_return - 1.0,
            "rollingVolatility": volatility,
            "rollingBeta": beta,
            "window": window,
        })
    return rows


def run_portfolio_backtest(body, save_result=False):
    data = body if isinstance(body, dict) else {}
    preset = get_portfolio_preset(str(data.get("presetId") or ""))
    if not preset and isinstance(data.get("preset"), dict):
        preset = data["preset"]
    if not preset:
        raise HTTPException(status_code=404, detail="Portfolio preset not found")
    start = str(data.get("start") or "2018-01-01")[:10]
    end = str(data.get("end") or kst_date())[:10]
    if start >= end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")
    base_currency = str(data.get("baseCurrency") or preset.get("baseCurrency") or "USD").upper()
    if base_currency not in {"USD", "KRW"}:
        base_currency = "USD"
    raw_initial_value = data.get("initialValue", 10000.0)
    initial_value = _coerce_float(raw_initial_value, None)
    if initial_value is None or initial_value <= 0:
        raise HTTPException(status_code=422, detail="Initial value must be a positive finite number")
    rebalance = str(data.get("rebalance") or "monthly").lower()
    if rebalance not in {"none", "monthly", "quarterly", "yearly"}:
        rebalance = "monthly"
    benchmark_ticker = str(data.get("benchmark") or ("SPY" if base_currency == "USD" else "069500.KS")).strip().upper()
    preset_id = str(preset.get("id") or "")
    should_resolve_positions = (not preset_id) or preset_id.startswith("draft-")
    positions = _normalize_preset_weights([normalize_preset_position(row, resolve=should_resolve_positions) for row in preset.get("positions", [])])
    positions = [row for row in positions if row.get("ticker") and row.get("weight") > 0]
    if not positions:
        raise HTTPException(status_code=400, detail="Preset has no weighted positions")
    # Every currency in the run needs its own rate. A single KRW=X series left a
    # Tokyo or Amsterdam position with nothing to convert against.
    fx_series = _fx_series_for_currencies(
        [base_currency, *(row.get("currency") for row in positions)],
        start,
        end,
    )
    asset_series = []
    sources = []
    for row in positions:
        raw_series, source = _download_adjusted_close(row["symbol"], start, end)
        currency = str(row.get("currency") or "USD").upper()
        if not raw_series:
            raise HTTPException(status_code=400, detail=f"{row['ticker']} price series is empty")
        if currency != "USD" and not fx_series.get(currency):
            raise HTTPException(status_code=400, detail=f"{row['ticker']} FX series is unavailable")
        if base_currency != "USD" and not fx_series.get(base_currency):
            raise HTTPException(status_code=400, detail=f"Base currency {base_currency} FX series is unavailable")
        asset_series.append({**row, "series": raw_series})
        sources.append({"ticker": row["ticker"], "symbol": row["symbol"], "currency": row.get("currency"), "source": source})
    price_rows, alignment_fx_coverage = _aligned_native_price_rows_with_fx(asset_series, base_currency, fx_series)
    if len(price_rows) < 3:
        raise HTTPException(status_code=400, detail="Not enough overlapping price data for backtest")
    weights = {item["symbol"]: _float_value(item.get("weight"), 0.0) for item in asset_series}
    try:
        values, increments = _run_weight_backtest(price_rows, weights, initial_value, rebalance, include_increments=True)
    except BacktestCalculationLimitError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    benchmark_values = []
    benchmark = None
    benchmark_comparison = {
        "status": "unavailable", "comparisonStart": None, "comparisonEnd": None,
        "observations": 0, "reason": "benchmark_not_requested",
    }
    comparable_portfolio_values = []
    if benchmark_ticker:
        try:
            resolved_benchmark = resolve_portfolio_ticker(benchmark_ticker)
            benchmark_symbol = resolved_benchmark.get("symbol") or portfolio_symbol(benchmark_ticker)
            benchmark_currency = str(resolved_benchmark.get("currency") or fallback_currency(benchmark_symbol)).upper()
            raw_benchmark, source = _download_adjusted_close(benchmark_symbol, start, end)
            benchmark_fx_currencies = [
                currency for currency in {benchmark_currency, base_currency}
                if currency != "USD" and currency not in fx_series
            ]
            if benchmark_fx_currencies:
                # Benchmark-only provider work stays inside this guarded path:
                # an unavailable comparison must not discard a valid portfolio run.
                fx_series.update(_fx_series_for_currencies(benchmark_fx_currencies, start, end))
            simulation_dates = [row["date"] for row in values]
            if benchmark_currency != "USD" and not fx_series.get(benchmark_currency):
                raise ValueError("benchmark_fx_series_unavailable")
            benchmark_rows, benchmark_fx_by_symbol = _aligned_native_price_rows_with_fx(
                [{"symbol": "benchmark", "currency": benchmark_currency, "series": raw_benchmark}],
                base_currency,
                fx_series,
                simulation_dates=simulation_dates,
            )
            benchmark_fx_coverage = benchmark_fx_by_symbol.get("benchmark")
            comparable_dates = {row["date"] for row in benchmark_rows}
            comparable_portfolio_values = [row for row in values if row["date"] in comparable_dates]
            if len(benchmark_rows) >= 2 and len(comparable_portfolio_values) == len(benchmark_rows):
                benchmark_values = _run_weight_backtest(benchmark_rows, {"benchmark": 1.0}, initial_value, "none")
                benchmark_comparison = {
                    "status": "comparable",
                    "comparisonStart": benchmark_values[0]["date"],
                    "comparisonEnd": benchmark_values[-1]["date"],
                    "observations": len(benchmark_values),
                }
            else:
                benchmark_comparison = {
                    "status": "unavailable", "comparisonStart": None, "comparisonEnd": None,
                    "observations": len(benchmark_rows), "reason": "benchmark_has_no_comparable_two_observation_period",
                }
            benchmark = {
                "ticker": benchmark_ticker, "symbol": benchmark_symbol,
                "name": resolved_benchmark.get("name") or benchmark_ticker, "source": source,
                "status": benchmark_comparison["status"], "fxCoverage": benchmark_fx_coverage,
                "coverage": {
                    "ticker": benchmark_ticker, "symbol": benchmark_symbol, "currency": benchmark_currency,
                    "included": benchmark_comparison["status"] == "comparable",
                    "actualStart": _series_coverage(raw_benchmark, simulation_dates)["actualStart"],
                    "actualEnd": _series_coverage(raw_benchmark, simulation_dates)["actualEnd"],
                    "simulationStart": values[0]["date"], "simulationEnd": values[-1]["date"],
                    "price": {key: _series_coverage(raw_benchmark, simulation_dates)[key] for key in ("observedDays", "forwardFilledDays", "trailingForwardFilledDays", "coverage")},
                    "fx": benchmark_fx_coverage,
                    "unavailableReasons": [] if benchmark_comparison["status"] == "comparable" else [benchmark_comparison.get("reason")],
                },
            }
        except Exception:
            # A benchmark adds context but must not turn a complete asset/FX
            # simulation into an empty result.  Comparison metrics spell out why.
            benchmark = {"ticker": benchmark_ticker, "status": "unavailable"}
            benchmark_comparison = {
                "status": "unavailable", "comparisonStart": None, "comparisonEnd": None,
                "observations": 0, "reason": "benchmark_data_unavailable",
            }
    try:
        metrics = _backtest_analysis_call(_portfolio_metrics, values, [])
    except BacktestCalculationLimitError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    if benchmark_comparison.get("status") == "comparable":
        try:
            comparable_metrics = _backtest_analysis_call(_portfolio_metrics, comparable_portfolio_values, benchmark_values)
            standalone_benchmark_metrics = _backtest_analysis_call(_portfolio_metrics, benchmark_values, [])
        except BacktestCalculationLimitError as exc:
            raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
        benchmark_metric_names = {
            "benchmarkTotalReturn", "excessReturn", "beta", "alpha", "correlation", "rSquared",
            "trackingError", "informationRatio", "treynor", "upCapture", "downCapture",
        }
        for name in benchmark_metric_names:
            metrics[name] = comparable_metrics.get(name)
            if name in comparable_metrics.get("metricUnavailableReasons", {}):
                metrics.setdefault("metricUnavailableReasons", {})[name] = comparable_metrics["metricUnavailableReasons"][name]
            else:
                metrics.setdefault("metricUnavailableReasons", {}).pop(name, None)
        metrics["benchmarkComparablePortfolioTotalReturn"] = comparable_metrics.get("totalReturn")
        metrics["benchmarkComparablePortfolioCagr"] = comparable_metrics.get("cagr")
        metrics["benchmarkComparablePortfolioVolatility"] = comparable_metrics.get("volatility")
        metrics["benchmarkComparablePortfolioMaxDrawdown"] = comparable_metrics.get("maxDrawdown")
        metrics["benchmarkComparablePortfolioSharpe"] = comparable_metrics.get("sharpe")
        metrics["benchmarkComparableVolatility"] = standalone_benchmark_metrics.get("volatility")
        metrics["benchmarkComparableMaxDrawdown"] = standalone_benchmark_metrics.get("maxDrawdown")
        metrics["benchmarkComparableSharpe"] = standalone_benchmark_metrics.get("sharpe")
    try:
        drawdown_series, drawdown_episodes = _backtest_analysis_call(drawdown_analysis, values)
    except BacktestCalculationLimitError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    simulation_dates = [row["date"] for row in values]
    coverage_positions = []
    for item in asset_series:
        price_coverage = _series_coverage(item.get("series"), simulation_dates)
        fx_coverage = dict(alignment_fx_coverage.get(item.get("symbol")) or {})
        fx_coverage.setdefault("actualStart", None)
        fx_coverage.setdefault("actualEnd", None)
        coverage_positions.append({
            "ticker": item.get("ticker"), "symbol": item.get("symbol"), "currency": item.get("currency"),
            "included": True, "actualStart": price_coverage["actualStart"], "actualEnd": price_coverage["actualEnd"],
            "simulationStart": values[0]["date"], "simulationEnd": values[-1]["date"],
            "price": {key: price_coverage[key] for key in ("observedDays", "forwardFilledDays", "trailingForwardFilledDays", "coverage")},
            "fx": fx_coverage, "unavailableReasons": [],
        })
    data_coverage = {
        "status": "complete",
        "positions": coverage_positions,
        "benchmark": benchmark.get("coverage") if isinstance(benchmark, dict) else None,
        "unavailableMetrics": [
            {"metric": name, "reason": reason}
            for name, reason in sorted((metrics.get("metricUnavailableReasons") or {}).items())
        ],
    }
    result = {
        "analysisVersion": ANALYSIS_VERSION,
        "id": hashlib.sha256(f"{preset.get('id')}:{start}:{end}:{rebalance}:{base_currency}:{now_iso()}".encode("utf-8")).hexdigest()[:16],
        "name": f"{preset.get('name', 'Preset')} 백테스트",
        "presetId": preset.get("id"),
        "presetName": preset.get("name"),
        "start": values[0]["date"],
        "end": values[-1]["date"],
        "requestedStart": start,
        "requestedEnd": end,
        "baseCurrency": base_currency,
        "initialValue": initial_value,
        "rebalance": rebalance,
        "benchmark": benchmark,
        "metrics": metrics,
        "series": values,
        "benchmarkSeries": benchmark_values,
        "yearlyReturns": _period_returns(values, "year"),
        "monthlyReturns": _period_returns(values, "month"),
        "assetContributions": _backtest_analysis_call(_actual_asset_contributions, asset_series, increments, initial_value, price_rows),
        "contributionMethod": "actual_simulation_increment_over_initial_value",
        "riskContributions": _backtest_analysis_call(_asset_risk_contributions, asset_series, price_rows, weights, benchmark_values),
        "riskContributionMethod": "static_target_weight_sample_covariance_approximation",
        "rollingMetrics": _backtest_analysis_call(_rolling_metrics, values, benchmark_values, 252),
        "drawdownSeries": drawdown_series,
        "drawdownEpisodes": drawdown_episodes,
        "benchmarkComparison": benchmark_comparison,
        "dataCoverage": data_coverage,
        "calculationBasis": {
            "riskFreeRate": {"annual": RISK_FREE_RATE_ANNUAL, "source": "fixed_assumption", "method": "constant_annual_zero"},
            "annualization": {"tradingDays": TRADING_DAYS_PER_YEAR},
            "returnMethod": "adjusted_close_daily",
            "priceAlignment": {
                "method": "native_price_forward_fill_then_asof_fx_mark_no_reweighting",
                "fxValuation": "latest_asof_fx_is_applied_on_each_simulation_date_after_native_price_carry",
                "simulationStart": values[0]["date"], "simulationEnd": values[-1]["date"],
                "observations": len(values), **_strict_common_observation_window(asset_series),
            },
            "periodReturnMethod": "boundary_value_with_preceding_observation_baseline",
        },
        "positions": [{k: v for k, v in row.items() if k != "series"} for row in asset_series],
        "sources": sources + ([{"ticker": benchmark_ticker, "symbol": benchmark.get("symbol"), "source": benchmark.get("source")}] if benchmark else []),
        "assumptions": [
            "yfinance auto_adjust=True 조정 종가를 사용합니다.",
            "배당과 분할은 조정가격에 반영된 것으로 간주합니다.",
            "수수료, 세금, 슬리피지, 체결오차는 제외합니다.",
            "비USD 자산은 일자별 USD/통화 환율을 거쳐 기준 통화로 환산합니다.",
            "가격과 환율의 관측일 공백은 최초 관측 이후에만 직전 값을 사용하며, coverage에 횟수를 남깁니다.",
            "무위험수익률은 연 0% 고정 가정이며, 샤프·알파는 표본 일간수익률 기준입니다.",
        ],
        "createdAt": now_iso(),
    }
    try:
        _raise_on_nonfinite_backtest_value(result)
        result["interpretation"] = deterministic_interpretation(result)
        _raise_on_nonfinite_backtest_value(result)
    except BacktestCalculationLimitError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    if save_result:
        BACKTESTS_DIR.mkdir(parents=True, exist_ok=True)
        result["savedAt"] = now_iso()
        write_json(BACKTESTS_DIR / f"{result['id']}.json", result)
    return result


def save_portfolio_backtest_result(body):
    data = body if isinstance(body, dict) else {}
    result = data.get("result") if isinstance(data.get("result"), dict) else data
    if not isinstance(result, dict):
        raise HTTPException(status_code=400, detail="Backtest result is required")
    if result.get("type") == "comparison":
        if not isinstance(result.get("results"), list) or not result.get("results"):
            raise HTTPException(status_code=400, detail="Comparison result is empty")
    elif not isinstance(result.get("metrics"), dict) or not isinstance(result.get("series"), list):
        raise HTTPException(status_code=400, detail="Backtest result is incomplete")
    result = dict(result)
    try:
        _raise_on_nonfinite_backtest_value(result)
    except BacktestCalculationLimitError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    result_id = str(result.get("id") or "").strip()
    if not result_id:
        basis = f"{result.get('name')}:{result.get('start')}:{result.get('end')}:{now_iso()}"
        result_id = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    result["id"] = re.sub(r"[^A-Za-z0-9_-]", "", result_id)[:40] or hashlib.sha256(now_iso().encode("utf-8")).hexdigest()[:16]
    result["savedAt"] = now_iso()
    result.setdefault("createdAt", result["savedAt"])
    BACKTESTS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(BACKTESTS_DIR / f"{result['id']}.json", result)
    return result


def run_portfolio_backtest_comparison(body):
    data = body if isinstance(body, dict) else {}
    preset_ids = [str(item).strip() for item in data.get("presetIds", []) if str(item).strip()]
    preset_ids = list(dict.fromkeys(preset_ids))
    draft_presets = [item for item in data.get("presets", []) if isinstance(item, dict)]
    if len(preset_ids) + len(draft_presets) < 2:
        raise HTTPException(status_code=400, detail="Select or create at least two portfolio drafts to compare")
    results = []
    errors = []
    for preset_id in preset_ids:
        try:
            payload = {**data, "presetId": preset_id}
            results.append(run_portfolio_backtest(payload, save_result=False))
        except Exception:
            preset = get_portfolio_preset(preset_id) or {}
            errors.append({"presetId": preset_id, "presetName": preset.get("name") or preset_id, "error": "backtest_failed"})
    for index, preset in enumerate(draft_presets, start=1):
        draft_name = str(preset.get("name") or f"비교 초안 {index}").strip()
        try:
            payload = {**data, "presetId": "", "preset": {**preset, "name": draft_name}}
            results.append(run_portfolio_backtest(payload, save_result=False))
        except Exception:
            errors.append({"presetId": str(preset.get("id") or f"draft-{index}"), "presetName": draft_name, "error": "backtest_failed"})
    if not results:
        raise HTTPException(status_code=400, detail="No comparable backtest result could be generated")
    first = results[0]
    benchmark_candidates = [item.get("benchmark") for item in results if isinstance(item.get("benchmark"), dict)]
    shared_benchmark = None
    if len(benchmark_candidates) == len(results) and benchmark_candidates:
        identities = {
            (str(item.get("ticker") or ""), str(item.get("symbol") or ""), str(item.get("status") or ""))
            for item in benchmark_candidates
        }
        if len(identities) == 1:
            # All comparison legs used the same explicitly returned benchmark
            # basis.  A mixed set intentionally has no top-level benchmark.
            shared_benchmark = dict(benchmark_candidates[0])
    return {
        "type": "comparison",
        "id": hashlib.sha256(f"compare:{','.join(preset_ids)}:{len(draft_presets)}:{data.get('start')}:{data.get('end')}:{now_iso()}".encode("utf-8")).hexdigest()[:16],
        "name": "포트폴리오 비교 백테스트",
        "presetIds": preset_ids,
        "draftCount": len(draft_presets),
        "start": first.get("start"),
        "end": first.get("end"),
        "requestedStart": first.get("requestedStart"),
        "requestedEnd": first.get("requestedEnd"),
        "baseCurrency": first.get("baseCurrency"),
        "initialValue": first.get("initialValue"),
        "rebalance": first.get("rebalance"),
        "benchmark": shared_benchmark,
        "results": results,
        "errors": errors,
        "assumptions": first.get("assumptions", []),
        "createdAt": now_iso(),
    }


def list_portfolio_backtests():
    if not BACKTESTS_DIR.exists():
        return []
    items = []
    for path in sorted(BACKTESTS_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        data = read_json(path, {})
        if isinstance(data, dict):
            items.append({
                "id": data.get("id") or path.stem,
                "name": data.get("name") or path.stem,
                "presetName": data.get("presetName", ""),
                "type": data.get("type", "single"),
                "start": data.get("start", ""),
                "end": data.get("end", ""),
                "baseCurrency": data.get("baseCurrency", ""),
                "initialValue": data.get("initialValue"),
                "rebalance": data.get("rebalance"),
                "benchmark": data.get("benchmark"),
                "createdAt": data.get("createdAt", ""),
                "savedAt": data.get("savedAt", ""),
                "metrics": data.get("metrics", {}),
                "resultCount": len(data.get("results", [])) if isinstance(data.get("results"), list) else 1,
            })
    return items


def _portfolio_backtest_path(backtest_id):
    identifier = str(backtest_id or "")
    if not BACKTEST_ID_RE.fullmatch(identifier):
        return None
    root = os.path.realpath(BACKTESTS_DIR)
    path = os.path.realpath(os.path.join(root, f"{identifier}.json"))
    if not path.startswith(root + os.sep):
        return None
    return Path(path)


def get_portfolio_backtest(backtest_id):
    path = _portfolio_backtest_path(backtest_id)
    if path is None:
        return None
    if not path.exists():
        return None
    return read_json(path, None)


def delete_portfolio_backtest(backtest_id):
    identifier = str(backtest_id or "")
    path = _portfolio_backtest_path(identifier)
    if path is None:
        return {"deleted": False, "id": identifier}
    if path.exists():
        path.unlink()
        return {"deleted": True, "id": identifier}
    return {"deleted": False, "id": identifier}
