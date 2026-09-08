"""Focused Q3a checks for the briefing final fact validator."""

from __future__ import annotations

import pytest

from features.daily_briefing.finalize import (
    BriefingFinalizationError,
    SharedRepairBudget,
    _Fact,
    _contains_alias,
    finalize_briefing_candidate,
    validate_briefing_candidate,
)


def _candidate(markdown: str, *, scope: str = "kr", snapshot=None, korea=None, tape=None, sources=None) -> dict:
    return {
        "marketScope": scope,
        "markdown": markdown,
        "marketSnapshot": snapshot or {"ok": False},
        "koreaMarketData": korea or {"ok": False},
        "marketTape": tape or {},
        "sources": sources or [],
        "generationEvidence": {"status": "declared"},
        "claimLedger": {"claims": []},
    }


def test_kospi_precision_sign_and_date_match():
    candidate = _candidate(
        "# Korea Market Briefing\n\nKOSPI 종가는 6,820.02 / +0.46% (2026-08-31)였습니다.",
        korea={
            "ok": True,
            "date": "2026-08-31",
            "indices": {
                "KOSPI": {
                    "label": "KOSPI", "close": 6820.02, "changePct": 0.46,
                    "asOfDate": "2026-08-31", "priceUnit": "points",
                },
            },
        },
    )

    validation = validate_briefing_candidate(candidate)
    assert validation["status"] == "pass"
    assert any(row["kind"] == "changePct" for row in validation["verifiedClaims"])
    assert any(row["kind"] == "value" for row in validation["verifiedClaims"])
    finalized = finalize_briefing_candidate(candidate)
    assert finalized["finalValidation"]["status"] == "pass"


def test_contradictory_format_valid_prose_is_saved_verbatim():
    candidate = _candidate(
        "# US Market Briefing\n\nNVDA는 +1.48% 상승으로 마감했다.",
        scope="us",
        snapshot={
            "ok": True,
            "tickers": {"NVDA": {"label": "NVIDIA", "last": 123.4, "oneDayPct": 1.48, "asOfDate": "2026-08-31"}},
        },
    )
    assert validate_briefing_candidate(candidate)["status"] == "pass"

    bad = dict(candidate, markdown="# US Market Briefing\n\nNVDA는 -1.48% 하락했다.")
    finalized = finalize_briefing_candidate(bad, allow_repair=False)
    assert finalized["markdown"] == bad["markdown"]
    assert finalized["finalValidation"]["contentAssessment"] == "not_assessed"
    assert finalized["finalValidation"]["contradictionCount"] is None
    assert finalized["finalValidation"]["verifiedClaimCount"] is None


def test_operating_metric_percent_is_not_compared_to_stock_return():
    candidate = _candidate(
        "# US Market Briefing\n\nNVDA 매출 성장률 20%, 주가는 +1.48% 상승했다.",
        scope="us",
        snapshot={
            "ok": True,
            "tickers": {"NVDA": {"label": "NVIDIA", "last": 123.4, "oneDayPct": 1.48, "asOfDate": "2026-08-31"}},
        },
    )
    validation = validate_briefing_candidate(candidate)
    assert validation["status"] == "pass"
    assert any(row["factKey"] == "NVDA" and row["value"] == 1.48 for row in validation["verifiedClaims"])
    assert not any(row["kind"] == "value_mismatch" for row in validation["contradictions"])


def test_relative_strength_accepts_less_negative_move_but_rejects_hyundai_case():
    tape = {
        "items": [
            {"symbol": "005380", "label": "현대차", "value": 378000, "changePct": -5.62, "asOf": "2026-09-02", "market": "KR"},
            {"symbol": "KOSPI", "label": "KOSPI", "value": 2500, "changePct": -3.99, "asOf": "2026-09-02", "market": "KR"},
        ]
    }
    valid = _candidate("현대차 -2.00%, KOSPI -3.00% 대비 상대 강세를 보였다.", tape={"items": [
        {"symbol": "005380", "label": "현대차", "changePct": -2.0, "asOf": "2026-09-02", "market": "KR"},
        {"symbol": "KOSPI", "label": "KOSPI", "changePct": -3.0, "asOf": "2026-09-02", "market": "KR"},
    ]})
    assert validate_briefing_candidate(valid)["status"] == "pass"

    bad = _candidate("현대차 -5.62%, KOSPI -3.99% 대비 상대 방어와 강세가 이어졌다.", tape=tape)
    finalized = finalize_briefing_candidate(bad, allow_repair=False)
    assert finalized["markdown"] == bad["markdown"]
    assert finalized["finalValidation"]["contentAssessment"] == "not_assessed"
    assert finalized["finalValidation"]["contradictionCount"] is None


def test_relative_strength_without_known_benchmark_is_unknown_not_rejected():
    candidate = _candidate(
        "현대차 -5.62% 상대 방어를 보였다.",
        tape={"items": [{"symbol": "005380", "label": "현대차", "changePct": -5.62, "asOf": "2026-09-02", "market": "KR"}]},
    )
    validation = validate_briefing_candidate(candidate)
    assert validation["status"] == "warn"
    assert not validation["contradictions"]
    assert any(row.get("kind") == "relative_strength_without_known_benchmark" for row in validation["unknownClaims"])


def test_absolute_strength_still_conflicts_with_a_negative_return():
    candidate = _candidate(
        "현대차 -5.62% strength continues.",
        tape={"items": [{"symbol": "005380", "label": "현대차", "changePct": -5.62, "asOf": "2026-09-02", "market": "KR"}]},
    )
    validation = validate_briefing_candidate(candidate)
    assert validation["status"] == "reject"
    assert any(row["kind"] == "direction_mismatch" for row in validation["contradictions"])


def test_market_aliases_use_boundaries():
    kospi = _Fact(key="KOSPI", label="KOSPI", aliases=("KOSPI",))
    spy = _Fact(key="SPY", label="SPY", aliases=("SPY",))
    assert not _contains_alias("KOSPI200 +1.0%", kospi)
    assert not _contains_alias("SPYword +1.0%", spy)
    assert _contains_alias("KOSPI는 +1.0%", kospi)
    assert _contains_alias("SPY +1.0%", spy)


def test_weekly_uses_weekly_return_not_one_day_return():
    candidate = _candidate(
        "# US Weekly Briefing\n\nNVDA +1.48% rose.",
        scope="us",
        snapshot={
            "ok": True,
            "tickers": {
                "NVDA": {
                    "label": "NVIDIA", "last": 123.4, "oneDayPct": 1.48,
                    "weeklyPct": 5.00, "asOfDate": "2026-09-04",
                },
            },
        },
    )
    validation = validate_briefing_candidate(dict(candidate, kind="weekly", weekEnd="2026-09-04"))
    assert validation["status"] == "reject"
    assert any(row["expected"] == 5.0 for row in validation["contradictions"] if row["kind"] == "value_mismatch")


def test_stale_or_undated_structured_price_is_not_compared_to_current_body():
    stale = _candidate(
        "# US Market Briefing\n\nNVDA +1.48% rose.",
        scope="us",
        snapshot={
            "ok": True,
            "tickers": {"NVDA": {"label": "NVIDIA", "last": 123.4, "oneDayPct": 1.48, "asOfDate": "2026-09-03"}},
        },
    )
    stale["sessionDate"] = "2026-09-04"
    stale_result = validate_briefing_candidate(stale)
    assert not stale_result["verifiedClaims"]
    assert not stale_result["contradictions"]

    undated = _candidate(
        "# US Market Briefing\n\nNVDA +1.48% rose.",
        scope="us",
        snapshot={"ok": True, "tickers": {"NVDA": {"label": "NVIDIA", "last": 123.4, "oneDayPct": 1.48}}},
    )
    undated["sessionDate"] = "2026-09-04"
    undated_result = validate_briefing_candidate(undated)
    assert not undated_result["verifiedClaims"]
    assert not undated_result["contradictions"]


def test_future_historical_and_intraday_numbers_are_not_current_price_claims():
    base = {
        "ok": True,
        "tickers": {"NVDA": {"label": "NVIDIA", "last": 120, "oneDayPct": 1.48, "asOfDate": "2026-08-31"}},
    }
    for text in (
        "NVDA가 상승하면 +10%가 될 수 있다.",
        "2026-08-30 당시 NVDA는 -10.00%였다.",
        "장중 NVDA는 -2.00%까지 밀렸다.",
    ):
        assert validate_briefing_candidate(_candidate(text, scope="us", snapshot=base))["status"] in {"pass", "warn"}


def test_required_korea_facts_do_not_trigger_production_repair():
    candidate = _candidate(
        "# Korea Market Briefing\n\n오늘 한국장 흐름을 정리했다.",
        korea={
            "ok": True,
            "date": "2026-09-04",
            "indices": {
                "KOSPI": {"label": "KOSPI", "close": 6820.02, "changePct": 1.64, "asOfDate": "2026-09-04"},
                "KOSDAQ": {"label": "KOSDAQ", "close": 900.10, "changePct": 2.95, "asOfDate": "2026-09-04"},
            },
            # The production provider can leave investorFlows empty.  Q2's
            # retained writerExcerpt is the authoritative bounded input for
            # these required Sep 4 facts.
            "investorFlows": {},
        },
        sources=[{
            "sourceId": "src_flow",
            "date": "2026-09-04",
            "writerExcerpt": "KOSPI +1.64%, KOSDAQ +2.95%\n외국인 5034억원, 기관 1조6690억원, 6거래일 수급 전환",
        }],
    )
    finalized = finalize_briefing_candidate(candidate)
    assert finalized["markdown"] == candidate["markdown"]
    assert finalized["finalValidation"]["repairApplied"] is False
    assert finalized["finalValidation"]["repairCount"] == 0
    assert finalized["finalValidation"]["contentAssessment"] == "not_assessed"


def test_manifest_declaration_is_not_semantic_verification_and_unsafe_url_blocks():
    source = {"sourceId": "src_a", "title": "Source", "url": "https://example.com/a", "writerExcerpt": "시장 흐름"}
    candidate = _candidate("시장 흐름", sources=[source])
    candidate["generationEvidence"] = {"status": "inferred_candidate_fallback"}
    candidate["claimLedger"] = {"claims": [{"claim": "매출 100%", "supportingSourceIds": ["src_a"]}]}
    result = validate_briefing_candidate(candidate)
    assert result["sourceChecks"]["semanticVerifiedClaimCount"] == 0
    assert result["sourceChecks"]["status"] == "review"

    unsafe = _candidate("시장 흐름", sources=[{"sourceId": "bad", "title": "Bad", "url": "javascript:alert(1)"}])
    with pytest.raises(BriefingFinalizationError):
        finalize_briefing_candidate(unsafe)


def test_manifest_quote_requires_whole_quote_and_final_body_presence():
    source = {"sourceId": "src_a", "title": "Source", "url": "https://example.com/a", "writerExcerpt": "Nvidia fell sharply."}
    overlap = _candidate(
        "# Brief\n\nNvidia rose.",
        scope="us",
        sources=[source],
    )
    overlap["claimLedger"] = {"claims": [{"claim": "Nvidia rose", "supportingSourceIds": ["src_a"]}]}
    assert validate_briefing_candidate(overlap)["sourceChecks"]["semanticVerifiedClaimCount"] == 0

    quoted = _candidate(
        '# Brief\n\n본문: "Nvidia fell".',
        scope="us",
        sources=[source],
    )
    quoted["claimLedger"] = {"claims": [{"claim": '"Nvidia fell"', "supportingSourceIds": ["src_a"]}]}
    assert validate_briefing_candidate(quoted)["sourceChecks"]["semanticVerifiedClaimCount"] == 1

    reference_only = _candidate(
        "# Brief\n\n## Source & Data Notes\n\n- Nvidia fell.",
        scope="us",
        sources=[source],
    )
    reference_only["claimLedger"] = {"claims": [{"claim": '"Nvidia fell"', "supportingSourceIds": ["src_a"]}]}
    assert validate_briefing_candidate(reference_only)["sourceChecks"]["semanticVerifiedClaimCount"] == 0


def test_manifest_section_must_be_in_final_body_whitelist():
    source = {"sourceId": "src_a", "title": "Source", "url": "https://example.com/a", "writerExcerpt": "Nvidia fell sharply."}
    candidate = _candidate("# Brief\n\n## Market Flow\n\nNvidia fell.", scope="us", sources=[source])
    candidate["claimLedger"] = {"claims": [{
        "claim": '"Nvidia fell"', "supportingSourceIds": ["src_a"], "section": "not-a-section",
    }]}
    validation = validate_briefing_candidate(candidate)
    assert "section_outside_whitelist" in validation["sourceChecks"]["errors"]
    assert validation["status"] == "reject"


def test_production_finalization_does_not_spend_repair_budget():
    korea = {"ok": True, "date": "2026-09-04", "indices": {"KOSPI": {"close": 6820.02, "changePct": 1.64, "asOfDate": "2026-09-04"}}}
    budget = SharedRepairBudget()
    first = _candidate("본문", korea=korea)
    first_result = finalize_briefing_candidate(first, repair_budget=budget)
    second_result = finalize_briefing_candidate(_candidate("본문", korea=korea), repair_budget=budget)
    assert first_result["markdown"] == first["markdown"]
    assert second_result["markdown"] == "본문"
    assert first_result["finalValidation"]["repairCount"] == 0
    assert second_result["finalValidation"]["repairCount"] == 0
    assert budget.used == 0
