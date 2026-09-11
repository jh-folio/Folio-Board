from pathlib import Path
import json

import pytest

from features.daily_briefing import builder
from features.daily_briefing.tests.test_builder import DOCS, _visuals
from features.daily_briefing.finalize import BriefingFinalizationError


def _configure(monkeypatch, tmp_path, bad):
    directory = tmp_path / "briefings"
    directory.mkdir()
    monkeypatch.setattr(builder, "DATA_DIR", tmp_path)
    monkeypatch.setattr(builder, "BRIEFINGS_DIR", directory)
    monkeypatch.setattr(builder, "MARKET_MEMORY_DB_PATH", tmp_path / "memory.sqlite3")
    monkeypatch.setattr(builder, "build_index", lambda **kw: {})
    monkeypatch.setattr(builder, "load_index", lambda: {"documents": DOCS})
    monkeypatch.setattr(builder, "cached_market_snapshot", lambda **kw: {"ok": False})
    monkeypatch.setattr(builder, "cached_korea_market_data", lambda *args: {"ok": False})
    monkeypatch.setattr(builder, "list_briefing_memories", lambda *args, **kw: [])
    monkeypatch.setattr(builder, "load_prev_briefing", lambda *args: None)
    monkeypatch.setattr(builder, "resolve_briefing_by_session", lambda *args: None)
    monkeypatch.setattr(builder, "collect_briefing_visuals", _visuals)
    monkeypatch.setattr(builder, "apply_quality_loop", lambda _kind, report, **kw: report)
    original_single_market_briefing = builder._single_market_briefing
    def fixed_markdown(scope, text):
        label = "미국장" if scope == "us" else "한국장"
        title = "US Market Briefing" if scope == "us" else "Korea Market Briefing"
        company_one = "NVIDIA" if scope == "us" else "삼성전자"
        company_two = "Alphabet" if scope == "us" else "SK하이닉스"
        return "\n\n".join([
            f"# {title} — 2026.06.09 마감",
            f"## 0. 오늘의 {label} 성격",
            f"## 1. {label} 시장 흐름",
            f"## 2. {label}을 움직인 핵심 변수",
            f"## 3. {label}을 주도한 기업 ① — {company_one}",
            f"## 4. {label}을 주도한 기업 ② — {company_two}",
            "## 5. 일반 투자자 관점",
            f"## 6. 다음 {label} 체크포인트",
            "## 오늘의 결론",
            "## Source & Data Notes",
            "**한 줄 결론:** 확인\n" * 7,
            "· 확인 항목\n" * 18,
            f"{text}\n" + "근거 있는 분석 문장 " * 1000,
        ])
    def prepare_candidate(briefing, scope, checkpoints=None):
        candidate = original_single_market_briefing(briefing, scope, checkpoints)
        if scope in {"us", "kr"}:
            candidate = dict(candidate)
            candidate["markdown"] = fixed_markdown(scope,
                (
                    "NVDA -1.48% 하락했다." if bad else "NVDA +1.48% 상승했다."
                ) if scope == "us" else "삼성전자 +1.48% 상승했다."
            )
            if scope == "us":
                candidate["marketSnapshot"] = {"tickers": {"NVDA": {"oneDayPct": 1.48, "asOfDate": "2026-06-09"}}}
            if bad == "unsafe" and scope == "us":
                candidate["sources"] = [{"sourceId": "unsafe", "url": "javascript:alert(1)"}]
        return candidate
    monkeypatch.setattr(builder, "_single_market_briefing", prepare_candidate)
    monkeypatch.setattr(builder, "upsert_memory", lambda *args: pytest.fail("partial run must not project rejected market"))
    return directory


def test_api_final_postprocessing_failure_preserves_normal_file(monkeypatch, tmp_path):
    directory = _configure(monkeypatch, tmp_path, "unsafe")
    old = directory / "2026-06-09.us.json"
    old.write_text('{"markdown":"old normal"}', encoding="utf-8")
    sidecar = directory / "2026-06-09.us.visuals.json.gz"
    sidecar.write_bytes(b"old visual")
    with pytest.raises(BriefingFinalizationError):
        builder.build_briefing("2026-06-10", strict_date=True, llm_override=False, persist=True, market_scope="us")
    assert old.read_text(encoding="utf-8") == '{"markdown":"old normal"}'
    assert sidecar.read_bytes() == b"old visual"


def test_api_valid_market_survives_other_market_final_rejection(monkeypatch, tmp_path):
    directory = _configure(monkeypatch, tmp_path, "unsafe")
    result = builder.build_briefing("2026-06-10", strict_date=True, llm_override=False, persist=True, market_scope="both")
    assert result["includedMarkets"] == ["KR"]
    assert not (directory / "2026-06-09.us.json").exists()
    assert (directory / "2026-06-10.kr.json").exists()
    assert "NVDA -1.48" not in result["markdown"]


def test_api_saves_contradictory_format_valid_prose_verbatim(monkeypatch, tmp_path):
    directory = _configure(monkeypatch, tmp_path, True)
    monkeypatch.setattr(builder, "upsert_memory", lambda *args: None)
    result = builder.build_briefing("2026-06-10", strict_date=True, llm_override=False, persist=True, market_scope="both")
    saved = json.loads((directory / "2026-06-09.us.json").read_text(encoding="utf-8"))
    assert set(result["includedMarkets"]) == {"US", "KR"}
    assert (directory / "2026-06-10.kr.json").exists()
    assert "-1.48%" in saved["markdown"] and "+1.48%" not in saved["markdown"]
    assert saved["finalValidation"]["contentAssessment"] == "not_assessed"
    assert saved["finalValidation"]["contradictionCount"] is None
