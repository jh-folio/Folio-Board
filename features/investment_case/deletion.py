"""Forward-only privacy deletion, with durable hashes and exact source identity."""
from __future__ import annotations

from copy import deepcopy
import re

from features.agent_mode.report_delete import DeleteRequest, execute_report_delete, SourceChangedError, acknowledge_delete_receipt
from features.common.canonical_reports import ReportKind, resolve_exact_report_path, CanonicalNotFoundError, CanonicalIdentityError
from . import CaseError, SLOTS
from .paths import action_lock, byte_hash, canonical, database, digest, identifier, journal_path, now, parse, safe_path
from . import store


def _assert_source_not_preparing(conn, source):
    for op in store.pending(conn):
        if any(r.get("kind") == source["kind"] and r.get("id") == source["id"] for r in op["metadata"].get("sourceRefs", {}).values()):
            raise CaseError("case_recovery_required", 409, operationId=op["operation_id"])


def tombstone(body, slots, personal, stamp, policy):
    body = deepcopy(body)
    for name in slots:
        item = body["inputs"][name]
        item.update(status="purged", reason="explicit_content_deletion", content=None)
        item.pop("requiresExclusion", None)
    if personal:
        body.update(decisionText="", uncertainties="", userReportedAt={"value": None, "precision": "unknown"}, selectedScenario=None, personalPurgedAt=stamp)
    body["purges"].append({"slots": sorted(slots), "personal": personal, "purgedAt": stamp, "policy": policy})
    return body


def _target(root, row, slots, personal, stamp, policy):
    from .service import _body
    body = _body(root, row)
    updated = tombstone(body, slots, personal, stamp, policy)
    return {"journalId": row["journal_id"], "caseId": row["case_id"], "oldHash": row["file_hash"], "newHash": byte_hash(canonical(updated)),
            "slots": sorted(slots), "personal": personal, "stamp": stamp, "policy": policy}


def _prepare(root, operation_id, request_hash, case_key, expected, meta):
    from .service import _assert_no_pending
    with store.Store(root).write() as conn:
        if case_key:
            store.assert_revision(conn, case_key, expected)
        _assert_no_pending(conn, case_key, [meta.get("source") or {}])
        # A pending publication may contain a source which has no index yet.
        source = meta.get("source")
        if source:
            _assert_source_not_preparing(conn, source)
        for target in meta["targets"]:
            row = store.index(conn, target["journalId"])
            if not row or row["status"] != "ready" or row["file_hash"] != target["oldHash"]:
                raise CaseError("journal_changed", 409)
        store.add_operation(conn, operation_id, request_hash, case_key, expected, "source_delete" if source else "purge", "deleting", meta, meta["stamp"])
        for target in meta["targets"]:
            conn.execute("UPDATE decision_journal_index SET status='deletion_pending' WHERE journal_id=?", (target["journalId"],))


def begin_purge(root, proposal, operation_id, request_hash, *, fault=None):
    request = proposal["request"]
    stamp = now()
    with database(root) as conn:
        row = store.index(conn, request["targetJournalId"])
        target = _target(root, row, list(SLOTS) if request["purgePersonal"] else request["purgeSlots"], request["purgePersonal"], stamp, "personal_request")
    meta = {"stamp": stamp, "targets": [target], "source": None, "result": {"caseId": row["case_id"], "caseRevision": request["expectedCaseRevision"] + 1, "journalId": row["journal_id"]}}
    _prepare(root, operation_id, request_hash, row["case_id"], request["expectedCaseRevision"], meta)
    from .service import _fault
    _fault("purge_prepared", fault)
    return finish_purge(root, operation_id, fault=fault)


def _source(root, kind, key):
    if kind not in {"company", "topic"} or not isinstance(key, str):
        raise CaseError("invalid_source_id")
    folder = "company-analysis" if kind == "company" else "topic-reports"
    safe_path(root, folder)  # the resolver reads identity from the source file
    try:
        path = resolve_exact_report_path(root, ReportKind.COMPANY_ANALYSIS if kind == "company" else ReportKind.TOPIC_REPORT, key)
    except CanonicalNotFoundError:
        raise CaseError("source_not_found", 404) from None
    except (CanonicalIdentityError, ValueError):
        raise CaseError("invalid_source_id") from None
    # The canonical resolver validates identity; this also bounds the configured
    # source directory against redirected directories before reading its bytes.
    path = safe_path(root, folder, path.name)
    return {"kind": kind, "id": key, "folder": folder, "name": path.name, "contentHash": byte_hash(path.read_bytes())}


def source_delete_preview(root, value, *, cache=None):
    from .service import CACHE, _assert_no_pending
    cache = cache or CACHE
    if not isinstance(value, dict) or set(value) - {"kind", "id", "policy"}:
        raise CaseError("invalid_source_deletion")
    policy = value.get("policy", "purge")
    if policy not in {"purge", "preserve"}:
        raise CaseError("invalid_deletion_policy")
    source = _source(root, value.get("kind"), value.get("id"))
    with database(root) as conn:
        _assert_no_pending(conn, None, [source])
        _assert_source_not_preparing(conn, source)
        links = store.source_links(conn, source["kind"], source["id"])
        affected = {}
        for row in links:
            affected.setdefault(row["journal_id"], {"journalId": row["journal_id"], "caseId": row["case_id"], "bodyHash": row["file_hash"], "slots": []})["slots"].append(row["slot"])
        # Fail before issuing an approval token when any body cannot be read.
        from .service import _body
        for key in affected:
            _body(root, store.index(conn, key))
    proposal = {"type": "source_delete", "source": source, "policy": policy, "affected": list(affected.values())}
    token = cache.put(root, proposal)
    return {"token": token, "canConfirm": True, "source": {k: v for k, v in source.items() if k not in {"folder", "name"}},
            "policy": policy, "affected": proposal["affected"], "linkedJournalCount": len(affected),
            "notice": "원본과 연결된 당시 보존본문을 함께 삭제합니다. 기존 백업은 자동 삭제하지 않습니다." if policy == "purge" else "원본을 삭제해도 연결된 개인 기록의 보존본문은 남습니다. 이 보존 선택을 확인해 주세요."}


def delete_source(root, kind, key, *, token=None, operation_id=None, fallback=None, cache=None, fault=None):
    """Called by the existing owner endpoints, with their original no-link path."""
    from .service import CACHE, _fault, _operation
    if kind not in {"company", "topic"} or not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", key):
        raise CaseError("invalid_source_id")
    safe_path(root, "company-analysis" if kind == "company" else "topic-reports")
    cache = cache or CACHE
    with action_lock(root):
        with database(root) as conn:
            links = store.source_links(conn, kind, key)
            if token and operation_id:
                identifier(operation_id)
                old = store.operation(conn, operation_id)
                if old:
                    if old["request_hash"] != digest(token) or (old["metadata"].get("source") or {}).get("id") != key or (old["metadata"].get("source") or {}).get("kind") != kind:
                        raise CaseError("operation_key_conflict", 409)
                    if old["status"] == "ready":
                        return {"deleted": old["metadata"].get("sourceOutcome") == "deleted", "id": key, **_operation(old)}
                    raise CaseError("case_recovery_required", 409, operationId=operation_id)
        if not token:
            if links:
                raise CaseError("journal_confirmation_required", 409)
            from .service import _assert_no_pending
            with database(root) as conn:
                _assert_no_pending(conn, None, [{"kind": kind, "id": key}])
                _assert_source_not_preparing(conn, {"kind": kind, "id": key})
            return fallback() if fallback else {"deleted": False, "id": key}
        identifier(operation_id)
        proposal = cache.get(root, token)
        if proposal.get("type") != "source_delete" or proposal["source"]["kind"] != kind or proposal["source"]["id"] != key:
            raise CaseError("preview_source_mismatch", 409)
        if _source(root, kind, key) != proposal["source"]:
            raise CaseError("source_changed", 409)
        fresh = source_delete_preview(root, {"kind": kind, "id": key, "policy": proposal["policy"]}, cache=cache)
        if fresh["affected"] != proposal["affected"]:
            raise CaseError("journal_links_changed", 409)
        stamp = now()
        with database(root) as conn:
            targets = [_target(root, store.index(conn, item["journalId"]), item["slots"], False, stamp, "source_deleted") for item in proposal["affected"]] if proposal["policy"] == "purge" else []
        meta = {"stamp": stamp, "targets": targets, "source": proposal["source"], "policy": proposal["policy"], "affected": proposal["affected"], "result": {"sourceKind": kind, "sourceId": key}}
        _prepare(root, operation_id, digest(token), None, 0, meta)
        _fault("purge_prepared", fault)
        result = finish_purge(root, operation_id, fault=fault)
        return {"deleted": result.get("sourceOutcome") == "deleted", "id": key, **result}


def finish_purge(root, operation_id, *, fault=None):
    from .service import _fault, _operation, _clean_temporary
    from features.common.canonical_report_io import atomic_write
    with database(root) as conn:
        op = store.operation(conn, operation_id)
    if not op or op["status"] not in {"deleting", "ready"}:
        raise CaseError("operation_not_recoverable", 409)
    if op["status"] == "ready":
        return _operation(op)
    meta = op["metadata"]
    for target in meta["targets"]:
        path = journal_path(root, target["journalId"])
        if not path.exists():
            raise CaseError("journal_file_missing", 409, operationId=operation_id)
        raw = path.read_bytes()
        checksum = byte_hash(raw)
        if checksum == target["oldHash"]:
            value = tombstone(parse(raw), target["slots"], target["personal"], target["stamp"], target["policy"])
            replacement = canonical(value)
            if byte_hash(replacement) != target["newHash"]:
                raise CaseError("journal_changed", 409)
            atomic_write(path, replacement)
            _fault("purge_replaced", fault)
        elif checksum != target["newHash"]:
            raise CaseError("journal_changed", 409, operationId=operation_id)
        journal_path(root, target["journalId"], pending=True).unlink(missing_ok=True)
        _clean_temporary(root, target["journalId"])
        with store.Store(root).write() as conn:
            row = store.index(conn, target["journalId"])
            if not row or row["file_hash"] not in {target["oldHash"], target["newHash"]}:
                raise CaseError("journal_changed", 409)
            conn.execute("UPDATE decision_journal_index SET file_hash=? WHERE journal_id=?", (target["newHash"], target["journalId"]))
            for slot in target["slots"]:
                conn.execute("DELETE FROM decision_journal_links WHERE journal_id=? AND slot=?", (target["journalId"], slot))
            _fault("purge_database_commit", fault)
    _fault("purge_bodies_done", fault)
    source = meta.get("source")
    if source:
        path = safe_path(root, source["folder"], source["name"])
        try:
            if meta.get("sourceOutcome"):
                # A previous durable outcome owns the deletion boundary, even
                # after its low-level receipt has been acknowledged. A restored
                # file (including identical bytes) is never acquired again.
                if path.exists():
                    raise SourceChangedError("source_changed")
                result = None
            else:
                result = execute_report_delete(DeleteRequest(root=path.parent, identity=f'{source["kind"]}:{source["id"]}', primary_names=(path.name,), target_names=(path.name,), expected_hashes={path.name: source["contentHash"]}, receipt_id=operation_id, fault_stage=fault.removeprefix("source:") if fault and fault.startswith("source:") else None))
            # Missing cannot establish who deleted the source; report it as a
            # partial outcome even when our previous response may have been lost.
            if result is not None:
                meta["sourceOutcome"] = "deleted" if result.deleted else "missing"
        except SourceChangedError as error:
            if str(error) != "source_changed":
                raise CaseError("source_tombstone_changed", 409, operationId=operation_id) from None
            meta["sourceOutcome"] = "changed"
        meta["outcome"] = "complete" if meta["sourceOutcome"] == "deleted" else "partial"
        with store.Store(root).write() as conn:
            store.set_operation(conn, operation_id, "deleting", meta)
        acknowledge_delete_receipt(path.parent, f'{source["kind"]}:{source["id"]}', operation_id)
    else:
        meta["outcome"] = "complete"
    with store.Store(root).write() as conn:
        if op["case_id"]:
            saved = store.assert_revision(conn, op["case_id"], op["expected_revision"])
            conn.execute("UPDATE investment_cases SET revision=revision+1,updated_at=? WHERE case_id=?", (meta["stamp"], op["case_id"]))
            conn.execute("INSERT INTO investment_case_events VALUES(?,?,?,?,?,?,?,?,?,?)", (operation_id, op["case_id"], op["expected_revision"] + 1, "purge", saved["lifecycle"], saved["lifecycle"], saved["episode_id"], None, meta["result"]["journalId"], meta["stamp"]))
        for target in meta["targets"]:
            conn.execute("UPDATE decision_journal_index SET status='ready' WHERE journal_id=?", (target["journalId"],))
        store.set_operation(conn, operation_id, "ready", meta)
        _fault("purge_completed_commit", fault)
    _fault("purge_committed", fault)
    with database(root) as conn:
        return _operation(store.operation(conn, operation_id))
