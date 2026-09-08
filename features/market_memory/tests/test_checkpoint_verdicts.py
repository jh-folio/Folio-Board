"""체크포인트 판정 pass와 규칙 갱신 생존(병합) 테스트.

    py -3 features/market_memory/tests/test_checkpoint_verdicts.py

네트워크와 실제 워크스페이스 DB를 건드리지 않는다 — 전부 임시 SQLite 파일이다.
"""
import json
import os
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.market_memory import memory as M
from features.market_memory import regime_v2 as R
from features.market_memory.checkpoint_verdicts import (
    apply_verdict,
    evaluate_checkpoint,
    matches_checkpoint,
    merge_state_checkpoints,
    run_checkpoint_verdicts,
)

STATE_ID = "state-power"
AS_OF = "2026-08-30T00:00:00+00:00"


def _structured(**overrides):
    base = {
        "item": "전력 설비 기업 실적 가이던스 상향",
        "direction": "supporting",
        "matchers": {"tickers": ["GEV"], "keywords": ["가이던스 상향"]},
        "status": "open",
        "createdAt": "2026-08-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def _row(**overrides):
    base = {
        "memoryId": "mem-1",
        "evidenceDate": "2026-08-20",
        "role": "supporting",
        "score": 0.8,
        "title": "전력기기 기업 가이던스상향",
        "summary": "수주잔고가 늘었다",
        "matchedTerms": ["전력", "데이터센터"],
    }
    base.update(overrides)
    return base


# --- 매칭 ---------------------------------------------------------------

def test_keyword_matching_ignores_whitespace():
    """한국어 복합어 띄어쓰기 편차 — 글쓴이 습관이 판정을 가르면 안 된다."""
    checkpoint = _structured()
    assert matches_checkpoint(checkpoint, _row(title="가이던스 상향 발표"))
    assert matches_checkpoint(checkpoint, _row(title="가이던스상향 발표"))
    assert matches_checkpoint(checkpoint, _row(title="무관한 제목", summary="사측이 가이던스  상향을 밝혔다"))
    assert not matches_checkpoint(checkpoint, _row(title="무관한 제목", summary="무관한 요약", matchedTerms=[]))


def test_ticker_matches_only_through_matched_terms():
    """본문에서 티커를 찾지 않는다 — 짧은 티커가 우연히 걸리면 남의 기사가 확인 신호가 된다."""
    checkpoint = _structured(matchers={"tickers": ["GEV"], "keywords": ["없는키워드"]})
    assert matches_checkpoint(checkpoint, _row(title="무관", summary="무관", matchedTerms=["gev"]))
    assert not matches_checkpoint(checkpoint, _row(title="GEV 실적", summary="", matchedTerms=["전력"]))


# --- 과잉 판정 방지 4겹 --------------------------------------------------

def test_neutral_role_is_never_counted():
    """실측 898행 중 364행이 neutral — 이걸 세면 매일 confirmed가 된다."""
    out = evaluate_checkpoint(_structured(), [_row(role="neutral")], as_of=AS_OF)
    assert out["verdict"] == "no_signal"


def test_role_decides_the_verdict_counter_evidence_alone_counts():
    """role이 판정을 정한다 — 반증 단독이 무시되면(옛 direction 정합 규칙) 반증+지지
    혼합보다 반증 단독이 약해지는 비대칭이 생긴다(2026-08-30 리뷰)."""
    challenging_only = evaluate_checkpoint(_structured(), [_row(role="challenging")], as_of=AS_OF)
    assert challenging_only["verdict"] == "challenged"
    aligned = evaluate_checkpoint(_structured(), [_row(role="supporting")], as_of=AS_OF)
    assert aligned["verdict"] == "confirmed"


def test_low_score_evidence_is_ignored():
    assert evaluate_checkpoint(_structured(), [_row(score=0.49)], as_of=AS_OF)["verdict"] == "no_signal"
    assert evaluate_checkpoint(_structured(), [_row(score=0.5)], as_of=AS_OF)["verdict"] == "confirmed"


def test_both_directions_hit_prefers_challenged():
    """확증편향 방지는 반증에 우선권을 준다(§5 원칙 3)."""
    rows = [_row(memoryId="mem-a", role="supporting"), _row(memoryId="mem-b", role="challenging")]
    out = evaluate_checkpoint(_structured(), rows, as_of=AS_OF)
    assert out["verdict"] == "challenged"
    assert out["evidence"][0]["role"] == "challenging"


def test_refuting_evidence_survives_the_copy_cap():
    """지지 3건이 더 최신이어도 반증 행이 사본에서 잘리면, challenged 배지 아래
    확인 기사만 보여 사용자가 판정을 눈으로 검증할 수 없다(2026-08-30 리뷰)."""
    rows = [
        _row(memoryId="mem-c", role="challenging", evidenceDate="2026-08-21"),
        _row(memoryId="mem-s1", role="supporting", evidenceDate="2026-08-27"),
        _row(memoryId="mem-s2", role="supporting", evidenceDate="2026-08-27"),
        _row(memoryId="mem-s3", role="supporting", evidenceDate="2026-08-27"),
    ]
    out = evaluate_checkpoint(_structured(), rows, as_of=AS_OF)
    assert out["verdict"] == "challenged"
    assert out["evidence"][0]["memoryId"] == "mem-c"  # 반증이 먼저 실린다


def test_same_day_counter_evidence_can_flip_a_morning_verdict():
    """오전 판정 뒤 같은 날짜로 들어온 반증이 영구 스킵되면 confirmed가 하루 종일
    눌러앉는다 — 마지막 verdict '날짜'는 다시 본다(strict `<` skip)."""
    checkpoint = _structured(
        status="confirmed",
        lastVerdict={"verdict": "confirmed", "at": "2026-08-27T01:00:00+00:00", "evidence": []},
    )
    afternoon = _row(role="challenging", evidenceDate="2026-08-27")
    out = evaluate_checkpoint(checkpoint, [afternoon], as_of=AS_OF)
    assert out["verdict"] == "challenged"


def test_first_pass_excludes_evidence_from_the_birth_date():
    """체크포인트는 대개 그날의 근거에서 태어난다 — 낳아 준 근거로 즉시 확인되는
    것은 자기확인이다. 첫 판정은 createdAt 날짜를 제외한다."""
    checkpoint = _structured(createdAt="2026-08-20T09:00:00+00:00")
    same_day = evaluate_checkpoint(checkpoint, [_row(evidenceDate="2026-08-20")], as_of=AS_OF)
    assert same_day["verdict"] == "no_signal"
    next_day = evaluate_checkpoint(checkpoint, [_row(evidenceDate="2026-08-21")], as_of=AS_OF)
    assert next_day["verdict"] == "confirmed"


def test_challenging_direction_checkpoint_reports_challenged():
    checkpoint = _structured(item="착공 지연 보도", direction="challenging", matchers={"keywords": ["착공 지연"]})
    out = evaluate_checkpoint(checkpoint, [_row(role="challenging", title="대형 프로젝트 착공지연")], as_of=AS_OF)
    assert out["verdict"] == "challenged"


def test_evidence_copy_uses_memory_id_not_evidence_id():
    """근거 행은 갱신마다 DELETE 후 재삽입이라 evidence_id가 다음 날 사라진다."""
    out = evaluate_checkpoint(_structured(), [_row(memoryId="mem-42")], as_of=AS_OF)
    assert out["evidence"] == [{
        "memoryId": "mem-42", "date": "2026-08-20",
        "title": "전력기기 기업 가이던스상향", "role": "supporting",
    }]


# --- 판정 반영 -----------------------------------------------------------

def test_only_new_evidence_after_last_verdict_counts():
    checkpoint = _structured(
        status="confirmed",
        lastVerdict={"verdict": "confirmed", "at": "2026-08-25T00:00:00+00:00", "evidence": []},
    )
    stale = evaluate_checkpoint(checkpoint, [_row(evidenceDate="2026-08-20")], as_of=AS_OF)
    assert stale["verdict"] == "no_signal"
    fresh = evaluate_checkpoint(checkpoint, [_row(evidenceDate="2026-08-27")], as_of=AS_OF)
    assert fresh["verdict"] == "confirmed"


def test_stale_open_without_due_by_expires_after_ninety_days():
    """LLM이 매일 문구를 조금씩 바꿔 내면 open이 무한히 쌓인다(병합은 open을 자르지
    않는다). 구조 판정 창(90일)을 신호 없이 넘긴 open은 만료된다."""
    old = _structured(createdAt="2026-05-01T00:00:00+00:00")
    result = apply_verdict(old, {"verdict": "no_signal", "evidence": [], "at": AS_OF}, as_of=AS_OF)
    assert result["to"] == "expired"
    fresh = _structured(createdAt="2026-08-01T00:00:00+00:00")
    result = apply_verdict(fresh, {"verdict": "no_signal", "evidence": [], "at": AS_OF}, as_of=AS_OF)
    assert result["changed"] is False and fresh["status"] == "open"


def test_roleless_pool_ignores_rows_when_direction_is_not_an_enum():
    """정규화 안 된 dict가 흘러들었을 때 기본이 challenged면, 지지 기사가 가설을
    약화시켰다고 기록된다 — enum 밖 direction은 판정하지 않는다."""
    bad = _structured(direction="긍정")
    out = evaluate_checkpoint(bad, [_row(role="")], as_of=AS_OF, role_pool=False)
    assert out["verdict"] == "no_signal"


def test_no_signal_changes_nothing():
    checkpoint = _structured(status="confirmed", lastVerdict={"verdict": "confirmed", "at": AS_OF, "evidence": []})
    result = apply_verdict(checkpoint, {"verdict": "no_signal", "evidence": [], "at": AS_OF}, as_of=AS_OF)
    assert result["changed"] is False
    assert checkpoint["status"] == "confirmed"
    assert checkpoint["lastVerdict"]["at"] == AS_OF
    assert checkpoint.get("history") in (None, [])


def test_history_only_when_verdict_changes():
    checkpoint = _structured()
    outcome = {"verdict": "confirmed", "evidence": [], "at": AS_OF}
    first = apply_verdict(checkpoint, outcome, as_of=AS_OF)
    second = apply_verdict(checkpoint, {**outcome, "at": "2026-08-31T00:00:00+00:00"}, as_of=AS_OF)
    assert first["changed"] is True and second["changed"] is False
    assert len(checkpoint["history"]) == 1
    flipped = apply_verdict(checkpoint, {"verdict": "challenged", "evidence": [], "at": AS_OF}, as_of=AS_OF)
    assert flipped["changed"] is True
    assert [h["to"] for h in checkpoint["history"]] == ["confirmed", "challenged"]


def test_due_by_expires_only_open_checkpoints_without_verdict():
    expired = _structured(dueBy="2026-08-15")
    result = apply_verdict(expired, {"verdict": "no_signal", "evidence": [], "at": AS_OF}, as_of=AS_OF)
    assert expired["status"] == "expired"
    assert result["verdict"] == "no_signal" and result["to"] == "expired"
    assert expired["history"][-1]["from"] == "open"

    judged = _structured(dueBy="2026-08-15", status="confirmed")
    apply_verdict(judged, {"verdict": "no_signal", "evidence": [], "at": AS_OF}, as_of=AS_OF)
    assert judged["status"] == "confirmed"


# --- DB 경로 -------------------------------------------------------------

def _seed(db_path, *, memories=(), checkpoints=None):
    conn = M.connect(db_path)
    M.init_db(conn)
    with conn:
        conn.execute(
            """
            INSERT INTO market_narrative_states (
                state_id, state_key, state_label, story, story_family, status, bias,
                category, region, importance, net_effect, summary, rationale, confidence,
                effective_from, effective_to, source_memory_id, next_checkpoints_json, updated_at
            )
            VALUES (?, 'ai_power', 'AI 데이터센터 전력 병목', 'ai_power', 'AI 데이터센터 전력 병목',
                'active', 'bullish', 'stock_bond', 'GLOBAL', 'high', 'benefit',
                'AI 데이터센터 전력 수요가 강하다', '전력기기 수주 확인', 0.55,
                '2026-08-01T00:00:00+00:00', '', 'mem-1', ?, '2026-08-01T00:00:00+00:00')
            """,
            (STATE_ID, json.dumps(checkpoints if checkpoints is not None else [], ensure_ascii=False)),
        )
        for memory_id, date, title, summary in memories:
            conn.execute(
                """
                INSERT INTO market_memory (
                    memory_id, as_of, date, title, summary, story, story_family,
                    category, region, importance, entry_mode, tags_json, sources_json,
                    state_key, state_label, created_at
                )
                VALUES (?, ?, ?, ?, ?, 'ai_power', 'AI 데이터센터 전력 병목', 'stock_bond',
                    'GLOBAL', 'high', 'issue', '["AI"]',
                    '[{"source":"test","date":"2026-08-20","title":"t"},{"source":"test2","date":"2026-08-20","title":"t2"}]',
                    'ai_power', 'AI 데이터센터 전력 병목', ?)
                """,
                (memory_id, f"{date}T00:00:00+00:00", date, title, summary, f"{date}T00:00:00+00:00"),
            )
    conn.close()


def _stored_checkpoints(db_path):
    conn = M.connect(db_path)
    row = conn.execute("SELECT next_checkpoints_json FROM market_narrative_states WHERE state_id=?", (STATE_ID,)).fetchone()
    conn.close()
    return json.loads(row["next_checkpoints_json"])


def test_structured_checkpoint_survives_two_regime_refreshes(monkeypatch):
    """갱신을 두 번 돌려도 구조화 체크포인트의 status가 살아남는다.

    이 회귀 테스트가 Stage A의 이유다 — 예전에는 `refresh_regime_state`가 목록을
    통째로 덮어써서, 판정 pass가 기록한 status가 다음 갱신에 초기화됐다.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        stored = _structured(
            status="confirmed",
            lastVerdict={"verdict": "confirmed", "at": "2026-08-21T00:00:00+00:00",
                         "evidence": [{"memoryId": "mem-s", "date": "2026-08-20", "title": "t", "role": "supporting"}]},
            history=[{"at": "2026-08-21T00:00:00+00:00", "from": "open", "to": "confirmed", "verdict": "confirmed"}],
        )
        _seed(db_path, memories=[("mem-s", "2026-08-20", "전력기기 가이던스상향", "AI 데이터센터 전력 수요 growth")], checkpoints=[stored, "옛 템플릿 문장"])
        monkeypatch.setattr(R, "_now", lambda: AS_OF)

        R.refresh_regime_state(db_path, STATE_ID, days=90, role_mode="rules")
        R.refresh_regime_state(db_path, STATE_ID, days=90, role_mode="rules")

        checkpoints = _stored_checkpoints(db_path)
        survived = [c for c in checkpoints if isinstance(c, dict)]
        templates = [c for c in checkpoints if isinstance(c, str)]
        assert len(survived) == 1
        assert survived[0]["status"] == "confirmed"
        assert survived[0]["lastVerdict"]["verdict"] == "confirmed"
        assert len(survived[0]["history"]) == 1
        assert templates and "옛 템플릿 문장" not in templates      # 템플릿만 오늘 것으로 갈아끼운다


def test_verdict_pass_records_change_and_is_idempotent(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed(
            db_path,
            memories=[("mem-s", "2026-08-20", "전력기기 실적 가이던스상향", "AI 데이터센터 전력 수요가 strong growth")],
            checkpoints=[_structured()],
        )
        monkeypatch.setattr(R, "_now", lambda: AS_OF)
        R.refresh_regime_state(db_path, STATE_ID, days=90, role_mode="rules")

        first = run_checkpoint_verdicts(db_path, as_of=AS_OF)
        assert first["checkpointCount"] == 1
        assert first["changeCount"] == 1
        stored = [c for c in _stored_checkpoints(db_path) if isinstance(c, dict)][0]
        assert stored["status"] == "confirmed"
        assert stored["lastVerdict"]["evidence"][0]["memoryId"] == "mem-s"

        changes = R.list_regime_changes(db_path, STATE_ID)
        checkpoint_changes = [c for c in changes if c["field"].startswith("checkpoint:")]
        assert len(checkpoint_changes) == 1
        assert checkpoint_changes[0]["newValue"] == "confirmed"
        # momentum/confidence 변경 행은 진짜 evidence_id를 싣는 컬럼이라, memory_id
        # 사본은 `memory:` 접두로 이름공간을 가른다.
        assert checkpoint_changes[0]["evidenceIds"] == ["memory:mem-s"]

        # 같은 날 두 번 돌아도 안전하다 — 새 근거가 없으므로 이력이 늘지 않는다.
        second = run_checkpoint_verdicts(db_path, as_of=AS_OF)
        assert second["changeCount"] == 0
        again = [c for c in _stored_checkpoints(db_path) if isinstance(c, dict)][0]
        assert len(again["history"]) == 1
        assert len([c for c in R.list_regime_changes(db_path, STATE_ID) if c["field"].startswith("checkpoint:")]) == 1


def test_template_only_state_produces_no_verdicts(monkeypatch):
    """구조화 체크포인트가 없는 상태(기존 저장본 65건 전부)는 판정 대상이 아니다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed(db_path, memories=[("mem-s", "2026-08-20", "전력기기 가이던스상향", "growth")], checkpoints=["템플릿 문장만 있다"])
        monkeypatch.setattr(R, "_now", lambda: AS_OF)
        R.refresh_regime_state(db_path, STATE_ID, days=90, role_mode="rules")

        result = run_checkpoint_verdicts(db_path, as_of=AS_OF)
        assert result["checkpointCount"] == 0
        assert result["changeCount"] == 0
        assert not [c for c in R.list_regime_changes(db_path, STATE_ID) if c["field"].startswith("checkpoint:")]


def test_invalid_structured_checkpoint_is_preserved_but_not_judged(monkeypatch):
    """저장된 dict의 재검증 실패는 원소가 아니라 규칙 쪽 변화다(라벨 개명 등).
    매일 도는 갱신·판정이 그것을 지우면 체크포인트와 이력이 소리 없이 사라진다 —
    보존하고 판정에서만 뺀다(화면은 `검증 불가` 표시)."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        broken = {"item": "방향이 없는 항목", "matchers": {"keywords": ["가이던스"]}}
        _seed(db_path, memories=[("mem-s", "2026-08-20", "가이던스상향", "growth")], checkpoints=[broken])
        monkeypatch.setattr(R, "_now", lambda: AS_OF)
        R.refresh_regime_state(db_path, STATE_ID, days=90, role_mode="rules")

        result = run_checkpoint_verdicts(db_path, as_of=AS_OF)
        assert result["checkpointCount"] == 0                     # 판정 대상 아님
        checkpoints = _stored_checkpoints(db_path)
        assert [c for c in checkpoints if isinstance(c, dict)] == [broken]  # 갱신·판정을 거쳐도 보존
        assert [c for c in checkpoints if isinstance(c, str)]     # 화면이 비지 않는다


def test_merge_state_checkpoints_inherits_verdict_state(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed(db_path, checkpoints=[_structured(status="challenged"), "템플릿"])
        out = merge_state_checkpoints(db_path, STATE_ID, [_structured(), _structured(item="새 확인 항목")], as_of=AS_OF)
        assert out["ok"] is True
        stored = [c for c in _stored_checkpoints(db_path) if isinstance(c, dict)]
        by_item = {c["item"]: c for c in stored}
        assert by_item["전력 설비 기업 실적 가이던스 상향"]["status"] == "challenged"
        assert by_item["새 확인 항목"]["status"] == "open"
        assert "템플릿" in _stored_checkpoints(db_path)


def _run_all():
    import pytest
    sys.exit(pytest.main([os.path.abspath(__file__), "-q"]))


if __name__ == "__main__":
    _run_all()
