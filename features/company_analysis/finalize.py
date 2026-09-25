"""생성된 기업분석 보고서를 **한 곳에서** 마감한다 — API 경로와 CLI 경로가 함께 쓴다.

조립기(`generation_context.py`)가 앞을 하나로 묶었다면 여기는 뒤를 묶는다. 계약 검증과
점수 상한이 경로마다 흩어져 있으면, 한쪽에만 붙인 장치가 다른 쪽에서 조용히 빠진다 —
실제로 그렇게 됐다(CLI 보고서에 `contractValidation`이 아예 없었다).
"""
from __future__ import annotations

import re
from concurrent.futures import CancelledError

from features.company_analysis.report_contract import (
    apply_report_ceiling,
    validate_company_report,
)

_HEADING_RE = re.compile(r"^#{1,2}\s+\S")


def _ensure_markdown_title(markdown: str, headline: str) -> str:
    """본문이 `# 제목` 줄로 시작하도록 보장한다.

    프런트엔드(`CompanyAnalysisRoute.tsx`·`app.js`의 `splitReportTitle()`)는 첫
    내용 줄이 `# `로 시작해야 그 줄을 카드 제목으로 뽑아내고 본문에서 지운다.
    규칙 기반 경로(`render_report`)는 `# ✅ 이름 (티커)`를 항상 쓰지만, CLI/LLM
    경로는 모델 출력에 그대로 의존해 형식이 흔들렸다 — 같은 세션 실측으로 RIVN은
    `# Rivian ...`으로 맞았지만 SK하이닉스는 `#` 없이 "SK하이닉스(000660) 기업
    분석"으로 시작해, splitReportTitle이 못 찾고 그 줄이 카드 제목 아래 스타일
    없는 문단으로 그대로 남아 두 번째(가짜) 제목처럼 보였다. 첫 heading(`#`/`##`)
    앞의 내용은 전부 제목 자리이므로, 모델이 그 자리를 어떻게 채웠든 headline으로
    통일한다 — 프롬프트 지시에 기대지 않고 여기서 구조로 보장한다.
    """
    text = str(markdown or "").replace("\r\n", "\n")
    lines = text.split("\n")
    first_content = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first_content is None or _HEADING_RE.match(lines[first_content].strip()):
        return text
    heading_index = next(
        (i for i, line in enumerate(lines) if _HEADING_RE.match(line.strip())),
        None,
    )
    if heading_index is None:
        # 헤딩이 전혀 없으면 무엇이 "제목 자리"인지 판단할 근거가 없다 — 이런
        # 문서는 애초에 섹션 구조가 없다는 훨씬 큰 문제이고, 그건 계약 검증이
        # 잡는다. 여기서 원문을 지우고 제목만 남기면 그 결함을 숨기게 된다.
        return text
    body = "\n".join(lines[heading_index:]).lstrip("\n")
    title = str(headline or "").strip() or "기업 분석"
    return f"# {title}\n\n{body}"


_VALIDATION_WARNING = {
    "code": "validation_unavailable",
    "message": "보고서 구조 검증을 완료하지 못했습니다.",
}


def _mark_validation_unassessed(report: dict) -> dict:
    """Keep the exact candidate while making a validator failure explicit.

    A validator exception is an observation failure, not a passing report.  The
    fixed warning deliberately contains no exception text, report body, or
    traceback; diagnostics own technical failure details separately.
    """
    report["validationStatus"] = "unassessed"
    report["validationWarning"] = dict(_VALIDATION_WARNING)
    report["contractValidation"] = {
        "status": "unassessed",
        "defects": [],
        "metrics": {},
    }
    quality = dict(report.get("quality") or {})
    quality["status"] = "warn"
    warnings = [str(item) for item in (quality.get("warnings") or []) if item]
    if _VALIDATION_WARNING["code"] not in warnings:
        warnings.append(_VALIDATION_WARNING["code"])
    quality["warnings"] = warnings
    report["quality"] = quality
    generation = dict(report.get("generation") or {})
    existing = str(generation.get("message") or "").strip()
    notice = "검수 미완료: 보고서 구조를 확인하지 못했습니다."
    if notice not in existing:
        generation["message"] = f"{existing} {notice}".strip()
    report["generation"] = generation
    return report


def preserve_unassessed_warning(report: dict) -> dict:
    """Re-assert the warning after a later quality pass may rebuild fields."""
    if isinstance(report, dict) and report.get("validationStatus") == "unassessed":
        return _mark_validation_unassessed(report)
    return report


def finalize_report(
    report: dict,
    *,
    depth_policy: dict | None = None,
    source_ledger: list | None = None,
    quote_sources: list | None = None,
) -> dict:
    """계약을 검증하고 그 무게를 품질 점수에 반영한다.

    본문은 보존하고 완료 상태를 표시한다. 불완전 결과의 정상본 승격은 저장 경계에서
    차단하며 복구 후보로 남긴다. 품질이 아직 계산되지 않았으면 상한은 다음 호출로
    미룬다(`apply_report_ceiling`이 그때 다시 읽는다).
    """
    from features.company_analysis.recovery import completion_summary
    report = dict(report or {})
    preexisting_unassessed = report.get("validationStatus") == "unassessed"
    if report.get("markdown"):
        report["markdown"] = _ensure_markdown_title(report["markdown"], report.get("headline"))
    try:
        report["contractValidation"] = validate_company_report(
            str(report.get("markdown") or ""),
            depth_policy=depth_policy if depth_policy is not None else report.get("depthPolicy"),
            source_ledger=source_ledger if source_ledger is not None else report.get("sourceLedger"),
            quote_sources=quote_sources,
        )
    except (KeyboardInterrupt, SystemExit, CancelledError):
        # Explicit process interruption must remain observable to the caller.
        raise
    except Exception:
        report["completion"] = completion_summary(report)
        return _mark_validation_unassessed(report)
    report["completion"] = completion_summary(report)
    try:
        finalized = apply_report_ceiling(report)
    except (KeyboardInterrupt, SystemExit, CancelledError):
        raise
    except Exception:
        return _mark_validation_unassessed(report)
    return _mark_validation_unassessed(finalized) if preexisting_unassessed else finalized


__all__ = ["finalize_report", "preserve_unassessed_warning"]
