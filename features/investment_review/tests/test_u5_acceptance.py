"""Root-owned adversarial acceptance, independent of implementation fixtures."""
from __future__ import annotations

import json

import pytest

from features.investment_review import review_v2
from features.investment_review.schema import normalize_review


def test_direct_reports_survive_market_background_and_global_cap(tmp_path):
    holdings = [{"ticker": f"SYM{i:02}", "market": "US"} for i in range(18)]
    (tmp_path / "briefings").mkdir()
    (tmp_path / "company-analysis").mkdir()
    for day in range(1, 10):
        (tmp_path / "briefings" / f"2026-09-{day:02}.us.json").write_text(
            json.dumps({"date": f"2026-09-{day:02}", "marketScope": "us"}), encoding="utf-8")
    for row in holdings:
        (tmp_path / "company-analysis" / f"{row['ticker']}.json").write_text(
            json.dumps({"id": row["ticker"], "ticker": row["ticker"], "title": f"Direct {row['ticker']}"}), encoding="utf-8")
    refs = review_v2._used_reports(tmp_path, {row["ticker"] for row in holdings}, positions=holdings)
    direct = {ref["id"] for ref in refs if ref["kind"] == "company_analysis"}
    assert direct == {row["ticker"] for row in holdings}
    inputs = {"portfolio": {"revision": 1}, "positions": holdings, "reportRefs": refs}
    basis = review_v2.build_input_basis(inputs)
    structured = review_v2.build_structured_review(inputs, basis)
    normalized = normalize_review({"schemaVersion": 2, "inputBasis": basis, **structured})
    for row in normalized["positionReviews"]:
        assert any(ref["kind"] == "company_analysis" and ref["id"] == row["ticker"] for ref in row["canonicalReferences"])
    projected_union = {(ref["kind"], ref["id"]) for row in normalized["positionReviews"] for ref in row["canonicalReferences"]}
    assert projected_union == {(ref["kind"], ref["id"]) for ref in normalized["inputBasis"]["canonicalReports"]}


def test_exact_challenge_keeps_all_18_minimum_rows_and_saved_bytes(tmp_path):
    review_dir = tmp_path / "investment-review"
    review_dir.mkdir()
    tickers = [f"SYM{i:02}" for i in range(18)]
    raw = {"schemaVersion": 2, "sourceSchemaVersion": 2, "date": "2026-09-04", "reviewRevision": 7,
           "positionReviews": [{"ticker": ticker, "thesisVerdict": "broken" if i == 17 else "maintained"} for i, ticker in enumerate(tickers)]}
    path = review_dir / "2026-09-04.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    before = path.read_bytes()
    context = review_v2.challenge_context(tmp_path, review_dir, "2026-09-04", 7)
    assert {row["ticker"] for row in context["investmentReview"]["positionRoster"]} == set(tickers)
    assert context["reuseAsEvidence"] is False
    assert path.read_bytes() == before
    rejected = review_v2.challenge_context(tmp_path, review_dir, "2026-09-04", 6)
    assert rejected["dataGaps"] == [{"code": "review_changed_reopen_challenge"}]
    assert "investmentReview" not in rejected


def test_reason_target_and_structured_change_survive_without_unknown_keys():
    view = normalize_review({"schemaVersion": 2, "inputBasis": {},
        "uncertainties": [{"code": "thesis_missing", "ticker": "NVDA", "secret": "SECRET_CANARY"}],
        "changesSincePrevious": [{"kind": "checkpoint", "key": "cp1", "change": "changed",
            "from": {"status": "open", "direction": "challenging", "dueBy": "2026-09-03", "secret": "SECRET_CANARY"},
            "to": {"status": "challenged", "direction": "challenging", "dueBy": "2026-09-03"}}]})
    assert view["uncertainties"][0]["ticker"] == "NVDA"
    assert view["changesSincePrevious"][0]["from"]["status"] == "open"
    assert view["changesSincePrevious"][0]["to"]["status"] == "challenged"
    assert "SECRET_CANARY" not in json.dumps(view)


def test_typed_checkpoint_verdict_is_not_stringified():
    inputs = {"portfolio": {"revision": 1}, "positions": [{"ticker": "NVDA"}],
        "checkpoints": [{"id": "cp1", "ticker": "NVDA", "item": "Demand", "status": "open",
            "lastVerdict": {"verdict": "challenged", "at": "2026-09-03T00:00:00Z", "secret": "SECRET_CANARY"}}]}
    basis = review_v2.build_input_basis(inputs)
    view = normalize_review({"schemaVersion": 2, "inputBasis": basis, **review_v2.build_structured_review(inputs, basis)})
    assert view["checkpointReviews"][0]["lastVerdict"]["verdict"] == "challenged"
    assert "SECRET_CANARY" not in json.dumps(view)


def test_pre_u5_basis_fingerprint_remains_byte_equivalent():
    # Captured from the pre-U.5 implementation on 2026-09-04, not recomputed
    # from the new implementation as a self-fulfilling expected value.
    inputs = {"portfolio": {"revision": 3, "updatedAt": "2026-09-03T00:00:00Z"},
        "positions": [{"ticker": "NVDA"}], "theses": [], "states": [], "checkpoints": [],
        "reportRefs": [{"kind": "company_analysis", "id": "nvda-old", "revision": 2,
            "asOf": "2026-09-01", "tickers": ["NVDA"], "marketWide": False, "marketScope": ""}],
        "analytics": {"methodVersion": "portfolio-analytics-v1"}, "capturedAt": "2026-09-04T00:00:00Z"}
    assert review_v2.build_input_basis(inputs)["fingerprint"] == "0e2655affd089ff28ba57c62e97500b8db1b07ca094d5cd4c474565fdbfa83ee"


def test_long_conversation_preserves_exact_roster_and_counter_context(tmp_path, monkeypatch):
    from features.agent_mode import consultation_context
    from features.investment_review import service

    folder = tmp_path / "investment-review"
    folder.mkdir()
    roster = [{"ticker": f"SYM{i:02}", "thesisVerdict": "broken" if i == 17 else "maintained"} for i in range(18)]
    (folder / "2026-09-04.json").write_text(json.dumps({
        "schemaVersion": 2, "sourceSchemaVersion": 2, "date": "2026-09-04", "reviewRevision": 7,
        "positionReviews": roster, "counterEvidence": [{"title": "핵심 반증 반드시 보존"}],
    }), encoding="utf-8")
    session = {"id": "isolated-u5", "scope": {"kind": "investment_review", "id": "2026-09-04", "revision": 7, "intent": "challenge"},
        "memory": {"summary": "기존 대화" * 4000},
        "messages": [{"role": "user" if i % 2 else "assistant", "content": "긴 이전 메시지" * 1200} for i in range(20)]}
    monkeypatch.setattr(consultation_context, "get_session", lambda *_: session)
    monkeypatch.setattr(service, "REVIEW_DIR", folder)
    context = consultation_context.assemble_consultation_context(tmp_path, session["id"])
    assert len(context["serialized"]) <= 32000
    payload = json.loads(context["serialized"])
    snapshot = payload["sourceContext"]["investmentReview"]
    assert (snapshot["date"], snapshot["reviewRevision"]) == ("2026-09-04", 7)
    assert {row["ticker"] for row in snapshot["positionRoster"]} == {row["ticker"] for row in roster}
    assert "핵심 반증 반드시 보존" in context["serialized"]
    assert "marketState" not in payload["sourceContext"]


@pytest.mark.parametrize("count", [18, 24, 40, 100, 101])
def test_roster_coverage_is_truthful_and_late_risk_is_not_silent(count):
    holdings = [{"ticker": f"SYM{i:03}"} for i in range(count)]
    risky = holdings[-1]["ticker"]
    inputs = {"portfolio": {"revision": 1}, "positions": holdings,
        "theses": [{"ticker": risky, "latestDelta": {"deltaId": "risk", "verdict": "broken",
            "counterEvidence": [{"title": "Late material counterevidence"}]}}]}
    structured = review_v2.build_structured_review(inputs, review_v2.build_input_basis(inputs))
    view = normalize_review({"schemaVersion": 2, "inputBasis": review_v2.build_input_basis(inputs), **structured})
    coverage = view["coverage"]
    assert coverage["totalPositionCount"] == count
    assert coverage["rosterIncludedCount"] == len(view["positionRoster"])
    assert coverage["omittedRosterCount"] == count - len(view["positionRoster"])
    assert coverage["detailIncludedCount"] == len(view["positionReviews"])
    assert coverage["omittedDetailCount"] == count - len(view["positionReviews"])
    assert len(view["positionRoster"]) == min(count, 100)
    assert len(view["positionReviews"]) <= 24
    assert risky in {row["ticker"] for row in view["positionReviews"]}


def test_overdue_is_separate_unique_snapshot_count_and_review_is_not_resolution(monkeypatch):
    checkpoint = {"id": "shared-cp", "label": "Resolve common premise", "dueAt": "2026-09-03T00:00:00Z"}
    review = {"schemaVersion": 2, "sourceSchemaVersion": 2, "reviewState": "reviewed",
        "generatedAt": "2026-09-04T00:00:00Z", "reviewedAt": "2026-09-04T01:00:00Z",
        "inputBasis": {"fingerprint": "same"},
        "positionReviews": [{"ticker": ticker, "dueCheckpoints": [checkpoint]} for ticker in ["NVDA", "AMD"]]}
    monkeypatch.setattr(review_v2, "_now", lambda: "2026-09-04T02:00:00Z")
    state, freshness, _ = review_v2.effective_freshness(review, {"fingerprint": "same"})
    assert state == "reviewed"
    assert freshness["dueCount"] == 0
    assert freshness["overdueUnresolvedCount"] == 1
    assert freshness["evaluatedAt"] == "2026-09-04T02:00:00Z"
    review["generatedAt"] = "2026-09-02T00:00:00Z"
    review["reviewedAt"] = ""
    state, freshness, _ = review_v2.effective_freshness(review, {"fingerprint": "same"})
    assert state == "due"
    assert freshness["dueCount"] == 2  # Pre-existing E.1 duplicate semantics.
    assert freshness["overdueUnresolvedCount"] == 1


def test_priority_detail_rotation_does_not_fake_position_add_remove():
    holdings = [{"ticker": f"SYM{i:03}"} for i in range(30)]
    inputs = {"portfolio": {"revision": 1}, "positions": holdings,
        "theses": [{"ticker": row["ticker"], "latestDelta": {"deltaId": f"d{i}", "verdict": "maintained"}} for i, row in enumerate(holdings)]}
    basis = review_v2.build_input_basis(inputs)
    old = normalize_review({"schemaVersion": 2, "sourceSchemaVersion": 2, "inputBasis": basis, **review_v2.build_structured_review(inputs, basis)})
    inputs["theses"][-1]["latestDelta"]["verdict"] = "broken"
    current = review_v2.build_structured_review(inputs, review_v2.build_input_basis(inputs))
    changes, _ = review_v2.compare_previous(current, old, current_basis=basis)
    verdicts = [row for row in changes if row["kind"] == "verdict"]
    assert verdicts == [{"kind": "verdict", "key": "SYM029", "change": "changed", "from": "maintained", "to": "broken"}]


def test_job_final_prompt_cannot_add_generic_market_or_screen_report(tmp_path, monkeypatch):
    from features.agent_mode import chat, consultation_store, job_runtime
    from features.investment_review import service

    folder = tmp_path / "investment-review"
    folder.mkdir()
    (folder / "2026-09-04.json").write_text(json.dumps({"schemaVersion": 2, "sourceSchemaVersion": 2,
        "date": "2026-09-04", "reviewRevision": 7,
        "positionReviews": [{"ticker": "NVDA", "thesisVerdict": "broken"}],
        "counterEvidence": [{"title": "Saved exact counterevidence"}]}), encoding="utf-8")
    monkeypatch.setattr(service, "REVIEW_DIR", folder)
    session = consultation_store.create_session(tmp_path, {"scope": {
        "kind": "investment_review", "id": "2026-09-04", "revision": 7, "intent": "challenge"}})
    message = consultation_store.append_user_message(tmp_path, session["id"], "검토해줘", operation_id="u5-root-prompt")["message"]
    seen = []

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Generic market/collection context was queried")

    def fake_engine(question, screen, options, **kwargs):
        prompt = chat.build_chat_prompt(question, screen, options, markdown="WRONG_SCREEN_REPORT_CANARY", conversation=kwargs["conversation"])
        seen.append(prompt)
        return {"reply": "격리된 테스트 응답", "engine": "rules"}

    monkeypatch.setattr(chat, "run_agent_chat", fake_engine)
    monkeypatch.setattr(chat, "_market_state_query", forbidden)
    monkeypatch.setattr(chat, "render_collection_projection", forbidden)
    job_runtime.run_consultation_job(tmp_path, session["id"], message["id"],
        screen_context={"viewId": "analysis", "reportKind": "company_analysis", "reportId": "WRONG_ID", "collectionId": "WRONG_COLLECTION"})
    assert len(seen) == 1  # A swallowed assertion/fallback is not success.
    assert "Saved exact counterevidence" in seen[0]
    assert "WRONG_SCREEN_REPORT_CANARY" not in seen[0]
    assert "WRONG_ID" not in seen[0]
    assert "WRONG_COLLECTION" not in seen[0]


def test_report_identity_does_not_change_just_when_checkpoint_time_passes(tmp_path, monkeypatch):
    from features.portfolio import service as portfolio_service

    holdings = [{"ticker": f"SYM{i:03}", "market": "US"} for i in range(30)]
    folder = tmp_path / "company-analysis"
    folder.mkdir()
    for row in holdings:
        (folder / f"{row['ticker']}.json").write_text(json.dumps({"id": row["ticker"], "ticker": row["ticker"]}), encoding="utf-8")
    monkeypatch.setattr(portfolio_service, "get_portfolio", lambda *_: {"revision": 1, "positions": holdings})
    monkeypatch.setattr(review_v2, "_theses_result", lambda *_: ([], True))
    monkeypatch.setattr(review_v2, "_current_states", lambda *_: [])
    monkeypatch.setattr(review_v2, "_manual_links", lambda *_: {})
    monkeypatch.setattr(review_v2, "_analytics_snapshot", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(review_v2, "_backtest_ref", lambda *_: (None, []))
    monkeypatch.setattr(review_v2, "_tracked_checkpoint_rows", lambda *_: [{"id": "last-cp", "ticker": "SYM029", "item": "Boundary", "status": "open", "dueAt": "2026-09-04T12:00:00Z"}])
    monkeypatch.setattr(review_v2, "_now", lambda: "2026-09-04T11:59:59Z")
    before = review_v2.build_input_basis(review_v2.gather_inputs(tmp_path, report_selection_version="u5-v1"))
    monkeypatch.setattr(review_v2, "_now", lambda: "2026-09-04T12:00:01Z")
    after = review_v2.build_input_basis(review_v2.gather_inputs(tmp_path, report_selection_version="u5-v1"))
    assert before["fingerprint"] == after["fingerprint"]
    legacy = review_v2.gather_inputs(tmp_path, report_selection_version="")
    expected = review_v2._used_reports(tmp_path, {row["ticker"] for row in holdings}, positions=holdings, legacy=True)
    assert legacy["reportRefs"] == expected
