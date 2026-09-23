"""Research Quality common evaluator tests.

    py -3 features/common/research_quality/tests/test_research_quality.py
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.common.research_quality.evaluator import evaluate_artifact, evaluate_report


GOOD = """# 리포트

## Executive Summary
현재 판단: 자료 기반으로 중립.

## 질문 정의와 분석 범위
포함 범위와 제외 범위.

## 핵심 데이터
S&P 500 1.2%, 금리 4.5%, 환율 1350, 유가 70.

## 반론과 리스크
이 판단이 틀릴 수 있는 조건.

## 시나리오
금리 4.7%를 상회하면 위험.

## 앞으로 확인할 체크포인트
- 금리 4.7% 상회 여부

## Source & Data Notes
로컬 자료와 marketTape 기반. 일부 추정.
"""


def test_evaluate_report_has_step7_fields():
    q = evaluate_report(
        GOOD,
        evidence_summary={"totalDocs": 8, "roleCounts": {"challenging": 1}, "axisCoverage": {}},
        checkpoints=[{"checkpoint": "금리"}],
        source_ledger=[{"title": "A", "source": "Reuters"}],
        evidence_items=[{"title": "A", "type": "news"}],
        market_tape={"items": [{"status": "fresh"}]},
    )
    assert q["status"] in {"pass", "warn", "fail"}
    assert q["sourceGrounding"] in {"high", "medium", "low", "none"}
    assert "source_grounding" in q["checks"]
    assert q["hallucinationRisk"] in {"low", "medium", "high"}


def test_user_note_not_counted_for_grounding():
    q = evaluate_report(
        "# Memo\n\n## 결론\n수치 1 2 3 4 5 6 7 8 9 10",
        evidence_items=[{"title": "내 노트", "type": "user_note"}],
        source_ledger=[],
        artifact_type="personal_overlay",
        user_context_present=True,
    )
    detail = q["sourceGroundingDetail"]
    assert detail["evidenceCount"] == 0
    assert q["personalBiasRisk"] == "elevated"


def test_briefing_artifact_adapter_uses_structured_fields():
    q = evaluate_artifact("briefing", {
        "markdown": GOOD,
        "sources": [{"title": "A"}],
        "stats": {"sourceCount": 5},
        "checkpoints": [{"checkpoint": "금리"}],
        "sourceLedger": [{"title": "A"}],
        "marketTape": {"items": [{"status": "fresh"}]},
    })
    assert q["artifactType"] == "briefing"
    assert q["checkpointQuality"] in {"high", "medium"}


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"PASS {t.__name__}")
    print(f"\n{passed}/{len(tests)} tests passed")
    return passed == len(tests)


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)


def test_recheck_persists_through_the_canonical_pipeline(tmp_path, monkeypatch):
    """재평가 저장이 canonicalRevision 지문을 깨뜨리면 안 된다.

    quality는 지문 계산에 포함되는 필드라, 예전처럼 파일을 직접 덮어쓰면 지문이
    어긋나 그 보고서의 재생성·Personal Overlay가 영구히 실패했다
    (실측: data/briefings/2026-08-04.kr.json). 저장 후에도 정식 배관의 다음
    커밋이 성공해야 한다.
    """
    import json

    from features.common import research_quality
    from features.common.canonical_identity import ReportKind
    from features.common.canonical_report_state import revision
    from features.common.canonical_report_types import WriteKind
    from features.common.canonical_reports import commit_sync, prepare
    from features.common.research_quality import service as svc

    briefings = tmp_path / "briefings"
    briefings.mkdir()
    path = briefings / "2099-01-05.us.json"
    commit_sync(prepare(
        report_kind=ReportKind.BRIEFING,
        exact_path=path,
        write_kind=WriteKind.CANONICAL,
        candidate={"date": "2099-01-05", "marketScope": "us", "markdown": "# 본문"},
    ))
    monkeypatch.setattr(svc, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        svc, "load_artifact", lambda _type, _id: json.loads(path.read_text(encoding="utf-8"))
    )

    result = svc.recheck_quality("briefing", "2099-01-05.us")

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert result["saved"] is True
    assert saved["quality"] == result["quality"]
    assert revision(saved) is not None  # 지문 검증이 예외 없이 통과해야 한다

    # 지문이 멀쩡하므로 이후의 정식 커밋(재생성·overlay에 해당)이 계속 성공한다.
    commit_sync(prepare(
        report_kind=ReportKind.BRIEFING,
        exact_path=path,
        write_kind=WriteKind.CANONICAL,
        candidate={"date": "2099-01-05", "marketScope": "us", "markdown": "# 본문 v2"},
    ))
    regenerated = json.loads(path.read_text(encoding="utf-8"))
    assert regenerated["markdown"] == "# 본문 v2"


def test_not_executed_questions_do_not_zero_the_coverage_score():
    """round 1이 충분해 건너뛴 질문은 결측이지 0점이 아니다 — 0으로 세면 커버리지가
    가장 좋았던 실행일수록 점수가 깎인다."""
    from features.common.research_quality.evaluator import evaluate_report

    def run(question_coverage):
        return evaluate_report(
            "## 본문 내용",
            evidence_summary={
                "deepResearch": {"enabled": True},
                "questionCoverage": question_coverage,
            },
        )["checks"]["deep_question_coverage"]

    covered = run({
        "q1": {"level": "high", "question": "a"},
        "q2": {"level": "not_executed", "question": "b", "executed": False},
    })
    only_high = run({"q1": {"level": "high", "question": "a"}})
    assert covered == only_high


def test_artifact_lookup_ids_cannot_leave_the_report_folder(tmp_path, monkeypatch):
    import json

    from features.common.research_quality import service as quality_svc
    from features.common.research_schema import service as schema_svc

    briefings = tmp_path / "briefings"
    briefings.mkdir()
    (briefings / "2099-01-05.us.json").write_text(json.dumps({"date": "2099-01-05"}), encoding="utf-8")
    (tmp_path / "portfolio.json").write_text(json.dumps({"positions": ["private"]}), encoding="utf-8")
    monkeypatch.setattr(quality_svc, "DATA_DIR", tmp_path)
    monkeypatch.setattr(schema_svc, "DATA_DIR", tmp_path)

    for hostile in ("../portfolio", "..\\portfolio"):
        assert quality_svc._artifact_json_path("briefing", hostile) is None
        assert schema_svc._find_json_report(briefings, hostile) is None
    assert quality_svc._artifact_json_path("briefing", "2099-01-05.us").name == "2099-01-05.us.json"
    assert schema_svc._find_json_report(briefings, "2099-01-05.us") == {"date": "2099-01-05"}
