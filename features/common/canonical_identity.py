from __future__ import annotations

import json
import re
from enum import StrEnum
from pathlib import Path
from collections.abc import Mapping
from typing import Final, assert_never

from features.common.canonical_json import JsonValue
from features.common.canonical_report_io import safe_child_path
from features.common.markets import PRODUCT_MARKETS

DATE_PATTERN: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SAFE_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
# 브리핑 파일 접미사는 시장 계약에서 파생한다. 여기에 시장을 다시 적으면
# 새 시장의 저장이 정체성 검증에서만 조용히 막힌다.
BRIEFING_MARKETS: Final = tuple(market.value.lower() for market in PRODUCT_MARKETS)
_MARKET_ALT: Final = "|".join(BRIEFING_MARKETS)
# 기본(일간) 외의 브리핑 종류 접미사. 권위는 `daily_briefing.schema.BRIEFING_KINDS`이며
# `features/common`이 feature를 import하지 않기 위해 여기 한 줄로 다시 적는다 —
# 둘이 어긋나면 `features/daily_briefing/tests/test_weekly_briefing.py`가 잡는다.
# 여기 없는 종류는 저장이 정체성 검증에서만 조용히 막힌다.
BRIEFING_KIND_SUFFIXES: Final = ("weekly",)
_KIND_ALT: Final = "|".join(BRIEFING_KIND_SUFFIXES)
BRIEFING_ID_PATTERN: Final = re.compile(
    rf"(\d{{4}}-\d{{2}}-\d{{2}})(?:\.({_MARKET_ALT}))?(?:\.({_KIND_ALT}))?"
)
BRIEFING_FILE_PATTERN: Final = re.compile(
    rf"(\d{{4}}-\d{{2}}-\d{{2}})(?:\.({_MARKET_ALT}))?(?:\.({_KIND_ALT}))?\.json"
)


class ReportKind(StrEnum):
    BRIEFING = "briefing"
    COMPANY_ANALYSIS = "company_analysis"
    TOPIC_REPORT = "topic_report"


class CanonicalIdentityError(Exception):
    __slots__ = ("code", "detail")

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail

    def __str__(self) -> str:
        return self.detail


class CanonicalNotFoundError(Exception):
    __slots__ = ("code", "report_id")

    def __init__(self, code: str, report_id: str) -> None:
        super().__init__(report_id)
        self.code = code
        self.report_id = report_id

    def __str__(self) -> str:
        return f"canonical report not found: {self.report_id}"


def split_briefing_id(report_id: str) -> tuple[str, str | None, str]:
    """브리핑 report id를 `(발행일, 시장, 종류)`로 가른다.

    id에 실려 오는 형태가 넷이다 — `{날짜}`, `{날짜}.{시장}`, `{날짜}.weekly`,
    `{날짜}.{시장}.weekly`. 호출부마다 접미사를 손으로 떼면 종류가 조용히 사라져
    주간 요청이 그날 **일간** 파일을 가리킨다. 패턴을 소유한 이 모듈이 대신 가른다.
    못 읽는 id는 날짜 자리에 원문을 그대로 돌려준다(호출부가 404로 끝낸다).
    """
    match = BRIEFING_ID_PATTERN.fullmatch(str(report_id or "").strip())
    if match is None:
        return str(report_id or ""), None, "daily"
    date_text, market, kind_suffix = match.groups()
    return date_text, market, kind_suffix or "daily"


def _briefing_identity(report_id: str, market_scope: str | None) -> tuple[str, str | None, str | None]:
    normalized_scope = str(market_scope or "").strip().lower() or None
    markets = ", ".join(BRIEFING_MARKETS)
    if normalized_scope in {"both", "all"}:
        # 통합 범위는 파일 하나를 가리키지 않는다. 어느 시장을 쓰는지 밝혀야 한다.
        raise CanonicalIdentityError("briefing_overlay_scope_required", f"briefing scope must be one of {markets}")
    if normalized_scope is not None and normalized_scope not in BRIEFING_MARKETS:
        raise CanonicalIdentityError("briefing_scope_invalid", f"briefing scope must be one of {markets}")
    match = BRIEFING_ID_PATTERN.fullmatch(report_id)
    if match is None:
        raise CanonicalIdentityError("briefing_id_invalid", f"briefing id must be YYYY-MM-DD[.{'|.'.join(BRIEFING_MARKETS)}]")
    date_text, suffix, kind_suffix = match.groups()
    if suffix is not None and normalized_scope is not None and suffix != normalized_scope:
        raise CanonicalIdentityError("briefing_scope_mismatch", "briefing id suffix and scope differ")
    return date_text, normalized_scope or suffix, kind_suffix


def _read_report_id(folder: Path, filename: str) -> str | None:
    try:
        path = safe_child_path(folder, filename)
        # Path is bound by safe_child_path.
        # codeql[py/path-injection]
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    report_id = value.get("id")
    return report_id if isinstance(report_id, str) else None


def resolve_exact_report_path(
    data_root: Path,
    report_kind: ReportKind,
    report_id: str,
    market_scope: str | None = None,
) -> Path:
    match report_kind:
        case ReportKind.BRIEFING:
            date_text, scope, kind_suffix = _briefing_identity(report_id, market_scope)
            stem = f"{date_text}.{scope}" if scope is not None else date_text
            filename = f"{stem}.{kind_suffix}.json" if kind_suffix else f"{stem}.json"
            candidate = safe_child_path(data_root / "briefings", filename)
            # Fixed folder plus validated date/scope.
            # codeql[py/path-injection]
            if candidate.is_file():
                return candidate
        case ReportKind.COMPANY_ANALYSIS:
            if SAFE_ID_PATTERN.fullmatch(report_id) is None:
                raise CanonicalIdentityError("company_report_id_invalid", "company report id is invalid")
            filename = f"{report_id}.json"
            candidate = safe_child_path(data_root / "company-analysis", filename)
            # Fixed folder plus validated safe ID.
            # codeql[py/path-injection]
            if candidate.is_file() and _read_report_id(candidate.parent, candidate.name) in {None, report_id}:
                return candidate
        case ReportKind.TOPIC_REPORT:
            if SAFE_ID_PATTERN.fullmatch(report_id) is None:
                raise CanonicalIdentityError("topic_report_id_invalid", "topic report id is invalid")
            folder = data_root / "topic-reports"
            exact_matches = [
                safe_child_path(folder, path.name)
                for path in sorted(folder.glob("*.json"))
                if _read_report_id(folder, path.name) == report_id
            ]
            if len(exact_matches) == 1:
                return exact_matches[0]
            if len(exact_matches) > 1:
                raise CanonicalIdentityError("topic_report_id_conflict", "multiple topic reports have the same exact id")
        case unreachable:
            assert_never(unreachable)
    raise CanonicalNotFoundError("canonical_report_not_found", report_id)


def validate_report_identity(
    report_kind: ReportKind,
    exact_path: Path,
    report: Mapping[str, JsonValue],
) -> None:
    match report_kind:
        case ReportKind.BRIEFING:
            match = BRIEFING_FILE_PATTERN.fullmatch(exact_path.name)
            date_value = report.get("date")
            scope_value = report.get("marketScope")
            if match is None or date_value != match.group(1):
                raise CanonicalIdentityError("briefing_path_mismatch", "briefing date does not match exact path")
            if match.group(2) is not None and scope_value != match.group(2):
                raise CanonicalIdentityError("briefing_scope_mismatch", "briefing scope does not match exact path")
            # 파일 이름이 주간이라고 말하는데 본문이 일간이면 (또는 그 반대면) 그 보고서는
            # 다음 읽기에서 자기 종류를 잘못 말한다. 접미사와 `kind`를 여기서 묶어 둔다.
            path_kind = match.group(3) or "daily"
            report_kind_value = str(report.get("kind") or "daily").strip().lower() or "daily"
            if path_kind != report_kind_value:
                raise CanonicalIdentityError("briefing_kind_mismatch", "briefing kind does not match exact path")
        case ReportKind.COMPANY_ANALYSIS:
            if report.get("id") != exact_path.stem:
                raise CanonicalIdentityError("company_report_id_mismatch", "company report id does not match exact path")
        case ReportKind.TOPIC_REPORT:
            report_id = report.get("id")
            if not isinstance(report_id, str) or not (
                exact_path.stem == report_id or exact_path.stem.endswith(f"_{report_id}")
            ):
                raise CanonicalIdentityError("topic_report_id_mismatch", "topic report id does not match exact path")
        case unreachable:
            assert_never(unreachable)
