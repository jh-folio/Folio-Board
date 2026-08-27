"""저장 키는 그 시장의 세션일이다 — durable 경로가 발행일로 덮어쓰지 않는지 못박는다.

02:04(pre-open)에 만든 08-27 세션 브리핑이 `2026-08-28.kr.json`으로 저장됐다(실측).
`write_briefing_from_markdown`은 세션 키를 옳게 계산했는데 producer가 요청 발행일로
도로 덮어썼고, 다음 날 저녁의 진짜 08-28 세션 실행이 그 파일을 덮어쓸 상태였다.
"""
from __future__ import annotations

from pathlib import Path

from features.common.job_briefing_producer import briefing_specs
from features.common.job_json_producer_types import BriefingJobRequest


def _request(report_date: str | None, *, kind: str = "daily") -> BriefingJobRequest:
    report = {"markdown": "# x", "marketScope": "kr"}
    if report_date is not None:
        report["date"] = report_date
    return BriefingJobRequest(
        date="2026-08-28",
        scopes=("kr",),
        reports={"kr": report},
        visuals={"kr": {"snapshots": {"market-heatmap:kr:x": {"rows": []}}}},
        terminal_result={},
        kind=kind,
    )


def test_the_reports_own_session_date_names_the_file():
    specs = briefing_specs(Path("/data"), _request("2026-08-27"))
    report_spec, visual_spec = specs
    assert report_spec.exact_path.name == "2026-08-27.kr.json"
    assert report_spec.artifact_id == "2026-08-27.kr"
    assert report_spec.candidate["date"] == "2026-08-27"
    assert visual_spec.exact_path.name == "2026-08-27.kr.visuals.json.gz"
    assert visual_spec.payload["date"] == "2026-08-27"


def test_a_report_without_a_date_falls_back_to_the_request_date():
    specs = briefing_specs(Path("/data"), _request(None))
    assert specs[0].exact_path.name == "2026-08-28.kr.json"


def test_a_malformed_report_date_falls_back_rather_than_naming_a_file():
    specs = briefing_specs(Path("/data"), _request("bad-date"))
    assert specs[0].exact_path.name == "2026-08-28.kr.json"
    assert specs[0].candidate["date"] == "2026-08-28"


def test_weekly_keeps_the_publication_date_key():
    """주간의 세션 키는 곧 발행일이다 — 보고서 date가 발행일로 실려 오므로 결과가 같다."""
    specs = briefing_specs(Path("/data"), _request("2026-08-28", kind="weekly"))
    assert specs[0].exact_path.name == "2026-08-28.kr.weekly.json"
