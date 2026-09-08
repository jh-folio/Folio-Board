"""생성된 기업분석 보고서를 **한 곳에서** 마감한다 — API 경로와 CLI 경로가 함께 쓴다.

조립기(`generation_context.py`)가 앞을 하나로 묶었다면 여기는 뒤를 묶는다. 계약 검증과
점수 상한이 경로마다 흩어져 있으면, 한쪽에만 붙인 장치가 다른 쪽에서 조용히 빠진다 —
실제로 그렇게 됐다(CLI 보고서에 `contractValidation`이 아예 없었다).
"""
from __future__ import annotations

from concurrent.futures import CancelledError

from features.company_analysis.report_contract import (
    apply_report_ceiling,
    validate_company_report,
)


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

    어느 결함도 산출물을 되돌리지 않는다 — 기업분석에는 후보 구조가 없어 차단하면
    사용자가 아무것도 받지 못한다. 품질이 아직 계산되지 않았으면 상한은 다음 호출로
    미룬다(`apply_report_ceiling`이 그때 다시 읽는다).
    """
    report = dict(report or {})
    preexisting_unassessed = report.get("validationStatus") == "unassessed"
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
        return _mark_validation_unassessed(report)
    try:
        finalized = apply_report_ceiling(report)
    except (KeyboardInterrupt, SystemExit, CancelledError):
        raise
    except Exception:
        return _mark_validation_unassessed(report)
    return _mark_validation_unassessed(finalized) if preexisting_unassessed else finalized


__all__ = ["finalize_report", "preserve_unassessed_warning"]
