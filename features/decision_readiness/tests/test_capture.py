import copy
import json
import sqlite3
import pytest
from fastapi import FastAPI

from features.decision_readiness import DecisionError
from features.decision_readiness.routes import create_decision_router
from features.decision_readiness.service import comparison
from features.price_scenarios.routes import create_price_router
from features.price_scenarios.store import PriceStore
from features.price_scenarios.tests.snapshot_fixtures import make
from features.market_memory.tests.live_http import LiveHttpClient
from .test_rules import ready_snapshot

STAMP = "2025-03-03T00:00:00Z"


def seeded(root, ticker="ACME", currency="USD"):
    store = PriceStore(root / "market-memory.sqlite3")
    snapshot = ready_snapshot()
    snapshot["inputs"]["instrumentId"] = f"US:{ticker}"
    snapshot["inputs"]["identity"]["ticker"] = ticker
    snapshot["inputs"]["price"]["currency"] = currency
    store.save_snapshot(snapshot["inputs"], snapshot["results"])
    return store


def test_pure_comparison_replay_after_new_correction_and_criteria(tmp_path):
    store = seeded(tmp_path)
    store.save_criteria(required_return="10", min_margin_of_safety="20", holding_years=10)
    path = store.path; before = path.read_bytes()
    original = comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=STAMP)
    assert path.read_bytes() == before
    assert original["candidates"][0]["readiness"]["state"] == "ready_for_review"
    store.save_criteria(required_return="90", min_margin_of_safety="20", holding_years=10, expected_revision_id=1)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO price_snapshot_reviews(snapshot_id,reason,metric,fiscal_year,detected_by_snapshot_id,created_at) VALUES(?,?,?,?,?,?)",
                     (original["candidates"][0]["sourceRefs"]["snapshotId"], "restated", "EPS", 2024, "correction", "2025-03-03T01:00:00Z"))
    replay = comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=original["evaluatedAt"], reference_set=original["referenceSet"])
    assert replay == original
    current = comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=STAMP)
    assert current["candidates"][0]["readiness"]["state"] == "stale"
    assert "requiredReturn_unmet" in current["candidates"][0]["readiness"]["blockingReasons"]


def test_mixed_reasons_do_not_change_preparation_and_review_events_are_pinned(tmp_path):
    from features.thesis_tracking import store as ST, reason_history as RH, reason_review as RR
    from features.thesis_tracking.model import Thesis
    store = seeded(tmp_path, "NONE"); seeded(tmp_path, "SHORT"); seeded(tmp_path, "LONG")
    store.save_criteria(required_return="10", min_margin_of_safety="20", holding_years=10)
    with ST.connect(store.path) as conn:
        ST.upsert_thesis(conn, Thesis(ticker="SHORT", core_thesis="한 줄 이유"), edit_source="manual")
        ST.upsert_thesis(conn, Thesis(ticker="LONG", core_thesis="긴 분석의 이유와 반증 조건입니다. " * 80), edit_source="manual")
        conn.commit()
    selected = [{"instrumentId": f"US:{ticker}"} for ticker in ("NONE", "SHORT", "LONG")]
    initial = comparison(tmp_path, selected, at=STAMP)
    assert [row["readiness"]["state"] for row in initial["candidates"]] == ["ready_for_review"] * 3
    assert [row["dimensions"]["reasonState"]["value"]["status"] for row in initial["candidates"]] == ["unwritten", "unreviewed", "unreviewed"]
    with ST.connect(store.path) as conn:
        revision = RH.latest(conn, "SHORT")
        RR.record(conn, "SHORT", revision["revisionId"], source="manual_review", outcome="reviewed", checked_scope=["fixture"])
        conn.commit()
    assert comparison(tmp_path, selected, at=initial["evaluatedAt"], reference_set=initial["referenceSet"]) == initial
    assert comparison(tmp_path, selected, at=STAMP)["candidates"][1]["dimensions"]["reasonState"]["value"]["status"] == "reviewed"


def test_foreign_currency_dates_methods_and_unsupported_market(tmp_path):
    seeded(tmp_path, "USD", "USD"); seeded(tmp_path, "EUR", "EUR")
    out = comparison(tmp_path, [{"instrumentId": "US:USD"}, {"instrumentId": "US:EUR"}, {"instrumentId": "JP:7203.T"}], at=STAMP)
    assert [row["identity"]["instrumentId"] for row in out["candidates"]] == ["US:USD", "US:EUR", "JP:7203.T"]
    pair = out["comparability"][0]["dimensions"]["scenarioReturn"]
    assert pair["status"] == "incomparable" and "currency_different" in pair["reasons"]
    assert out["candidates"][2]["readiness"]["state"] == "unknown"
    assert out["candidates"][2]["dimensions"]["scenarioReturn"]["value"] is None
    for item in out["candidates"]:
        assert "company_report_missing" in item["readiness"]["warnings"]


def test_mutable_report_and_portfolio_changes_refuse_replay(tmp_path):
    seeded(tmp_path)
    directory = tmp_path / "company-analysis"; directory.mkdir()
    path = directory / "report-test.json"
    path.write_text(json.dumps({"company": {"ticker": "ACME", "market": "US"}, "generatedAt": STAMP, "markdown": "### 재무 품질 분석\n현금 전환에 확인할 부분이 있습니다.", "quality": {"score": 99}}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "portfolio.json").write_text(json.dumps({"positions": [{"ticker": "ACME", "market": "US", "quantity": "1"}]}))
    first = comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=STAMP)
    assert "99" not in first["candidates"][0]["dimensions"]["companyQuality"]["value"]
    assert comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=first["evaluatedAt"], reference_set=first["referenceSet"]) == first
    path.write_text(path.read_text(encoding="utf-8").replace("현금", "부채"), encoding="utf-8")
    with pytest.raises(DecisionError, match="comparison_inputs_changed"):
        comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=first["evaluatedAt"], reference_set=first["referenceSet"])
    updated = comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=STAMP)
    (tmp_path / "portfolio.json").write_text('{"positions": []}')
    with pytest.raises(DecisionError, match="comparison_inputs_changed"):
        comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=updated["evaluatedAt"], reference_set=updated["referenceSet"])


def test_absent_refs_remain_absent_and_attempt_support_not_misrepresented(tmp_path):
    request = [{"instrumentId": "US:ETF"}]
    initial = comparison(tmp_path, request, at=STAMP)
    assert list(tmp_path.iterdir()) == []
    path = tmp_path / "price-attempts.json"
    path.write_text(json.dumps({"US:ETF": {"status": "failed", "reason": {"code": "fund_not_supported"}}}))
    assert comparison(tmp_path, request, at=initial["evaluatedAt"], reference_set=initial["referenceSet"]) == initial
    current = comparison(tmp_path, request, at=STAMP)
    assert "unsupported_model" in current["candidates"][0]["readiness"]["blockingReasons"]
    path.write_text('{}')
    with pytest.raises(DecisionError, match="comparison_inputs_changed"):
        comparison(tmp_path, request, at=current["evaluatedAt"], reference_set=current["referenceSet"])


def test_strict_http_and_no_automatic_writes(tmp_path):
    app = FastAPI(); app.include_router(create_price_router(tmp_path)); app.include_router(create_decision_router(tmp_path))
    with LiveHttpClient(app) as client:
        assert client.get('/api/decision-readiness/US:ACME').json()["readiness"]["state"] == "unknown"
        assert client.post('/api/opportunity-comparison', json={"candidates": [{"instrumentId": "US:ACME"}]}).status_code == 200
        assert list(tmp_path.iterdir()) == []
        for body in ({"candidates": []}, {"candidates": [{"instrumentId": "../../secrets"}]}, {"candidates": [{"instrumentId": "US:ACME"}] * 2}, {"candidates": [{"instrumentId": "US:ACME"}], "attributionYears": 2}, {"candidates": [{"instrumentId": "US:ACME"}], "rank": True}):
            assert client.post('/api/opportunity-comparison', json=body).status_code == 422
        assert client.get('/api/decision-readiness/US:ACME', params={"snapshotId": "price-absent"}).status_code == 404
        basis = client.post('/api/portfolio/decision-preview/basis', json={"instrumentId": "US:ACME"}).json()
        assert list(tmp_path.iterdir()) == []
        result = client.post('/api/portfolio/decision-preview', json={"instrumentId": "US:ACME", "basisId": basis["basisId"], "candidateWeightPercent": "20"})
        assert result.json()["before"] is None
        assert list(tmp_path.iterdir()) == []
        assert client.post('/api/portfolio/decision-preview', json={"instrumentId": "US:ACME", "basisId": basis["basisId"], "candidateWeightPercent": 20}).status_code == 422


def test_old_schema_read_does_not_migrate_explicit_write_preserves_rows(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript("CREATE TABLE price_scenario_schema(version INTEGER PRIMARY KEY); INSERT INTO price_scenario_schema VALUES(1); CREATE TABLE valuation_user_criteria(revision_id INTEGER PRIMARY KEY,required_return TEXT,min_margin_of_safety TEXT,holding_years INTEGER,created_at TEXT NOT NULL); INSERT INTO valuation_user_criteria VALUES(1,'6','20',10,'old');")
    before = path.read_bytes(); store = PriceStore(path)
    assert store.criteria()["allowAboveHistoricalRange"] is None and path.read_bytes() == before
    new = store.save_criteria(required_return="7", min_margin_of_safety="20", holding_years=10, expected_revision_id=1, allow_above_historical_range=False)
    assert new["allowAboveHistoricalRange"] is False
    assert store.criteria(1)["createdAt"] == "old" and store.criteria(1)["allowAboveHistoricalRange"] is None
    next_value = store.save_criteria(required_return="7", holding_years=10, expected_revision_id=2)
    assert next_value["allowAboveHistoricalRange"] is False
    assert store.save_criteria(holding_years=10, expected_revision_id=3, allow_above_historical_range=None)["allowAboveHistoricalRange"] is None
    with sqlite3.connect(path) as conn:
        with pytest.raises(sqlite3.IntegrityError): conn.execute("UPDATE valuation_user_criteria SET required_return='0'")
    assert len(list((tmp_path / "backups").glob('*.sqlite3'))) == 1
