import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.daily_briefing import builder


def _scope_result(scope):
    market = scope.upper()
    return {
        "markdown": f"# {'US' if scope == 'us' else 'Korea'} Market Briefing\n\n{scope} body",
        "sessionMode": f"{scope}_close",
        "marketSessionDate": "2026-06-19",
        "sources": [],
        "generation": {"mode": "rules", "status": "ok", "provider": "fixture"},
        "status": "ok",
        "headlines": [],
        "groups": [],
        "issueCoverageRaw": [],
        "issueCoverage": [],
        "marketDrivers": [{"market": scope, "driver": f"{scope} driver", "score": 1, "docs": []}],
        "documents": [],
    }


def _build_patches(visuals):
    return [
        patch.object(builder, "build_index"),
        patch.object(builder, "load_index", return_value={"documents": []}),
        patch.object(builder, "select_briefing_docs", return_value=([], "2026-06-19", {"sourceDates": ["2026-06-19"]})),
        patch.object(builder, "cached_market_snapshot", return_value={"ok": True}),
        patch.object(builder, "cached_korea_market_data", return_value={"ok": True}),
        patch.object(builder, "build_market_tape", return_value={}),
        patch.object(builder, "preflight_from_context", return_value={}),
        patch.object(builder, "list_briefing_memories", return_value=[]),
        patch.object(builder, "load_prev_briefing", return_value=None),
        patch.object(builder, "_scope_result", side_effect=lambda scope, *args, **kwargs: _scope_result(scope)),
        patch.object(builder, "leading_company_subjects_from_markdown", return_value=[]),
        patch.object(builder, "collect_briefing_visuals", return_value=visuals),
        patch.object(builder, "session_doc_counts", return_value={}),
        patch.object(builder, "checkpoints_from_markdown", return_value=[]),
        patch.object(builder, "data_gaps_from_messages", return_value=[]),
        patch.object(builder, "read_briefing_prompt", return_value="prompt"),
        patch.object(builder, "apply_quality_loop", side_effect=lambda kind, payload, **kwargs: payload),
        patch.object(builder, "build_memory_from_briefing", return_value=[]),
    ]


def test_single_market_briefing_tags_generation_scope():
    combined = {
        "marketScope": "both",
        "markdown": "# US Market Briefing\n\nbody\n\n---\n\n# Korea Market Briefing\n\nbody",
        "briefings": {
            "us": {"markdown": "# US Market Briefing\n\nbody"},
            "kr": {"markdown": "# Korea Market Briefing\n\nbody"},
        },
    }
    us = builder._single_market_briefing(combined, "us")
    assert us["marketScope"] == "us"
    assert us.get("generationScope") == "both"

    single = {"marketScope": "us", "markdown": "# US Market Briefing\n\nbody"}
    solo = builder._single_market_briefing(single, "us")
    assert solo.get("generationScope") == "us"


def test_build_briefing_persists_per_market_reports_and_sidecars():
    sidecar = {
        "date": "2026-06-20",
        "snapshots": {
            "us-heat": {"id": "us-heat", "market": "US", "rows": [{"ticker": "NVDA", "marketCap": 1}]},
            "kr-heat": {"id": "kr-heat", "market": "KR", "rows": [{"ticker": "005930", "marketCap": 1}]},
        },
    }
    visuals = {
        "visualRecommendations": [
            {"id": "us-rec", "snapshotId": "us-heat", "market": "US"},
            {"id": "kr-rec", "snapshotId": "kr-heat", "market": "KR"},
        ],
        "visualSnapshots": [
            {"id": "us-heat", "type": "market_heatmap", "market": "US"},
            {"id": "kr-heat", "type": "market_heatmap", "market": "KR"},
        ],
        "sidecar": sidecar,
        "warnings": [],
    }
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        patches = [patch.object(builder, "BRIEFINGS_DIR", root), *_build_patches(visuals)]
        for item in patches:
            item.start()
        try:
            result = builder.build_briefing("2026-06-20", persist=True, market_scope="both", llm_override=False)
        finally:
            for item in reversed(patches):
                item.stop()

        assert result["marketScope"] == "both"
        assert (root / "2026-06-20.us.json").exists()
        assert (root / "2026-06-20.kr.json").exists()
        assert not (root / "2026-06-20.json").exists()

        us = json.loads((root / "2026-06-20.us.json").read_text(encoding="utf-8"))
        kr = json.loads((root / "2026-06-20.kr.json").read_text(encoding="utf-8"))
        assert us["marketScope"] == "us" and "us body" in us["markdown"]
        assert kr["marketScope"] == "kr" and "kr body" in kr["markdown"]
        assert [row["market"] for row in us["visualSnapshots"]] == ["US"]
        assert [row["market"] for row in kr["visualSnapshots"]] == ["KR"]
        assert (root / "2026-06-20.us.visuals.json.gz").exists()
        assert (root / "2026-06-20.kr.visuals.json.gz").exists()

        # 연결 분석은 제거됐다. 통합 생성이 더 이상 사이드카를 만들지 않는다.
        assert not (root / "2026-06-20.link.json").exists()


def test_single_market_regeneration_preserves_sibling_and_marks_overlay_stale():
    date = "2026-06-21"
    visuals = {
        "visualRecommendations": [{"id": "us-rec", "snapshotId": "us-heat", "market": "US"}],
        "visualSnapshots": [{"id": "us-heat", "type": "market_heatmap", "market": "US"}],
        "sidecar": {
            "date": date,
            "snapshots": {
                "us-heat": {"id": "us-heat", "market": "US", "rows": [{"ticker": "NVDA"}]},
            },
        },
        "warnings": [],
    }
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        us_path = root / f"{date}.us.json"
        kr_path = root / f"{date}.kr.json"
        us_path.write_text(json.dumps({
            "date": date,
            "marketScope": "us",
            "markdown": "old us",
            "personalOverlay": {"enabled": True, "stale": False},
        }), encoding="utf-8")
        kr_path.write_text(json.dumps({
            "date": date,
            "marketScope": "kr",
            "markdown": "old kr sibling",
        }), encoding="utf-8")
        sibling_before = kr_path.read_bytes()

        patches = [patch.object(builder, "BRIEFINGS_DIR", root), *_build_patches(visuals)]
        for item in patches:
            item.start()
        try:
            result = builder.build_briefing(date, persist=True, market_scope="us", llm_override=False)
        finally:
            for item in reversed(patches):
                item.stop()

        saved = json.loads(us_path.read_text(encoding="utf-8"))
        assert result["marketScope"] == "us"
        assert saved["markdown"].startswith("# US Market Briefing")
        assert saved["personalOverlay"]["stale"] is True
        assert kr_path.read_bytes() == sibling_before
        assert not (root / f"{date}.kr.visuals.json.gz").exists()


def test_projection_follows_the_report_store_not_the_real_data_dir(tmp_path):
    """테스트 픽스처가 사용자 DB에 변화 이벤트를 남기면 대시보드에 가짜 알림이 뜬다."""
    from features.common.change_intelligence.service import projection_db_for_report
    from features.daily_briefing import builder

    default_db = builder.MARKET_MEMORY_DB_PATH
    # 임시 저장소로 커밋하면 projection도 그 안에 머문다.
    temp_report = tmp_path / "briefings" / "2026-06-10.us.json"
    assert projection_db_for_report(temp_report, default_db) == tmp_path / default_db.name
    # 실제 경로에서는 기존 DB를 그대로 쓴다.
    real_report = builder.BRIEFINGS_DIR / "2026-08-01.us.json"
    assert projection_db_for_report(real_report, default_db) == default_db


def _weekly_scope_result(scope):
    label = {"us": "US", "kr": "Korea", "europe": "Europe", "jp": "Japan"}[scope]
    return {
        **_scope_result(scope),
        "kind": "weekly",
        "markdown": f"# {label} Market Briefing 주간 — 08.17~08.23\n\n{scope} weekly body",
        "sessionMode": "",
        "marketSessionDate": "2026-08-23",
    }


def test_a_weekly_briefing_never_overwrites_that_week_s_daily_report():
    """**이번 릴리즈에서 가장 위험했던 충돌.**

    일요일(08-23) 실행의 세션일은 금요일(08-21)이다. 종류 접미사가 없으면 주간
    보고서가 그 주 금요일 일간 브리핑 파일로 떨어져 통째로 덮어쓴다.
    """
    visuals = {"visualRecommendations": [], "visualSnapshots": [], "sidecar": {}, "warnings": []}
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        # 그 주 금요일 일간 브리핑이 이미 저장돼 있다.
        (root / "2026-08-21.us.json").write_text(
            json.dumps({"date": "2026-08-21", "marketScope": "us", "markdown": "# 금요일 일간"}),
            encoding="utf-8",
        )
        patches = [
            patch.object(builder, "BRIEFINGS_DIR", root),
            *_build_patches(visuals),
        ]
        # 세션일이 금요일로 떨어지는 상황을 그대로 재현한다.
        patches.append(patch.object(builder, "_scope_session_date", return_value="2026-08-21"))
        patches.append(
            patch.object(builder, "_scope_result", side_effect=lambda scope, *a, **k: _weekly_scope_result(scope))
        )
        for item in patches:
            item.start()
        try:
            result = builder.build_briefing(
                "2026-08-23", persist=True, markets=["us"], kind="weekly", llm_override=False,
            )
        finally:
            for item in reversed(patches):
                item.stop()

        assert result["kind"] == "weekly"
        assert result["weekStart"] == "2026-08-17" and result["weekEnd"] == "2026-08-23"
        # 발행일 + 종류 접미사로 저장된다. 세션일 파일이 아니다.
        assert (root / "2026-08-23.us.weekly.json").exists()
        assert not (root / "2026-08-21.us.weekly.json").exists()
        # 금요일 일간 브리핑은 그대로다.
        friday = json.loads((root / "2026-08-21.us.json").read_text(encoding="utf-8"))
        assert friday["markdown"] == "# 금요일 일간"

        weekly = json.loads((root / "2026-08-23.us.weekly.json").read_text(encoding="utf-8"))
        assert weekly["kind"] == "weekly"
        assert weekly["date"] == "2026-08-23"
        assert weekly["markdown"].startswith("# US Market Briefing 주간 — 08.17~08.23")
        # 단일 시장 저장본은 `_single_market_briefing`이 섹션을 비우고 최상위로 올린다.
        assert weekly["title"] == "US Market Briefing 주간 — 08.17~08.23"


def test_a_weekly_briefing_does_not_accumulate_market_memory():
    """같은 이슈를 일간이 이미 그 주에 넣었다. 다시 넣으면 근거 카운트가 부푼다."""
    visuals = {"visualRecommendations": [], "visualSnapshots": [], "sidecar": {}, "warnings": []}
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        saved = []
        patches = [
            patch.object(builder, "BRIEFINGS_DIR", root),
            *_build_patches(visuals),
            patch.object(builder, "upsert_memory", side_effect=lambda *a, **k: saved.append(a)),
            patch.object(builder, "build_memory_from_briefing", return_value=[{"id": "m1"}]),
            patch.object(builder, "_scope_result", side_effect=lambda scope, *a, **k: _weekly_scope_result(scope)),
        ]
        for item in patches:
            item.start()
        try:
            builder.build_briefing(
                "2026-08-23", persist=True, markets=["us", "kr"], kind="weekly", llm_override=False,
            )
        finally:
            for item in reversed(patches):
                item.stop()

        assert saved == []
