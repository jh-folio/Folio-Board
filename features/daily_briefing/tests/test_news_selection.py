from features.daily_briefing.news_selection import (
    BASELINE_SELECTOR_VERSION,
    MAX_CANDIDATES,
    assess_news_candidates,
    evaluate_news_selection,
    select_prior_briefing_baseline,
)
from features.common.canonical_report_state import canonical_content_hash


def _report(**overrides):
    row = {
        "id": "brief-old",
        "market": "us",
        "kind": "daily",
        "sessionDate": "2026-09-04",
        "cutoff": "2026-09-04T23:00:00Z",
        "selectionVersion": BASELINE_SELECTOR_VERSION,
        "status": "completed",
        "markdown": "old",
    }
    row.update(overrides)
    return row


def _persisted_report(**overrides):
    """Shape emitted by the current atomic briefing writer."""
    row = {
        "id": "persisted-old",
        "date": "2026-09-04",
        "marketScope": "us",
        "kind": "daily",
        "sessionDate": "2026-09-04",
        "generatedAt": "2026-09-05T07:20:00+09:00",
        "markdown": "# US Market Briefing",
        "generation": {"mode": "agent", "status": "ok_agent_authored"},
        "canonicalRevision": {"number": 3},
    }
    row.update(overrides)
    row["canonicalRevision"] = {
        "number": row["canonicalRevision"].get("number", 3),
        "hash": canonical_content_hash(row),
    }
    return row


def test_baseline_requires_exact_market_kind_and_prior_completed_session():
    reports = [
        _report(id="same-day", sessionDate="2026-09-05"),
        _report(id="weekly", kind="weekly", sessionDate="2026-09-03"),
        _report(id="kr", market="kr", sessionDate="2026-09-03"),
        _report(id="oldest", sessionDate="2026-09-02"),
        _report(id="nearest", sessionDate="2026-09-04"),
    ]
    result = select_prior_briefing_baseline(
        reports,
        market="US",
        kind="daily",
        current_session_date="2026-09-05",
        current_cutoff="2026-09-05T23:00:00Z",
    )
    assert result.status == "baseline_ready"
    assert result.report_id == "nearest"
    assert result.pin["market"] == "us"
    assert result.pin["kind"] == "daily"
    assert result.pin["sessionDate"] == "2026-09-04"
    assert result.pin["contentHash"]


def test_baseline_distinguishes_contaminated_from_missing_and_pins_version():
    contaminated = select_prior_briefing_baseline(
        [_report(cutoff="2026-09-05T00:00:00Z")],
        market="us",
        current_session_date="2026-09-06",
        current_cutoff="2026-09-05T00:00:00Z",
    )
    assert contaminated.status == "baseline_contaminated"
    assert "baseline_contaminated" in contaminated.reason_codes

    missing = select_prior_briefing_baseline(
        [_report(status="failed"), _report(id="no-cutoff", cutoff="")],
        market="us",
        current_session_date="2026-09-06",
        current_cutoff="2026-09-06T00:00:00Z",
    )
    assert missing.status == "baseline_missing"
    assert "baseline_missing" in missing.reason_codes

    source_contaminated = select_prior_briefing_baseline(
        [_report(sourceRefs=[{"publishedAt": "2026-09-06T00:00:00Z"}])],
        market="us",
        current_session_date="2026-09-07",
        current_cutoff="2026-09-05T23:00:00Z",
    )
    assert source_contaminated.status == "baseline_contaminated"


def test_atomic_persisted_report_is_completed_without_selector_version_and_uses_canonical_revision():
    result = select_prior_briefing_baseline(
        [_persisted_report()],
        market="us",
        current_session_date="2026-09-05",
        current_cutoff="2026-09-05T23:00:00Z",
    )
    assert result.status == "baseline_ready"
    assert result.version == "3"
    assert result.pin["canonicalRevision"]["number"] == 3
    assert result.pin["cutoffProvenance"] == "generatedAt"


def test_baseline_rejects_calendar_invalid_session_date():
    result = select_prior_briefing_baseline(
        [_report(sessionDate="2026-02-30")],
        market="us",
        current_session_date="2026-03-01",
        current_cutoff="2026-03-01T23:00:00Z",
    )
    assert result.status == "baseline_missing"


def test_baseline_pin_hash_excludes_personal_and_derived_projection_fields():
    report = _persisted_report()
    changed = dict(report, personalOverlay={"thesis": "private"}, notes="private", changeSummary={"status": "new"})
    result_hash = result_hash_for(report)
    assert result_hash
    assert result_hash == result_hash_for(changed)


def result_hash_for(report):
    from features.daily_briefing.news_selection import immutable_report_hash

    return immutable_report_hash(report)


def test_pre_top_n_dedupe_never_uses_company_or_ticker_and_retains_period_and_correction():
    rows = assess_news_candidates(
        [
            {"id": "a", "market": "us", "sourceId": "wire-1", "ticker": "NVDA", "type": "news"},
            # Same company does not make a duplicate when the source is distinct.
            {"id": "b", "market": "us", "sourceId": "wire-2", "ticker": "NVDA", "type": "news"},
            {"id": "a-copy", "market": "us", "sourceId": "wire-1", "ticker": "NVDA", "type": "news"},
            {"id": "period", "market": "us", "sourceId": "wire-1", "observedPeriod": "Q2", "type": "news"},
            {"id": "correction", "market": "us", "sourceId": "wire-1", "correctionOf": "a", "type": "news"},
        ],
        market="us",
    )
    assert [row["status"] for row in rows] == [
        "assessed", "assessed", "excluded_duplicate", "assessed", "assessed"
    ]
    assert rows[2]["duplicateOf"] == "a"
    assert rows[3]["observedPeriod"] == "Q2"
    assert rows[4]["correction"] is True


def test_candidate_evidence_gate_rejects_reports_generated_notes_and_unknown_role_stays_unknown():
    rows = assess_news_candidates(
        [
            {"id": "report", "market": "us", "sourceId": "r", "sourceType": "report"},
            {"id": "note", "market": "us", "sourceId": "n", "type": "news", "generated_by": "folio", "reuseAsEvidence": False},
            {"id": "article", "market": "us", "sourceId": "a", "type": "news"},
        ],
        market="us",
    )
    assert rows[0]["sourceEvidence"] is False
    assert rows[1]["sourceEvidence"] is False
    assert rows[2]["assessmentStatus"] == "evaluated"
    assert rows[2]["evidenceRole"] == "unknown"


def test_deep_budget_counts_only_unique_eligible_candidates_and_exposes_partial_coverage():
    candidates = [
        {"id": "dup", "market": "us", "sourceId": "dup", "type": "news"},
        *[
            {"id": str(index), "market": "us", "sourceId": str(index), "type": "news"}
            for index in range(24)
        ],
    ]
    result = evaluate_news_selection(candidates, market="us", mode="shadow", deep_limit=2)
    assert sum(row["deepAssessment"] for row in result["assessments"]) == 2
    assert result["coverage"]["status"] == "partial"
    assert result["coverage"]["deepUnassessedCount"] == 23


def test_mode_contract_off_is_zero_work_and_shadow_keeps_operational_selection():
    candidates = [
        {"id": "a", "market": "us", "sourceId": "1", "type": "news"},
        {"id": "b", "market": "us", "sourceId": "2", "type": "news"},
    ]
    off = evaluate_news_selection(candidates, market="us", mode="off", top_n=1)
    assert off["workPerformed"] is False
    assert off["assessments"] == []
    assert off["selectedCandidateIds"] == ["a"]

    shadow = evaluate_news_selection(candidates, market="us", mode="shadow", top_n=1)
    assert shadow["effectiveMode"] == "shadow"
    assert shadow["selectedCandidateIds"] == ["a"]
    assert shadow["operationalSelection"] == ["a"]


def test_active_is_limited_to_us_kr_daily_and_falls_back_without_reselection():
    candidates = [{"id": "a", "market": "jp", "sourceId": "1", "type": "news"}]
    result = evaluate_news_selection(candidates, market="jp", kind="weekly", mode="active")
    assert result["effectiveMode"] == "shadow"
    assert result["fallbackReason"] == "active_scope_unsupported"
    assert result["selectedCandidateIds"] == ["a"]


def test_candidate_cap_is_bounded():
    candidates = [
        {"id": str(index), "market": "us", "sourceId": str(index), "type": "news"}
        for index in range(MAX_CANDIDATES + 7)
    ]
    rows = assess_news_candidates(candidates, market="us", candidate_limit=MAX_CANDIDATES + 7)
    assert len(rows) == MAX_CANDIDATES
