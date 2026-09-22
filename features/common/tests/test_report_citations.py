import json
from pathlib import Path

import pytest

from features.common.execution_result import ExecutionResult
from features.common.provider_result import Citation, ProviderPayload
from features.common.report_citations import render_citation_links, strip_citation_links

URL = "https://example.com/Acme/annual(2026)?a=1&b=2"
LEDGER = [{"sourceId": "ev_001", "title": "Acme 연차보고서", "url": URL}]


def native(text, *, url=URL, start=0, end=None):
    return ExecutionResult(text=text, provider=ProviderPayload(adapter="claude", session_id="PRIVATE_SESSION",
        citations=(Citation(block_index=0, start=start, end=len(text) if end is None else end,
                            url=url, source_id="PRIVATE_SOURCE", cited_text="PRIVATE_QUOTE"),)))


def test_native_link_is_ledger_backed_private_free_and_idempotent():
    text = "## 사업\n\n매출이 증가했다."
    execution = native(text)
    result = render_citation_links(text, LEDGER, execution=execution)
    assert "[Acme 연차보고서](https://example.com/Acme/annual%282026%29?a=1&b=2)" in result
    assert "PRIVATE" not in result
    assert strip_citation_links(result) == text
    assert render_citation_links(result, LEDGER, execution=execution) == result
    assert render_citation_links(result.strip(), LEDGER, execution=execution) == result
    assert json.loads(json.dumps({"markdown": result}))["markdown"] == result


@pytest.mark.parametrize("changed", ["수정된 주장", "본문 본문", ""])
def test_edited_or_ambiguous_native_span_does_not_attach(changed):
    assert render_citation_links(changed, LEDGER, execution=native("본문")) == changed


def test_remapped_unchanged_block_and_same_url_deduplicate():
    original = "본문"
    text = "# 제목\n\n본문\n\n<!-- folio-source-ids: ev_001 -->"
    result = render_citation_links(text, LEDGER, execution=native(original))
    assert result.count("인용 출처:") == 2  # different attributed blocks
    combined = render_citation_links("본문 [ev_001, ev_001]", LEDGER)
    assert combined.count("[Acme 연차보고서]") == 1


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///secret", "https://u:p@example.com/a", "https://example.com/a\nB", "https://[bad", "https://example.com\\bad"])
def test_unsafe_url_never_links(url):
    text = "본문 [ev_001]"
    assert render_citation_links(text, [{**LEDGER[0], "url": url}]) == text


def test_unknown_and_ambiguous_sources_are_not_inferred():
    text = "본문 [ev_999]"
    assert render_citation_links(text, LEDGER, execution=native(text, url="https://other.example/a")) == text
    assert render_citation_links(text, LEDGER * 2, execution=native(text)) == text
    assert render_citation_links("[ev_001]", LEDGER * 2) == "[ev_001]"


@pytest.mark.parametrize("text", ["```md\n[ev_001]\n```", "```md\n[ev_001]", "`[ev_001]`", "[ev_001](https://other.example/a)", "~~~md\n<!-- folio-source-ids: ev_001 -->\n~~~"])
def test_examples_and_existing_links_are_not_citations(text):
    assert render_citation_links(text, LEDGER) == text


def test_table_is_not_split_and_unknown_ids_remain_visible():
    text = "| 내용 | 출처 |\n|---|---|\n| 매출 | [ev_001, ev_999] |\n| 비용 | 20 |\n\n## 다음\n다음 본문"
    result = render_citation_links(text, LEDGER)
    assert result.index("인용 출처:") > result.index("| 비용 | 20 |")
    assert "ev_999" in result and strip_citation_links(result) == text


def test_notion_payload_preserves_links_without_internal_comments():
    from features.notion_export.client import markdown_to_blocks
    text = render_citation_links("본문\n\n<!-- folio-source-ids: ev_001 -->", LEDGER)
    blocks = markdown_to_blocks(text)
    rich = [piece for b in blocks for piece in b[b["type"]].get("rich_text", [])]
    links = [p["text"]["link"]["url"] for p in rich if p["text"].get("link")]
    assert links == [URL.replace("(", "%28").replace(")", "%29")]
    assert "<!--" not in json.dumps(blocks)


@pytest.mark.parametrize("kind", ["company", "topic"])
def test_obsidian_real_file_preserves_citation_and_user_notes(tmp_path, monkeypatch, kind):
    from features.obsidian.export import service
    monkeypatch.setattr(service, "_require_vault", lambda: tmp_path)
    monkeypatch.setattr(service, "_all_company_names", lambda: ["Acme"])
    text = render_citation_links("Acme 본문\n\n<!-- folio-source-ids: ev_001 -->", LEDGER)
    report = {"markdown": text, "company": {"name": "Acme", "ticker": "ACME"}, "topicLabel": "Acme 조사"}
    export = service.export_analysis_to_obsidian if kind == "company" else service.export_topic_report_to_obsidian
    result = export(report)
    path = Path(result["path"])
    content = path.read_text(encoding="utf-8")
    assert "[[Acme]] 본문" in content
    assert "[Acme 연차보고서](https://example.com/Acme/annual%282026%29?a=1&b=2)" in content
    assert "reuse_as_evidence: false" in content.lower()
    path.write_text(content + "\n사용자 생각 유지", encoding="utf-8")
    export(report)
    assert "사용자 생각 유지" in path.read_text(encoding="utf-8")


def test_company_service_projects_native_result_without_leaking_it(monkeypatch):
    from features.company_analysis import service
    from features.company_analysis.tests.test_generation_paths import _MATERIALS
    monkeypatch.setattr(service, "selected_cli_config", lambda: {"enabled": True, "provider": "claude", "model": "test"})
    def request(*args, **kwargs):
        kwargs["result_sink"]["result"] = native("원래 본문")
        return "원래 본문", "", {}
    monkeypatch.setattr(service, "request_cli_text", request)
    result, status = service.generate_llm_company_analysis("ACME", [], materials=_MATERIALS,
        context="fixed", llm_override=True, web_search_override=False, source_ledger=LEDGER)
    assert status.startswith("ok_")
    assert "인용 출처:" in result["markdown"]
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("improved", [True, False])
def test_company_bridge_uses_only_selected_retry_citations(tmp_path, monkeypatch, improved):
    from unittest.mock import Mock
    from features.agent_mode import bridge
    from features.company_analysis import service
    from features.company_analysis.tests.test_preservation_safety import _draft
    first = _draft(drop=("어떻게 접근할까",))
    second = _draft() if improved else first
    second_url = "https://example.com/second"
    ledger = LEDGER + [{"sourceId": "ev_002", "title": "두 번째 자료", "url": second_url}]
    pack = {"taskType": "company_analysis", "artifactType": "company_analysis", "artifactId": "ACME_2099-12-31",
            "outputContract": {"format": "markdown"}, "draftArtifact": {"company": {"name": "Acme", "ticker": "ACME"},
            "generatedAt": "2099-12-31T00:00:00Z", "sourceLedger": ledger}}
    monkeypatch.setattr(service, "ANALYSIS_REPORTS_DIR", tmp_path / "analysis")
    monkeypatch.setattr(bridge.agent_service, "prepare_pack", lambda *a, **k: (pack, tmp_path / "pack.json"))
    calls = iter([(first, URL), (second, second_url)])
    def invoke(*a, **k):
        body, url = next(calls)
        k["result_sink"]["result"] = native(body, url=url)
        return body
    monkeypatch.setattr(bridge, "_invoke_task_cli", invoke)
    monkeypatch.setattr(bridge.schema, "update_pack_status", lambda *a, **k: None)
    writeback = Mock(return_value={"id": "report", "saved": True})
    monkeypatch.setattr(bridge.agent_service, "writeback_pack", writeback)
    bridge._run_agent_task_locked("company_analysis", {}, selected={"id": "claude", "executable": "unused", "available": True},
                                  durable=False, progress=lambda *a, **k: None, job_id="")
    output = writeback.call_args.kwargs["markdown"]
    assert ("두 번째 자료" in output) is improved
    assert ("Acme 연차보고서" in output) is not improved
    assert "PRIVATE" not in json.dumps(pack)


def test_deep_repair_drops_changed_native_citation_including_recovery_checkpoint(tmp_path):
    from dataclasses import replace
    from features.common.quality_generation.candidate_store import CandidateStore
    from features.topic_report.deep_pipeline import run_deep_pipeline
    from features.topic_report.tests.test_deep_pipeline import _markdown, _outcome, _command, JOB_ID
    text = _markdown(thin="현재 상황")
    original = _outcome(text)
    # A native citation covered the complete original response. Editing a
    # section invalidates that scope, even if the final paragraph survives.
    original.report["sourceLedger"] = [{**LEDGER[0], "evidenceRole": "challenging", "date": "2026-08-23"}]
    original = replace(original, execution=native(text))
    def repair(*args):
        return json.dumps({"patches": [{"heading": "현재 상황", "replacementBody": "보강한 조건부 분석 문장입니다. " * 50, "sourceIds": ["ev_001"]}]})
    store = CandidateStore(tmp_path / "candidates")
    result = run_deep_pipeline(original, _command(), job_id=JOB_ID, report_id="report-a", candidate_store=store, repair_call=repair)
    assert result.report["executionProvenance"]["selectedCandidateIndex"] == 1
    clean = strip_citation_links(result.report["markdown"])
    # Only surviving explicit source tags contribute; native full-body link is gone.
    assert result.report["markdown"] == render_citation_links(clean, result.report["sourceLedger"])
    checkpoint = store.latest_accepted(JOB_ID)
    assert checkpoint.report["markdown"] == result.report["markdown"]
    assert "PRIVATE" not in json.dumps(checkpoint.report)


@pytest.mark.parametrize("kind", ["company", "topic"])
def test_notion_export_service_sends_real_link_payload(monkeypatch, kind):
    from features.notion_export import service
    monkeypatch.setattr(service, "_require_config", lambda: {"token": "fake", "dbId": "fake"})
    payloads = []
    def create(*a, **k):
        payloads.append(k)
        return {"id": "fixture", "url": "https://notion.example/fixture"}
    monkeypatch.setattr(service, "create_page", create)
    report = {"markdown": render_citation_links("본문 [ev_001]", LEDGER), "company": {"name": "Acme"}}
    (service.export_analysis if kind == "company" else service.export_topic_report)(report)
    content = json.dumps(payloads, ensure_ascii=False)
    assert "annual%282026%29" in content and "folio-citation-links" not in content
