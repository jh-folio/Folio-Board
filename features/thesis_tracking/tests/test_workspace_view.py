"""종목 Thesis workspace projection (0.6 Stage C.2 + A.3).

    py -3 -m pytest features/thesis_tracking/tests/test_workspace_view.py -q
"""
import json
import os
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.market_memory import memory as MM
from features.thesis_tracking import model as M
from features.thesis_tracking import store as ST
from features.thesis_tracking import workspace_view as W

TICKER = "NVDA"
TODAY = "2026-08-31"


def _checkpoint(**overrides):
    base = {
        "id": "cp_t",
        "item": "데이터센터 매출 가이던스 상향",
        "direction": "supporting",
        "matchers": {"tickers": [TICKER], "keywords": ["가이던스 상향"]},
        "dueBy": None,
        "status": "confirmed",
        "createdAt": "2026-08-01T00:00:00+00:00",
        "lastVerdict": {
            "verdict": "confirmed",
            "at": "2026-08-25T00:00:00+00:00",
            "evidence": [{"docId": "research-inbox/rss/x.md", "date": "2026-08-24", "title": "엔비디아 가이던스상향"}],
        },
        "history": [{"at": "2026-08-25T00:00:00+00:00", "from": "open", "to": "confirmed", "verdict": "confirmed"}],
    }
    base.update(overrides)
    return base


def _seed_thesis(db_path, *, source="manual", linked_regimes=(), checkpoints=None):
    conn = ST.connect(db_path)
    ST.upsert_thesis(conn, M.Thesis(
        ticker=TICKER, company="NVIDIA", core_thesis="AI 가속기 수요가 이어진다",
        key_assumptions=["자본지출 유지"], falsification_triggers=["대형 고객 자체 칩 전환"],
        key_metrics=["데이터센터 매출"], linked_regimes=list(linked_regimes),
        source=source, next_checkpoints=["노트에서 읽은 문장"],
    ))
    if checkpoints is not None:
        ST.save_thesis_checkpoints(conn, TICKER, checkpoints + ["노트에서 읽은 문장"])
    conn.close()


def _seed_state(db_path, *, state_key="ai_power", label="AI 데이터센터 전력 병목",
                checkpoints=(), challenging_date=""):
    conn = MM.connect(db_path)
    MM.init_db(conn)
    with conn:
        conn.execute(
            """
            INSERT INTO market_narrative_states (
                state_id, state_key, state_label, story, story_family, status, bias,
                category, region, importance, net_effect, summary, rationale, confidence,
                momentum, effective_from, effective_to, source_memory_id, next_checkpoints_json, updated_at
            )
            VALUES ('state-1', ?, ?, ?, ?, 'active', 'bullish', 'stock_bond', 'GLOBAL', 'high',
                'benefit', '요약', '근거', 0.7, 'stable', '2026-08-01T00:00:00+00:00', '', 'mem-1', ?,
                '2026-08-25T00:00:00+00:00')
            """,
            (state_key, label, state_key, label, json.dumps(list(checkpoints), ensure_ascii=False)),
        )
        if challenging_date:
            conn.execute(
                """
                INSERT INTO market_regime_evidence (
                    evidence_id, state_id, memory_id, evidence_date, role, score,
                    title, summary, source_kind, sources_json, matched_terms_json, created_at
                )
                VALUES ('ev-c', 'state-1', 'mem-2', ?, 'challenging', 0.8, '착공 지연 보도', '요약',
                    'rss', '[]', '[]', '2026-08-25T00:00:00+00:00')
                """,
                (challenging_date,),
            )
    conn.close()


def _seed_vault_note(db_path, ticker=TICKER):
    conn = MM.connect(db_path)
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS obsidian_note_index (
                note_id TEXT PRIMARY KEY, rel_path TEXT NOT NULL DEFAULT '', path TEXT NOT NULL DEFAULT '',
                note_type TEXT NOT NULL DEFAULT 'unknown', layer TEXT NOT NULL DEFAULT 'unknown',
                importable INTEGER NOT NULL DEFAULT 0, ticker TEXT NOT NULL DEFAULT '',
                company TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '', source_layer TEXT NOT NULL DEFAULT '',
                reuse_as_hypothesis INTEGER NOT NULL DEFAULT 0, reuse_as_evidence INTEGER NOT NULL DEFAULT 0,
                tags_json TEXT NOT NULL DEFAULT '[]', content_hash TEXT NOT NULL DEFAULT '',
                mtime REAL NOT NULL DEFAULT 0, first_seen TEXT NOT NULL DEFAULT '', last_seen TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            "INSERT INTO obsidian_note_index (note_id, rel_path, note_type, ticker, title, last_seen) "
            "VALUES ('n1', 'Thesis/NVDA.md', 'company_thesis', ?, 'NVDA thesis', '2026-08-30')",
            (ticker,),
        )
    conn.close()


# --- 없는 thesis ---------------------------------------------------------

def test_missing_thesis_returns_empty_workspace():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        out = W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)
        assert out["hasThesis"] is False and out["thesis"] is None
        assert out["layer"] == "hypothesis" and out["reuseAsEvidence"] is False


def test_ticker_is_normalized_the_same_way_as_the_registry():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path)
        assert W.thesis_workspace_payload("nvda", db_path, as_of=TODAY)["hasThesis"] is True
        assert W.thesis_workspace_payload("005930.KS", db_path, as_of=TODAY)["ticker"] == "005930"


# --- 두 층의 판정 (§3.2) -------------------------------------------------

def test_delta_verdict_and_checkpoint_status_live_in_separate_keys():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, checkpoints=[_checkpoint()])
        conn = ST.connect(db_path)
        ST.save_delta(conn, TICKER, {
            "verdict": "weakened", "summary": "약화 판정",
            "generatedAt": "2026-08-28T00:00:00+00:00",
            "counterEvidence": [{"title": "주문 축소", "source": "Reuters", "date": "2026-08-27"}],
            "uncertainties": ["실적 발표 전"],
        })
        conn.close()

        out = W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)
        # 6값 enum (Delta)
        assert out["latestDelta"]["verdict"] == "weakened"
        assert out["latestDelta"]["verdictLabel"] == "약화"
        # 3값 enum (체크포인트 판정) — 다른 키에 산다
        assert out["checkpoints"]["structured"][0]["status"] == "confirmed"
        assert out["checkpoints"]["structured"][0]["lastVerdict"]["verdict"] == "confirmed"
        assert out["checkpoints"]["counts"]["confirmed"] == 1
        assert out["latestDelta"]["counterEvidence"][0]["title"] == "주문 축소"


def test_thesis_checkpoint_evidence_has_no_role_key():
    """문서 풀에는 role 분류가 없다 — 없는 분류를 화면에 만들어 내지 않는다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, checkpoints=[_checkpoint()])
        evidence = W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)["checkpoints"]["structured"][0]["lastVerdict"]["evidence"]
        assert evidence == [{"date": "2026-08-24", "title": "엔비디아 가이던스상향"}]


def test_history_comes_from_checkpoint_dict_and_delta_rows():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, checkpoints=[_checkpoint()])
        conn = ST.connect(db_path)
        ST.save_delta(conn, TICKER, {"verdict": "maintained", "generatedAt": "2026-08-20T00:00:00+00:00"})
        ST.save_delta(conn, TICKER, {"verdict": "weakened", "generatedAt": "2026-08-28T00:00:00+00:00"})
        conn.close()
        out = W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)
        assert [row["verdict"] for row in out["deltaHistory"]] == ["weakened", "maintained"]
        assert out["checkpoints"]["structured"][0]["history"][0]["to"] == "confirmed"


# --- 소유권 (Stage B 리뷰 확정 1) ----------------------------------------

def test_app_owned_thesis_with_a_vault_note_reports_paused_sync():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, source="manual")
        _seed_vault_note(db_path)
        ownership = W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)["ownership"]
        assert ownership["syncPaused"] is True
        assert "Vault에서 더 이상 갱신되지 않습니다" in ownership["message"]
        assert ownership["vaultNote"]["relPath"] == "Thesis/NVDA.md"


def test_vault_owned_thesis_is_not_flagged():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, source="obsidian")
        _seed_vault_note(db_path)
        ownership = W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)["ownership"]
        assert ownership["syncPaused"] is False and ownership["message"] == ""


def test_app_owned_thesis_without_a_vault_note_is_not_flagged():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, source="native_note")
        ownership = W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)["ownership"]
        assert ownership["syncPaused"] is False


# --- A.3 linked_regimes 전파 ---------------------------------------------

def test_challenged_checkpoint_in_a_linked_regime_raises_an_alert():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_state(db_path, checkpoints=[{
            "id": "cp_s", "item": "착공 지연 보도", "direction": "challenging",
            "matchers": {"keywords": ["착공 지연"]}, "dueBy": None, "status": "challenged",
            "createdAt": "2026-08-01T00:00:00+00:00", "lastVerdict": None, "history": [],
        }])
        _seed_thesis(db_path, linked_regimes=["ai_power"])
        alerts = W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)["regimeAlerts"]
        assert len(alerts) == 1
        assert alerts[0]["label"] == "AI 데이터센터 전력 병목"
        assert alerts[0]["reasons"][0]["kind"] == "challenged_checkpoint"


def test_recent_challenging_evidence_in_a_linked_regime_raises_an_alert():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_state(db_path, challenging_date="2026-08-25")
        _seed_thesis(db_path, linked_regimes=["AI 데이터센터 전력 병목"])   # 라벨로도 연결된다
        alerts = W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)["regimeAlerts"]
        assert alerts and alerts[0]["reasons"][0]["kind"] == "challenging_evidence"


def test_old_challenging_evidence_does_not_raise_an_alert():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_state(db_path, challenging_date="2026-06-01")
        _seed_thesis(db_path, linked_regimes=["ai_power"])
        assert W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)["regimeAlerts"] == []


def test_undeclared_regimes_do_not_raise_alerts():
    """자동 추론 링크까지 끌어오면 사용자가 연결한 적 없는 내러티브가 경고를 만든다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_state(db_path, challenging_date="2026-08-25")
        _seed_thesis(db_path, linked_regimes=[])
        assert W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)["regimeAlerts"] == []


def test_manual_link_to_rotated_state_uses_current_lineage_not_old_checkpoint():
    """수동 관계는 보존하지만 overridden 행의 과거 반증을 현재 경고로 읽지 않는다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_state(db_path, checkpoints=[{
            "id": "old-cp", "item": "과거 착공 지연", "direction": "challenging",
            "matchers": {"keywords": ["지연"]}, "dueBy": None, "status": "challenged",
            "createdAt": "2026-08-01T00:00:00+00:00", "lastVerdict": None, "history": [],
        }])
        _seed_thesis(db_path, linked_regimes=[])
        conn = MM.connect(db_path)
        with conn:
            conn.execute("UPDATE market_narrative_states SET status='overridden' WHERE state_id='state-1'")
            conn.execute(
                """INSERT INTO market_narrative_states (state_id, state_key, state_label, story, story_family,
                    status, bias, category, region, importance, net_effect, summary, rationale, confidence,
                    momentum, effective_from, effective_to, source_memory_id, next_checkpoints_json, updated_at)
                   VALUES ('state-2', 'ai_power', 'AI 데이터센터 전력 병목', 'ai_power', 'AI 데이터센터 전력 병목',
                    'active', 'bullish', 'stock_bond', 'GLOBAL', 'high', 'benefit', '새 요약', '새 근거', .7,
                    'stable', '2026-08-30T00:00:00+00:00', '', 'mem-2', '[]', '2026-08-30T00:00:00+00:00')"""
            )
            conn.execute(
                """INSERT INTO market_regime_thesis_links
                   (link_id, state_id, ticker, thesis_ticker, relationship, strength, method, note_path, created_at, updated_at)
                   VALUES ('manual-old', 'state-1', '', ?, 'related', .9, 'manual', '', '2026-08-01', '2026-08-01')""",
                (TICKER,),
            )
        conn.close()
        assert W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)["regimeAlerts"] == []

        conn = MM.connect(db_path)
        with conn:
            conn.execute("UPDATE market_narrative_states SET next_checkpoints_json=? WHERE state_id='state-2'", (json.dumps([{
                "id": "current-cp", "item": "현재 착공 지연", "direction": "challenging",
                "matchers": {"keywords": ["지연"]}, "dueBy": None, "status": "challenged",
                "createdAt": "2026-08-30T00:00:00+00:00", "lastVerdict": None, "history": [],
            }], ensure_ascii=False),))
        conn.close()
        alerts = W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)["regimeAlerts"]
        assert len(alerts) == 1 and alerts[0]["stateId"] == "state-2"


def test_propagation_does_not_change_any_stored_verdict():
    """A.3은 표시일 뿐이다 — 전파가 thesis verdict도 체크포인트 status도 바꾸지 않는다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_state(db_path, challenging_date="2026-08-25")
        _seed_thesis(db_path, linked_regimes=["ai_power"], checkpoints=[_checkpoint()])
        conn = ST.connect(db_path)
        ST.save_delta(conn, TICKER, {"verdict": "strengthened", "generatedAt": "2026-08-28T00:00:00+00:00"})
        before = json.dumps(ST.get_thesis(conn, TICKER), ensure_ascii=False, sort_keys=True)
        conn.close()

        out = W.thesis_workspace_payload(TICKER, db_path, as_of=TODAY)
        assert out["regimeAlerts"]
        assert out["latestDelta"]["verdict"] == "strengthened"

        conn = ST.connect(db_path)
        after = json.dumps(ST.get_thesis(conn, TICKER), ensure_ascii=False, sort_keys=True)
        conn.close()
        assert after == before


def _run_all():
    import pytest
    sys.exit(pytest.main([os.path.abspath(__file__), "-q"]))


if __name__ == "__main__":
    _run_all()
