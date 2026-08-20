"""Cached, read-only metadata index for saved daily briefings."""

from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
from pathlib import Path

from features.common.generation_engine import engine_detail, engine_label
from features.daily_briefing.schema import (
    AGGREGATE_SCOPES,
    BRIEFING_KINDS,
    BRIEFING_TYPES,
    DEFAULT_BRIEFING_KIND,
    SINGLE_MARKET_SCOPES,
    briefing_archive_items,
    briefing_market_metadata,
    market_keys_for_briefing_scope,
    market_selection_scope,
    normalize_market_scope,
)
from features.common.workspace import data_dir


ROOT = Path(__file__).resolve().parents[2]
BRIEFINGS_DIR = data_dir() / "briefings"
# 사이드카(`.visuals.json`, `.link.json`)를 보고서로 읽지 않도록 시장 접미사를 고정한다.
_MARKET_ALTERNATION = "|".join(SINGLE_MARKET_SCOPES)
# 종류 접미사는 일간에만 없다. 새로 붙는 종류가 정규식에 없으면 그 파일은 아카이브에
# 아예 나타나지 않는다 — 저장은 되는데 화면에는 없는 상태가 된다.
_KIND_ALTERNATION = "|".join(sorted(BRIEFING_KINDS - {DEFAULT_BRIEFING_KIND}))
REPORT_FILE_RE = re.compile(
    rf"^\d{{4}}-\d{{2}}-\d{{2}}(?:\.(?:{_MARKET_ALTERNATION}))?(?:\.(?:{_KIND_ALTERNATION}))?\.json$"
)
SCOPED_REPORT_FILE_RE = re.compile(
    rf"^(?P<date>\d{{4}}-\d{{2}}-\d{{2}})\.(?P<market>{_MARKET_ALTERNATION})"
    rf"(?:\.(?P<kind>{_KIND_ALTERNATION}))?\.json$"
)


def _date(value, field):
    if not value:
        return ""
    try:
        return dt.date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def _bounded_int(value, field, minimum, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if number < minimum:
        raise ValueError(f"{field} must be {minimum} or greater")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return number


class BriefingArchiveIndex:
    def __init__(self, reports_dir, *, ttl_seconds=30, loader=None, clock=None):
        self.reports_dir = Path(reports_dir)
        self.ttl_seconds = max(0, int(ttl_seconds))
        self.loader = loader or self._load_json
        self.clock = clock or time.monotonic
        self._entries = {}
        self._last_scan = float("-inf")
        self._refreshed_at = ""
        self._lock = threading.RLock()

    @staticmethod
    def _load_json(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def _scan(self, force=False):
        now = self.clock()
        if not force and now - self._last_scan < self.ttl_seconds:
            return
        paths = sorted(
            path for path in self.reports_dir.glob("*.json")
            if REPORT_FILE_RE.fullmatch(path.name)
        ) if self.reports_dir.exists() else []
        refreshed = {}
        for path in paths:
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            current = self._entries.get(path)
            if current and current["signature"] == signature:
                refreshed[path] = current
                continue
            try:
                report = self.loader(path)
                sections = report.get("briefings") or {}
                rows = []
                for item in briefing_archive_items(report):
                    scope = item["marketScope"]
                    section = sections.get(scope) if isinstance(sections.get(scope), dict) else report
                    # 어느 모델이 썼는지. schema는 의존성 없는 계약 모듈이라 여기서 붙인다.
                    generation = section.get("generation") or report.get("generation")
                    item["engine"] = engine_label(generation)
                    item["engineDetail"] = engine_detail(generation)
                    search_text = " ".join((
                        item.get("title", ""),
                        item.get("summary", ""),
                        item.get("sessionDate", ""),
                        item.get("reportDate", ""),
                        str(section.get("markdown") or ""),
                    )).casefold()
                    rows.append({"item": item, "searchText": search_text})
                refreshed[path] = {"signature": signature, "rows": rows, "warning": ""}
            except Exception:
                refreshed[path] = {
                    "signature": signature,
                    "rows": [],
                    "warning": f"브리핑 파일을 읽지 못했습니다: {path.name}",
                }
        self._entries = refreshed
        self._last_scan = now
        self._refreshed_at = dt.datetime.now(dt.timezone.utc).isoformat()

    @staticmethod
    def _row_key(item):
        scope = item.get("marketScope", "")
        # **종류가 키에 들어간다.** 일요일 주간 브리핑의 세션일은 그 주 마지막 날이라
        # 같은 시장의 일간 카드와 겹칠 수 있고, 겹치면 둘 중 하나가 조용히 사라진다.
        kind = item.get("kind") or DEFAULT_BRIEFING_KIND
        if scope in SINGLE_MARKET_SCOPES:
            # 정체성은 **세션**이다. 저장 키가 세션일로 넘어가는 동안 같은 세션이 옛
            # 발행일 파일과 새 세션 파일 양쪽에 있을 수 있고, `reportDate`로 묶으면
            # 같은 장이 카드 두 장으로 보인다.
            return (item.get("sessionDate") or item.get("reportDate", ""), scope, kind)
        # 종합 카드에는 세션일이 하나로 정해지지 않는다.
        return (item.get("reportDate", ""), scope, kind)

    @staticmethod
    def _path_priority(path):
        return 1 if SCOPED_REPORT_FILE_RE.fullmatch(path.name) else 0

    def query(
        self, *, q="", market_scope="all", briefing_type="all", kind="all",
        date_from="", date_to="", offset=0, limit=20, force_refresh=False,
    ):
        market_scope = str(market_scope or "all").strip().lower()
        briefing_type = str(briefing_type or "all").strip().lower()
        kind = str(kind or "all").strip().lower()
        # `all` here means "no market filter" for the archive query, which is a
        # different word from the `all` briefing scope — a filter named after a
        # scope would silently hide every single-market card. `aggregate`
        # selects the multi-market cards regardless of which run produced them.
        if market_scope not in {"all", "aggregate", "both", *SINGLE_MARKET_SCOPES}:
            raise ValueError(
                "marketScope must be all, aggregate, us, kr, europe, jp, or both"
            )
        if briefing_type not in {"all", *BRIEFING_TYPES}:
            raise ValueError("briefingType must be all, default, market_focused, or concise")
        if kind not in {"all", *BRIEFING_KINDS}:
            raise ValueError("kind must be all, daily, or weekly")
        start = _date(date_from, "dateFrom")
        end = _date(date_to, "dateTo")
        if start and end and start > end:
            raise ValueError("dateFrom must be on or before dateTo")
        offset = _bounded_int(offset, "offset", 0)
        limit = _bounded_int(limit, "limit", 1, 100)
        needle = str(q or "").strip().casefold()

        with self._lock:
            self._scan(force=force_refresh)
            deduped = {}
            for path, entry in self._entries.items():
                base_priority = self._path_priority(path)
                for pair in entry["rows"]:
                    item = pair["item"]
                    # 이미 세션 키로 저장된 파일이 이긴다. 이관 중 둘이 공존하면
                    # 새 쪽이 권위이며, 옛 파일은 이관이 지울 때까지 조용히 가려진다.
                    priority = base_priority
                    session = str(item.get("sessionDate") or "")
                    if base_priority and session and path.name.startswith(f"{session}."):
                        priority += 1
                    key = self._row_key(item)
                    current = deduped.get(key)
                    if current is None or priority >= current["priority"]:
                        deduped[key] = {"pair": pair, "priority": priority}
            # 시장별 파일은 시장별 카드로 남는다. 예전에는 한 번의 다중 시장 생성에서
            # 나온 파일들을 카드 하나로 접었는데, US+KR을 함께 예약하면 그 카드가
            # 15,000자짜리 합본으로 열려 시장별 보고서가 화면에서 사라졌다.
            # 각 시장을 따로 읽는 것이 이 제품이 하려는 일이다(2026-08-10 사용자 결정).
            pairs = [value["pair"] for value in deduped.values()]
            warnings = [entry["warning"] for entry in self._entries.values() if entry["warning"]]
            refreshed_at = self._refreshed_at
            report_files = len(self._entries)

        filtered = []
        for pair in pairs:
            item = pair["item"]
            # `all`은 이 질의에서 "시장 필터 없음"이다(브리핑 범위의 `all`과 다른 말).
            # 다중 시장 카드만 보려면 `aggregate`를 쓴다.
            if market_scope == "aggregate":
                if item["reportScope"] not in AGGREGATE_SCOPES:
                    continue
            elif market_scope == "both":
                if item["reportScope"] != "both":
                    continue
            elif market_scope in SINGLE_MARKET_SCOPES and item["marketScope"] != market_scope:
                continue
            if briefing_type != "all" and item["briefingType"] != briefing_type:
                continue
            if kind != "all" and (item.get("kind") or DEFAULT_BRIEFING_KIND) != kind:
                continue
            searchable_dates = [
                value for value in (item.get("reportDate", ""), item.get("sessionDate", ""))
                if value
            ]
            if (start or end) and not any(
                (not start or value >= start) and (not end or value <= end)
                for value in searchable_dates
            ):
                continue
            if needle and needle not in pair["searchText"]:
                continue
            filtered.append(item)

        order = {key: index for index, key in enumerate((*SINGLE_MARKET_SCOPES, "both", "all"))}
        filtered.sort(key=lambda row: order.get(row["marketScope"], 9))
        filtered.sort(key=lambda row: row["reportDate"], reverse=True)
        total = len(filtered)
        return {
            "items": filtered[offset:offset + limit],
            "total": total,
            "offset": offset,
            "limit": limit,
            "warnings": warnings[:20],
            "cache": {"refreshedAt": refreshed_at, "reportFiles": report_files},
        }


_ARCHIVE_INDEX = BriefingArchiveIndex(BRIEFINGS_DIR)


def query_briefing_archive(
    *, q="", market_scope="all", briefing_type="all", kind="all",
    date_from="", date_to="", offset=0, limit=20,
):
    return _ARCHIVE_INDEX.query(
        q=q,
        market_scope=market_scope,
        briefing_type=briefing_type,
        kind=kind,
        date_from=date_from,
        date_to=date_to,
        offset=offset,
        limit=limit,
    )


def refresh_briefing_archive():
    """Force the cached archive index to rescan (e.g. after a delete)."""
    with _ARCHIVE_INDEX._lock:
        _ARCHIVE_INDEX._scan(force=True)
