"""내러티브 검증 projection (0.6 Stage C.1·C.3).

    py -3 -m pytest features/market_memory/tests/test_verification_view.py -q
"""
import json
import os
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.market_memory import memory as M
from features.market_memory import verification_view as V

STATE_ID = "state-power"
TODAY = "2026-08-31"


def _checkpoint(**overrides):
    base = {
        "id": "cp_a",
        "item": "전력 설비 기업 실적 가이던스 상향",
        "direction": "supporting",
        "matchers": {"tickers": ["GEV"], "keywords": ["가이던스 상향"]},
        "dueBy": None,
        "status": "confirmed",
        "createdAt": "2026-08-01T00:00:00+00:00",
        "lastVerdict": {
            "verdict": "confirmed",
            "at": "2026-08-25T00:00:00+00:00",
            "evidence": [{"memoryId": "mem-1", "date": "2026-08-24", "title": "전력기기 가이던스상향", "role": "supporting"}],
        },
        "history": [{"at": "2026-08-25T00:00:00+00:00", "from": "open", "to": "confirmed", "verdict": "confirmed"}],
    }
    base.update(overrides)
    return base


def _seed(db_path, *, checkpoints=None, evidence_date="2026-08-24", changes=()):
    conn = M.connect(db_path)
    M.init_db(conn)
    with conn:
        conn.execute(
            """
            INSERT INTO market_narrative_states (
                state_id, state_key, state_label, story, story_family, status, bias,
                category, region, importance, net_effect, summary, rationale, confidence,
                momentum, evidence_count_7d, evidence_count_30d, evidence_count_90d,
                last_confirmed_at, last_challenged_at,
                effective_from, effective_to, source_memory_id, next_checkpoints_json, updated_at
            )
            VALUES (?, 'ai_power', 'AI 데이터센터 전력 병목', 'ai_power', 'AI 데이터센터 전력 병목',
                'active', 'bullish', 'stock_bond', 'GLOBAL', 'high', 'benefit',
                '전력 수요가 강하다', '전력기기 수주 확인', 0.72,
                'strengthening', 2, 5, 9, '2026-08-24', '',
                '2026-08-01T00:00:00+00:00', '', 'mem-1', ?, '2026-08-25T00:00:00+00:00')
            """,
            (STATE_ID, json.dumps(checkpoints if checkpoints is not None else [], ensure_ascii=False)),
        )
        if evidence_date:
            conn.execute(
                """
                INSERT INTO market_regime_evidence (
                    evidence_id, state_id, memory_id, evidence_date, role, score,
                    title, summary, source_kind, sources_json, matched_terms_json, created_at
                )
                VALUES ('ev-1', ?, 'mem-1', ?, 'supporting', 0.82, '전력기기 가이던스상향', '요약',
                    'rss', '[]', '["전력"]', '2026-08-25T00:00:00+00:00')
                """,
                (STATE_ID, evidence_date),
            )
        for index, (field, old, new, reason, refs) in enumerate(changes):
            conn.execute(
                """
                INSERT INTO market_regime_changes (
                    change_id, state_id, changed_at, field, old_value, new_value, reason,
                    evidence_ids_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"chg-{index}", STATE_ID, f"2026-08-2{index}T00:00:00+00:00", field, old, new, reason,
                 json.dumps(refs, ensure_ascii=False), "2026-08-25T00:00:00+00:00"),
            )
    conn.close()


def _payload(db_path):
    return V.narrative_verification_payload(db_path, as_of=TODAY)


# --- 체크포인트 판정 표시 ------------------------------------------------

def test_structured_checkpoint_carries_status_and_evidence_copies():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed(db_path, checkpoints=[_checkpoint(), "템플릿 문장"])
        state = _payload(db_path)["states"][0]
        assert state["checkpointCounts"]["confirmed"] == 1
        checkpoint = state["checkpoints"][0]
        assert checkpoint["statusLabel"] == "확인됨"
        assert checkpoint["lastVerdict"]["verdictLabel"] == "확인됨"
        assert checkpoint["lastVerdict"]["evidence"] == [
            {"date": "2026-08-24", "title": "전력기기 가이던스상향", "role": "supporting"}
        ]
        assert state["templates"] == ["템플릿 문장"]


def test_invalid_stored_checkpoint_is_reported_not_hidden():
    """검증 실패 원소는 저장에서 보존된다 — 화면도 `검증 불가`로 그 사실을 말한다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed(db_path, checkpoints=[_checkpoint(), {"item": "방향이 없다", "matchers": {"keywords": ["증설"]}}])
        state = _payload(db_path)["states"][0]
        assert state["unverifiableCount"] == 1
        assert len(state["checkpoints"]) == 1


def test_evidence_copy_never_leaks_internal_ids():
    """화면 문장에 memory_id 같은 내부 id가 나가지 않는다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed(db_path, checkpoints=[_checkpoint()])
        blob = json.dumps(_payload(db_path), ensure_ascii=False)
        assert "mem-1" not in blob
        assert "memory:" not in blob


# --- 무소식 배지 (계획 §4) -----------------------------------------------

def test_silence_ladder_is_fixed_at_14_and_30_days():
    assert V.silence_badge(13)["level"] == "active"
    assert V.silence_badge(14)["level"] == "cooling"
    assert "식어가는 중" in V.silence_badge(14)["label"]
    assert V.silence_badge(29)["level"] == "cooling"
    assert V.silence_badge(30)["level"] == "dormant"
    assert "정리 후보" in V.silence_badge(30)["label"]
    assert V.silence_badge(None)["level"] == "unknown"


def test_dormant_badge_says_the_state_does_not_change_itself():
    """30일 무소식은 resolved 자동 전환이 아니라 후보 제안이다(§3.5)."""
    assert "자동으로 바뀌지 않습니다" in V.silence_badge(45)["note"]


def test_silence_days_come_from_the_latest_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed(db_path, checkpoints=[_checkpoint()], evidence_date="2026-08-01")
        state = _payload(db_path)["states"][0]
        assert state["silence"]["days"] == 30
        assert state["silence"]["level"] == "dormant"


def test_state_without_evidence_reports_unknown_not_zero():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed(db_path, checkpoints=[], evidence_date="")
        state = _payload(db_path)["states"][0]
        assert state["silence"]["level"] == "unknown"
        assert state["silence"]["days"] is None


# --- 판정 이력 타임라인 (C.3) --------------------------------------------

def test_timeline_reads_existing_change_rows_including_checkpoint_field():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed(
            db_path,
            checkpoints=[_checkpoint()],
            changes=[
                ("momentum", "stable", "strengthening", "30일 근거 비중으로 판정", []),
                ("checkpoint:cp_a", "open", "confirmed", "전력 설비 기업 실적 가이던스 상향 — 규칙 판정 confirmed", ["memory:mem-1"]),
            ],
        )
        timeline = _payload(db_path)["states"][0]["timeline"]
        kinds = [row["kind"] for row in timeline]
        assert "checkpoint" in kinds and "momentum" in kinds
        checkpoint_row = next(row for row in timeline if row["kind"] == "checkpoint")
        # memory_id 사본은 join하지 않는다 — 몇 건이 근거였는지만 말한다.
        assert checkpoint_row["evidenceCount"] == 1
        assert "evidenceRefs" not in checkpoint_row
        assert checkpoint_row["to"] == "confirmed"


def test_current_state_timeline_includes_old_lineage_status_but_excludes_other_keys():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed(db_path, checkpoints=[])
        conn = M.connect(db_path)
        with conn:
            conn.execute("UPDATE market_narrative_states SET state_id='state-power-old', status='overridden' WHERE state_id=?", (STATE_ID,))
            conn.execute("""INSERT INTO market_narrative_states (state_id, state_key, state_label, story, story_family, status, bias,
                category, region, importance, net_effect, summary, rationale, confidence, momentum, effective_from, next_checkpoints_json, updated_at)
                VALUES (?, 'ai_power', 'AI 데이터센터 전력 병목', 'ai_power', 'AI 데이터센터 전력 병목', 'active', 'bullish',
                'stock_bond', 'GLOBAL', 'high', 'benefit', '', '', .7, 'stable', '2026-08-30T00:00:00+00:00', '[]', '2026-08-30T00:00:00+00:00')""", (STATE_ID,))
            conn.execute("""INSERT INTO market_narrative_states (state_id, state_key, state_label, story, story_family, status, bias,
                category, region, importance, net_effect, summary, rationale, confidence, momentum, effective_from, next_checkpoints_json, updated_at)
                VALUES ('other-state', 'unrelated', '무관', 'unrelated', '무관', 'active', 'neutral',
                'stock_bond', 'GLOBAL', 'low', '', '', '', .5, 'stable', '2026-08-30T00:00:00+00:00', '[]', '2026-08-30T00:00:00+00:00')""")
            conn.execute("""INSERT INTO market_regime_changes (change_id, state_id, changed_at, field, old_value, new_value, reason, evidence_ids_json, created_at)
                VALUES ('old-status', 'state-power-old', '2026-08-29T00:00:00+00:00', 'status', 'active', 'overridden', '회전', '[]', '2026-08-29T00:00:00+00:00')""")
            conn.execute("""INSERT INTO market_regime_changes (change_id, state_id, changed_at, field, old_value, new_value, reason, evidence_ids_json, created_at)
                VALUES ('other-status', 'other-state', '2026-08-30T00:00:00+00:00', 'status', 'active', 'overridden', '무관', '[]', '2026-08-30T00:00:00+00:00')""")
        conn.close()
        timeline = _payload(db_path)["states"][0]["timeline"]
        assert any(row["kind"] == "status" and row["to"] == "overridden" and row["reason"] == "회전" for row in timeline)
        assert not any(row["reason"] == "무관" for row in timeline)


def test_blank_state_key_keeps_its_own_timeline_history():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed(db_path, checkpoints=[])
        conn = M.connect(db_path)
        with conn:
            conn.execute("UPDATE market_narrative_states SET state_key='' WHERE state_id=?", (STATE_ID,))
            conn.execute("""INSERT INTO market_regime_changes (change_id, state_id, changed_at, field, old_value, new_value, reason, evidence_ids_json, created_at)
                VALUES ('blank-key', ?, '2026-08-30T00:00:00+00:00', 'status', 'active', 'watch', 'legacy', '[]', '2026-08-30T00:00:00+00:00')""", (STATE_ID,))
        conn.close()
        assert _payload(db_path)["states"][0]["timeline"][0]["reason"] == "legacy"


def test_summary_counts_across_states():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed(db_path, checkpoints=[_checkpoint(), _checkpoint(id="cp_b", item="착공 지연 보도", direction="challenging",
                                                              matchers={"keywords": ["착공 지연"]}, status="challenged",
                                                              lastVerdict=None, history=[])])
        summary = _payload(db_path)["summary"]
        assert summary["stateCount"] == 1
        assert summary["checkpointCount"] == 2
        assert summary["confirmed"] == 1 and summary["challenged"] == 1


def test_missing_database_returns_empty_payload():
    with tempfile.TemporaryDirectory() as tmp:
        payload = V.narrative_verification_payload(os.path.join(tmp, "nope.sqlite3"), as_of=TODAY)
        assert payload["states"] == [] and payload["summary"]["stateCount"] == 0


def _run_all():
    import pytest
    sys.exit(pytest.main([os.path.abspath(__file__), "-q"]))


if __name__ == "__main__":
    _run_all()
