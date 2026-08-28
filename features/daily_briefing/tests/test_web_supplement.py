"""브리핑 웹 보완(찾기 전용)과 문체 실측을 못박는다.

§6 규칙 9는 다섯 곳(제품 계약·README·프롬프트·API 배선·기본값)에 있었지만 실제 사용
경로(CLI)에는 통로가 없었다 — 저장 브리핑 14건 전부 웹 기여 0건. 여기 테스트는
공백 판정이 건강한 날에 조용한지, 두 경로가 같은 값을 받는지, 조회 실패가 브리핑을
죽이지 않는지를 지킨다.
"""
from __future__ import annotations

import re
from pathlib import Path

from features.daily_briefing.style_check import briefing_style_check
from features.daily_briefing.web_lookup import (
    lookup_briefing,
    market_gaps,
    render_web_lookup,
    web_supplement,
)

ROOT = Path(__file__).resolve().parents[3]

HEALTHY_SNAPSHOT = {
    "ok": True,
    "tickers": {
        "SPY": {"last": 560.0, "oneDayPct": 0.4, "asOfDate": "2026-08-26", "label": "SPY"},
        "QQQ": {"last": 480.0, "oneDayPct": 0.6, "asOfDate": "2026-08-26", "label": "QQQ"},
    },
}
HEALTHY_KR = {
    "ok": True,
    "indices": {
        "KOSPI": {"close": 3100.0, "changePct": -0.5},
        "KOSDAQ": {"close": 826.0, "changePct": 0.1},
    },
    "fx": {"USDKRW": {"close": 1384.0, "changePct": 0.2}},
}


class TestGapDetection:
    def test_a_healthy_day_stays_quiet(self):
        """공백이 없으면 조회도 없다 — 매일 웹을 때리는 장치는 보완이 아니다."""
        assert market_gaps("us", HEALTHY_SNAPSHOT, None, "2026-08-26") == []
        assert market_gaps("kr", HEALTHY_SNAPSHOT, HEALTHY_KR, "2026-08-26") == []

    def test_missing_and_stale_proxies_are_gaps(self):
        assert [g["id"] for g in market_gaps("us", None, None, "2026-08-26")] == ["snapshot_unavailable"]
        stale = {"ok": True, "tickers": {
            "SPY": {"last": 560.0, "asOfDate": "2026-08-10"},
            "QQQ": {"last": 480.0, "asOfDate": "2026-08-10"},
        }}
        assert [g["id"] for g in market_gaps("us", stale, None, "2026-08-26")] == ["us_proxy_missing"]

    def test_kr_gaps_come_from_korea_data_not_the_snapshot(self):
        """KR 지수는 스냅샷 티커에 없다(실측) — 스냅샷 기준으로 재면 매일 오탐이다."""
        broken = {**HEALTHY_KR, "indices": {
            "KOSPI": {"close": None, "changePct": None},
            "KOSDAQ": {"close": 826.0, "changePct": 0.1},
        }, "fx": {}}
        ids = [g["id"] for g in market_gaps("kr", HEALTHY_SNAPSHOT, broken, "2026-08-26")]
        assert ids == ["kr_index_missing:KOSPI", "kr_fx_missing"]

    def test_jp_and_europe_are_structural_gaps(self):
        """이 두 시장 지수는 로컬 수치 피드가 아예 다루지 않는다 — 웹 보완이 §6 규칙 9가
        말하는 '부족한 지수' 바로 그 자리다."""
        assert [g["id"] for g in market_gaps("jp", HEALTHY_SNAPSHOT, None, "2026-08-26")] == ["jp_index_feed_absent"]
        assert [g["id"] for g in market_gaps("europe", HEALTHY_SNAPSHOT, None, "2026-08-26")] == ["europe_index_feed_absent"]


class TestSupplement:
    def test_no_gaps_means_no_lookup_call(self):
        def explode(prompt, context):
            raise AssertionError("공백이 없으면 호출하면 안 된다")

        block, summary = web_supplement(
            "us", "2026-08-26",
            market_snapshot=HEALTHY_SNAPSHOT, korea_market_data=None,
            web_search=True, lookup=explode,
        )
        assert block == "" and summary["gaps"] == []

    def test_web_off_records_gaps_but_never_calls(self):
        block, summary = web_supplement(
            "jp", "2026-08-26",
            market_snapshot=HEALTHY_SNAPSHOT, korea_market_data=None,
            web_search=False, lookup=None,
        )
        assert block == ""
        assert summary == {"webSearch": False, "gaps": ["jp_index_feed_absent"]}

    def test_lookup_failure_does_not_kill_the_briefing(self):
        def broken(prompt, context):
            raise TimeoutError("engine down")

        block, summary = web_supplement(
            "jp", "2026-08-26",
            market_snapshot=HEALTHY_SNAPSHOT, korea_market_data=None,
            web_search=True, lookup=broken,
        )
        assert block == ""
        assert summary["ok"] is False and summary["reason"] == "TimeoutError"

    def test_found_facts_render_with_source_and_boundary(self):
        stub = lambda p, c: (
            '{"facts":[{"item":"닛케이 225","value":"42,100 (+1.2%)","asOf":"2026-08-26",'
            '"source":"Nikkei","url":"https://www.nikkei.com/x"}],"notFound":["TOPIX"]}'
        )
        block, summary = web_supplement(
            "jp", "2026-08-26",
            market_snapshot=HEALTHY_SNAPSHOT, korea_market_data=None,
            web_search=True, lookup=stub,
        )
        assert summary["ok"] is True and len(summary["facts"]) == 1
        assert "42,100" in block and "nikkei.com" in block
        # 경계: 보완이지 대체가 아니다 + 못 찾은 값은 추정 금지
        assert "로컬 기사" in block and "추정하지 말고" in block

    def test_facts_without_a_url_are_dropped(self):
        """출처 없는 수치는 수치가 아니다."""
        stub = lambda p, c: '{"facts":[{"item":"닛케이","value":"42,100","asOf":"2026-08-26","source":"?","url":""}]}'
        row = lookup_briefing("jp", "2026-08-26", market_gaps("jp", HEALTHY_SNAPSHOT, None, "2026-08-26"), stub)
        assert row["ok"] is True and row["facts"] == []
        assert render_web_lookup(row, []) == ""


class TestPathParity:
    """§6 규칙 14 — 확인은 구조가 아니라 값으로 한다."""

    def test_both_paths_resolve_missing_websearch_from_the_setting(self):
        """CLI pack과 API 경로 모두 `None → 설정값` 규칙을 쓴다. 어느 한쪽이 `is True`로
        접으면 화면이 값을 안 보낼 때 그 경로만 조용히 꺼진다(기업분석에서 실측)."""
        pack_source = (ROOT / "features/agent_mode/service.py").read_text(encoding="utf-8")
        api_source = (ROOT / "features/daily_briefing/service.py").read_text(encoding="utf-8")
        rule = "use_web_search_for_briefing() if web_search"
        assert rule in pack_source
        assert "use_web_search_for_briefing() if web_search_override is None" in api_source

    def test_app_briefing_endpoint_never_hard_folds_the_cli_branch(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        assert not re.search(r'"web_search":\s*bool_override\([^)]*webSearch[^)]*\)\s+is\s+True', source)
        # CLI 브리핑 분기가 webSearch를 아예 안 보내던 상태로 돌아가지 않게
        briefing_block = source[source.index('submit_agent_task("briefing"'):][:900]
        assert '"web_search": bool_override(body.get("webSearch"))' in briefing_block

    def test_the_supplement_lives_in_the_shared_assembler(self):
        """블록이 조립기(build_llm_context) 안에 있으면 CLI에서만 빠지는 일이 구조적으로
        불가능하다. 호출부 두 곳으로 흩어지면 기업분석의 8/30 겹침 사고가 재현된다."""
        api_source = (ROOT / "features/daily_briefing/service.py").read_text(encoding="utf-8")
        start = api_source.index("def build_llm_context(")
        end = api_source.index("def ", start + 30)
        assert "web_search" in api_source[start:end]


class TestStyleCheck:
    def test_violations_measured_with_the_common_ruler(self):
        hedgy = "## 시장 흐름\n" + ("지수가 오를 수 있다. " * 40)
        row = briefing_style_check(hedgy)
        assert "hedge_overuse" in row["violations"]
        assert row["topPhrase"] == "수 있다"

    def test_clean_text_passes_and_empty_text_reports_nothing(self):
        assert briefing_style_check("## 시장 흐름\n지수가 1.2% 올랐다.")["violations"] == []
        assert briefing_style_check("") == {}


class TestScopeNameDoesNotExpandTheMarketList:
    """범위 이름으로 시장을 다시 풀면 임의 조합이 네 시장으로 퍼진다(§10)."""

    def test_a_two_market_selection_only_supplements_those_two(self, monkeypatch):
        from features.daily_briefing import service as svc

        seen: list[str] = []

        def spy(scope, date, **kwargs):
            seen.append(scope)
            return "", {"ok": True}

        monkeypatch.setattr(svc, "briefing_web_supplement", spy)
        svc._web_supplement_block(
            "multi", "2026-08-28", {}, None,
            web_search=True, lookup=None, sink={}, markets=["kr", "jp"],
        )
        assert seen == ["kr", "jp"], seen

    def test_without_a_list_it_still_falls_back_to_the_scope_name(self, monkeypatch):
        from features.daily_briefing import service as svc

        seen: list[str] = []
        monkeypatch.setattr(svc, "briefing_web_supplement", lambda scope, date, **kw: (seen.append(scope), ("", {}))[1])
        svc._web_supplement_block(
            "both", "2026-08-28", {}, None, web_search=True, lookup=None, sink={},
        )
        assert seen == ["us", "kr"], seen
