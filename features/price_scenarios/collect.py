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
from concurrent.futures import CancelledError

from features.company_analysis import dart_client, sec_filings, sec_companyfacts
from features.company_analysis.market_identity import market_identity
from features.company_analysis.risk_free import risk_free_as_of
from features.common.atomic_replace import write_bytes_atomic

from .beta import measure_beta
from .decimal_ops import load_source_json
from .prices import fetch_daily_history, fetch_instrument_type, provider_failure

SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_FUNDS_URL = "https://www.sec.gov/files/company_tickers_mf.json"
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
                 fetch_daily=None, instrument_type=None, beta_of=None, risk_free_of=None, cancel: Callable[[], None] = lambda: None,
                 progress: Callable[..., None] | None = None):
        self.root = Path(data_root)
        self.now = now or (lambda: dt.datetime.now(dt.timezone.utc))
        self.sec_bytes, self.dart_get = sec_bytes or _sec_bytes, dart_get or _dart_get
        self.fetch_daily, self.beta_of = fetch_daily or fetch_daily_history, beta_of or measure_beta
        self.instrument_type = instrument_type or fetch_instrument_type
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
        if market == "KR" and re.fullmatch(r"[0-9][A-Z0-9]{5}", ticker):
            return self._collect_kr(ticker)
        raise CollectionError("instrument_not_supported")

    # --- shared tail: price, rates, beta ---------------------------------------

    def _is_fund(self, ticker: str, market: str) -> bool:
        kinds = []
        for symbol in ([ticker] if market == "US" else [ticker + ".KS", ticker + ".KQ"]):
            self.cancel()
            try:
                kinds.append(self.instrument_type(symbol))
            except CancelledError:
                raise
            except Exception:  # a failed type lookup keeps the official identification failure
                kinds.append(None)
        found = {str(kind).upper() for kind in kinds if kind}
        if bool(found) and found <= {"ETF", "MUTUALFUND"}:
            return True
        return self._sec_fund(ticker) if market == "US" else False

    def _sec_fund(self, ticker: str) -> bool:
        """Exact official fund symbol, only after the missing-company type probe."""
        self.cancel()
        path = self.cache / "company_tickers_mf.json"
        try:
            cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            fetched = dt.datetime.fromisoformat(cached.get("fetchedAt", ""))
            fresh = dt.timedelta(0) <= self.now() - fetched < dt.timedelta(days=7)
        except (ValueError, TypeError, OSError):
            cached, fresh = {}, False
        packet = cached.get("data") if fresh else None
        if packet is None:
            try:
                packet = json.loads(self.sec_bytes(SEC_FUNDS_URL))
                self.cancel()
                path.parent.mkdir(parents=True, exist_ok=True)
                write_bytes_atomic(path, json.dumps({"fetchedAt": self.now().isoformat(), "data": packet}).encode("utf-8"))
            except CancelledError:
                raise
            except Exception:
                return False  # no stale fallback or retries after an unsuccessful lookup
        if (not isinstance(packet, dict) or not isinstance(packet.get("fields"), list)
                or not isinstance(packet.get("data"), list) or "symbol" not in packet["fields"]):
            return False
        index = packet["fields"].index("symbol")
        return any(isinstance(row, list) and len(row) > index and row[index] == ticker
                   for row in packet.get("data", []))

    def _tail(self, raw: dict, currency: str) -> dict:
        self.cancel()
        session = raw["daily"]["price"]["sessionDate"]
        self.progress(message="무위험수익률과 베타를 확인하고 있습니다.")
        observed = self.risk_free_of(session, currency)
        raw["riskFree"] = {**observed, "fetchedAt": self.now().isoformat()}
        raw["beta"] = self.beta_of(raw["daily"]["price"]["providerSymbol"])
        return raw

    # --- US --------------------------------------------------------------------

    def _class_filings(self, facts, submissions, annual, markup, daily, cik, ticker):
        from .class_history import listed_class
        from .history import sec_history
        from .securities import listed_security
        security = listed_security(markup, ticker, accession=annual["accession"])
        session = daily["price"]["sessionDate"]
        history = sec_history(facts, as_of=session)
        years = {r["fiscalYear"] for r in history["rows"]}
        if (annual["form"] not in {"10-K", "10-K/A"} or not listed_class(security) or not years
                or any(r["metric"] == "EPS Diluted" and r["fiscalYear"] == max(years) for r in history["rows"])):
            return None
        metadata = []
        def add(recent):
            for i, form in enumerate(recent.get("form", [])):
                if form not in {"10-K", "10-K/A"}:
                    continue
                try:
                    filed, accession, doc = (recent[k][i] for k in ("filingDate", "accessionNumber", "primaryDocument"))
                except (KeyError, IndexError):
                    continue
                if filed <= session and re.fullmatch(r"[0-9-]+", accession) and re.fullmatch(r"[A-Za-z0-9_.-]+", doc):
                    metadata.append({"form": form, "filed": filed, "accession": accession,
                                     "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{doc}"})
        add(submissions.get("filings", {}).get("recent", {}))
        for archive in sorted(submissions.get("filings", {}).get("files", []), key=lambda f: f.get("filingTo", ""), reverse=True):
            if len({m["accession"] for m in metadata}) >= 4:
                break
            self.cancel()
            name = archive.get("name", "")
            if not re.fullmatch(r"CIK[0-9]+-submissions-[0-9]+\.json", name):
                continue
            text, _ = sec_filings.fetch_text("https://data.sec.gov/submissions/" + name, self.cache / "submissions" / name)
            try:
                add(json.loads(text))
            except (ValueError, TypeError):
                return [{"form": "10-K", "filed": session, "accession": "unavailable", "markup": ""}]
        selected = sorted({m["accession"]: m for m in metadata}.values(), key=lambda m: (m["filed"], m["accession"]), reverse=True)[:4]
        packets = []
        for item in selected:
            self.cancel()
            text = markup if item["accession"] == annual["accession"] else sec_filings.fetch_text(
                item["url"], self.cache / "filings" / f"{cik}-{item['accession'].replace('-', '')}.json")[0]
            packet = {**item, "markup": text}
            self._class_labels(packet, security)
            packets.append(packet)
        return packets

    def _class_labels(self, packet, security):
        """Resolve an issuer extension only through its official label linkbase."""
        from bs4 import BeautifulSoup
        from .class_history import read_class_filing
        # Standard members need no extra taxonomy requests.
        parsed = read_class_filing(packet, security, cik=packet["url"].split("/")[-3], currency="USD")
        if parsed["reason"] is None:
            return
        soup = BeautifulSoup(packet.get("markup", ""), "html.parser")
        schemas = {t.get("xlink:href") for t in soup.find_all("link:schemaref") if t.get("xlink:href")}
        base = packet["url"].rsplit("/", 1)[0] + "/"
        schema_urls = {urllib.parse.urljoin(packet["url"], href) for href in schemas}
        schema_urls = {url for url in schema_urls if url.startswith(base) and url.endswith(".xsd")}
        if len(schema_urls) != 1:
            return
        schema_url = next(iter(schema_urls))
        self.cancel()
        xsd, _ = sec_filings.fetch_text(schema_url, self.cache / "filings" / (packet["accession"].replace("-", "") + "-schema.json"))
        xml = BeautifulSoup(xsd, "xml")
        label_urls = {urllib.parse.urljoin(schema_url, t.get("xlink:href", "")) for t in xml.find_all("linkbaseRef")
                      if t.get("xlink:role") == "http://www.xbrl.org/2003/role/labelLinkbaseRef"}
        label_urls = {url for url in label_urls if url.startswith(base)}
        if len(label_urls) != 1:
            return
        url = next(iter(label_urls))
        self.cancel()
        labels, _ = sec_filings.fetch_text(url, self.cache / "filings" / (packet["accession"].replace("-", "") + "-labels.json"))
        from .class_labels import official_labels
        packet["labels"] = official_labels(packet["markup"], xsd, labels)
        packet["labelSources"] = [{"schemaUrl": schema_url, "labelUrl": url}]

    def _collect_us(self, ticker: str) -> dict:
        self.cancel()
        company = {"ticker": ticker, "market": "US"}
        cik = sec_companyfacts.resolve_cik(company, self.cache)
        if not cik:
            if self._is_fund(ticker, "US"):
                raise CollectionError("fund_not_supported")
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
            # The submissions carry the official exchanges/tickers that identify the listing.
            daily = self.fetch_daily(ticker, "US", submissions, now=self.now())
        except ValueError as error:
            raise CollectionError("price_unavailable", str(error) if str(error) in {"exchange_unknown", "instrument_not_in_submissions", "price_unavailable"} else None) from None
        except CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            raise CollectionError("price_unavailable", "provider_error" if provider_failure(error) else None) from None
        exchanges = submissions.get("exchanges") or []
        raw = {"market": "US", "ticker": ticker, "now": self.now().isoformat(),
               "identity": {"providerSymbol": daily["price"]["providerSymbol"], "exchangeSource": daily["exchangeSource"],
                            "exchange": exchanges[0] if exchanges else None, "cik": cik},
               "daily": daily, "companyfacts": facts, "submissions": submissions, "annualMarkup": markup,
               "annualAccession": annual["accession"], "annualForm": annual["form"]}
        filings = self._class_filings(facts, submissions, annual, markup, daily, cik, ticker)
        if filings is not None:
            raw["annualFilings"] = filings
        return self._tail(raw, "USD")

    # --- KR --------------------------------------------------------------------

    def _dart_year(self, endpoint: str, corp_code: str, year: int, fs_div: str | None) -> dict:
        self.cancel()
        self.progress(message=f"DART {year}년 사업보고서의 {endpoint}를 읽고 있습니다.")
        params = {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": "11011", **({"fs_div": fs_div} if fs_div else {})}
        try:
            return self.dart_get(endpoint, params)
        except Exception:  # noqa: BLE001
            raise CollectionError("financial_history_unavailable", f"dart_{endpoint}_failed") from None

    @staticmethod
    def _statement_batches(financials: dict, stocks: dict, basis: str):
        batches, latest_rows = [], []
        for year in sorted(financials):
            financial, stock = financials[year], stocks[year]
            if financial.get("status") == stock.get("status") == "000":
                ends = {row["stlm_dt"] for row in stock.get("list", []) if row.get("stlm_dt")}
                if len(ends) == 1:
                    batches.append({"basis": basis, "periodEnd": ends.pop(), "periodEndSource": f"stockTotqySttus:{year}:stlm_dt",
                                    "rows": financial["list"]})
                    latest_rows = financial["list"]
        return batches, latest_rows

    def _collect_kr(self, ticker: str) -> dict:
        self.cancel()
        if not dart_client.dart_api_key():
            raise CollectionError("source_credential_missing", "dart")
        identity = market_identity({"ticker": ticker, "market": "KR"}, self.dart_cache)
        if not identity.get("ok"):
            if self._is_fund(ticker, "KR"):
                raise CollectionError("fund_not_supported")
            raise CollectionError("company_not_found", identity.get("reason"))
        corp_code, profile = identity["corpCode"], identity["profile"]
        self.cancel()
        self.progress(message="완결 거래일 종가와 사건을 읽고 있습니다.")
        try:
            daily = self.fetch_daily(ticker, "KR", profile, now=self.now())
        except ValueError as error:
            raise CollectionError("price_unavailable", str(error) if str(error) in {"exchange_not_supported", "price_unavailable"} else None) from None
        except CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            raise CollectionError("price_unavailable", "provider_error" if provider_failure(error) else None) from None
        today = self.now().date()
        years = range(today.year - KR_REPORT_YEARS + 1, today.year + 1)
        packets: dict[str, dict[int, dict]] = {name: {} for name in DART_YEAR_ENDPOINTS}
        # The current year is included: a March fiscal year closes in the same calendar year it is filed.
        # A report that is not filed yet answers status 013 and is skipped downstream.
        for year in years:
            for endpoint in DART_YEAR_ENDPOINTS:
                packets[endpoint][year] = self._dart_year(endpoint, corp_code, year, "CFS" if endpoint == "fnlttSinglAcntAll" else None)
        begin = today.replace(year=today.year - DECISION_LOOKBACK_YEARS) if not (today.month == 2 and today.day == 29) else today.replace(year=today.year - DECISION_LOOKBACK_YEARS, day=28)
        try:
            bonus = self.dart_get("fricDecsn", {"corp_code": corp_code, "bgn_de": begin.strftime("%Y%m%d"), "end_de": today.strftime("%Y%m%d")})
        except Exception:  # noqa: BLE001
            raise CollectionError("financial_history_unavailable", "dart_fricDecsn_failed") from None
        batches, latest_rows = self._statement_batches(packets["fnlttSinglAcntAll"], packets["stockTotqySttus"], "CFS")
        if not batches:  # no consolidated statement at all: one separate-statement basis for the whole company (spec §2.3)
            separate = {year: self._dart_year("fnlttSinglAcntAll", corp_code, year, "OFS") for year in years}
            batches, latest_rows = self._statement_batches(separate, packets["stockTotqySttus"], "OFS")
        dividends = [packets["alotMatter"][year] for year in sorted(years)]
        stock_totqy = {str(year): packets["stockTotqySttus"][year] for year in sorted(years)}
        irds = {str(year): packets["irdsSttus"][year] for year in sorted(years)}
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
