from __future__ import annotations

import json
from concurrent.futures import CancelledError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from features.agent_mode import bridge
from features.agent_mode import service as agent_service
from features.company_analysis import generation_service
from features.company_analysis import service
from features.company_analysis.direct_observer import run_direct_analysis
from features.company_analysis.finalize import finalize_report
from features.company_analysis.style import REQUIRED_SECTION_HEADINGS


def _draft(*, drop: tuple[str, ...] = ()) -> str:
    return "\n\n".join(
        f"## {heading}\n\n본문입니다."
        for heading in REQUIRED_SECTION_HEADINGS
        if heading not in drop
    )


def _inputs() -> SimpleNamespace:
    company = {"name": "Howmet", "ticker": "HWM"}
    materials = {"company": company, "selectedDocs": []}
    return SimpleNamespace(
        company=company,
        docs=[],
        materials=materials,
        selected=[],
        charts=[],
        preflight={},
        depthPolicy={},
        sourceLedger=[],
        webSourceItems=[],
        dataGaps={"gaps": []},
        quoteSources=[],
        context="",
    )


def _generation_runtime(llm):
    return {
        "build_generation_inputs": lambda *args, **kwargs: _inputs(),
        "generate_llm_company_analysis": llm,
        "build_rule_report": lambda *args, **kwargs: "# 규칙 기반 보고서",
        "company_analysis_sources": lambda *args, **kwargs: [],
        "selected_llm_config": lambda: {"provider": "openai", "model": ""},
        "use_web_search_for_analysis": lambda: False,
    }


def test_api_retry_timeout_keeps_exact_first_usable_draft(monkeypatch: pytest.MonkeyPatch):
    original = _draft(drop=("어떻게 접근할까",))
    calls = {"count": 0}

    def llm(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return {"markdown": original, "usedDocs": [], "webSearch": False}, "ok"
        raise TimeoutError("provider timeout with sensitive details")

    runtime = _generation_runtime(llm)
    monkeypatch.setattr(generation_service, "build_generation_inputs", runtime.pop("build_generation_inputs"))
    monkeypatch.setattr(generation_service, "draft_artifact", lambda *args, **kwargs: {
        "company": _inputs().company, "analysisInputs": {}, "dataGaps": {"gaps": []},
        "resolutionAttempts": [], "sourceLedger": [], "depthPolicy": {}, "sources": [],
    })
    monkeypatch.setattr(generation_service, "resolve_company_analysis_gaps", lambda *args, **kwargs: {"gaps": []})
    monkeypatch.setattr(generation_service, "decorate_candidate", lambda _kind, report, **kwargs: report)

    report = generation_service.analyze_company("HWM", runtime=runtime)

    assert calls["count"] == 2
    assert report["markdown"] == original
    assert report["draftGuard"] == {
        "missing": ["어떻게 접근할까"], "retried": True, "outcome": "retry_failed",
    }


def test_api_initial_structure_check_error_keeps_body_unassessed(monkeypatch: pytest.MonkeyPatch):
    exact = _draft(drop=("어떻게 접근할까",))
    runtime = _generation_runtime(lambda *args, **kwargs: ({"markdown": exact, "usedDocs": [], "webSearch": False}, "ok"))
    monkeypatch.setattr(generation_service, "build_generation_inputs", runtime.pop("build_generation_inputs"))
    monkeypatch.setattr(generation_service, "missing_sections", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("section checker unavailable")))
    monkeypatch.setattr(generation_service, "draft_artifact", lambda *args, **kwargs: {
        "company": _inputs().company, "analysisInputs": {}, "dataGaps": {"gaps": []},
        "resolutionAttempts": [], "sourceLedger": [], "depthPolicy": {}, "sources": [],
    })
    monkeypatch.setattr(generation_service, "resolve_company_analysis_gaps", lambda *args, **kwargs: {"gaps": []})
    monkeypatch.setattr(generation_service, "decorate_candidate", lambda _kind, report, **kwargs: report)

    report = generation_service.analyze_company("HWM", runtime=runtime)

    assert report["markdown"] == exact
    assert report["validationStatus"] == "unassessed"
    assert report["validationWarning"]["code"] == "validation_unavailable"


def test_finalize_validator_error_keeps_body_and_marks_unassessed(monkeypatch: pytest.MonkeyPatch):
    exact = "# Keep this body\n\n## 핵심 판단\n\nSECRET-CANARY"

    def fail(*args, **kwargs):
        raise RuntimeError("raw exception must not be copied")

    monkeypatch.setattr("features.company_analysis.finalize.validate_company_report", fail)
    result = finalize_report({"markdown": exact, "generation": {"message": "생성 완료"}})

    assert result["markdown"] == exact
    assert result["validationStatus"] == "unassessed"
    assert result["validationWarning"] == {
        "code": "validation_unavailable",
        "message": "보고서 구조 검증을 완료하지 못했습니다.",
    }
    assert result["contractValidation"]["status"] == "unassessed"
    assert result["quality"]["status"] == "warn"
    assert "validation_unavailable" in result["quality"]["warnings"]
    assert "검수 미완료" in result["generation"]["message"]
    assert "raw exception must not be copied" not in json.dumps(result, ensure_ascii=False)


def test_finalize_ceiling_error_keeps_body_and_marks_unassessed(monkeypatch: pytest.MonkeyPatch):
    exact = "# Exact body"
    monkeypatch.setattr("features.company_analysis.finalize.validate_company_report", lambda *a, **k: {"defects": [], "metrics": {}})
    monkeypatch.setattr("features.company_analysis.finalize.apply_report_ceiling", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("ceiling unavailable")))

    result = finalize_report({"markdown": exact})

    assert result["markdown"] == exact
    assert result["validationStatus"] == "unassessed"
    assert result["quality"]["status"] == "warn"


def test_direct_late_quality_pass_cannot_hide_unassessed_validation():
    report = {
        "markdown": "# body",
        "validationStatus": "unassessed",
        "validationWarning": {"code": "validation_unavailable", "message": "보고서 구조 검증을 완료하지 못했습니다."},
    }

    result = run_direct_analysis(
        query="HWM", web_search_override=None, llm_override=None,
        analysis_style="beginner", quality_mode="diagnose_only",
        generate=lambda *args, **kwargs: dict(report),
        apply_quality=lambda *args, **kwargs: {**report, "quality": {"status": "pass", "warnings": []}},
        apply_ceiling=lambda value: value,
        save=lambda value: {**value, "saved": True},
    )

    assert result["quality"]["status"] == "warn"
    assert "validation_unavailable" in result["quality"]["warnings"]


def test_cli_retry_timeout_writes_back_original_markdown():
    original = _draft(drop=("어떻게 접근할까",))
    pack = {
        "taskType": "company_analysis",
        "artifactType": "company_analysis",
        "artifactId": "HWM_2099-12-31",
        "title": "Howmet 기업 분석",
        "metadata": {"analysisStyle": "beginner"},
        "outputContract": {"format": "markdown", "requiredSections": list(REQUIRED_SECTION_HEADINGS)},
        "draftArtifact": {"company": {"name": "Howmet", "ticker": "HWM"}, "generatedAt": "2099-12-31T00:00:00Z"},
    }
    pack_path = Path("company-preservation-pack.json")
    writeback = Mock(return_value={"id": "hwm-report", "saved": True})
    with (
        patch.object(bridge.agent_service, "prepare_pack", return_value=(pack, pack_path)),
        patch.object(bridge, "_invoke_task_cli", side_effect=[original, TimeoutError("retry timeout")]),
        patch.object(bridge.agent_service, "writeback_pack", writeback),
        patch.object(bridge.schema, "update_pack_status"),
    ):
        result = bridge._run_agent_task_locked(
            "company_analysis",
            {},
            selected={"id": "codex", "executable": "codex", "available": True},
            durable=False,
            progress=lambda *args, **kwargs: None,
            job_id="",
        )

    assert result["artifactId"] == "hwm-report"
    writeback.assert_called_once_with(pack, markdown=original)


def test_cli_retry_no_improvement_writes_back_original_markdown():
    original = _draft(drop=("어떻게 접근할까",))
    pack = {
        "taskType": "company_analysis", "artifactType": "company_analysis",
        "artifactId": "HWM_2099-12-31", "title": "Howmet 기업 분석",
        "outputContract": {"format": "markdown", "requiredSections": list(REQUIRED_SECTION_HEADINGS)},
        "draftArtifact": {"company": {"name": "Howmet", "ticker": "HWM"}, "generatedAt": "2099-12-31T00:00:00Z"},
    }
    writeback = Mock(return_value={"id": "hwm-report", "saved": True})
    with (
        patch.object(bridge.agent_service, "prepare_pack", return_value=(pack, Path("no-gain-pack.json"))),
        patch.object(bridge, "_invoke_task_cli", side_effect=[original, original]),
        patch.object(bridge.agent_service, "writeback_pack", writeback),
        patch.object(bridge.schema, "update_pack_status"),
    ):
        bridge._run_agent_task_locked(
            "company_analysis", {},
            selected={"id": "codex", "executable": "codex", "available": True},
            durable=False, progress=lambda *args, **kwargs: None, job_id="",
        )

    writeback.assert_called_once_with(pack, markdown=original)


def test_cli_initial_structure_check_error_keeps_output_and_marks_pack_unassessed():
    original = _draft(drop=("어떻게 접근할까",))
    pack = {
        "taskType": "company_analysis", "artifactType": "company_analysis",
        "artifactId": "HWM_2099-12-31", "title": "Howmet 기업 분석",
        "outputContract": {"format": "markdown", "requiredSections": list(REQUIRED_SECTION_HEADINGS)},
        "draftArtifact": {"company": {"name": "Howmet", "ticker": "HWM"}, "generatedAt": "2099-12-31T00:00:00Z"},
    }
    writeback = Mock(return_value={"id": "hwm-report", "saved": True})
    with (
        patch.object(bridge.agent_service, "prepare_pack", return_value=(pack, Path("initial-check-pack.json"))),
        patch.object(bridge, "company_missing_sections", side_effect=RuntimeError("section checker unavailable")),
        patch.object(bridge, "_invoke_task_cli", return_value=original),
        patch.object(bridge.agent_service, "writeback_pack", writeback),
        patch.object(bridge.schema, "update_pack_status"),
    ):
        bridge._run_agent_task_locked(
            "company_analysis", {},
            selected={"id": "codex", "executable": "codex", "available": True},
            durable=False, progress=lambda *args, **kwargs: None, job_id="",
        )

    assert pack["draftArtifact"]["validationStatus"] == "unassessed"
    writeback.assert_called_once_with(pack, markdown=original)


def test_cli_cancel_requested_does_not_write_back_original():
    original = _draft(drop=("어떻게 접근할까",))
    pack = {
        "taskType": "company_analysis", "artifactType": "company_analysis",
        "artifactId": "HWM_2099-12-31", "title": "Howmet 기업 분석",
        "outputContract": {"format": "markdown", "requiredSections": list(REQUIRED_SECTION_HEADINGS)},
        "draftArtifact": {"company": {"name": "Howmet", "ticker": "HWM"}, "generatedAt": "2099-12-31T00:00:00Z"},
    }
    writeback = Mock()
    with (
        patch.object(bridge.agent_service, "prepare_pack", return_value=(pack, Path("cancelled-pack.json"))),
        patch.object(bridge, "_invoke_task_cli", side_effect=[original, original]),
        patch.object(bridge, "get_job", return_value={"status": "cancel_requested"}),
        patch.object(bridge.schema, "update_pack_status"),
        patch.object(bridge.agent_service, "writeback_pack", writeback),
    ):
        result = bridge._run_agent_task_locked(
            "company_analysis", {},
            selected={"id": "codex", "executable": "codex", "available": True},
            durable=False, progress=lambda *args, **kwargs: None, job_id="cancelled-job",
        )

    assert result == {"cancelled": True, "artifactType": "company_analysis"}
    writeback.assert_not_called()


def test_actual_company_save_preserves_exact_body_when_validation_is_unassessed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    exact = "# Exact report\n\n## 핵심 판단\n\n저장된 본문"
    monkeypatch.setattr("features.company_analysis.finalize.validate_company_report", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("validator unavailable")))
    monkeypatch.setattr(service, "ANALYSIS_REPORTS_DIR", tmp_path / "company-analysis")
    monkeypatch.setattr(service, "MARKET_MEMORY_DB_PATH", tmp_path / "market-memory.sqlite3")
    pack = {
        "draftArtifact": {
            "company": {"name": "Howmet", "ticker": "HWM"},
            "generatedAt": "2099-12-31T00:00:00Z",
            "headline": "Howmet 기업 분석",
            "sources": [], "depthPolicy": {}, "analysisStyle": "beginner",
        },
        "internal": {"qualityMode": "diagnose_only"},
        "executedAdapter": "codex",
    }
    candidate = agent_service.write_company_analysis_from_markdown(pack, exact, persist=False)
    saved = service.save_analysis_report(candidate)
    stored = json.loads((tmp_path / "company-analysis" / f"{saved['id']}.json").read_text(encoding="utf-8"))

    assert stored["markdown"] == exact
    assert stored["validationStatus"] == "unassessed"
    assert stored["quality"]["status"] == "warn"
    assert stored["saved"] is True


def test_direct_save_failure_returns_bounded_unsaved_report():
    report = {"markdown": "# body", "generation": {"message": "생성 완료"}}

    def fail(_report):
        raise OSError("secret path and credentials")

    result = run_direct_analysis(
        query="HWM", web_search_override=None, llm_override=None,
        analysis_style="beginner", quality_mode="diagnose_only",
        generate=lambda *args, **kwargs: dict(report),
        apply_quality=lambda *args, **kwargs: dict(report),
        apply_ceiling=lambda value: value,
        save=fail,
    )

    assert result["saved"] is False
    assert result["saveError"] == {"code": "save_failed", "message": "보고서를 저장하지 못했습니다."}
    assert "secret path and credentials" not in json.dumps(result, ensure_ascii=False)


def test_direct_save_without_explicit_true_is_not_reported_as_persisted():
    result = run_direct_analysis(
        query="HWM", web_search_override=None, llm_override=None,
        analysis_style="beginner", quality_mode="diagnose_only",
        generate=lambda *args, **kwargs: {"markdown": "# body"},
        apply_quality=lambda *args, **kwargs: {"markdown": "# body"},
        apply_ceiling=lambda value: value,
        save=lambda report: dict(report),
    )

    assert result["saved"] is False


def test_direct_generation_cancellation_is_not_saved():
    save = Mock()

    def cancel(*args, **kwargs):
        raise CancelledError()

    with pytest.raises(CancelledError):
        run_direct_analysis(
            query="HWM", web_search_override=None, llm_override=None,
            analysis_style="beginner", quality_mode="diagnose_only",
            generate=cancel, apply_quality=lambda *args, **kwargs: args[1],
            apply_ceiling=lambda value: value, save=save,
        )

    save.assert_not_called()


def test_cli_retry_cancelled_error_is_not_converted_to_writeback():
    original = _draft(drop=("어떻게 접근할까",))
    pack = {
        "taskType": "company_analysis", "artifactType": "company_analysis",
        "artifactId": "HWM_2099-12-31", "title": "Howmet 기업 분석",
        "outputContract": {"format": "markdown", "requiredSections": list(REQUIRED_SECTION_HEADINGS)},
        "draftArtifact": {"company": {"name": "Howmet", "ticker": "HWM"}, "generatedAt": "2099-12-31T00:00:00Z"},
    }
    with (
        patch.object(bridge.agent_service, "prepare_pack", return_value=(pack, Path("cancelled-error-pack.json"))),
        patch.object(bridge, "_invoke_task_cli", side_effect=[original, CancelledError()]),
        patch.object(bridge.schema, "update_pack_status"),
        patch.object(bridge.agent_service, "writeback_pack") as writeback,
    ):
        with pytest.raises(CancelledError):
            bridge._run_agent_task_locked(
                "company_analysis", {},
                selected={"id": "codex", "executable": "codex", "available": True},
                durable=False, progress=lambda *args, **kwargs: None, job_id="",
            )
    writeback.assert_not_called()
