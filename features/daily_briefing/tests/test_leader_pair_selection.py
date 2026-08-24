from __future__ import annotations

import json
from pathlib import Path

import pytest

from features.daily_briefing.concentration.adjudication import adjudicate_conflict
from features.daily_briefing.concentration.leader_selection import select_leader_pair
from features.daily_briefing.concentration.signatures import overlap


FIXTURE = Path(__file__).with_name("fixtures") / "kr_concentration_cases.json"


def _candidate(identifier: str, score: float, **updates) -> dict:
    row = {
        "candidateId": identifier,
        "subject": identifier,
        "sector": "반도체",
        "catalysts": [],
        "mechanisms": [],
        "outcomes": [],
        "evidenceIds": [],
        "baseLeaderScore": score,
        "directEvidenceCount": 1,
    }
    row.update(updates)
    return row


def test_signature_hard_negatives() -> None:
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for case in cases:
        assert overlap(case["left"], case["right"])["independentDimensions"] is case["expectedIndependent"]


def test_same_sector_independent_pair_is_allowed() -> None:
    signatures = [
        _candidate("hynix", 100, catalysts=["ai", "hbm"], mechanisms=["supply"], outcomes=["profit"]),
        _candidate("samsung", 95, catalysts=["ai", "foundry"], mechanisms=["utilization"], outcomes=["share"]),
    ]
    decision = select_leader_pair(signatures)
    assert decision["decision"] == "allow_pair"
    assert decision["finalPair"] == ["hynix", "samsung"]


def test_redundant_pair_uses_only_qualified_alternative() -> None:
    signatures = [
        _candidate("hynix", 100, catalysts=["hbm"], mechanisms=["supply"], outcomes=["profit"]),
        _candidate("samsung", 95, catalysts=["hbm"], mechanisms=["supply"], outcomes=["profit"]),
        _candidate("naver", 80, sector="인터넷", catalysts=["ads"], mechanisms=["demand"], outcomes=["revenue"]),
    ]
    decision = select_leader_pair(signatures)
    assert decision["decision"] == "replace"
    assert decision["finalPair"] == ["hynix", "naver"]


def test_agent_cannot_select_outside_whitelist_and_timeout_never_aborts() -> None:
    signatures = [_candidate("a", 10), _candidate("b", 9), _candidate("c", 8)]
    base = select_leader_pair(signatures)
    invalid = adjudicate_conflict(
        base,
        signatures,
        invoke=lambda _prompt: '{"decision":"replace","replacementCandidateId":"invented"}',
    )
    assert invalid["agentStatus"] == "invalid"
    timed_out = adjudicate_conflict(base, signatures, invoke=lambda _prompt: (_ for _ in ()).throw(TimeoutError()))
    assert timed_out["agentStatus"] == "timeout"
    assert timed_out["finalPair"] == base["finalPair"]
