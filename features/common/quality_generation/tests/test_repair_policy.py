import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.common.quality_generation import loop as loop_module
from features.common.quality_generation.loop import apply_quality_loop


def test_diagnose_only_does_not_repair():
    artifact = {"markdown": "# Report\n\n요약", "sources": []}
    out = apply_quality_loop("topic_report", artifact, mode="diagnose_only")
    assert out["qualityGeneration"]["repairApplied"] is False
    assert out["markdown"] == artifact["markdown"]


def test_llm_section_improve_does_not_call_llm_for_rule_report():
    artifact = {"markdown": "# Report\n\n요약", "sources": [], "generation": {"mode": "rules"}}
    out = apply_quality_loop("topic_report", artifact, mode="llm_section_improve")
    assert out["qualityGeneration"]["repairApplied"] is False
    assert out["qualityGeneration"]["repairReason"] == "llm_section_rewrite_skipped_non_llm_generation"
    assert len(out.get("sources") or []) == 0
    assert out["qualityGeneration"]["weakSectionsBefore"]


def test_legacy_improve_once_maps_to_llm_section_improve():
    artifact = {"markdown": "# Report\n\n요약", "sources": [], "generation": {"mode": "rules"}}
    out = apply_quality_loop("topic_report", artifact, mode="improve_once")
    assert out["qualityGeneration"]["mode"] == "llm_section_improve"


def test_topic_report_llm_section_improve_skips_above_80_without_calling_llm():
    original_evaluate = loop_module.evaluate_artifact
    original_should = loop_module.should_llm_rewrite
    original_improve = loop_module.improve_sections_with_llm
    original_detect = loop_module.detect_weak_sections
    calls = {"improve": 0}

    def fake_improve(*_args, **_kwargs):
        calls["improve"] += 1
        return {"repairApplied": True, "artifact": {}}

    try:
        loop_module.evaluate_artifact = lambda *_args, **_kwargs: {"score": 81, "status": "warn", "grade": "B"}
        loop_module.should_llm_rewrite = original_should
        loop_module.improve_sections_with_llm = fake_improve
        loop_module.detect_weak_sections = lambda *_args, **_kwargs: [{"section": "source_notes"}]
        artifact = {"markdown": "# Original\n\n본문", "sources": [], "generation": {"mode": "llm"}}
        out = apply_quality_loop("topic_report", artifact, mode="llm_section_improve", preflight={"status": "warn"})
    finally:
        loop_module.evaluate_artifact = original_evaluate
        loop_module.should_llm_rewrite = original_should
        loop_module.improve_sections_with_llm = original_improve
        loop_module.detect_weak_sections = original_detect

    assert calls["improve"] == 0
    assert out["markdown"] == artifact["markdown"]
    assert out["qualityGeneration"]["repairApplied"] is False
    assert out["qualityGeneration"]["repairReason"] == "llm_section_rewrite_skipped_score_above_threshold"


def test_topic_report_llm_section_improve_rejects_quality_regression():
    original_evaluate = loop_module.evaluate_artifact
    original_should = loop_module.should_llm_rewrite
    original_improve = loop_module.improve_sections_with_llm
    original_detect = loop_module.detect_weak_sections

    calls = {"evaluate": 0}

    def fake_evaluate(_artifact_type, _artifact):
        calls["evaluate"] += 1
        if calls["evaluate"] == 1:
            return {"score": 87, "status": "pass", "grade": "A-"}
        return {"score": 85, "status": "pass", "grade": "A-"}

    def fake_improve(_artifact_type, artifact, *_args, **_kwargs):
        return {
            "artifact": {**artifact, "markdown": "# Improved\n\n후보"},
            "repairApplied": True,
            "repairReason": "llm_section_rewrite",
            "changedSections": ["summary"],
            "warnings": [],
        }

    try:
        loop_module.evaluate_artifact = fake_evaluate
        loop_module.should_llm_rewrite = lambda *_args, **_kwargs: True
        loop_module.improve_sections_with_llm = fake_improve
        loop_module.detect_weak_sections = lambda quality, _preflight: [{"section": "x"}] if quality.get("score") < 90 else []
        artifact = {"markdown": "# Original\n\n본문", "sources": [], "generation": {"mode": "llm"}}
        out = apply_quality_loop("topic_report", artifact, mode="llm_section_improve", preflight={"status": "warn"})
    finally:
        loop_module.evaluate_artifact = original_evaluate
        loop_module.should_llm_rewrite = original_should
        loop_module.improve_sections_with_llm = original_improve
        loop_module.detect_weak_sections = original_detect

    qg = out["qualityGeneration"]
    assert out["markdown"] == artifact["markdown"]
    assert qg["repairApplied"] is False
    assert qg["repairAttempted"] is True
    assert qg["repairReason"] == "llm_section_rewrite_quality_regression"
    assert qg["qualityAfter"]["score"] == 87
    assert qg["rejectedQualityAfter"]["score"] == 85


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\n{len(tests)}/{len(tests)} tests passed")
    return True


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
