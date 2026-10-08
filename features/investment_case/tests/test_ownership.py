import importlib
import json
import sqlite3
from uuid import uuid4

import pytest

from features.investment_case import CaseError
from features.investment_case import service, ownership, deletion
from features.investment_case.paths import canonical, database, journal_path
from features.investment_case.tests.test_records import setup, save, request, write
from features.thesis_tracking import store as thesis_store
from features.thesis_tracking.model import Thesis


def review(root, **fields):
    return save(root, kind="ownership_review", ownershipReview=fields)


def saved(root, operation):
    return service.read_journal(root, operation["journalId"], current=False)["journal"]


def clock(monkeypatch, stamp):
    monkeypatch.setattr(service, "now", lambda: stamp)
    monkeypatch.setattr(importlib.import_module("features.investment_case.capture"), "now", lambda: stamp)


def test_initial_comparison_and_preview_do_not_write_or_infer_missing_reason(tmp_path):
    view = ownership.view(tmp_path, "US:ACME")
    assert view["original"]["reason"] == "original_not_recorded"
    assert view["comparison"]["reason"] == {"before": None, "after": None, "revisionChanged": False}
    assert view["issues"] == [] and list(tmp_path.iterdir()) == []
    save(tmp_path, "create")
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    service.preview(tmp_path, request(tmp_path, kind="ownership_review", ownershipReview={"completed": True, "checkedScope": ["company"], "conclusion": "defer"}))
    ownership.view(tmp_path, "US:ACME")
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = review(tmp_path, completed=True, checkedScope=["company"], conclusion="defer")
    data = saved(tmp_path, result)["ownershipReview"]
    assert data["resolution"] == "unresolved" and data["reviewedAt"] and data["originalJournalId"] is None
    assert not (tmp_path / "portfolio.json").exists()


@pytest.mark.parametrize("reason", ["", "한 줄", "개인적으로 익숙한 회사", "검증할 가정과 불확실성 " * 300])
def test_reason_length_is_not_judgment_quality_and_no_owner_write(tmp_path, reason):
    price, _ = setup(tmp_path)
    with thesis_store.connect(price.path) as conn:
        thesis_store.upsert_thesis(conn, Thesis(ticker="ACME", core_thesis=reason), edit_source="manual")
        conn.commit()
    baseline = save(tmp_path)
    with database(tmp_path) as conn:
        old = dict(conn.execute("SELECT * FROM thesis WHERE ticker='ACME'").fetchone())
    outcome = review(tmp_path, completed=True, checkedScope=["reason"], conclusion="defer", evidence="missing")
    result = ownership.historical(tmp_path, outcome["journalId"])
    assert result["original"]["id"] == baseline["journalId"]
    assert result["review"]["conclusion"] == "defer"
    assert result["comparison"]["reason"]["before"]["content"]["core_thesis"] == reason
    with database(tmp_path) as conn:
        assert dict(conn.execute("SELECT * FROM thesis WHERE ticker='ACME'").fetchone()) == old
        assert conn.execute("SELECT COUNT(*) FROM reason_review_event").fetchone()[0] == 0


def test_replay_uses_review_time_inputs_after_same_id_report_replacement(tmp_path):
    _, path = setup(tmp_path)
    baseline = save(tmp_path)
    write(tmp_path, str(path.relative_to(tmp_path)), {"id": "report-a", "company": {"ticker": "ACME", "market": "US"}, "markdown": "V2"})
    result = review(tmp_path, companyView="사업 전제 확인", priceView="가격과 별개", conclusion="maintain", evidence="partial")
    old = ownership.historical(tmp_path, result["journalId"])
    company = next(row for row in old["comparison"]["business"] if row["slot"] == "company")
    assert company["before"]["content"]["markdown"] == "보고서 V1"
    assert company["after"]["content"]["markdown"] == "V2"
    write(tmp_path, str(path.relative_to(tmp_path)), {"id": "report-a", "company": {"ticker": "ACME", "market": "US"}, "markdown": "V3"})
    assert ownership.historical(tmp_path, result["journalId"]) == old
    assert old["original"]["id"] == baseline["journalId"]


def test_continuation_keeps_condition_from_intermediate_reason_revision(tmp_path):
    price, _ = setup(tmp_path)
    original = save(tmp_path)
    with thesis_store.connect(price.path) as conn:
        thesis_store.upsert_thesis(conn, Thesis(ticker="ACME", core_thesis="이유 R2", falsification_triggers=["중간 조건 R2"]), edit_source="manual")
        conn.commit()
    option = next(row for row in ownership.view(tmp_path, "US:ACME")["conditionOptions"] if row["origin"] == "current")
    first = review(tmp_path, condition={k: v for k, v in option.items() if k != "text"}, conclusion="defer", nextCheck="다음 실적")
    with thesis_store.connect(price.path) as conn:
        thesis_store.upsert_thesis(conn, Thesis(ticker="ACME", core_thesis="이유 R3", falsification_triggers=["현재 조건 R3"]), edit_source="manual")
        conn.commit()
    second = review(tmp_path, previousReviewJournalId=first["journalId"], condition={"origin": "previous"}, conclusion="new_reason", evidence="partial")
    data = saved(tmp_path, second)["ownershipReview"]
    assert data["rootReviewJournalId"] == first["journalId"] != second["journalId"]
    assert data["condition"]["anchorJournalId"] == first["journalId"]
    assert data["originalJournalId"] == original["journalId"]
    current = ownership.view(tmp_path, "US:ACME")
    assert len(current["issues"]) == 1 and len(current["timeline"]) == 2
    assert current["issues"][0]["conditionView"]["text"] == "중간 조건 R2"
    with pytest.raises(CaseError, match="ownership_review_changed"):
        review(tmp_path, previousReviewJournalId=first["journalId"], condition={"origin": "previous"})


def test_completed_deferral_rescheduling_keeps_old_due_and_exception_expiry(tmp_path, monkeypatch):
    setup(tmp_path); save(tmp_path)
    clock(monkeypatch, "2026-10-01T01:00:00Z")
    first = review(tmp_path, conclusion="defer", completed=True, checkedScope=["reason"], nextCheckAt="2026-10-03")
    clock(monkeypatch, "2026-10-05T01:00:00Z")
    second = review(tmp_path, previousReviewJournalId=first["journalId"], condition={"origin": "previous"}, conclusion="exception", completed=True,
                    checkedScope=["company", "reason"], nextCheckAt="2026-10-20", exceptionEndAt="2026-10-04")
    view = ownership.view(tmp_path, "US:ACME")
    issue = view["issues"][0]
    assert issue["due"]["schedule"] == "scheduled" and issue["due"]["overdueUnresolved"] and issue["due"]["exceptionExpired"]
    assert issue["review"]["firstSeenAt"] == "2026-10-01T01:00:00Z"
    assert issue["review"]["latestReviewedAt"] == "2026-10-05T01:00:00Z"
    assert issue["due"]["earliestUnresolvedDueAt"] == "2026-10-03"
    resolved = review(tmp_path, previousReviewJournalId=second["journalId"], condition={"origin": "previous"}, conclusion="maintain", evidence="sufficient", resolution="resolved")
    view = ownership.historical(tmp_path, resolved["journalId"])
    assert not view["issues"][0]["due"]["overdueUnresolved"]
    assert view["timeline"][1]["due"]["earliestUnresolvedDueAt"] == "2026-10-03"


@pytest.mark.parametrize("fields,code", [
    ({"completed": True}, "ownership_scope_required"),
    ({"resolution": "resolved", "conclusion": "defer", "evidence": "sufficient"}, "unresolved_ownership_review"),
    ({"resolution": "resolved", "conclusion": "maintain", "evidence": "stale"}, "unresolved_ownership_review"),
    ({"observation": {"eventAt": "2026-10-01T10:00:00"}}, "invalid_ownership_time"),
    ({"conclusion": "sell"}, "invalid_ownership_choice"),
    ({"observation": {"sourceRefs": [{"url": "javascript:alert(1)"}]}}, "invalid_ownership_refs"),
    ({"condition": {"origin": "current", "reasonRevisionId": "invented", "field": "falsification_triggers", "index": 0}}, "ownership_condition_changed"),
])
def test_invalid_review_refuses_before_write(tmp_path, fields, code):
    setup(tmp_path)
    revision = service.read_case(tmp_path, "US:ACME")["caseRevision"]
    with pytest.raises(CaseError, match=code):
        review(tmp_path, **fields)
    assert service.read_case(tmp_path, "US:ACME")["caseRevision"] == revision


def test_preview_rechecks_baseline_and_current_revision(tmp_path):
    setup(tmp_path); initial = save(tmp_path)
    preview = service.preview(tmp_path, request(tmp_path, kind="ownership_review", ownershipReview={}))
    save(tmp_path, "purge", targetJournalId=initial["journalId"], purgeSlots=["company"])
    with pytest.raises(CaseError, match="inputs_changed"):
        service.confirm(tmp_path, preview["token"], uuid4().hex)


def test_source_purge_changes_comparison_without_reconstructing_baseline(tmp_path):
    setup(tmp_path); original = save(tmp_path)
    result = review(tmp_path, interpretation="개인 해석", observation={"text": "개인이 연결한 관찰", "eventAt": "2026-10-01"})
    before = ownership.historical(tmp_path, result["journalId"])
    token = deletion.source_delete_preview(tmp_path, {"kind": "company", "id": "report-a"})
    deletion.delete_source(tmp_path, "company", "report-a", token=token["token"], operation_id=uuid4().hex)
    after = ownership.historical(tmp_path, result["journalId"])
    assert after["originalHashChanged"] and before["original"]["id"] == after["original"]["id"] == original["journalId"]
    company = next(row for row in after["comparison"]["business"] if row["slot"] == "company")
    assert company["before"]["status"] == company["after"]["status"] == "purged"
    assert after["comparison"]["reason"]["before"]["content"]["core_thesis"] == "이유 A"
    save(tmp_path, "purge", targetJournalId=result["journalId"], purgePersonal=True)
    text = journal_path(tmp_path, result["journalId"]).read_text(encoding="utf-8")
    assert "개인 해석" not in text and "개인이 연결한 관찰" not in text
    assert ownership.historical(tmp_path, result["journalId"])["review"]["purgedAt"]


@pytest.mark.parametrize("fault", ["staged", "published_file", "database_commit", "committed"])
def test_review_recovery_is_fixed_point_in_time_and_idempotent(tmp_path, monkeypatch, fault):
    setup(tmp_path); save(tmp_path)
    clock(monkeypatch, "2026-10-01T01:00:00Z")
    preview = service.preview(tmp_path, request(tmp_path, kind="ownership_review", ownershipReview={"completed": True, "checkedScope": ["company"], "conclusion": "defer"}))
    operation_id = uuid4().hex
    with pytest.raises(OSError):
        service.confirm(tmp_path, preview["token"], operation_id, fault=fault)
    clock(monkeypatch, "2026-10-02T01:00:00Z")
    result = service.recover(tmp_path, operation_id)
    assert service.confirm(tmp_path, preview["token"], operation_id) == result
    body = saved(tmp_path, result)
    assert body["recordedAt"] == body["ownershipReview"]["reviewedAt"] == "2026-10-01T01:00:00Z"
    assert len(ownership.view(tmp_path, "US:ACME")["issues"]) == 1


def test_postmortem_while_owned_does_not_archive_or_use_future_input(tmp_path):
    setup(tmp_path); save(tmp_path, "transition", toStage="owned")
    result = save(tmp_path, kind="postmortem", ownershipReview={"conclusion": "undecided", "postmortemAssessment": "external_change", "expectedPath": "정책 지속", "observedPath": "정책 변화"})
    assert service.read_case(tmp_path, "US:ACME")["lifecycle"] == "owned"
    historical = ownership.historical(tmp_path, result["journalId"])
    assert historical["review"]["postmortemAssessment"] == "external_change"
    write(tmp_path, "company-analysis/report-a.json", {"id": "report-a", "company": {"ticker": "ACME", "market": "US"}, "markdown": "미래 자료"})
    assert ownership.historical(tmp_path, result["journalId"]) == historical


def test_missing_baseline_and_offline_current_still_allow_historical_reader(tmp_path, monkeypatch):
    setup(tmp_path); original = save(tmp_path); result = review(tmp_path)
    journal_path(tmp_path, original["journalId"]).unlink()
    monkeypatch.setattr(ownership, "capture", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")))
    out = ownership.historical(tmp_path, result["journalId"])
    assert out["original"]["reason"] == "journal_file_missing"
    assert out["comparison"]["reason"]["before"] is None
    assert out["comparison"]["reason"]["after"]["content"]["core_thesis"] == "이유 A"


def test_numeric_comparison_requires_period_unit_definition_and_method(tmp_path):
    from features.price_scenarios.tests.snapshot_fixtures import make
    from features.investment_case.ownership_comparison import quantitative
    from copy import deepcopy
    inputs, results = make(extra_inputs={"history": {"rows": []}})
    inputs["history"] = {"rows": [{"metric": "Revenue", "value": "100", "unit": "USD", "period": {"start": "2025-01-01", "end": "2025-12-31"}}]}
    a = {"inputs": {"price": {"status": "preserved", "content": {"snapshot": {"inputs": inputs, "results": results}}}}}
    b = deepcopy(a); b["inputs"]["price"]["content"]["snapshot"]["inputs"]["history"]["rows"][0]["value"] = "120"
    out = quantitative(a, b)
    assert out["annual"][0]["difference"] == "20"
    assert out["annual"][0]["meaning"] == "same_period_observation_revision"
    assert out["userExpectation"]["status"] == out["companyGuidance"]["status"] == "unavailable"
    b["inputs"]["price"]["content"]["snapshot"]["inputs"]["history"]["rows"][0]["unit"] = "KRW"
    assert quantitative(a, b)["annual"][0]["difference"] is None
    b["inputs"]["price"]["content"]["snapshot"]["inputs"]["methodVersion"] = "future"
    assert all(row["difference"] is None for row in quantitative(a, b)["scenarios"])


def test_missing_latest_review_cannot_branch_from_older_entry(tmp_path):
    setup(tmp_path); save(tmp_path)
    first = review(tmp_path, conclusion="defer")
    latest = review(tmp_path, previousReviewJournalId=first["journalId"], condition={"origin": "previous"})
    journal_path(tmp_path, latest["journalId"]).unlink()
    view = ownership.view(tmp_path, "US:ACME")
    assert len(view["issues"]) == 1 and view["issues"][0]["id"] == latest["journalId"]
    assert view["issues"][0]["status"] == "unavailable"
    with pytest.raises(CaseError, match="ownership_review_changed"):
        review(tmp_path, previousReviewJournalId=first["journalId"], condition={"origin": "previous"})


@pytest.mark.parametrize("resolution,code", [("resolved", "ownership_condition_unavailable"), ("unresolved", "ownership_review_changed")])
def test_condition_anchor_loss_after_preview_refuses_confirmation(tmp_path, resolution, code):
    price, _ = setup(tmp_path); save(tmp_path)
    with thesis_store.connect(price.path) as conn:
        thesis_store.upsert_thesis(conn, Thesis(ticker="ACME", core_thesis="R2", falsification_triggers=["R2 condition"]), edit_source="manual")
        conn.commit()
    condition = next(row for row in ownership.view(tmp_path, "US:ACME")["conditionOptions"] if row["origin"] == "current")
    first = review(tmp_path, condition={key: value for key, value in condition.items() if key != "text"})
    second = review(tmp_path, previousReviewJournalId=first["journalId"], condition={"origin": "previous"})
    proposal = service.preview(tmp_path, request(tmp_path, kind="ownership_review", ownershipReview={"previousReviewJournalId": second["journalId"], "condition": {"origin": "previous"}, "conclusion": "maintain", "evidence": "sufficient", "resolution": resolution}))
    journal_path(tmp_path, first["journalId"]).unlink()
    with pytest.raises(CaseError, match=code):
        service.confirm(tmp_path, proposal["token"], uuid4().hex)


def test_numeric_definition_statement_basis_and_new_period_gaps():
    from copy import deepcopy
    from features.price_scenarios.tests.snapshot_fixtures import make
    from features.investment_case.ownership_comparison import quantitative
    inputs, results = make()
    inputs["history"]["basis"] = "CFS"
    for row in inputs["history"]["rows"]:
        row["concept"] = "original-" + row["metric"]
        row["unit"] = "USD/shares" if row["metric"] == "EPS Diluted" else "USD"
    a = {"inputs": {"price": {"status": "preserved", "content": {"snapshot": {"inputs": inputs, "results": results}}}}}
    b = deepcopy(a)
    for row in b["inputs"]["price"]["content"]["snapshot"]["inputs"]["history"]["rows"]:
        if row["metric"] == "Net Income": row["value"] = str(float(row["value"]) * 1.5)
    comparable = quantitative(a, b)
    assert all(row["difference"] is not None for row in comparable["annual"] if row["metric"] == "Net Margin")
    for changed in ("statement", "Net Income", "Revenue"):
        c = deepcopy(b); history = c["inputs"]["price"]["content"]["snapshot"]["inputs"]["history"]
        if changed == "statement": history["basis"] = "OFS"
        else:
            for row in history["rows"]:
                if row["metric"] == changed: row["concept"] = "different-definition"
        output = quantitative(a, c)
        assert all(row["difference"] is None for row in output["annual"] if row["metric"] == "Net Margin")
        assert all(row["difference"] is None for row in output["scenarios"])
    c = deepcopy(a)
    for row in c["inputs"]["price"]["content"]["snapshot"]["inputs"]["history"]["rows"]:
        row["period"] = {"start": "2098-01-01", "end": "2098-12-31"}
    assert all(row["difference"] is None for row in quantitative(a, c)["annual"])


def test_portfolio_refs_survive_save_review_and_detect_deleted_original(tmp_path, monkeypatch):
    from copy import deepcopy
    from features.investment_review import review_v2
    from features.investment_review.tests.test_review_v2 import _inputs
    from features.investment_review.schema import normalize_review
    setup(tmp_path); original = save(tmp_path)
    inputs = _inputs()
    for key in ("positions",):
        inputs[key] = [{"ticker": "ACME", "market": "US", "instrumentId": "US:ACME", "name": "ACME"}]
    inputs["portfolio"]["positions"] = deepcopy(inputs["positions"])
    monkeypatch.setattr(review_v2, "gather_inputs", lambda *_args, **_kwargs: deepcopy(inputs))
    target = tmp_path / "investment-review"
    candidate = review_v2.build_candidate(tmp_path, target, "2026-10-01")
    refs = candidate["inputBasis"]["originalDecisions"]
    assert refs[0]["journalId"] == original["journalId"] and refs[0]["instrumentId"] == "US:ACME"
    assert normalize_review(candidate)["inputBasis"]["originalDecisions"] == refs
    outcome = review_v2.finalize_and_commit(tmp_path, target, candidate)
    checked = review_v2.mark_reviewed(tmp_path, target, "2026-10-01", outcome["reviewRevision"])
    assert checked["inputBasis"]["originalDecisions"] == refs
    legacy = review_v2.attach_macro_lineage(deepcopy(inputs), tmp_path, {})
    assert "originalDecisions" not in legacy
    save(tmp_path, "purge", targetJournalId=original["journalId"], purgePersonal=True)
    with pytest.raises(review_v2.ReviewRevisionConflict, match="investment_review_stale"):
        review_v2.mark_reviewed(tmp_path, target, "2026-10-01", checked["reviewRevision"])
    staged = review_v2.prepare_commit_candidate(tmp_path, target, {**candidate, "baseReviewRevision": checked["reviewRevision"]})
    assert staged["reviewState"] == "stale"
    assert staged["inputBasis"]["originalDecisions"] == refs


def test_completed_scope_distinguishes_unchanged_inputs_and_later_corrections(tmp_path):
    setup(tmp_path); save(tmp_path)
    write(tmp_path, "company-analysis/report-a.json", {"id": "report-a", "company": {"ticker": "ACME", "market": "US"}, "markdown": "V2"})
    completed = review(tmp_path, completed=True, checkedScope=["company", "reason"], conclusion="maintain", evidence="sufficient", resolution="resolved")
    initial = ownership.view(tmp_path, "US:ACME")
    original_difference = next(row for row in initial["comparison"]["business"] if row["slot"] == "company")
    assert original_difference["status"] == "changed_input"
    changes = initial["issues"][0]["sinceReviewed"]
    assert changes["journalId"] == completed["journalId"] and changes["changedSlots"] == []
    assert changes["unchangedSlots"] == ["company", "reason"] and changes["gapSlots"] == ["delta", "research"]
    historical = ownership.historical(tmp_path, completed["journalId"])
    write(tmp_path, "company-analysis/report-a.json", {"id": "report-a", "company": {"ticker": "ACME", "market": "US"}, "markdown": "V3 correction"})
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    latest = ownership.view(tmp_path, "US:ACME")
    issue = latest["issues"][0]
    assert issue["sinceReviewed"]["changedSlots"] == ["company"]
    assert issue["review"]["resolution"] == "resolved" and issue["review"]["conclusion"] == "maintain"
    assert issue["review"]["reviewedAt"] == initial["issues"][0]["review"]["reviewedAt"]
    assert ownership.historical(tmp_path, completed["journalId"]) == historical
    assert {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_incomplete_followup_preserves_last_completed_scope_and_purge_leaves_gap(tmp_path):
    setup(tmp_path); save(tmp_path)
    completed = review(tmp_path, completed=True, checkedScope=["company"])
    followup = review(tmp_path, previousReviewJournalId=completed["journalId"], condition={"origin": "previous"}, checkedScope=["price"])
    changes = ownership.view(tmp_path, "US:ACME")["issues"][0]["sinceReviewed"]
    assert changes["journalId"] == completed["journalId"] and changes["checkedScope"] == ["company"]
    save(tmp_path, "purge", targetJournalId=completed["journalId"], purgePersonal=True)
    issue = ownership.view(tmp_path, "US:ACME")["issues"][0]
    assert issue["id"] == followup["journalId"] and issue["sinceReviewed"]["status"] == "unavailable"


@pytest.mark.parametrize("price_value,changed_reason,conclusion", [("15", False, "maintain"), ("60", True, "withdraw")])
def test_price_and_company_judgment_are_independent(tmp_path, price_value, changed_reason, conclusion):
    from features.price_scenarios.tests.snapshot_fixtures import make, PRICE
    price, _ = setup(tmp_path); original = save(tmp_path)
    old = saved(tmp_path, original)
    inputs, results = make(price={**PRICE, "value": price_value})
    price.save_snapshot(inputs, results)
    if changed_reason:
        with thesis_store.connect(price.path) as conn:
            thesis_store.upsert_thesis(conn, Thesis(ticker="ACME", core_thesis="사업 전제를 철회한 이유"), edit_source="manual")
            conn.commit()
    outcome = review(tmp_path, conclusion=conclusion, companyView="사업에 대한 내 판단", priceView="사업과 다른 가격의 변화")
    view = ownership.historical(tmp_path, outcome["journalId"])
    assert view["comparison"]["reason"]["revisionChanged"] is changed_reason
    assert view["comparison"]["price"][0]["status"] == "changed_input"
    assert view["review"]["conclusion"] == conclusion and view["review"]["priceView"] == "사업과 다른 가격의 변화"
    assert saved(tmp_path, original) == old


def test_price_review_ignores_view_time_but_detects_criteria_change(tmp_path, monkeypatch):
    clock(monkeypatch, "2026-10-01T00:00:00Z")
    price, _ = setup(tmp_path); save(tmp_path)
    completed = review(tmp_path, completed=True, checkedScope=["price"], conclusion="maintain", evidence="sufficient")
    initial = ownership.view(tmp_path, "US:ACME")
    assert initial["issues"][0]["sinceReviewed"]["changedSlots"] == []
    clock(monkeypatch, "2026-10-02T00:00:00Z")
    later = ownership.view(tmp_path, "US:ACME")
    assert later["issues"][0]["sinceReviewed"]["changedSlots"] == []
    assert later["issues"][0]["sinceReviewed"]["unchangedSlots"] == ["price", "readiness"]
    assert all(row["status"] == "unchanged_input" for row in later["comparison"]["price"])
    price.save_criteria(required_return="25", holding_years=10, expected_revision_id=1)
    changed = ownership.view(tmp_path, "US:ACME")
    assert changed["issues"][0]["sinceReviewed"]["changedSlots"] == ["price", "readiness"]
    assert changed["issues"][0]["review"]["reviewedAt"] == saved(tmp_path, completed)["ownershipReview"]["reviewedAt"]


def test_macro_review_ignores_view_time_but_detects_source_correction(tmp_path, monkeypatch):
    from features.company_exposure.tests.test_exposure import materials
    from features.company_exposure.extraction import extract
    from features.company_exposure.store import ExposureStore
    from features.macro_state.tests.test_store import snapshot
    from features.macro_state.store import StateStore

    clock(monkeypatch, "2026-10-07T08:00:00Z")
    setup(tmp_path)
    profile = extract({"ticker": "ACME", "market": "US"}, materials())
    ExposureStore(tmp_path).save(profile, materials=materials())
    store = StateStore(tmp_path / "market-memory.sqlite3")
    store.save(snapshot(), reason="fixture")
    original = save(tmp_path)
    completed = review(tmp_path, completed=True, checkedScope=["macro"], conclusion="maintain", evidence="sufficient")
    historical = ownership.historical(tmp_path, completed["journalId"])

    clock(monkeypatch, "2026-10-07T08:00:01Z")
    later = ownership.view(tmp_path, "US:ACME")
    row = later["comparison"]["macro"][0]
    assert row["before"]["content"] != row["after"]["content"]
    assert row["status"] == "unchanged_input"
    assert later["issues"][0]["sinceReviewed"]["unchangedSlots"] == ["macro"]
    assert later["issues"][0]["sinceReviewed"]["changedSlots"] == []

    store.save(snapshot("2"), reason="source_revision")
    changed = ownership.view(tmp_path, "US:ACME")
    assert changed["issues"][0]["sinceReviewed"]["changedSlots"] == ["macro"]
    assert changed["issues"][0]["review"] == later["issues"][0]["review"]
    assert ownership.historical(tmp_path, completed["journalId"]) == historical
    assert changed["original"]["id"] == original["journalId"]
