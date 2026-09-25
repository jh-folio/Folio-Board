import json
import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from features.market_memory.market_state_ref import MarketStateRefQuery
from features.market_memory.snapshot import (
    build_market_state_context,
    current_market_state_snapshot,
    ensure_snapshot_table,
    render_market_memory_context,
    save_market_state_snapshot,
    validate_market_state_snapshot,
)
from features.market_memory.state_dashboard import market_state_dashboard_payload, summarize_market_state


def test_summarize_market_state_returns_one_summary_and_five_drivers():
    states = [
        {"stateLabel": "AI 반도체 공급망", "momentum": "strengthening", "confidence": 0.82, "summary": "AI 공급망 실적 기대가 강화됐다.", "rationale": "HBM 수요 확인", "nextCheckpoints": ["HBM 출하 가이던스"]},
        {"stateLabel": "AI 데이터센터 전력 병목", "momentum": "strengthening", "confidence": 0.7, "summary": "전력 병목이 수혜 범위를 넓힌다.", "rationale": "전력기기 수주 확인", "nextCheckpoints": ["전력기기 수주잔고"]},
        {"stateLabel": "금리·달러 유동성", "momentum": "conflicted", "confidence": 0.58, "summary": "금리와 달러는 성장주 상단을 제한한다.", "rationale": "국채금리 확인"},
        {"stateLabel": "중동 에너지 리스크", "momentum": "stable", "confidence": 0.52, "summary": "유가 리스크는 관망 상태다.", "rationale": "유가 반응 확인"},
        {"stateLabel": "한국 반도체 수출", "momentum": "stable", "confidence": 0.61, "summary": "한국 반도체 수출 기대가 유지된다.", "rationale": "수출 데이터 확인"},
        {"stateLabel": "잡음", "momentum": "stable", "confidence": 0.1, "summary": "숨겨야 한다.", "rationale": ""},
    ]
    payload = summarize_market_state(states, limit=5)
    assert payload["title"] == "현재 중기 시장 상황"
    assert len(payload["drivers"]) == 5
    assert payload["summary"] == "시장이 나쁘지는 않지만, 아무 종목이나 따라 살 장은 아닙니다."
    assert payload["plainConclusion"] == payload["summary"]
    assert "AI 반도체 공급망" not in payload["summary"]
    assert "금리" not in payload["summary"]
    assert payload["watchItems"] == ["HBM 출하 가이던스", "전력기기 수주잔고"]
    assert "핵심 흐름" in payload["stance"]
    assert payload["posture"]["label"] == "선별적"
    assert payload["actionGuide"]["headline"] == "좋은 기업만 골라서 천천히 접근"
    assert "분할" in payload["actionGuide"]["timing"]
    assert [item["label"] for item in payload["briefs"]] == ["현재 판단", "왜 이렇게 보는가", "행동 가이드", "다음 확인"]
    assert payload["briefs"][0]["value"] == payload["summary"]
    assert "AI 반도체 공급망" in payload["reasonSummary"]
    assert "분할" in payload["briefs"][3]["value"]
    assert "rawEvidence" not in payload["drivers"][0]


def test_summarize_market_state_without_drivers_keeps_one_wait_message():
    payload = summarize_market_state([], limit=5)

    assert payload["drivers"] == []
    assert payload["posture"]["label"] == "대기"
    # 안내는 posture 한 곳에서 나온다 — summary가 덮이는 죽은 대입이 남아 있으면 안 된다.
    assert payload["summary"] == "아직 판단할 자료가 부족합니다. 먼저 최신 뉴스와 시장 흐름을 더 모아야 합니다."
    assert payload["plainConclusion"] == payload["summary"]
    assert payload["briefs"][0]["value"] == payload["summary"]
    assert "RSS 수집과 Market Memory 정리" in payload["actionGuide"]["timing"]


def test_driver_headline_prefers_conclusion_and_keeps_condensed_details():
    states = [
        {
            "id": "state-ai",
            "stateLabel": "AI 반도체 공급망",
            "status": "active",
            "momentum": "strengthening",
            "confidence": 0.82,
            "conclusion": "AI 반도체 공급망은 긍정 판단을 유지한다.",
            "summary": "AI 공급망 실적 기대가 강화됐다.",
            "rationale": "HBM 수요 확인",
            "evidenceCount7d": 2,
            "evidenceCount30d": 5,
            "evidenceCount90d": 8,
            "linkedCompanies": ["NVDA", "000660.KS", "005930.KS", "TSM", "AMD"],
            "nextCheckpoints": [{"label": "다음 분기 HBM 출하 가이던스"}],
        },
    ]
    driver = summarize_market_state(states, limit=5)["drivers"][0]
    assert driver["interpretation"] == "AI 반도체 공급망은 긍정 판단을 유지한다."
    assert driver["elaboration"] == "AI 공급망 실적 기대가 강화됐다."
    assert driver["rationale"] == "HBM 수요 확인"
    assert driver["confidencePct"] == 82
    assert driver["evidenceCounts"] == {"d7": 2, "d30": 5, "d90": 8}
    assert driver["linkedCompanies"] == ["NVDA", "000660.KS", "005930.KS", "TSM"]
    assert driver["nextCheckpoint"] == "다음 분기 HBM 출하 가이던스"
    assert driver["directionLabel"] == "도움"
    assert "주식시장에는 도움이 됩니다" in driver["marketImpact"]
    assert driver["evidenceSummary"] == "HBM 수요 확인"
    assert driver["nextMemoryCheck"] == "다음 업데이트에서 다음 분기 HBM 출하 가이던스 변화가 이 판단을 강화하는지 확인합니다."


def test_market_state_stance_becomes_cautious_when_risks_conflict():
    states = [
        {"stateLabel": "금리·달러 유동성", "momentum": "conflicted", "confidence": 0.62, "summary": "금리와 달러가 성장주 상단을 제한한다."},
        {"stateLabel": "중동 에너지 리스크", "momentum": "turning", "confidence": 0.58, "summary": "유가 리스크가 다시 커진다."},
    ]
    payload = summarize_market_state(states, limit=5)
    assert "리스크 점검" in payload["stance"]
    assert payload["posture"]["label"] == "방어적"
    assert payload["summary"] == "시장이 흔들릴 가능성이 크니, 당분간 방어적으로 보는 게 좋습니다."
    assert payload["actionGuide"]["headline"] == "새 매수보다 리스크 점검"
    assert payload["drivers"][0]["directionLabel"] in {"부담", "변동성"}


def test_validate_market_state_snapshot_requires_counter_evidence_and_sources():
    snapshot = validate_market_state_snapshot({
        "headline": "AI 공급망이 시장의 중심축",
        "oneLineSummary": "AI 반도체와 전력 병목이 위험선호를 설명한다.",
        "beginnerSummary": "시장은 아직 괜찮지만, 좋은 기업만 골라서 봐야 합니다.",
        "marketRegime": "risk_on_selective",
        "actionPosture": "추격보다 확인된 수혜와 반대 근거를 함께 점검",
        "actionGuide": {
            "headline": "좋은 기업만 골라서 천천히 접근",
            "action": "보유 종목은 유지하되 새 매수는 선별합니다.",
            "timing": "가격이 쉬거나 근거가 추가될 때 분할로 검토합니다.",
        },
        "keyDrivers": [
            {
                "title": "AI 반도체 공급망",
                "summary": "HBM 수요가 유지된다.",
                "directionLabel": "도움",
                "marketImpact": "관련 성장주에는 도움이 됩니다.",
                "nextMemoryCheck": "다음 업데이트에서 실적 기대가 유지되는지 확인합니다.",
                "evidenceSummary": "HBM 수요 관련 기사 반복",
                "sourceRefs": ["rss:1"],
            },
        ],
        "watchItems": ["HBM 출하 가이던스"],
        "counterEvidence": ["금리 상승은 밸류에이션 상단을 제한한다."],
        "sourceRefs": [{"id": "rss:1", "title": "AI chip demand", "source": "Reuters"}],
        "confidence": 0.82,
    })
    assert snapshot["horizon"] == "medium_term"
    assert snapshot["status"] == "agent_authored"
    assert snapshot["confidence"] == 0.82
    assert snapshot["beginnerSummary"] == "시장은 아직 괜찮지만, 좋은 기업만 골라서 봐야 합니다."
    assert snapshot["actionGuide"]["headline"] == "좋은 기업만 골라서 천천히 접근"
    assert snapshot["keyDrivers"][0]["marketImpact"] == "관련 성장주에는 도움이 됩니다."
    assert snapshot["keyDrivers"][0]["sourceRefs"] == ["rss:1"]


def test_save_and_load_current_market_state_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        saved = save_market_state_snapshot(db_path, {
            "headline": "금리와 AI가 함께 시장을 설명",
            "oneLineSummary": "금리 부담 속에서도 AI 공급망은 강하다.",
            "marketRegime": "selective_growth",
            "actionPosture": "신규 확대보다 체크포인트 확인",
            "keyDrivers": [{"title": "금리·달러 유동성", "summary": "금리가 상단을 제한한다.", "sourceRefs": ["rss:1"]}],
            "watchItems": ["10년물 금리"],
            "counterEvidence": ["AI 실적이 예상보다 강하면 위험선호가 유지된다."],
            "sourceRefs": [{"id": "rss:1", "title": "Yields rise", "source": "Bloomberg"}],
            "confidence": 0.64,
        })
        loaded = current_market_state_snapshot(db_path)
        assert loaded["id"] == saved["id"]
        assert loaded["headline"] == "금리와 AI가 함께 시장을 설명"
        assert loaded["watchItems"] == ["10년물 금리"]


def test_current_market_state_snapshot_normalizes_legacy_thin_market_views():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        ensure_snapshot_table(conn)
        payload = {
            "headline": "종합 시장 판단",
            "oneLineSummary": "미국장은 선별적이고 한국장은 환율 부담을 본다.",
            "marketRegime": "mixed_selective",
            "actionPosture": "시장별로 다른 체크포인트를 본다.",
            "keyDrivers": [{
                "title": "금리",
                "summary": "상단 압력",
                "whyItMatters": "금리는 할인율과 자금 흐름을 바꾼다.",
                "evidenceSummary": "미국 10년물과 달러가 함께 움직였다.",
                "marketImpact": "성장주 밸류에이션에는 부담이다.",
                "sourceRefs": ["rss:1"],
            }],
            "watchItems": ["미국 10년물"],
            "counterEvidence": ["AI 실적이 강하면 위험선호가 유지된다."],
            "sourceRefs": [{"id": "rss:1", "title": "Rates", "source": "Reuters"}],
            "confidence": 0.7,
            "marketViews": {
                "us": {
                    "headline": "미국장",
                    "marketInterpretation": "미국장은 AI 기대가 지수 하단을 받친다.",
                    "actionSummary": "성장주는 실적 확인 후 접근한다.",
                    "keyDrivers": [{"title": "AI 실적", "summary": "성장주 지지"}],
                },
            },
        }
        conn.execute(
            """
            INSERT INTO market_state_snapshots
            (snapshot_id, as_of, horizon, status, headline, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("legacy-thin", "2026-07-01T00:00:00+09:00", "medium_term", "agent_authored", payload["headline"], json.dumps(payload)),
        )
        conn.commit()
        conn.close()

        loaded = current_market_state_snapshot(db_path)

        assert loaded["marketViews"]["us"]["keyDrivers"][0]["whyItMatters"]
        assert loaded["marketViews"]["us"]["keyDrivers"][0]["sourceRefs"] == []


def test_snapshot_driver_keeps_own_checkpoints_and_marks_counts_unavailable():
    snapshot = validate_market_state_snapshot({
        "headline": "종합 시장 판단",
        "oneLineSummary": "시장별로 서로 다른 드라이버를 확인한다.",
        "marketRegime": "mixed",
        "actionPosture": "확인 후 대응",
        "keyDrivers": [{"title": "상위 금리", "summary": "상단 압력", "sourceRefs": ["rss:top"]}],
        "watchItems": ["페이지 전체 확인 항목"],
        "counterEvidence": ["실적 상향"],
        "sourceRefs": [
            {"id": "rss:top", "title": "Top", "source": "Reuters"},
            {"id": "rss:us", "title": "US", "source": "Reuters"},
        ],
        "confidence": 0.7,
        "marketViews": {
            "us": {
                "headline": "미국장",
                "marketInterpretation": "미국장은 드라이버별 확인 항목을 따로 둔다.",
                "keyDrivers": [
                    {
                        "title": "드라이버 A",
                        "summary": "A 판단",
                        "nextMemoryCheck": "A만 다시 확인",
                        "sourceRefs": ["rss:us"],
                    },
                    {"title": "드라이버 B", "summary": "B 판단"},
                ],
                "watchItems": ["미국장 페이지 확인 항목"],
            },
        },
    })
    from features.market_memory.state_dashboard import dashboard_payload_from_snapshot

    payload = dashboard_payload_from_snapshot(snapshot)["marketViews"]["us"]
    first, second = payload["drivers"]

    assert payload["watchItems"] == ["미국장 페이지 확인 항목"]
    assert first["nextCheckpoint"] == "A만 다시 확인"
    assert first["whatToWatch"] == "A만 다시 확인"
    assert first["nextMemoryCheck"] == "A만 다시 확인"
    assert second["nextCheckpoint"] == ""
    assert second["whatToWatch"] == ""
    assert second["nextMemoryCheck"] == ""
    assert first["evidenceCounts"] == {"d7": None, "d30": None, "d90": None}
    assert first["evidenceCountStatus"] == "unavailable"
    assert second["evidenceCounts"] == {"d7": None, "d30": None, "d90": None}
    assert second["evidenceCountStatus"] == "unavailable"
    assert first["elaboration"] == "출처: rss:us"
    assert second["elaboration"] == ""


def test_dashboard_payload_prefers_saved_snapshot_over_rule_summary():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        save_market_state_snapshot(db_path, {
            "headline": "저장된 Agent 시장 판단",
            "oneLineSummary": "RSS 전체와 기존 내러티브를 종합한 판단이다.",
            "beginnerSummary": "지금은 무리하게 따라가기보다 좋은 기업만 골라서 볼 때입니다.",
            "marketRegime": "selective_growth",
            "actionPosture": "확인된 수혜만 선별하고 금리 반전을 확인",
            "actionGuide": {
                "headline": "선별적으로 후보 압축",
                "action": "좋은 기업만 남기고 무리한 추격은 피합니다.",
                "timing": "가격이 쉬거나 근거가 추가될 때 분할로 검토합니다.",
            },
            "keyDrivers": [{
                "title": "AI 공급망",
                "summary": "수요 기대가 유지된다.",
                "directionLabel": "도움",
                "marketImpact": "관련 성장주에는 도움이 됩니다.",
                "nextMemoryCheck": "다음 업데이트에서 수요 기대가 실제 실적으로 이어지는지 확인합니다.",
                "evidenceSummary": "AI 수요 관련 기사",
                "sourceRefs": ["rss:1"],
            }],
            "watchItems": ["엔비디아 가이던스"],
            "counterEvidence": ["금리 상승"],
            "sourceRefs": [{"id": "rss:1", "title": "AI demand", "source": "Reuters"}],
            "confidence": 0.73,
        })
        payload = market_state_dashboard_payload(db_path)
        assert payload["title"] == "저장된 Agent 시장 판단"
        assert payload["summary"] == "지금은 무리하게 따라가기보다 좋은 기업만 골라서 볼 때입니다."
        assert payload["reasonSummary"] == "RSS 전체와 기존 내러티브를 종합한 판단이다."
        assert payload["stance"] == "좋은 기업만 남기고 무리한 추격은 피합니다."
        assert payload["posture"]["label"] == "선별적"
        assert payload["actionGuide"]["headline"] == "선별적으로 후보 압축"
        assert [item["label"] for item in payload["briefs"]] == ["현재 판단", "왜 이렇게 보는가", "행동 가이드", "다음 확인"]
        assert payload["briefs"][1]["value"] == "RSS 전체와 기존 내러티브를 종합한 판단이다."
        assert payload["briefs"][3]["value"] == "가격이 쉬거나 근거가 추가될 때 분할로 검토합니다."
        assert payload["drivers"][0]["directionLabel"] == "도움"
        assert payload["drivers"][0]["marketImpact"] == "관련 성장주에는 도움이 됩니다."
        assert payload["drivers"][0]["interpretation"] == "수요 기대가 유지된다."
        assert payload["drivers"][0]["evidenceSummary"] == "AI 수요 관련 기사"
        assert payload["snapshot"]["status"] == "agent_authored"


def test_dashboard_payload_marks_snapshot_stale_when_memory_is_newer():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        save_market_state_snapshot(db_path, {
            "asOf": "2026-07-06T07:02:42+00:00",
            "headline": "어제 시장 판단",
            "oneLineSummary": "어제 자료 기준 판단이다.",
            "marketRegime": "mixed",
            "actionPosture": "추격보다 확인",
            "keyDrivers": [{"title": "반도체", "summary": "실적 확인", "sourceRefs": ["rss:1"]}],
            "watchItems": ["외국인 수급"],
            "counterEvidence": ["금리 부담"],
            "sourceRefs": [{"id": "rss:1", "title": "Rates", "source": "Reuters"}],
            "confidence": 0.7,
        })
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            INSERT INTO market_memory
            (memory_id, as_of, date, title, summary, story, created_at, source_kind)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "mem-newer",
                "2026-07-07T05:13:23+00:00",
                "2026-07-07",
                "최신 메모리",
                "스냅샷 이후 저장된 메모리",
                "latest_memory",
                "2026-07-07T05:13:23+00:00",
                "agent",
            ),
        )
        conn.commit()
        conn.close()

        payload = market_state_dashboard_payload(db_path)

        assert payload["freshness"]["stale"] is True
        assert payload["freshness"]["snapshotAsOf"] == "2026-07-06T07:02:42+00:00"
        assert payload["freshness"]["latestMemoryAt"] == "2026-07-07T05:13:23+00:00"
        assert payload["freshness"]["latestMemoryTitle"] == "최신 메모리"


def test_dashboard_payload_ignores_newer_rss_digest_for_agent_snapshot_staleness():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        save_market_state_snapshot(db_path, {
            "asOf": "2026-07-07T05:40:29+00:00",
            "headline": "최신 Agent 시장 판단",
            "oneLineSummary": "Agent가 최신 시장 상태를 정리했다.",
            "marketRegime": "mixed",
            "actionPosture": "추격보다 확인",
            "keyDrivers": [{"title": "반도체", "summary": "실적 확인", "sourceRefs": ["rss:1"]}],
            "watchItems": ["외국인 수급"],
            "counterEvidence": ["금리 부담"],
            "sourceRefs": [{"id": "rss:1", "title": "Rates", "source": "Reuters"}],
            "confidence": 0.7,
            "inputWatermarks": {"GLOBAL": None, "US": None, "KR": None},
        })
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            INSERT INTO market_memory
            (memory_id, as_of, date, title, summary, story, created_at, source_kind)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "rss-newer",
                "2026-07-07T05:42:24+00:00",
                "2026-07-07",
                "RSS 단기 신호",
                "스냅샷 이후 자동 digest가 붙었다.",
                "rss_digest",
                "2026-07-07T05:42:24+00:00",
                "rss_digest",
            ),
        )
        conn.commit()
        conn.close()

        payload = market_state_dashboard_payload(
            db_path,
            ref_query=MarketStateRefQuery(
                market_db_path=Path(db_path),
                research_db_path=Path(tmp) / "research-index.sqlite3",
                scope="GLOBAL",
                now=datetime(2026, 7, 7, 6, tzinfo=UTC),
            ),
        )

        assert payload["freshness"]["stale"] is False
        assert payload["freshness"]["latestMemoryTitle"] == ""


def test_build_market_state_context_combines_rss_digest_and_existing_states():
    market_tape = {
        "status": "partial",
        "markets": {
            "us": [{"id": "sp500", "label": "S&P 500", "changePct1d": 0.7, "source": "yfinance"}],
            "kr": [{"id": "kospi", "label": "KOSPI", "changePct1d": -0.2, "source": "yfinance"}],
        },
    }
    macro_snapshot = {
        "status": "partial",
        "items": {
            "us": [{"id": "us10y", "label": "US 10Y", "value": 4.2, "source": "fred"}],
            "kr": [{"id": "kr_base_rate", "label": "한국 기준금리", "value": 2.5, "source": "bok"}],
        },
    }
    context = build_market_state_context(
        rss_items=[
            {"title": "Nvidia HBM demand lifts AI chip suppliers", "media": "Reuters", "summary": "AI demand"},
            {"title": "AI semiconductor supply chain optimism expands", "media": "Bloomberg", "summary": "Chip demand"},
            {"title": "Treasury yields rise as dollar firms", "media": "WSJ", "summary": "Rates"},
        ],
        states=[{"stateLabel": "AI 반도체 공급망", "momentum": "strengthening", "confidence": 0.8, "summary": "기존 상태"}],
        market_tape=market_tape,
        macro_snapshot=macro_snapshot,
    )
    assert len(context["rssCandidates"]) == 3
    assert context["rssCandidates"][0]["id"] == "rss:item:1"
    assert context["rssCandidates"][2]["title"] == "Treasury yields rise as dollar firms"
    assert "marketRelevance" not in context["rssCandidates"][0]
    assert context["shortTermDigest"][0]["stateLabel"] == "AI 반도체 공급망"
    assert context["existingStates"][0]["stateLabel"] == "AI 반도체 공급망"
    assert context["priorUsePolicy"]["role"] == "hypothesis_to_recheck"
    assert "Do not anchor" in context["priorUsePolicy"]["instruction"]
    assert "broad rssCandidates list" in context["instruction"]
    assert "marketTape" in context["instruction"]
    assert "macroSnapshot" in context["instruction"]
    assert "LLM should choose" in context["instruction"]
    assert "invalidate existingStates" in context["instruction"]
    assert context["marketTape"]["markets"]["us"][0]["label"] == "S&P 500"
    assert context["marketTape"]["markets"]["kr"][0]["label"] == "KOSPI"
    assert context["macroSnapshot"]["items"]["us"][0]["source"] == "fred"
    assert context["macroSnapshot"]["items"]["kr"][0]["source"] == "bok"


def test_build_market_state_context_filters_candidates_by_market_scope():
    rss_items = [
        {"title": "S&P 500 futures rise", "media": "Reuters", "summary": "US market", "markets": ["US"]},
        {"title": "코스피 외국인 순매수", "media": "연합뉴스", "summary": "KR market", "markets": ["KR"]},
        {"title": "Oil and dollar shape global risk", "media": "Bloomberg", "summary": "Global", "markets": ["GLOBAL"]},
        {"title": "Lifestyle gadget roundup", "media": "Example", "summary": "No market", "markets": ["UNKNOWN"]},
    ]

    overall = build_market_state_context(rss_items=rss_items, states=[], market_tape={}, macro_snapshot={}, market_scope="overall")
    us = build_market_state_context(rss_items=rss_items, states=[], market_tape={}, macro_snapshot={}, market_scope="us")
    kr = build_market_state_context(rss_items=rss_items, states=[], market_tape={}, macro_snapshot={}, market_scope="kr")

    assert overall["marketScope"] == "overall"
    assert [item["title"] for item in overall["rssCandidates"]] == [
        "S&P 500 futures rise",
        "코스피 외국인 순매수",
        "Oil and dollar shape global risk",
        "Lifestyle gadget roundup",
    ]
    assert [item["title"] for item in us["rssCandidates"]] == ["S&P 500 futures rise", "Oil and dollar shape global risk"]
    assert [item["title"] for item in kr["rssCandidates"]] == ["코스피 외국인 순매수", "Oil and dollar shape global risk"]
    assert us["sourceRefs"][0]["id"] == "rss:item:1"
    assert kr["sourceRefs"][0]["id"] == "rss:item:2"
    assert "supporting evidence" in us["marketDataPolicy"]["role"]
    assert "uncertainties" in us["marketDataPolicy"]["missingDataPolicy"]


def test_build_market_state_context_filters_candidates_for_europe_and_jp():
    """instruction이 '이 목록은 이 marketScope로 걸러졌다'고 보증하므로 실제로 걸러야 한다."""
    rss_items = [
        {"title": "S&P 500 futures rise", "media": "Reuters", "summary": "US market", "markets": ["US"]},
        {"title": "코스피 외국인 순매수", "media": "연합뉴스", "summary": "KR market", "markets": ["KR"]},
        {"title": "DAX slips after ECB comments", "media": "Reuters", "summary": "Europe market", "markets": ["EUROPE"]},
        {"title": "닛케이 반도체주 상승", "media": "Nikkei", "summary": "Japan market", "markets": ["JP"]},
        {"title": "Oil and dollar shape global risk", "media": "Bloomberg", "summary": "Global", "markets": ["GLOBAL"]},
    ]

    europe = build_market_state_context(rss_items=rss_items, states=[], market_tape={}, macro_snapshot={}, market_scope="europe")
    jp = build_market_state_context(rss_items=rss_items, states=[], market_tape={}, macro_snapshot={}, market_scope="jp")

    assert [item["title"] for item in europe["rssCandidates"]] == [
        "DAX slips after ECB comments",
        "Oil and dollar shape global risk",
    ]
    assert [item["title"] for item in jp["rssCandidates"]] == [
        "닛케이 반도체주 상승",
        "Oil and dollar shape global risk",
    ]
    assert "already filtered for this marketScope" in europe["instruction"]


def test_run_llm_market_state_snapshot_generates_independent_market_views(tmp_path, monkeypatch):
    from features.market_memory import service as memory_service

    calls = []

    def fake_context(*, market_scope="overall", **_kwargs):
        calls.append(market_scope)
        return {
            "marketScope": market_scope,
            "rssCandidates": [{"id": f"rss:{market_scope}", "title": f"{market_scope} source"}],
            "sourceRefs": [{"id": f"rss:{market_scope}", "title": f"{market_scope} source", "source": "Test"}],
            "marketTape": {},
            "macroSnapshot": {},
            "existingStates": [],
        }

    def fake_llm(_cfg, _prompt, context, **_kwargs):
        scope = json.loads(context)["marketScope"]
        payload = {
            "headline": f"{scope} headline",
            "oneLineSummary": f"{scope} interpretation",
            "beginnerSummary": f"{scope} action",
            "marketRegime": f"{scope}_regime",
            "actionPosture": f"{scope} posture",
            "actionGuide": {"headline": f"{scope} guide", "action": f"{scope} action", "timing": f"{scope} timing"},
            "keyDrivers": [{
                "title": f"{scope} driver",
                "summary": f"{scope} summary",
                "whyItMatters": f"{scope} why",
                "evidenceSummary": f"{scope} evidence",
                "marketImpact": f"{scope} impact",
                "nextMemoryCheck": f"{scope} check",
                "sourceRefs": [f"rss:{scope}"],
            }],
            "watchItems": [f"{scope} watch"],
            "counterEvidence": [f"{scope} counter"],
            "sourceRefs": [f"rss:{scope}"],
            "confidence": 0.7,
        }
        return json.dumps(payload, ensure_ascii=False), f"resp-{scope}", {}

    monkeypatch.setattr(memory_service, "MARKET_MEMORY_DB_PATH", tmp_path / "market-memory.sqlite3")
    monkeypatch.setattr(memory_service, "selected_cli_config", lambda: {"enabled": True, "apiKey": "key", "provider": "test", "model": "test-model"})
    monkeypatch.setattr(memory_service, "build_market_state_context", fake_context)
    monkeypatch.setattr(memory_service, "request_cli_text", fake_llm)

    result = memory_service.run_llm_market_state_snapshot()

    assert result["ok"] is True
    # 4시장 제품이므로 종합 + 시장 넷이다. 시장 상태 갱신은 사용자가 명시적으로
    # 누르는 action이고 호출 수는 시장 수를 따른다.
    assert calls == ["overall", "us", "kr", "europe", "jp"]
    assert result["snapshot"]["headline"] == "overall headline"
    assert result["snapshot"]["sourceRefs"][0]["id"] == "rss:overall"
    for scope in ("overall", "us", "kr", "europe", "jp"):
        assert result["snapshot"]["marketViews"][scope]["sourceRefs"][0]["id"] == f"rss:{scope}"


def test_snapshot_source_refs_resolve_internal_rss_ids_for_display():
    context = build_market_state_context(
        rss_items=[
            {"title": "First market article", "media": "Reuters", "summary": "One", "url": "https://example.com/1"},
            {"title": "Second market article", "media": "Bloomberg", "summary": "Two", "url": "https://example.com/2"},
        ],
        states=[],
        market_tape={},
        macro_snapshot={},
    )
    snapshot = validate_market_state_snapshot({
        "headline": "AI와 금리가 시장을 설명",
        "oneLineSummary": "두 번째 기사와 기존 시장 흐름을 함께 봐야 한다.",
        "marketRegime": "mixed",
        "actionPosture": "추격보다 확인",
        "keyDrivers": [{"title": "금리", "summary": "상단 압력", "sourceRefs": ["rss:item:2"]}],
        "watchItems": ["금리"],
        "counterEvidence": ["AI 실적"],
        "sourceRefs": ["rss:item:2"],
        "confidence": 0.7,
    }, context=context)

    assert snapshot["sourceRefs"] == [{
        "id": "rss:item:2",
        "title": "Second market article",
        "source": "Bloomberg",
        "date": "",
        "url": "https://example.com/2",
    }]


def test_validate_market_state_snapshot_preserves_overall_us_and_kr_views():
    snapshot = validate_market_state_snapshot({
        "headline": "종합 시장 판단",
        "oneLineSummary": "미국장은 선별적이고 한국장은 환율 부담을 본다.",
        "marketRegime": "mixed_selective",
        "actionPosture": "시장별로 다른 체크포인트를 본다.",
        "keyDrivers": [{"title": "금리", "summary": "상단 압력", "sourceRefs": ["rss:1"]}],
        "watchItems": ["미국 10년물", "원달러"],
        "counterEvidence": ["AI 실적이 강하면 위험선호가 유지된다."],
        "sourceRefs": [{"id": "rss:1", "title": "Rates", "source": "Reuters"}],
        "confidence": 0.7,
        "marketViews": {
            "overall": {
                "headline": "종합",
                "marketInterpretation": "시장은 좋지도 나쁘지도 않은 선별 구간이다.",
                "actionSummary": "추격보다 보유 종목 점검이 우선이다.",
                "keyDrivers": [{"title": "금리", "summary": "상단 압력", "sourceRefs": ["rss:1"]}],
                "watchItems": ["미국 10년물"],
            },
            "us": {
                "headline": "미국장",
                "marketInterpretation": "AI 기대가 지수 하단을 받친다.",
                "actionSummary": "성장주는 실적 확인 후 접근한다.",
                "keyDrivers": [{"title": "AI 실적", "summary": "성장주 지지", "sourceRefs": ["rss:1"]}],
                "watchItems": ["나스닥 폭"],
            },
            "kr": {
                "headline": "한국장",
                "marketInterpretation": "반도체 수출 기대와 환율 부담이 공존한다.",
                "actionSummary": "환율과 외국인 수급을 확인한다.",
                "keyDrivers": [{"title": "원달러", "summary": "수급 부담", "sourceRefs": ["rss:1"]}],
                "watchItems": ["외국인 순매수"],
            },
        },
    })
    assert sorted(snapshot["marketViews"]) == ["kr", "overall", "us"]
    assert snapshot["marketViews"]["overall"]["headline"] == "종합"
    assert snapshot["marketViews"]["us"]["marketInterpretation"] == "AI 기대가 지수 하단을 받친다."
    assert snapshot["marketViews"]["kr"]["actionSummary"] == "환율과 외국인 수급을 확인한다."


def test_market_view_thin_drivers_keep_missing_source_refs_empty():
    snapshot = validate_market_state_snapshot({
        "headline": "종합 시장 판단",
        "oneLineSummary": "미국장은 선별적이고 한국장은 환율 부담을 본다.",
        "marketRegime": "mixed_selective",
        "actionPosture": "시장별로 다른 체크포인트를 본다.",
        "keyDrivers": [{
            "title": "금리",
            "summary": "상단 압력",
            "whyItMatters": "금리는 할인율과 자금 흐름을 바꾼다.",
            "evidenceSummary": "미국 10년물과 달러가 함께 움직였다.",
            "marketImpact": "성장주 밸류에이션에는 부담이다.",
            "sourceRefs": ["rss:1"],
        }],
        "watchItems": ["미국 10년물", "원달러"],
        "counterEvidence": ["AI 실적이 강하면 위험선호가 유지된다."],
        "sourceRefs": [{"id": "rss:1", "title": "Rates", "source": "Reuters"}],
        "confidence": 0.7,
        "marketViews": {
            "us": {
                "headline": "미국장",
                "marketInterpretation": "미국장은 AI 기대가 지수 하단을 받치지만 금리 부담이 상단을 제한한다.",
                "actionSummary": "성장주는 실적 확인 후 접근한다.",
                "keyDrivers": [{"title": "AI 실적", "summary": "성장주 지지"}],
                "watchItems": ["나스닥 폭"],
            },
        },
    })

    driver = snapshot["marketViews"]["us"]["keyDrivers"][0]
    assert driver["whyItMatters"]
    assert driver["evidenceSummary"]
    assert driver["marketImpact"]
    assert driver["sourceRefs"] == []


def test_market_view_thin_driver_does_not_inherit_matching_top_level_source_refs():
    snapshot = validate_market_state_snapshot({
        "headline": "종합 시장 판단",
        "oneLineSummary": "미국장은 선별적이고 한국장은 환율 부담을 본다.",
        "marketRegime": "mixed_selective",
        "actionPosture": "시장별로 다른 체크포인트를 본다.",
        "keyDrivers": [
            {
                "title": "한국 반도체 수급 부담",
                "summary": "한국 반도체는 수급 부담이 있다.",
                "whyItMatters": "한국 증시 수급에 중요하다.",
                "evidenceSummary": "한국 반도체 기사",
                "marketImpact": "한국 증시 변동성을 키운다.",
                "sourceRefs": ["rss:kr"],
            },
            {
                "title": "미국 기술주 위험선호",
                "summary": "미국 기술주는 위험선호를 받친다.",
                "whyItMatters": "미국 성장주 멀티플에 중요하다.",
                "evidenceSummary": "미국 기술주 기사",
                "marketImpact": "미국장에는 지지 요인이다.",
                "sourceRefs": ["rss:us"],
            },
        ],
        "watchItems": ["나스닥", "원달러"],
        "counterEvidence": ["금리 상승"],
        "sourceRefs": [
            {"id": "rss:kr", "title": "Korea chips", "source": "연합뉴스"},
            {"id": "rss:us", "title": "US tech", "source": "Reuters"},
        ],
        "confidence": 0.7,
        "marketViews": {
            "us": {
                "headline": "미국장",
                "marketInterpretation": "미국장은 기술주 위험선호를 본다.",
                "actionSummary": "기술주는 실적 확인 후 접근한다.",
                "keyDrivers": [{"title": "미국 기술주", "summary": "위험선호 지지"}],
            },
        },
    })

    driver = snapshot["marketViews"]["us"]["keyDrivers"][0]
    assert driver["sourceRefs"] == []


def test_market_view_thin_driver_does_not_inherit_unrelated_sources_when_many_fallbacks():
    snapshot = validate_market_state_snapshot({
        "headline": "종합 시장 판단",
        "oneLineSummary": "미국장은 선별적이고 한국장은 환율 부담을 본다.",
        "marketRegime": "mixed_selective",
        "actionPosture": "시장별로 다른 체크포인트를 본다.",
        "keyDrivers": [
            {"title": "한국 반도체 수급 부담", "summary": "한국 수급 부담", "sourceRefs": ["rss:kr"]},
            {"title": "미국 금리 부담", "summary": "미국 금리 부담", "sourceRefs": ["rss:us"]},
        ],
        "watchItems": ["나스닥", "원달러"],
        "counterEvidence": ["AI 실적"],
        "sourceRefs": [
            {"id": "rss:kr", "title": "Korea chips", "source": "연합뉴스"},
            {"id": "rss:us", "title": "US rates", "source": "Reuters"},
        ],
        "confidence": 0.7,
        "marketViews": {
            "us": {
                "headline": "미국장",
                "marketInterpretation": "미국장은 위험자산 내부 괴리를 본다.",
                "actionSummary": "무리한 추격은 피한다.",
                "keyDrivers": [{"title": "비트코인·테슬라 괴리", "summary": "위험자산 내부 괴리"}],
            },
        },
    })

    driver = snapshot["marketViews"]["us"]["keyDrivers"][0]
    assert driver["sourceRefs"] == []


def test_dashboard_payload_exposes_market_views_for_market_switching():
    snapshot = validate_market_state_snapshot({
        "headline": "종합 시장 판단",
        "oneLineSummary": "미국장은 선별적이고 한국장은 환율 부담을 본다.",
        "beginnerSummary": "새 매수보다 시장별 부담을 먼저 확인하세요.",
        "marketRegime": "mixed_selective",
        "actionPosture": "시장별로 다른 체크포인트를 본다.",
        "actionGuide": {"headline": "시장별 점검", "action": "무리한 추격은 피합니다.", "timing": "다음 데이터 확인 후"},
        "keyDrivers": [{"title": "금리", "summary": "상단 압력", "sourceRefs": ["rss:1"]}],
        "watchItems": ["미국 10년물", "원달러"],
        "counterEvidence": ["AI 실적이 강하면 위험선호가 유지된다."],
        "sourceRefs": [{"id": "rss:1", "title": "Rates", "source": "Reuters"}],
        "confidence": 0.7,
        "marketViews": {
            "us": {
                "headline": "미국장",
                "marketInterpretation": "AI 기대가 지수 하단을 받친다.",
                "actionSummary": "성장주는 실적 확인 후 접근한다.",
                "keyDrivers": [{"title": "AI 실적", "summary": "성장주 지지", "sourceRefs": ["rss:1"]}],
                "watchItems": ["나스닥 폭"],
            },
            "kr": {
                "headline": "한국장",
                "marketInterpretation": "반도체 수출 기대와 환율 부담이 공존한다.",
                "actionSummary": "환율과 외국인 수급을 확인한다.",
                "keyDrivers": [{"title": "원달러", "summary": "수급 부담", "sourceRefs": ["rss:1"]}],
                "watchItems": ["외국인 순매수"],
            },
        },
    })
    from features.market_memory.state_dashboard import dashboard_payload_from_snapshot

    payload = dashboard_payload_from_snapshot(snapshot)
    assert sorted(payload["marketViews"]) == ["kr", "overall", "us"]
    assert payload["marketViews"]["overall"]["title"] == "종합 시장 판단"
    assert payload["marketViews"]["us"]["title"] == "미국장"
    assert payload["marketViews"]["us"]["drivers"][0]["title"] == "AI 실적"
    assert payload["marketViews"]["kr"]["watchItems"] == ["외국인 순매수"]


def test_dashboard_payload_hides_unresolved_internal_source_ids():
    snapshot = validate_market_state_snapshot({
        "headline": "종합 시장 판단",
        "oneLineSummary": "시장 판단은 유지한다.",
        "marketRegime": "mixed",
        "actionPosture": "추격보다 확인",
        "keyDrivers": [{"title": "금리", "summary": "상단 압력", "sourceRefs": ["rss:item:2"]}],
        "watchItems": ["금리"],
        "counterEvidence": ["AI 실적"],
        "sourceRefs": ["rss:item:2"],
        "confidence": 0.7,
    })
    from features.market_memory.state_dashboard import dashboard_payload_from_snapshot

    payload = dashboard_payload_from_snapshot(snapshot)
    assert payload["sourceRefs"] == []


def test_render_market_memory_context_is_source_grounded_medium_term_context():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        save_market_state_snapshot(db_path, {
            "headline": "AI 공급망이 시장의 중심축",
            "oneLineSummary": "AI 반도체와 전력 병목이 위험선호를 설명한다.",
            "marketRegime": "selective_growth",
            "actionPosture": "추격보다 확인된 수혜와 반대 근거를 함께 점검",
            "keyDrivers": [{"title": "AI 반도체 공급망", "summary": "HBM 수요가 유지된다.", "sourceRefs": ["rss:1"]}],
            "watchItems": ["HBM 출하 가이던스"],
            "counterEvidence": ["금리 상승은 밸류에이션 상단을 제한한다."],
            "sourceRefs": [{"id": "rss:1", "title": "AI demand", "source": "Reuters"}],
            "confidence": 0.82,
        })
        rendered = render_market_memory_context(db_path)
        assert "## Market Memory Context" in rendered
        assert "AI 공급망이 시장의 중심축" in rendered
        assert "금리 상승" in rendered
        assert "기업 고유 사실의 evidence가 아니라 시장 배경" in rendered


def test_render_market_memory_context_returns_empty_when_no_snapshot_or_state():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        assert render_market_memory_context(db_path) == ""
