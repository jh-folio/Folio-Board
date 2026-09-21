"""Personal Overlay 생성·저장 서비스.

Canonical 보고서(브리핑/기업분석)를 사용자 Obsidian hypothesis 노트와 대조한 개인 해석을 만든다.

엄격 규칙:
- Canonical `markdown`은 절대 수정하지 않는다. overlay는 `personalOverlay` 필드로만 붙인다.
- 사용자 노트는 evidence가 아니라 hypothesis(가설)다.
- LLM이 꺼져 있거나 실패하면 규칙 기반 fallback으로 구조를 채운다(서비스가 죽지 않는다).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from features.common.canonical_identity import ReportKind
from features.common.canonical_report_types import WriteKind
from features.common.canonical_reports import commit_sync, prepare
from features.common.jobs import (
    current_diagnostic_recorder,
    diagnostic_execution,
    diagnostic_stage,
    diagnostic_stage_end,
    diagnostic_stage_failure,
    diagnostic_stage_start,
)
from features.common.utils import read_json
from features.daily_briefing.schema import (
    SINGLE_MARKET_SCOPES,
    briefing_file_name,
    normalize_briefing_kind,
    normalize_market_scope,
)
from features.llm_settings.client import (
    request_cli_text,
    selected_cli_config,
    strip_llm_citation_markers,
)
from features.common.quality_generation.telemetry import normalize_token_usage
from features.obsidian.importer import parser as P
from features.obsidian.importer.service import list_hypotheses, scan_vault
from features.personal_overlay import schema as S
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = data_dir()
BRIEFINGS_DIR = DATA_DIR / "briefings"
ANALYSIS_REPORTS_DIR = DATA_DIR / "company-analysis"
PROMPT_PATH = Path(__file__).resolve().parent / "prompt.md"

DISCLAIMER = (
    "이 섹션은 사용자의 Obsidian 노트와 현재 자료를 비교한 개인용 해석입니다. "
    "기본 보고서의 근거에는 포함되지 않습니다."
)


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def read_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# hypothesis 수집
# ---------------------------------------------------------------------------

def _gather_hypotheses(kind: str, canonical: dict) -> list:
    """import 인덱스에서 연결할 hypothesis 노트를 모은다.

    Vault 미설정/미존재 등으로 실패하면 빈 리스트를 반환한다(서비스 계속 동작).
    """
    ticker = None
    if kind == "analysis":
        company = canonical.get("company") or {}
        if isinstance(company, dict):
            ticker = (company.get("ticker") or "").strip() or None
    # 최신 Vault 상태를 인덱스에 반영한 뒤 조회한다(노트를 만들면 어느 폴더든 즉시 반영).
    # Vault 미설정/미존재 등으로 스캔이 실패해도 기존 인덱스로 조회를 계속한다.
    try:
        scan_vault()
    except Exception as error:
        diagnostic_stage_failure(
            current_diagnostic_recorder(), error,
            stage_id=None, stage_code="context", boundary="generic",
        )
        pass
    try:
        return list_hypotheses(ticker=ticker) if ticker else list_hypotheses()
    except Exception as error:
        diagnostic_stage_failure(
            current_diagnostic_recorder(), error,
            stage_id=None, stage_code="context", boundary="generic",
        )
        return []


def _note_excerpt(note_row: dict, limit: int = 1200) -> str:
    if note_row.get("excerpt"):
        return str(note_row["excerpt"])[:limit]
    path = note_row.get("path")
    if not path:
        return ""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""
    return (P.parse_note(text).body or "").strip()[:limit]


def _linked_notes(hypotheses: list) -> list:
    return [
        {
            "noteId": h.get("note_id", ""),
            "title": h.get("title") or h.get("rel_path", ""),
            "type": h.get("note_type", ""),
            "ticker": h.get("ticker", ""),
        }
        for h in hypotheses
    ]


# ---------------------------------------------------------------------------
# 생성 (LLM + fallback)
# ---------------------------------------------------------------------------

def _build_context(canonical: dict, hypotheses: list, kind: str) -> str:
    parts = [f"# Canonical 보고서 ({kind})", (canonical.get("markdown") or "")[:6000]]
    parts.append("\n# 사용자 hypothesis 노트 (evidence 아님, 가설로만 취급)")
    if not hypotheses:
        parts.append("(연결된 노트 없음)")
    for h in hypotheses:
        head = f"\n## [{h.get('note_type', '')}] {h.get('title') or h.get('rel_path', '')}"
        if h.get("ticker"):
            head += f" (ticker={h['ticker']})"
        parts.append(head)
        parts.append(_note_excerpt(h))
    return "\n".join(parts)


def _fallback_overlay(hypotheses: list) -> dict:
    linked = _linked_notes(hypotheses)
    if hypotheses:
        uncertainties = [
            "LLM이 꺼져 있거나 호출에 실패해 자동 대조를 수행하지 못했습니다. 연결된 노트 목록만 표시합니다.",
        ]
        body = "\n".join(f"- {n['title']} ({n['type']})" for n in linked)
        markdown = f"## 내 노트와 연결\n\n{DISCLAIMER}\n\n연결된 노트:\n{body}"
    else:
        uncertainties = [
            "연결할 Obsidian hypothesis 노트가 없습니다. Vault에 company_thesis/market_memo 노트를 작성한 뒤 다시 시도하세요.",
        ]
        markdown = f"## 내 노트와 연결\n\n{DISCLAIMER}\n\n연결된 노트가 없습니다."
    return S.normalize_overlay(
        {"uncertainties": uncertainties, "stance": "insufficient"},
        linked_notes=linked,
        markdown=markdown,
    )


def generate_overlay(canonical: dict, hypotheses: list, *, kind="briefing", llm_override=None, web_search_override=None):
    """(overlay, status) 반환. canonical markdown은 읽기만 한다."""
    # 연결할 노트가 없으면 LLM을 호출하지 않는다(빈 비교는 의미가 없고 토큰만 낭비).
    if not hypotheses:
        diagnostic_execution(final_engine="rules")
        return _fallback_overlay([]), "no_notes"
    cfg = selected_cli_config()
    llm_on = cfg["enabled"] if llm_override is None else bool(llm_override)
    if not llm_on:
        diagnostic_execution(final_engine="rules")
        return _fallback_overlay(hypotheses), "disabled"
    if not cfg["enabled"]:
        diagnostic_execution(final_engine="rules")
        return _fallback_overlay(hypotheses), "cli_disabled"
    prompt = read_prompt()
    if not prompt:
        diagnostic_execution(final_engine="rules")
        return _fallback_overlay(hypotheses), "missing_prompt"
    context = _build_context(canonical, hypotheses, kind)
    web_search = bool(web_search_override) if web_search_override is not None else False
    try:
        text, _rid, usage = request_cli_text(cfg, prompt, context, web_search=web_search, json_mode=True, include_usage=True)
        if not text:
            diagnostic_execution(
                attempted_engine="cli", final_engine="rules", fallback_reason="engine_failed",
            )
            return _fallback_overlay(hypotheses), "empty_response"
        with diagnostic_stage("validate", boundary="validation"):
            raw = json.loads(text)
            markdown = strip_llm_citation_markers(str(raw.get("markdown", "") or ""))
            overlay = S.normalize_overlay(raw, linked_notes=_linked_notes(hypotheses), markdown=markdown)
        overlay["generation"] = {
            "mode": "llm",
            "provider": cfg.get("provider", ""),
            "model": cfg.get("model", ""),
            "responseId": _rid,
            "tokenUsage": normalize_token_usage(usage, prompt=prompt, context=context, output=text),
        }
        diagnostic_execution(attempted_engine="cli", final_engine="cli")
        return overlay, "ok"
    except Exception as error:
        # The fallback is an existing public contract.  Retain only the typed
        # cause at the producer catch; never retain provider text or JSON.
        diagnostic_stage_failure(
            current_diagnostic_recorder(), error,
            stage_id=None, stage_code="generate", boundary="adapter",
        )
        diagnostic_execution(
            attempted_engine="cli", final_engine="rules", fallback_reason="engine_failed",
        )
        return _fallback_overlay(hypotheses), "generation_failed"


# ---------------------------------------------------------------------------
# 저장/조회 (markdown 불변 보장)
# ---------------------------------------------------------------------------

def with_overlay(report: dict, overlay: dict, *, status="", generated_at=None) -> dict:
    """report에 personalOverlay를 붙인 새 dict 반환. 기본 `markdown`은 절대 수정하지 않는다."""
    out = dict(report or {})
    block = dict(overlay)
    block["enabled"] = True
    block["status"] = status
    block["generatedAt"] = generated_at or _now_iso()
    block["canonicalRevision"] = S._revision(out.get("canonicalRevision"))
    block["stale"] = False
    block["staleReason"] = ""
    out["personalOverlay"] = block
    return out


def strip_overlay(report, include_personal: bool):
    """include_personal=False면 응답에서 personalOverlay를 제거한다(기본 보고서 응답 보호)."""
    if not isinstance(report, dict) or "personalOverlay" not in report:
        return report
    if include_personal:
        out = dict(report)
        out["personalOverlay"] = S.public_projection(
            report.get("personalOverlay"),
            canonical_revision=report.get("canonicalRevision"),
        )
        return out
    out = dict(report)
    out.pop("personalOverlay", None)
    return out


def _briefing_overlay_path(date: str, market_scope: str = "both", kind: str = "daily") -> Path:
    """Overlay가 얹힐 Canonical 파일.

    **종류를 받지 않으면 주간 보고서를 열어 둔 채 누른 `개인 해석 생성`이 그날 일간
    보고서를 고친다.** 주간의 저장 키는 발행일이라 같은 날 일간과 날짜가 겹친다.
    """
    scope = normalize_market_scope(market_scope)
    kind = normalize_briefing_kind(kind)
    if scope in SINGLE_MARKET_SCOPES:
        scoped = BRIEFINGS_DIR / briefing_file_name(date, scope, kind)
        if scoped.exists():
            return scoped
        return BRIEFINGS_DIR / briefing_file_name(date, None, kind)
    aggregate = BRIEFINGS_DIR / briefing_file_name(date, None, kind)
    if aggregate.exists():
        return aggregate
    # 합본 파일은 **옛 일간 보고서에만** 있다. 주간은 시장별로만 저장되므로 이 이름은
    # 만들어지는 경로가 아예 없고, 새 일간도 시장별로 저장된다. 그 날짜에 시장 파일이
    # 하나뿐이면 가리키는 대상이 하나로 정해지므로 그것을 쓴다 — 여러 시장이 함께 있으면
    # 어느 쪽에 얹을지 정할 수 없어 예전처럼 없는 파일을 돌려주고 호출부가 404로 끝낸다.
    scoped_files = [
        path for path in (
            BRIEFINGS_DIR / briefing_file_name(date, single, kind) for single in SINGLE_MARKET_SCOPES
        ) if path.exists()
    ]
    if len(scoped_files) == 1:
        return scoped_files[0]
    return aggregate


def attach_overlay_to_briefing(date: str, *, market_scope="both", kind="daily", llm_override=None, web_search_override=None) -> dict:
    with diagnostic_stage("context"):
        path = _briefing_overlay_path(date, market_scope, kind)
        canonical = read_json(path, None)
        if not canonical:
            raise FileNotFoundError(f"Briefing not found: {date}")
        hyps = _gather_hypotheses("briefing", canonical)
    recorder, stage_id = diagnostic_stage_start("generate")
    try:
        overlay, status = generate_overlay(canonical, hyps, kind="briefing",
                                           llm_override=llm_override, web_search_override=web_search_override)
    except Exception as error:
        diagnostic_stage_failure(recorder, error, stage_id=stage_id,
                                 stage_code="generate" if stage_id is not None else None, boundary="generic")
        diagnostic_stage_end(recorder, stage_id, "generate")
        raise
    diagnostic_stage_end(recorder, stage_id, "generate")
    updated = with_overlay(canonical, overlay, status=status)
    # 통째 write_json으로 되쓰지 않는다. generate_overlay(LLM 수십 초) 사이에 예약 생성·
    # 제안 승인이 같은 파일을 새 canonicalRevision으로 커밋할 수 있는데, 읽어 둔 dict을
    # 그대로 쓰면 그 커밋이 조용히 옛 본문으로 되돌아간다. prepare()가 잠금 안에서 현재
    # 파일을 다시 읽어 personalOverlay만 얹는다(CLI 잡 경로의 overlay_spec과 같은 배관).
    commit_sync(prepare(
        report_kind=ReportKind.BRIEFING,
        exact_path=path,
        write_kind=WriteKind.OVERLAY,
        candidate={"personalOverlay": updated["personalOverlay"]},
    ))
    return {"ok": True, "status": status, "personalOverlay": updated["personalOverlay"]}


def attach_overlay_to_report(report_id: str, *, llm_override=None, web_search_override=None) -> dict:
    from features.company_analysis.service import get_analysis_report
    with diagnostic_stage("context"):
        canonical = get_analysis_report(report_id)
        if not canonical:
            raise FileNotFoundError(f"Analysis report not found: {report_id}")
        hyps = _gather_hypotheses("analysis", canonical)
    recorder, stage_id = diagnostic_stage_start("generate")
    try:
        overlay, status = generate_overlay(canonical, hyps, kind="analysis",
                                           llm_override=llm_override, web_search_override=web_search_override)
    except Exception as error:
        diagnostic_stage_failure(recorder, error, stage_id=stage_id,
                                 stage_code="generate" if stage_id is not None else None, boundary="generic")
        diagnostic_stage_end(recorder, stage_id, "generate")
        raise
    diagnostic_stage_end(recorder, stage_id, "generate")
    updated = with_overlay(canonical, overlay, status=status)
    commit_sync(prepare(
        report_kind=ReportKind.COMPANY_ANALYSIS,
        exact_path=ANALYSIS_REPORTS_DIR / f"{canonical.get('id') or report_id}.json",
        write_kind=WriteKind.OVERLAY,
        candidate={"personalOverlay": updated["personalOverlay"]},
    ))
    return {"ok": True, "status": status, "personalOverlay": updated["personalOverlay"]}
