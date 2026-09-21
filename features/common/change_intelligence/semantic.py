"""내용 기반 의미 비교 — 변화 판정의 두 번째 층.

규칙 비교기는 "무엇이 어떻게 움직였나"(순위·비중·지표)를 결정적으로 잡지만,
비중 이동은 그날 보도량 구성의 함수라서 내용이 바뀌었는지는 말하지 못한다.
이 모듈은 변화 단위별 직전/현재 대표 기사 제목을 LLM에 한 번 보여
semanticVerdict enum으로 분류받고, 코드가 enum·인용·길이를 검증한 뒤
상태 승격/강등 게이트를 적용한다.

경계:
- 생성 잡 안에서만 실행된다(브리핑 생성이라는 명시적 사용자 action의 연장).
  변화 판정 자체를 위해 별도 Agent job을 만들지 않는다.
- LLM은 분류만 한다. "중대한 변화"라는 결론은 코드 게이트(enum + 증거 등급)가
  확정한다 (§5-4).
- LLM이 없으면 not_evaluated로 정직하게 표시하고, 내용 확인 없는 major_change
  승격을 막는다. 커밋은 절대 실패시키지 않는다.
"""
from __future__ import annotations

import json

SEMANTIC_VERDICTS = (
    "new_information",      # 펀더멘털에 새로운 사실
    "trend_development",    # 기존 흐름의 진전
    "reversal",             # 방향 전환
    "coverage_shift_only",  # 내용은 같고 보도량/비중만 이동
    "no_new_information",   # 실질적 차이 없음
)
PROMOTING_VERDICTS = {"new_information", "reversal"}
QUIET_VERDICTS = {"coverage_shift_only", "no_new_information"}
SEMANTIC_KINDS = {"market_driver", "issue_coverage"}
NOTE_MAX_CHARS = 300
MAX_OUTPUT_TOKENS = 1400

SEMANTIC_PROMPT = (
    "너는 투자 리서치의 변화 분류기다. 각 항목의 직전 대표 기사 제목과 현재 대표 기사 제목을 비교해 "
    "내용 변화를 분류한다.\n"
    "verdict는 반드시 다음 중 하나다: new_information(펀더멘털에 새로운 사실), "
    "trend_development(기존 흐름의 진전), reversal(방향 전환), "
    "coverage_shift_only(내용은 같고 보도량·비중만 이동), no_new_information(실질적 차이 없음).\n"
    "note는 한국어 1~2문장으로 무엇이 달라졌는지 쓴다. 제공된 제목에 없는 사실을 만들지 않는다. "
    "제목만으로 판단이 어려우면 no_new_information을 쓴다.\n"
    "citedTitles에는 판단에 실제로 쓴 제목만 원문 그대로 담는다.\n"
    'JSON만 출력한다: {"units": [{"id": "...", "verdict": "...", "note": "...", "citedTitles": ["..."]}]}'
)


def _has_both_sides(row: dict) -> bool:
    """직전과 현재 대표 기사가 모두 있어야 내용을 대조할 수 있다.

    한쪽만 있는 단위(그날 새로 뽑힌 이슈)를 보내면 모델은 비교할 것이 없으므로
    당연히 `new_information`을 답하고, 그 verdict가 승격 게이트를 통과시킨다.
    실측 8/25 KR 브리핑은 판정 6건이 전부 그런 `added` 이슈였다. 대조가 불가능한
    것을 "새 정보"로 세면 의미 비교 층이 강등 장치가 아니라 승격 장치가 된다.
    """
    return bool(row.get("contextDocs")) and bool(row.get("previousContextDocs"))


def semantic_eligible_items(summary: dict) -> list[dict]:
    return [
        row for row in (summary or {}).get("changedItems") or []
        if isinstance(row, dict) and row.get("kind") in SEMANTIC_KINDS and _has_both_sides(row)
    ]


def _context_payload(items: list[dict]) -> dict:
    units = []
    for row in items:
        units.append({
            "id": row.get("id"),
            "subject": row.get("subject"),
            "change": row.get("change"),
            "previousTitles": list(row.get("previousContextDocs") or []),
            "currentTitles": list(row.get("contextDocs") or []),
        })
    return {"units": units}


def _validate_verdicts(raw: dict, items: list[dict]) -> dict[str, dict]:
    if not isinstance(raw, dict) or not isinstance(raw.get("units"), list):
        return {}
    allowed_titles = {
        str(row.get("id")): set((row.get("contextDocs") or []) + (row.get("previousContextDocs") or []))
        for row in items
    }
    verdicts: dict[str, dict] = {}
    for unit in (raw or {}).get("units") or []:
        if not isinstance(unit, dict):
            continue
        unit_id = str(unit.get("id") or "")
        verdict = str(unit.get("verdict") or "")
        if unit_id not in allowed_titles or verdict not in SEMANTIC_VERDICTS:
            continue
        cited_titles = unit.get("citedTitles")
        cited = [
            title for title in (cited_titles if isinstance(cited_titles, list) else [])
            if isinstance(title, str) and title in allowed_titles[unit_id]
        ][:3]
        verdicts[unit_id] = {
            "verdict": verdict,
            "note": str(unit.get("note") or "")[:NOTE_MAX_CHARS],
            "citedTitles": cited,
        }
    return verdicts


def _cli_semantic_call():
    """Agent CLI로 같은 판정 프롬프트를 보내는 호출자. 쓸 수 없으면 None.

    **CLI 모드에서는 API 키가 없는 것이 정상이다.** 키만 보고 판정을 접으면 CLI로
    브리핑을 만드는 구성에서는 의미 비교가 영원히 `not_evaluated`로 남는다 —
    화면은 그것을 "판정하지 못했다"로 읽고 이미 연결된 Agent를 연결하라고 말한다.
    """
    from features.agent_mode.bridge import run_agent_prompt
    from features.llm_settings.client import extract_json_object

    def call(prompt: str, context: str) -> dict:
        # 이 함수는 브리핑 생성 잡의 커밋 단계에서 불린다 — 그 잡이 이미
        # `_RUN_SEMAPHORE`를 쥐고 있으므로 다시 잡으면 잡 스레드가 영원히 멈춘다.
        from features.llm_settings.task_runtime import current_task_policy
        policy = current_task_policy()
        options = {}
        if isinstance(policy, dict) and policy.get("mode") == "cli":
            options = {
                "adapter": str(policy.get("provider") or ""),
                "model": str(policy.get("model") or ""),
                "reasoning_effort": str(policy.get("reasoningEffort") or ""),
            }
        result = run_agent_prompt(
            f"{prompt}\n\n{context}", serialize=False,
            diagnostic_primary=False, **options,
        )
        return extract_json_object(str(result.get("output") or ""))

    return call


def evaluate_semantic_changes(summary: dict, *, llm_call=None) -> dict:
    """변화 단위의 내용 분류. 실패는 not_evaluated일 뿐 예외를 밖으로 내지 않는다."""
    items = semantic_eligible_items(summary)
    if not items:
        return {"status": "no_eligible_items", "verdicts": {}}
    if llm_call is None:
        from features.llm_settings.client import (
                    extract_json_object,
            request_cli_text,
            selected_cli_config,
        )

        from features.llm_settings.task_runtime import current_task_policy, generation_mode
        policy = current_task_policy()
        bound_mode = generation_mode(policy) if isinstance(policy, dict) else None
        if bound_mode == "rules":
            return {"status": "not_evaluated", "verdicts": {}, "reason": "generation_rules_mode"}
        # A CLI task must not validate an unused global API model/effort.
        # Frozen per-task routing takes precedence over unrelated API keys.
        try:
            cfg = policy if bound_mode == "llm_cli" else selected_cli_config()
        except (ValueError, KeyError, TypeError, OSError, RuntimeError):
            return {"status": "not_evaluated", "verdicts": {}, "reason": "llm_configuration_invalid"}
        from features.llm_settings.client import default_generation_mode

        if (bound_mode is None and default_generation_mode() != "llm_cli"):
            return {"status": "not_evaluated", "verdicts": {}, "reason": "llm_unavailable"}
        try:
            llm_call = _cli_semantic_call()
        except Exception:  # noqa: BLE001 - 어댑터를 못 고르면 판정만 접는다
            return {"status": "not_evaluated", "verdicts": {}, "reason": "llm_unavailable"}
        provider, model = "agent_cli", ""
        try:
            raw = llm_call(SEMANTIC_PROMPT, json.dumps(_context_payload(items), ensure_ascii=False))
        except (KeyError, TypeError, ValueError, OSError, RuntimeError):
            return {"status": "not_evaluated", "verdicts": {}, "reason": "llm_failed"}
    else:
        provider, model = "injected", ""
        try:
            raw = llm_call(SEMANTIC_PROMPT, json.dumps(_context_payload(items), ensure_ascii=False))
        except Exception:
            return {"status": "not_evaluated", "verdicts": {}, "reason": "llm_failed"}
    verdicts = _validate_verdicts(raw, items)
    if not verdicts:
        return {"status": "not_evaluated", "verdicts": {}, "reason": "no_valid_verdicts"}
    return {"status": "evaluated", "verdicts": verdicts, "provider": provider, "model": model}


# 내용 확인 없이 major를 유지시키는 문턱. 지표 눈금상 1.0은 그 자산에서 드문 하루라
# 뜻이 분명하고, 0.9는 거기에 거의 닿은 값이다. 예전 0.7은 지수 2.6%·유가 5% 이동이면
# 걸려서 "내용 확인 없는 major를 막는다"는 이 층의 목적을 자주 우회했다.
METRIC_ALONE_MAJOR_MAGNITUDE = 0.9


def _metric_alone_is_major(summary: dict) -> bool:
    """지표 급변은 의미 분류 대상이 아니므로 지표만으로 넘은 major는 유지한다."""
    return any(
        row.get("kind") == "market_metric" and float(row.get("magnitude") or 0) >= METRIC_ALONE_MAJOR_MAGNITUDE
        for row in summary.get("changedItems") or []
    )


def apply_semantic_verdicts(summary: dict, evaluation: dict) -> dict:
    """verdict를 changedItems에 붙이고 상태 게이트를 적용한다. 원본은 바꾸지 않는다."""
    result = dict(summary or {})
    items = [dict(row) for row in result.get("changedItems") or []]
    verdicts = (evaluation or {}).get("verdicts") or {}
    evaluated = (evaluation or {}).get("status") == "evaluated"
    for row in items:
        verdict = verdicts.get(str(row.get("id")))
        if verdict:
            row["semanticVerdict"] = verdict["verdict"]
            row["semanticNote"] = verdict["note"]
            row["semanticCitedTitles"] = verdict["citedTitles"]
        elif row.get("kind") in SEMANTIC_KINDS and _has_both_sides(row):
            row["semanticVerdict"] = "not_evaluated"
    result["changedItems"] = items
    result["semanticEvaluation"] = {
        "status": (evaluation or {}).get("status") or "not_evaluated",
        # **왜 판정하지 못했는지를 함께 남긴다.** 이유가 없으면 화면은 판정 엔진이 없어서인지
        # 호출이 실패해서인지 구분할 수 없어 어댑터를 스스로 뒤지게 되고, 그 추측이 API 키만
        # 쓰는 설치에서 "AI Agent를 연결하세요"를 되살렸다(엔진은 이미 연결돼 있다).
        "reason": (evaluation or {}).get("reason"),
        "provider": (evaluation or {}).get("provider"),
        "model": (evaluation or {}).get("model"),
        # wall-clock을 쓰면 동일 재생성이 canonical no-op이 아니게 된다(comparator와 같은 이유).
        "evaluatedAt": (summary or {}).get("generatedAt"),
    }

    status = result.get("status")
    if status in {"baseline_created", "insufficient_basis", "conflicting_uncertain"}:
        return result
    corroboration = result.get("corroboration") or {}
    evidence_gate = int(corroboration.get("tier1") or 0) >= 1 or int(corroboration.get("independentTier2") or 0) >= 2
    semantic_flags = {row.get("semanticVerdict") for row in items if row.get("semanticVerdict")}

    if evaluated:
        has_promoting = bool(semantic_flags & PROMOTING_VERDICTS)
        if status == "major_change" and not has_promoting and not _metric_alone_is_major(result):
            # 물량으로만 오른 major는 내용 확인 없이는 유지하지 않는다.
            result["status"] = "developing_signal" if semantic_flags - QUIET_VERDICTS else "no_material_change"
        elif status in {"developing_signal", "no_material_change"} and has_promoting and evidence_gate:
            # 새 사실/방향 전환 + 충분한 독립 근거 = 비중이 작아도 중대한 변화다.
            result["status"] = "major_change"
    elif status == "major_change" and not _metric_alone_is_major(result):
        # 내용 미평가 상태로는 major를 확정하지 않는다. 지어내는 것보다 한계 명시가 낫다.
        result["status"] = "developing_signal"
        # 대조할 단위가 없어 판정을 건너뛴 것(`no_eligible_items`)은 실패가 아니다.
        # 그때까지 "판정하지 못했다"로 적으면 화면이 엔진을 의심하게 된다.
        if (evaluation or {}).get("status") != "no_eligible_items":
            uncertainties = list(result.get("uncertainties") or [])
            if "semantic_not_evaluated" not in uncertainties:
                uncertainties.append("semantic_not_evaluated")
            result["uncertainties"] = uncertainties
    return result
