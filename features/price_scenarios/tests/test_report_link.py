from features.company_analysis.generation_context import GenerationInputs, draft_artifact
from features.company_analysis.report_rules import build_rule_report
from features.price_scenarios import report_link

from .test_report import FORBIDDEN, dcf, view_of

LEGACY_CHARTS = {"available": True, "valuation": {"scenarios": [{"label": "기준"}], "currentPrice": 29.0, "status": "ok"},
                 "dcf": {"ok": True, "scenarios": [{"name": "기준"}]}, "valuationBasis": {"reportingCurrency": "USD"},
                 "charts": [{"id": "financials"}, {"id": "dcf", "kind": "dcf", "legacy": True},
                            {"id": "scenario_price", "kind": "scenario_price"}, {"id": "price_return"}]}


def saved(tmp_path):
    view = view_of(tmp_path, dcf=dcf())
    return {"status": "saved", "snapshotId": view["snapshotId"], "view": view}


def test_without_a_snapshot_decision_the_legacy_path_is_untouched():
    materials = {}
    assert report_link.apply_price_snapshot(LEGACY_CHARTS, materials, None) == (LEGACY_CHARTS, {}, "")
    assert materials == {} and report_link.rule_section(None) is None and report_link.rule_section(materials.get("priceSnapshot")) is None


def test_a_saved_snapshot_replaces_the_scenario_table_and_the_second_dcf(tmp_path):
    snapshot, materials = saved(tmp_path), {}
    charts, state, context = report_link.apply_price_snapshot(LEGACY_CHARTS, materials, snapshot)
    ids = [chart["id"] for chart in charts["charts"]]
    assert ids == ["financials", "dcf", "price_return"]                        # x0.7/x1.3 chart is gone, DCF chart kept in place
    dcf_chart = next(chart for chart in charts["charts"] if chart["id"] == "dcf")
    assert "legacy" not in dcf_chart and dcf_chart["priceSnapshotId"] == snapshot["snapshotId"]
    assert charts["priceSnapshotId"] == snapshot["snapshotId"] and charts["priceScenario"]["snapshotId"] == snapshot["snapshotId"]
    assert charts["valuation"]["status"] == "superseded" and charts["valuation"]["currentPrice"] == 30.0 and "scenarios" not in charts["valuation"]
    assert charts["dcf"]["status"] == "superseded" and charts["valuationBasis"] == {"reportingCurrency": "USD"}
    assert state == {"status": "saved", "snapshotId": snapshot["snapshotId"], "asOf": "2025-03-03", "methodVersion": snapshot["view"]["methodVersion"]}
    assert context.startswith("## 가격 시나리오 (이 값을 그대로 쓰세요)") and materials["priceSnapshot"]["snapshotId"] == snapshot["snapshotId"]
    assert LEGACY_CHARTS["charts"][1].get("legacy")  # the caller's object is not modified


def test_an_unavailable_snapshot_keeps_the_report_going_without_an_id(tmp_path):
    materials = {}
    snapshot = {"status": "unavailable", "reason": {"code": "price_stale"}}
    charts, state, context = report_link.apply_price_snapshot(LEGACY_CHARTS, materials, snapshot)
    assert [chart["id"] for chart in charts["charts"]] == ["financials", "price_return"]
    assert "priceSnapshotId" not in charts and state == {"status": "unavailable", "reason": {"code": "price_stale"}}
    assert "가격 시나리오는 계산하지 못했습니다" in context and "추정하거나 다시 계산하지 마세요" in context
    assert materials["priceSnapshot"] == {"status": "unavailable", "reason": {"code": "price_stale"}}
    assert "가격 시나리오는 계산하지 못했습니다" in report_link.rule_section(materials["priceSnapshot"])


def test_the_draft_artifact_names_only_a_stored_snapshot():
    def draft(state):
        inputs = GenerationInputs(company={"name": "X", "ticker": "X"}, docs=[], materials={}, selected=[], charts={}, preflight={},
                                  depthPolicy={}, sourceLedger=[], dataGaps={"gaps": []}, priceSnapshot=state)
        return draft_artifact(inputs, "X", analysis_style="beginner")
    stored = draft({"status": "saved", "snapshotId": "price-abc"})
    assert stored["priceSnapshotId"] == "price-abc" and stored["priceSnapshot"]["status"] == "saved"
    failed = draft({"status": "unavailable", "reason": {"code": "price_stale"}})
    assert "priceSnapshotId" not in failed and failed["priceSnapshot"]["reason"] == {"code": "price_stale"}
    legacy = draft({})
    assert "priceSnapshotId" not in legacy and "priceSnapshot" not in legacy


def analysis(snapshot=None):
    return {"company": {"name": "X", "ticker": "X", "market": "US"}, "secFacts": {"ok": True, "currency": "USD", "rows": []},
            "marketData": {"ok": False}, "marketFinancialData": {"ok": False}, "dartFacts": {"ok": False}, "docs": [], "supportDocs": [],
            "rankedFiling": {"ok": True, "metadata": {"url": "http://x", "form": "10-K"}, "paragraphs": []},
            **({"priceSnapshot": snapshot} if snapshot else {})}


def test_the_rule_report_reads_its_valuation_section_from_the_snapshot(tmp_path):
    snapshot = saved(tmp_path)
    text = build_rule_report(analysis(snapshot), "beginner")
    assert "## 3. 밸류에이션 지표" in text and "### 가정별 연환산 수익률" in text and snapshot["snapshotId"] in text
    assert "### Valuation Metrics" in text and "현재 주가" in text and "| PER |" in text          # today's multiples are kept
    assert "현재가 대비" not in text and "### DCF 기반 내재가치" not in text and "×0.7" not in text   # the x0.7/x1.3 table and the second DCF are not
    section = text.split("## 3. 밸류에이션 지표", 1)[1].split("## 4.", 1)[0]
    for banned in FORBIDDEN:
        assert banned not in section, banned
    missing = build_rule_report(analysis({"status": "unavailable", "reason": {"code": "price_unavailable"}}), "beginner")
    assert "가격 시나리오는 계산하지 못했습니다" in missing and "### Valuation Metrics" in missing and "### DCF 기반 내재가치" not in missing
    legacy = build_rule_report(analysis(), "beginner")
    assert "### Valuation Metrics" in legacy                                   # no decision -> the existing report is unchanged


def test_the_second_valuation_in_the_materials_context_is_replaced_for_snapshot_reports(tmp_path):
    legacy = " | ".join(["| 시나리오", "내재가치/주", "현재가 대비 |"])
    parts = ["앞부분", "", "## 앱 계산 Valuation 및 DCF", "설명", legacy, "", "## 공식 숫자 데이터", "숫자"]
    context = "\n".join(parts)
    for snapshot in (saved(tmp_path), {"status": "unavailable", "reason": {"code": "price_stale"}}):
        materials = {"context": context, "computedValuation": legacy}
        report_link.apply_price_snapshot(LEGACY_CHARTS, materials, snapshot)
        assert "현재가 대비" not in materials["context"] and "내재가치/주" not in materials["context"]
        assert materials["context"].startswith("앞부분") and materials["context"].endswith("## 공식 숫자 데이터\n숫자")
        assert report_link.POINTER in materials["context"] and materials["computedValuation"] == report_link.POINTER
    block = "\n".join(["### Valuation Metrics", "", "| 지표 | 계산값 |", "| PER | 20.0배 |", "", "### DCF 기반 내재가치", legacy])
    with_multiples = "\n".join(["앞부분", "", "## 앱 계산 Valuation 및 DCF", "설명", block, "", "## 공식 숫자 데이터", "숫자"])
    materials = {"context": with_multiples, "computedValuation": block}
    report_link.apply_price_snapshot(LEGACY_CHARTS, materials, saved(tmp_path))
    assert "| PER | 20.0배 |" in materials["context"] and "### DCF 기반 내재가치" not in materials["context"] and "현재가 대비" not in materials["context"]
    assert materials["computedValuation"].startswith("### Valuation Metrics") and materials["computedValuation"].endswith(report_link.POINTER)
    untouched = {"context": context}
    report_link.apply_price_snapshot(LEGACY_CHARTS, untouched, None)
    assert untouched["context"] == context
