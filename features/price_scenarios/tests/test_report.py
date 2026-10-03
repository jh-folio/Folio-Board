import itertools
import re

from features.price_scenarios import report, service
from features.price_scenarios.store import PriceStore

from .snapshot_fixtures import make

FORBIDDEN = ("매수", "매도", "목표가", "적정가", "비중", "싸다", "비싸다", "고평가", "저평가", "상승여력", "하락여력",
             "확률", "빈도", "원금", "현재가 대비", "×0.7", "×1.3")


def dcf(judgement="eligible"):
    row = lambda name, per_share, growth: {"name": name, "ok": True, "growth": growth, "discount": "0.09", "terminal": "0.025",
                                           "equityValue": "1200000000000", "perShare": per_share, "terminalShare": "0.6"}
    return {"status": "available", "marginOfSafetyJudgment": judgement, "notices": [],
            "result": {"currency": "USD", "scenarios": [row("보수", "70.5", "0.05"), row("기준", "100", "0.09"), row("낙관", "130.25", "0.13")],
                       "discountRate": {"rate": "0.09", "method": "wacc"}, "growth": {"basis": "revenue_cagr"},
                       "fadePath": ["0.09"] * 10, "terminalShare": "0.6", "impliedGrowth": {"status": "solved", "growth": "0.0953"}}}


_COUNTER = itertools.count()


def view_of(tmp_path, **patch):
    """A fresh workspace per call: one fingerprint never stores two different results."""
    root = tmp_path / f"workspace-{next(_COUNTER)}"
    store = PriceStore(root / "market-memory.sqlite3")
    inputs, results = make(results_patch=patch)
    saved = store.save_snapshot(inputs, results)
    return service.snapshot_view(root, saved["snapshotId"])


def test_section_reads_every_number_from_the_snapshot_and_never_uses_forbidden_wording(tmp_path):
    view = view_of(tmp_path, dcf=dcf())
    text = report.render_section(view)
    assert text.startswith("## 가격과 가정별 수익률")
    for needle in ("가정별 연환산 수익률", "과거 10년 중 낮은 편(하위 25%)", "중간값", "높은 편(상위 25%)", "끝날 때 PER", view["snapshotId"],
                   "분할만 반영한 실제 종가", "손실이 나지 않으려면(손익분기)", "내재가치/주", "예측이 아니며"):
        assert needle in text, needle
    base = next(r for r in view["results"]["scenarios"] if r["label"] == "base" and r["horizon"] == 10)
    assert report.pct(base["irr"]) in text and report.multiple(base["exitPE"]) in text
    for banned in FORBIDDEN:
        assert banned not in text, banned
    assert "현재가 대비" not in text and "| 보수 |" in text  # the DCF table has no price-difference column
    assert len(re.findall(r"^\| ", text, re.M)) >= 8


def test_context_block_shares_the_same_wording_and_carries_the_usage_rules(tmp_path):
    view = view_of(tmp_path, dcf=dcf())
    context = report.render_context(view)
    section_body = "\n".join(report.lines(view))
    assert section_body in context and context.startswith("## 가격 시나리오 (이 값을 그대로 쓰세요)")
    assert "다시 계산하거나" in context and "추정하지 말고" in context
    # the usage rules name what is forbidden, so the scan applies to the numeric part only
    for banned in FORBIDDEN:
        assert banned not in section_body, banned


def test_unavailable_blocks_state_the_reason_instead_of_numbers(tmp_path):
    view = view_of(tmp_path, dcf={"status": "unavailable", "reason": {"code": "dcf_not_computable"}})
    text = report.render_section(view)
    assert "현금흐름 할인(DCF) 계산은 하지 않았습니다 — 현금흐름 할인 계산에 필요한 입력이 부족해" in text
    limited = view_of(tmp_path, support={"status": "limited", "reasons": [{"code": "adr_ratio_unverified"}], "notices": []})
    assert "ADR 비율을 공시에서 확인하지 못해" in report.render_section(limited) and "연환산" not in report.render_section(limited).split("\n", 3)[3]
    fallback = report.render_section(view_of(tmp_path, dcf=dcf("unknown")))
    assert "안전마진 판정에는 쓰지 않습니다" in fallback


def test_notices_and_decomposition_sentences_appear_when_they_apply(tmp_path):
    view = view_of(tmp_path, dcf=dcf(), support={"status": "supported", "reasons": [], "notices": ["share_classes_same_eps", "preferred_shares_exist"]})
    text = report.render_section(view)
    assert "같은 주당이익을 공시하는 여러 주식 종류" in text and "우선주가 있으며" in text
    view["results"]["decomposition"]["notes"] = [{"code": "margin_majority"}, {"code": "share_reduction_significant"}]
    both = report.render_section(view)
    assert "절반 이상이 마진 개선에서 왔습니다" in both and "주식 수 감소(자사주 매입 등)" in both


def test_chart_payload_is_read_from_the_snapshot_and_has_no_personal_layer(tmp_path):
    view = view_of(tmp_path, dcf=dcf())
    chart = report.dcf_chart(view)
    assert chart["id"] == "dcf" and chart["kind"] == "dcf" and chart["priceSnapshotId"] == view["snapshotId"]
    assert [row["name"] for row in chart["scenarios"]] == ["보수", "기준", "낙관"] and chart["impliedGrowth"] == 0.0953
    assert chart["currentPrice"] == 30.0 and chart["currency"] == "USD"
    assert report.dcf_chart(view_of(tmp_path, dcf={"status": "unavailable", "reason": {"code": "x"}})) is None
    payload = report.scenario_payload(view)
    assert payload["snapshotId"] == view["snapshotId"] and "values" not in payload["ranges"]["growth"]
    assert not {"verdict", "criteria", "myAssumptions"} & payload.keys()
