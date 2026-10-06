"""Ephemeral inputs and pure composition arithmetic. Never writes portfolio, FX cache or research state."""
from __future__ import annotations

import datetime as dt
import json
import re
import secrets
import threading
from copy import deepcopy
from decimal import Decimal, localcontext

from features.common.market_data.readonly_quote import read_quote, read_fx
from features.portfolio.decimal_values import parse_decimal
from features.price_scenarios.store import decimal_text
from features.common.instruments.registry import exchange_suffix, infer_market
from . import DecisionError
from .inputs import Files, database, exposure, digest, identity

TTL_SECONDS = 1800


def instrument_for(position):
    market = str(position.get("market") or (position.get("resolved") or {}).get("market") or "").upper()
    ticker = str(position.get("ticker") or "").upper()
    if not market or not ticker:
        return None
    if market == "KR":
        ticker = re.sub(r"\.(KS|KQ)$", "", ticker)
    try:
        if market in {"JP", "EUROPE"}:
            symbol = str(position.get("symbol") or (position.get("resolved") or {}).get("providerSymbol") or ticker).upper()
            if not verified_symbol({"ticker": ticker, "market": market}, symbol):
                return None
            ticker = symbol  # Separate venue lines cannot share a ticker-only denominator entry.
        return identity(f"{market}:{ticker}")["instrumentId"]
    except DecisionError:
        return None


def verified_symbol(ident, symbol):
    """A provider line must identify the same ticker and market; issuer aliases are not proof."""
    ticker, market = ident["ticker"], ident["market"]
    suffix = exchange_suffix(symbol)
    if market == "US":
        return not suffix and symbol in {ticker, ticker.replace(".", "-")}
    if not suffix or infer_market(symbol).value != market:
        return False
    root = symbol[:-len(suffix)]
    return root == ticker if not exchange_suffix(ticker) else symbol == ticker


def raw_portfolio(files):
    value, checksum = files.read("portfolio.json")
    if value is None:
        value = {"positions": [], "cash": []}
    if isinstance(value, list):
        value = {"positions": value, "cash": []}
    if not isinstance(value, dict) or not isinstance(value.get("positions", []), list) or not isinstance(value.get("cash", []), list):
        raise DecisionError("portfolio_document_invalid", 503)
    if int(value.get("schemaVersion") or 1) > 3:
        raise DecisionError("portfolio_schema_unsupported", 503)
    return value, checksum


def capture_basis(root, instrument, *, quote_reader=read_quote, fx_reader=read_fx):
    ident = identity(instrument)
    files = Files(root)
    portfolio, checksum = raw_portfolio(files)
    gaps, holdings, candidates = [], {}, []
    with database(root) as conn:
        profile = exposure(conn, ident["ticker"], market=ident["market"]) if ident["market"] in {"US", "KR"} else None
        candidate = {**ident, "industry": None, "currency": None, "assetClass": None, "exposure": profile, "components": []}
        # Candidate classification is taken from exact saved identity only. No candidate price is needed.
        snapshot = conn.execute("SELECT body,id,fingerprint FROM price_snapshots WHERE instrument_id=? ORDER BY as_of DESC,computed_at DESC,seq DESC LIMIT 1", (instrument,)).fetchone() if conn is not None and conn.execute("SELECT 1 FROM sqlite_master WHERE name='price_snapshots'").fetchone() else None
        if snapshot:
            inputs = json.loads(snapshot[0])["inputs"]
            classification = inputs.get("classificationInputs") or {}
            candidate.update(industry=classification.get("industry"), currency=(inputs.get("price") or {}).get("currency"), assetClass=classification.get("quoteType"), classificationRef={"type": "price_snapshot", "id": snapshot[1], "inputFingerprint": snapshot[2], "methodVersion": inputs.get("methodVersion"), "specSha256": inputs.get("specSha256")})
        for index, position in enumerate(portfolio.get("positions", [])):
            if not isinstance(position, dict):
                gaps.append("position_invalid"); continue
            key = instrument_for(position)
            try:
                quantity = parse_decimal(position.get("quantity"))
                if quantity < 0:
                    raise ValueError()
            except ValueError:
                gaps.append("quantity_invalid"); continue
            if not key:
                gaps.append("holding_identity_unknown"); continue
            held_ident = identity(key)
            symbol = str(position.get("symbol") or (position.get("resolved") or {}).get("providerSymbol") or held_ident["ticker"]).upper()
            if held_ident["market"] == "KR" and not re.search(r"\.(KS|KQ)$", symbol):
                symbol = ""  # Exchange cannot be guessed from the price model's market alone.
            if not verified_symbol(held_ident, symbol):
                gaps.append("holding_quote_identity_unverified")
                symbol = ""
            if key in holdings:
                holdings[key]["quantity"] += quantity
                continue
            holdings[key] = {**held_ident, "quantity": quantity, "symbol": symbol, "industry": position.get("industry"),
                             "assetClass": position.get("assetClass"), "currency": position.get("currency"),
                             "exposure": exposure(conn, held_ident["ticker"], market=held_ident["market"]) if held_ident["market"] in {"US", "KR"} else None,
                             "components": []}
        for key, row in holdings.items():
            quote_value = (quote_reader(row["symbol"]) if row["symbol"] else {"status": "unavailable", "reason": "quote_identity_unknown"}) if row["quantity"] > 0 else {"status": "available", "value": "0", "currency": row.get("currency"), "source": "zero_quantity"}
            row["quote"] = quote_value
            if quote_value.get("status") != "available" or not quote_value.get("currency"):
                gaps.append("holding_quote_unavailable")
            else:
                row["currency"] = quote_value["currency"]
                row["assetClass"] = row["assetClass"] or quote_value.get("assetClass")
            if key == instrument:
                candidate.update({key_: row.get(key_) for key_ in ("industry", "currency", "assetClass", "exposure", "components")})
        # ETF components are not collected or inferred. A future owner can supply verified composition packets.
        cash = portfolio.get("cash", [])
        currencies = {row.get("currency") for row in holdings.values()} | {row.get("currency") for row in cash if isinstance(row, dict)}
        fx = {currency: fx_reader(currency) for currency in sorted(c for c in currencies if isinstance(c, str) and re.fullmatch(r"[A-Z]{3}", c))}
    entries = []
    with localcontext() as context:
        context.prec = 2300
        for key, row in holdings.items():
            currency = row.get("currency")
            rate = fx.get(currency, {})
            try:
                if row["quote"].get("status") != "available" or rate.get("status") != "available":
                    raise ValueError()
                price, conversion = parse_decimal(row["quote"]["value"]), parse_decimal(rate["rateToUsd"])
                if price < 0 or (price == 0 and row["quantity"] != 0) or conversion <= 0:
                    raise ValueError()
                value = row["quantity"] * price * conversion
            except (ValueError, KeyError):
                gaps.append("portfolio_value_unavailable"); value = None
            entries.append({**row, "quantity": str(row["quantity"]), "valueUsd": str(value) if value is not None else None, "kind": "holding"})
        for index, row in enumerate(cash):
            try:
                currency, amount = row["currency"], parse_decimal(row["amount"])
                rate = fx.get(currency, {})
                if amount < 0 or rate.get("status") != "available":
                    raise ValueError()
                conversion = parse_decimal(rate["rateToUsd"])
                if conversion <= 0:
                    raise ValueError()
                value = amount * conversion
            except (ValueError, KeyError, TypeError):
                gaps.append("cash_value_unavailable"); currency, value = (row or {}).get("currency") if isinstance(row, dict) else None, None
            entries.append({"instrumentId": f"cash:{index}", "kind": "cash", "currency": currency, "industry": "현금",
                            "valueUsd": str(value) if value is not None else None, "exposure": None, "assetClass": "cash", "components": []})
    files.verify()
    body = {"candidate": candidate, "entries": entries, "fx": fx, "portfolioHash": checksum,
            "portfolioRevision": portfolio.get("revision", 0), "dataGaps": sorted(set(gaps)),
            "notice": "후보의 최종 비중을 바꾸고 나머지 자산과 현금을 같은 비율로 조정합니다. 실제 보유는 변경하지 않습니다."}
    return {**body, "basisFingerprint": digest(body)}


def _composition(entries):
    groups = {"security": {}, "industry": {}, "currency": {}, "macro": {}}
    coverage, unknown, looked = [], Decimal(0), []
    for entry in entries:
        weight = Decimal(entry["weight"])
        for dimension, key in (("security", entry["instrumentId"]), ("industry", entry.get("industry") or "미조사"), ("currency", entry.get("currency") or "미확인")):
            groups[dimension][key] = groups[dimension].get(key, Decimal(0)) + weight
        profile = entry.get("exposure") or {}
        factors = {(row.get("factor"), row.get("direction")) for row in profile.get("items", [])}
        if entry["kind"] != "cash":
            if not factors:
                unknown += weight
            for factor, direction in sorted(factors):
                key = f"{factor}:{direction}"
                groups["macro"][key] = groups["macro"].get(key, Decimal(0)) + weight
            coverage.append({"instrumentId": entry["instrumentId"], "weight": str(weight), "profileId": profile.get("profileId"),
                             "sourceRefs": [ref for item in profile.get("items", []) for ref in item.get("sourceRefs", [])],
                             "items": [{key: item.get(key) for key in ("id", "factor", "direction", "quote", "magnitudeBasis", "magnitudeQuote", "sourceRefs")} for item in profile.get("items", [])],
                             "status": "partial" if factors else "not_investigated"})
        if entry.get("assetClass") in {"ETF", "MUTUALFUND"}:
            packet = entry.get("components")
            packet = packet if isinstance(packet, dict) else {}
            component_rows = packet.get("items") or []
            verified = packet.get("verified") is True and packet.get("asOf") and packet.get("sourceRefs")
            items, known = [], Decimal(0)
            try:
                if verified:
                    seen = set()
                    dt.date.fromisoformat(packet["asOf"])
                    for component in component_rows:
                        key = identity(component["instrumentId"])["instrumentId"]
                        part = parse_decimal(component["weight"])
                        if part < 0 or part > 1 or key in seen:
                            raise ValueError()
                        seen.add(key); known += part
                        items.append({"instrumentId": key, "weight": str(weight * part)})
                    if known > 1:
                        raise ValueError()
            except (ValueError, KeyError, TypeError):
                verified, items, known = False, [], Decimal(0)
            looked.append({"instrumentId": entry["instrumentId"], "status": "partial" if verified else "not_investigated",
                           "unknownWeight": str(weight * (1 - known)), "compositionCoverage": str(known), "asOf": packet.get("asOf") if verified else None,
                           "sourceRefs": packet.get("sourceRefs", []) if verified else [], "items": items})
    weights = sorted((Decimal(row["weight"]) for row in entries if row["kind"] != "cash"), reverse=True)
    return {**{key: {label: str(value) for label, value in sorted(values.items())} for key, values in groups.items()},
            "concentration": {"maxHolding": str(max(weights, default=Decimal(0))), "top3": str(sum(weights[:3])), "top5": str(sum(weights[:5]))},
            "coverage": coverage, "uninvestigatedHoldingWeight": str(unknown), "etfLookThrough": looked}


def current_composition(basis):
    """Known holdings only, with a complete denominator; missing inputs never become zero."""
    if basis["dataGaps"] or not basis["entries"]:
        return None
    with localcontext() as context:
        context.prec = 2300
        total = sum(Decimal(row["valueUsd"]) for row in basis["entries"])
        if total <= 0:
            return None
        return _composition([{**row, "weight": str(Decimal(row["valueUsd"]) / total)} for row in basis["entries"]])


def preview(basis, instrument, weight_text):
    if basis["candidate"]["instrumentId"] != instrument:
        raise DecisionError("candidate_basis_mismatch")
    try:
        weight = Decimal(decimal_text(weight_text, field="candidateWeightPercent", low=Decimal(0), high=Decimal(100))) / 100
    except ValueError:
        raise DecisionError("invalid_candidate_weight") from None
    base = {"basisFingerprint": basis["basisFingerprint"], "portfolioRevision": basis["portfolioRevision"], "assumption": basis["notice"],
            "candidateWeightPercent": str(weight * 100), "dataGaps": basis["dataGaps"], "sourceRefs": {"fx": basis["fx"], "quotes": [row.get("quote") for row in basis["entries"] if row.get("quote")]}}
    if basis["dataGaps"] or not basis["entries"]:
        return {**base, "status": "unavailable", "reason": "portfolio_basis_unavailable", "before": None, "after": None, "delta": None}
    with localcontext() as context:
        context.prec = 2300
        total = sum(Decimal(row["valueUsd"]) for row in basis["entries"])
        if total <= 0:
            return {**base, "status": "unavailable", "reason": "portfolio_basis_unavailable", "before": None, "after": None, "delta": None}
        before = [{**row, "weight": str(Decimal(row["valueUsd"]) / total)} for row in basis["entries"]]
        old = sum(Decimal(row["weight"]) for row in before if row["instrumentId"] == instrument)
        if old == 1 and weight != 1:
            return {**base, "status": "unavailable", "reason": "no_other_assets", "before": _composition(before), "after": None, "delta": None}
        after = [{**row, "weight": str(Decimal(row["weight"]) * (1 - weight) / (1 - old))} for row in before if row["instrumentId"] != instrument] if old != 1 else []
        after.append({**basis["candidate"], "kind": "holding", "weight": str(weight)})
        first, last = _composition(before), _composition(after)
        delta = {key: {label: str(Decimal(last[key].get(label, "0")) - Decimal(first[key].get(label, "0"))) for label in sorted(set(first[key]) | set(last[key]))} for key in ("security", "industry", "currency", "macro", "concentration")}
    return {**base, "status": "available", "before": first, "after": last, "delta": delta,
            "backtest": {"status": "unavailable", "reason": "matching_candidate_backtest_not_verified"},
            "notice": "공시 노출 비중은 확인된 보유 비중입니다. 그룹끼리 겹치며 전체 위험률·손실률이 아닙니다. 시세 통화와 매출 통화는 다릅니다."}


class BasisCache:
    def __init__(self, clock=lambda: dt.datetime.now(dt.timezone.utc)):
        self.clock, self.items, self.lock = clock, {}, threading.Lock()

    def put(self, root, basis):
        now = self.clock()
        with self.lock:
            self.items = {key: value for key, value in self.items.items() if value[2] > now}
            if len(self.items) >= 128:
                self.items.pop(next(iter(self.items)))
            key = secrets.token_urlsafe(24)
            expires = now + dt.timedelta(seconds=TTL_SECONDS)
            self.items[key] = (str(Files(root).root), deepcopy(basis), expires)
        return {**basis, "basisId": key, "expiresAt": expires.isoformat().replace("+00:00", "Z")}

    def get(self, root, key):
        with self.lock:
            stored = self.items.get(key)
        if not stored or stored[0] != str(Files(root).root) or stored[2] <= self.clock():
            raise DecisionError("portfolio_basis_expired", 409)
        files = Files(root)
        _, checksum = raw_portfolio(files)
        if checksum != stored[1]["portfolioHash"]:
            raise DecisionError("comparison_inputs_changed", 409)
        return deepcopy(stored[1])
