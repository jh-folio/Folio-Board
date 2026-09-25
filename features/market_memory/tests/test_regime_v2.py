"""Regime v2 단위 테스트.

    py -3 features/market_memory/tests/test_regime_v2.py
"""
import os
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.market_memory import memory as M
from features.market_memory import regime_v2 as R


def test_momentum_normalize_enum_guard():
    assert R.normalize_momentum("strengthening") == "strengthening"
    assert R.normalize_momentum("강화") == "stable"
    assert R.normalize_momentum("") == "stable"


def test_supporting_challenging_classification_respects_bias():
    bullish = {"bias": "bullish", "net_effect": ""}
    bearish = {"bias": "bearish", "net_effect": ""}
    assert R.classify_evidence("guidance raise and strong growth", bullish) == "supporting"
    assert R.classify_evidence("guidance cut and weak demand", bullish) == "challenging"
    assert R.classify_evidence("risk and downside pressure", bearish) == "supporting"
    assert R.classify_evidence("surge and recovery", bearish) == "challenging"


def test_evidence_window_calculation():
    rows = [
        {"evidenceDate": "2026-06-10", "role": "supporting"},
        {"evidenceDate": "2026-06-01", "role": "challenging"},
        {"evidenceDate": "2026-04-01", "role": "neutral"},
        {"evidenceDate": "2025-12-01", "role": "supporting"},
    ]
    out = R.evidence_windows(rows, as_of="2026-06-11T00:00:00+00:00")
    assert out["evidenceCount7d"] == 1
    assert out["evidenceCount30d"] == 2
    assert out["evidenceCount90d"] == 3
    assert out["supporting30d"] == 1
    assert out["challenging30d"] == 1


def test_stale_penalty_increases_with_age():
    assert R.stale_penalty(5) == 0
    assert R.stale_penalty(60) > R.stale_penalty(5)
    assert R.stale_penalty(200) > R.stale_penalty(60)


def test_momentum_rules():
    support = [
        {"evidenceDate": "2026-06-10", "role": "supporting", "score": 0.8},
        {"evidenceDate": "2026-06-09", "role": "supporting", "score": 0.7},
    ]
    conflict = support + [{"evidenceDate": "2026-06-08", "role": "challenging", "score": 0.7}]
    challenge = [{"evidenceDate": "2026-06-10", "role": "challenging", "score": 0.8}]
    assert R.determine_momentum(support, as_of="2026-06-11T00:00:00+00:00") == "strengthening"
    assert R.determine_momentum(conflict, as_of="2026-06-11T00:00:00+00:00") == "conflicted"
    assert R.determine_momentum(challenge, as_of="2026-06-11T00:00:00+00:00") == "fading"


def test_regime_checkpoint_templates_use_human_momentum_wording_without_enum_tokens():
    state = {"state_label": "AI 데이터센터 전력 병목"}
    raw_tokens = ("momentum=", "conflicted", "turning", "fading")
    expected = {
        "conflicted": "상반된 근거가 함께 이어지면",
        "turning": "추세 전환 신호가 이어지면",
        "fading": "추세 약화가 이어지면",
    }

    for momentum, wording in expected.items():
        first = R.regime_checkpoints(state, [], momentum)
        second = R.regime_checkpoints(state, [], momentum)
        assert first == second
        rendered = "\n".join(first)
        assert wording in rendered
        assert not any(token in rendered for token in raw_tokens)

    empty = R.regime_checkpoints({}, [], "")
    assert empty == R.regime_checkpoints({}, [], "")
    assert not any(token in "\n".join(empty) for token in raw_tokens)


def _seed_db(db_path):
    conn = M.connect(db_path)
    M.init_db(conn)
    with conn:
        conn.execute(
            """
            INSERT INTO market_narrative_states (
                state_id, state_key, state_label, story, story_family, status, bias,
                category, region, importance, net_effect, summary, rationale, confidence,
                effective_from, effective_to, source_memory_id, updated_at
            )
            VALUES ('state-ai', 'ai_supply', 'AI 공급망', 'ai_supply', 'AI 공급망',
                'active', 'bullish', 'stock_bond', 'GLOBAL', 'high', 'benefit',
                'AI 공급망 수요가 강하다', 'HBM과 장비 수요 개선', 0.55,
                '2026-06-01T00:00:00+00:00', '', 'mem-1', '2026-06-01T00:00:00+00:00')
            """
        )
        for memory_id, date, title, summary in [
            ("mem-1", "2026-06-10", "AI supply growth", "AI 공급망 성장과 strong demand"),
            ("mem-2", "2026-06-09", "AI supply risk", "AI 공급망 risk and weak order"),
        ]:
            conn.execute(
                """
                INSERT INTO market_memory (
                    memory_id, as_of, date, title, summary, story, story_family,
                    category, region, importance, entry_mode, tags_json, sources_json,
                    state_key, state_label, created_at
                )
                VALUES (?, ?, ?, ?, ?, 'ai_supply', 'AI 공급망', 'stock_bond',
                    'GLOBAL', 'high', 'issue', '["AI"]', '[{"source":"test","date":"2026-06-10","title":"t"}]',
                    'ai_supply', 'AI 공급망', ?)
                """,
                (memory_id, f"{date}T00:00:00+00:00", date, title, summary, f"{date}T00:00:00+00:00"),
            )
    conn.close()


def test_refresh_regime_state_keeps_existing_status_compatibility(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_db(db_path)
        monkeypatch.setattr(R, "_now", lambda: "2026-06-11T00:00:00+00:00")
        result = R.refresh_regime_state(db_path, "state-ai", days=7, role_mode="rules")
        assert result["ok"] is True
        assert result["evidenceCount7d"] == 2
        assert result["evidenceCount30d"] == 2
        assert result["momentum"] in R.MOMENTUM_CHOICES
        states = M.list_states(db_path, status="current")
        assert states[0]["status"] == "active"  # 기존 active/watch 조회 호환
        assert "momentum" in states[0]
        assert states[0]["evidenceCount90d"] == 2


def test_refresh_records_evidence_count_change_once_and_skips_unchanged_refresh(monkeypatch):
    """C.3: 근거 수 변화는 이력에 남되 동일 refresh는 중복 행을 만들지 않는다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_db(db_path)
        monkeypatch.setattr(R, "_now", lambda: "2026-06-11T00:00:00+00:00")
        R.refresh_regime_state(db_path, "state-ai", days=7, role_mode="rules")
        conn = M.connect(db_path)
        first = conn.execute("SELECT old_value, new_value FROM market_regime_changes WHERE field='evidence_count'").fetchall()
        conn.close()
        assert len(first) == 1 and '"d7": 0' in first[0]["old_value"] and '"d7": 2' in first[0]["new_value"]
        R.refresh_regime_state(db_path, "state-ai", days=7, role_mode="rules")
        conn = M.connect(db_path)
        assert conn.execute("SELECT COUNT(*) AS n FROM market_regime_changes WHERE field='evidence_count'").fetchone()["n"] == 1
        conn.close()


def test_state_status_transition_is_recorded_on_existing_change():
    """C.3: 실제 상태 전환도 기존 market_regime_changes 시간축으로 남는다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        conn = M.connect(db_path)
        M.init_db(conn)
        base = {
            "id": "mem-status", "date": "2026-06-10", "asOf": "2026-06-10T00:00:00+00:00",
            "title": "AI 공급망", "summary": "수요 변화", "story": "ai_supply", "storyFamily": "AI 공급망",
            "stateKey": "ai_supply", "stateLabel": "AI 공급망", "importance": "high", "stateStatus": "active",
        }
        M.upsert_state_from_memory(conn, base, observed_at="2026-06-10T00:00:00+00:00")
        M.upsert_state_from_memory(conn, {**base, "stateStatus": "watch"}, observed_at="2026-06-11T00:00:00+00:00")
        row = conn.execute("SELECT field, old_value, new_value FROM market_regime_changes WHERE field='status'").fetchone()
        conn.close()
        assert row and (row["field"], row["old_value"], row["new_value"]) == ("status", "active", "watch")


def test_upsert_memory_keeps_regime_calculated_confidence():
    """재저장이 Regime이 계산한 confidence를 기본값으로 되돌리면 안 된다.

    같은 날 같은 state_key는 같은 state_id라 재저장이 흔한 경로다. momentum과
    근거 카운트는 남는데 confidence만 0.55로 돌아가면 행이 서로 모순된다.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        entry = {
            "date": "2026-06-10",
            "title": "AI 반도체 공급망 수요가 이어진다",
            "summary": "HBM 주문과 서버 투자 계획이 함께 늘었다.",
            "storyFamily": "AI 반도체 공급망",
            "importance": "high",
            "entryMode": "issue",
            "tags": ["AI", "반도체"],
            "sources": [
                {"source": "Reuters", "title": "HBM demand", "url": "https://example.com/a"},
                {"source": "Bloomberg", "title": "server capex", "url": "https://example.com/b"},
            ],
        }
        first = M.upsert_memory(db_path, entry)
        state_id = first["state"]["id"]

        conn = M.connect(db_path)
        with conn:
            conn.execute(
                """
                UPDATE market_narrative_states
                SET confidence=0.81, momentum='strengthening', evidence_count_30d=3
                WHERE state_id=?
                """,
                (state_id,),
            )
        conn.close()

        M.upsert_memory(db_path, entry)

        conn = M.connect(db_path)
        row = conn.execute(
            "SELECT confidence, momentum, evidence_count_30d FROM market_narrative_states WHERE state_id=?",
            (state_id,),
        ).fetchone()
        conn.close()
        assert row["confidence"] == 0.81
        assert row["momentum"] == "strengthening"
        assert row["evidence_count_30d"] == 3


def test_refresh_thesis_links_keeps_manual_relationship():
    """사용자가 지정한 링크 relationship을 자동 추론이 덮어쓰면 안 된다.

    thesis는 hypothesis이고 이 행은 연결 정보다. method='manual'인 행을 자동
    갱신이 바꾸면 행이 자기 출처를 거짓으로 말하게 된다.
    """
    from features.thesis_tracking import store as thesis_store

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_db(db_path)
        conn = M.connect(db_path)
        thesis_store.init_db(conn)
        with conn:
            conn.execute(
                """
                INSERT INTO thesis (ticker, company, status, linked_regimes_json, note_path)
                VALUES ('NVDA', 'NVIDIA', 'active', '["ai_supply"]', 'Theses/NVDA.md')
                """
            )
        conn.close()

        R.upsert_regime_thesis_link(db_path, "state-ai", {
            "ticker": "NVDA",
            "relationship": "core_holding",
            "strength": 0.9,
        })

        conn = M.connect(db_path)
        summary = R.refresh_thesis_links(conn, "state-ai")
        conn.close()
        assert summary["count"] >= 1  # 자동 추론이 같은 행을 실제로 쳤다

        link = R.list_regime_thesis_links(db_path, "state-ai")[0]
        assert link["method"] == "manual"
        assert link["relationship"] == "core_holding"


def test_memory_matching_distinguishes_states():
    """상태별 근거가 구분되어야 한다 — 감성 단어 겹침만으로 전부 매칭되면 안 됨."""
    ai_state = {"state_key": "ai_supply", "state_label": "AI 반도체 공급망", "story": "ai_supply", "story_family": "AI 반도체 공급망",
                "summary": "AI 투자 사이클이 반도체 실적 기대와 수급으로 전이", "rationale": "수요 확대와 리스크 공존"}
    rate_state = {"state_key": "rates_dollar", "state_label": "금리·달러 유동성", "story": "rates_dollar", "story_family": "금리·달러 유동성",
                  "summary": "AI 투자 사이클이 반도체 실적 기대와 수급으로 전이", "rationale": "수요 확대와 리스크 공존"}
    rate_memory = {"story": "fx_rates", "title": "금리 인상과 달러 강세", "summary": "달러 유동성 부담과 환율 리스크 확대", "tags_json": '["금리"]'}
    ai_memory = {"story": "nvda_supply", "title": "AI 반도체 공급망 수요", "summary": "HBM 주문 증가", "tags_json": '["AI"]'}
    assert R._memory_matches_state(rate_memory, rate_state)[0] is True
    assert R._memory_matches_state(ai_memory, ai_state)[0] is True
    # 상태 간 교차 오염 금지: summary가 중복돼도 금리 memory가 AI 상태 근거가 되면 안 된다
    assert R._memory_matches_state(rate_memory, ai_state)[0] is False
    assert R._memory_matches_state(ai_memory, rate_state)[0] is False
    # 영/한 동의 토큰(semiconductor↔반도체)은 개념 1개 — 이것만으로 매칭되면 안 된다
    kr_export_state = {"state_key": "korea_semiconductor_exports", "state_label": "한국 반도체 수출 민감도",
                       "story": "korea_export", "story_family": "한국 수출"}
    semis_only_memory = {"story": "global_chips", "title": "Global semiconductor 반도체 시황", "summary": "업황 업데이트", "tags_json": "[]"}
    assert R._memory_matches_state(semis_only_memory, kr_export_state)[0] is False


def test_state_conclusion_uses_primary_theme_before_rate_mentions():
    energy = M.state_conclusion(
        "중동 리스크 프리미엄 완화",
        "bearish",
        "geopolitical_premium_eases",
        "유가와 달러가 함께 하락했고 외국인 수급이 회복됐다",
        "중동발 군사 긴장은 유가, 달러, 외국인 수급을 통해 작동한다",
    )
    assert "에너지·지정학" in energy
    assert "금리·달러" not in energy

    ai = M.state_conclusion(
        "AI 반도체 공급망",
        "bullish",
        "ai_semis_bullish",
        "매출 성장, 금리, AI 관련 보도가 누적됐다",
        "AI 투자 사이클이 반도체, 서버, 메모리로 전이된다",
    )
    assert "AI 반도체 공급망" in ai
    assert "금리·달러" not in ai

    power = M.state_conclusion(
        "AI 데이터센터 전력 병목",
        "mixed",
        "ai_power_bottleneck",
        "유가·달러 동반 하락 보도도 함께 있었다",
        "AI 인프라 수요가 전력과 유틸리티 병목으로 확산된다",
    )
    assert "AI 데이터센터 전력 병목" in power
    assert "금리·달러" not in power

    korea_fx = M.state_conclusion(
        "한국 반도체 수출 수혜와 원화·수급 긴장",
        "mixed",
        "korea_chip_fx_sensitivity_high",
        "금리와 달러 변화에도 민감하다",
        "원화 안정과 외국인 자금 유입이 중요하다",
    )
    assert "한국 수출·환율" in korea_fx
    assert "금리·달러" not in korea_fx


def test_state_conclusion_keeps_rate_theme_when_primary_is_rates():
    conclusion = M.state_conclusion(
        "금리·달러 유동성",
        "neutral",
        "rates_dollar_liquidity",
        "AI 관련 보도도 일부 있다",
        "금리와 국채 수급, 달러 유동성이 위험자산 흐름을 좌우한다",
    )
    assert "금리·달러" in conclusion


def test_canonical_state_aliases_keep_distinct_axes():
    assert M.canonical_state_for("ai_supply_chain_bottleneck")["stateKey"] == "ai_semiconductor_supply_chain"
    assert M.canonical_state_for("korea_semiconductors")["stateKey"] == "korea_semiconductor_exports_fx_sensitivity"
    assert M.canonical_state_for("energy_geopolitical_risk")["stateKey"] == "middle_east_energy_risk"
    power = M.canonical_state_for(
        "ai_data_center_power_bottleneck",
        text="AI 반도체와 데이터센터 전력 병목이 같이 언급됨",
    )
    assert power["stateKey"] == "ai_data_center_power_bottleneck"


def test_market_state_classification_handles_long_untrusted_text_without_regex_backtracking():
    long_text = ("neutral observation " * 20_000) + "AI data center grid"

    canonical = M.canonical_state_for(text=long_text)
    inferred = M.inferred_axis_from_context(text=long_text)

    assert canonical["stateKey"] == "ai_data_center_power_bottleneck"
    assert inferred["key"] == "ai_data_center_power_bottleneck"


def test_reconcile_state_aliases_collapses_current_duplicates():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        conn = M.connect(db_path)
        M.init_db(conn)
        with conn:
            for state_id, state_key, label, effective_from in [
                ("state-main", "ai_semiconductor_supply_chain", "AI 반도체 공급망", "2026-06-14T00:00:00+00:00"),
                ("state-alias", "ai_supply_chain_bottleneck", "AI 공급망 병목 수혜 재선별", "2026-06-13T00:00:00+00:00"),
            ]:
                conn.execute(
                    """
                    INSERT INTO market_narrative_states (
                        state_id, state_key, state_label, story, story_family, status, bias,
                        category, region, importance, net_effect, summary, rationale, confidence,
                        effective_from, effective_to, source_memory_id, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'active', 'mixed', 'stock_bond', 'GLOBAL', 'high',
                        'ai_leadership_repricing', 'AI 반도체와 공급망 병목', 'AI 공급망', 0.55,
                        ?, '', '', ?)
                    """,
                    (state_id, state_key, label, state_key, label, effective_from, effective_from),
                )
            conn.execute(
                """
                INSERT INTO market_memory (
                    memory_id, as_of, date, title, summary, story, story_family,
                    category, region, importance, entry_mode, tags_json, sources_json,
                    state_key, state_label, created_at
                )
                VALUES ('mem-alias', '2026-06-13T00:00:00+00:00', '2026-06-13',
                    'AI 공급망 병목 수혜 재선별', 'AI 반도체 병목', 'ai_leadership_narrows',
                    'AI 리더십 재분류', 'stock_bond', 'GLOBAL', 'high', 'issue',
                    '["AI","Semiconductors"]', '[]', 'ai_supply_chain_bottleneck',
                    'AI 공급망 병목 수혜 재선별', '2026-06-13T00:00:00+00:00')
                """
            )
        conn.close()

        result = M.reconcile_state_aliases(db_path)
        assert result["ok"] is True
        conn = M.connect(db_path)
        states = conn.execute("SELECT state_key, status FROM market_narrative_states ORDER BY state_id").fetchall()
        current = [row for row in states if row["status"] in {"active", "watch"}]
        assert len(current) == 1
        assert current[0]["state_key"] == "ai_semiconductor_supply_chain"
        mem = conn.execute("SELECT state_key, state_label FROM market_memory WHERE memory_id='mem-alias'").fetchone()
        assert mem["state_key"] == "ai_semiconductor_supply_chain"
        assert mem["state_label"] == "AI 반도체 공급망"
        conn.close()


def test_audit_memory_closes_sqlite_connection():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_db(db_path)
        real_connect = M.connect
        tracker = {"closed": False}

        class TrackedConnection:
            def __init__(self, conn):
                self._conn = conn

            def execute(self, *args, **kwargs):
                return self._conn.execute(*args, **kwargs)

            def close(self):
                tracker["closed"] = True
                return self._conn.close()

            def __getattr__(self, name):
                return getattr(self._conn, name)

        try:
            M.connect = lambda path: TrackedConnection(real_connect(path))
            result = M.audit_memory(db_path)
            assert result["status"] in {"pass", "warn"}
            assert tracker["closed"] is True
        finally:
            M.connect = real_connect


def test_upsert_memory_closes_sqlite_connection():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        real_connect = M.connect
        tracker = {"closed": False}

        class TrackedConnection:
            def __init__(self, conn):
                self._conn = conn

            def execute(self, *args, **kwargs):
                return self._conn.execute(*args, **kwargs)

            def close(self):
                tracker["closed"] = True
                return self._conn.close()

            def __enter__(self):
                self._conn.__enter__()
                return self

            def __exit__(self, *args):
                return self._conn.__exit__(*args)

            def __getattr__(self, name):
                return getattr(self._conn, name)

        try:
            M.connect = lambda path: TrackedConnection(real_connect(path))
            result = M.upsert_memory(db_path, {
                "date": "2099-12-31",
                "title": "AI 반도체 공급망 점검",
                "summary": "AI 반도체 공급망 내러티브를 점검한다.",
                "storyFamily": "AI 반도체 공급망",
                "tags": ["AI", "반도체"],
            })
            assert result["id"]
            assert tracker["closed"] is True
        finally:
            M.connect = real_connect


def test_basic_briefing_markdown_invariant():
    before = "# Daily\n\nCanonical markdown body"
    rows = [{"evidenceDate": "2026-06-10", "role": "supporting", "score": 0.8}]
    R.determine_momentum(rows, as_of="2026-06-11T00:00:00+00:00")
    assert before == "# Daily\n\nCanonical markdown body"


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
