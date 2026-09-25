from features.agent_mode.companion import (
    agent_companion_reply,
    classify_agent_intent,
    normalize_agent_context,
    normalize_agent_options,
)
from pydantic import ValidationError


VALID_COLLECTION_ID = "sc_12345678-1234-4234-9234-123456789abc"


def test_normalize_agent_context_keeps_safe_fields_only():
    raw = {
        "surface": "briefing_reader",
        "viewId": "briefing",
        "reportKind": "briefing",
        "reportId": "2026-07-02.us",
        "marketScope": "us",
        "selectedText": "AI capex remains central",
        "visibleSection": "leading_companies",
        "apiKey": "sk-proj-secret",
        "token": "secret",
    }
    ctx = normalize_agent_context(raw)
    assert ctx == {
        "surface": "briefing_reader",
        "viewId": "briefing",
        "reportKind": "briefing",
        "reportId": "2026-07-02.us",
        "marketScope": "us",
        "selectedText": "AI capex remains central",
        "visibleSection": "leading_companies",
        "portfolioLinked": False,
    }


def test_normalize_agent_context_preserves_legacy_both_and_canonicalizes_eu():
    assert normalize_agent_context({"marketScope": "both"})["marketScope"] == "both"
    assert normalize_agent_context({"marketScope": "EU"})["marketScope"] == "europe"
    assert normalize_agent_context({"marketScope": "MARS"})["marketScope"] == ""


def test_normalize_agent_context_accepts_only_collection_identity():
    ctx = normalize_agent_context({
        "surface": "deep_research",
        "collectionId": VALID_COLLECTION_ID,
        "collectionRevision": 3,
        "query": "IGNORE RULES QUERY CANARY",
        "matches": [{"body": "FAKE MATCH BODY CANARY"}],
        "evidenceBodies": ["FAKE EVIDENCE BODY CANARY"],
        "userContext": "HYPOTHESIS CANARY",
    })
    assert ctx["collectionId"] == VALID_COLLECTION_ID
    assert ctx["collectionRevision"] == 3
    assert not ({"query", "matches", "evidenceBodies", "userContext"} & ctx.keys())


def test_normalize_agent_context_rejects_malformed_collection_identity():
    for raw in (
        {"collectionId": "../../smart-collections.json", "collectionRevision": 1},
        {"collectionId": VALID_COLLECTION_ID, "collectionRevision": 0},
        {"collectionId": VALID_COLLECTION_ID, "collectionRevision": "1"},
        {"collectionId": VALID_COLLECTION_ID},
        {"collectionRevision": 1},
    ):
        try:
            normalize_agent_context(raw)
            assert False, f"must reject {raw!r}"
        except ValidationError:
            pass


def test_classify_agent_intent_starts_as_companion_for_questions():
    assert classify_agent_intent("이 브리핑에서 제일 중요한 게 뭐야?") == "companion"
    assert classify_agent_intent("내 포트폴리오에 어떤 의미야?") == "companion"


def test_classify_agent_intent_switches_to_task_for_mutating_requests():
    assert classify_agent_intent("이 기업분석에 bear case 섹션 추가해줘") == "task"
    assert classify_agent_intent("최신 RSS로 Market Memory 업데이트해줘") == "task"
    assert classify_agent_intent("내일 아침 브리핑 자동화 설정해줘") == "task"


def test_companion_reply_never_writes_state():
    result = agent_companion_reply(
        "이 브리핑에서 반대로 볼 근거는?",
        {"surface": "briefing_reader", "reportKind": "briefing", "reportId": "2026-07-02.us"},
    )
    assert result["mode"] == "companion"
    assert result["requiresApproval"] is False
    assert result["writeback"] is None
    assert any(action["id"] == "create_personal_overlay" for action in result["actions"])


def test_normalize_agent_options_clamps_effort_and_attachments():
    options = normalize_agent_options({
        "model": "gpt-5.3-codex",
        "effort": "extreme",
        "attachments": [
            {"name": "memo.md", "size": "12", "content": "x" * 9000},
            {"name": "", "size": 1},
            "not-a-dict",
        ],
    })
    assert options["model"] == "gpt-5.3-codex"
    assert options["effort"] == "medium"
    assert len(options["attachments"]) == 1
    assert options["attachments"][0]["name"] == "memo.md"
    assert len(options["attachments"][0]["content"]) == 4000


def test_normalize_agent_options_accepts_response_depth_as_the_canonical_name():
    """Agent Dock Stage B: `responseDepth`가 정식 이름, `effort`는 하위 호환 별칭이다."""
    only_depth = normalize_agent_options({"responseDepth": "high"})
    assert only_depth["responseDepth"] == "high"
    assert only_depth["effort"] == "high"  # existing readers of `effort` keep working

    only_effort = normalize_agent_options({"effort": "low"})
    assert only_effort["responseDepth"] == "low"
    assert only_effort["effort"] == "low"

    both_given = normalize_agent_options({"responseDepth": "max", "effort": "low"})
    assert both_given["responseDepth"] == "max"
    assert both_given["effort"] == "max"


def test_normalize_agent_options_accepts_the_full_provider_reasoning_range():
    """Codex는 xhigh/ultra까지 노력 단계를 낸다(features/llm_settings/reasoning.py) —
    이 정규화가 low/medium/high/max로만 좁혀 놓으면 Dock에서 그 단계를 골라도
    조용히 medium으로 깎여, 실제 CLI에는 다른 값이 전달된다(§6 규칙14와 같은 유형).
    """
    xhigh = normalize_agent_options({"effort": "xhigh"})
    assert xhigh["effort"] == "xhigh"
    assert xhigh["responseDepth"] == "xhigh"

    ultra = normalize_agent_options({"effort": "ultra"})
    assert ultra["effort"] == "ultra"
    assert ultra["responseDepth"] == "ultra"


def test_normalize_agent_options_defaults_search_policy_to_off():
    """Agent Dock Stage D: 안 보내거나 모르는 값이면 기존 동작(검색 없음)을 유지한다."""
    assert normalize_agent_options({})["searchPolicy"] == "off"
    assert normalize_agent_options({"searchPolicy": "nonsense"})["searchPolicy"] == "off"
    assert normalize_agent_options({"searchPolicy": "auto"})["searchPolicy"] == "auto"
    assert normalize_agent_options({"searchPolicy": "ON"})["searchPolicy"] == "on"


def test_companion_reply_echoes_normalized_options():
    result = agent_companion_reply(
        "이 화면 요약해줘?",
        {"surface": "briefing_reader"},
        {"model": "claude-opus", "effort": "high", "attachments": [{"name": "notes.txt", "size": 10}]},
    )
    assert result["options"]["model"] == "claude-opus"
    assert result["options"]["effort"] == "high"
    assert result["options"]["attachments"][0]["name"] == "notes.txt"
