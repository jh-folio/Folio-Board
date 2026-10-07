"""Preview/confirm and durable, recoverable publication of personal journals."""
from __future__ import annotations

import json
import secrets
import threading
import time
import uuid
from copy import deepcopy

from features.common.atomic_replace import replace_with_retry
from features.common.canonical_report_io import atomic_write
from features.decision_readiness.inputs import has
from . import CaseError, MAX_BYTES, METHOD_VERSION, SCHEMA_VERSION, SPEC_SHA256, SLOTS
from .capture import capture, case_id, source_status
from .paths import action_lock, byte_hash, canonical, database, digest, identifier, journal_path, now, parse, safe_path
from . import store, validation


class PreviewCache:
    def __init__(self):
        self.entries = {}
        self.lock = threading.Lock()

    def put(self, root, value):
        token = secrets.token_hex(32)
        size = len(canonical(value))
        if size > 100 * 1024 * 1024:
            raise CaseError("preview_too_large", 413)
        with self.lock:
            self.entries = {k: v for k, v in self.entries.items() if v[0] > time.monotonic()}
            while len(self.entries) >= 20 or (self.entries and sum(v[3] for v in self.entries.values()) + size > 100 * 1024 * 1024):
                self.entries.pop(next(iter(self.entries)))
            self.entries[token] = (time.monotonic() + 900, str(safe_path(root, "investment-case")), deepcopy(value), size)
        return token

    def get(self, root, token):
        with self.lock:
            row = self.entries.get(token) if isinstance(token, str) else None
            if row is None or row[0] <= time.monotonic() or row[1] != str(safe_path(root, "investment-case")):
                raise CaseError("preview_expired", 409)
            return deepcopy(row[2])


CACHE = PreviewCache()


def _fault(stage, fault):
    if fault == stage:
        raise OSError("injected_case_write_failure")


def _operation(row):
    if not row:
        raise CaseError("operation_not_found", 404)
    meta = row["metadata"]
    return {"operationId": row["operation_id"], "status": row["status"], "kind": row["kind"], "createdAt": row["created_at"],
            "caseId": row["case_id"], "result": meta.get("result"), "journalId": meta.get("journalId"),
            "outcome": meta.get("outcome"), "sourceOutcome": meta.get("sourceOutcome"),
            "cancelAllowed": row["status"] == "preparing", "recoveryRequired": row["status"] in {"preparing", "deleting"}}


def get_operation(root, operation_id):
    identifier(operation_id)
    with database(root) as conn:
        return _operation(store.operation(conn, operation_id))


def _body(root, row):
    if row is None:
        raise CaseError("journal_not_found", 404)
    if row["status"] != "ready":
        raise CaseError("journal_deletion_pending", 409)
    path = journal_path(root, row["journal_id"])
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise CaseError("journal_file_missing", 409) from None
    if len(raw) > MAX_BYTES or byte_hash(raw) != row["file_hash"]:
        raise CaseError("journal_integrity_error", 409)
    value = parse(raw)
    if value.get("id") != row["journal_id"] or value.get("caseId") != row["case_id"] or value.get("sourceLayer") != "hypothesis" or value.get("reuseAsEvidence") is not False:
        raise CaseError("journal_integrity_error", 409)
    return value


def read_journal(root, journal_id, *, current=True):
    identifier(journal_id)
    with database(root) as conn:
        row = store.index(conn, journal_id)
        body = _body(root, row)
        corrections = [dict(r) for r in conn.execute("SELECT * FROM decision_journal_corrections WHERE journal_id=? ORDER BY noted_at,link_id", (journal_id,))] if has(conn, "decision_journal_corrections") else []
    links = [{"id": r["link_id"], "slot": r["slot"], "oldRef": json.loads(r["old_ref_json"]), "newRef": json.loads(r["new_ref_json"]), "notedAt": r["noted_at"]} for r in corrections]
    availability = {}
    if current:
        for name, item in body.get("inputs", {}).items():
            dependencies = item.get("dependencies") or []
            availability[name] = [{"ref": dep, "status": source_status(root, dep)} for dep in dependencies]
    return {"journal": body, "bodyHash": row["file_hash"], "sourceAvailability": availability, "corrections": links,
            "checkedAt": now(), "notice": "당시 입력을 보존한 개인 기록입니다. 현재 자료와 이후 정정은 별도로 표시합니다."}


def _assert_no_pending(conn, case_key, refs=(), *, except_id=None):
    sources = {(r.get("kind"), r.get("id")) for r in refs if r.get("id")}
    for op in store.pending(conn):
        if op["operation_id"] == except_id:
            continue
        source = op["metadata"].get("source") or {}
        if (case_key is not None and op["case_id"] == case_key) or (source.get("kind"), source.get("id")) in sources or any(t.get("caseId") == case_key for t in op["metadata"].get("targets", [])):
            raise CaseError("case_recovery_required", 409, operationId=op["operation_id"])


def read_case(root, instrument):
    captured = capture(root, instrument)
    saved = captured.pop("saved")
    with database(root) as conn:
        entries = store.journals(conn, captured["caseId"])
        events = [dict(r) for r in conn.execute("SELECT * FROM investment_case_events WHERE case_id=? ORDER BY case_revision", (captured["caseId"],))] if saved else []
        pending = []
        for row in store.pending(conn):
            source = row["metadata"].get("source") or {}
            affected = row["metadata"].get("targets", []) + row["metadata"].get("affected", [])
            matches_source = bool(source.get("id")) and any((source.get("kind"), source["id"]) == (r.get("kind"), r.get("id")) for r in captured["sourceRefs"].values())
            if row["case_id"] == captured["caseId"] or any(t.get("caseId") == captured["caseId"] for t in affected) or matches_source:
                pending.append(_operation(row))
    summaries = []
    for row in entries:
        summary = {"id": row["journal_id"], "recordedAt": row["recorded_at"], "episodeId": row["episode_id"], "status": row["status"], "bodyHash": row["file_hash"]}
        try:
            body = _body(root, row)
            summary.update(kind=body["kind"], preview=body.get("decisionText", "")[:240], purged=bool(body.get("personalPurgedAt")))
        except CaseError as error:
            summary.update(status="unavailable", reason=error.code)
        summaries.append(summary)
    recorded = json.loads(saved["refs_json"]) if saved else {}
    stale = []
    for key, previous in recorded.items():
        if key == "readiness":
            continue
        latest = captured["sourceRefs"].get(key) or {}
        if previous.get("contentHash") != latest.get("contentHash") or previous.get("id") != latest.get("id"):
            stale.append({"slot": key, "code": "source_missing" if latest.get("id") is None else "input_changed"})
        if previous.get("methodVersion") != latest.get("methodVersion"):
            stale.append({"slot": key, "code": "method_changed"})
    held = captured["portfolioPresence"]["held"]
    stage = saved["lifecycle"] if saved else None
    mismatch = bool(stage and held is not None and ((stage == "owned") != held))
    price = (captured["inputs"]["price"]["content"] or {}).get("snapshot") or {}
    scenarios = [{"snapshotId": price.get("snapshotId"), "label": r.get("label"), "horizon": r.get("horizon")} for r in (price.get("results") or {}).get("scenarios", [])]
    # The live Case is a projection. Full source text is delivered only by the
    # explicit journal preview and historical reader, never persisted in Case.
    input_summaries = {key: {k: v for k, v in item.items() if k != "content"} for key, item in captured.pop("inputs").items()}
    return {**captured, "schemaVersion": SCHEMA_VERSION, "specSha256": SPEC_SHA256, "lifecycle": stage,
            "episodeId": saved["episode_id"] if saved else None, "recordedRefs": recorded, "staleReasons": stale,
            "inputs": input_summaries, "journals": summaries, "events": events, "pendingOperations": pending, "scenarioOptions": scenarios,
            "lifecycleMismatch": mismatch, "notice": "검토 단계는 직접 붙인 기록이며 실제 보유는 Portfolio에서 확인합니다."}


def _journal(request, captured, *, journal_id="0" * 32, operation_id="0" * 32, episode_id="0" * 32, stamp="0000-00-00T00:00:00Z"):
    inputs = deepcopy(captured["inputs"])
    for key in request["excludedSlots"]:
        inputs[key].update(status="excluded", content=None, reason="user_excluded")
        inputs[key].pop("requiresExclusion", None)
    scenario = request.get("selectedScenario")
    if scenario:
        price = captured["inputs"]["price"]["content"] or {}
        snapshot = price.get("snapshot") or {}
        if scenario["snapshotId"] != snapshot.get("snapshotId") or not any(row.get("label") == scenario["label"] and row.get("horizon") == scenario["horizon"] for row in (snapshot.get("results") or {}).get("scenarios", [])):
            raise CaseError("selected_scenario_changed", 409)
    return {"schemaVersion": SCHEMA_VERSION, "methodVersion": METHOD_VERSION, "specSha256": SPEC_SHA256,
            "id": journal_id, "caseId": captured["caseId"], "instrumentId": request["instrumentId"], "episodeId": episode_id,
            "operationId": operation_id, "caseRevision": captured["caseRevision"] + 1, "recordedAt": stamp,
            "sourceLayer": "hypothesis", "reuseAsEvidence": False,
            "kind": "stage_change" if request["action"] == "transition" else request["kind"],
            "previousJournalId": request.get("previousJournalId"), "decisionText": request["decisionText"],
            "uncertainties": request["uncertainties"], "userReportedAt": request["userReportedAt"], "selectedScenario": scenario,
            "inputs": inputs, "inputFingerprint": captured["inputFingerprint"], "purges": []}


def _target(root, conn, journal_id, case_key):
    row = store.index(conn, journal_id)
    if not row or row["case_id"] != case_key:
        raise CaseError("journal_case_mismatch", 409)
    return row, _body(root, row)


def preview(root, raw_request, *, cache=CACHE):
    request = validation.request(raw_request)
    captured = capture(root, request["instrumentId"], request["selection"])
    expected, action = request["expectedCaseRevision"], request["action"]
    if captured["caseRevision"] != expected:
        raise CaseError("case_revision_changed", 409)
    if (action == "create") != (expected == 0):
        raise CaseError("case_already_exists" if action == "create" else "case_not_created", 409)
    target = None
    with database(root) as conn:
        _assert_no_pending(conn, captured["caseId"], captured["sourceRefs"].values())
        if request.get("previousJournalId"):
            previous, _ = _target(root, conn, request["previousJournalId"], captured["caseId"])
            if request["kind"] in {"partial_change", "reason_replaced"} and previous["episode_id"] != (captured["saved"] or {}).get("episode_id"):
                raise CaseError("journal_episode_mismatch", 409)
        if request.get("targetJournalId"):
            target = _target(root, conn, request["targetJournalId"], captured["caseId"])
    saved = captured["saved"]
    if action == "transition" and request["toStage"] == saved["lifecycle"]:
        raise CaseError("lifecycle_unchanged")
    makes_journal = action == "journal" or (action == "transition" and request["toStage"] == "owned")
    journal = _journal(request, captured) if makes_journal else None
    blocked = [key for key, item in (journal or {}).get("inputs", {}).items() if item.get("requiresExclusion")]
    size = len(canonical(journal)) if journal else 0
    value = {"request": request, "capture": {k: captured[k] for k in ("checkedAt", "inputFingerprint", "caseId", "caseRevision")}, "journal": journal, "size": size,
             "targetHash": target[0]["file_hash"] if target else None, "payloadHash": digest(journal) if journal else digest(request)}
    if action == "correction":
        item = captured["inputs"][request["correctionSlot"]]
        old = target[1]["inputs"][request["correctionSlot"]]["ref"]
        if not item["ref"].get("id") or item["ref"] == old:
            raise CaseError("no_new_source_reference", 409)
        value["correction"] = {"slot": request["correctionSlot"], "oldRef": old, "newRef": item["ref"]}
    allowed = size <= MAX_BYTES and not blocked
    return {"token": cache.put(root, value) if allowed else None, "canConfirm": allowed, "action": action, "caseId": captured["caseId"],
            "caseRevision": expected, "inputFingerprint": captured["inputFingerprint"], "methodVersion": METHOD_VERSION,
            "totalBytes": size, "maxBytes": MAX_BYTES, "blockedSlots": blocked, "reason": "bundle_too_large" if size > MAX_BYTES else "sensitive_content_requires_exclusion" if blocked else None,
            "journal": journal if size <= MAX_BYTES else None,
            "inputs": [{"slot": key, "status": item["status"], "reason": item["reason"], "ref": item["ref"], "preservationScope": item["preservationScope"], "bytes": len(canonical(item))} for key, item in (journal or {"inputs": captured["inputs"]})["inputs"].items()],
            "lifecycle": {"from": (saved or {}).get("lifecycle"), "to": request.get("toStage") or (saved or {}).get("lifecycle") or "researching"},
            "correction": value.get("correction"), "purge": {"journalId": request.get("targetJournalId"), "slots": list(SLOTS) if request["purgePersonal"] else request["purgeSlots"], "personal": request["purgePersonal"]} if action == "purge" else None,
            "notice": "선택한 당시 입력을 개인 기록으로 저장합니다. 자동 만료는 없으며 원본 삭제 시 연결 보존본문도 기본 삭제합니다. 기존 백업은 자동 삭제하지 않습니다."}


def _metadata(request, captured, journal, operation_id, stamp):
    saved = captured["saved"] or {}
    stage = request.get("toStage") or saved.get("lifecycle") or "researching"
    episode = journal["episodeId"] if journal else saved.get("episode_id") or uuid.uuid4().hex
    result = {"caseId": captured["caseId"], "caseRevision": captured["caseRevision"] + 1, "journalId": journal["id"] if journal else None}
    return {"instrumentId": request["instrumentId"], "journalId": result["journalId"], "fileHash": byte_hash(canonical(journal)) if journal else None,
            "stamp": stamp, "episodeId": episode, "previousEpisodeId": saved.get("episode_id") if request["kind"] == "reentry" else None,
            "stage": stage, "fromStage": saved.get("lifecycle"), "sourceRefs": captured["sourceRefs"], "fingerprint": captured["inputFingerprint"],
            "kind": request["kind"] if request["action"] == "journal" else request["action"], "previousJournalId": request.get("previousJournalId"),
            "result": result, "createdAt": saved.get("created_at") or stamp}


def _commit(root, operation_id, *, fault=None):
    with database(root) as conn:
        op = store.operation(conn, operation_id)
    if op is None:
        raise CaseError("operation_not_found", 404)
    if op["status"] == "ready":
        return _operation(op)
    if op["status"] != "preparing":
        raise CaseError("operation_not_recoverable", 409)
    meta, body = op["metadata"], None
    if meta["journalId"]:
        final = journal_path(root, meta["journalId"])
        staging = journal_path(root, meta["journalId"], pending=True)
        chosen = final if final.exists() else staging
        if not chosen.exists() or byte_hash(chosen.read_bytes()) != meta["fileHash"]:
            raise CaseError("recovery_unavailable", 409, operationId=operation_id)
        body = parse(chosen.read_bytes())
        if body.get("id") != meta["journalId"] or body.get("operationId") != operation_id or body.get("caseId") != op["case_id"]:
            raise CaseError("journal_integrity_error", 409)
        if chosen == staging:
            replace_with_retry(staging, final)
        _fault("published_file", fault)
    with store.Store(root).write() as conn:
        current = store.operation(conn, operation_id)
        if current["status"] == "ready":
            return _operation(current)
        store.assert_revision(conn, op["case_id"], op["expected_revision"])
        _assert_no_pending(conn, op["case_id"], meta["sourceRefs"].values(), except_id=operation_id)
        values = (meta["result"]["caseRevision"], meta["stage"], meta["episodeId"], canonical(meta["sourceRefs"]).decode(), meta["fingerprint"], METHOD_VERSION, meta["stamp"])
        if op["expected_revision"] == 0:
            conn.execute("INSERT INTO investment_cases VALUES(?,?,?,?,?,?,?,?,?,?)", (op["case_id"], meta["instrumentId"], *values[:6], meta["createdAt"], meta["stamp"]))
        else:
            conn.execute("UPDATE investment_cases SET revision=?,lifecycle=?,episode_id=?,refs_json=?,fingerprint=?,method=?,updated_at=? WHERE case_id=? AND revision=?", (*values, op["case_id"], op["expected_revision"]))
        conn.execute("INSERT INTO investment_case_events VALUES(?,?,?,?,?,?,?,?,?,?)", (operation_id, op["case_id"], meta["result"]["caseRevision"], meta["kind"], meta["fromStage"], meta["stage"], meta["episodeId"], meta["previousEpisodeId"], meta["journalId"] or meta["previousJournalId"], meta["stamp"]))
        if body:
            conn.execute("INSERT INTO decision_journal_index VALUES(?,?,?,?,?,?,?)", (body["id"], op["case_id"], body["episodeId"], operation_id, body["recordedAt"], meta["fileHash"], "ready"))
            for key, item in body["inputs"].items():
                if item["status"] != "preserved":
                    continue
                for dep in item["dependencies"]:
                    if dep.get("id"):
                        conn.execute("INSERT OR IGNORE INTO decision_journal_links VALUES(?,?,?,?,?)", (body["id"], key, dep["kind"], str(dep["id"]), dep.get("contentHash")))
        if meta.get("correction"):
            correction = meta["correction"]
            conn.execute("INSERT INTO decision_journal_corrections VALUES(?,?,?,?,?,?)", (operation_id, meta["targetJournalId"], correction["slot"], canonical(correction["oldRef"]).decode(), canonical(correction["newRef"]).decode(), meta["stamp"]))
        _fault("database_commit", fault)
        store.set_operation(conn, operation_id, "ready", meta)
    _fault("committed", fault)
    with database(root) as conn:
        return _operation(store.operation(conn, operation_id))


def confirm(root, token, operation_id, *, cache=CACHE, fault=None):
    identifier(operation_id)
    if not isinstance(token, str) or not re_token(token):
        raise CaseError("invalid_preview_token")
    with action_lock(root):
        with database(root) as conn:
            previous = store.operation(conn, operation_id)
        if previous:
            if previous["request_hash"] != digest(token):
                raise CaseError("operation_key_conflict", 409)
            if previous["status"] == "ready":
                return _operation(previous)
            raise CaseError("case_recovery_required", 409, operationId=operation_id)
        proposal = cache.get(root, token)
        request = proposal["request"]
        captured = capture(root, request["instrumentId"], request["selection"], at=proposal["capture"]["checkedAt"])
        if captured["caseRevision"] != request["expectedCaseRevision"] or captured["inputFingerprint"] != proposal["capture"]["inputFingerprint"]:
            raise CaseError("inputs_changed", 409)
        with database(root) as conn:
            _assert_no_pending(conn, captured["caseId"], captured["sourceRefs"].values())
            if request.get("targetJournalId"):
                target, _ = _target(root, conn, request["targetJournalId"], captured["caseId"])
                if target["file_hash"] != proposal["targetHash"]:
                    raise CaseError("journal_changed", 409)
            if request.get("previousJournalId"):
                _target(root, conn, request["previousJournalId"], captured["caseId"])
        if request["action"] == "purge":
            from .deletion import begin_purge
            return begin_purge(root, proposal, operation_id, digest(token), fault=fault)
        stamp = now()
        saved = captured["saved"] or {}
        episode = uuid.uuid4().hex if request["kind"] == "reentry" or not saved else saved["episode_id"]
        journal = None
        if proposal["journal"]:
            unchanged = _journal(request, captured)
            if digest(unchanged) != proposal["payloadHash"]:
                raise CaseError("inputs_changed", 409)
            journal = _journal(request, captured, journal_id=uuid.uuid4().hex, operation_id=operation_id, episode_id=episode, stamp=stamp)
            if len(canonical(journal)) != proposal["size"] or len(canonical(journal)) > MAX_BYTES:
                raise CaseError("bundle_too_large", 413)
        meta = _metadata(request, captured, journal, operation_id, stamp)
        if proposal.get("correction"):
            meta.update(correction=proposal["correction"], targetJournalId=request["targetJournalId"])
        with store.Store(root).write() as conn:
            store.assert_revision(conn, captured["caseId"], request["expectedCaseRevision"])
            _assert_no_pending(conn, captured["caseId"], captured["sourceRefs"].values())
            store.add_operation(conn, operation_id, digest(token), captured["caseId"], request["expectedCaseRevision"], request["action"], "preparing", meta, stamp)
        _fault("prepared", fault)
        if journal:
            atomic_write(journal_path(root, journal["id"], pending=True), canonical(journal))
        _fault("staged", fault)
        return _commit(root, operation_id, fault=fault)


def re_token(value):
    import re
    return re.fullmatch(r"[0-9a-f]{64}", value) is not None


def recover(root, operation_id, *, fault=None):
    identifier(operation_id)
    with action_lock(root):
        with database(root) as conn:
            op = store.operation(conn, operation_id)
        if not op:
            raise CaseError("operation_not_found", 404)
        if op["status"] == "deleting":
            from .deletion import finish_purge
            return finish_purge(root, operation_id, fault=fault)
        return _commit(root, operation_id, fault=fault)


def cancel(root, operation_id, *, confirmed=False):
    identifier(operation_id)
    with action_lock(root):
        with database(root) as conn:
            op = store.operation(conn, operation_id)
            if not op:
                raise CaseError("operation_not_found", 404)
            if op["status"] != "preparing":
                raise CaseError("operation_not_cancellable", 409)
            key = op["metadata"].get("journalId")
            if key and store.index(conn, key):
                raise CaseError("journal_already_published", 409)
        if not confirmed:
            return {"operationId": operation_id, "journalId": key, "requiresConfirmation": True, "notice": "미완료 저장의 준비 파일을 지웁니다. 이미 게시된 기록은 취소할 수 없습니다."}
        if key:
            for path in (journal_path(root, key), journal_path(root, key, pending=True)):
                path.unlink(missing_ok=True)
            _clean_temporary(root, key)
        with store.Store(root).write() as conn:
            store.set_operation(conn, operation_id, "failed", {**op["metadata"], "outcome": "cancelled"})
        with database(root) as conn:
            return _operation(store.operation(conn, operation_id))


def _clean_temporary(root, key):
    """Only this operation's atomic temporary names, inside the validated folder."""
    import re
    directory = safe_path(root, "decision-journals")
    if directory.exists():
        pattern = re.compile(rf"\.(?:\.pending-)?{identifier(key)}\.json\.[0-9a-f]{{32}}\.tmp")
        for entry in directory.iterdir():
            if pattern.fullmatch(entry.name):
                safe_path(root, "decision-journals", entry.name).unlink(missing_ok=True)
