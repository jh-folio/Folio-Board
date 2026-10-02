"""Explicit source collection for one calculation (the only IO of the price calculation).

Every call here happens because the person pressed `계산` or a company analysis was
generated; reading a snapshot never comes here. Sources that carry exact
decimals (SEC company facts) are fetched and parsed here rather than through the
float-parsing caches. Providers are injectable so tests and audits replay saved
packets. The result feeds `assemble()` unchanged.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from features.company_analysis import dart_client, sec_filings, sec_companyfacts
from features.company_analysis.market_identity import market_identity
from features.company_analysis.risk_free import risk_free_as_of

from .beta import measure_beta
from .decimal_ops import load_source_json
from .prices import fetch_daily_history

SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
DART_API = "https://opendart.fss.or.kr/api/{endpoint}.json"
DART_YEAR_ENDPOINTS = ("fnlttSinglAcntAll", "stockTotqySttus", "alotMatter", "irdsSttus")
KR_REPORT_YEARS = 8
DECISION_LOOKBACK_YEARS = 11


class CollectionError(Exception):
    """A required source could not be obtained; `.code` is a stable enum for the job and the API."""

    def __init__(self, code: str, sub_code: str | None = None):
        super().__init__(code)
        self.code, self.sub_code = code, sub_code


def _sec_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": sec_companyfacts.sec_user_agent(), "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(request, timeout=int(os.environ.get("SEC_TIMEOUT_SECONDS", "30"))) as response:
        raw = response.read()
    return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


def _dart_get(endpoint: str, params: dict) -> dict:
    query = urllib.parse.urlencode({"crtfc_key": dart_client.dart_api_key(), **params})
    request = urllib.request.Request(f"{DART_API.format(endpoint=endpoint)}?{query}", headers={"User-Agent": "MarketResearchArchive/0.1"})
    with urllib.request.urlopen(request, timeout=int(os.environ.get("DART_TIMEOUT_SECONDS", "30"))) as response:
        return json.loads(response.read().decode("utf-8"))


class Collector:
    def __init__(self, data_root, *, now: Callable[[], dt.datetime] | None = None, sec_bytes=None, dart_get=None,
                 fetch_daily=None, beta_of=None, risk_free_of=None, cancel: Callable[[], None] = lambda: None,
                 progress: Callable[..., None] | None = None):
        self.root = Path(data_root)
        self.now = now or (lambda: dt.datetime.now(dt.timezone.utc))
        self.sec_bytes, self.dart_get = sec_bytes or _sec_bytes, dart_get or _dart_get
        self.fetch_daily, self.beta_of = fetch_daily or fetch_daily_history, beta_of or measure_beta
        self.risk_free_of = risk_free_of or (lambda session, currency: risk_free_as_of(
            session, currency, api_key=os.environ.get("FRED_API_KEY", "").strip()))
        self.cancel, self.progress = cancel, progress or (lambda **_: None)

    @property
    def cache(self) -> Path:
        return self.root / "sec-cache"

    @property
    def dart_cache(self) -> Path:
        return self.root / "dart-cache"

    def collect(self, market: str, ticker: str) -> dict:
        ticker = str(ticker or "").strip().upper()
        if market == "US" and re.fullmatch(r"[A-Z0-9.\-]{1,10}", ticker):
            return self._collect_us(ticker)
        if market == "KR" and re.fullmatch(r"\d{6}", ticker):
            return self._collect_kr(ticker)
        raise CollectionError("instrument_not_supported")

    # --- shared tail: price, rates, beta ---------------------------------------

    def _tail(self, raw: dict, currency: str) -> dict:
        self.cancel()
        session = raw["daily"]["price"]["sessionDate"]
        self.progress(message="무위험수익률과 베타를 확인하고 있습니다.")
        observed = self.risk_free_of(session, currency)
        raw["riskFree"] = {**observed, "fetchedAt": self.now().isoformat()}
        raw["beta"] = self.beta_of(raw["daily"]["price"]["providerSymbol"])
        return raw

    # --- US --------------------------------------------------------------------

    def _collect_us(self, ticker: str) -> dict:
        self.cancel()
        company = {"ticker": ticker, "market": "US"}
        cik = sec_companyfacts.resolve_cik(company, self.cache)
        if not cik:
            raise CollectionError("company_not_found", "no_cik")
        self.progress(message="SEC 공시 원자료를 읽고 있습니다.")
        try:
            facts = load_source_json(self.sec_bytes(SEC_FACTS_URL.format(cik=cik)))
        except Exception:  # noqa: BLE001 - provider failure is a stable code, never a message
            raise CollectionError("financial_history_unavailable", "sec_companyfacts_failed") from None
        self.cancel()
        submissions, _ = sec_filings.get_company_submissions(cik, self.cache)
        annual = sec_filings.latest_annual_report_metadata(cik, self.cache)
        if not submissions or not annual.get("ok"):
            raise CollectionError("financial_history_unavailable", "annual_report_not_found")
        markup, error = sec_filings.fetch_text(annual["url"], self.cache / "filings" / f"{cik}-{annual['accession'].replace('-', '')}.json")
        if not markup:
            raise CollectionError("financial_history_unavailable", "annual_report_text_unavailable")
        self.cancel()
        self.progress(message="완결 거래일 종가와 사건을 읽고 있습니다.")
        try:
            daily = self.fetch_daily(ticker, "US", {}, now=self.now())
        except Exception:  # noqa: BLE001
            raise CollectionError("price_unavailable") from None
        exchanges = submissions.get("exchanges") or []
        raw = {"market": "US", "ticker": ticker, "now": self.now().isoformat(),
               "identity": {"providerSymbol": daily["price"]["providerSymbol"], "exchangeSource": daily["exchangeSource"],
                            "exchange": exchanges[0] if exchanges else None, "cik": cik},
               "daily": daily, "companyfacts": facts, "submissions": submissions, "annualMarkup": markup,
               "annualAccession": annual["accession"], "annualForm": annual["form"]}
        return self._tail(raw, "USD")

    # --- KR --------------------------------------------------------------------

    def _collect_kr(self, ticker: str) -> dict:
        self.cancel()
        if not dart_client.dart_api_key():
            raise CollectionError("source_credential_missing", "dart")
        identity = market_identity({"ticker": ticker, "market": "KR"}, self.dart_cache)
        if not identity.get("ok"):
            raise CollectionError("company_not_found", identity.get("reason"))
        corp_code, profile = identity["corpCode"], identity["profile"]
        self.cancel()
        self.progress(message="완결 거래일 종가와 사건을 읽고 있습니다.")
        try:
            daily = self.fetch_daily(ticker, "KR", profile, now=self.now())
        except Exception:  # noqa: BLE001
            raise CollectionError("price_unavailable") from None
        today = self.now().date()
        packets: dict[str, dict[int, dict]] = {name: {} for name in DART_YEAR_ENDPOINTS}
        # The current year is included: a March fiscal year closes in the same calendar year it is filed.
        # A report that is not filed yet answers status 013 and is skipped downstream.
        for year in range(today.year - KR_REPORT_YEARS + 1, today.year + 1):
            for endpoint in DART_YEAR_ENDPOINTS:
                self.cancel()
                self.progress(message=f"DART {year}년 사업보고서의 {endpoint}를 읽고 있습니다.")
                params = {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": "11011"}
                if endpoint == "fnlttSinglAcntAll":
                    params["fs_div"] = "CFS"
                try:
                    packets[endpoint][year] = self.dart_get(endpoint, params)
                except Exception:  # noqa: BLE001
                    raise CollectionError("financial_history_unavailable", f"dart_{endpoint}_failed") from None
        begin = today.replace(year=today.year - DECISION_LOOKBACK_YEARS) if not (today.month == 2 and today.day == 29) else today.replace(year=today.year - DECISION_LOOKBACK_YEARS, day=28)
        try:
            bonus = self.dart_get("fricDecsn", {"corp_code": corp_code, "bgn_de": begin.strftime("%Y%m%d"), "end_de": today.strftime("%Y%m%d")})
        except Exception:  # noqa: BLE001
            raise CollectionError("financial_history_unavailable", "dart_fricDecsn_failed") from None
        batches, latest_rows, dividends, stock_totqy, irds = [], [], [], {}, {}
        for year in sorted(packets["fnlttSinglAcntAll"]):
            financial, stock = packets["fnlttSinglAcntAll"][year], packets["stockTotqySttus"][year]
            if financial.get("status") == stock.get("status") == "000":
                ends = {row["stlm_dt"] for row in stock.get("list", []) if row.get("stlm_dt")}
                if len(ends) == 1:
                    batches.append({"basis": "CFS", "periodEnd": ends.pop(), "periodEndSource": f"stockTotqySttus:{year}:stlm_dt",
                                    "rows": financial["list"]})
                    latest_rows = financial["list"]
            dividends.append(packets["alotMatter"][year])
            stock_totqy[str(year)] = stock
            irds[str(year)] = packets["irdsSttus"][year]
        raw = {"market": "KR", "ticker": ticker, "now": self.now().isoformat(),
               "identity": {"providerSymbol": identity["providerSymbol"], "exchangeSource": identity["exchangeSource"],
                            "exchange": identity["exchange"], "corpCode": corp_code},
               "daily": daily,
               "dart": {"profile": profile, "batches": batches, "dividends": dividends, "latestFinancialRows": latest_rows,
                        "stockTotqy": stock_totqy, "irds": irds, "bonus": bonus,
                        "coverage": {"state": "confirmed", "start": max(begin.isoformat(), daily["request"]["start"]),
                                     "end": today.isoformat()},
                        "unitBases": {}}}
        return self._tail(raw, "KRW")
