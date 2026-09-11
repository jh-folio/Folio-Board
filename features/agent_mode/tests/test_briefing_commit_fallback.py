import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest

from features.agent_mode import job_runtime, service
from features.common.job_json_producer_types import BriefingJobRequest
from features.common.job_json_producers import JobJsonProducers
from features.common.quality_generation.call_budget import SharedRepairBudget, bind_briefing_budget
from features.common.shared_jobs_private import JobPrivateLifecycle
from features.common.shared_jobs_store import SharedJobStore
from features.daily_briefing.finalize import BriefingFinalizationError
from features.daily_briefing.source_integrity import MANIFEST_END, MANIFEST_START
from features.common.shared_jobs_schema import TaskType
from features.common.tests.test_job_json_producers import _clock, _running


def test_unrelated_value_error_is_not_disguised_as_output_contract_failure(tmp_path):
    with (
        patch.object(job_runtime, "_running", return_value=SimpleNamespace()),
        patch.object(job_runtime.jobs, "data_root", return_value=tmp_path),
        patch.object(job_runtime.jobs, "private_lifecycle", return_value=object()),
        patch.object(job_runtime.agent_service, "write_briefing_from_markdown", side_effect=ValueError("configuration_error")),
        patch.object(job_runtime, "_prepare_rules_briefing_fallback") as fallback,
        pytest.raises(ValueError, match="configuration_error"),
    ):
        job_runtime.commit_json_output("job-test", TaskType.BRIEFING, _pack(), markdown="text", payload=None)
    fallback.assert_not_called()


def test_contract_failure_keeps_only_closed_codes():
    from features.agent_mode.briefing_contract import BriefingOutputContractError
    error = BriefingOutputContractError(["필수 제목 누락: private subject", "최소 분량 미달: private text"])
    prepared = job_runtime._prepare_rules_briefing_fallback(
        _pack(), reason="cli_output_contract_failed", rejection_codes=error.reason_codes,
    )
    assert prepared["reports"]["us"]["generation"]["rejectedReasonCodes"] == ["contract_missing_heading", "contract_too_short"]


def _pack():
    document = {
        "sourceId": "rss:test-1",
        "path": "research-inbox/rss/test.md",
        "title": "NVIDIA AI demand rises",
        "summary": "NVIDIA demand and shares rose 1.48%.",
        "content": "NVIDIA demand and shares rose 1.48%.",
        "date": "2026-09-07",
        "market": "US",
        "source": "Reuters",
        "type": "rss",
        "url": "https://example.com/test",
        "companies": [{"name": "NVIDIA", "market": "US"}],
        "sectors": ["semiconductor"],
        "impactTags": ["earnings"],
        "sourceWeight": 9,
        "marketRelevance": 90,
        "wordCount": 180,
    }
    second_document = {
        **document,
        "sourceId": "rss:test-2",
        "path": "research-inbox/rss/test-2.md",
        "title": "Microsoft cloud demand supports Nasdaq",
        "summary": "Microsoft cloud demand supports shares.",
        "content": "Microsoft cloud demand supports shares.",
        "companies": [{"name": "Microsoft", "market": "US"}],
    }
    return {
        "artifactId": "2026-09-07",
        "draftArtifact": {
            "date": "2026-09-07",
            "marketScope": "us",
            "generationMarkets": ["us"],
            "briefingType": "concise",
            "kind": "daily",
            "stats": {"sourceDate": "2026-09-07"},
            "marketWindows": {},
            "marketSnapshot": {"ok": False},
            "koreaMarketData": {"ok": False},
        },
        "internal": {"groups": [
            {"company": "NVIDIA", "sector": "semiconductor", "docs": [document]},
            {"company": "Microsoft", "sector": "software", "docs": [second_document]},
        ]},
    }


def _prepared():
    report = {"date": "2026-09-07", "kind": "daily", "marketScope": "us", "generation": {}}
    return {
        "reports": {"us": report},
        "result": {"date": "2026-09-07", "kind": "daily", "title": "Briefing"},
        "visuals": {},
    }


def _multi_market_pack():
    pack = _pack()
    pack["draftArtifact"] = {
        **pack["draftArtifact"],
        "marketScope": "both",
        "generationMarkets": ["us", "kr"],
    }
    base = pack["internal"]["groups"][0]["docs"][0]
    for index, (name, ticker) in enumerate((("삼성전자", "005930"), ("SK하이닉스", "000660")), 1):
        document = {
            **base,
            "sourceId": f"rss:kr-{index}",
            "path": f"research-inbox/rss/kr-{index}.md",
            "title": f"{name} 코스피 수급 update",
            "summary": f"{name} shares rose.",
            "content": f"{name} shares rose.",
            "market": "KR",
            "companies": [{"name": name, "ticker": ticker, "market": "KR"}],
        }
        pack["internal"]["groups"].append({
            "company": name, "sector": "semiconductor", "docs": [document],
        })
    pack["sources"] = [
        document
        for group in pack["internal"]["groups"]
        for document in group["docs"]
    ]
    return pack


def test_rules_fallback_reuses_only_pinned_pack_documents():
    markdown = service.build_rules_briefing_markdown_from_pack(_pack())

    assert "# US Market Briefing" in markdown
    assert "## 0. 오늘의 미국장 성격" in markdown
    assert "NVIDIA" in markdown
    assert "NVIDIA AI demand rises" in markdown


def test_rules_fallback_is_ready_for_shared_staging():
    prepared = job_runtime._prepare_rules_briefing_fallback(
        _pack(), reason="cli_output_contract_failed"
    )

    assert set(prepared["reports"]) == {"us"}
    assert prepared["reports"]["us"]["generation"]["mode"] == "rules"
    assert prepared["result"]["generation"]["status"] == "rules_fallback_after_cli_validation"
    assert prepared["fallbackReason"] == "cli_output_contract_failed"


def test_rules_fallback_handles_empty_groups():
    pack = _pack()
    pack["internal"]["groups"] = []
    markdown = service.build_rules_briefing_markdown_from_pack(pack)
    assert "# US Market Briefing" in markdown


def test_rules_fallback_handles_market_without_matching_groups():
    pack = _pack()
    pack["draftArtifact"]["generationMarkets"] = ["us", "kr"]
    pack["draftArtifact"]["marketScope"] = "both"
    markdown = service.build_rules_briefing_markdown_from_pack(pack)
    assert "# US Market Briefing" in markdown
    assert "# Korea Market Briefing" in markdown


def test_rules_fallback_candidate_passes_the_real_shared_stager(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "BRIEFINGS_DIR", tmp_path / "briefings")
    prepared = job_runtime._prepare_rules_briefing_fallback(
        _pack(), reason="cli_final_validation_failed"
    )
    data_root = tmp_path / "data"
    store = SharedJobStore(data_root / "jobs-v2.json", data_root / "jobs.json", clock=_clock)
    job = _running(store, "briefing")
    producer = JobJsonProducers(data_root, clock=_clock)

    with bind_briefing_budget(SharedRepairBudget()):
        bundle = producer.stage_briefing(
            job,
            BriefingJobRequest(
                "2026-09-07",
                ("us",),
                prepared["reports"],
                {},
                {
                    "artifactId": "2026-09-07",
                    "reportId": "2026-09-07",
                    "date": "2026-09-07",
                    "title": "Briefing",
                },
                kind="daily",
            ),
        )

    assert bundle.intent.expectedArtifacts
    assert bundle.intent.expectedArtifacts[0].id == "2026-09-07.us"


def test_writeback_and_shared_commit_canonicalize_duplicate_url_aliases(tmp_path, monkeypatch):
    # This crosses the real writeback -> source ledger -> common stager path;
    # a duplicate candidate URL must not leave the claim pointing at a source
    # ID that disappeared during the first service-side cap/dedup pass.
    # Keep the no-persist writeback read path isolated from the user's active
    # briefing directory; otherwise an existing same-session report can be
    # merged into this fixture before the shared commit is exercised.
    monkeypatch.setattr(service, "BRIEFINGS_DIR", tmp_path / "generated-briefings")
    monkeypatch.setattr(service, "resolve_briefing_by_session", lambda *_args, **_kwargs: None)
    pack = _pack()
    pack["sources"] = [
        {"sourceId": "src_a", "title": "Input A", "url": "https://example.org/a"},
        {"sourceId": "alias_a", "title": "Input A alias", "url": "https://EXAMPLE.org/a/"},
    ]
    authored = service.build_rules_briefing_markdown_from_pack(pack)
    authored += (
        "\n"
        f"{MANIFEST_START}\n"
        '{"usedSourceIds":["alias_a"],"externalSources":[],'
        '"claims":[{"claim":"input","sourceIds":["alias_a"]}]}\n'
        f"{MANIFEST_END}"
    )
    written = service.write_briefing_from_markdown(
        pack, authored, persist=False, validate_contract=False
    )
    report = written["reports"]["us"]

    data_root = tmp_path / "data"
    store = SharedJobStore(data_root / "jobs-v2.json", data_root / "jobs.json", clock=_clock)
    job = _running(store, "briefing")
    producer = JobJsonProducers(data_root, clock=_clock)
    with bind_briefing_budget(SharedRepairBudget()):
        bundle = producer.stage_briefing(
            job,
            BriefingJobRequest(
                "2026-09-07", ("us",), {"us": report}, {},
                {"artifactId": "2026-09-07", "reportId": "2026-09-07", "date": "2026-09-07", "title": "Briefing"},
                kind="daily",
            ),
        )
        producer.workspace.commit(bundle, store, JobPrivateLifecycle(data_root / "job-context", clock=_clock))
    saved = json.loads((data_root / "briefings/2026-09-07.us.json").read_text(encoding="utf-8"))
    # The deterministic rules body also contains a visible source link from
    # the pinned pack; it is retained as a separate safe external row. The
    # duplicate candidate alias itself must collapse to the canonical ID.
    saved_ids = [row["sourceId"] for row in saved["sources"]]
    assert saved_ids[0] == "src_a"
    assert "alias_a" not in saved_ids
    assert saved["claimLedger"]["claims"][0]["sourceIds"] == ["src_a"]


def test_multi_market_writeback_and_shared_commit_keep_each_market(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "BRIEFINGS_DIR", tmp_path / "generated-briefings")
    monkeypatch.setattr(service, "resolve_briefing_by_session", lambda *_args, **_kwargs: None)
    pack = _multi_market_pack()
    authored = service.build_rules_briefing_markdown_from_pack(pack)
    authored += (
        "\n"
        f"{MANIFEST_START}\n"
        '{"usedSourceIds":[],"externalSources":[{"sourceId":"web_a","title":"Public release",'
        '"url":"https://example.org/release"}],"claims":[{"sourceIds":["web_a"]}]}\n'
        f"{MANIFEST_END}"
    )
    written = service.write_briefing_from_markdown(
        pack, authored, persist=False, validate_contract=False
    )
    data_root = tmp_path / "data"
    store = SharedJobStore(data_root / "jobs-v2.json", data_root / "jobs.json", clock=_clock)
    job = _running(store, "briefing")
    producer = JobJsonProducers(data_root, clock=_clock)
    with bind_briefing_budget(SharedRepairBudget()):
        bundle = producer.stage_briefing(
            job,
            BriefingJobRequest(
                "2026-09-07", ("us", "kr"), written["reports"], {},
                {"artifactId": "2026-09-07", "reportId": "2026-09-07", "date": "2026-09-07", "title": "Briefing"},
                kind="daily",
            ),
        )
        producer.workspace.commit(bundle, store, JobPrivateLifecycle(data_root / "job-context", clock=_clock))

    for scope in ("us", "kr"):
        saved = json.loads((data_root / f"briefings/2026-09-07.{scope}.json").read_text(encoding="utf-8"))
        assert saved["marketScope"] == scope
        expected_title = "# US Market Briefing" if scope == "us" else "# Korea Market Briefing"
        assert expected_title in saved["markdown"]
        assert "web_a" in {row["sourceId"] for row in saved["sources"]}
        assert saved["generation"]["mode"] == "agent"
        assert not saved["generation"].get("fallbackReason")
        assert saved["finalValidation"]["contentAssessment"] == "not_assessed"
        assert "source_outside_whitelist" not in (saved.get("finalValidation") or {}).get("reasonCodes", [])


def test_commit_retries_shared_stage_with_rules_fallback_after_final_rejection(tmp_path):
    calls = []

    class Producer:
        def __init__(self, *_args, **_kwargs):
            self.workspace = SimpleNamespace(commit=lambda *_args: calls.append("commit"))

        def stage_briefing(self, _job, request):
            calls.append(request.terminal_result)
            if len(calls) == 1:
                raise BriefingFinalizationError("briefing_final_validation_failed")
            return SimpleNamespace(terminal_result=request.terminal_result)

    with (
        patch.object(job_runtime, "_running", return_value=SimpleNamespace()),
        patch.object(job_runtime.jobs, "data_root", return_value=tmp_path),
        patch.object(job_runtime.jobs, "private_lifecycle", return_value=object()),
        patch.object(job_runtime.jobs, "shared_store", return_value=SimpleNamespace(update_runtime=lambda *_args: calls.append("runtime_rules"))),
        patch.object(job_runtime, "JobJsonProducers", Producer),
        patch.object(job_runtime.agent_service, "write_briefing_from_markdown", return_value=_prepared()),
        patch.object(
            job_runtime,
            "_prepare_rules_briefing_fallback",
            return_value={**_prepared(), "fallbackReason": "cli_final_validation_failed"},
        ) as fallback,
    ):
        result = job_runtime.commit_json_output(
            "job-1",
            TaskType.BRIEFING,
            _pack(),
            markdown="# rejected",
            payload=None,
        )

    fallback.assert_called_once_with(_pack(), reason="cli_final_validation_failed", rejection_codes=[])
    assert "runtime_rules" in calls
    assert result["generationMode"] == "rules"
    assert result["fallbackReason"] == "cli_final_validation_failed"
    request_results = [item for item in calls if isinstance(item, dict)]
    assert request_results[-1]["generationMode"] == "rules"
    assert request_results[-1]["fallbackReason"] == "cli_final_validation_failed"
    assert request_results[-1] != request_results[0]
    assert calls.count("commit") == 1
