"""One bounded, read-only capture of the existing owners. No network or migrations."""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from copy import deepcopy

from features.decision_readiness import METHOD_VERSION as READINESS_METHOD, DecisionError
from features.decision_readiness.inputs import LATEST, capture as capture_owner, criteria, has, identity
from features.decision_readiness.comparison import candidate
from features.decision_readiness.portfolio_fit import raw_portfolio, instrument_for
from features.thesis_tracking import reason_history
from features.thesis_tracking.store import get_delta
from features.price_scenarios.attribution import historical_attribution
from features.macro_state.store import StateStore
from . import CaseError, METHOD_VERSION, SLOTS
from .paths import SourceFiles, database, digest, now
from .preservation import preserve, REPORT_FIELDS, REASON_FIELDS
from . import store

SAFE_SOURCE_ID = re.compile(r"[A-Za-z0-9_-]{1,160}")


def case_identity(instrument):
    try:
        return identity(instrument)
    except DecisionError as error:
        raise CaseError(error.code, 400 if error.status == 422 else error.status) from None


def case_id(instrument):
    case_identity(instrument)
    return digest(instrument)


def ref(kind, key, value, *, checksum=None, revision=None, as_of=None, method=None, **extra):
    return {"kind": kind, "id": key, "revision": revision, "asOf": as_of, "methodVersion": method,
            "contentHash": checksum or (digest(value) if value is not None else None), **extra}


def slot(name, reference, value, *, reason="source_missing", fields=None, dependencies=None, layer="source-grounded"):
    reference = {**reference, "slot": name, "status": "available" if value is not None else "unavailable", "reason": None if value is not None else reason}
    result = {"ref": reference, "status": "preserved" if value is not None else "unavailable", "reason": None if value is not None else reason,
              "content": None, "originalLayer": layer, "dependencies": dependencies or ([reference] if reference.get("id") else []),
              "preservationScope": {"kind": "reader_fields", "attachmentsPreserved": False, "omittedFieldCount": 0}}
    if value is not None:
        try:
            result["content"], result["preservationScope"] = preserve(value, allowed=fields)
        except CaseError as error:
            result.update(status="unavailable", reason=error.code, requiresExclusion=True)
    return result


def read_report(files, folder, source_id):
    if not isinstance(source_id, str) or not SAFE_SOURCE_ID.fullmatch(source_id):
        raise CaseError("invalid_source_id")
    if folder == "company-analysis":
        value, checksum = files.read(f"{folder}/{source_id}.json")
        if value is not None and (not isinstance(value, dict) or value.get("id", source_id) != source_id):
            raise CaseError("report_identity_invalid", 409)
        return value, checksum
    found = []
    for name in files.catalog(folder):
        value, checksum = files.read(f"{folder}/{name}")
        if isinstance(value, dict) and value.get("id") == source_id:
            found.append((value, checksum))
    if len(found) > 1:
        raise CaseError("report_identity_conflict", 409)
    return found[0] if found else (None, None)


def _report_matches(value, ident):
    company = (value or {}).get("company") or {}
    return isinstance(company, dict) and company.get("ticker") == ident["ticker"] and str(company.get("market") or "").upper() == ident["market"]


def _reason(conn, data):
    key = data["refs"]["reasonRevisionId"]
    value = reason_history.get(conn, key) if key else None
    return slot("reason", ref("reason_revision", key, value, revision=(value or {}).get("revision"), as_of=(value or {}).get("recordedAt")), value,
                fields=REASON_FIELDS, reason="reason_identity_unverified" if data["reason"].get("identityGap") else "reason_revision_missing", layer="hypothesis")


def _delta(conn, data):
    events = data["reason"].get("events") or []
    event = next((row for row in events if row.get("delta_id")), None)
    value = get_delta(conn, event["delta_id"]) if event and has(conn, "thesis_delta") else None
    if value and value.get("reasonRevisionId") != data["refs"]["reasonRevisionId"]:
        value = None
    return slot("delta", ref("thesis_delta", (value or {}).get("deltaId"), value, as_of=(value or {}).get("generatedAt")), value,
                reason="reason_delta_missing", layer="hypothesis")


def _macro(conn, data):
    states, refs = [], []
    if has(conn, "macro_state_snapshots"):
        seen = set()
        for row in conn.execute("SELECT * FROM macro_state_snapshots WHERE market=? ORDER BY as_of DESC,seq DESC", (data["identity"]["market"],)):
            if row["axis"] in seen:
                continue
            seen.add(row["axis"])
            body = StateStore._project(conn, row) if has(conn, "macro_state_decisions") else json.loads(row["body"])
            states.append(body)
            refs.append(ref("macro_snapshot", row["id"], body, as_of=row["as_of"], method=row["method"]))
    narrative = None
    if has(conn, "market_state_snapshots"):
        row = conn.execute("SELECT * FROM market_state_snapshots WHERE status!='archived' ORDER BY as_of DESC,snapshot_id DESC LIMIT 1").fetchone()
        if row:
            narrative = json.loads(row["payload_json"])
            refs.append(ref("market_state", row["snapshot_id"], narrative, as_of=row["as_of"]))
    profile = data["exposure"]
    if profile:
        refs.append(ref("exposure_profile", profile.get("profileId"), profile, as_of=profile.get("asOf")))
    value = {"states": states, "marketState": narrative, "profile": profile, "interpretation": data["macro"], "sourceRefs": refs} if refs else None
    stable = deepcopy(value)
    if stable:
        for item in (stable.get("interpretation") or {}).get("items", []):
            if isinstance(item.get("observation"), dict):
                item["observation"].pop("asOf", None)  # query evaluation time, not the source vintage
        for context in (stable.get("interpretation") or {}).get("financialContext", []):
            context.pop("asOf", None)
    return slot("macro", ref("macro_context", digest(refs) if refs else None, value, checksum=digest(stable) if stable else None,
                             as_of=max((r["asOf"] for r in refs if r.get("asOf")), default=None), method="owner_snapshots"), value,
                dependencies=refs, reason="macro_state_missing")


def _review(files, ident, selection):
    day = selection.get("reviewDate")
    if day is not None and (not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day)):
        raise CaseError("invalid_review_date")
    if day:
        dt.date.fromisoformat(day)
        names = [f"{day}.json"]
    else:
        names = sorted((n for n in files.catalog("investment-review") if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", n)), reverse=True)
    for name in names:
        value, checksum = files.read(f"investment-review/{name}")
        if not isinstance(value, dict):
            continue
        rows = value.get("positionReviews") or []
        matches = [r for r in rows if isinstance(r, dict) and (r.get("instrumentId") == ident["instrumentId"] if r.get("instrumentId") else instrument_for(r) == ident["instrumentId"])]
        unverified = [r for r in rows if isinstance(r, dict) and str(r.get("ticker") or "").upper().replace(".", "-") == ident["ticker"].replace(".", "-")]
        if not matches and not unverified and not day:
            continue
        reference = ref("investment_review", name[:-5], value, checksum=checksum, revision=value.get("reviewRevision"), as_of=value.get("generatedAt"), method=value.get("methodVersion"))
        if len(matches) != 1:
            return slot("review", {**reference, "relation": "user_selected_context" if day else "identity_unverified", "identityStatus": "unverified"}, None, reason="review_identity_unverified", layer="hypothesis")
        body = {key: value.get(key) for key in ("date", "reviewRevision", "generatedAt", "reviewState", "summary", "coverage", "uncertainties", "counterEvidence", "portfolioRisks", "inputBasis", "freshness") if key in value}
        # Historical inputBasis may contain other holdings; retain lineage, not their personal reasons.
        body["inputBasis"] = {key: (value.get("inputBasis") or {}).get(key) for key in ("status", "capturedAt", "fingerprint", "marketData")}
        body["positionReviews"] = matches
        return slot("review", reference, body, layer="hypothesis")
    return slot("review", ref("investment_review", day, None), None, reason="investment_review_missing", layer="hypothesis")


def capture(root, instrument, selection=None, *, at=None):
    ident = case_identity(instrument)
    selection = dict(selection or {})
    stamp = at or now()
    files = SourceFiles(root)
    try:
        with database(root) as conn:
            saved = store.case(conn, case_id(instrument))
            explicit_research = "researchId" in selection
            if saved and not explicit_research:
                previous = json.loads(saved["refs_json"])
                selection["researchId"] = (previous.get("research") or {}).get("id")
            personal = criteria(conn)
            data = capture_owner(conn, files, ident, stamp, snapshot_id=selection.get("snapshotId") or LATEST)
            if selection.get("companyId"):
                value, checksum = read_report(files, "company-analysis", selection["companyId"])
                if value is None or not _report_matches(value, ident):
                    raise CaseError("company_report_identity_unverified", 409)
                data["report"], data["refs"]["report"] = value, {"id": selection["companyId"], "hash": checksum}
            portfolio, portfolio_hash = raw_portfolio(files)
            output = candidate(data, personal, stamp, 5, portfolio)
            report = data["report"]
            report_ref = data["refs"]["report"] or {}
            inputs = {"company": slot("company", ref("company", report_ref.get("id"), report, checksum=report_ref.get("hash"),
                revision=(report or {}).get("revision"), as_of=(report or {}).get("generatedAt"), method=(report or {}).get("methodVersion")), report, fields=REPORT_FIELDS)}
            research = research_hash = None
            if selection.get("researchId"):
                research, research_hash = read_report(files, "topic-reports", selection["researchId"])
                if research is None and explicit_research:
                    raise CaseError("research_report_missing", 404)
            same = _report_matches(research, ident) if research else False
            inputs["research"] = slot("research", ref("topic", selection.get("researchId"), research, checksum=research_hash,
                as_of=(research or {}).get("generatedAt"), relation="same_security" if same else "user_selected_context",
                identityStatus="verified" if same else "unverified"), research, fields=REPORT_FIELDS, reason="source_missing" if selection.get("researchId") else "research_not_selected")
            inputs["reason"] = _reason(conn, data)
            inputs["delta"] = _delta(conn, data)
            inputs["macro"] = _macro(conn, data)
            inputs["review"] = _review(files, ident, selection)
            snapshot = data["snapshot"]
            price_ref = ref("price_snapshot", (snapshot or {}).get("snapshotId"), snapshot, as_of=(snapshot or {}).get("asOf"), method=((snapshot or {}).get("inputs") or {}).get("methodVersion"))
            criteria_ref = ref("valuation_criteria", str(personal["revisionId"]) if personal else None, personal, revision=(personal or {}).get("revisionId"), as_of=(personal or {}).get("createdAt"))
            price_body = {"snapshot": snapshot, "criteria": personal, "reviewRows": data["reviews"], "returnAttribution": output["dimensions"]["returnSource"]} if snapshot or personal else None
            inputs["price"] = slot("price", {**price_ref, "criteriaRef": criteria_ref}, price_body,
                dependencies=[r for r in (price_ref, criteria_ref) if r["id"]], reason="price_snapshot_missing")
            readiness = {"evaluatedAt": stamp, "methodVersion": READINESS_METHOD, **output["readiness"]}
            readiness.pop("projection", None)
            # No report/reason prose is duplicated in this derived slot.
            dependencies = [r for r in (price_ref, criteria_ref) if r["id"]]
            inputs["readiness"] = slot("readiness", ref("readiness", digest(dependencies), readiness, as_of=stamp, method=READINESS_METHOD), readiness, dependencies=dependencies)
            refs = {key: inputs[key]["ref"] for key in SLOTS}
            # The time of viewing is not a new input. Preserve it in the journal,
            # while conflicts and live Agent scopes compare stable owner inputs.
            stable_refs = {k: v for k, v in refs.items() if k != "readiness"}
            fingerprint = digest({"refs": stable_refs, "readiness": {k: v for k, v in readiness.items() if k != "evaluatedAt"}, "portfolioHash": portfolio_hash, "method": METHOD_VERSION})
            held = output["dimensions"]["portfolioOverlap"]["value"]["heldSameSecurity"]
            files.verify()
            return {"identity": ident, "caseId": case_id(instrument), "saved": saved, "caseRevision": saved["revision"] if saved else 0,
                    "inputs": inputs, "sourceRefs": refs, "inputFingerprint": fingerprint, "methodVersion": METHOD_VERSION,
                    "checkedAt": stamp, "portfolioPresence": {"held": held, "authority": "portfolio", "contentHash": portfolio_hash},
                    "reasonSummary": (inputs["reason"]["content"] or {}).get("content"), "readiness": readiness,
                    "gaps": [{"slot": k, "reason": v["reason"]} for k, v in inputs.items() if v["status"] != "preserved"]}
    except DecisionError as error:
        raise CaseError("inputs_changed" if error.status == 409 else error.code, error.status) from None


def source_status(root, reference):
    """Inspect the exact old owner ID, never substitute the newest report."""
    kind, key, expected = reference.get("kind"), reference.get("id"), reference.get("contentHash")
    if not key:
        return "unavailable"
    files = SourceFiles(root)
    try:
        if kind in {"company", "topic"}:
            value, checksum = read_report(files, "company-analysis" if kind == "company" else "topic-reports", key)
        elif kind == "investment_review":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", key):
                return "identity_unverified"
            value, checksum = files.read(f"investment-review/{key}.json")
        else:
            with database(root) as conn:
                value = None
                if kind == "reason_revision" and has(conn, "reason_revision"):
                    value = reason_history.get(conn, key)
                elif kind == "thesis_delta" and has(conn, "thesis_delta"):
                    value = get_delta(conn, key)
                elif kind == "price_snapshot" and has(conn, "price_snapshots"):
                    from features.price_scenarios.store import PriceStore
                    row = conn.execute("SELECT * FROM price_snapshots WHERE id=?", (key,)).fetchone()
                    value = PriceStore._load(row) if row else None
                elif kind == "valuation_criteria" and has(conn, "valuation_user_criteria"):
                    value = criteria(conn, int(key))
                elif kind == "market_state" and has(conn, "market_state_snapshots"):
                    row = conn.execute("SELECT payload_json FROM market_state_snapshots WHERE snapshot_id=?", (key,)).fetchone()
                    value = json.loads(row[0]) if row else None
                elif kind == "macro_snapshot" and has(conn, "macro_state_snapshots"):
                    row = conn.execute("SELECT * FROM macro_state_snapshots WHERE id=?", (key,)).fetchone()
                    value = StateStore._project(conn, row) if row and has(conn, "macro_state_decisions") else json.loads(row["body"]) if row else None
                elif kind == "exposure_profile" and has(conn, "company_macro_exposures"):
                    row = conn.execute("SELECT body FROM company_macro_exposures WHERE id=?", (key,)).fetchone()
                    value = json.loads(row[0]) if row else None
                else:
                    return "unknown"
                checksum = digest(value) if value is not None else None
        files.verify()
        return "source_missing" if value is None else "current" if checksum == expected else "source_changed"
    except (CaseError, DecisionError, ValueError, TypeError, KeyError, OSError, sqlite3.Error):
        return "source_unreadable"
