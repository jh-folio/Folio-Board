"""RSS 수집 실패가 실행 기록에 실패로 남는지.

실측 2026-08-14~24, 열흘 동안 매시 RSS 자동 수집이 서브프로세스 상한(300초)에서
잘려 **한 건도 수집하지 못했는데** 실행 기록은 전부 `done`이었다. 수집 함수가 예외를
통째로 삼키고 이유 없는 한 줄만 남겼고, 호출자는 그 한 줄을 읽지 않았다. 그동안
브리핑·딥리서치는 열흘 전에서 멈춘 자료로 만들어졌다.
"""
from __future__ import annotations

from features.automation import service


def _isolate(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(service, "RUNS_PATH", tmp_path / "automation-runs.json")
    monkeypatch.setattr(service, "promote_kr_rss_leads", lambda _data_dir: 0)


def test_failed_collection_is_recorded_as_failed(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        service,
        "import_rssarchive",
        lambda run_collection=True: {
            "output": "RSS collection timed out after 1800s.",
            "collection": {"ok": False, "error": "timeout"},
            "added": 0,
            "total": 27892,
        },
    )

    outcome = service.run_automation_once("rss")

    assert outcome["status"] == "failed"
    assert service.list_runs(1)[0]["status"] == "failed"


def test_successful_collection_still_reports_done(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        service,
        "import_rssarchive",
        lambda run_collection=True: {
            "output": "RSS collection finished. Added 12, total 27904.",
            "collection": {"ok": True, "error": ""},
            "added": 12,
            "total": 27904,
        },
    )

    assert service.run_automation_once("rss")["status"] == "done"


def test_result_without_collection_field_stays_done(tmp_path, monkeypatch):
    # 워크스페이스 이동 중 건너뛴 결과처럼 이 필드가 없는 응답을 실패로 읽지 않는다.
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        service,
        "import_rssarchive",
        lambda run_collection=True: {"output": "skipped", "skipped": "workspace_moved", "added": 0},
    )

    assert service.run_automation_once("rss")["status"] == "done"
