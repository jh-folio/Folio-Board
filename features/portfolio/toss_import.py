"""Read-only Toss holdings preview and explicit Portfolio import confirmation.

The broker response and account identifiers deliberately live only in a small
process-memory TTL store.  The durable sidecar is recovery metadata, never a
broker cache.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from features.common.market_data.toss_open_api import (
    TOSS_REST_OPENAPI_VERSION,
    fetch_toss_accounts,
    fetch_toss_holdings,
)
from features.common.utils import now_iso, write_json
from .decimal_values import DecimalValueError, canonical_average_price, canonical_decimal, canonical_quantity, exact_subtract, parse_decimal
from . import service


TTL_SECONDS = 300.0
AUTHORITY_FINGERPRINT_VERSION = 2
MERGE_FINGERPRINT_VERSION = 2
AUTHORITY_DOMAIN = "folio.portfolio.authority/v2"
MERGE_DOMAIN = "folio.toss.upsert-preserve-preview/v2"
_LEGACY_AUTHORITY_DOMAIN = "folio.portfolio.authority/v1"
_LEGACY_MERGE_DOMAIN = "folio.toss.upsert-preserve-preview/v1"
_HEX = re.compile(r"^[0-9a-f]{64}$")
_COUNTS = ("additions", "updates", "preservedManual", "unchanged", "conflicts", "unsupported")
_POSITION_FIELDS = ("id", "ticker", "symbol", "name", "market", "quantity", "averagePrice", "targetWeight", "currency", "assetClass", "sector", "industry", "country", "exchange", "quoteType")
_RESOLVED_FIELDS = ("ok", "ticker", "symbol", "name", "market", "currency", "assetClass", "sector", "industry", "country", "exchange", "quoteType")
_SAFE_PROVIDER_CODES = {"disabled", "credentials_missing", "multi_process_unsupported", "invalid_token", "token_expired", "ip_allowlist_or_permission_denied", "rate_limited", "provider_contract_invalid", "provider_error"}


class TossImportError(RuntimeError):
    """A short public error which cannot retain a broker response."""

    def __init__(self, code: str, *, status: int = 400, latest: dict | None = None, metadata_status: str = "") -> None:
        self.code = str(code)
        self.status = int(status)
        self.latest = latest
        self.metadata_status = metadata_status
        super().__init__(self.code)

    def __repr__(self) -> str:
        return f"TossImportError(code={self.code!r}, status={self.status})"


@dataclass
class _MemoryValue:
    value: dict[str, Any]
    expires_at: float


def _text(value: object, *, upper: bool = False) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).strip()
    return text.upper() if upper else text


def _decimal(value: object) -> Decimal | None:
    try:
        return parse_decimal(value)
    except DecimalValueError:
        return None


def _decimal_text(value: Decimal) -> str:
    return canonical_decimal(value)


def _legacy_decimal_text(value: Decimal) -> str:
    """Frozen v1 serializer used only to match old recovery records."""
    value = value.normalize()
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _legacy_json_value(value: Any) -> Any:
    """RFC-8259-friendly canonical value with NFC strings and decimal strings."""
    if isinstance(value, Decimal):
        return _legacy_decimal_text(value)
    if isinstance(value, float):
        decimal = _decimal(value)
        if decimal is None:
            raise ValueError("non_finite_number")
        return _legacy_decimal_text(decimal)
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_legacy_json_value(item) for item in value]
    if isinstance(value, dict):
        items = ((unicodedata.normalize("NFC", str(key)), _legacy_json_value(item)) for key, item in value.items())
        return {key: item for key, item in sorted(items, key=lambda item: item[0])}
    if value is None or isinstance(value, (bool, int)):
        return value
    return unicodedata.normalize("NFC", str(value))


def _json_value(value: Any) -> Any:
    """v2 fingerprint JSON: exact decimals become canonical strings."""
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, float):
        parsed = _decimal(value)
        if parsed is None:
            raise ValueError("non_finite_number")
        return canonical_decimal(parsed)
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        items = ((unicodedata.normalize("NFC", str(key)), _json_value(item)) for key, item in value.items())
        return {key: item for key, item in sorted(items, key=lambda item: item[0])}
    if value is None or isinstance(value, (bool, int)):
        return value
    return unicodedata.normalize("NFC", str(value))


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(_json_value(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _legacy_canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(_legacy_json_value(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(domain: str, value: Any) -> tuple[str, bytes]:
    raw = canonical_json_bytes(value)
    digest = hashlib.sha256(domain.encode("utf-8") + b"\n" + raw).hexdigest()
    return digest, raw


def _legacy_fingerprint(domain: str, value: Any) -> tuple[str, bytes]:
    raw = _legacy_canonical_json_bytes(value)
    digest = hashlib.sha256(domain.encode("utf-8") + b"\n" + raw).hexdigest()
    return digest, raw


def position_key(row: dict) -> str:
    return f"{_text(row.get('market'), upper=True)}:{_text(row.get('currency'), upper=True)}:{_text(row.get('ticker') or row.get('symbol'), upper=True)}"


def _legacy_authority_projection(portfolio: dict) -> dict:
    positions = []
    for source in portfolio.get("positions", []):
        if not isinstance(source, dict):
            continue
        resolved = source.get("resolved") if isinstance(source.get("resolved"), dict) else {}
        row = {field: source.get(field) for field in _POSITION_FIELDS}
        row["resolved"] = {field: resolved.get(field) for field in _RESOLVED_FIELDS}
        positions.append(row)
    cash = [{"currency": row.get("currency"), "amount": row.get("amount")} for row in portfolio.get("cash", []) if isinstance(row, dict)]
    positions.sort(key=lambda row: (position_key(row), _legacy_json_value(row).get("id", ""), _legacy_canonical_json_bytes(row)))
    cash.sort(key=lambda row: (_text(row.get("currency"), upper=True), _legacy_canonical_json_bytes(row)))
    return {
        "domain": _LEGACY_AUTHORITY_DOMAIN,
        "schemaVersion": 2,
        "revision": int(portfolio.get("revision") or 0),
        "positions": positions,
        "cash": cash,
    }


def legacy_authority_fingerprint(portfolio: dict) -> tuple[str, bytes]:
    return _legacy_fingerprint(_LEGACY_AUTHORITY_DOMAIN, _legacy_authority_projection(portfolio))


def _authority_projection(portfolio: dict) -> dict:
    positions = []
    for source in portfolio.get("positions", []):
        if not isinstance(source, dict):
            continue
        resolved = source.get("resolved") if isinstance(source.get("resolved"), dict) else {}
        row = {field: source.get(field) for field in _POSITION_FIELDS}
        row["quantity"] = canonical_decimal(row["quantity"])
        row["averagePrice"] = canonical_decimal(row["averagePrice"])
        row["resolved"] = {field: resolved.get(field) for field in _RESOLVED_FIELDS}
        positions.append(row)
    cash = [{"currency": row.get("currency"), "amount": row.get("amount")} for row in portfolio.get("cash", []) if isinstance(row, dict)]
    positions.sort(key=lambda row: (position_key(row), _json_value(row).get("id", ""), canonical_json_bytes(row)))
    cash.sort(key=lambda row: (_text(row.get("currency"), upper=True), canonical_json_bytes(row)))
    return {"domain": AUTHORITY_DOMAIN, "schemaVersion": 3, "revision": int(portfolio.get("revision") or 0), "positions": positions, "cash": cash}


def authority_fingerprint(portfolio: dict) -> tuple[str, bytes]:
    return fingerprint(AUTHORITY_DOMAIN, _authority_projection(portfolio))


def mask_account_number(value: object) -> str:
    raw = _text(value)
    return f"•••• {raw[-4:]}" if len(raw) >= 4 else "••••"


def _safe_issue(key: str | None, codes: set[str]) -> dict:
    return {"positionKey": key or None, "issueCodes": sorted(_text(code).lower() for code in codes if code)}


def _provider_code(exc: BaseException) -> str:
    code = str(getattr(exc, "code", "") or "")
    return code if code in _SAFE_PROVIDER_CODES else "provider_unavailable"


class TossHoldingsImport:
    """A process-local broker-import coordinator with no durable raw holdings."""

    def __init__(
        self,
        data_dir: Path,
        *,
        accounts_reader: Callable[[], list[dict]] = fetch_toss_accounts,
        holdings_reader: Callable[[int], dict] = fetch_toss_holdings,
        monotonic: Callable[[], float] = time.monotonic,
        state_writer: Callable[[Path, dict], None] = write_json,
        portfolio_writer: Callable[..., dict] = service.write_portfolio_authority,
    ) -> None:
        self.data_dir = Path(data_dir)
        self._accounts_reader = accounts_reader
        self._holdings_reader = holdings_reader
        self._monotonic = monotonic
        self._state_writer = state_writer
        self._portfolio_writer = portfolio_writer
        self._selections: dict[str, _MemoryValue] = {}
        self._previews: dict[str, _MemoryValue] = {}

    @property
    def state_path(self) -> Path:
        return self.data_dir / "portfolio-import-state.json"

    def _put(self, store: dict[str, _MemoryValue], value: dict) -> str:
        self._sweep_memory()
        key = secrets.token_urlsafe(24)
        store[key] = _MemoryValue(value=value, expires_at=self._monotonic() + TTL_SECONDS)
        return key

    def _take(self, store: dict[str, _MemoryValue], key: object, expired: str) -> dict:
        self._sweep_memory()
        value = store.get(str(key or ""))
        if value is None or value.expires_at <= self._monotonic():
            store.pop(str(key or ""), None)
            raise TossImportError(expired, status=410)
        return value.value

    def _sweep_memory(self) -> None:
        now = self._monotonic()
        for store in (self._selections, self._previews):
            for key, item in tuple(store.items()):
                if item.expires_at <= now:
                    # Dropping the whole value removes account sequence and any
                    # normalized quantities/prices cached with a preview.
                    del store[key]

    def _state(self) -> dict:
        if not self.state_path.exists():
            return {"schemaVersion": 1, "source": "toss_open_api", "lastImport": None, "pendingImport": None}
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise TossImportError("metadata_unavailable", status=503, metadata_status="metadata_unavailable")
        if not isinstance(value, dict) or set(value) != {"schemaVersion", "source", "lastImport", "pendingImport"} or value.get("schemaVersion") != 1 or value.get("source") != "toss_open_api":
            raise TossImportError("metadata_unavailable", status=503, metadata_status="metadata_unavailable")
        if value.get("lastImport") is not None and not self._valid_record(value["lastImport"], pending=False):
            raise TossImportError("metadata_unavailable", status=503, metadata_status="metadata_unavailable")
        if value.get("pendingImport") is not None and not self._valid_record(value["pendingImport"], pending=True):
            raise TossImportError("metadata_unavailable", status=503, metadata_status="metadata_unavailable")
        return value

    def _write_state(self, value: dict) -> None:
        # The only durable import payload. Callers construct it from safe
        # fingerprints/counts/keys, never from a broker row.
        self._state_writer(self.state_path, value)

    @staticmethod
    def _valid_record(record: object, *, pending: bool = False) -> bool:
        if not isinstance(record, dict):
            return False
        required = {"importId", "importedAt", "mergeMode", "portfolioRevision", "authorityFingerprintVersion", "authorityFingerprint", "mergeFingerprintVersion", "mergeFingerprint", "positionKeys", "counts", "openApiVersion"}
        if pending:
            required |= {"basePortfolioRevision", "baseAuthorityFingerprintVersion", "baseAuthorityFingerprint"}
        if set(record) != required or record.get("mergeMode") != "upsert_preserve" or record.get("openApiVersion") != TOSS_REST_OPENAPI_VERSION:
            return False
        if not isinstance(record.get("importId"), str) or not record["importId"] or not isinstance(record.get("importedAt"), str):
            return False
        if isinstance(record.get("portfolioRevision"), bool) or not isinstance(record.get("portfolioRevision"), int) or record["portfolioRevision"] < 0:
            return False
        authority_version = record.get("authorityFingerprintVersion")
        merge_version = record.get("mergeFingerprintVersion")
        if authority_version not in {1, AUTHORITY_FINGERPRINT_VERSION} or merge_version != authority_version:
            return False
        if not isinstance(record.get("authorityFingerprint"), str) or not isinstance(record.get("mergeFingerprint"), str) or not _HEX.fullmatch(record["authorityFingerprint"]) or not _HEX.fullmatch(record["mergeFingerprint"]):
            return False
        keys = record.get("positionKeys")
        counts = record.get("counts")
        if not isinstance(keys, list) or keys != sorted(set(keys)) or not all(isinstance(key, str) and key for key in keys) or not isinstance(counts, dict) or set(counts) != set(_COUNTS) or not all(not isinstance(value, bool) and isinstance(value, int) and value >= 0 for value in counts.values()):
            return False
        if pending:
            return record.get("baseAuthorityFingerprintVersion") == authority_version and not isinstance(record.get("basePortfolioRevision"), bool) and isinstance(record.get("basePortfolioRevision"), int) and record["basePortfolioRevision"] >= 0 and isinstance(record.get("baseAuthorityFingerprint"), str) and bool(_HEX.fullmatch(record["baseAuthorityFingerprint"]))
        return True

    def _authority_digests_for_record(self, portfolio: dict, version: object) -> set[str]:
        if version == AUTHORITY_FINGERPRINT_VERSION:
            return {authority_fingerprint(portfolio)[0]}
        if version == 1:
            # Old finalization could fingerprint either the raw v2 write target
            # (where numbers were JSON ints/floats) or the old GET projection.
            # Both candidates are available only while the original v1/v2 file
            # remains on disk.  Do not manufacture either from a v3 document.
            raw = service.legacy_v1_raw_portfolio_view(self.data_dir)
            legacy = service.legacy_v1_portfolio_view(self.data_dir)
            return {legacy_authority_fingerprint(candidate)[0] for candidate in (raw, legacy) if candidate is not None}
        return set()

    def _recover_locked(self, latest: dict) -> tuple[dict, str]:
        state = self._state()
        pending = state.get("pendingImport")
        if pending is None:
            return state, "ready"
        if not self._valid_record(pending, pending=True):
            raise TossImportError("metadata_unavailable", status=503, metadata_status="metadata_unavailable")
        current_digests = self._authority_digests_for_record(latest, pending.get("authorityFingerprintVersion"))
        target_match = bool(current_digests) and int(pending.get("portfolioRevision", -1)) == latest["revision"] and any(hmac.compare_digest(digest, pending["authorityFingerprint"]) for digest in current_digests)
        base_match = bool(current_digests) and int(pending.get("basePortfolioRevision", -1)) == latest["revision"] and any(hmac.compare_digest(digest, str(pending.get("baseAuthorityFingerprint") or "")) for digest in current_digests)
        try:
            if target_match:
                state["lastImport"] = {key: value for key, value in pending.items() if not key.startswith("base")}
                state["pendingImport"] = None
                self._write_state(state)
                return state, "recovered"
            if base_match:
                state["pendingImport"] = None
                self._write_state(state)
                return state, "ready"
            state["pendingImport"] = None
            self._write_state(state)
            return state, "stale"
        except Exception:
            raise TossImportError("metadata_unavailable", status=503, metadata_status="recovery_pending") from None

    def accounts(self) -> dict:
        self._sweep_memory()
        with service.portfolio_write_lock():
            self._recover_locked(service.get_portfolio(self.data_dir))
        try:
            rows = self._accounts_reader()
        except Exception as exc:
            raise TossImportError(_provider_code(exc), status=503) from None
        accounts = []
        for row in rows:
            number = _text(row.get("accountNo"))
            account_type = _text(row.get("accountType"), upper=True)
            try:
                sequence = int(row.get("accountSeq"))
            except (TypeError, ValueError):
                sequence = -1
            selectable = bool(number and sequence >= 0 and account_type == "BROKERAGE")
            reason = "" if selectable else ("unsupported_account_type" if account_type else "invalid_account")
            item = {"label": mask_account_number(number), "accountType": account_type or "UNKNOWN", "selectable": selectable, "reason": reason}
            if selectable:
                item["selectionId"] = self._put(self._selections, {"accountSeq": sequence, "accountType": account_type})
            accounts.append(item)
        return {"accounts": accounts, "provider": "toss_open_api", "openApiVersion": TOSS_REST_OPENAPI_VERSION}

    def recover_portfolio(self) -> dict:
        """Run redacted pending-finalization recovery without contacting Toss."""
        self._sweep_memory()
        with service.portfolio_write_lock():
            latest = service.get_portfolio(self.data_dir)
            try:
                self._recover_locked(latest)
            except TossImportError:
                # Manual Portfolio reads must remain available when a sidecar is
                # locked or corrupt; only a new broker confirmation fails closed.
                pass
            return service.get_portfolio(self.data_dir)

    def _incoming(self, item: dict) -> tuple[dict, set[str], str | None]:
        ticker = _text(item.get("symbol"), upper=True)
        name = _text(item.get("name"))
        market = _text(item.get("marketCountry"), upper=True)
        currency = _text(item.get("currency"), upper=True)
        quantity = _decimal(item.get("quantity"))
        average = _decimal(item.get("averagePurchasePrice"))
        issues: set[str] = set()
        if not all((ticker, name, market, currency)):
            issues.add("missing_required_field")
        if market not in {"KR", "US"} or {"KR": "KRW", "US": "USD"}.get(market) != currency:
            issues.add("unsupported_market_or_currency")
        try:
            quantity_text = canonical_quantity(item.get("quantity"))
        except DecimalValueError as exc:
            quantity_text = None
            issues.add("invalid_quantity" if exc.code == "invalid_quantity" else exc.code)
        try:
            average_text = canonical_average_price(item.get("averagePurchasePrice"), blank_is_zero=False)
        except DecimalValueError as exc:
            average_text = None
            issues.add("invalid_average_purchase_price" if exc.code == "invalid_average_price" else exc.code)
        key = f"{market}:{currency}:{ticker}" if ticker and market and currency else None
        return {
            "positionKey": key,
            "ticker": ticker or None,
            "name": name or None,
            "market": market or None,
            "currency": currency or None,
            "quantity": quantity_text,
            "averagePurchasePrice": average_text,
        }, issues, key

    def _build_preview(self, overview: dict, portfolio: dict) -> dict:
        items = overview.get("items") if isinstance(overview, dict) else None
        if not isinstance(items, list):
            items = []
        base_digest, base_bytes = authority_fingerprint(portfolio)
        existing: dict[str, dict] = {}
        conflicts: list[dict] = []
        existing_tickers: dict[str, list[str]] = {}
        for row in portfolio["positions"]:
            key = position_key(row)
            ticker = _text(row.get("ticker") or row.get("symbol"), upper=True)
            if ticker:
                existing_tickers.setdefault(ticker, []).append(key)
            if not key or key in existing:
                conflicts.append(_safe_issue(key or None, {"duplicate_existing_position"}))
            else:
                existing[key] = dict(row)
        for ticker, keys in existing_tickers.items():
            if len(keys) > 1:
                conflicts.extend(_safe_issue(key or None, {"duplicate_existing_ticker"}) for key in keys)
        duplicate_existing_tickers = {
            ticker for ticker, keys in existing_tickers.items() if len(keys) > 1
        }
        duplicate_existing_keys = {
            key
            for ticker, keys in existing_tickers.items()
            if ticker in duplicate_existing_tickers
            for key in keys
        }

        incoming: list[dict] = []
        unsupported: list[dict] = []
        parsed = [self._incoming(raw if isinstance(raw, dict) else {}) for raw in items]
        incoming_tickers: dict[str, int] = {}
        for normalized, _issues, _key in parsed:
            if normalized["ticker"]:
                incoming_tickers[normalized["ticker"]] = incoming_tickers.get(normalized["ticker"], 0) + 1

        additions: list[str] = []
        updates: list[str] = []
        unchanged: list[str] = []
        matched: set[str] = set()
        operations: list[tuple[str, str, dict, dict | None]] = []
        details: list[dict] = []
        for normalized, original_issues, key in parsed:
            issues = set(original_issues)
            if normalized["ticker"] and incoming_tickers.get(normalized["ticker"], 0) > 1:
                issues.add("duplicate_incoming_ticker")
            # The merge identity is ticker. If its existing multiplicity is
            # ambiguous, no incoming row for that ticker may become an
            # update/add/unchanged success even when a position key matches.
            if normalized["ticker"] in duplicate_existing_tickers:
                issues.add("duplicate_existing_ticker")
            if issues:
                # Missing required merge fields are a capability/shape problem,
                # not a conflict with a manual Portfolio position.
                (unsupported if {"unsupported_market_or_currency", "missing_required_field"} & issues else conflicts).append(_safe_issue(key, issues))
                incoming.append({**normalized, "issueCodes": sorted(issues)})
                continue
            assert key is not None
            ticker_matches = existing_tickers.get(normalized["ticker"], [])
            if ticker_matches and key not in existing:
                issues.add("market_currency_conflict")
            if issues:
                conflicts.append(_safe_issue(key, issues))
                incoming.append({**normalized, "issueCodes": sorted(issues)})
                continue
            incoming.append({**normalized, "issueCodes": []})
            current = existing.get(key)
            if current is None:
                additions.append(key)
                operations.append(("add", key, normalized, None))
                details.append({"positionKey": key, "action": "add", "ticker": normalized["ticker"], "currency": normalized["currency"], "before": None, "after": {"quantity": normalized["quantity"], "averagePrice": normalized["averagePurchasePrice"]}, "delta": {"quantity": exact_subtract(normalized["quantity"], None), "averagePrice": exact_subtract(normalized["averagePurchasePrice"], None)}})
            else:
                matched.add(key)
                current_quantity = canonical_decimal(current.get("quantity"))
                current_average = canonical_decimal(current.get("averagePrice"))
                before = {"quantity": current_quantity, "averagePrice": current_average}
                after = {"quantity": normalized["quantity"], "averagePrice": normalized["averagePurchasePrice"]}
                if current_quantity != after["quantity"] or current_average != after["averagePrice"]:
                    updates.append(key)
                    operations.append(("update", key, normalized, current))
                    details.append({"positionKey": key, "action": "update", "ticker": normalized["ticker"], "currency": normalized["currency"], "before": before, "after": after, "delta": {"quantity": exact_subtract(after["quantity"], before["quantity"]), "averagePrice": exact_subtract(after["averagePrice"], before["averagePrice"])}})
                else:
                    unchanged.append(key)
                    details.append({"positionKey": key, "action": "unchanged", "ticker": normalized["ticker"], "currency": normalized["currency"], "before": before, "after": after, "delta": {"quantity": "0", "averagePrice": "0"}})
        # Existing duplicated positions are blocker evidence, not a successful
        # "manual preserved" result. They must not leak into success buckets.
        preserved = sorted((set(existing) - matched) - duplicate_existing_keys)
        buckets = {
            "additions": sorted(additions), "updates": sorted(updates), "preservedManual": preserved,
            "unchanged": sorted(unchanged),
            "conflicts": sorted(conflicts, key=lambda row: ((row.get("positionKey") or ""), row["issueCodes"])),
            "unsupported": sorted(unsupported, key=lambda row: ((row.get("positionKey") or ""), row["issueCodes"])),
        }
        blocked = bool(buckets["conflicts"] or buckets["unsupported"])
        target = None
        target_digest: str | None = None
        target_bytes: bytes | None = None
        if not blocked:
            target_positions = [dict(row) for row in portfolio["positions"]]
            target_by_key = {position_key(row): row for row in target_positions}
            for action, key, normalized, _current in operations:
                if action == "add":
                    target_by_key[key] = service.normalize_portfolio_position({
                        "ticker": normalized["ticker"], "symbol": normalized["ticker"], "name": normalized["name"],
                        "market": normalized["market"], "currency": normalized["currency"],
                        "quantity": normalized["quantity"], "averagePrice": normalized["averagePurchasePrice"],
                    })
                    target_positions.append(target_by_key[key])
                else:
                    target_by_key[key]["quantity"] = normalized["quantity"]
                    target_by_key[key]["averagePrice"] = normalized["averagePurchasePrice"]
            target = {"schemaVersion": 3, "revision": portfolio["revision"] + 1, "positions": target_positions, "cash": portfolio["cash"], "updatedAt": now_iso()}
            target_digest, target_bytes = authority_fingerprint(target)
        merge_root = {
            "domain": MERGE_DOMAIN, "mergeMode": "upsert_preserve", "openApiVersion": TOSS_REST_OPENAPI_VERSION,
            "base": {"portfolioRevision": portfolio["revision"], "authorityFingerprintVersion": AUTHORITY_FINGERPRINT_VERSION, "authorityFingerprint": base_digest},
            "incoming": sorted(incoming, key=lambda row: ((row.get("positionKey") or ""), canonical_json_bytes(row))),
            "result": {"portfolioRevision": portfolio["revision"] + 1, "authorityFingerprintVersion": AUTHORITY_FINGERPRINT_VERSION, "authorityFingerprint": target_digest, "buckets": buckets},
        }
        merge_digest, merge_bytes = fingerprint(MERGE_DOMAIN, merge_root)
        # An empty broker response is not an implicit request to replace or
        # delete the manual Portfolio. Invalid rows remain blockers instead of
        # being relabelled as an innocuous empty account.
        empty = not items
        return {"base": portfolio, "baseDigest": base_digest, "baseBytes": base_bytes, "authorityVersion": AUTHORITY_FINGERPRINT_VERSION, "target": target, "targetDigest": target_digest, "targetBytes": target_bytes, "buckets": buckets, "details": sorted(details, key=lambda row: row["positionKey"]), "incoming": incoming, "mergeDigest": merge_digest, "mergeBytes": merge_bytes, "mergeVersion": MERGE_FINGERPRINT_VERSION, "empty": empty}

    @staticmethod
    def _public_preview(preview_id: str, value: dict) -> dict:
        return {
            "previewId": preview_id, "expectedRevision": value["base"]["revision"], "canConfirm": not value["empty"] and not value["buckets"]["conflicts"] and not value["buckets"]["unsupported"], "status": "empty" if value["empty"] else "ready",
            "buckets": value["buckets"], "details": value["details"], "provider": "toss_open_api", "openApiVersion": TOSS_REST_OPENAPI_VERSION,
        }

    def preview(self, selection_id: object) -> dict:
        self._sweep_memory()
        selection = self._take(self._selections, selection_id, "selection_expired")
        if selection.get("accountType") != "BROKERAGE":
            raise TossImportError("unsupported_account_type", status=400)
        try:
            overview = self._holdings_reader(int(selection["accountSeq"]))
        except Exception as exc:
            raise TossImportError(_provider_code(exc), status=503) from None
        with service.portfolio_write_lock():
            portfolio = service.get_portfolio(self.data_dir)
            self._recover_locked(portfolio)
            value = self._build_preview(overview, portfolio)
        value["accountSeq"] = selection["accountSeq"]  # server memory only
        value["importId"] = secrets.token_urlsafe(24)
        preview_id = self._put(self._previews, value)
        return self._public_preview(preview_id, value)

    def _record(self, value: dict) -> dict:
        buckets = value["buckets"]
        keys = sorted(set(buckets["additions"] + buckets["updates"] + buckets["unchanged"]))
        return {
            "importId": value["importId"], "importedAt": now_iso(), "mergeMode": "upsert_preserve",
            "portfolioRevision": value["target"]["revision"], "authorityFingerprintVersion": AUTHORITY_FINGERPRINT_VERSION, "authorityFingerprint": value["targetDigest"],
            "mergeFingerprintVersion": MERGE_FINGERPRINT_VERSION, "mergeFingerprint": value["mergeDigest"], "positionKeys": keys,
            "counts": {key: len(buckets[key]) for key in _COUNTS}, "openApiVersion": TOSS_REST_OPENAPI_VERSION,
        }

    def confirm(self, preview_id: object, expected_revision: object) -> dict:
        self._sweep_memory()
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool):
            raise TossImportError("expected_revision_required", status=400)
        if expected_revision < 0:
            raise TossImportError("expected_revision_invalid", status=400)
        value = self._take(self._previews, preview_id, "preview_expired")
        with service.portfolio_write_lock():
            latest = service.get_portfolio(self.data_dir)
            state, metadata = self._recover_locked(latest)
            latest = service.get_portfolio(self.data_dir)
            # A client may retry after the authority write succeeded but before
            # its response arrived.  Idempotency owns that case even though the
            # original expected revision is now naturally stale.
            last = state.get("lastImport")
            if isinstance(last, dict) and last.get("importId") == value["importId"]:
                current_digest, current_bytes = authority_fingerprint(latest)
                if (
                    self._valid_record(last)
                    and latest["revision"] == value["target"]["revision"]
                    and value["authorityVersion"] == AUTHORITY_FINGERPRINT_VERSION
                    and hmac.compare_digest(last["mergeFingerprint"], value["mergeDigest"])
                    and hmac.compare_digest(last["authorityFingerprint"], value["targetDigest"])
                    and hmac.compare_digest(current_digest, value["targetDigest"])
                    and hmac.compare_digest(current_bytes, value["targetBytes"])
                ):
                    return {"portfolio": latest, "metadataStatus": metadata, "idempotent": True}
                raise TossImportError("idempotency_conflict", status=409, latest=latest)
            if expected_revision != value["base"]["revision"] or latest["revision"] != expected_revision:
                raise TossImportError("portfolio_revision_conflict", status=409, latest=latest)
            current_digest, current_bytes = authority_fingerprint(latest)
            if not (value["authorityVersion"] == AUTHORITY_FINGERPRINT_VERSION and value["mergeVersion"] == MERGE_FINGERPRINT_VERSION and hmac.compare_digest(current_digest, value["baseDigest"]) and hmac.compare_digest(current_bytes, value["baseBytes"])):
                raise TossImportError("preview_stale", status=409, latest=latest)
            try:
                overview = self._holdings_reader(int(value["accountSeq"]))
            except Exception as exc:
                raise TossImportError(_provider_code(exc), status=503) from None
            rebuilt = self._build_preview(overview, latest)
            if not (
                rebuilt["authorityVersion"] == value["authorityVersion"]
                and rebuilt["mergeVersion"] == value["mergeVersion"]
                and hmac.compare_digest(rebuilt["mergeDigest"], value["mergeDigest"])
                and hmac.compare_digest(rebuilt["mergeBytes"], value["mergeBytes"])
                and hmac.compare_digest(str(rebuilt["targetDigest"] or ""), str(value["targetDigest"] or ""))
                and hmac.compare_digest(rebuilt["targetBytes"] or b"", value["targetBytes"] or b"")
            ):
                raise TossImportError("preview_stale", status=409, latest=latest)
            if rebuilt["empty"]:
                raise TossImportError("empty_holdings", status=409, latest=latest)
            if rebuilt["buckets"]["conflicts"] or rebuilt["buckets"]["unsupported"]:
                raise TossImportError("blocking_items", status=409, latest=latest)
            record = self._record(value)
            pending = {**record, "basePortfolioRevision": latest["revision"], "baseAuthorityFingerprintVersion": AUTHORITY_FINGERPRINT_VERSION, "baseAuthorityFingerprint": current_digest}
            try:
                self._write_state({"schemaVersion": 1, "source": "toss_open_api", "lastImport": state.get("lastImport"), "pendingImport": pending})
            except Exception:
                raise TossImportError("pending_write_failed", status=503) from None
            try:
                committed = self._portfolio_writer(rebuilt["target"], data_dir=self.data_dir)
            except Exception:
                after = service.get_portfolio(self.data_dir)
                after_digest, _ = authority_fingerprint(after)
                try:
                    if after["revision"] == latest["revision"] and hmac.compare_digest(after_digest, current_digest):
                        self._write_state({"schemaVersion": 1, "source": "toss_open_api", "lastImport": state.get("lastImport"), "pendingImport": None})
                        raise TossImportError("portfolio_write_failed", status=503)
                    if after["revision"] == value["target"]["revision"] and hmac.compare_digest(after_digest, value["targetDigest"]):
                        committed = after
                    else:
                        self._write_state({"schemaVersion": 1, "source": "toss_open_api", "lastImport": state.get("lastImport"), "pendingImport": None})
                        raise TossImportError("portfolio_write_failed", status=503, latest=after, metadata_status="stale")
                except TossImportError:
                    raise
                except Exception:
                    raise TossImportError("metadata_unavailable", status=503, metadata_status="recovery_pending") from None
            try:
                self._write_state({"schemaVersion": 1, "source": "toss_open_api", "lastImport": record, "pendingImport": None})
                return {"portfolio": committed, "metadataStatus": "ready", "idempotent": False}
            except Exception:
                return {"portfolio": committed, "metadataStatus": "recovery_pending", "idempotent": False}


__all__ = [
    "AUTHORITY_FINGERPRINT_VERSION", "MERGE_FINGERPRINT_VERSION", "TTL_SECONDS", "TossHoldingsImport", "TossImportError",
    "authority_fingerprint", "canonical_json_bytes", "fingerprint", "mask_account_number", "position_key",
]
