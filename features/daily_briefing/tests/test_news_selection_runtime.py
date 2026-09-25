"""Focused contract tests for the opt-in Q5 selection runtime facade."""

from __future__ import annotations

from copy import deepcopy

from features.daily_briefing import news_selection_runtime as runtime


def _article(identifier: str, *, title: str = "Market event", companies=None) -> dict:
    return {
        "id": identifier,
        "market": "us",
        "type": "news",
        "path": f"research-inbox/articles/{identifier}.md",
        "title": title,
        "source": "Reuters",
        "url": f"https://example.test/{identifier}",
        "date": "2026-09-05",
        "summary": "A bounded event summary.",
        "companies": companies or [],
    }


def _old_report() -> dict:
    return {
        "id": "old-us",
        "market": "us",
        "kind": "daily",
        "sessionDate": "2026-09-03",
        "cutoff": "2026-09-04T23:00:00Z",
        "status": "completed",
        "selectionVersion": "q5-s1-v1",
        "markdown": "old briefing",
        "sourceRefs": [{"sourceId": "old-source"}],
    }


def test_pin_reads_before_intake_and_detaches_baseline_copy(monkeypatch):
    stored = [_old_report()]
    monkeypatch.setattr(runtime, "_load_existing_reports", lambda: stored)
    monkeypatch.setenv(runtime.MODE_ENV, "shadow")

    context = runtime.pin_selection_context(
        "2026-09-05", ["us"], "daily", "2026-09-05T23:00:00Z"
    )
    assert context["mode"] == "shadow"
    assert context["baselines"]["us"]["status"] == "baseline_ready"
    assert context["baselines"]["us"]["pin"]["reportId"] == "old-us"

    stored[0]["markdown"] = "mutated after pin"
    # Canonical body/private overlays are intentionally excluded from the
    # serialized baseline copy.
    assert "markdown" not in context["baselines"]["us"]["report"]
    assert "personalOverlay" not in context["baselines"]["us"]["report"]


def test_off_pin_is_zero_report_io(monkeypatch):
    def fail_load():
        raise AssertionError("off pin must not read existing reports")

    monkeypatch.setattr(runtime, "_load_existing_reports", fail_load)
    monkeypatch.setenv(runtime.MODE_ENV, "off")
    context = runtime.pin_selection_context("2026-09-05", ["us"], "daily")
    assert context["baselines"]["us"]["status"] == "not_run"


def test_off_returns_operational_input_without_search_or_assessment(monkeypatch):
    docs = [_article("existing")]

    def fail_search(*args, **kwargs):
        raise AssertionError("off mode must not search")

    monkeypatch.setattr(runtime, "search_documents", fail_search)
    monkeypatch.setenv(runtime.MODE_ENV, "off")
    result = runtime.prepare_selection_candidates(docs, {"documents": []}, "us", "daily", {})
    assert result["operationalCandidates"] == docs
    assert result["selectedCandidateIds"] == ["existing"]
    assert result["assessments"] == []
    assert result["metadata"] == {}


def test_shadow_search_is_four_queries_at_twelve_and_preserves_operational_input(monkeypatch):
    existing = [_article("existing")]
    queried = _article("new", title="New company event", companies=[{"name": "Acme"}])
    calls = []

    def fake_search(index, *, query, limit, scope):
        calls.append((query, limit, scope))
        return [queried]

    monkeypatch.setattr(runtime, "search_documents", fake_search)
    monkeypatch.setenv(runtime.MODE_ENV, "shadow")
    result = runtime.prepare_selection_candidates(
        existing, {"documents": [queried]}, "us", "daily", {"mode": "shadow"}
    )
    # No pinned baseline means no checkpoint question queries; only the two
    # bounded open-exploration queries run.
    assert len(calls) == 2
    assert all(limit == 12 and scope == "news" for _, limit, scope in calls)
    assert result["effectiveMode"] == "shadow"
    assert result["operationalCandidates"] == existing
    assert result["selectedCandidateIds"] == ["existing"]
    assert result["metadata"]["candidateCap"] == 96
    assert result["metadata"]["deepCandidateCap"] == 24
    assert result["metadata"]["excerptChars"] == 1200


def test_weekly_and_non_us_kr_modes_are_strictly_no_extra_work(monkeypatch):
    monkeypatch.setenv(runtime.MODE_ENV, "active")
    monkeypatch.setattr(runtime, "search_documents", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no search")))
    docs = [_article("existing")]
    for market, kind in (("us", "weekly"), ("europe", "daily")):
        result = runtime.prepare_selection_candidates(
            docs, {"documents": []}, market, kind, {"mode": "active"}
        )
        assert result["effectiveMode"] == "off"
        assert result["operationalCandidates"] == docs


def test_active_us_daily_requires_semantic_evaluation_even_without_callback(monkeypatch):
    existing = [_article("existing")]
    queried = _article("new", title="New company event", companies=[{"name": "Acme"}])
    monkeypatch.setattr(runtime, "search_documents", lambda *args, **kwargs: [queried])
    monkeypatch.setenv(runtime.MODE_ENV, "active")
    result = runtime.prepare_selection_candidates(
        existing,
        {"documents": [queried]},
        "us",
        "daily",
        {
            "mode": "active",
            "analysisAsOf": "2026-09-05T23:00:00Z",
            "baselines": {"us": {"status": "baseline_ready"}},
        },
        top_n=2,
    )
    assert result["mode"] == "active"
    assert result["effectiveMode"] == "active"
    assert result["selectedCandidateIds"] == ["existing"]
    assert result["operationalCandidates"] == existing
    assert result["proposalApplied"] is False
    assert result["proposedRanking"][0]["roleDecision"] == "core_flow"
    assert result["proposedRanking"][1]["roleDecision"] == "new_signal"
    assert result["proposedRanking"][1]["semanticAssessment"] == "unavailable"
    assert result["proposedRanking"][1]["semanticAssessmentReason"] == "no_validated_same_input_assessment"


def test_verified_challenge_can_replace_company_slot_but_not_core_market_slot():
    candidates = [_article("core"), _article("old-company", companies=["Old"]), _article("challenge", companies=["New"])]
    assessments = runtime.assess_news_candidates([runtime._safe_assessment_candidate(row) for row in candidates], market="us", kind="daily")
    semantics = {
        row["id"]: {"assessmentStatus": "assessed", "verdict": "new_information", "editorialRoles": ["new_signal"], "judgmentUpdateImportance": "low", "explanationImportance": "low"}
        for row in candidates
    }
    semantics["challenge"].update(editorialRoles=["checkpoint_result", "judgment_change"], judgmentUpdateImportance="high")
    kwargs = dict(top_n=2, baseline_writer_ids=set(), original_ids=["core", "old-company"], baseline_known=True, semantic_required=True, semantic_evaluated=True)
    selected, _, applied = runtime._active_proposal(candidates, assessments, semantic_rows=semantics, **kwargs)
    assert applied and selected == ["core", "challenge"]
    del semantics["core"]
    _, _, applied = runtime._active_proposal(candidates, assessments, semantic_rows=semantics, **kwargs)
    assert not applied


def test_safe_metadata_has_counts_ids_and_reasons_but_no_assessment_text():
    result = {
        "mode": "shadow",
        "effectiveMode": "shadow",
        "selectedCandidateIds": ["candidate-1"],
        "proposalApplied": False,
        "assessments": [{
            "candidateId": "candidate-1",
            "assessmentStatus": "evaluated",
            "roleDecision": "new_signal",
            "excerpt": "private article body should not be projected",
        }],
        "metadata": {"candidateCount": 1},
    }
    context = {"kind": "daily", "baselines": {"us": {"status": "baseline_missing", "reasonCodes": ["baseline_missing"]}}}
    projected = runtime.safe_selection_metadata(result, context, "us")
    assert projected["assessmentStatusCounts"] == {"evaluated": 1}
    assert projected["roleCounts"] == {"new_signal": 1}
    assert projected["selectedCandidateIds"] == ["candidate-1"]
    assert "assessments" not in projected
    assert "private article body" not in str(projected)


def test_active_correction_without_validated_semantics_keeps_original(monkeypatch):
    old = _article("old", title="Old event")
    correction = _article("correction", title="Corrected event")
    correction["correctionOf"] = "old"
    monkeypatch.setattr(runtime, "search_documents", lambda *args, **kwargs: [correction])
    monkeypatch.setenv(runtime.MODE_ENV, "active")
    result = runtime.prepare_selection_candidates(
        [old], {"documents": [correction]}, "us", "daily",
        {"mode": "active", "baselines": {"us": {"status": "baseline_ready"}}}, top_n=2,
    )
    assert result["proposalApplied"] is False
    assert result["selectedCandidateIds"] == ["old"]


def test_search_candidates_are_market_and_cutoff_filtered_and_metadata_is_bounded(monkeypatch):
    bad_market = dict(_article("kr"), market="kr")
    future = dict(_article("future"), date="2026-09-06")
    private = dict(_article("private"), path=r"C:\private\article.md", content="secret full text")
    monkeypatch.setattr(runtime, "search_documents", lambda *args, **kwargs: [bad_market, future, private])
    monkeypatch.setenv(runtime.MODE_ENV, "shadow")
    result = runtime.prepare_selection_candidates(
        [], {"documents": []}, "us", "daily", {"mode": "shadow", "analysisAsOf": "2026-09-05T23:00:00Z"}
    )
    assert result["metadata"]["candidateCount"] == 0
    assert all("C:\\private" not in str(row) for row in result["assessments"])
    assert all(len(str(row.get("excerpt", ""))) <= 1200 for row in result["assessments"])


def test_timestamped_candidate_after_analysis_as_of_is_rejected(monkeypatch):
    before = _article("before")
    before["publishedAt"] = "2026-09-05T22:59:00Z"
    after = _article("after")
    after["publishedAt"] = "2026-09-05T23:01:00Z"
    monkeypatch.setattr(runtime, "search_documents", lambda *args, **kwargs: [before, after])
    result = runtime.prepare_selection_candidates(
        [], {"documents": []}, "us", "daily",
        {
            "mode": "shadow",
            "analysisAsOf": "2026-09-05T23:00:00Z",
            "sourceDates": {"us": ["2026-09-05"]},
        },
    )
    ids = {row["candidateId"] for row in result["assessments"]}
    assert ids == {"before"}


def test_pinned_checkpoint_is_used_without_post_intake_report_read(monkeypatch):
    from features.daily_briefing import service

    def fail_load(*args, **kwargs):
        raise AssertionError("shadow/active must not reload reports")

    monkeypatch.setattr(service, "load_prev_briefing", fail_load)
    result = service.previous_checklists_by_market(
        "2026-09-05", ["us"], kind="daily",
        selection_context={
            "mode": "shadow",
            "baselines": {
                "us": {
                    "status": "baseline_ready",
                    "report": {"checkpointQuestions": ["Check the prior CPI reaction"]},
                }
            },
        },
    )
    assert result == {"us": "Check the prior CPI reaction"}


def test_indexed_kst_timestamp_respects_cutoff():
    doc = _article("kst")
    doc["publishedAtKst"] = "2026-09-05 23:01:00"
    assert not runtime._is_allowed_news(doc, "us", cutoff="2026-09-05T23:00:00+09:00", existing=True)


def test_pinned_writer_checklist_preserves_existing_markdown_selection():
    from features.daily_briefing import service
    markdown = "## 내일 확인할 것\n\n- 실제 확인 사항\n"
    expected = service.extract_prev_checklist(markdown)
    report = runtime._safe_baseline_report({"markdown": markdown, "checkpoints": ["other metadata"]})
    result = service.previous_checklists_by_market("2026-09-05", ["us"], selection_context={
        "mode": "shadow", "baselines": {"us": {"status": "baseline_ready", "report": report}},
    })
    assert result["us"] == expected


def test_active_callback_failure_falls_back_to_existing_selection(monkeypatch):
    existing = [_article("existing")]
    queried = _article("new", title="New event", companies=[{"name": "Acme"}])
    monkeypatch.setenv(runtime.MODE_ENV, "active")
    monkeypatch.setattr(runtime, "search_documents", lambda *args, **kwargs: [queried])
    result = runtime.prepare_selection_candidates(
        existing,
        {"documents": [queried]},
        "us",
        "daily",
        {
            "mode": "active",
            "analysisAsOf": "2026-09-05T23:00:00Z",
            "baselines": {"us": {"status": "baseline_ready", "report": {"checkpoints": [{"id": "cp", "item": "check"}]}}},
        },
        top_n=2,
        semantic_callback=lambda *_args, **_kwargs: {"invalid": True},
        semantic_adapter_limits_verified=True,
        semantic_cache=runtime_news_cache(),
    )
    assert result["proposalApplied"] is False
    assert result["operationalCandidates"] == existing
    assert result["metadata"]["semanticAssessment"] == "not_evaluated"


def runtime_news_cache():
    from features.daily_briefing.news_semantics import BoundedSemanticCache

    return BoundedSemanticCache()
