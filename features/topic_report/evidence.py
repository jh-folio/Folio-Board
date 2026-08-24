"""Evidence Pack — 보고서 근거를 분석 축별로 구조화한다 (설계 04 §6~7).

- 검색은 TopicPlan의 axis별 searchQueries를 쓴다 (label.split() 의존 제거).
- evidenceRole은 코드에서 enum 검증한다. userContext/Obsidian 노트는 evidence가 아니다.
- LLM 없이도 동작한다 — 전 과정 규칙 기반.
"""
from __future__ import annotations

import datetime as dt
import re

from features.common.research_library.rss.policy import normalize_url
from features.smart_collections.providers import inbox_path
from features.topic_report.topic_schema import normalize_evidence_role

_POSITIVE_TERMS = (
    "beat", "boost", "expand", "gain", "growth", "improve", "increase", "raise", "rally",
    "recover", "strong", "surge", "upside",
    "강세", "개선", "반등", "상승", "상향", "서프라이즈", "성장", "수혜", "증가", "호조", "회복", "확대",
)
_NEGATIVE_TERMS = (
    "concern", "cut", "decline", "delay", "disappoint", "downside", "drop", "fall", "miss",
    "pressure", "risk", "slow", "slowdown", "weak",
    "감소", "둔화", "리스크", "부담", "악화", "약세", "우려", "위험", "하락", "하향",
)


def _age_days(value, as_of: str = "") -> int:
    text = str(value or "")[:10]
    try:
        event = dt.date.fromisoformat(text)
    except Exception:
        return 9999
    try:
        anchor = dt.date.fromisoformat(str(as_of or "")[:10])
    except Exception:
        anchor = dt.datetime.now(dt.timezone.utc).date()
    return max(0, (anchor - event).days)


def _freshness(age: int) -> str:
    if age <= 7:
        return "recent"
    if age <= 30:
        return "current"
    if age <= 90:
        return "dated"
    return "stale"


def classify_evidence_role(text: str, age_days: int = 0) -> str:
    """규칙 기반 evidenceRole. 수치 위주 → data_point, 오래된 자료 → background,
    감성 단어 우세 방향에 따라 supporting/challenging, 그 외 neutral."""
    body = str(text or "")
    lower = body.lower()
    digits = len(re.findall(r"\d+(?:\.\d+)?%?", body))
    words = max(1, len(body.split()))
    if digits >= 5 and digits / words > 0.18:
        return "data_point"
    if age_days > 90:
        return "background"
    positive = sum(1 for term in _POSITIVE_TERMS if term in lower)
    negative = sum(1 for term in _NEGATIVE_TERMS if term in lower)
    if positive >= negative + 2:
        return "supporting"
    if negative >= positive + 2:
        return "challenging"
    return normalize_evidence_role("neutral")


def _relevance(doc: dict, query_tokens: set[str]) -> float:
    score = doc.get("score") or doc.get("relevance")
    if isinstance(score, (int, float)) and 0 < float(score) <= 1:
        return round(float(score), 3)
    hay = " ".join(str(doc.get(k, "") or "") for k in ("title", "summary", "searchSnippet")).lower()
    if not query_tokens:
        return 0.5
    hit = sum(1 for token in query_tokens if token in hay)
    return round(min(1.0, 0.3 + hit / max(3, len(query_tokens)) * 0.7), 3)


def _coverage_level(count: int) -> str:
    if count >= 4:
        return "high"
    if count >= 2:
        return "medium"
    if count >= 1:
        return "low"
    return "none"


def _admission_key(doc: dict) -> str:
    raw_url = str(doc.get("url") or "").strip()
    if raw_url:
        normalized_url = normalize_url(raw_url)
        if normalized_url:
            return f"url:{normalized_url}"
    raw_path = str(doc.get("path") or "").strip()
    if raw_path:
        return f"path:{inbox_path(raw_path)}"
    document_id = str(doc.get("id") or doc.get("documentId") or "").strip()
    if document_id:
        return f"id:{document_id}"
    title = str(doc.get("title") or "").strip()
    return f"legacy:{title}" if title else ""


def build_evidence_pack(
    plan: dict,
    *,
    search_docs,
    search_memories,
    date: str = "",
    limit_per_axis: int = 5,
    deep_research: bool = False,
) -> dict:
    """TopicPlan 기반 Evidence Pack 생성.

    search_docs(queries: list[str], limit) / search_memories(keywords, limit)는
    호출자가 주입한다 (service의 기존 검색 재사용 + 테스트 용이성).
    """
    axes = plan.get("analysisAxes") or []
    seen_keys: set[str] = set()
    items: list[dict] = []
    axis_coverage: dict[str, dict] = {}
    counter = 0

    def _add_doc(
        doc: dict,
        axis_key: str,
        queries: list[str],
        *,
        research_question_id: str = "",
        research_round: int = 0,
    ) -> bool:
        nonlocal counter
        dedupe = _admission_key(doc)
        if not dedupe or dedupe in seen_keys:
            return False
        seen_keys.add(dedupe)
        counter += 1
        text = " ".join(str(doc.get(k, "") or "") for k in ("title", "summary", "searchSnippet", "snippet", "content"))[:800]
        age = _age_days(doc.get("date"), as_of=date)
        tokens = {t.lower() for q in queries for t in re.findall(r"[A-Za-z가-힣0-9]{2,}", q)}
        item = {
            "id": f"ev_{counter:03d}",
            "type": doc.get("type") or "news",
            "source": doc.get("source", ""),
            "date": str(doc.get("date", ""))[:10],
            "title": str(doc.get("title", ""))[:200],
            "summary": str(doc.get("summary") or doc.get("searchSnippet") or doc.get("snippet") or "")[:400],
            "url": doc.get("url", ""),
            "path": doc.get("path", ""),
            "relevance": _relevance(doc, tokens),
            "axisKey": axis_key,
            "evidenceRole": classify_evidence_role(text, age),
            "confidence": "medium",
            "freshness": _freshness(age),
        }
        document_id = str(doc.get("id") or doc.get("documentId") or "").strip()
        if document_id:
            item["documentId"] = document_id
        if research_question_id:
            item["researchQuestionId"] = research_question_id
        if research_round:
            item["researchRound"] = research_round
        items.append(item)
        return True

    question_coverage: dict[str, dict] = {}
    deep_meta = plan.get("deepResearch") or {}
    subquestions = list(deep_meta.get("subQuestions") or []) if deep_research else []
    round_stats: list[dict] = []
    round_1_gap_reasons: list[str] = []
    round_2_reason = "not_applicable"

    if subquestions:
        axis_counts = {axis.get("key", ""): 0 for axis in axes}
        by_round = {
            round_no: [question for question in subquestions if int(question.get("round") or 1) == round_no]
            for round_no in (1, 2)
        }

        def execute_round(round_no: int, questions: list[dict]) -> None:
            searched = selected = 0
            executed_ids = []
            for question in questions:
                qid = str(question.get("id") or "")
                axis_key = str(question.get("axisKey") or "")
                queries = list(question.get("searchQueries") or []) or list(plan.get("searchQueries") or [])[:2]
                added = 0
                try:
                    docs = search_docs(queries, limit=limit_per_axis * 2)
                except Exception:
                    docs = []
                searched += len(docs)
                for doc in docs:
                    if _add_doc(
                        doc,
                        axis_key,
                        queries,
                        research_question_id=qid,
                        research_round=round_no,
                    ):
                        added += 1
                        selected += 1
                        if axis_key in axis_counts:
                            axis_counts[axis_key] += 1
                    if added >= limit_per_axis:
                        break
                question_coverage[qid] = {
                    "question": question.get("question", ""),
                    "axisKey": axis_key,
                    "round": round_no,
                    "count": added,
                    "level": _coverage_level(added),
                    "executed": True,
                }
                executed_ids.append(qid)
            round_stats.append({
                "round": round_no,
                "executedQuestionIds": executed_ids,
                "searchedCount": searched,
                "selectedCount": selected,
            })

        execute_round(1, by_round[1])
        for question in by_round[1]:
            coverage = question_coverage.get(str(question.get("id") or ""), {})
            if coverage.get("level") in {"none", "low"}:
                round_1_gap_reasons.append(f"low_question_coverage:{question.get('id', '')}")
        for axis in axes:
            axis_key = axis.get("key", "")
            if _coverage_level(axis_counts.get(axis_key, 0)) in {"none", "low"}:
                round_1_gap_reasons.append(f"low_axis_coverage:{axis_key}")
        challenging_count = sum(item.get("evidenceRole") == "challenging" for item in items)
        if challenging_count == 0:
            round_1_gap_reasons.append("missing_challenging_evidence")
        if by_round[2] and round_1_gap_reasons:
            execute_round(2, by_round[2])
            round_2_reason = "executed_for_coverage_gaps"
        else:
            round_2_reason = "skipped_sufficient_round_1" if by_round[2] else "skipped_no_approved_round_2_questions"
            for question in by_round[2]:
                qid = str(question.get("id") or "")
                question_coverage[qid] = {
                    "question": question.get("question", ""),
                    "axisKey": question.get("axisKey", ""),
                    "round": 2,
                    "count": 0,
                    "level": "not_executed",
                    "executed": False,
                }
        for axis in axes:
            axis_key = axis.get("key", "")
            count = axis_counts.get(axis_key, 0)
            axis_coverage[axis_key] = {"label": axis.get("label", ""), "count": count, "level": _coverage_level(count)}
    else:
        # 1) 축별 검색 — planner가 만든 axis searchQueries 사용
        for axis in axes:
            axis_key = axis.get("key", "")
            queries = list(axis.get("searchQueries") or [])
            if not queries:
                queries = list(plan.get("searchQueries") or [])[:2]
            added = 0
            try:
                docs = search_docs(queries, limit=limit_per_axis * 2)
            except Exception:
                docs = []
            for doc in docs:
                if _add_doc(doc, axis_key, queries):
                    added += 1
                if added >= limit_per_axis:
                    break
            axis_coverage[axis_key] = {"label": axis.get("label", ""), "count": added, "level": _coverage_level(added)}

    # 2) 주제 전체 검색 — 축에 안 잡힌 일반 근거 보충
    try:
        general_docs = search_docs(list(plan.get("searchQueries") or [])[:4], limit=8)
    except Exception:
        general_docs = []
    for doc in general_docs:
        _add_doc(doc, "", list(plan.get("searchQueries") or [])[:4])

    # 3) 시장 내러티브 메모리
    try:
        memories = search_memories(list(plan.get("memoryQueries") or []), limit=12)
    except Exception:
        memories = []

    # 4) 데이터 갭 — 계획상 우려 + 실제 커버리지 결합
    data_gaps = list(plan.get("dataGapsLikely") or [])
    for axis_key, cov in axis_coverage.items():
        if cov["level"] in ("none", "low"):
            data_gaps.append(f"'{cov['label']}' 축의 로컬 자료가 부족합니다 ({cov['count']}건).")
    for qid, cov in question_coverage.items():
        if cov["level"] in ("none", "low") and cov.get("executed", True):
            data_gaps.append(f"심층 질문 '{cov['question']}'의 로컬 근거가 부족합니다 ({cov['count']}건).")

    role_counts: dict[str, int] = {}
    for item in items:
        role_counts[item["evidenceRole"]] = role_counts.get(item["evidenceRole"], 0) + 1
    freshness_counts: dict[str, int] = {}
    for item in items:
        freshness = str(item.get("freshness") or "unknown")
        freshness_counts[freshness] = freshness_counts.get(freshness, 0) + 1

    return {
        "items": items,
        "marketMemory": memories,
        "axisCoverage": axis_coverage,
        "questionCoverage": question_coverage,
        "deepResearch": {
            "enabled": bool(subquestions),
            "maxRounds": min(2, int(deep_meta.get("maxRounds") or 1)) if subquestions else 1,
            "subQuestionCount": len(subquestions),
            "rounds": round_stats,
            "round1GapReasons": round_1_gap_reasons,
            "round2Reason": round_2_reason,
            "challengingEvidenceCount": role_counts.get("challenging", 0),
            "freshnessCounts": freshness_counts,
        },
        "dataGaps": data_gaps[:10],
        "roleCounts": role_counts,
        "totalDocs": len(items),
    }


def evidence_pack_summary(pack: dict) -> dict:
    """보고서 JSON에 저장할 압축 요약 (원본 items 전체는 저장하지 않음)."""
    return {
        "totalDocs": pack.get("totalDocs", 0),
        "roleCounts": pack.get("roleCounts", {}),
        "axisCoverage": pack.get("axisCoverage", {}),
        "questionCoverage": pack.get("questionCoverage", {}),
        "deepResearch": pack.get("deepResearch", {}),
        "dataGaps": pack.get("dataGaps", []),
        "memoryCount": len(pack.get("marketMemory", [])),
    }
