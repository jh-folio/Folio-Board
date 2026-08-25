import json

from features.daily_briefing.concentration.history import (
    canonical_company_id,
    history_metrics,
    load_recent_history,
)
from features.daily_briefing.concentration.leader_selection import select_leader_pair


def _signature(identifier, subject, score, *, catalysts, mechanisms, outcomes):
    return {
        "candidateId": identifier,
        "canonicalId": canonical_company_id(subject),
        "subject": subject,
        "sector": "반도체",
        "catalysts": catalysts,
        "mechanisms": mechanisms,
        "outcomes": outcomes,
        "evidenceIds": [identifier],
        "baseLeaderScore": score,
        "directEvidenceCount": 1,
    }


def test_known_korean_company_aliases_share_identity() -> None:
    assert canonical_company_id("삼성전자") == canonical_company_id("Samsung Electronics") == "kr:005930"
    assert canonical_company_id("SK하이닉스") == canonical_company_id("SK hynix") == "kr:000660"
    assert canonical_company_id("삼성전자", "005930.KS") == "kr:005930"


def test_same_company_new_causal_path_is_not_penalized() -> None:
    current = _signature("s", "삼성전자", 100, catalysts=["foundry_order"], mechanisms=["utilization"], outcomes=["share"])
    old = _signature("old", "Samsung Electronics", 1, catalysts=["hbm_contract"], mechanisms=["supply"], outcomes=["profitability"])
    metrics = history_metrics(current, [old])
    assert metrics["recentAppearanceCount"] == 1
    assert metrics["novelCausalPath"] is True
    decision = select_leader_pair([current, _signature("n", "NAVER", 90, catalysts=["earnings"], mechanisms=["demand"], outcomes=["revenue"])], mode="active", history=[old])
    assert decision["originalPair"][0] == "s"


def test_repeated_causal_path_gets_soft_penalty_only_in_active_mode() -> None:
    samsung = _signature("s", "삼성전자", 100, catalysts=["hbm_contract"], mechanisms=["supply"], outcomes=["profitability"])
    naver = _signature("n", "NAVER", 91, catalysts=["earnings"], mechanisms=["demand"], outcomes=["revenue"])
    history = [{**samsung, "candidateId": f"old-{i}"} for i in range(3)]
    shadow = select_leader_pair([samsung, naver], mode="shadow", history=history)
    active = select_leader_pair([samsung, naver], mode="active", history=history)
    assert shadow["originalPair"][0] == "s"
    assert active["originalPair"][0] == "n"
    assert "recent_causal_repetition" in active["conflictSignals"]


def test_history_loader_reads_only_prior_kr_daily_sessions(tmp_path) -> None:
    signature = _signature("s", "삼성전자", 100, catalysts=["hbm_contract"], mechanisms=["supply"], outcomes=["profitability"])
    report = {
        "date": "2026-08-22",
        "concentrationControl": {"byMarket": {"kr": {"leaderDecision": {"finalPair": ["s"]}, "signatures": [signature]}}},
    }
    (tmp_path / "2026-08-22.kr.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "2026-08-23.kr.weekly.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "2026-08-25.kr.json").write_text(json.dumps(report), encoding="utf-8")
    rows = load_recent_history(before_date="2026-08-25", reports_dir=tmp_path)
    assert len(rows) == 1
    assert rows[0]["sessionDate"] == "2026-08-22"


def test_legacy_report_heading_contributes_appearance_history(tmp_path) -> None:
    report = {"date": "2026-08-20", "markdown": "## 3. 한국장을 주도한 기업 ① — 삼성전자\n본문"}
    (tmp_path / "2026-08-20.kr.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    rows = load_recent_history(before_date="2026-08-25", reports_dir=tmp_path)
    assert rows[0]["canonicalId"] == "kr:005930"
