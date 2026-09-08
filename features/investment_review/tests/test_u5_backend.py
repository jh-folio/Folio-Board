"""Focused U.5 plumbing regressions kept separate from root acceptance QA."""
from __future__ import annotations

import json
from types import SimpleNamespace


def test_recovery_reuses_staged_report_selection_version(tmp_path, monkeypatch):
    """Recovery must not reinterpret a staged legacy/U.5 review selection."""
    from features.common import job_json_recovery
    from features.investment_review import review_v2

    staged_path = tmp_path / "review.json"
    staged_path.write_text(json.dumps({"inputBasis": {
        "fingerprint": "expected", "reportSelectionVersion": "u5-v1", "analytics": {},
    }}), encoding="utf-8")
    artifact = SimpleNamespace(
        manifest=SimpleNamespace(expected=SimpleNamespace(type="investment_review", storage="json")),
        staged_path=staged_path,
    )
    bundle = SimpleNamespace(artifacts=[artifact])
    seen = {}

    monkeypatch.setattr(
        "features.common.job_json_codec.read_logical",
        lambda *_args: json.loads(staged_path.read_text(encoding="utf-8")),
    )

    def fake_gather(_root, *, analytics_authority=None, report_selection_version=""):
        seen["selection"] = report_selection_version
        return {"selection": report_selection_version}

    monkeypatch.setattr(review_v2, "gather_inputs", fake_gather)
    monkeypatch.setattr(review_v2, "build_input_basis", lambda inputs: {"fingerprint": "expected"})
    job_json_recovery._validate_investment_review_recovery_authority(tmp_path, bundle, None)
    assert seen["selection"] == "u5-v1"


def test_exact_challenge_keeps_roster_and_counter_under_detail_budget(monkeypatch):
    from pathlib import Path
    from features.agent_mode import consultation_context as context
    from features.investment_review import review_v2

    raw = {"schemaVersion": 2, "sourceSchemaVersion": 2, "date": "2026-09-04", "reviewRevision": 7,
           "counterEvidence": [{"title": "핵심 반증 보존"}],
           "positionReviews": [
               {"ticker": f"SYM{index:02}", "thesisVerdict": "broken",
                "counterEvidence": [{"title": "반증" * 120} for _ in range(4)],
                "canonicalReferences": [{"kind": "company_analysis", "id": f"ref-{index}-{item}",
                                         "title": "관련 제목" * 45, "relatedReason": "관련 설명" * 45} for item in range(8)],
                "dueCheckpoints": [{"id": f"cp-{index}-{item}", "label": "확인 사항" * 40,
                                    "dueAt": "2026-09-01"} for item in range(8)]}
               for index in range(18)
           ]}
    session = {"id": "mock", "scope": {"kind": "investment_review", "id": "2026-09-04", "revision": 7, "intent": "challenge"},
               "messages": [], "memory": {}}
    monkeypatch.setattr(context, "get_session", lambda *_args: session)
    monkeypatch.setattr(review_v2, "load_raw", lambda *_args: raw)
    assembled = context.assemble_consultation_context(Path("unused-readonly"), "mock")
    review = assembled["pack"]["sourceContext"]["investmentReview"]
    assert len(assembled["serialized"]) <= context.MAX_CONTEXT_CHARS
    assert len(review["positionRoster"]) == 18
    assert any(item["title"] == "핵심 반증 보존" for item in review["counterEvidence"])


def test_exact_challenge_protected_fallback_keeps_priority_counter(monkeypatch):
    from pathlib import Path
    from features.agent_mode import consultation_context as context
    from features.investment_review import review_v2

    tickers = [f"SYM{index:03}" + "X" * 18 for index in range(100)]
    raw = {"schemaVersion": 2, "sourceSchemaVersion": 2, "date": "2026-09-04", "reviewRevision": 7,
           "positionRoster": [{"ticker": ticker, "thesisVerdict": "maintained", "thesisPresent": True, "latestReviewPresent": True} for ticker in tickers],
           "coverage": {"totalPositionCount": 100, "rosterIncludedCount": 100, "detailIncludedCount": 24, "omittedDetailCount": 76},
           "positionReviews": [{"ticker": ticker, "name": "N" * 160, "thesisVerdict": "broken", "thesisPresent": True, "latestReviewPresent": True,
               "counterEvidence": [{"title": "LATE_CRITICAL_UNIQUE" if index == 0 else f"pos-counter-{index}"}],
               "canonicalReferences": [{"kind": "company_analysis", "id": "R" * 150 + str(item), "title": "T" * 240, "relatedReason": "Q" * 240} for item in range(8)],
               "dueCheckpoints": [{"id": "C" * 150 + str(item), "label": "L" * 240, "dueAt": "2026-09-01T00:00:00Z"} for item in range(8)]}
               for index, ticker in enumerate(tickers[:24])],
           "counterEvidence": [{"title": f"EARLY_COUNTER_{index}_" + "x" * 210} for index in range(12)],
           "sharedExposures": [{"type": "narrative", "key": f"key{index}", "stateKey": f"key{index}", "label": "E" * 160,
                                "tickers": [f"T{item}" + "X" * 20 for item in range(24)]} for index in range(6)]}
    session = {"id": "mock", "scope": {"kind": "investment_review", "id": "2026-09-04", "revision": 7, "intent": "challenge"},
               "messages": [{"role": "user", "content": "x" * 6000} for _ in range(20)], "memory": {"summary": "m" * 5000}}
    monkeypatch.setattr(context, "get_session", lambda *_args: session)
    monkeypatch.setattr(review_v2, "load_raw", lambda *_args: raw)
    assembled = context.assemble_consultation_context(Path("unused-readonly"), "mock")
    review = assembled["pack"]["sourceContext"]["investmentReview"]
    assert len(assembled["serialized"]) <= context.MAX_CONTEXT_CHARS
    assert len(review["positionRoster"]) == 100
    assert any(item["title"] == "LATE_CRITICAL_UNIQUE" for item in review["counterEvidence"])
    assert assembled["pack"]["sourceContext"]["dataGaps"]


def test_partial_roster_never_turns_cap_omission_into_removal():
    from features.investment_review.review_v2 import compare_previous

    previous = {"sourceSchemaVersion": 2,
                "positionRoster": [{"ticker": "SYM001", "thesisVerdict": "maintained"}] * 100,
                "coverage": {"totalPositionCount": 101, "rosterIncludedCount": 100, "omittedRosterCount": 1},
                "positionReviews": [{"ticker": "SYM101", "thesisVerdict": "broken"}]}
    current = {"positionRoster": [{"ticker": "SYM001", "thesisVerdict": "maintained"}] * 100,
               "coverage": {"totalPositionCount": 101, "rosterIncludedCount": 100, "omittedRosterCount": 1},
               "positionReviews": []}
    changes, uncertainties = compare_previous(current, previous)
    assert not [row for row in changes if row["kind"] == "verdict"]
    assert "previous_verdict_not_comparable" in {row["code"] for row in uncertainties}


def test_u5_keeps_direct_weekly_briefing_without_market_scope(tmp_path):
    from features.investment_review.review_v2 import _used_reports

    folder = tmp_path / "briefings"
    folder.mkdir()
    (folder / "weekly.json").write_text(json.dumps({
        "id": "weekly", "kind": "weekly", "ticker": "NVDA", "title": "주간 NVIDIA 점검",
    }), encoding="utf-8")
    refs = _used_reports(tmp_path, {"NVDA"}, positions=[{"ticker": "NVDA"}])
    assert refs == [{**refs[0], "reportKind": "weekly", "title": "주간 NVIDIA 점검",
                     "relatedReason": "종목 직접 자료", "tickers": ["NVDA"]}]


def test_risk_compare_ignores_unprojected_contribution_metrics():
    from features.investment_review.review_v2 import compare_previous

    backtest = {"id": "run", "methodVersion": "portfolio-backtest-v1", "baseCurrency": "USD", "window": "monthly", "start": "2025", "end": "2026"}
    previous = {"sourceSchemaVersion": 2, "inputBasis": {"analytics": {"backtest": backtest}},
                "portfolioRisks": [{"riskKey": "saved_backtest", "methodVersion": "portfolio-backtest-v1", "status": "available",
                                    "riskContributions": [{"ticker": "NVDA", "weight": .5}]}]}
    current = {"portfolioRisks": [{"riskKey": "saved_backtest", "methodVersion": "portfolio-backtest-v1", "status": "available",
                                    "riskContributions": [{"ticker": "NVDA", "weight": .5, "volatilityShare": .9, "unused": "display"}]}]}
    changes, _ = compare_previous(current, previous, current_basis={"analytics": {"backtest": backtest}})
    assert not [row for row in changes if row["kind"] == "risk"]


def test_rules_summary_distinguishes_missing_theses_from_reviewed_insufficiency():
    from features.investment_review.review_v2 import build_rules_summary

    summary = build_rules_summary({
        "coverage": {"totalPositionCount": 18, "detailIncludedCount": 18},
        "positionRoster": [
            {"ticker": f"SYM{index:02}", "thesisPresent": False,
             "latestReviewPresent": False, "thesisVerdict": "insufficient_evidence"}
            for index in range(18)
        ],
    })
    assert "Thesis 미작성 18개" in summary
    assert "검토 후 근거가 부족" not in summary
    assert "검토 완료" not in summary


def test_rules_summary_marks_partial_readiness_as_unknown_without_inference():
    from features.investment_review.review_v2 import build_rules_summary

    summary = build_rules_summary({
        "coverage": {"totalPositionCount": 5, "detailIncludedCount": 5},
        "_summaryRows": [
            {"ticker": "NEW", "thesisPresent": True, "latestReviewPresent": False,
             "thesisVerdict": "maintained"},
            {"ticker": "THIN", "thesisPresent": True, "latestReviewPresent": True,
             "thesisVerdict": "insufficient_evidence"},
            {"ticker": "NONE", "thesisPresent": False, "latestReviewPresent": False,
             "thesisVerdict": "insufficient_evidence"},
            {"ticker": "UNKNOWN", "thesisPresent": True, "thesisVerdict": "maintained"},
            {"ticker": "RISK", "thesisPresent": True, "latestReviewPresent": True,
             "thesisVerdict": "broken"},
        ],
        "positionRoster": [],
    })
    assert "Thesis 미작성 1개" in summary
    assert "저장된 최신 검토가 없는 Thesis 1개" in summary
    assert "검토 후 근거가 부족한 종목 1개" in summary
    assert "준비 상태를 확인할 수 없는 종목 1개" in summary
    assert "약화 또는 이탈 주의 판정 1개" in summary
    assert "검토 완료" not in summary


def test_rules_summary_empty_portfolio_does_not_claim_a_completed_review():
    from features.investment_review.review_v2 import build_rules_summary, render_v2_markdown

    summary = build_rules_summary({"coverage": {"totalPositionCount": 0, "detailIncludedCount": 0}, "positionRoster": []})
    assert "점검할 대상이 없습니다" in summary
    assert "검토 완료" not in summary
    markdown = render_v2_markdown({"date": "2026-09-04", "summary": summary, "positionReviews": []})
    assert "## 저장 리뷰 요약" in markdown
    assert "오늘의 판단 요약" not in markdown


def test_rules_summary_uses_full_candidate_scope_not_capped_roster():
    from features.investment_review.review_v2 import build_rules_summary

    summary = build_rules_summary({
        "coverage": {"totalPositionCount": 101, "detailIncludedCount": 24},
        "positionRoster": [{"ticker": "EARLY", "thesisPresent": True, "latestReviewPresent": True,
                            "thesisVerdict": "maintained"}],
        "_summaryRows": ([{"ticker": f"SYM{index:03}", "thesisPresent": True,
                            "latestReviewPresent": True, "thesisVerdict": "maintained"} for index in range(100)]
                         + [{"ticker": "LATE", "thesisPresent": True, "latestReviewPresent": True,
                             "thesisVerdict": "broken"}]),
    })
    assert "저장된 보유 101개" in summary
    assert "약화 또는 이탈 주의 판정 1개" in summary
    assert "저장 최소 목록" not in summary
