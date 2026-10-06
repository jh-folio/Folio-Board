"""Read-only capture and exact-reference replay. No owner getter may create schema here."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from features.price_scenarios.store import PriceStore
from features.macro_state.replay import Replay
from features.macro_state.inputs import utc
from features.company_exposure.interpretation import interpret
from features.thesis_tracking.model import normalize_ticker
from . import DecisionError

LATEST = object()
REF_KEYS = frozenset({"instrumentId", "snapshotId", "priceReviews", "reasonRevisionId", "reasonReviews", "reasonLegacyHash",
                      "exposureProfileId", "macroRows", "macroMaxId", "report", "reportReadErrors", "attemptHash"})


def validate_reference(ref):
    if not isinstance(ref, dict) or set(ref) != REF_KEYS:
        raise DecisionError("invalid_reference_set")
    for key in ("snapshotId", "reasonRevisionId", "exposureProfileId"):
        if ref[key] is not None and (not isinstance(ref[key], str) or not 1 <= len(ref[key]) <= 160):
            raise DecisionError("invalid_reference_set")
    for key in ("reasonLegacyHash", "attemptHash"):
        if ref[key] is not None and (not isinstance(ref[key], str) or not re.fullmatch(r"[0-9a-f]{64}", ref[key])):
            raise DecisionError("invalid_reference_set")
    for key in ("priceReviews", "reasonReviews", "macroRows"):
        values = ref[key]
        if not isinstance(values, list) or len(values) > 5000:
            raise DecisionError("invalid_reference_set")
        for row in values:
            if not isinstance(row, dict) or set(row) != {"id", "hash"} or not isinstance(row["hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["hash"]):
                raise DecisionError("invalid_reference_set")
            if key == "reasonReviews":
                if not isinstance(row["id"], str) or not 1 <= len(row["id"]) <= 160:
                    raise DecisionError("invalid_reference_set")
            elif type(row["id"]) is not int or row["id"] < 1:
                raise DecisionError("invalid_reference_set")
        if len({row["id"] for row in values}) != len(values):
            raise DecisionError("invalid_reference_set")
    if ref["macroMaxId"] is not None and (type(ref["macroMaxId"]) is not int or ref["macroMaxId"] < 1):
        raise DecisionError("invalid_reference_set")
    if ref["report"] is not None:
        value = ref["report"]
        if not isinstance(value, dict) or set(value) != {"id", "hash"} or not isinstance(value["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", value["id"]) or not isinstance(value["hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["hash"]):
            raise DecisionError("invalid_reference_set")
    if not isinstance(ref["reportReadErrors"], list) or len(ref["reportReadErrors"]) > 1000:
        raise DecisionError("invalid_reference_set")
    for value in ref["reportReadErrors"]:
        if not isinstance(value, dict) or set(value) != {"id", "hash"} or not isinstance(value["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", value["id"]) or not isinstance(value["hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["hash"]):
            raise DecisionError("invalid_reference_set")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def identity(value: str) -> dict:
    found = re.fullmatch(r"(US|KR|JP|EUROPE):([A-Z0-9][A-Z0-9.\-]{0,24})", value) if isinstance(value, str) else None
    if not found or (found[1] == "KR" and not re.fullmatch(r"[0-9][A-Z0-9]{5}", found[2])):
        raise DecisionError("invalid_instrument_id")
    return {"instrumentId": value, "market": found[1], "ticker": found[2], "providerSymbol": found[2]}


def evaluated_at(value=None):
    try:
        return utc(value or dt.datetime.now(dt.timezone.utc).isoformat())
    except (ValueError, TypeError, AttributeError):
        raise DecisionError("invalid_evaluated_at") from None


class Files:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.observed = {}
        self.catalogs = {}

    def path(self, relative: str):
        path = os.path.realpath(self.root / relative)
        # The separator prevents sibling names such as data-other from passing.
        if not path.startswith(os.path.join(str(self.root), "")):
            raise DecisionError("source_path_outside_workspace", 503)
        return Path(path)

    def list_reports(self):
        directory = self.path("company-analysis")
        paths = sorted(directory.glob("*.json")) if directory.exists() else []
        self.catalogs["company-analysis"] = tuple(path.name for path in paths)
        return paths

    def read(self, relative: str):
        path = self.path(relative)
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            raw = None
        checksum = hashlib.sha256(raw).hexdigest() if raw is not None else None
        self.observed[relative] = checksum
        if raw is None:
            return None, None
        try:
            value = json.loads(raw, parse_float=str, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError):
            raise DecisionError("source_file_invalid", 503) from None
        return value, checksum

    def verify(self):
        for relative, names in self.catalogs.items():
            directory = self.path(relative)
            current = tuple(sorted(path.name for path in directory.glob("*.json"))) if directory.exists() else ()
            if current != names:
                raise DecisionError("comparison_inputs_changed", 409)
        for relative, checksum in self.observed.items():
            path = self.path(relative)
            try:
                current = hashlib.sha256(path.read_bytes()).hexdigest()
            except FileNotFoundError:
                current = None
            if current != checksum:
                raise DecisionError("comparison_inputs_changed", 409)


@contextmanager
def database(root):
    path = Path(root).resolve() / "market-memory.sqlite3"
    if not path.exists():
        yield None
        return
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        version = conn.execute("PRAGMA data_version").fetchone()[0]
        yield conn
        conn.rollback()
        if conn.execute("PRAGMA data_version").fetchone()[0] != version:
            raise DecisionError("comparison_inputs_changed", 409)


def has(conn, table):
    return conn is not None and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _checked(value, ref):
    if not isinstance(ref, dict) or value is None or digest(value) != ref.get("hash"):
        raise DecisionError("comparison_inputs_changed", 409)
    return value


def rows(conn, table, where, args, order, refs=LATEST, id_column="seq"):
    if refs is not LATEST and not isinstance(refs, list):
        raise DecisionError("invalid_reference_set")
    if not has(conn, table):
        if refs not in (LATEST, []):
            raise DecisionError("comparison_inputs_changed", 409)
        return [], []
    captured = [dict(r) for r in conn.execute(f"SELECT * FROM {table} WHERE {where} ORDER BY {order}", args)]
    if refs is not LATEST:
        by_id = {r[id_column]: r for r in captured}
        captured = [_checked(by_id.get(r.get("id")), r) for r in refs]
    return captured, [{"id": row[id_column], "hash": digest(row)} for row in captured]


def criteria(conn, revision=LATEST):
    if not has(conn, "valuation_user_criteria"):
        if revision not in (LATEST, None):
            raise DecisionError("revision_not_found", 404)
        return None
    if revision is None:
        return None
    row = conn.execute("SELECT * FROM valuation_user_criteria ORDER BY revision_id DESC LIMIT 1").fetchone() if revision is LATEST else conn.execute(
        "SELECT * FROM valuation_user_criteria WHERE revision_id=?", (revision,)).fetchone()
    if row is None and revision is not LATEST:
        raise DecisionError("revision_not_found", 404)
    return PriceStore.criteria_row(row)


def price(conn, instrument, ref=LATEST):
    if ref is None:
        return None
    row = None
    if has(conn, "price_snapshots"):
        row = conn.execute("SELECT * FROM price_snapshots WHERE instrument_id=? ORDER BY as_of DESC,computed_at DESC,seq DESC LIMIT 1", (instrument,)).fetchone() if ref is LATEST else conn.execute(
            "SELECT * FROM price_snapshots WHERE instrument_id=? AND id=?", (instrument, ref)).fetchone()
    if row is None and ref is not LATEST:
        raise DecisionError("snapshot_not_found", 404)
    return PriceStore._load(row) if row else None


def exposure(conn, ticker, ref=LATEST, *, market=None):
    if ref is None:
        return None
    row = None
    if has(conn, "company_macro_exposures"):
        if ref is LATEST:
            values = [json.loads(row[0]) for row in conn.execute("SELECT body FROM company_macro_exposures WHERE ticker=? ORDER BY seq DESC", (ticker,))]
            return next((value for value in values if market is None or value.get("market") == market), None)
        row = conn.execute(
            "SELECT body FROM company_macro_exposures WHERE ticker=? AND id=?", (ticker, ref)).fetchone()
    if row is None and ref is not LATEST:
        raise DecisionError("comparison_inputs_changed", 409)
    value = json.loads(row[0]) if row else None
    if value and market is not None and value.get("market") != market:
        raise DecisionError("invalid_reference_set")
    return value


def reason(conn, ticker, ref=LATEST, event_refs=LATEST, legacy_hash=LATEST):
    current = None
    if ref is not None and has(conn, "reason_revision"):
        current = conn.execute("SELECT * FROM reason_revision WHERE ticker=? ORDER BY revision DESC LIMIT 1", (ticker,)).fetchone() if ref is LATEST else conn.execute(
            "SELECT * FROM reason_revision WHERE ticker=? AND revision_id=?", (ticker, ref)).fetchone()
    if current is None and ref not in (LATEST, None):
        raise DecisionError("comparison_inputs_changed", 409)
    if current is None:
        # Older workspaces may have a current reason without immutable history. Do not turn that into unwritten.
        legacy = conn.execute("SELECT core_thesis FROM thesis WHERE ticker=?", (ticker,)).fetchone() if (ref is LATEST or legacy_hash not in (LATEST, None)) and has(conn, "thesis") else None
        checksum = digest(dict(legacy)) if legacy else None
        if legacy_hash is not LATEST and checksum != legacy_hash:
            raise DecisionError("comparison_inputs_changed", 409)
        return {"status": "unknown" if legacy and legacy[0] else "unwritten", "revisionId": None, "text": "", "events": [], "legacyHash": checksum}, []
    content = json.loads(current["content_json"])
    events, refs = rows(conn, "reason_review_event", "ticker=? AND reason_revision_id=?", (ticker, current["revision_id"]), "reviewed_at DESC,event_id DESC", event_refs, "event_id")
    completed = next((row for row in events if row["source"] in {"manual_review", "explicit_delta"}), None)
    text = content.get("core_thesis") or ""
    status = "unwritten" if not text else "unreviewed" if completed is None else "evidence_gap" if completed["outcome"] in {"evidence_gap", "no_new_material", "collection_failed", "unsupported", "deferred"} else "reviewed"
    return {"status": status, "revisionId": current["revision_id"], "contentHash": current["content_hash"], "text": text,
            "counterConditions": content.get("falsification_triggers") or [], "events": events}, refs


def macro(conn, root, at, refs=LATEST, maximum_id=LATEST):
    if not has(conn, "macro_observations") or not has(conn, "macro_metadata"):
        if refs not in (LATEST, []):
            raise DecisionError("comparison_inputs_changed", 409)
        return [], [], None
    maximum_id = conn.execute("SELECT MAX(id) FROM macro_observations").fetchone()[0] if maximum_id is LATEST else maximum_id
    if maximum_id is not None and (type(maximum_id) is not int or maximum_id < 1):
        raise DecisionError("invalid_reference_set")
    selected = [] if maximum_id is None else Replay(Path(root) / "market-memory.sqlite3", ["DFF", "NFCI", "KR_RATE", "KR_USDKRW"], connection=conn, maximum_id=maximum_id).select(at, observation_end=at[:10])
    # All selected observations are frozen, including those the interpretation might query as a fallback window.
    if refs is not LATEST:
        if not isinstance(refs, list):
            raise DecisionError("invalid_reference_set")
        if refs != [{"id": item["id"], "hash": digest(item)} for item in selected]:
            raise DecisionError("comparison_inputs_changed", 409)
    return selected, [{"id": item["id"], "hash": digest(item)} for item in selected], maximum_id


def report(files, ident, ref=LATEST, error_refs=LATEST):
    errors = []
    if error_refs is not LATEST:
        for error_ref in error_refs:
            relative = f'company-analysis/{error_ref["id"]}.json'
            try:
                files.read(relative)
            except DecisionError as error:
                if error.code != "source_file_invalid":
                    raise
            if files.observed[relative] != error_ref["hash"]:
                raise DecisionError("comparison_inputs_changed", 409)
        errors = error_refs
    if ref is None:
        return None, None, errors
    if ref is not LATEST:
        report_id = ref.get("id") if isinstance(ref, dict) else None
        if not isinstance(report_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", report_id):
            raise DecisionError("invalid_reference_set")
        value, checksum = files.read(f"company-analysis/{report_id}.json")
        if checksum != ref.get("hash"):
            raise DecisionError("comparison_inputs_changed", 409)
        company = (value or {}).get("company") or {}
        if not isinstance(company, dict) or str(company.get("ticker") or "").upper() != ident["ticker"] or str(company.get("market") or "").upper() != ident["market"]:
            raise DecisionError("invalid_reference_set")
        return value, ref, errors
    found = []
    for path in files.list_reports():
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", path.stem):
            continue
        try:
            value, checksum = files.read(f"company-analysis/{path.name}")
        except DecisionError as error:
            if error.code != "source_file_invalid":
                raise
            errors.append({"id": path.stem, "hash": files.observed[f"company-analysis/{path.name}"]})
            continue
        if not isinstance(value, dict):
            continue
        company = value.get("company") or {}
        if not isinstance(company, dict):
            continue
        if str(company.get("ticker") or "").upper() == ident["ticker"] and str(company.get("market") or "").upper() == ident["market"]:
            found.append((str(value.get("generatedAt") or value.get("createdAt") or ""), path.stem, value, checksum))
    if not found:
        return None, None, errors
    _, key, value, checksum = max(found, key=lambda row: row[:2])
    return value, {"id": key, "hash": checksum}, errors


def capture(conn, files, ident, at, ref=LATEST, snapshot_id=LATEST):
    if ref is not LATEST:
        validate_reference(ref)
    if ref is not LATEST and (not isinstance(ref, dict) or ref.get("instrumentId") != ident["instrumentId"]):
        raise DecisionError("invalid_reference_set")
    if ref is not LATEST and snapshot_id is not LATEST and snapshot_id != ref["snapshotId"]:
        raise DecisionError("invalid_reference_set")
    get_ref = lambda key: ref.get(key) if ref is not LATEST else LATEST
    try:
        snapshot = price(conn, ident["instrumentId"], snapshot_id if ref is LATEST else get_ref("snapshotId"))
    except DecisionError as error:
        if ref is not LATEST and error.status == 404:
            raise DecisionError("comparison_inputs_changed", 409) from None
        raise
    reviews, review_refs = rows(conn, "price_snapshot_reviews", "snapshot_id=?", ((snapshot or {}).get("snapshotId"),), "seq", get_ref("priceReviews"))
    # The reason owner predates market-qualified identity. Only its existing unambiguous ticker convention is reusable.
    suffix = re.search(r"\.(T|L|DE|PA|AS|MI|MC)$", ident["ticker"])
    scoped = ident["market"] == "KR" or (ident["market"] == "US" and not suffix and not re.fullmatch(r"\d{6}", ident["ticker"])) or (ident["market"] == "JP" and ident["ticker"].endswith(".T")) or (ident["market"] == "EUROPE" and suffix and suffix[1] != "T")
    scoped = scoped and bool(normalize_ticker(ident["ticker"]))
    if scoped:
        reason_value, reason_refs = reason(conn, normalize_ticker(ident["ticker"]), get_ref("reasonRevisionId"), get_ref("reasonReviews"), get_ref("reasonLegacyHash"))
    else:
        if ref is not LATEST and (get_ref("reasonRevisionId") is not None or get_ref("reasonReviews") or get_ref("reasonLegacyHash") is not None):
            raise DecisionError("invalid_reference_set")
        reason_value, reason_refs = {"status": "unknown", "revisionId": None, "text": "", "events": [], "legacyHash": None, "identityGap": "reason_identity_not_verified"}, []
    profile = exposure(conn, ident["ticker"], get_ref("exposureProfileId"), market=ident["market"]) if ident["market"] in {"US", "KR"} else None
    macro_rows, macro_refs, macro_max = macro(conn, files.root, at, get_ref("macroRows"), get_ref("macroMaxId"))
    report_value, report_ref, report_errors = report(files, ident, get_ref("report"), get_ref("reportReadErrors"))
    attempt = None
    attempt_hash = None
    if snapshot is None and (ref is LATEST or get_ref("attemptHash") is not None):
        attempts, attempt_hash = files.read("price-attempts.json")
        attempt = (attempts or {}).get(ident["instrumentId"])
        if ref is not LATEST and attempt_hash != get_ref("attemptHash"):
            raise DecisionError("comparison_inputs_changed", 409)
    refs = {"instrumentId": ident["instrumentId"], "snapshotId": (snapshot or {}).get("snapshotId"), "priceReviews": review_refs,
            "reasonRevisionId": reason_value["revisionId"], "reasonReviews": reason_refs, "reasonLegacyHash": reason_value.get("legacyHash"),
            "exposureProfileId": (profile or {}).get("profileId"), "macroRows": macro_refs, "macroMaxId": macro_max, "report": report_ref, "reportReadErrors": report_errors, "attemptHash": attempt_hash}
    interpretation = interpret(profile, macro_rows, at) if profile else None
    return {"identity": ident, "snapshot": snapshot, "reviews": reviews, "reason": reason_value, "report": report_value,
            "exposure": profile, "macro": interpretation, "attempt": attempt, "reportReadErrors": report_errors, "refs": refs}
