"""딥 리서치 재개 체크포인트.

값비싼 것은 쓰기가 아니라 그 앞이다(웹 조회·축 브리프·논지). 사용량 한도로 끊긴 실행이
다시 돌 때 그 셋을 다시 태우지 않는지, 그리고 **이어 쓰면 안 되는 경우**(다른 계획·다른
근거·유효기간 초과)를 확실히 버리는지 본다.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from features.agent_mode.bridge import rate_limit_hint
from features.topic_report.axis_analysis import build_axis_briefs
from features.topic_report import resume_store


def _store(tmp_path, fingerprint: str = "fp1"):
    return resume_store.ResumeStore(tmp_path, key="2026-09-02_abc123def456", fingerprint=fingerprint)


def test_resume_key_matches_artifact_id_shape():
    assert resume_store.resume_key("2026-09-02", "abc123def4567890") == "2026-09-02_abc123def456"


def test_resume_key_rejects_unsafe_input():
    assert resume_store.resume_key("../..", "abc") == ""


def test_stages_round_trip(tmp_path):
    store = _store(tmp_path)
    store.put_web_lookup({"axisKey": "rates", "status": "ok", "facts": [{"statement": "x"}]})
    store.put_axis_brief({"axisKey": "rates", "status": "ok", "findings": ["y"]})
    store.put_thesis({"claim": "z"})

    reopened = _store(tmp_path)
    assert [row["axisKey"] for row in reopened.web_lookups()] == ["rates"]
    assert [row["axisKey"] for row in reopened.axis_briefs()] == ["rates"]
    assert reopened.thesis() == {"claim": "z"}


def test_same_axis_is_replaced_not_duplicated(tmp_path):
    store = _store(tmp_path)
    store.put_axis_brief({"axisKey": "rates", "status": "ok", "findings": ["old"]})
    store.put_axis_brief({"axisKey": "rates", "status": "ok", "findings": ["new"]})
    assert [row["findings"] for row in _store(tmp_path).axis_briefs()] == [["new"]]


def test_failed_axis_brief_is_not_saved(tmp_path):
    """성공한 것만 남긴다. 실패한 축은 다음 실행이 다시 시도해야 한다."""
    store = _store(tmp_path)
    store.put_axis_brief({"axisKey": "rates", "status": "unavailable", "findings": []})
    store.put_axis_brief({"axisKey": "fx", "status": "empty", "findings": []})
    assert _store(tmp_path).axis_briefs() == []


def test_different_fingerprint_is_ignored(tmp_path):
    """근거나 계획이 달라지면 이어 쓰지 않는다 — 어제 브리프로 오늘을 말하게 된다."""
    _store(tmp_path, "fp1").put_thesis({"claim": "z"})
    assert _store(tmp_path, "fp2").thesis() == {}


def test_expired_checkpoint_is_ignored(tmp_path, monkeypatch):
    store = _store(tmp_path)
    store.put_thesis({"claim": "z"})
    path = tmp_path / "2026-09-02_abc123def456.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["updatedAt"] = (datetime.now(UTC) - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert _store(tmp_path).thesis() == {}


def test_disabled_store_never_touches_disk(tmp_path):
    store = resume_store.ResumeStore(tmp_path, key="", fingerprint="")
    store.put_thesis({"claim": "z"})
    assert store.thesis() == {}
    assert list(tmp_path.glob("*.json")) == []


def test_clear_removes_checkpoint(tmp_path):
    store = _store(tmp_path)
    store.put_thesis({"claim": "z"})
    store.clear()
    assert _store(tmp_path).thesis() == {}


def test_prune_removes_expired_only(tmp_path):
    fresh = _store(tmp_path)
    fresh.put_thesis({"claim": "z"})
    stale = tmp_path / "2026-01-01_old000000000.json"
    stale.write_text(json.dumps({"updatedAt": "2020-01-01T00:00:00Z"}), encoding="utf-8")
    assert resume_store.prune(tmp_path) == 1
    assert not stale.exists()
    assert _store(tmp_path).thesis() == {"claim": "z"}


def test_fingerprint_changes_with_evidence_selection():
    common = {
        "plan_hash": "h",
        "as_of_date": "2026-09-02",
        "adapter": "claude",
        "requested_mode": "cli",
    }
    first = resume_store.fingerprint(selected_evidence_ids=["a", "b"], **common)
    second = resume_store.fingerprint(selected_evidence_ids=["a", "c"], **common)
    assert first != second


PLAN = {
    "topic": "질문",
    "analysisAxes": [
        {"key": "rates", "label": "금리", "questions": ["q1"]},
        {"key": "fx", "label": "환율", "questions": ["q2"]},
    ],
    "deepResearch": {"subQuestions": []},
}


def test_existing_briefs_skip_the_call():
    """이미 만든 축은 어댑터를 다시 부르지 않는다 — 재개의 핵심."""
    called: list[str] = []

    def run_call(prompt: str, context: str) -> str:
        called.append(context[:20])
        return json.dumps({"findings": ["새 발견"], "sourceIds": []})

    briefs = build_axis_briefs(
        PLAN,
        [],
        run_call=run_call,
        existing=[{"axisKey": "rates", "status": "ok", "findings": ["예전 발견"], "label": "금리"}],
    )
    assert len(called) == 1
    by_axis = {row["axisKey"]: row for row in briefs}
    assert by_axis["rates"]["findings"] == ["예전 발견"]
    assert by_axis["fx"]["findings"] == ["새 발견"]


def test_on_brief_fires_only_for_successful_axes():
    saved: list[dict] = []

    calls = {"n": 0}

    def run_call(prompt: str, context: str) -> str:
        # 컨텍스트에는 축 목록 전체가 실리므로 라벨로는 어느 축인지 가릴 수 없다.
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("사용량 한도")
        return json.dumps({"findings": ["발견"], "sourceIds": []})

    build_axis_briefs(PLAN, [], run_call=run_call, on_brief=saved.append)
    assert [row["axisKey"] for row in saved] == ["rates"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("You've hit your session limit · resets 9pm (Asia/Seoul)", "resets 9pm (Asia/Seoul)"),
        ('{"error":"rate_limit","status":429}', ""),
        ("Agent CLI가 죽었습니다: ENOENT", None),
        ("", None),
    ],
)
def test_rate_limit_hint(text, expected):
    """한도는 코드 결함과 대처가 다르다. 표지를 못 잡으면 잡에 그 사실이 안 남는다."""
    assert rate_limit_hint(text) == expected


# --- 생성 경로 통합 -----------------------------------------------------------
# 위 단위 테스트는 저장소만 본다. 여기서는 `build_approved_report()`가 실제로 이어받는지,
# 그리고 사용량 한도가 잡에 그 이름으로 남는지를 본다.

from pathlib import Path  # noqa: E402

from features.topic_report import approved_generation as generation  # noqa: E402
from features.topic_report.approved_generation_support import EngineFailedError  # noqa: E402
from features.topic_report.tests.test_approved_generation import (  # noqa: E402
    NOW,
    fake_materials,
    prepared_input,
)


def _axis_payload() -> str:
    return json.dumps({
        "concept": ["개념"],
        "mechanism": ["경로"],
        "findings": ["발견"],
        "numbers": [],
        "counterEvidence": [],
        "sourceIds": [],
    })


def _rate_limited_cli(*_args, **_kwargs):
    raise EngineFailedError("cli_rate_limited")


def test_a_rate_limited_run_keeps_its_axis_briefs_and_names_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """한도로 초안이 죽어도 앞 단계는 남는다. 예전에는 11분치가 통째로 사라졌다."""
    monkeypatch.setattr(generation, "resume_root", lambda: tmp_path / "resume")
    monkeypatch.setattr(generation, "_materials", fake_materials)
    monkeypatch.setattr(generation, "_read_prompt", lambda: "Approved prompt")
    monkeypatch.setattr(generation, "attempt_cli", _rate_limited_cli)
    monkeypatch.setattr(
        generation, "configured_axis_call", lambda *a, **k: (lambda _p, _c: _axis_payload())
    )

    outcome = generation.build_approved_report(
        prepared_input(tmp_path, "cli"), job_id="job-rate-limited", clock=lambda: NOW
    )

    # 규칙으로 떨어졌지만 이유가 "일반 실패"가 아니라 "한도"로 남는다.
    assert outcome.finalEngine == "rules"
    assert outcome.fallbackReason == "engine_rate_limited"
    saved = list((tmp_path / "resume").glob("*.json"))
    assert len(saved) == 1
    stages = json.loads(saved[0].read_text(encoding="utf-8"))["stages"]
    assert stages["axisBriefs"], "축 브리프가 남아야 다음 실행이 이어받는다"


def test_the_next_run_does_not_pay_for_the_axes_it_already_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(generation, "resume_root", lambda: tmp_path / "resume")
    monkeypatch.setattr(generation, "_materials", fake_materials)
    monkeypatch.setattr(generation, "_read_prompt", lambda: "Approved prompt")
    monkeypatch.setattr(generation, "attempt_cli", _rate_limited_cli)

    calls = {"n": 0}

    def axis_call(*_args, **_kwargs):
        def run(_prompt, _context):
            calls["n"] += 1
            return _axis_payload()

        return run

    monkeypatch.setattr(generation, "configured_axis_call", axis_call)
    command = prepared_input(tmp_path, "cli")
    resumed: list[str] = []
    monkeypatch.setattr(generation, "diagnostic_resume", resumed.append)

    generation.build_approved_report(command, job_id="job-first", clock=lambda: NOW)
    first = calls["n"]
    assert first > 0
    assert resumed == []  # enabled storage is not itself a diagnostic resume.

    calls["n"] = 0
    outcome = generation.build_approved_report(command, job_id="job-second", clock=lambda: NOW)

    # 축 브리프는 전부 재사용된다. 남은 호출은 논지 선정뿐이다.
    assert calls["n"] < first
    # 재사용한 브리프가 실제로 보고서에 실린다(호출만 아끼고 내용이 비면 의미가 없다).
    summary = outcome.report["axisAnalysis"]
    assert summary and summary["okCount"] == summary["axisCount"] > 0
    assert resumed == ["context"], "only actual cached axis consumption emits resume"


def test_a_different_evidence_selection_is_not_resumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """근거가 바뀌면 이어 쓰지 않는다 — 어제 자료로 오늘을 말하게 된다."""
    monkeypatch.setattr(generation, "resume_root", lambda: tmp_path / "resume")
    monkeypatch.setattr(generation, "_materials", fake_materials)
    monkeypatch.setattr(generation, "_read_prompt", lambda: "Approved prompt")
    monkeypatch.setattr(generation, "attempt_cli", _rate_limited_cli)

    calls = {"n": 0}

    def axis_call(*_args, **_kwargs):
        def run(_prompt, _context):
            calls["n"] += 1
            return _axis_payload()

        return run

    monkeypatch.setattr(generation, "configured_axis_call", axis_call)
    command = prepared_input(tmp_path, "cli")
    generation.build_approved_report(command, job_id="job-a", clock=lambda: NOW)
    first = calls["n"]

    # 같은 계획·같은 날짜지만 다른 어댑터로 실행하면 지문이 달라 처음부터 만든다.
    other = generation.ApprovedGenerationInput(
        approved=command.approved,
        approvalId=command.approvalId,
        requestedMode=command.requestedMode,
        adapter="claude",
        preview=command.preview,
        research=command.research,
        marketState=command.marketState,
    )
    calls["n"] = 0
    generation.build_approved_report(other, job_id="job-b", clock=lambda: NOW)
    assert calls["n"] == first
