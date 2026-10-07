import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import FastAPI

from features.investment_case import CaseError, MAX_BYTES
from features.investment_case import service, deletion
from features.investment_case.paths import canonical, journal_path, database
from features.investment_case.capture import capture
from features.investment_case.routes import create_case_router
from features.investment_case.agent_context import context
from features.decision_readiness.tests.test_capture import seeded
from features.thesis_tracking import store as thesis_store, reason_history
from features.thesis_tracking.model import Thesis
from features.market_memory.tests.live_http import LiveHttpClient


def write(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))
    return path


def request(root, action="journal", **extra):
    return {"instrumentId": "US:ACME", "expectedCaseRevision": service.read_case(root, "US:ACME")["caseRevision"], "action": action, **extra}


def save(root, action="journal", **extra):
    proposal = service.preview(root, request(root, action, **extra))
    assert proposal["canConfirm"], proposal
    return service.confirm(root, proposal["token"], uuid4().hex)


def setup(root):
    price = seeded(root)
    price.save_criteria(required_return="10", min_margin_of_safety="20", holding_years=10)
    connection = thesis_store.connect(price.path)
    try:
        thesis_store.upsert_thesis(connection, Thesis(ticker="ACME", core_thesis="이유 A", falsification_triggers=["현금 전환 악화"]), edit_source="manual")
        connection.commit()
    finally:
        connection.close()
    report = write(root, "company-analysis/report-a.json", {"id": "report-a", "company": {"ticker": "ACME", "market": "US"}, "generatedAt": "2025-03-03T00:00:00Z", "markdown": "보고서 V1", "sources": [{"id": "SEC", "url": "https://sec.gov/filing", "apiKey": "never-copy"}]})
    save(root, "create")
    return price, report


def test_get_and_preview_are_read_only_even_without_schema(tmp_path):
    assert service.read_case(tmp_path, "US:ACME")["caseRevision"] == 0
    service.preview(tmp_path, request(tmp_path, "create"))
    assert list(tmp_path.iterdir()) == []
    save(tmp_path, "create")
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    service.read_case(tmp_path, "US:ACME")
    service.preview(tmp_path, request(tmp_path, decisionText="선택 기록"))
    assert {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_old_inputs_reopen_after_reason_report_and_criteria_change(tmp_path):
    price, report = setup(tmp_path)
    first = save(tmp_path, decisionText="개인 결정", uncertainties="수요 불확실", userReportedAt={"precision": "date", "value": "2025-01-02"})
    old = service.read_journal(tmp_path, first["journalId"])
    assert old["journal"]["inputs"]["reason"]["content"]["content"]["core_thesis"] == "이유 A"
    assert "apiKey" not in json.dumps(old)
    assert old["journal"]["inputs"]["price"]["content"]["snapshot"]["results"]["reverse"]
    write(tmp_path, str(report.relative_to(tmp_path)), {"id": "report-a", "company": {"ticker": "ACME", "market": "US"}, "markdown": "보고서 V2"})
    connection = thesis_store.connect(price.path)
    try:
        thesis_store.upsert_thesis(connection, Thesis(ticker="ACME", core_thesis="이유 B"), edit_source="manual"); connection.commit()
    finally:
        connection.close()
    price.save_criteria(required_return="25", holding_years=10, expected_revision_id=1)
    again = service.read_journal(tmp_path, first["journalId"])
    assert again["journal"] == old["journal"] and again["bodyHash"] == old["bodyHash"]
    assert again["sourceAvailability"]["company"][0]["status"] == "source_changed"
    assert service.read_case(tmp_path, "US:ACME")["reasonSummary"]["core_thesis"] == "이유 B"
    save(tmp_path, "correction", targetJournalId=first["journalId"], correctionSlot="company")
    assert service.read_journal(tmp_path, first["journalId"])["corrections"][0]["oldRef"] != service.read_journal(tmp_path, first["journalId"])["corrections"][0]["newRef"]


def test_lifecycle_is_explicit_and_episodes_keep_history(tmp_path):
    save(tmp_path, "create")
    owned = save(tmp_path, "transition", toStage="owned")
    body = service.read_journal(tmp_path, owned["journalId"])["journal"]
    assert body["kind"] == "stage_change" and body["decisionText"] == ""
    assert service.read_case(tmp_path, "US:ACME")["lifecycleMismatch"] is True
    partial = save(tmp_path, kind="partial_change", previousJournalId=body["id"])
    assert service.read_journal(tmp_path, partial["journalId"])["journal"]["episodeId"] == body["episodeId"]
    save(tmp_path, "transition", toStage="archived")
    reentry = save(tmp_path, kind="reentry", previousJournalId=body["id"], toStage="researching")
    assert service.read_journal(tmp_path, reentry["journalId"])["journal"]["episodeId"] != body["episodeId"]
    assert not (tmp_path / "portfolio.json").exists()
    with pytest.raises(CaseError, match="journal_episode_mismatch"):
        service.preview(tmp_path, request(tmp_path, kind="partial_change", previousJournalId=body["id"]))


@pytest.mark.parametrize("stage", ["prepared", "staged", "published_file", "database_commit", "committed"])
def test_publication_faults_recover_exactly_or_cancel_missing_stage(tmp_path, stage):
    save(tmp_path, "create")
    proposal = service.preview(tmp_path, request(tmp_path, decisionText="중단 전 기록"))
    operation = uuid4().hex
    with pytest.raises(OSError):
        service.confirm(tmp_path, proposal["token"], operation, fault=stage)
    first = service.get_operation(tmp_path, operation)
    if stage == "prepared":
        with pytest.raises(CaseError, match="recovery_unavailable"):
            service.recover(tmp_path, operation)
        with pytest.raises(CaseError, match="case_recovery_required"):
            service.preview(tmp_path, request(tmp_path))
        assert service.cancel(tmp_path, operation)["requiresConfirmation"]
        assert service.cancel(tmp_path, operation, confirmed=True)["status"] == "failed"
        assert service.read_case(tmp_path, "US:ACME")["caseRevision"] == 1
        return
    result = service.recover(tmp_path, operation)
    assert result["journalId"] == first["journalId"]
    assert result["createdAt"] == first["createdAt"]
    assert service.confirm(tmp_path, proposal["token"], operation) == result
    assert len(service.read_case(tmp_path, "US:ACME")["journals"]) == 1
    assert service.read_journal(tmp_path, result["journalId"])["journal"]["decisionText"] == "중단 전 기록"


def test_conflicting_preview_and_repeated_operation_are_not_duplicate_writes(tmp_path):
    save(tmp_path, "create")
    one = service.preview(tmp_path, request(tmp_path))
    two = service.preview(tmp_path, request(tmp_path, decisionText="다른 기록"))
    def commit(p):
        try:
            return service.confirm(tmp_path, p["token"], uuid4().hex)
        except CaseError as e:
            return e.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(commit, [one, two]))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert "inputs_changed" in results
    assert len(service.read_case(tmp_path, "US:ACME")["journals"]) == 1


def test_missing_tampered_staging_cannot_be_healed_from_new_sources(tmp_path):
    setup(tmp_path)
    proposal = service.preview(tmp_path, request(tmp_path))
    operation = uuid4().hex
    with pytest.raises(OSError): service.confirm(tmp_path, proposal["token"], operation, fault="staged")
    key = service.get_operation(tmp_path, operation)["journalId"]
    journal_path(tmp_path, key, pending=True).write_text("tampered")
    with pytest.raises(CaseError, match="recovery_unavailable"): service.recover(tmp_path, operation)
    service.cancel(tmp_path, operation, confirmed=True)
    assert not journal_path(tmp_path, key, pending=True).exists()


def test_deleted_source_is_distinct_from_retained_copy_and_purge_is_explicit(tmp_path):
    _, report = setup(tmp_path)
    saved = save(tmp_path)
    report.unlink()
    current = service.read_journal(tmp_path, saved["journalId"])
    assert current["sourceAvailability"]["company"][0]["status"] == "source_missing"
    assert current["journal"]["inputs"]["company"]["content"]["markdown"] == "보고서 V1"
    save(tmp_path, "purge", targetJournalId=saved["journalId"], purgePersonal=True)
    purged = service.read_journal(tmp_path, saved["journalId"])["journal"]
    assert all(item["content"] is None for item in purged["inputs"].values())
    assert purged["personalPurgedAt"] and purged["id"] == saved["journalId"]


def test_preparing_journal_blocks_unlinked_source_delete_and_preview(tmp_path):
    _, report = setup(tmp_path)
    proposal = service.preview(tmp_path, request(tmp_path))
    operation = uuid4().hex
    with pytest.raises(OSError): service.confirm(tmp_path, proposal["token"], operation, fault="staged")
    with pytest.raises(CaseError, match="case_recovery_required"):
        deletion.delete_source(tmp_path, "company", "report-a", fallback=lambda: report.unlink())
    with pytest.raises(CaseError, match="case_recovery_required"):
        deletion.source_delete_preview(tmp_path, {"kind": "company", "id": "report-a"})
    assert report.exists()
    service.recover(tmp_path, operation)


@pytest.mark.parametrize("stage", ["purge_prepared", "purge_replaced", "purge_database_commit", "purge_bodies_done", "purge_completed_commit", "purge_committed"])
def test_purge_faults_are_hidden_then_forward_completed(tmp_path, stage):
    setup(tmp_path); saved = save(tmp_path, decisionText="나중에 삭제할 본문")
    proposal = service.preview(tmp_path, request(tmp_path, "purge", targetJournalId=saved["journalId"], purgePersonal=True))
    operation = uuid4().hex
    with pytest.raises(OSError): service.confirm(tmp_path, proposal["token"], operation, fault=stage)
    if stage != "purge_committed":
        with pytest.raises(CaseError, match="journal_deletion_pending"): service.read_journal(tmp_path, saved["journalId"])
        with pytest.raises(CaseError, match="operation_not_cancellable"): service.cancel(tmp_path, operation, confirmed=True)
    assert service.recover(tmp_path, operation)["status"] == "ready"
    assert service.read_journal(tmp_path, saved["journalId"])["journal"]["decisionText"] == ""


@pytest.mark.parametrize("policy", ["purge", "preserve"])
def test_source_delete_confirmation_applies_selected_retention_policy(tmp_path, policy):
    _, report = setup(tmp_path); saved = save(tmp_path)
    with pytest.raises(CaseError, match="journal_confirmation_required"):
        deletion.delete_source(tmp_path, "company", "report-a")
    proposal = deletion.source_delete_preview(tmp_path, {"kind": "company", "id": "report-a", "policy": policy})
    result = deletion.delete_source(tmp_path, "company", "report-a", token=proposal["token"], operation_id=uuid4().hex)
    assert result["deleted"] and not report.exists()
    body = service.read_journal(tmp_path, saved["journalId"])["journal"]
    assert (body["inputs"]["company"]["content"] is None) == (policy == "purge")


@pytest.mark.parametrize("stage", ["purge_replaced", "source:journaled", "source:renamed", "source:unlinked", "source:refreshed"])
def test_recovery_never_deletes_regenerated_v2(tmp_path, stage):
    _, report = setup(tmp_path); saved = save(tmp_path)
    proposal = deletion.source_delete_preview(tmp_path, {"kind": "company", "id": "report-a"})
    operation = uuid4().hex
    with pytest.raises((OSError, RuntimeError)):
        deletion.delete_source(tmp_path, "company", "report-a", token=proposal["token"], operation_id=operation, fault=stage)
    report.write_bytes(canonical({"id": "report-a", "company": {"ticker": "ACME", "market": "US"}, "markdown": "V2 survives"}))
    result = service.recover(tmp_path, operation)
    assert result["status"] == "ready" and result["outcome"] == "partial" and result["sourceOutcome"] == "changed"
    assert json.loads(report.read_bytes())["markdown"] == "V2 survives"
    assert service.read_journal(tmp_path, saved["journalId"])["journal"]["inputs"]["company"]["content"] is None


@pytest.mark.parametrize("stage", ["source:renamed", "source:unlinked", "source:refreshed", "purge_completed_commit"])
@pytest.mark.parametrize("startup_recovery", [False, True])
def test_delete_receipt_preserves_identically_restored_source(tmp_path, stage, startup_recovery):
    from features.agent_mode.report_delete import recover_report_deletes
    _, report = setup(tmp_path)
    save(tmp_path)
    original = report.read_bytes()
    proposal = deletion.source_delete_preview(tmp_path, {"kind": "company", "id": "report-a"})
    operation = uuid4().hex
    with pytest.raises((OSError, RuntimeError)):
        deletion.delete_source(tmp_path, "company", "report-a", token=proposal["token"], operation_id=operation, fault=stage)
    report.write_bytes(original)
    if startup_recovery:
        recover_report_deletes(report.parent)
    result = service.recover(tmp_path, operation)
    assert result["outcome"] == "partial" and result["sourceOutcome"] == "changed"
    assert report.read_bytes() == original
    assert not list(report.parent.glob(".report-delete-*.json"))


def test_research_identity_review_ambiguity_and_scope_replay(tmp_path):
    setup(tmp_path)
    write(tmp_path, "topic-reports/2025-03-03_ai_topic-a.json", {"id": "topic-a", "markdown": "사용자 선택 산업 맥락", "topicPlan": {"candidateTickers": ["ACME"]}})
    write(tmp_path, "investment-review/2025-03-03.json", {"reviewRevision": 1, "date": "2025-03-03", "positionReviews": [{"ticker": "ACME", "summary": "시장 미확인"}]})
    saved = save(tmp_path, selection={"researchId": "topic-a"})
    body = service.read_journal(tmp_path, saved["journalId"])["journal"]
    assert body["inputs"]["research"]["ref"]["identityStatus"] == "unverified"
    assert body["inputs"]["review"]["content"] is None
    assert service.read_case(tmp_path, "US:ACME")["sourceRefs"]["research"]["id"] == "topic-a"
    write(tmp_path, "investment-review/2025-03-03.json", {"reviewRevision": 2, "date": "2025-03-03", "positionReviews": [{"ticker": "ACME", "market": "US", "summary": "정확한 종목"}]})
    assert capture(tmp_path, "US:ACME")["inputs"]["review"]["content"]["positionReviews"][0]["summary"] == "정확한 종목"


def test_byte_limit_exclusion_and_sensitive_body_are_explicit(tmp_path):
    _, report = setup(tmp_path)
    source = json.loads(report.read_bytes()); source["markdown"] = "x" * MAX_BYTES; report.write_bytes(canonical(source))
    proposal = service.preview(tmp_path, request(tmp_path))
    assert proposal["token"] is None and proposal["totalBytes"] > MAX_BYTES
    assert service.preview(tmp_path, request(tmp_path, excludedSlots=["company"]))["canConfirm"]
    source["markdown"] = "C:\\Users\\Private\\notes.txt"; report.write_bytes(canonical(source))
    blocked = service.preview(tmp_path, request(tmp_path))
    assert blocked["blockedSlots"] == ["company"] and not blocked["canConfirm"]
    good = service.preview(tmp_path, request(tmp_path, excludedSlots=["company"]))
    assert good["canConfirm"] and good["journal"]["inputs"]["company"]["content"] is None


def test_exact_agent_scopes_and_restore_in_different_root(tmp_path):
    root = tmp_path / "original"; root.mkdir(); _, report = setup(root)
    saved = save(root, decisionText="당시 생각")
    case = service.read_case(root, "US:ACME")
    scope = {"kind": "investment_case", "id": case["caseId"], "caseRevision": case["caseRevision"], "inputFingerprint": case["inputFingerprint"], "methodVersion": case["methodVersion"]}
    assert "investmentCase" in context(root, scope)
    old = service.read_journal(root, saved["journalId"])
    journal_scope = {"kind": "decision_journal", "id": saved["journalId"], "bodyHash": old["bodyHash"]}
    report.write_bytes(canonical({"id": "report-a", "company": {"ticker": "ACME", "market": "US"}, "markdown": "changed"}))
    assert "dataGaps" in context(root, scope)
    assert "decisionJournal" in context(root, journal_scope)
    restored = tmp_path / "restored"; shutil.copytree(root, restored)
    assert service.read_journal(restored, saved["journalId"])["journal"] == old["journal"]
    save(restored, "purge", targetJournalId=saved["journalId"], purgePersonal=True)
    assert "dataGaps" in context(restored, journal_scope)


def test_http_round_trip_and_error_body_are_bounded(tmp_path):
    app = FastAPI(); app.include_router(create_case_router(tmp_path))
    with LiveHttpClient(app) as client:
        assert client.get("/api/investment-cases/US:ACME").status_code == 200
        proposal = client.post("/api/investment-cases/preview", json={"instrumentId": "US:ACME", "expectedCaseRevision": 0, "action": "create"}).json()
        assert client.post("/api/investment-cases/confirm", json={"token": proposal["token"], "operationId": uuid4().hex}).status_code == 200
        bad = client.post("/api/investment-cases/preview", json={"instrumentId": "../../secret", "expectedCaseRevision": 0, "action": "create"})
        assert bad.status_code == 400 and "secret" not in json.dumps(bad.json())
        assert client.post("/api/investment-cases/confirm", json={"token": "guess", "operationId": uuid4().hex}).status_code == 400


def test_macro_owner_fields_and_fingerprint_are_stable_between_views(tmp_path):
    from features.company_exposure.tests.test_exposure import materials
    from features.company_exposure.extraction import extract
    from features.company_exposure.store import ExposureStore
    from features.macro_state.tests.test_store import snapshot
    from features.macro_state.store import StateStore
    profile = extract({"ticker": "ACME", "market": "US"}, materials())
    ExposureStore(tmp_path).save(profile, materials=materials())
    macro = StateStore(tmp_path / "market-memory.sqlite3").save(snapshot(), reason="fixture")
    one = capture(tmp_path, "US:ACME", at="2026-10-07T08:00:00Z")
    two = capture(tmp_path, "US:ACME", at="2026-10-07T08:00:01Z")
    assert one["inputFingerprint"] == two["inputFingerprint"]
    body = one["inputs"]["macro"]["content"]
    assert body["profile"]["limitations"] == profile["limitations"]
    assert body["profile"]["coverage"] == profile["coverage"]
    assert body["states"][0]["unknownReason"] == macro["unknownReason"]
    assert body["states"][0]["observationSelection"] == macro["observationSelection"]
    assert body["interpretation"]["financialContext"]


def test_pending_scope_excludes_unrelated_cases_and_survives_source_removal(tmp_path):
    _, report = setup(tmp_path)
    proposal = service.preview(tmp_path, request(tmp_path))
    op = uuid4().hex
    with pytest.raises(OSError): service.confirm(tmp_path, proposal["token"], op, fault="staged")
    assert service.read_case(tmp_path, "US:OTHER")["pendingOperations"] == []
    service.recover(tmp_path, op)
    proposal = deletion.source_delete_preview(tmp_path, {"kind": "company", "id": "report-a"})
    op = uuid4().hex
    with pytest.raises(OSError): deletion.delete_source(tmp_path, "company", "report-a", token=proposal["token"], operation_id=op, fault="purge_completed_commit")
    assert not report.exists()
    assert service.read_case(tmp_path, "US:ACME")["pendingOperations"][0]["operationId"] == op
    service.recover(tmp_path, op)


def test_new_review_identity_is_retained_but_legacy_is_never_backfilled(tmp_path):
    from features.investment_review.review_v2 import build_structured_review
    from features.investment_review.schema import normalize_review
    inputs = {"positions": [{"ticker": "BRK.B", "market": "US"}], "thesisAuthorityAvailable": True}
    generated = build_structured_review(inputs, {})
    view = normalize_review({"schemaVersion": 2, "date": "2026-10-01", **generated})
    assert view["positionReviews"][0]["instrumentId"] == "US:BRK.B"
    assert view["positionRoster"][0]["market"] == "US"
    path = write(tmp_path, "investment-review/2026-10-01.json", view)
    assert capture(tmp_path, "US:BRK.B")["inputs"]["review"]["status"] == "preserved"
    assert capture(tmp_path, "US:BRK-B")["inputs"]["review"]["status"] == "unavailable"
    legacy = normalize_review({"schemaVersion": 2, "date": "2026-10-01", "positionReviews": [{"ticker": "BRK-B", "thesisVerdict": "maintained"}]})
    assert "market" not in legacy["positionReviews"][0] and "instrumentId" not in legacy["positionReviews"][0]


@pytest.mark.parametrize("initial_condition", ["", "현금 전환 악화"])
def test_conditions_and_reported_time_remain_original_after_event_and_new_reason(tmp_path, initial_condition):
    from features.thesis_tracking.service import upsert_manual_thesis
    path = tmp_path / "market-memory.sqlite3"
    save(tmp_path, "create")
    missing = save(tmp_path)
    assert service.read_journal(tmp_path, missing["journalId"])["journal"]["inputs"]["reason"]["content"] is None
    first_reason = upsert_manual_thesis({"ticker": "ACME", "coreThesis": "한 줄 이유", "conditionResponse": "written" if initial_condition else "unknown", "falsificationTriggers": [initial_condition] if initial_condition else [], "userStatedAt": "2025-01-02"}, db_path=path)["reasonRevision"]
    first = save(tmp_path, userReportedAt={"precision": "unknown", "value": None})
    before = service.read_journal(tmp_path, first["journalId"])["journal"]
    connection = thesis_store.connect(path)
    try:
        thesis_store.save_thesis_checkpoints(connection, "ACME", [{"id": "cp-1", "item": "현금 전환 악화", "status": "challenged", "lastVerdict": {"verdict": "challenged", "at": "2026-10-07T08:00:00Z", "evidence": []}}])
    finally:
        connection.close()
    upsert_manual_thesis({"ticker": "ACME", "coreThesis": "사건 후 이유 수정", "conditionResponse": "written", "falsificationTriggers": ["이후 확인할 새 조건"], "expectedRevisionId": first_reason["revisionId"]}, db_path=path)
    after = service.read_journal(tmp_path, first["journalId"])["journal"]
    assert after == before
    reason = after["inputs"]["reason"]["content"]
    assert reason["revisionId"] == first_reason["revisionId"]
    assert reason["conditionResponse"] == ("written" if initial_condition else "unknown")
    assert reason["content"]["falsification_triggers"] == ([initial_condition] if initial_condition else [])
    assert reason["fieldPresence"] == first_reason["fieldPresence"]
    assert reason["userStatedAt"] == "2025-01-02" and reason["recordedAt"] != "2025-01-02"
    assert after["userReportedAt"] == {"precision": "unknown", "value": None}
    assert service.read_journal(tmp_path, missing["journalId"])["journal"]["inputs"]["reason"]["content"] is None
    assert service.read_case(tmp_path, "US:ACME")["reasonSummary"]["falsification_triggers"] == ["이후 확인할 새 조건"]


def test_held_portfolio_does_not_infer_owned_lifecycle(tmp_path):
    write(tmp_path, "portfolio.json", {"positions": [{"ticker": "ACME", "market": "US", "quantity": "3"}]})
    original = (tmp_path / "portfolio.json").read_bytes()
    save(tmp_path, "create")
    case = service.read_case(tmp_path, "US:ACME")
    assert case["lifecycle"] == "researching" and case["lifecycleMismatch"] is True
    save(tmp_path, "transition", toStage="archived")
    assert (tmp_path / "portfolio.json").read_bytes() == original
