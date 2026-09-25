from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

from features.agent_mode import consultation_store as store
from features.agent_mode.consultation_store import append_user_message, create_session
from features.agent_mode.consultation_context import assemble_consultation_context
from features.agent_mode.chat import build_chat_prompt
from features.agent_mode.job_runtime import run_consultation_job
from features.investment_notes.service import normalize_note
from features.market_memory import memory as MM
from features.thesis_tracking import model as thesis_model
from features.thesis_tracking import store as thesis_store


CANARY = "CONSULTATION_CANARY_MUST_NEVER_BECOME_EVIDENCE"


def _seed_stage_d_context(db_path):
    conn = MM.connect(db_path)
    MM.init_db(conn)
    with conn:
        for state_id, key, label in (
            ("state-selected", "ai_power", "선택한 전력 전제"),
            ("state-unrelated", "oil", "관계없는 유가 전제"),
        ):
            conn.execute(
                """
                INSERT INTO market_narrative_states (
                    state_id, state_key, state_label, story, story_family, status, bias,
                    category, region, importance, net_effect, summary, rationale, confidence,
                    momentum, evidence_count_7d, evidence_count_30d, evidence_count_90d,
                    effective_from, effective_to, source_memory_id, next_checkpoints_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'active', 'bullish', 'stock_bond', 'GLOBAL', 'high',
                    'benefit', '요약', '근거', .7, 'strengthening', 1, 3, 7,
                    '2026-08-01T00:00:00+00:00', '', 'mem', ?, '2026-08-30T00:00:00+00:00')
                """,
                (state_id, key, label, key, label, json.dumps([{
                    "id": f"cp-{state_id}", "item": f"{label} 반증", "direction": "challenging",
                    "matchers": {"keywords": ["반증"]}, "status": "challenged", "dueBy": None,
                    "createdAt": "2026-08-01T00:00:00+00:00", "lastVerdict": {"verdict": "challenged", "at": "2026-08-30T00:00:00+00:00", "evidence": [{"title": f"{label} 근거", "date": "2026-08-30", "role": "challenging"}]}, "history": [],
                }], ensure_ascii=False)),
            )
    conn.close()
    conn = thesis_store.connect(db_path)
    thesis_store.upsert_thesis(conn, thesis_model.Thesis(
        ticker="NVDA", company="NVIDIA", core_thesis="선택한 NVDA 가설", key_assumptions=["자본지출 유지"],
        falsification_triggers=["고객 자체칩 전환"], linked_regimes=["ai_power"], source="manual",
    ))
    thesis_store.save_delta(conn, "NVDA", {
        "verdict": "weakened", "generatedAt": "2026-08-30T00:00:00+00:00", "summary": "집중도 위험",
        "supportingEvidence": [
            {"title": "90일 밖 근거 CANARY", "source": "Old source", "date": "2026-05-01", "reason": "오래됨"},
            {"title": "최근 수요 확인", "source": "Reuters", "date": "2026-08-29", "reason": "최근"},
        ],
        "counterEvidence": [{"title": "자체칩 확대", "source": "Reuters", "date": "2026-08-30", "reason": "가정과 충돌"}],
        "contradictions": ["수요 전망과 고객 집중도가 충돌"], "uncertainties": ["다음 실적 전"],
    })
    conn.close()


def _challenge_session(tmp_path, scope, message):
    session = create_session(tmp_path, {"scope": {**scope, "intent": "challenge"}})
    append_user_message(tmp_path, session["id"], message, operation_id=f"op-{session['id']}")
    return session


def test_atomic_session_idempotency_and_hypothesis_boundary(tmp_path):
    session = store.create_session(tmp_path, {"scope": {"kind": "portfolio"}})
    first = store.append_user_message(tmp_path, session["id"], CANARY, operation_id="op-fixed")
    second = store.append_user_message(tmp_path, session["id"], "different", operation_id="op-fixed")
    assert first["message"]["id"] == second["message"]["id"]
    loaded = store.get_session(tmp_path, session["id"])
    assert loaded["layer"] == "hypothesis"
    assert loaded["sourceLayer"] == "user_consultation"
    assert loaded["reuseAsEvidence"] is False
    assert not list(store.sessions_dir(tmp_path).glob("*.tmp"))


def test_100_turn_context_is_bounded_and_valid_json(tmp_path):
    session = store.create_session(tmp_path, {"scope": {"kind": "watchlist", "tickers": ["NVDA"]}})
    for index in range(105):
        row = store.append_user_message(tmp_path, session["id"], f"question {index} " + ("x" * 200), operation_id=f"op-{index}")
        store.append_assistant_message(tmp_path, session["id"], row["message"]["id"], f"answer {index} " + ("y" * 200))
    samples = []
    for _ in range(30):
        started = time.perf_counter()
        context = assemble_consultation_context(tmp_path, session["id"])
        samples.append((time.perf_counter() - started) * 1000)
    assert sorted(samples)[27] <= 300
    assert len(context["serialized"]) <= 32_000
    assert json.loads(context["serialized"])["rules"]["consultationIsEvidence"] is False
    assert len(context["pack"]["recentMessages"]) <= 20


def test_current_message_is_excluded_from_recent_messages_to_avoid_repeating_it(tmp_path):
    """Agent Dock Stage B: 방금 저장된 질문은 recentMessages에 다시 넣지 않는다 —
    `build_chat_prompt()`가 같은 문장을 `사용자 질문:` 자리에 이미 따로 싣는다."""
    session = store.create_session(tmp_path, {"scope": {"kind": "general"}})
    appended = store.append_user_message(tmp_path, session["id"], "이 질문은 딱 한 번만 나와야 한다", operation_id="op-dedupe")
    message_id = appended["message"]["id"]

    with_id = assemble_consultation_context(tmp_path, session["id"], current_message_id=message_id)
    assert all(row["content"] != "이 질문은 딱 한 번만 나와야 한다" for row in with_id["pack"]["recentMessages"])

    without_id = assemble_consultation_context(tmp_path, session["id"])
    assert any(row["content"] == "이 질문은 딱 한 번만 나와야 한다" for row in without_id["pack"]["recentMessages"])


def test_truly_general_scope_still_gets_lightweight_market_context(tmp_path):
    """주제·보고서·티커가 전혀 없는 순수 질문도 marketState/recentChanges는 받는다 —
    둘 다 이미 상한이 걸린 요약값이라 "요즘 시장 어때" 류 질문의 근거가 된다.
    실사용 확인(2026-09-16): 완전히 비웠더니 이런 일반 시장 질문의 답이 얕아져서
    되돌렸다. fastSignals는 티커별 조회라 티커가 없으면 여전히 안 붙는다."""
    session = store.create_session(tmp_path, {"scope": {"kind": "general"}})
    store.append_user_message(tmp_path, session["id"], "오늘 기분이 어때?", operation_id="op-general")
    source = assemble_consultation_context(tmp_path, session["id"])["pack"]["sourceContext"]
    assert "marketState" in source
    assert "recentChanges" in source
    assert "fastSignals" not in source


def test_general_scope_with_a_mentioned_ticker_still_gets_fast_signals(tmp_path):
    """관련 있는 티커가 있으면(주제 자체는 general이어도) 여전히 근거를 붙인다."""
    session = store.create_session(tmp_path, {"scope": {"kind": "general", "tickers": ["NVDA"]}})
    store.append_user_message(tmp_path, session["id"], "NVDA 어때?", operation_id="op-ticker")
    source = assemble_consultation_context(tmp_path, session["id"])["pack"]["sourceContext"]
    assert "fastSignals" in source
    assert "marketState" in source


def test_recent_messages_shrink_once_a_rolling_summary_exists_to_avoid_repeating_old_turns(tmp_path):
    """`_update_memory()`가 요약한 구간이 `recentMessages`에도 원문 그대로 다시 실리면
    같은 옛 턴을 두 번 지불하는 것과 같다."""
    session = store.create_session(tmp_path, {"scope": {"kind": "general"}})
    for index in range(10):
        row = store.append_user_message(tmp_path, session["id"], f"OLDQ{index}", operation_id=f"op-{index}")
        store.append_assistant_message(tmp_path, session["id"], row["message"]["id"], f"OLDA{index}")
    saved = store.get_session(tmp_path, session["id"])
    assert saved["memory"]["summary"]  # `_update_memory`가 정확히 20개째에 발동했다

    context = assemble_consultation_context(tmp_path, session["id"])
    assert len(context["pack"]["recentMessages"]) <= 12
    recent_texts = {row["content"] for row in context["pack"]["recentMessages"]}
    assert "OLDQ0" not in recent_texts
    assert "OLDA0" not in recent_texts


def test_context_reads_latest_market_snapshot_by_as_of(tmp_path):
    session = store.create_session(tmp_path, {"scope": {"kind": "portfolio"}})
    db = tmp_path / "market-memory.sqlite3"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE market_state_snapshots (snapshot_id TEXT PRIMARY KEY, as_of TEXT, payload_json TEXT)")
        connection.execute("INSERT INTO market_state_snapshots VALUES (?,?,?)", ("older", "2026-07-01T00:00:00Z", json.dumps({"id": "older", "asOf": "2026-07-01T00:00:00Z", "marketRegime": "old"})))
        connection.execute("INSERT INTO market_state_snapshots VALUES (?,?,?)", ("latest", "2026-08-01T00:00:00Z", json.dumps({"id": "latest", "asOf": "2026-08-01T00:00:00Z", "marketRegime": "risk_on"})))
        connection.commit()
    context = assemble_consultation_context(tmp_path, session["id"])
    assert context["pack"]["sourceContext"]["marketState"]["id"] == "latest"


def test_narrative_challenge_context_reads_only_the_selected_state_and_is_bounded(tmp_path):
    _seed_stage_d_context(tmp_path / "market-memory.sqlite3")
    session = _challenge_session(tmp_path, {"kind": "market_memory", "id": "state-selected"}, "이 전제를 반박해줘")
    context = assemble_consultation_context(tmp_path, session["id"])
    source = context["pack"]["sourceContext"]
    selected = source["selectedNarrative"]
    assert selected["stateId"] == "state-selected"
    assert selected["layer"] == "source-grounded"
    assert "관계없는 유가 전제" not in context["serialized"]
    assert len(selected["checkpoints"]) <= 8
    assert source["evidenceWindow"] == {"days": 90, "maxItems": 6}
    assert len(context["serialized"]) <= 32_000


def test_thesis_challenge_keeps_hypothesis_and_verification_in_separate_layers_without_mutation(tmp_path):
    db_path = tmp_path / "market-memory.sqlite3"
    _seed_stage_d_context(db_path)
    before = db_path.read_bytes()
    session = _challenge_session(tmp_path, {"kind": "watchlist", "id": "NVDA", "tickers": ["NVDA"]}, "이 Thesis를 반박해줘")
    context = assemble_consultation_context(tmp_path, session["id"])
    selected = context["pack"]["sourceContext"]["selectedThesis"]
    assert selected["ticker"] == "NVDA"
    assert selected["hypothesis"]["layer"] == "hypothesis"
    assert selected["hypothesis"]["reuseAsEvidence"] is False
    assert selected["verification"]["layer"] == "source-grounded"
    assert selected["verification"]["latestDelta"]["counterEvidence"][0]["title"] == "자체칩 확대"
    assert selected["verification"]["latestDelta"]["supportingEvidence"][0]["title"] == "최근 수요 확인"
    assert "90일 밖 근거 CANARY" not in context["serialized"]
    assert context["pack"]["rules"]["challenge"]["noWriteback"] is True
    assert db_path.read_bytes() == before


def test_missing_challenge_identifier_returns_data_gap_without_broad_watchlist_or_narrative_fallback(tmp_path):
    _seed_stage_d_context(tmp_path / "market-memory.sqlite3")
    session = _challenge_session(tmp_path, {"kind": "watchlist", "id": "MISSING", "tickers": ["MISSING"]}, "이 Thesis를 반박해줘")
    source = assemble_consultation_context(tmp_path, session["id"])["pack"]["sourceContext"]
    assert source["dataGaps"][0]["id"] == "MISSING"
    assert "watchlist" not in source and "marketState" not in source and "selectedThesis" not in source


@pytest.mark.parametrize(
    ("scope", "message", "expected_key"),
    [
        ({"kind": "market_memory", "id": "state-selected"}, "그중 출처 신뢰도가 가장 약한 것은?", "selectedNarrative"),
        ({"kind": "watchlist", "id": "NVDA", "tickers": ["NVDA"]}, "그중 출처 신뢰도가 가장 약한 것은?", "selectedThesis"),
    ],
)
def test_challenge_scope_persists_selected_context_on_follow_up(tmp_path, scope, message, expected_key):
    _seed_stage_d_context(tmp_path / "market-memory.sqlite3")
    session = _challenge_session(tmp_path, scope, "이 전제를 반박해줘" if scope["kind"] == "market_memory" else "이 Thesis를 반박해줘")
    first = store.get_session(tmp_path, session["id"])["messages"][-1]
    store.append_assistant_message(tmp_path, session["id"], first["id"], "첫 반박 답변")
    store.append_user_message(tmp_path, session["id"], message, operation_id="follow-up")
    source = assemble_consultation_context(tmp_path, session["id"])["pack"]["sourceContext"]
    assert expected_key in source
    assert "marketState" not in source and "watchlist" not in source


def test_challenge_intent_survives_store_continuation_without_first_turn(tmp_path):
    _seed_stage_d_context(tmp_path / "market-memory.sqlite3")
    session = store.create_session(tmp_path, {"scope": {"kind": "watchlist", "id": "NVDA", "tickers": ["NVDA"], "intent": "challenge"}})
    path = store.sessions_dir(tmp_path) / f"{session['id']}.json"
    private = json.loads(path.read_text(encoding="utf-8"))
    private["messages"] = [{"id": f"msg-{index}", "role": "user", "content": "x", "createdAt": "2026-08-01T00:00:00Z", "status": "answered"} for index in range(500)]
    private["messageCount"] = 500
    store._atomic_write(path, private)
    continued = store.append_user_message(tmp_path, session["id"], "후속 질문", operation_id="continue-challenge")["session"]
    assert continued["scope"]["intent"] == "challenge"
    assert "selectedThesis" in assemble_consultation_context(tmp_path, continued["id"])["pack"]["sourceContext"]


def test_challenge_rules_do_not_change_regular_watchlist_or_portfolio_context(tmp_path):
    regular = store.create_session(tmp_path, {"scope": {"kind": "watchlist", "tickers": ["NVDA"]}})
    rules = assemble_consultation_context(tmp_path, regular["id"])["pack"]["rules"]
    assert "challenge" not in rules
    assert rules["canonicalWriteback"] is False
    assert rules["consultationIsEvidence"] is False


def test_report_scope_cannot_escape_report_directory(tmp_path):
    (tmp_path.parent / "private.json").write_text(json.dumps({"markdown": CANARY}), encoding="utf-8")
    session = store.create_session(tmp_path, {"scope": {"kind": "topic_report", "id": "../../private"}})
    context = assemble_consultation_context(tmp_path, session["id"])
    assert CANARY not in context["serialized"]
    assert context["pack"]["sourceContext"].get("report") is None


def test_message_limit_creates_linked_continuation(tmp_path):
    session = store.create_session(tmp_path, {"title": "Long session"})
    path = store.sessions_dir(tmp_path) / f"{session['id']}.json"
    private = json.loads(path.read_text(encoding="utf-8"))
    private["messages"] = [{"id": f"msg-{index}", "role": "user", "content": "x", "createdAt": "2026-08-01T00:00:00Z", "status": "answered"} for index in range(500)]
    private["messageCount"] = 500
    store._atomic_write(path, private)
    appended = store.append_user_message(tmp_path, session["id"], "continue", operation_id="op-next")
    assert appended["session"]["continuationOf"] == session["id"]
    assert store.get_session(tmp_path, session["id"])["continuedBy"] == appended["session"]["id"]


def test_retried_operation_at_message_limit_reuses_one_continuation(tmp_path):
    """같은 operationId 재시도가 continuation을 또 만들면 앞선 것이 고아가 된다."""
    session = store.create_session(tmp_path, {"title": "Long session"})
    path = store.sessions_dir(tmp_path) / f"{session['id']}.json"
    private = json.loads(path.read_text(encoding="utf-8"))
    private["messages"] = [{"id": f"msg-{index}", "role": "user", "content": "x", "createdAt": "2026-08-01T00:00:00Z", "status": "answered"} for index in range(500)]
    private["messageCount"] = 500
    store._atomic_write(path, private)

    first = store.append_user_message(tmp_path, session["id"], "continue", operation_id="op-retry")
    second = store.append_user_message(tmp_path, session["id"], "continue", operation_id="op-retry")

    assert second["session"]["id"] == first["session"]["id"]
    assert second["message"]["id"] == first["message"]["id"]
    assert second["idempotent"] is True
    # 원본 + continuation 하나뿐이어야 한다.
    assert len(list(store.sessions_dir(tmp_path).glob("*.json"))) == 2
    assert store.get_session(tmp_path, session["id"])["continuedBy"] == first["session"]["id"]


def test_message_limit_reserves_room_for_paired_assistant_reply(tmp_path):
    session = store.create_session(tmp_path, {"title": "Almost full"})
    path = store.sessions_dir(tmp_path) / f"{session['id']}.json"
    private = json.loads(path.read_text(encoding="utf-8"))
    private["messages"] = [{"id": f"msg-{index}", "role": "user", "content": "x", "createdAt": "2026-08-01T00:00:00Z", "status": "answered"} for index in range(499)]
    private["messageCount"] = 499
    store._atomic_write(path, private)

    appended = store.append_user_message(tmp_path, session["id"], "last turn", operation_id="op-pair")
    assert appended["session"]["continuationOf"] == session["id"]
    store.append_assistant_message(tmp_path, appended["session"]["id"], appended["message"]["id"], "paired answer")
    continued = store.get_session(tmp_path, appended["session"]["id"])
    assert continued["messageCount"] == 2


def test_saved_user_turn_can_be_retried_after_restart_without_proposal(tmp_path, monkeypatch):
    from features.agent_mode import bridge

    session = store.create_session(tmp_path, {"scope": {"kind": "portfolio"}})
    appended = store.append_user_message(tmp_path, session["id"], "장기 thesis와 최근 뉴스의 관계는?", operation_id="op-restart")
    monkeypatch.setattr(bridge, "bridge_status", lambda: {"available": False})
    result = run_consultation_job(tmp_path, session["id"], appended["message"]["id"])
    loaded = store.get_session(tmp_path, session["id"])
    assert result["status"] == "answered"
    assert loaded["messages"][-1]["role"] == "assistant"
    assert loaded["messages"][-1]["engine"] == "rules"
    assert not (tmp_path / "agent-proposals").exists()


def test_prompt_is_answer_first_and_note_snapshot_stays_hypothesis():
    """`build_consultation_prompt()`는 죽은 코드라 삭제했다(Agent Dock Stage B) — 실제
    프로덕션 경로인 `build_chat_prompt()`가 같은 answer-first 원칙을 갖는지 검사한다."""
    prompt = build_chat_prompt("질문", {}, {})
    assert "사용자의 현재 질문에 먼저 직접 답한다" in prompt
    assert "정해진 절차나 질문지를 강요하지 않는다" in prompt
    note = normalize_note({"noteType": "portfolio_decision", "title": "상담 정리", "consultationRef": "consult-abc", "body": CANARY})
    assert note["sourceLayer"] == "user_consultation"
    assert note["reuseAsEvidence"] is False
    assert note["consultationRef"] == "consult-abc"


def test_consultation_canary_remains_outside_research_and_canonical_paths(tmp_path):
    session = store.create_session(tmp_path, {"scope": {"kind": "portfolio"}})
    store.append_user_message(tmp_path, session["id"], CANARY, operation_id="op-canary")
    forbidden = [
        tmp_path / "research-index.sqlite3",
        tmp_path / "market-memory.sqlite3",
        tmp_path / "briefings",
        tmp_path / "company-analysis",
        tmp_path / "topic-reports",
    ]
    assert all(not path.exists() for path in forbidden)


def test_consultation_http_contract_and_explicit_delete(tmp_path, monkeypatch):
    from features.agent_mode import routes

    monkeypatch.setattr(routes, "submit_consultation_job", lambda _data, session_id, message_id, **_kwargs: {"id": "job-1", "status": "queued", "sessionId": session_id, "messageId": message_id})
    boundary = routes.AgentCompanionBoundary(object(), data_dir=tmp_path)
    created = boundary.create_consultation({"title": "NVDA 상담", "scope": {"kind": "watchlist", "id": "NVDA", "tickers": ["NVDA"]}})
    session_id = created["id"]
    message = boundary.add_consultation_message(session_id, {"message": "무엇이 바뀌었나?", "operationId": "op-http"})
    assert message["job"]["id"] == "job-1"
    note = boundary.consultation_note(session_id, {"preview": True, "noteType": "company_thesis"})
    assert note["persisted"] is False
    assert note["note"]["consultationRef"] == session_id
    with pytest.raises(HTTPException) as error:
        boundary.delete_consultation(session_id, {"confirm": False})
    assert error.value.status_code == 400
    with pytest.raises(HTTPException) as error:
        boundary.delete_consultation(session_id, {"confirm": True})
    assert error.value.status_code == 409 and error.value.detail == "consultation_not_empty"
    empty = boundary.create_consultation({"title": "빈 대화", "scope": {"kind": "general"}})
    assert boundary.delete_consultation(empty["id"], {"confirm": True})["deleted"] is True


def test_get_consultation_message_route_returns_the_message_or_404(tmp_path):
    """Agent Dock Stage C: 단일 메시지 endpoint — 전체 스레드 재조회의 대안."""
    from features.agent_mode import routes

    boundary = routes.AgentCompanionBoundary(object(), data_dir=tmp_path)
    session = boundary.create_consultation({"title": "대화", "scope": {"kind": "general"}})
    appended = store.append_user_message(tmp_path, session["id"], "질문", operation_id="op-single")
    store.append_assistant_message(tmp_path, session["id"], appended["message"]["id"], "답변 본문")
    reply_id = store.get_session(tmp_path, session["id"])["messages"][-1]["id"]

    message = boundary.get_consultation_message(session["id"], reply_id)
    assert message["content"] == "답변 본문"
    assert message["role"] == "assistant"

    with pytest.raises(HTTPException) as error:
        boundary.get_consultation_message(session["id"], "msg-missing")
    assert error.value.status_code == 404

    with pytest.raises(HTTPException) as error:
        boundary.get_consultation_message("session-missing", reply_id)
    assert error.value.status_code == 404


def test_assistant_message_carries_bounded_search_metadata_when_given(tmp_path):
    """Agent Dock Stage D: `search` 메타데이터는 옵션이고 저장되면 그대로 읽힌다.
    없으면(대부분의 기존 메시지) 필드 자체가 없다 — 기본값을 지어내지 않는다."""
    session = store.create_session(tmp_path, {"scope": {"kind": "general"}})
    appended = store.append_user_message(tmp_path, session["id"], "질문", operation_id="op-search")
    search_meta = {
        "requestedPolicy": "on", "toolEnabled": True, "toolUsed": "yes",
        "sourceRefs": [{"url": "https://www.reuters.com/x", "tier": "media", "label": "Reuters"}],
    }
    store.append_assistant_message(tmp_path, session["id"], appended["message"]["id"], "답변", search=search_meta)

    saved = store.get_session(tmp_path, session["id"])["messages"][-1]
    assert saved["search"] == search_meta

    without_search = store.create_session(tmp_path, {"scope": {"kind": "general"}})
    other_appended = store.append_user_message(tmp_path, without_search["id"], "질문2", operation_id="op-no-search")
    store.append_assistant_message(tmp_path, without_search["id"], other_appended["message"]["id"], "답변2")
    plain_saved = store.get_session(tmp_path, without_search["id"])["messages"][-1]
    assert "search" not in plain_saved


def test_delete_requires_json_true_not_truthy_string(tmp_path, monkeypatch):
    """삭제는 복구 불가라 "false" 같은 문자열이 동의로 통과하면 안 된다."""
    from features.agent_mode import routes

    monkeypatch.setattr(routes, "submit_consultation_job", lambda *_a, **_k: {"id": "j", "status": "queued"})
    boundary = routes.AgentCompanionBoundary(object(), data_dir=tmp_path)
    created = boundary.create_consultation({"title": "t", "scope": {"kind": "portfolio"}})
    for value in ("false", "no", "0", 1, "true"):
        with pytest.raises(HTTPException) as error:
            boundary.delete_consultation(created["id"], {"confirm": value})
        assert error.value.status_code == 400
    assert boundary.delete_consultation(created["id"], {"confirm": True})["deleted"] is True


def test_job_submit_failure_keeps_persisted_user_turn_and_blocks_empty_cleanup(tmp_path, monkeypatch):
    """The message append is durable before job submission, so cleanup cannot erase it."""
    from features.agent_mode import routes

    def fail_submit(*_args, **_kwargs):
        raise RuntimeError("job_submit_failed")

    monkeypatch.setattr(routes, "submit_consultation_job", fail_submit)
    boundary = routes.AgentCompanionBoundary(object(), data_dir=tmp_path)
    created = boundary.create_consultation({"scope": {"kind": "portfolio"}})
    with pytest.raises(RuntimeError, match="job_submit_failed"):
        boundary.add_consultation_message(created["id"], {"message": "저장된 질문", "operationId": "post-fails"})
    session = boundary.get_consultation(created["id"])
    assert len(session["messages"]) == 1 and session["messages"][0]["content"] == "저장된 질문"
    with pytest.raises(HTTPException) as error:
        boundary.delete_consultation(created["id"], {"confirm": True})
    assert error.value.status_code == 409 and error.value.detail == "consultation_not_empty"


def test_submit_consultation_job_runs_for_real_not_only_as_a_stub(tmp_path, monkeypatch):
    """도크가 실제로 부르는 경로. HTTP 테스트가 이 함수를 통째로 대체해 왔기 때문에
    본문이 깨져도(예: import 누락) 초록으로 남았다. 잡 실행만 가로채고 본문은 돌린다."""
    from features.common import jobs
    from features.agent_mode import job_runtime

    captured = {}

    def fake_submit(kind, label, fn, *args, **kwargs):
        captured["kind"] = kind
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"id": "job-real", "status": "queued"}

    monkeypatch.setattr(jobs, "submit_job", fake_submit)
    session = create_session(tmp_path, {"title": "실경로", "scope": {"kind": "general"}})
    appended = append_user_message(tmp_path, session["id"], "무엇이 바뀌었나?", operation_id="op-real")

    job = job_runtime.submit_consultation_job(tmp_path, session["id"], appended["message"]["id"])

    assert job["generationMode"] == "llm_cli"
    assert captured["args"][0] == Path(tmp_path)
    assert captured["args"][1] == session["id"]


def test_the_first_question_becomes_the_title(tmp_path):
    """목록에서 대화를 알아볼 단서는 제목뿐이다. 전부 "새 대화"면 읽히지 않는다."""
    session = create_session(tmp_path, {"scope": {"kind": "general"}})
    assert session["title"] == "새 대화"

    append_user_message(tmp_path, session["id"], "HWM 공시 서술이 왜 비었는지 확인해줘", operation_id="op-title")

    from features.agent_mode.consultation_store import get_session

    assert get_session(tmp_path, session["id"])["title"] == "HWM 공시 서술이 왜 비었는지 확인해줘"


def test_a_title_the_user_set_is_not_overwritten(tmp_path):
    from features.agent_mode.consultation_store import get_session

    session = create_session(tmp_path, {"title": "내가 정한 제목", "scope": {"kind": "general"}})
    append_user_message(tmp_path, session["id"], "질문", operation_id="op-keep")
    assert get_session(tmp_path, session["id"])["title"] == "내가 정한 제목"


def test_a_long_question_is_trimmed_for_the_list(tmp_path):
    from features.agent_mode.consultation_store import get_session

    session = create_session(tmp_path, {"scope": {"kind": "general"}})
    append_user_message(tmp_path, session["id"], "가" * 200, operation_id="op-long")
    title = get_session(tmp_path, session["id"])["title"]
    assert len(title) <= 40 and title.endswith("…")
