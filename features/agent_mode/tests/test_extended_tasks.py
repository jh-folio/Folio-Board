from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from features.agent_mode import service
from features.agent_mode import chat
from features.market_memory.snapshot import save_market_state_snapshot


def test_topic_pack_dispatch_preserves_custom_tickers_and_deep_research():
    captured = {}

    def fake_prepare(topic_key, **kwargs):
        captured["topic_key"] = topic_key
        captured.update(kwargs)
        return {"taskType": "topic_report"}, Path("pack.json")

    with patch.object(service, "prepare_topic_report_pack", side_effect=fake_prepare):
        service.prepare_pack(
            "topic_report",
            topic_key="custom",
            custom_tickers={"NVDA": "NVIDIA"},
            deep_research=True,
        )

    assert captured["custom_tickers"] == {"NVDA": "NVIDIA"}
    assert captured["deep_research"] is True


def test_market_memory_agent_writeback_uses_existing_normalizer():
    pack = {
        "artifactId": "2099-12-31",
        "internal": {"date": "2099-12-31", "usedDocs": [{"title": "Source"}]},
    }
    normalized = {"title": "Narrative", "summary": "Summary", "sources": [{"title": "Source"}]}
    with (
        patch.object(service, "normalize_llm_memory_entry", return_value=(normalized, "")),
        patch.object(service, "upsert_memory", side_effect=lambda _path, entry: entry),
    ):
        result = service.write_market_memory_from_json(pack, {"entries": [{"title": "Narrative"}]})
    assert result["status"] == "ok_agent_authored"
    assert result["saved"][0]["sourceKind"] == "agent"
    assert result["saved"][0]["generation"]["mode"] == "agent"


def test_market_state_snapshot_agent_writeback_saves_current_snapshot():
    with TemporaryDirectory() as tmp:
        original_db = service.MARKET_MEMORY_DB_PATH
        service.MARKET_MEMORY_DB_PATH = Path(tmp) / "market-memory.sqlite3"
        try:
            pack = {
                "artifactId": "2099-12-31",
                "internal": {"sourceRefs": [{"id": "rss:1", "title": "AI demand", "source": "Reuters"}]},
            }
            result = service.write_market_state_snapshot_from_json(pack, {
                "headline": "AI 공급망이 시장의 중심축",
                "oneLineSummary": "AI 반도체와 전력 병목이 위험선호를 설명한다.",
                "marketRegime": "selective_growth",
                "actionPosture": "추격보다 확인된 수혜와 반대 근거를 함께 점검",
                "keyDrivers": [{"title": "AI 반도체 공급망", "summary": "HBM 수요가 유지된다.", "sourceRefs": ["rss:1"]}],
                "watchItems": ["HBM 출하 가이던스"],
                "counterEvidence": ["금리 상승은 밸류에이션 상단을 제한한다."],
                "sourceRefs": [{"id": "rss:1", "title": "AI demand", "source": "Reuters"}],
                "confidence": 0.82,
            })
            assert result["status"] == "ok_agent_authored"
            assert result["snapshot"]["headline"] == "AI 공급망이 시장의 중심축"
            assert result["generation"]["mode"] == "agent"
        finally:
            service.MARKET_MEMORY_DB_PATH = original_db


def test_agent_chat_prompt_includes_market_memory_context():
    with TemporaryDirectory() as tmp:
        original_db = chat.MARKET_MEMORY_DB_PATH
        original_index = chat.RESEARCH_INDEX_PATH
        chat.MARKET_MEMORY_DB_PATH = Path(tmp) / "market-memory.sqlite3"
        chat.RESEARCH_INDEX_PATH = Path(tmp) / "research-index.sqlite3"
        try:
            save_market_state_snapshot(chat.MARKET_MEMORY_DB_PATH, {
                "headline": "AI 공급망이 시장의 중심축",
                "oneLineSummary": "AI 반도체와 전력 병목이 위험선호를 설명한다.",
                "marketRegime": "selective_growth",
                "actionPosture": "추격보다 확인된 수혜와 반대 근거를 함께 점검",
                "keyDrivers": [{"title": "AI 반도체 공급망", "summary": "HBM 수요가 유지된다.", "sourceRefs": ["rss:1"]}],
                "watchItems": ["HBM 출하 가이던스"],
                "counterEvidence": ["금리 상승은 밸류에이션 상단을 제한한다."],
                "sourceRefs": [{"id": "rss:1", "title": "AI demand", "source": "Reuters"}],
                "confidence": 0.82,
                "inputWatermarks": {"GLOBAL": None, "US": None, "KR": None},
            })
            prompt = chat.build_chat_prompt("현재 시장을 설명해줘", {"surface": "agent_home"}, {"effort": "medium"})
            assert "## Market State Reference" in prompt
            assert "status: current" in prompt
            assert "- asOf:" in prompt
            assert "reason: current_injected" in prompt
            assert "evidenceRole: context_only" in prompt
        finally:
            chat.MARKET_MEMORY_DB_PATH = original_db
            chat.RESEARCH_INDEX_PATH = original_index


def test_company_analysis_agent_pack_preserves_analysis_style():
    materials = {
        "company": {"name": "NVIDIA", "ticker": "NVDA", "market": "US"},
        "context": "company context",
        "selectedDocs": [],
        "supportDocs": [],
        "filingDocs": [],
        "secFacts": {"ok": False},
        "dartFacts": {"ok": False},
        "rankedFiling": {"ok": False, "paragraphs": []},
        "marketFinancialData": {},
    }
    # 자료 수집과 컨텍스트 조립은 이제 `generation_context`가 소유한다. API 경로와 CLI
    # 경로가 같은 조립기를 쓰므로 이음매도 거기다.
    from features.company_analysis import generation_context as gen_ctx

    with (
        patch.object(gen_ctx, "load_index", return_value=[]),
        patch.object(gen_ctx, "search_documents", return_value=[]),
        patch.object(gen_ctx, "infer_requested_company", return_value=materials["company"]),
        patch.object(gen_ctx, "build_company_analysis_materials", return_value=materials),
        patch.object(gen_ctx, "build_company_analysis_charts", return_value={"available": False, "charts": []}),
        patch.object(gen_ctx, "company_analysis_sources", return_value=[]),
        patch.object(service.A, "write_pack", side_effect=lambda pack: Path("agent-pack.json")),
    ):
        pack, path = service.prepare_company_analysis_pack("NVDA", analysis_style="advanced")

    assert path == Path("agent-pack.json")
    assert pack["metadata"]["analysisStyle"] == "advanced"
    assert pack["draftArtifact"]["analysisStyle"] == "advanced"
    assert pack["draftArtifact"]["dataGaps"]["summary"]["highSeverityUnresolved"] >= 1
    assert pack["internal"]["analysisStyle"] == "advanced"
    assert "숙련자" in pack["prompt"]


def test_quality_repair_and_investment_review_write_to_temporary_stores():
    with TemporaryDirectory() as tmp:
        original_briefings = service.BRIEFINGS_DIR
        original_reviews = service.REVIEW_DIR
        service.BRIEFINGS_DIR = Path(tmp) / "briefings"
        service.REVIEW_DIR = Path(tmp) / "reviews"
        try:
            quality_pack = {
                "draftArtifact": {"date": "2099-12-31", "markdown": "old", "sources": []},
                "internal": {"targetArtifactType": "briefing", "targetArtifactId": "2099-12-31"},
            }
            repaired = service.write_quality_repair_from_markdown(quality_pack, "## Repaired\n\nContent")
            assert repaired["qualityGeneration"]["repairType"] == "agent"
            assert (service.BRIEFINGS_DIR / "2099-12-31.json").exists()

            review_pack = {"artifactId": "2099-12-31", "draftArtifact": {"date": "2099-12-31"}}
            review = service.write_investment_review_from_markdown(review_pack, "## Review")
            assert review["mode"] == "agent"
            assert review["generation"]["mode"] == "agent"
            assert (service.REVIEW_DIR / "2099-12-31.json").exists()
        finally:
            service.BRIEFINGS_DIR = original_briefings
            service.REVIEW_DIR = original_reviews


if __name__ == "__main__":
    test_market_memory_agent_writeback_uses_existing_normalizer()
    test_market_state_snapshot_agent_writeback_saves_current_snapshot()
    test_agent_chat_prompt_includes_market_memory_context()
    test_quality_repair_and_investment_review_write_to_temporary_stores()
