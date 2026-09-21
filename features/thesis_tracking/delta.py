"""Thesis Delta engine.

Compares a registered user thesis (hypothesis) with recent local news/index evidence.
The canonical company-analysis markdown is never modified; results are persisted as
separate `thesis_delta` rows in market-memory.sqlite3.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from features.common.utils import normalize, summarize
from features.common.research_library.indexing.service import load_index
from features.llm_settings.client import (
    extract_json_object,
    request_cli_text,
    selected_cli_config,
    strip_llm_citation_markers,
)
from features.common.research_library.search.service import search_documents
from features.common.jobs import current_diagnostic_recorder, diagnostic_execution, diagnostic_stage, diagnostic_stage_failure
from features.common.research_schema.checkpoints import checkpoints_from_thesis_delta
from features.common.research_schema.data_gaps import data_gaps_from_messages
from features.common.research_schema.evidence import evidence_items_from_list
from features.common.research_schema.source_ledger import source_ledger_from_items
from features.common.research_schema.tracked_checkpoints import checkpoint_labels
from features.common.data_reliability.official_materials import gather_company_material_evidence
from features.common.data_reliability.source_priority import annotate_source_priority
from features.common.research_quality.evaluator import evaluate_artifact
from features.thesis_tracking import model as M
from features.common.quality_generation.telemetry import normalize_token_usage

ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = Path(__file__).resolve().parent / "delta_prompt.md"

PERIOD_CHOICES = {"30d", "90d", "since_last_review", "since_last_note", "last_earnings"}
PERIOD_DEFAULT = "90d"

DISCLAIMER = (
    "이 결과는 사용자 thesis를 최신 로컬 자료와 대조한 Personal Overlay 계층의 검증 결과입니다. "
    "사용자 노트는 근거가 아니라 가설이며, Canonical 기업분석 본문은 변경하지 않습니다."
)

POSITIVE_TERMS = [
    "beat", "raise", "raised", "growth", "accelerat", "margin expansion", "upgrade",
    "strong demand", "record", "outperform", "상향", "호조", "강세", "성장", "개선",
    "수요 증가", "실적 개선", "가이던스 상향", "증가", "회복",
]
NEGATIVE_TERMS = [
    "miss", "cut", "lower", "lowered", "decline", "slowdown", "weak", "risk",
    "downgrade", "margin pressure", "inventory", "guidance cut", "하향", "부진",
    "약세", "둔화", "감소", "리스크", "압박", "악화", "가이던스 하향",
]


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def normalize_period(value) -> str:
    s = str(value or "").strip().lower()
    return s if s in PERIOD_CHOICES else PERIOD_DEFAULT


def period_cutoff(thesis: dict, period: str, today: dt.date | None = None) -> tuple[str, int, list[str]]:
    """Return (YYYY-MM-DD cutoff, day count, uncertainties)."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    period = normalize_period(period)
    uncertainties: list[str] = []
    if period == "30d":
        days = 30
    elif period == "90d":
        days = 90
    elif period in {"since_last_review", "since_last_note"}:
        raw = thesis.get("last_reviewed_at") or thesis.get("updated_at") or thesis.get("created_at") or ""
        try:
            reviewed = dt.date.fromisoformat(str(raw)[:10])
            days = max(1, min(730, (today - reviewed).days))
        except Exception:
            days = 90
            uncertainties.append("마지막 리뷰 날짜를 해석하지 못해 기본 90일 창으로 판정했습니다.")
    else:
        days = 90
        uncertainties.append("마지막 실적일 자동 식별은 아직 지원하지 않아 기본 90일 창으로 판정했습니다.")
    cutoff = (today - dt.timedelta(days=days)).isoformat()
    return cutoff, days, uncertainties


def _split_terms(values) -> list[str]:
    terms: list[str] = []
    for value in values or []:
        text = normalize(value).lower()
        for token in re.findall(r"[A-Za-z0-9가-힣]{2,}", text):
            if len(token) >= 2:
                terms.append(token)
    return list(dict.fromkeys(terms))[:80]


def build_search_query(thesis: dict) -> str:
    parts = [
        thesis.get("ticker", ""),
        thesis.get("company", ""),
        thesis.get("core_thesis", ""),
        " ".join((thesis.get("key_metrics") or [])[:5]),
        " ".join((thesis.get("key_assumptions") or [])[:3]),
    ]
    query = " ".join(str(p or "") for p in parts)
    return normalize(query)[:500] or str(thesis.get("ticker") or thesis.get("company") or "")


def gather_local_evidence(thesis: dict, *, period: str = PERIOD_DEFAULT, limit: int = 12) -> tuple[list[dict], dict]:
    """Search local news and enrich it with official company-analysis materials."""
    period = normalize_period(period)
    cutoff, days, uncertainties = period_cutoff(thesis, period)
    index = load_index()
    query = build_search_query(thesis)
    company_query = thesis.get("ticker") or thesis.get("company") or query
    docs = search_documents(index, query=query, company=company_query, limit=max(limit * 3, 24), scope="news")
    filtered = [d for d in docs if not d.get("date") or str(d.get("date", ""))[:10] >= cutoff]
    if len(filtered) < max(3, min(limit, 6)):
        fallback = search_documents(index, query=company_query, company=company_query, limit=max(limit * 2, 16), scope="news")
        seen = {d.get("path") or d.get("url") or d.get("title") for d in filtered}
        for doc in fallback:
            key = doc.get("path") or doc.get("url") or doc.get("title")
            if key not in seen and (not doc.get("date") or str(doc.get("date", ""))[:10] >= cutoff):
                filtered.append(doc)
                seen.add(key)
            if len(filtered) >= limit:
                break
    news_evidence = [doc_to_evidence(d, thesis) for d in filtered[:limit]]
    official_evidence, official_gaps, official_meta = gather_company_material_evidence(
        thesis,
        index.get("documents") or [],
        artifact_id=str(thesis.get("ticker") or thesis.get("company") or ""),
        limit=max(4, min(limit, 10)),
    )
    combined = annotate_source_priority(
        list(official_evidence or []) + news_evidence,
        artifact_type="thesis_delta",
    )
    evidence: list[dict] = []
    seen: set[str] = set()
    for item in combined:
        key = item.get("url") or item.get("path") or f"{item.get('title')}|{item.get('source')}|{item.get('date')}"
        if not key or key in seen:
            continue
        seen.add(key)
        evidence.append(item)
        if len(evidence) >= limit:
            break
    return evidence, {
        "source": "official_materials+local_news_index" if official_evidence else "local_news_index",
        "query": query,
        "cutoff": cutoff,
        "period": period,
        "periodDays": days,
        "uncertainties": uncertainties,
        "dataGaps": official_gaps,
        "officialMaterials": official_meta,
        "documentCount": len(evidence),
        "newsEvidenceCount": len(news_evidence),
        "officialEvidenceCount": len(official_evidence or []),
    }


def doc_to_evidence(doc: dict, thesis: dict) -> dict:
    text = " ".join([
        str(doc.get("title") or ""),
        str(doc.get("summary") or ""),
        str(doc.get("searchSnippet") or ""),
        str(doc.get("content") or "")[:1200],
    ])
    text_l = normalize(text).lower()
    support_terms = _split_terms((thesis.get("key_assumptions") or []) + (thesis.get("supporting_signals") or []))
    weak_terms = _split_terms((thesis.get("weakening_signals") or []) + (thesis.get("falsification_triggers") or []))
    support_hits = [t for t in support_terms if t in text_l][:8]
    weak_hits = [t for t in weak_terms if t in text_l][:8]
    pos_hits = [t for t in POSITIVE_TERMS if t in text_l][:5]
    neg_hits = [t for t in NEGATIVE_TERMS if t in text_l][:5]
    support_score = len(support_hits) + len(pos_hits)
    weak_score = len(weak_hits) + len(neg_hits)
    role = "neutral"
    if weak_score > support_score and weak_score > 0:
        role = "challenging"
    elif support_score > weak_score and support_score > 0:
        role = "supporting"
    reason_terms = weak_hits + neg_hits if role == "challenging" else support_hits + pos_hits
    reason = ", ".join(reason_terms[:6]) or "티커/회사명 기준 관련 로컬 뉴스"
    return {
        "id": doc.get("id", ""),
        "title": doc.get("title", ""),
        "source": doc.get("source", ""),
        "date": str(doc.get("date", ""))[:10],
        "type": doc.get("type", ""),
        "url": doc.get("url", ""),
        "path": doc.get("path", ""),
        "snippet": summarize(doc.get("searchSnippet") or doc.get("summary") or doc.get("content") or doc.get("title"), 2),
        "role": role,
        "reason": reason,
        "score": float(doc.get("score", 0) or 0),
    }


def empty_delta() -> dict:
    return {
        "verdict": M.VERDICT_DEFAULT,
        "verdictLabel": M.VERDICT_LABELS[M.VERDICT_DEFAULT],
        "summary": "",
        "supportingEvidence": [],
        "counterEvidence": [],
        "contradictions": [],
        "uncertainties": [],
        "nextCheckpoints": [],
        "markdown": "",
    }


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [x for x in value if x not in (None, "")]
    return [value] if str(value).strip() else []


def normalize_delta(raw, *, thesis: dict, evidence: list, meta: dict, fallback_markdown: str = "") -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out = empty_delta()
    out["verdict"] = M.normalize_verdict(raw.get("verdict"))
    out["verdictLabel"] = M.VERDICT_LABELS.get(out["verdict"], M.VERDICT_LABELS[M.VERDICT_DEFAULT])
    out["summary"] = str(raw.get("summary") or "").strip()
    out["supportingEvidence"] = [_normalize_evidence_item(x) for x in _as_list(raw.get("supportingEvidence"))]
    out["counterEvidence"] = [_normalize_evidence_item(x) for x in _as_list(raw.get("counterEvidence"))]
    out["contradictions"] = [str(x).strip() for x in _as_list(raw.get("contradictions")) if str(x).strip()]
    out["uncertainties"] = [str(x).strip() for x in _as_list(raw.get("uncertainties")) if str(x).strip()]
    # thesis의 next_checkpoints에는 구조화 체크포인트(dict)가 섞일 수 있다.
    # Delta는 사람이 읽는 문장 목록이므로 라벨로 바꾼다.
    out["nextCheckpoints"] = checkpoint_labels(_as_list(raw.get("nextCheckpoints")), 360)
    markdown = strip_llm_citation_markers(str(raw.get("markdown") or "").strip())
    out["markdown"] = markdown or fallback_markdown

    if not out["counterEvidence"]:
        out["counterEvidence"] = [
            {
                "title": "로컬 인덱스 반대 근거 점검",
                "source": "Folio Board",
                "date": "",
                "reason": "이번 evidence window에서 명시적인 반대 근거가 제한적이거나 식별되지 않았습니다.",
            }
        ]
    if not out["uncertainties"]:
        out["uncertainties"] = list(meta.get("uncertainties") or []) or [
            "이 판정은 로컬 뉴스 인덱스와 가능한 공식자료 보강 기준이며, 부족한 SEC/DART·실적콜 원문은 dataGap으로 남깁니다.",
        ]
    else:
        out["uncertainties"].extend(x for x in meta.get("uncertainties") or [] if x not in out["uncertainties"])
    if not out["nextCheckpoints"]:
        out["nextCheckpoints"] = checkpoint_labels(thesis.get("next_checkpoints"), 360)[:5] or [
            "다음 실적 발표와 가이던스 변화",
            "thesis의 핵심 가정과 직접 충돌하는 공시/뉴스",
        ]
    if not out["summary"]:
        out["summary"] = _summary_from_verdict(out["verdict"], evidence)
    if not out["markdown"]:
        out["markdown"] = build_markdown(thesis, out, evidence, meta)
    out["evidence"] = evidence
    out["evidenceItems"] = evidence_items_from_list(evidence, artifact_type="thesis_delta", default_type="news")
    out["sourceLedger"] = source_ledger_from_items(out["evidenceItems"], artifact_type="thesis_delta")
    out["checkpoints"] = checkpoints_from_thesis_delta(out)
    out["dataGaps"] = data_gaps_from_messages(
        meta.get("dataGaps") or [],
        artifact_type="thesis_delta",
        category="official_materials",
        severity="medium",
    )
    out["officialMaterials"] = meta.get("officialMaterials") or {}
    out["evidenceSource"] = meta.get("source", "local_news_index")
    out["period"] = meta.get("period", PERIOD_DEFAULT)
    out["periodDays"] = meta.get("periodDays", 90)
    out["cutoff"] = meta.get("cutoff", "")
    out["generatedAt"] = now_iso()
    try:
        out["quality"] = evaluate_artifact("thesis_delta", out)
    except Exception:
        out["quality"] = {"status": "warn", "warnings": ["quality_evaluation_failed"]}
    return out


def _normalize_evidence_item(item) -> dict:
    if isinstance(item, dict):
        return {
            "title": str(item.get("title") or "").strip(),
            "source": str(item.get("source") or "").strip(),
            "date": str(item.get("date") or "").strip(),
            "reason": str(item.get("reason") or item.get("snippet") or "").strip(),
            "url": str(item.get("url") or "").strip(),
            "path": str(item.get("path") or "").strip(),
        }
    return {"title": "", "source": "", "date": "", "reason": str(item).strip(), "url": "", "path": ""}


def _summary_from_verdict(verdict: str, evidence: list) -> str:
    count = len(evidence)
    if verdict == "insufficient_evidence":
        return f"최근 로컬/공식자료 {count}건만으로는 thesis 변화를 판정하기에 근거가 부족합니다."
    return f"최근 로컬/공식자료 {count}건을 기준으로 thesis는 '{M.VERDICT_LABELS.get(verdict, verdict)}' 상태로 분류됩니다."


def fallback_delta(thesis: dict, evidence: list, meta: dict, *, status: str = "rules") -> dict:
    supporting = [e for e in evidence if e.get("role") == "supporting"]
    challenging = [e for e in evidence if e.get("role") == "challenging"]
    neutral = [e for e in evidence if e.get("role") == "neutral"]
    if not evidence:
        verdict = "insufficient_evidence"
    elif len(challenging) >= 3 and len(challenging) >= len(supporting):
        verdict = "at_risk"
    elif len(challenging) > len(supporting):
        verdict = "weakened"
    elif len(supporting) >= 3 and len(supporting) > len(challenging):
        verdict = "strengthened"
    else:
        verdict = "maintained"
    raw = {
        "verdict": verdict,
        "supportingEvidence": supporting[:5] or neutral[:2],
        "counterEvidence": challenging[:5],
        "contradictions": _contradictions_from_evidence(thesis, challenging),
        "uncertainties": list(meta.get("uncertainties") or []),
        "nextCheckpoints": thesis.get("next_checkpoints") or [],
    }
    if status != "rules":
        raw["uncertainties"].append(f"LLM Delta 생성 실패/비활성으로 규칙 기반 판정을 사용했습니다: {status}")
    delta = normalize_delta(raw, thesis=thesis, evidence=evidence, meta=meta)
    delta["generation"] = {"mode": "rules", "status": status, "sourceCount": len(evidence)}
    delta["markdown"] = build_markdown(thesis, delta, evidence, meta)
    return delta


def _contradictions_from_evidence(thesis: dict, challenging: list) -> list[str]:
    if not challenging:
        return []
    triggers = thesis.get("falsification_triggers") or thesis.get("weakening_signals") or []
    if triggers:
        return [f"'{triggers[0]}' 조건과 유사한 약화 신호가 로컬 뉴스에서 감지됐는지 확인이 필요합니다."]
    return ["일부 로컬 뉴스가 thesis의 강화 방향과 반대로 해석될 수 있습니다."]


def build_context(thesis: dict, evidence: list, meta: dict) -> str:
    payload = {
        "task": "Return JSON only. Verify this user thesis against local evidence.",
        "thesisLayer": "hypothesis",
        "evidenceLayer": "external_local_news_index",
        "period": meta,
        "thesis": thesis,
        "evidence": evidence[:12],
        "requiredBiasControls": ["counterEvidence", "contradictions", "uncertainties"],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def read_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return ""


def generate_delta(
    thesis: dict,
    *,
    period: str = PERIOD_DEFAULT,
    llm_override=None,
    evidence_limit: int = 12,
    prepared_evidence: list | None = None,
    prepared_meta: dict | None = None,
) -> tuple[dict, str]:
    """Generate from caller-prepared evidence when the producer owns context.

    The optional prepared values retain the legacy standalone API while letting
    the direct service keep authority lookup and evidence assembly in its real
    `context` boundary.
    """
    if prepared_evidence is None or prepared_meta is None:
        evidence, meta = gather_local_evidence(thesis, period=period, limit=evidence_limit)
    else:
        evidence, meta = prepared_evidence, prepared_meta
    if not evidence:
        diagnostic_execution(final_engine="rules")
        return fallback_delta(thesis, evidence, meta, status="no_evidence"), "no_evidence"
    cfg = selected_cli_config()
    llm_on = cfg["enabled"] if llm_override is None else bool(llm_override)
    if not llm_on:
        diagnostic_execution(final_engine="rules")
        return fallback_delta(thesis, evidence, meta, status="disabled"), "disabled"
    if not cfg["enabled"]:
        diagnostic_execution(final_engine="rules")
        return fallback_delta(thesis, evidence, meta, status="cli_disabled"), "cli_disabled"
    prompt = read_prompt()
    if not prompt:
        diagnostic_execution(final_engine="rules")
        return fallback_delta(thesis, evidence, meta, status="missing_prompt"), "missing_prompt"
    try:
        context = build_context(thesis, evidence, meta)
        text, rid, usage = request_cli_text(cfg, prompt, context, json_mode=True, max_output_tokens=3500, include_usage=True)
        if not text:
            diagnostic_execution(
                attempted_engine="cli", final_engine="rules", fallback_reason="engine_failed",
            )
            return fallback_delta(thesis, evidence, meta, status="generation_failed"), "generation_failed"
        with diagnostic_stage("validate", boundary="validation"):
            raw = extract_json_object(text)
            delta = normalize_delta(raw, thesis=thesis, evidence=evidence, meta=meta)
        delta["generation"] = {
            "mode": "llm",
            "status": "ok",
            "provider": cfg.get("provider", ""),
            "model": cfg.get("model", ""),
            "responseId": rid,
            "sourceCount": len(evidence),
            "tokenUsage": normalize_token_usage(usage, prompt=prompt, context=context, output=text, max_output_tokens=3500),
        }
        diagnostic_execution(attempted_engine="cli", final_engine="cli")
        return delta, "ok"
    except Exception as error:
        diagnostic_stage_failure(
            current_diagnostic_recorder(), error,
            stage_id=None, stage_code="generate", boundary="adapter",
        )
        diagnostic_execution(
            attempted_engine="cli", final_engine="rules", fallback_reason="engine_failed",
        )
        return fallback_delta(thesis, evidence, meta, status="generation_failed"), "generation_failed"


def build_markdown(thesis: dict, delta: dict, evidence: list, meta: dict) -> str:
    title = f"## Thesis 변화: {thesis.get('ticker') or thesis.get('company') or ''}".strip()
    lines = [
        title,
        "",
        DISCLAIMER,
        "",
        f"- 판정: **{delta.get('verdictLabel', '')}** (`{delta.get('verdict', '')}`)",
        f"- 기간: 최근 {meta.get('periodDays', 90)}일 (cutoff {meta.get('cutoff', '')})",
        f"- 근거: 로컬 뉴스 인덱스 및 공식자료 후보 {len(evidence)}건",
        "",
        "### 요약",
        delta.get("summary") or _summary_from_verdict(delta.get("verdict", M.VERDICT_DEFAULT), evidence),
    ]
    if delta.get("supportingEvidence"):
        lines += ["", "### 강화 근거"]
        for item in delta["supportingEvidence"][:5]:
            lines.append(f"- {item.get('date', '')} {item.get('source', '')} — {item.get('title', '')}: {item.get('reason', '')}")
    if delta.get("counterEvidence"):
        lines += ["", "### 반대 근거"]
        for item in delta["counterEvidence"][:5]:
            lines.append(f"- {item.get('date', '')} {item.get('source', '')} — {item.get('title', '')}: {item.get('reason', '')}")
    if delta.get("contradictions"):
        lines += ["", "### 충돌/모순"]
        lines += [f"- {x}" for x in delta["contradictions"][:6]]
    if delta.get("uncertainties"):
        lines += ["", "### 불확실성"]
        lines += [f"- {x}" for x in delta["uncertainties"][:6]]
    if delta.get("nextCheckpoints"):
        lines += ["", "### 다음 체크포인트"]
        lines += [f"- {x}" for x in delta["nextCheckpoints"][:6]]
    return "\n".join(lines).strip()
