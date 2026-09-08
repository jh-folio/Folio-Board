import json

import pytest

from features.common.job_json_producers import BriefingJobRequest, JobJsonProducers
from features.common.shared_jobs_private import JobPrivateLifecycle
from features.common.shared_jobs_store import SharedJobStore
from features.common.tests.test_job_json_producers import _clock, _running
from features.common.quality_generation.call_budget import SharedRepairBudget, bind_briefing_budget
from features.daily_briefing.finalize import BriefingFinalizationError


@pytest.mark.parametrize("repairs", [0, 1])
def test_cli_commits_locally_corrected_writer_without_rules_fallback(monkeypatch, tmp_path, repairs):
    from features.common import job_json_producers

    # Keep the real finalizer, staging and commit; exclude unrelated semantics.
    monkeypatch.setattr(job_json_producers, "decorate_candidate", lambda _kind, report, **kw: report)
    report = _report("us", bad=True)
    report["generation"] = {"mode": "agent", "adapter": "codex", "model": "writer-test"}
    report["markdown"] = "기존 근거 설명은 유지한다. " + report["markdown"] + " 다른 분석도 유지한다."
    store = SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=_clock)
    job = _running(store, "briefing")
    producer = JobJsonProducers(tmp_path, clock=_clock)
    budget = SharedRepairBudget(max_repairs=repairs)
    with bind_briefing_budget(budget):
        bundle = producer.stage_briefing(job, BriefingJobRequest(
            "2026-07-18", ("us",), {"us": report}, {},
            {"artifactId": "2026-07-18", "reportId": "2026-07-18", "date": "2026-07-18", "title": "Briefing"},
        ))
        producer.workspace.commit(bundle, store, JobPrivateLifecycle(tmp_path / "job-context", clock=_clock))
    saved = json.loads((tmp_path / "briefings/2026-07-18.us.json").read_text(encoding="utf-8"))
    assert "-1.48%" not in saved["markdown"] and "+1.48%" in saved["markdown"]
    assert saved["markdown"].startswith("기존 근거 설명은 유지한다. ")
    assert saved["markdown"].endswith(" 다른 분석도 유지한다.")
    assert saved["generation"] == report["generation"]
    assert saved["finalValidation"]["contradictionCount"] == 0
    assert saved["finalValidation"]["localCorrectedPassageCount"] == 1
    assert budget.used == 0


def test_cancellation_during_local_correction_aborts_all_staging(monkeypatch, tmp_path):
    from features.common import job_json_producers
    from features.daily_briefing import local_fact_repair

    monkeypatch.setattr(job_json_producers, "decorate_candidate", lambda _kind, report, **kw: report)
    cancelled = {"value": False}
    original = local_fact_repair.correct_verified_passages

    def cancel_after_correction(*args):
        result = original(*args)
        cancelled["value"] = True
        return result

    monkeypatch.setattr(local_fact_repair, "correct_verified_passages", cancel_after_correction)
    store = SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=_clock)
    job = _running(store, "briefing")
    producer = JobJsonProducers(tmp_path, clock=_clock)
    request = BriefingJobRequest("2026-07-18", ("jp", "us"),
        {"jp": {"markdown": "Japan report"}, "us": _report("us", True)}, {}, {})
    with bind_briefing_budget(SharedRepairBudget(cancelled=lambda: cancelled["value"])), pytest.raises(BriefingFinalizationError) as raised:
        producer.stage_briefing(job, request)
    assert "cancelled" in raised.value.validation["reasonCodes"]
    assert not (tmp_path / "briefings").exists()
    assert not (tmp_path / "job-staging" / job.id).exists()


def _report(scope, bad=False):
    return {
        "marketScope": scope,
        "markdown": "NVDA는 -1.48% 하락했다." if bad else "NVDA는 +1.48% 상승했다.",
        "generation": {"mode": "rules"},
        "sources": [{"sourceId": "unsafe", "url": "javascript:alert(1)"}] if bad == "unsafe" else [],
        "marketSnapshot": {"tickers": {"NVDA": {"oneDayPct": 1.48, "asOfDate": "2026-07-18"}}},
    }


def test_rejection_preserves_reason_codes_without_candidate_text(tmp_path):
    store = SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=_clock)
    job = _running(store, "briefing")
    producer = JobJsonProducers(tmp_path, clock=_clock)
    with pytest.raises(BriefingFinalizationError) as raised:
        producer.stage_briefing(job, BriefingJobRequest(
            date="2026-07-18", scopes=("us",), reports={"us": _report("us", bad="unsafe")},
            visuals={}, terminal_result={"title": "Briefing"}, kind="daily",
        ))
    assert "unsafe_url" in raised.value.validation["reasonCodes"]
    assert set(raised.value.validation) == {"reasonCodes"}


@pytest.mark.parametrize("repairs", [0, 1])
def test_opening_and_threshold_prose_commits_unchanged_without_fallback(tmp_path, repairs):
    text = "코스피는 6,910.78에 출발해 6,995.39로 마감했다.\n코스피가 7,000선에 접근할 때 업종 확산을 본다."
    report = {"marketScope": "kr", "markdown": text, "generation": {"mode": "rules"},
              "koreaMarketData": {"indices": {"KOSPI": {"close": 6995.39, "changePct": 4.61, "asOfDate": "2026-09-07"}}}}
    store = SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=_clock)
    job = _running(store, "briefing")
    producer = JobJsonProducers(tmp_path, clock=_clock)
    with bind_briefing_budget(SharedRepairBudget(max_repairs=repairs)):
        bundle = producer.stage_briefing(job, BriefingJobRequest(
            "2026-09-07", ("kr",), {"kr": report}, {},
            {"artifactId": "2026-09-07", "reportId": "2026-09-07", "date": "2026-09-07", "title": "Briefing"},
        ))
        producer.workspace.commit(bundle, store, JobPrivateLifecycle(tmp_path / "job-context", clock=_clock))
    saved = json.loads((tmp_path / "briefings/2026-09-07.kr.json").read_text(encoding="utf-8"))
    assert saved["markdown"] == text
    assert saved["finalValidation"]["contradictionCount"] == 0
    assert saved["finalValidation"]["repairCount"] == 0
    assert not saved["generation"].get("fallbackReason")


def test_cli_stager_preserves_bad_market_and_commits_independent_good_market(tmp_path):
    data = tmp_path / "data"
    directory = data / "briefings"
    directory.mkdir(parents=True)
    old = directory / "2026-07-18.us.json"
    visual = directory / "2026-07-18.us.visuals.json.gz"
    old.write_text('{"markdown":"old normal"}', encoding="utf-8")
    visual.write_bytes(b"old sidecar")
    store = SharedJobStore(data / "jobs-v2.json", data / "jobs.json", clock=_clock)
    job = _running(store, "briefing")
    producer = JobJsonProducers(data, clock=_clock)
    request = BriefingJobRequest("2026-07-18", ("us", "jp"), {"us": _report("us", "unsafe"), "jp": {"markdown": "Japan report"}}, {"us": {"snapshots": {"NVDA": {"rows": []}}}}, {"artifactId": "2026-07-18", "reportId": "2026-07-18", "date": "2026-07-18"})
    with bind_briefing_budget(SharedRepairBudget()):
        bundle = producer.stage_briefing(job, request)
    producer.workspace.commit(bundle, store, JobPrivateLifecycle(data / "job-context", clock=_clock))
    assert old.read_text(encoding="utf-8") == '{"markdown":"old normal"}'
    assert visual.read_bytes() == b"old sidecar"
    result = json.loads((directory / "2026-07-18.jp.json").read_text(encoding="utf-8"))
    assert result["finalValidation"]["contradictionCount"] == 0
    assert all("us" not in item.id for item in bundle.intent.expectedArtifacts)


@pytest.mark.parametrize("generation_mode", ["rules", "agent"])
def test_briefing_job_commit_does_not_compare_or_project_legacy_change_metadata(
    monkeypatch, tmp_path, generation_mode
):
    """CLI/rules briefing saves stay free of retired top-level change metadata."""
    from features.common.change_intelligence import service as change_intelligence_module
    from features.common import job_json_artifacts, job_json_producers
    from features.common.change_intelligence import comparator, semantic

    report = _report("us", bad=False)
    report["generation"] = {"mode": generation_mode, "adapter": "fixture"}
    report.update({
        "changeBasis": {"artifactId": "legacy"},
        "changeSummary": {"status": "major_change"},
        "changeIntelligence": {"status": "major_change", "projectionStatus": "pending"},
    })
    calls = []

    def _record(name):
        def _call(*_args, **_kwargs):
            calls.append(name)
            return None
        return _call

    monkeypatch.setattr(job_json_producers, "decorate_candidate", _record("decorate"))
    monkeypatch.setattr(change_intelligence_module, "decorate_candidate", _record("decorate"))
    monkeypatch.setattr(comparator, "compare_basis", _record("compare"))
    monkeypatch.setattr(change_intelligence_module, "compare_basis", _record("compare"))
    monkeypatch.setattr(semantic, "evaluate_semantic_changes", _record("semantic"))
    monkeypatch.setattr(change_intelligence_module, "project_committed_report", _record("project"))
    monkeypatch.setattr(job_json_artifacts, "project_committed_report", _record("project"), raising=False)

    data_root = tmp_path / "data"
    store = SharedJobStore(data_root / "jobs-v2.json", data_root / "jobs.json", clock=_clock)
    job = _running(store, "briefing")
    producer = JobJsonProducers(data_root, clock=_clock)
    bundle = producer.stage_briefing(
        job,
        BriefingJobRequest(
            "2026-07-18", ("us",), {"us": report}, {},
            {"artifactId": "2026-07-18", "reportId": "2026-07-18", "date": "2026-07-18", "title": "Briefing"},
        ),
    )
    producer.workspace.commit(bundle, store, JobPrivateLifecycle(data_root / "job-context", clock=_clock))

    saved = json.loads((data_root / "briefings/2026-07-18.us.json").read_text(encoding="utf-8"))
    assert all(key not in saved for key in ("changeBasis", "changeSummary", "changeIntelligence"))
    assert not (data_root / "market-memory.sqlite3").exists()
    assert calls == []


@pytest.mark.parametrize("state", ["contradiction", "cancelled", "deadline"])
def test_rejected_or_cancelled_candidate_does_not_stage_any_bytes(tmp_path, state):
    data = tmp_path / "data"
    store = SharedJobStore(data / "jobs-v2.json", data / "jobs.json", clock=_clock)
    job = _running(store, "briefing")
    producer = JobJsonProducers(data, clock=_clock)
    request = BriefingJobRequest("2026-07-18", ("us",), {"us": _report("us", "unsafe" if state == "contradiction" else False)}, {}, {})
    budget = SharedRepairBudget(deadline=0 if state == "deadline" else None, cancelled=lambda: state == "cancelled")
    with bind_briefing_budget(budget), pytest.raises((BriefingFinalizationError, RuntimeError, TimeoutError)):
        producer.stage_briefing(job, request)
    assert not (data / "briefings").exists()
    assert not (data / "job-staging" / job.id).exists()
