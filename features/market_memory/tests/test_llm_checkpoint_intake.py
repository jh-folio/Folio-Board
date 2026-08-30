"""LLM 시장 메모리 업데이트가 구조화 체크포인트를 내는 경로.

    py -3 -m pytest features/market_memory/tests/test_llm_checkpoint_intake.py -q

네트워크와 실제 워크스페이스를 건드리지 않는다 — 임시 SQLite와 순수 함수뿐이다.
"""
import json
import os
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.market_memory import memory as M
from features.market_memory import service as S

CHECKPOINT = {
    "item": "전력 설비 기업 실적 가이던스 상향",
    "direction": "supporting",
    "matchers": {"tickers": ["GEV"], "keywords": ["가이던스 상향"]},
}


def _entry(**overrides):
    base = {
        "date": "2026-08-30",
        "title": "AI 데이터센터 전력 병목이 이어진다",
        "summary": "전력기기 수주가 늘고 있다.",
        "story": "ai_power",
        "storyFamily": "AI 데이터센터 전력 병목",
        "stateKey": "ai_power",
        "stateLabel": "AI 데이터센터 전력 병목",
        "importance": "high",
        "entryMode": "issue",
        "sources": [
            {"title": "t1", "source": "s1", "date": "2026-08-30", "url": "u1"},
            {"title": "t2", "source": "s2", "date": "2026-08-30", "url": "u2"},
        ],
        "nextCheckpoints": [dict(CHECKPOINT)],
    }
    base.update(overrides)
    return base


# --- 엔트리 정규화 -------------------------------------------------------

def test_llm_checkpoint_inputs_keeps_only_generation_keys():
    """LLM은 status·createdAt·lastVerdict·history를 낼 수 없다.

    받으면 "이미 확인됨"으로 태어나는 체크포인트가 생긴다. validator의
    `trusted=False`가 한 번 더 막지만, 입력 모양에서부터 그 네 키를 들이지 않는다.
    """
    out = S.llm_checkpoint_inputs([
        {
            **CHECKPOINT,
            "id": "cp_forged",
            "status": "confirmed",
            "createdAt": "2020-01-01T00:00:00+00:00",
            "lastVerdict": {"verdict": "confirmed", "at": "2020-01-01T00:00:00+00:00"},
            "history": [{"at": "x", "from": "open", "to": "confirmed", "verdict": "confirmed"}],
        }
    ])
    assert out == [{
        "item": "전력 설비 기업 실적 가이던스 상향",
        "direction": "supporting",
        "matchers": {"tickers": ["GEV"], "keywords": ["가이던스 상향"]},
        "dueBy": None,
    }]


def test_llm_checkpoint_inputs_caps_at_three_and_skips_non_objects():
    out = S.llm_checkpoint_inputs(["문장", None, *[dict(CHECKPOINT, item=f"항목 {i}") for i in range(5)]])
    assert len(out) == S.MAX_ENTRY_CHECKPOINTS
    out2 = S.llm_checkpoint_inputs("not a list")
    assert out2 == []


def test_normalize_entry_carries_checkpoints():
    entry, reason = S.normalize_llm_memory_entry(
        {
            "title": "AI 데이터센터 전력 병목",
            "summary": "전력기기 수주가 늘고 있다.",
            "story": "ai_power",
            "nextCheckpoints": [{**CHECKPOINT, "status": "confirmed"}],
        },
        "2026-08-30",
        [],
    )
    assert reason == ""
    assert entry["nextCheckpoints"] == [{
        "item": CHECKPOINT["item"],
        "direction": "supporting",
        "matchers": {"tickers": ["GEV"], "keywords": ["가이던스 상향"]},
        "dueBy": None,
    }]
    # 자유 문장은 그대로 병존한다 — 구조화가 그것을 대체하지 않는다.
    assert entry["storyCheckpoint"]


# --- 상태 병합 -----------------------------------------------------------

def _states(db_path):
    conn = M.connect(db_path)
    rows = conn.execute("SELECT state_id, state_key, status, next_checkpoints_json FROM market_narrative_states").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def test_save_memory_entries_merges_checkpoints_into_the_state():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        out = S.save_memory_entries([_entry()], db_path=db_path)
        assert out["checkpointsMerged"] == 1
        assert out["checkpointsDropped"] == 0
        states = _states(db_path)
        assert len(states) == 1
        stored = json.loads(states[0]["next_checkpoints_json"])
        structured = [c for c in stored if isinstance(c, dict)]
        assert len(structured) == 1
        assert structured[0]["item"] == CHECKPOINT["item"]
        # 서버가 찍는 값 — LLM이 뭘 보냈든 open으로 태어난다.
        assert structured[0]["status"] == "open"
        assert structured[0]["lastVerdict"] is None
        assert structured[0]["history"] == []


def test_checkpoints_of_a_memo_that_did_not_become_a_state_are_dropped_and_counted():
    """체크포인트는 상태의 소유물이다 — 상태로 승격되지 않으면 갈 곳이 없다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        thin = _entry(importance="low", sources=[{"title": "t", "source": "s", "date": "2026-08-30", "url": "u"}])
        out = S.save_memory_entries([thin], db_path=db_path)
        assert out["saved"] and "state" not in out["saved"][0]
        assert out["checkpointsMerged"] == 0
        assert out["checkpointsDropped"] == 1
        assert _states(db_path) == []


def test_invalid_checkpoints_are_counted_as_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        entry = _entry(nextCheckpoints=[
            dict(CHECKPOINT),
            {"item": "방향이 없다", "direction": "긍정", "matchers": {"keywords": ["증설"]}},
        ])
        out = S.save_memory_entries([entry], db_path=db_path)
        assert out["checkpointsMerged"] == 1
        assert out["checkpointsDropped"] == 1


def test_state_label_keyword_is_rejected_at_the_merge_boundary():
    """상태 라벨 전문을 keyword로 쓰면 그 상태의 모든 근거가 매칭된다 — validator가 막는다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        entry = _entry(nextCheckpoints=[{
            "item": "관련 보도가 이어지는지",
            "direction": "supporting",
            "matchers": {"keywords": ["AI 데이터센터 전력 병목"]},
        }])
        out = S.save_memory_entries([entry], db_path=db_path)
        assert out["checkpointsMerged"] == 0
        assert out["checkpointsDropped"] == 1
        stored = json.loads(_states(db_path)[0]["next_checkpoints_json"])
        assert not [c for c in stored if isinstance(c, dict)]


def test_entries_without_checkpoints_still_save():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        out = S.save_memory_entries([_entry(nextCheckpoints=[])], db_path=db_path)
        assert len(out["saved"]) == 1
        assert out["checkpointsMerged"] == 0 and out["checkpointsDropped"] == 0


def test_second_run_inherits_verdict_state_for_the_same_checkpoint():
    """LLM이 같은 항목을 다시 내도 판정 결과를 되돌리지 않는다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        S.save_memory_entries([_entry()], db_path=db_path)
        state = _states(db_path)[0]
        stored = json.loads(state["next_checkpoints_json"])
        for element in stored:
            if isinstance(element, dict):
                element["status"] = "challenged"
                element["lastVerdict"] = {"verdict": "challenged", "at": "2026-08-30T00:00:00+00:00", "evidence": []}
        conn = M.connect(db_path)
        with conn:
            conn.execute(
                "UPDATE market_narrative_states SET next_checkpoints_json=? WHERE state_id=?",
                (json.dumps(stored, ensure_ascii=False), state["state_id"]),
            )
        conn.close()

        S.save_memory_entries([_entry()], db_path=db_path)
        again = [c for c in json.loads(_states(db_path)[0]["next_checkpoints_json"]) if isinstance(c, dict)]
        assert len(again) == 1
        assert again[0]["status"] == "challenged"


# --- 계보 승계·귀속 (2026-08-30 리뷰) -------------------------------------

def test_checkpoints_survive_the_daily_state_row_rotation():
    """상태 행은 날짜별로 회전한다(state_id = sha(state_key:date)) — 승계 없이는
    체크포인트가 매일 open으로 다시 태어나고 어제의 판정·이력은 판정 pass가 다시는
    방문하지 않는 overridden 행에 고립된다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        S.save_memory_entries([_entry(date="2026-08-30")], db_path=db_path)
        # 판정이 지나간 것처럼 status를 바꿔 둔다.
        state = next(s for s in _states(db_path) if s["status"] in ("active", "watch"))
        stored = json.loads(state["next_checkpoints_json"])
        for element in stored:
            if isinstance(element, dict):
                element["status"] = "confirmed"
                element["history"] = [{"at": "2026-08-30T01:00:00+00:00", "from": "open", "to": "confirmed", "verdict": "confirmed"}]
        conn = M.connect(db_path)
        with conn:
            conn.execute(
                "UPDATE market_narrative_states SET next_checkpoints_json=? WHERE state_id=?",
                (json.dumps(stored, ensure_ascii=False), state["state_id"]),
            )
        conn.close()

        # 다음 날 같은 내러티브가 다시 온다 — 새 행이 태어나고 어제 행은 밀려난다.
        S.save_memory_entries([_entry(date="2026-08-31")], db_path=db_path)
        live = [s for s in _states(db_path) if s["status"] in ("active", "watch")]
        assert len(live) == 1
        assert live[0]["state_id"] != state["state_id"]  # 실제로 회전했다
        survived = [c for c in json.loads(live[0]["next_checkpoints_json"]) if isinstance(c, dict)]
        assert len(survived) == 1
        assert survived[0]["status"] == "confirmed"
        assert len(survived[0]["history"]) == 1


def test_checkpoints_attach_to_an_existing_live_state_by_state_key():
    """새 상태를 파생하지 않는 엔트리(중요도 미달)라도 살아 있는 상태를 갱신하는
    것이면 체크포인트는 그 상태로 간다 — 귀속은 stateKey를 따른다(계획 결정 2)."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        S.save_memory_entries([_entry(nextCheckpoints=[])], db_path=db_path)  # 상태를 먼저 세운다
        thin = _entry(
            importance="low",
            sources=[{"title": "t", "source": "s", "date": "2026-08-30", "url": "u"}],
        )
        out = S.save_memory_entries([thin], db_path=db_path)
        assert "state" not in out["saved"][0]        # 새 상태는 파생되지 않았지만
        assert out["checkpointsMerged"] == 1         # 살아 있는 상태에 붙었다
        assert out["checkpointsDropped"] == 0
        live = next(s for s in _states(db_path) if s["status"] in ("active", "watch"))
        assert [c for c in json.loads(live["next_checkpoints_json"]) if isinstance(c, dict)]


def test_merge_failures_are_not_reported_as_llm_rejections(monkeypatch):
    """병합 실패를 dropped에 섞으면 기능 전체가 죽어도 'LLM이 나쁜 체크포인트를
    냈다'와 구분되지 않는다."""
    from features.market_memory import checkpoint_verdicts as CV

    def boom(*_args, **_kwargs):
        raise RuntimeError("db broke")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        monkeypatch.setattr(CV, "merge_state_checkpoints", boom)
        out = S.save_memory_entries([_entry()], db_path=db_path)
        assert out["checkpointsDropped"] == 0
        assert out["checkpointErrors"] == 1
        assert out["checkpointErrorCode"] == "RuntimeError"


def _run_all():
    import pytest
    sys.exit(pytest.main([os.path.abspath(__file__), "-q"]))


if __name__ == "__main__":
    _run_all()
