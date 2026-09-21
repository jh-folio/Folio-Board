from features.company_analysis.service import (
    build_filing_item_context,
    company_analysis_doc_score,
    filing_form_type,
    is_sec_filing_doc,
)
from features.company_analysis import service as svc
from features.market_memory.snapshot import save_market_state_snapshot

from pathlib import Path
from tempfile import TemporaryDirectory


def test_s1_local_filing_gets_keyword_excerpts_without_item_headings():
    repeated_business = " ".join(["business customers services revenue launch starlink"] * 30)
    repeated_risk = " ".join(["risk factors regulatory faa license launch competition liquidity"] * 30)
    repeated_growth = " ".join(["growth strategy investment capacity expansion starship ai"] * 30)
    spacer = " ".join(["neutral disclosure text"] * 450)
    doc = {
        "title": "Space Exploration Technologies - S-1",
        "path": "research-inbox/filings/SPCX_Space Exploration Technologies - S-1.html",
        "type": "filing",
        "date": "2026-06-15",
        "wordCount": 900,
        "content": f"""
            <html><body>
            <type>S-1</type>
            <title>Space Exploration Technologies Corp. Registration Statement</title>
            <p>{repeated_business}</p>
            <p>{spacer}</p>
            <p>{repeated_risk}</p>
            <p>{spacer}</p>
            <p>{repeated_growth}</p>
            </body></html>
        """,
    }

    assert is_sec_filing_doc(doc)
    assert filing_form_type(doc) == "S-1"

    context, used, paragraphs = build_filing_item_context([doc])

    assert used == [doc]
    assert "Extraction: keyword_excerpt" in context
    assert "Rule: 아래 로컬 공식자료 발췌" in context
    assert len(paragraphs) >= 2
    assert any(row.get("item") in {"risk", "regulation"} for row in paragraphs)


def test_same_form_local_filings_prefer_the_most_recent_disclosure():
    def make_doc(year: str) -> dict:
        body = " ".join(["business customers revenue segment platform"] * 30)
        risk = " ".join(["risk factors regulation liquidity competition legal"] * 30)
        growth = " ".join(["growth strategy investment margin cash flow ai"] * 30)
        spacer = " ".join(["neutral disclosure text"] * 450)
        return {
            "title": f"Example Corp - 10-K {year}",
            "path": f"research-inbox/filings/EX_10-K_{year}.html",
            "type": "filing",
            "date": f"{year}-02-10",
            "wordCount": 900,
            "content": f"""
                <html><body>
                <type>10-K</type>
                <title>Example Corp Annual Report {year}</title>
                <p>{body}</p>
                <p>{spacer}</p>
                <p>{risk}</p>
                <p>{spacer}</p>
                <p>{growth}</p>
                </body></html>
            """,
        }

    docs = [make_doc("2021"), make_doc("2025"), make_doc("2023")]
    assert {filing_form_type(d) for d in docs} == {"10-K"}

    _context, used, paragraphs = build_filing_item_context(docs, max_filings=2)

    assert [d["date"] for d in used] == ["2025-02-10", "2023-02-10"]
    assert paragraphs[0]["source"].endswith("EX_10-K_2025.html")


def test_company_analysis_materials_include_market_memory_as_context_not_evidence():
    with TemporaryDirectory() as tmp:
        original_db = svc.MARKET_MEMORY_DB_PATH
        svc.MARKET_MEMORY_DB_PATH = Path(tmp) / "market-memory.sqlite3"
        try:
            save_market_state_snapshot(svc.MARKET_MEMORY_DB_PATH, {
                "headline": "금리와 AI가 함께 시장을 설명",
                "oneLineSummary": "AI 수요는 강하지만 금리 부담이 밸류에이션을 제한한다.",
                "marketRegime": "selective_growth",
                "actionPosture": "기업별 실적 확인 전까지 선별 관찰",
                "keyDrivers": [{"title": "AI 공급망", "summary": "수요 기대가 유지된다.", "sourceRefs": ["rss:1"]}],
                "watchItems": ["10년물 금리"],
                "counterEvidence": ["금리 상승"],
                "sourceRefs": [{"id": "rss:1", "title": "AI demand", "source": "Reuters"}],
                "confidence": 0.7,
            })
            materials = svc.build_company_analysis_materials("NVDA", [], {"name": "NVIDIA", "ticker": "NVDA", "market": "US"})
            assert "## Market Memory Context" in materials["context"]
            assert "기업 고유 사실의 evidence가 아니라 시장 배경" in materials["context"]
        finally:
            svc.MARKET_MEMORY_DB_PATH = original_db


def test_us_company_analysis_penalizes_kr_only_news_sources():
    company = {"name": "Micron Technology, Inc.", "ticker": "MU", "market": "US"}
    us_doc = {
        "title": "Micron earnings show memory recovery",
        "summary": "Micron revenue and AI memory demand improve.",
        "content": "Micron MU revenue earnings AI memory demand margin guidance " * 40,
        "source": "Reuters",
        "sourceWeight": 10,
        "type": "article",
        "path": "research-inbox/rss/reuters-mu.md",
        "url": "https://www.reuters.com/markets/companies/MU.O/",
        "date": "2026-07-05",
        "wordCount": 420,
        "markets": ["US"],
    }
    kr_doc = {
        **us_doc,
        "source": "한국경제",
        "sourceWeight": 9,
        "path": "research-inbox/rss/hankyung-mu.md",
        "url": "https://www.hankyung.com/article/mu",
        "markets": ["KR"],
    }

    us_score = company_analysis_doc_score(us_doc, company, "MU")
    kr_score = company_analysis_doc_score(kr_doc, company, "MU")

    assert us_score["analysisScore"] > kr_score["analysisScore"]
    assert "미국 기업 분석에서 KR 전용 뉴스 감점" in kr_score["analysisReasons"]


def test_generate_llm_company_analysis_uses_selected_style_prompt(monkeypatch):
    captured = {}

    def fake_config():
        return {"provider": "openai", "enabled": True, "apiKey": "test", "model": "test-model"}

    def fake_openai(_cfg, prompt, context, web_search=False, include_usage=True):
        captured["prompt"] = prompt
        captured["context"] = context
        return "## 분석 결과", "resp-1", {}

    monkeypatch.setattr(svc, "selected_cli_config", fake_config)
    monkeypatch.setattr(svc, "request_cli_text", fake_openai)

    result, status = svc.generate_llm_company_analysis(
        "NVDA",
        [],
        web_search_override=False,
        llm_override=True,
        materials={"context": "context", "selectedDocs": [], "company": {"name": "NVIDIA", "ticker": "NVDA"}},
        quality_preflight={},
        analysis_style="advanced",
    )

    assert status == "ok_local_only"
    assert result["markdown"] == "## 분석 결과"
    assert "숙련자" in captured["prompt"]
    assert "초심자" not in captured["prompt"].split("숙련자", 1)[0]


def test_analyze_company_report_includes_style_and_data_gaps(monkeypatch):
    import app

    materials = {
        "company": {"name": "NVIDIA", "ticker": "NVDA", "market": "US"},
        "context": "context",
        "selectedDocs": [],
        "supportDocs": [],
        "filingDocs": [],
        "secFacts": {"ok": False},
        "dartFacts": {"ok": False},
        "rankedFiling": {"ok": False, "paragraphs": []},
        "marketFinancialData": {},
    }

    monkeypatch.setattr(app, "load_index", lambda: [])
    monkeypatch.setattr(app, "search_documents", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(app, "infer_requested_company", lambda *_args, **_kwargs: materials["company"])
    monkeypatch.setattr(app, "build_company_analysis_materials", lambda *_args, **_kwargs: materials)
    monkeypatch.setattr(app, "build_company_analysis_charts", lambda *_args, **_kwargs: {"available": False, "charts": []})
    monkeypatch.setattr(app, "generate_llm_company_analysis", lambda *_args, **_kwargs: (None, "disabled"))
    monkeypatch.setattr(app, "build_rule_report", lambda analysis, analysis_style="beginner": f"{analysis_style} rule report")
    monkeypatch.setattr(app, "company_analysis_sources", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(app, "selected_cli_config", lambda: {"provider": "openai"})

    report = app.analyze_company("NVDA", llm_override=False, analysis_style="advanced")

    assert report["analysisStyle"] == "advanced"
    assert report["markdown"] == "advanced rule report"
    assert report["dataGaps"]["summary"]["highSeverityUnresolved"] >= 1
    assert report["resolutionAttempts"] == report["dataGaps"]["gaps"]


def test_saved_analysis_list_preserves_style_and_gap_summary(monkeypatch, tmp_path):
    from features.company_analysis import service

    monkeypatch.setattr(service, "ANALYSIS_REPORTS_DIR", tmp_path)

    saved = service.save_analysis_report({
        "query": "NVDA",
        "company": {"name": "NVIDIA", "ticker": "NVDA"},
        "generatedAt": "2026-07-05T00:00:00+09:00",
        "headline": "NVIDIA 기업 분석",
        "markdown": "# NVIDIA",
        "analysisStyle": "beginner",
        "dataGaps": {"summary": {"highSeverityUnresolved": 1}, "gaps": []},
        "generation": {"mode": "rules", "provider": "local"},
    })

    listed = service.list_analysis_reports()

    assert listed[0]["id"] == saved["id"]
    assert listed[0]["analysisStyle"] == "beginner"
    assert listed[0]["dataGapSummary"]["highSeverityUnresolved"] == 1
