"""두 생성 경로가 같은 계약을 받는다.

기업분석에는 생성 경로가 둘이고(API `analyze_company`, CLI `prepare_company_analysis_pack`),
계약을 API 경로에만 붙였더니 CLI로 만든 보고서에는 하나도 적용되지 않았다. 사용자는
CLI를 쓰고 있었고, 그 사실은 보고서를 재보고 나서야 드러났다.

CLAUDE.md는 이 함정을 브리핑 절에서 이미 네 번 경고했다. 경고를 다섯 번째 적는 대신
**두 경로가 같은 조립기를 쓰는지 여기서 못박는다.**
"""
from __future__ import annotations

import os
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.agent_mode import service as agent_service
from features.company_analysis import generation_context as gen_ctx
from features.company_analysis import generation_service
from features.company_analysis import service as company_service
from features.company_analysis.style import REQUIRED_SECTION_HEADINGS

_CONTRACT_BLOCKS = ("분량 (섹션별 하한)", "이 보고서가 반드시 담아야 할 것")


@pytest.mark.parametrize("style", ["beginner", "advanced"])
@pytest.mark.parametrize("web_search", [False, True])
def test_cli_entry_points_deliver_shared_focus_once_with_style_and_context(style, web_search):
    """실제 로더부터 CLI 경계까지 검사하되 외부 호출·저장은 대체한다."""
    focus = company_service.ANALYSIS_FOCUS_PROMPT_PATH.read_text(encoding="utf-8")
    cfg = {"enabled": True, "provider": "codex", "model": "test-model", "effort": "high"}
    with ExitStack() as stack:
        for patcher in (*_stubbed(), patch.object(agent_service.A, "write_pack", return_value=Path("pack.json")),
                        patch.object(gen_ctx.company_web, "lookup_company", return_value={})):
            stack.enter_context(patcher)
        pack, _ = agent_service.prepare_company_analysis_pack("HWM", analysis_style=style, web_search=web_search)
    with (
        patch.object(company_service, "selected_cli_config", return_value=cfg),
        patch.object(company_service, "request_cli_text", return_value=(_draft(), "test-response", {})) as request,
    ):
        result, status = company_service.generate_llm_company_analysis(
            "HWM", [], materials=_MATERIALS, context=pack["context"],
            analysis_style=style, llm_override=True, web_search_override=web_search,
        )
    assert result is not None and status.startswith("ok_")
    request.assert_called_once_with(cfg, pack["prompt"], pack["context"], web_search=web_search, include_usage=True, facts_sink={}, result_sink={})
    assert pack["prompt"].count(focus) == 1
    assert company_service.read_analysis_prompt(style) in pack["prompt"]
    assert pack["outputContract"]["requiredSections"] == list(REQUIRED_SECTION_HEADINGS)

_MATERIALS = {
    "context": "로컬 자료 컨텍스트",
    "selectedDocs": [
        {"id": "doc-1", "title": "HWM 분기 실적", "source": "Reuters",
         "date": "2026-08-01", "url": "https://example.com/hwm", "path": "research-inbox/rss/hwm.md"},
    ],
    "secFacts": {"ok": True},
    "rankedFiling": {"ok": True, "paragraphs": ["a"]},
    "company": {"name": "Howmet", "ticker": "HWM"},
    "counts": {},
}


def _stubbed(charts=None):
    """조립기의 의존을 갈아끼운다. 두 경로가 같은 이음매를 쓴다."""
    return (
        patch.object(gen_ctx, "load_index", return_value=[]),
        patch.object(gen_ctx, "search_documents", return_value=[]),
        patch.object(gen_ctx, "infer_requested_company", return_value=_MATERIALS["company"]),
        patch.object(gen_ctx, "build_company_analysis_materials", return_value=_MATERIALS),
        patch.object(gen_ctx, "build_company_analysis_charts", return_value=charts or {"available": False, "charts": []}),
    )


def _draft() -> str:
    return "\n\n".join(f"## {name}\n\n본문입니다." for name in REQUIRED_SECTION_HEADINGS)


def test_both_paths_send_the_same_contract_blocks():
    seen: list[str] = []

    def llm(*_args, **kwargs):
        seen.append(str(kwargs.get("context") or ""))
        return ({"markdown": _draft(), "usedDocs": [], "webSearch": False}, "ok")

    with ExitStack() as stack:
        for patcher in (*_stubbed(), patch.object(agent_service.A, "write_pack", side_effect=lambda pack: Path("pack.json"))):
            stack.enter_context(patcher)
        generation_service.analyze_company("HWM", runtime={
            "generate_llm_company_analysis": llm,
            "use_web_search_for_analysis": lambda: False,
        })
        pack, _path = agent_service.prepare_company_analysis_pack("HWM", analysis_style="advanced")

    api_context, cli_context = seen[0], pack["context"]
    for block in _CONTRACT_BLOCKS:
        assert block in api_context, f"API 경로에 {block} 없음"
        assert block in cli_context, f"CLI 경로에 {block} 없음"


def test_both_paths_gather_material_the_same_way():
    # CLI는 사용자가 친 문자열 하나로 검색했다. 실측으로 NVDA 문서 겹침이 8/30이었고
    # CLI 상위 3건에 엔비디아 기사가 하나도 없었다.
    calls: list[dict] = []

    def spy_search(_index, **kwargs):
        calls.append(kwargs)
        return []

    with (
        patch.object(gen_ctx, "load_index", return_value=[]),
        patch.object(gen_ctx, "search_documents", side_effect=spy_search),
        patch.object(gen_ctx, "infer_requested_company", return_value={"name": "NVIDIA CORP", "ticker": "NVDA"}),
        patch.object(gen_ctx, "build_company_analysis_materials", return_value=_MATERIALS),
        patch.object(gen_ctx, "build_company_analysis_charts", return_value={"available": False, "charts": []}),
        patch.object(agent_service.A, "write_pack", side_effect=lambda pack: Path("pack.json")),
    ):
        agent_service.prepare_company_analysis_pack("NVDA")

    # 회사를 해석한 뒤 그 회사의 **표기별로** 검색한다. 원문 하나로 끝내지 않는다.
    queries = [str(row.get("query") or "") for row in calls]
    assert len(queries) > 2, f"표기별 검색이 돌지 않았다: {queries}"
    assert "NVIDIA CORP" in queries


def test_both_paths_persist_the_contract_fields():
    def llm(*_args, **_kwargs):
        return ({"markdown": _draft(), "usedDocs": [], "webSearch": False}, "ok")

    with ExitStack() as stack:
        for patcher in (*_stubbed(), patch.object(agent_service.A, "write_pack", side_effect=lambda pack: Path("pack.json"))):
            stack.enter_context(patcher)
        api_report = generation_service.analyze_company("HWM", runtime={
            "generate_llm_company_analysis": llm,
            "use_web_search_for_analysis": lambda: False,
        })
        pack, _path = agent_service.prepare_company_analysis_pack("HWM")
        cli_report = agent_service.write_company_analysis_from_markdown(pack, _draft(), persist=False)

    for report, label in ((api_report, "API"), (cli_report, "CLI")):
        assert report.get("depthPolicy"), f"{label}: depthPolicy 없음"
        assert report.get("sourceLedger") is not None, f"{label}: sourceLedger 없음"
        assert report.get("contractValidation"), f"{label}: contractValidation 없음"


def test_both_paths_keep_web_lookup_citations_in_sources():
    """§3.2 — 웹 조회로 인용한 자료가 sourceLedger에만 남고 reader가 표시하는 `sources`에서
    빠졌다. `draft_artifact`는 넣지만 API 경로의 `sources` 오버라이드가 3번째 인자를
    빠뜨려 다시 뺐다. CLI는 draftArtifact를 그대로 써 원래 정상이다."""
    web_row = {
        "status": "ok",
        "facts": [{"statement": "2026년 2분기 가이던스 상향", "url": "https://investor.hwm.example/q2"}],
        "quotes": [],
    }

    def llm(*_args, **_kwargs):
        return ({"markdown": _draft(), "usedDocs": [], "webSearch": True}, "ok")

    with ExitStack() as stack:
        for patcher in (
            *_stubbed(),
            patch.object(gen_ctx.company_web, "lookup_company", return_value=web_row),
            patch.object(agent_service.A, "write_pack", side_effect=lambda pack: Path("pack.json")),
        ):
            stack.enter_context(patcher)
        api_report = generation_service.analyze_company("HWM", runtime={
            "generate_llm_company_analysis": llm,
            "use_web_search_for_analysis": lambda: True,
        })
        pack, _path = agent_service.prepare_company_analysis_pack("HWM", web_search=True)
        cli_report = agent_service.write_company_analysis_from_markdown(pack, _draft(), persist=False)

    for report, label in ((api_report, "API"), (cli_report, "CLI")):
        source_urls = {str(s.get("url") or "") for s in report.get("sources") or []}
        ledger_urls = {str(s.get("url") or "") for s in report.get("sourceLedger") or []}
        assert "https://investor.hwm.example/q2" in ledger_urls, f"{label}: sourceLedger에서 빠졌다"
        assert "https://investor.hwm.example/q2" in source_urls, f"{label}: sources(리더 표시)에서 빠졌다"


def test_the_cli_output_contract_lists_every_required_section():
    # 손으로 여섯 개만 적어 두면 나머지 셋은 빠져도 아무도 모른다.
    with ExitStack() as stack:
        for patcher in (*_stubbed(), patch.object(agent_service.A, "write_pack", side_effect=lambda pack: Path("pack.json"))):
            stack.enter_context(patcher)
        pack, _path = agent_service.prepare_company_analysis_pack("HWM")
    assert pack["outputContract"]["requiredSections"] == list(REQUIRED_SECTION_HEADINGS)


def test_the_cli_retry_uses_the_same_section_check():
    # 브리지의 재시도 분기가 계약과 같은 판정을 쓰는지. 다른 판정을 쓰면 재시도가
    # 엉뚱한 때에 돌거나 필요한 때에 안 돈다.
    from features.agent_mode import bridge
    from features.company_analysis.report_contract import missing_sections

    assert bridge.company_missing_sections is missing_sections
    broken = "\n\n".join(f"## {name}\n\n본문" for name in REQUIRED_SECTION_HEADINGS[:5])
    assert bridge.company_missing_sections(broken)
    assert bridge.company_missing_sections(_draft()) == []


def test_both_paths_carry_the_price_return_chart_values():
    """화면 차트의 주가 수익률이 두 경로의 본문 입력에 같은 값으로 들어간다 (계획 §12 E)."""
    charts = {"available": True, "charts": [{
        "kind": "price_return", "labels": ["1개월", "3개월"], "asOf": "2026-09-24",
        "series": {"HWM": [-13.64, -18.86], "SPY": [1.57, 4.17]},
    }]}
    seen: list[str] = []

    def llm(*_args, **kwargs):
        seen.append(str(kwargs.get("context") or ""))
        return ({"markdown": _draft(), "usedDocs": [], "webSearch": False}, "ok")

    with ExitStack() as stack:
        for patcher in (*_stubbed(charts), patch.object(agent_service.A, "write_pack", side_effect=lambda pack: Path("pack.json"))):
            stack.enter_context(patcher)
        generation_service.analyze_company("HWM", runtime={
            "generate_llm_company_analysis": llm,
            "use_web_search_for_analysis": lambda: False,
        })
        pack, _path = agent_service.prepare_company_analysis_pack("HWM", analysis_style="beginner")

    for context in (seen[0], pack["context"]):
        assert "| HWM | -13.6% | -18.9% |" in context
        assert "2026-09-24 종가" in context
