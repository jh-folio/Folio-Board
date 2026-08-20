"""Daily briefing v2 contracts introduced by briefing upgrade Step 0.

This module is intentionally dependency-free.  Step 0 fixes the shape and enum
contracts before Step 1 changes selection or generation behavior.
"""

from __future__ import annotations

from copy import deepcopy
import re


# `both`는 US/KR만 담은 저장된 묶음이고 `all`은 네 시장이다. 둘을 하나로 합치면
# 예전 보고서가 담지 않은 시장을 담았다고 주장하게 된다.
# `multi`는 이름 없는 조합(예: 미국+일본)의 표시 레이블이다. 조합마다 이름을
# 만들면 추측이 자리만 옮긴다 — 실제 커버리지는 `includedMarkets`가 말한다.
MARKET_SCOPES = frozenset({"us", "kr", "europe", "jp", "all", "both", "multi"})
AGGREGATE_SCOPES = frozenset({"all", "both", "multi"})
SINGLE_MARKET_SCOPES = ("us", "kr", "europe", "jp")
LEGACY_AGGREGATE_MARKETS = ("us", "kr")
BRIEFING_TYPES = frozenset({"default", "market_focused", "concise"})
# 브리핑의 **종류**다. `briefingType`(편집 강조점)과 직교한다 — 그쪽은 세 값 모두
# "기존 섹션 구성을 유지하라"고 지시하므로 골격이 다른 주간 브리핑을 그 enum에 넣으면
# 계약이 자기 자신과 모순된다. 저장된 기존 예약·보고서에 이 값이 없으면 `daily`다.
BRIEFING_KINDS = frozenset({"daily", "weekly"})
DEFAULT_BRIEFING_KIND = "daily"
BRIEFING_KIND_TAGS = {"daily": "일간", "weekly": "주간"}
US_SESSION_MODES = frozenset({"us_close", "us_intraday", "us_holiday", "us_off_session"})
KR_SESSION_MODES = frozenset({"kr_close", "kr_intraday", "kr_holiday", "kr_off_session"})
# 유럽은 한국시간 자정 이후 마감해 미국과 같은 모양이고(장중 모드 없음),
# 일본은 한국과 같은 시간대라 장중이 있다.
EUROPE_SESSION_MODES = frozenset({"europe_close", "europe_holiday", "europe_off_session"})
JP_SESSION_MODES = frozenset({"jp_close", "jp_intraday", "jp_holiday", "jp_off_session"})
SESSION_MODES_BY_SCOPE = {
    "us": (US_SESSION_MODES, "us_off_session"),
    "kr": (KR_SESSION_MODES, "kr_off_session"),
    "europe": (EUROPE_SESSION_MODES, "europe_off_session"),
    "jp": (JP_SESSION_MODES, "jp_off_session"),
}
FRESHNESS_STATUSES = frozenset({
    "live",
    "partial_live",
    "delayed",
    "close_snapshot",
    "snapshot",
    "stale",
    "unavailable",
})
BODY_AVAILABILITY = frozenset({"full", "summary_only", "headline_only"})
MARKET_IMPACT_STATUSES = frozenset({"measured", "partial", "unavailable"})
VISUAL_MARKETS = frozenset({"US", "KR", "EUROPE", "JP", "BOTH", "ALL"})
VISUAL_TYPES = frozenset({"price_series", "market_heatmap", "index_chart"})
VISUAL_FAMILIES = frozenset({"trend", "composition"})
MARKET_TAGS = {
    "us": "미국장", "kr": "한국장", "europe": "유럽장", "jp": "일본장",
    "all": "종합", "both": "종합", "multi": "선택 시장",
}
MARKET_TITLE_LABELS = {
    "us": "US Market Briefing", "kr": "Korea Market Briefing",
    "europe": "Europe Market Briefing", "jp": "Japan Market Briefing",
}
BRIEFING_TYPE_TAGS = {"default": "기본", "market_focused": "시황중심", "concise": "요약"}
SESSION_STATUS_LABELS = {
    "us_close": "마감",
    "us_intraday": "장중",
    "us_holiday": "마감",
    "us_off_session": "마감",
    "kr_close": "마감",
    "kr_intraday": "장중",
    "kr_holiday": "마감",
    "kr_off_session": "마감",
    "europe_close": "마감",
    "europe_holiday": "마감",
    "europe_off_session": "마감",
    "jp_close": "마감",
    "jp_intraday": "장중",
    "jp_holiday": "마감",
    "jp_off_session": "마감",
}


def _scoped_file_stem(date, market_scope=None, kind=DEFAULT_BRIEFING_KIND):
    """저장 파일의 이름 줄기. **종류가 다르면 파일도 달라야 한다.**

    주간 브리핑에 접미사가 없으면 일요일 실행이 `{금요일}.{시장}.json`으로 떨어져
    그 주 금요일 일간 브리핑을 통째로 덮어쓴다 — 발행일 하나로는 두 보고서를
    구분할 수 없다. 일간은 접미사가 없어 기존 파일 이름이 그대로다.
    """
    date_text = str(date or "").strip()
    scope = str(market_scope or "").strip().lower()
    suffix = "" if normalize_briefing_kind(kind) == DEFAULT_BRIEFING_KIND else f".{normalize_briefing_kind(kind)}"
    if scope in SINGLE_MARKET_SCOPES:
        return f"{date_text}.{scope}{suffix}"
    return f"{date_text}{suffix}"


def briefing_file_name(date, market_scope=None, kind=DEFAULT_BRIEFING_KIND):
    """Return a briefing report filename.

    The no-scope form is kept for legacy read compatibility.  New writes should
    pass ``us`` or ``kr`` and produce one file per market.
    """
    return f"{_scoped_file_stem(date, market_scope, kind)}.json"


def briefing_link_file_name(date):
    """Legacy cross-market sidecar name, kept only so deletion still finds it.

    Connection analysis was removed: with a seven-driver taxonomy every market
    shared every driver, so "common flows" grew while the differences — the part
    that carried information — went blank. Sidecars saved before then stay on
    disk; nothing reads them, and deleting a briefing still cleans them up.
    """
    return f"{_scoped_file_stem(date)}.link.json"


def visual_sidecar_file_name(date, market_scope=None, kind=DEFAULT_BRIEFING_KIND):
    """Large visual constituents are stored beside the dated/scoped report."""
    return f"{_scoped_file_stem(date, market_scope, kind)}.visuals.json"


def visual_sidecar_gzip_file_name(date, market_scope=None, kind=DEFAULT_BRIEFING_KIND):
    """Compressed visual sidecar used by schema v2 reports."""
    return f"{_scoped_file_stem(date, market_scope, kind)}.visuals.json.gz"


def _normalize_enum(value, allowed, default):
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def normalize_market_scope(value):
    return _normalize_enum(value, MARKET_SCOPES, "both")


def normalize_briefing_type(value):
    return _normalize_enum(value, BRIEFING_TYPES, "default")


def normalize_briefing_kind(value):
    return _normalize_enum(value, BRIEFING_KINDS, DEFAULT_BRIEFING_KIND)


def briefing_type_instruction(value):
    """Return the shared editorial contract for API, CLI, and rules paths."""
    briefing_type = normalize_briefing_type(value)
    if briefing_type == "market_focused":
        return (
            "기존 섹션을 삭제하지 말고 전체 구성을 유지하세요. 시장 흐름과 핵심 변수의 비중을 높여 "
            "지수·금리·환율·수급·시장 폭·섹터 내부 흐름을 먼저 해석하고, 기업 뉴스도 시장 전체에 "
            "미친 영향과 연결하세요."
        )
    if briefing_type == "concise":
        return (
            "기존 섹션을 모두 유지하되 각 섹션의 한 줄 결론과 가운뎃점 요약 뒤 줄글을 짧게 "
            "압축하세요. 근거 수치, 인과관계, 반대 신호와 체크포인트는 생략하지 마세요."
        )
    return "현재 전체 구성과 분량을 유지하고 기존 섹션의 균형을 바꾸지 마세요."


def normalize_us_session_mode(value):
    return _normalize_enum(value, US_SESSION_MODES, "us_off_session")


def normalize_kr_session_mode(value):
    return _normalize_enum(value, KR_SESSION_MODES, "kr_off_session")


def normalize_session_mode(scope, value):
    allowed, default = SESSION_MODES_BY_SCOPE.get(normalize_market_scope(scope), (frozenset(), ""))
    return _normalize_enum(value, allowed, default) if allowed else ""


def market_keys_for_briefing_scope(value):
    """The markets a scope covers.

    `both` stays two markets forever: reports saved under it never held Europe
    or Japan, and widening it retroactively would claim coverage that was never
    generated.

    `multi` names a set the label cannot describe, so this returns every market
    as a **search space** — "look for any of these" — not as a coverage claim.
    What a `multi` report actually holds is in its stored market list, which is
    why the read path prefers that over this.
    """
    scope = normalize_market_scope(value)
    if scope in {"all", "multi"}:
        return SINGLE_MARKET_SCOPES
    if scope == "both":
        return LEGACY_AGGREGATE_MARKETS
    return (scope,)


def normalize_market_selection(value, *, default=LEGACY_AGGREGATE_MARKETS):
    """Resolve a requested market set from either a list or a legacy scope name.

    The selector is a set of markets, not a scope: {US, JP} is a perfectly good
    request and no scope name describes it. A scope string still resolves, so
    saved settings and old callers keep working, but the market list is what
    generation actually runs on.

    Order follows the market contract rather than the caller, so the same set
    always produces the same file order and the same archive card.
    """
    if isinstance(value, str) or value is None:
        text = str(value or "").strip()
        if not text:
            return tuple(default)
        # 쉼표 목록도 받는다. 쿼리스트링에서는 리스트가 문자열로 도착한다.
        if "," in text:
            value = text.split(",")
        else:
            return market_keys_for_briefing_scope(text)
    selected = set()
    for item in value:
        scope = str(item or "").strip().lower()
        if scope in SINGLE_MARKET_SCOPES:
            selected.add(scope)
        elif scope in AGGREGATE_SCOPES:
            selected.update(market_keys_for_briefing_scope(scope))
    ordered = tuple(key for key in SINGLE_MARKET_SCOPES if key in selected)
    return ordered or tuple(default)


def market_selection_scope(markets):
    """A display label for a market set.

    `all` and `both` are kept for the sets they have always meant so saved
    reports and archive filters keep their behavior. Every other combination is
    `multi`: inventing a name per subset would just move the guessing, and
    `includedMarkets` is what a reader should trust anyway.
    """
    selected = tuple(markets or ())
    if len(selected) == 1:
        return selected[0]
    if set(selected) == set(SINGLE_MARKET_SCOPES):
        return "all"
    if set(selected) == set(LEGACY_AGGREGATE_MARKETS):
        return "both"
    return "multi"


def _dotted_date(value):
    text = str(value or "").strip()[:10]
    return text.replace("-", ".") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else text


def _session_mode_from_phase(scope, phase, *, has_intraday):
    """Map a session descriptor phase onto this scope's mode enum."""
    if phase == "holiday":
        return f"{scope}_holiday"
    if has_intraday and phase == "intraday":
        return f"{scope}_intraday"
    if phase in {"pre_open", "closed", "intraday"}:
        return f"{scope}_close"
    return ""


def briefing_session_mode(scope, value="", market_windows=None):
    normalized_scope = normalize_market_scope(scope)
    raw = str(value or "").strip().lower()
    if normalized_scope == "us":
        return normalize_us_session_mode(raw or "us_close")
    if normalized_scope == "kr":
        if raw:
            return normalize_kr_session_mode(raw)
        windows = market_windows or {}
        phase = str(windows.get("krSessionPhase") or "")
        if phase == "intraday":
            return "kr_intraday"
        if phase in {"pre_open", "closed"}:
            return "kr_close"
        if phase == "holiday":
            return "kr_holiday"
        # phase가 없는 legacy window. 거래일이라는 사실만으로 장중이라고 하면
        # 지난 세션도 진행 중으로 읽힌다 — 세션일이 오늘이고 정규장 시간 안일
        # 때만 장중이다.
        from features.common.market_calendar import kr_session_is_open_now

        return "kr_intraday" if kr_session_is_open_now(windows) else "kr_close"
    if normalized_scope in {"europe", "jp"}:
        if raw:
            return normalize_session_mode(normalized_scope, raw)
        session = ((market_windows or {}).get("marketSessions") or {}).get(normalized_scope) or {}
        if not session:
            return f"{normalized_scope}_close"
        if not session.get("openOnBriefingDate"):
            return f"{normalized_scope}_holiday"
        # 유럽은 한국시간 자정 이후 마감하므로 장중 모드가 없다.
        mode = _session_mode_from_phase(
            normalized_scope,
            str(session.get("phase") or "closed"),
            has_intraday=normalized_scope == "jp",
        )
        return mode or f"{normalized_scope}_close"
    return ""


def _session_date_from_windows(scope, windows, session_mode=""):
    """이 시장의 세션일을 창에서 읽는다. 창에 답이 없으면 빈 문자열."""
    if scope == "us":
        return str(windows.get("usRegularSessionDate") or "")[:10]
    if scope == "kr":
        mode = briefing_session_mode("kr", session_mode, windows)
        if mode in {"kr_intraday", "kr_close"} and windows.get("krCurrentSessionDate"):
            return str(windows.get("krCurrentSessionDate"))[:10]
        return str(windows.get("krPreviousSessionDate") or "")[:10]
    if scope in {"europe", "jp"}:
        session = (windows.get("marketSessions") or {}).get(scope) or {}
        # 장중이면 진행 중인 세션이 이 브리핑의 세션이다. 창의 `sessionDate`는 직전
        # 완료 세션이라 그대로 읽으면 제목이 이미 끝난 세션을 `장중`이라고 말한다.
        # (유럽은 `phase` 키 자체가 없어 이 분기에 걸리지 않는다.)
        if session.get("phase") == "intraday" and windows.get("briefingDate"):
            return str(windows.get("briefingDate"))[:10]
        return str(session.get("sessionDate") or "")[:10]
    return ""


def briefing_session_date(report_date, scope, *, session_date="", session_mode="", market_windows=None):
    """이 브리핑이 다루는 거래일.

    **창이 있으면 창이 권위다.** 저장된 `sessionDate`는 원래 이 창에서 파생된 값이라
    제대로 만들어진 보고서에서는 둘이 같다. 다른 경우는 창을 못 받고 만들어져 발행일이
    박힌 보고서뿐이고, 그때 저장값을 믿으면 틀린 제목이 영원히 남는다 — 실제로 월요일
    08:03에 만든 브리핑이 아직 열지도 않은 그날 장을 `2026.08.10 마감`이라고 계속
    말했다. 창을 권위로 두면 이미 저장된 보고서도 읽을 때 제자리를 찾는다.

    창이 없는 옛 보고서는 저장값을 그대로 쓴다.
    """
    windows = market_windows or {}
    normalized_scope = normalize_market_scope(scope)
    from_windows = _session_date_from_windows(normalized_scope, windows, session_mode)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", from_windows or ""):
        return from_windows
    explicit = str(session_date or "").strip()[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", explicit):
        return explicit
    return str(report_date or "")[:10]


def briefing_market_title(report_date, scope, *, session_date="", session_mode="", market_windows=None):
    normalized_scope = normalize_market_scope(scope)
    if normalized_scope in AGGREGATE_SCOPES:
        return f"Daily Market Briefing — {_dotted_date(report_date)}"
    mode = briefing_session_mode(normalized_scope, session_mode, market_windows)
    resolved_date = briefing_session_date(
        report_date,
        normalized_scope,
        session_date=session_date,
        session_mode=mode,
        market_windows=market_windows,
    )
    label = MARKET_TITLE_LABELS.get(normalized_scope, "Daily Market Briefing")
    status = SESSION_STATUS_LABELS.get(mode, "마감")
    return f"{label} — {_dotted_date(resolved_date)} {status}".strip()


def briefing_expected_titles(report_date, market_scope, *, market_windows=None, session_modes=None):
    scope = normalize_market_scope(market_scope)
    modes = session_modes or {}
    targets = market_keys_for_briefing_scope(scope)
    return {
        target: briefing_market_title(
            report_date,
            target,
            session_mode=modes.get(target, ""),
            market_windows=market_windows,
        )
        for target in targets
    }


def normalize_briefing_markdown_titles(
    markdown, report_date, market_scope, *, market_windows=None, session_modes=None,
):
    text = str(markdown or "")
    for scope, title in briefing_expected_titles(
        report_date,
        market_scope,
        market_windows=market_windows,
        session_modes=session_modes,
    ).items():
        heading = MARKET_TITLE_LABELS.get(scope, "")
        if not heading:
            continue
        text = re.sub(
            rf"(?m)^#\s+{re.escape(heading)}(?:\s+[—-]\s+[^\r\n]+)?\s*$",
            f"# {title}",
            text,
            count=1,
        )
    return text


def normalize_freshness(value):
    return _normalize_enum(value, FRESHNESS_STATUSES, "unavailable")


def normalize_body_availability(value):
    return _normalize_enum(value, BODY_AVAILABILITY, "headline_only")


def normalize_market_impact_status(value):
    return _normalize_enum(value, MARKET_IMPACT_STATUSES, "unavailable")


def normalize_briefing_contract(report):
    """Return a backward-compatible v2 view without mutating the saved report.

    Legacy reports keep their canonical markdown and Personal Overlay byte-for-
    byte at the value level.  New structured fields are empty defaults until
    the corresponding implementation Step populates them.
    """
    if not isinstance(report, dict):
        return {}
    out = deepcopy(report)
    out["marketScope"] = normalize_market_scope(out.get("marketScope"))
    out["briefingType"] = normalize_briefing_type(out.get("briefingType"))
    out.setdefault("briefings", {})
    out.setdefault("visualRecommendations", [])
    out.setdefault("visualSnapshots", [])
    out.setdefault("issueCoverage", [])
    return out


def _plain_excerpt(value, limit=240):
    text = re.sub(r"[`*_>#\[\]()-]+", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _effective_market_windows(report):
    """Return read-time session windows for both new and legacy reports."""
    windows = report.get("marketWindows") or {}
    if (
        not windows
        or not windows.get("briefingDate")
        or windows.get("krSessionPhase")
        or not report.get("generatedAt")
    ):
        return windows
    try:
        from features.common.market_calendar import align_briefing_market_windows_to_as_of

        return align_briefing_market_windows_to_as_of(windows, report.get("generatedAt"))
    except Exception:
        return windows


def _weekly_metadata(report, source, scope, report_date, briefing_type, report_scope):
    """주간 보고서의 카드 메타. **세션을 되짚지 않는다.**

    주간에는 세션일도 `마감`/`장중`도 없다. 창(`weekStart`~`weekEnd`)이 저장돼 있고
    제목은 거기서 나온다 — 세션 판정을 태우면 발행일 기준 직전 세션이 끼어들어
    일요일 주간 보고서가 금요일 마감이라고 말하게 된다.
    """
    from features.daily_briefing.weekly import WeeklyWindow, weekly_title

    week_start = str(source.get("weekStart") or report.get("weekStart") or "")[:10]
    week_end = str(source.get("weekEnd") or report.get("weekEnd") or "")[:10] or report_date
    window = WeeklyWindow(
        publication_date=report_date,
        week_start=week_start or report_date,
        week_end=week_end,
        preview_start=str(source.get("previewStart") or report.get("previewStart") or "")[:10],
        preview_end=str(source.get("previewEnd") or report.get("previewEnd") or "")[:10],
    )
    default_title = weekly_title(scope, window) if scope in SINGLE_MARKET_SCOPES else str(
        source.get("title") or report.get("title") or ""
    )
    summary = source.get("summary") or report.get("summary") or _plain_excerpt(
        source.get("markdown") or report.get("markdown")
    )
    return {
        "id": f"{report_date}:{scope}:weekly",
        "reportDate": report_date,
        "reportScope": report_scope,
        "marketScope": scope,
        "kind": "weekly",
        "briefingType": briefing_type,
        "generatedAt": source.get("generatedAt") or report.get("generatedAt") or "",
        # 날짜 필터가 걸리도록 구간 끝을 세션일 자리에 둔다. 주간에 세션은 없지만
        # 아카이브의 날짜 질의는 이 두 값만 본다.
        "sessionDate": window.week_end,
        "sessionMode": "",
        "weekStart": window.week_start,
        "weekEnd": window.week_end,
        "previewStart": window.preview_start,
        "previewEnd": window.preview_end,
        "publicationDate": report_date,
        "title": default_title or str(source.get("title") or report.get("title") or ""),
        "summary": _plain_excerpt(summary),
        "tags": [MARKET_TAGS[scope], BRIEFING_KIND_TAGS["weekly"]],
        "combinedGeneration": False,
        "generationScope": "",
        "generationMarkets": [],
    }


def briefing_market_metadata(report, market_scope, section=None):
    source = section if isinstance(section, dict) else {}
    report_date = str(report.get("date") or "").strip()
    scope = normalize_market_scope(market_scope)
    report_scope = normalize_market_scope(report.get("marketScope"))
    briefing_type = normalize_briefing_type(source.get("briefingType") or report.get("briefingType"))
    kind = normalize_briefing_kind(source.get("kind") or report.get("kind"))
    if kind == "weekly":
        return _weekly_metadata(report, source, scope, report_date, briefing_type, report_scope)
    stored_market_windows = report.get("marketWindows") or {}
    market_windows = _effective_market_windows(report)
    raw_session_mode = source.get("sessionMode") or report.get("sessionMode")
    # Reports saved before phase-aware windows could persist an intraday mode
    # merely because the target date was a trading day. Re-resolve those from
    # the actual generation timestamp.
    if not stored_market_windows.get("krSessionPhase") and scope == "kr":
        raw_session_mode = ""
    session_mode = briefing_session_mode(
        scope,
        raw_session_mode,
        market_windows,
    )
    session_date = briefing_session_date(
        report_date,
        scope,
        session_date=source.get("sessionDate") or source.get("marketSessionDate") or report.get("sessionDate") or report.get("marketSessionDate"),
        session_mode=session_mode,
        market_windows=market_windows,
    )
    default_title = briefing_market_title(
        report_date,
        scope,
        session_date=session_date,
        session_mode=session_mode,
        market_windows=market_windows,
    )
    summary = source.get("summary") or report.get("summary") or _plain_excerpt(
        source.get("markdown") or report.get("markdown")
    )
    # `generationScope` is only written on per-market files produced by an
    # aggregate generation; legacy combined `{date}.json` files don't carry it.
    # Explicit (non-normalized) check so a missing field never defaults to an
    # aggregate. The value is carried through so the archive knows whether a
    # group came from a two-market `both` run or a four-market `all` run — the
    # file set alone cannot say, because an `all` run can lose two markets.
    generation_scope = str(report.get("generationScope") or "").strip().lower()
    generation_markets = [
        str(key).lower() for key in (report.get("generationMarkets") or [])
        if str(key).lower() in SINGLE_MARKET_SCOPES
    ]
    combined_generation = generation_scope in AGGREGATE_SCOPES or len(generation_markets) > 1
    return {
        "id": f"{report_date}:{scope}",
        "reportDate": report_date,
        "reportScope": report_scope,
        "marketScope": scope,
        "kind": kind,
        "briefingType": briefing_type,
        "generatedAt": source.get("generatedAt") or report.get("generatedAt") or "",
        "sessionDate": session_date,
        "sessionMode": session_mode,
        "publicationDate": report_date,
        "title": default_title if scope in SINGLE_MARKET_SCOPES else str(source.get("title") or default_title),
        "summary": _plain_excerpt(summary),
        "tags": [MARKET_TAGS[scope], BRIEFING_TYPE_TAGS[briefing_type]],
        "combinedGeneration": combined_generation,
        "generationScope": generation_scope if combined_generation else "",
        # 조합에 이름이 없을 수 있으므로 목록이 묶음의 기준이다.
        "generationMarkets": generation_markets if combined_generation else [],
    }


def enrich_briefing_sections(
    sections, *, report_date, report_scope, briefing_type, generated_at, report_summary="",
    market_windows=None, kind=DEFAULT_BRIEFING_KIND, weekly_window=None,
):
    """시장별 섹션에 제목·세션일·세션모드를 붙인다.

    `market_windows`가 곧 세션 판정의 근거다. 넘기지 않으면 `briefing_market_metadata`가
    창을 못 봐서 세션일이 발행일로 떨어지고, KR은 `krSessionPhase`가 없다는 이유로
    세션 모드까지 버린다(위 421행 가드). 그래서 08:00에 만든 브리핑이 아직 열지도 않은
    그날 장을 "마감"이라 하고, 장중 생성은 "장중"이 아예 나오지 않았다.

    창은 호출부가 이미 들고 있다 — 문서 선별(`select_briefing_docs`)이 돌려준 그 값이며,
    생성 시각(`as_of`) 기준으로 phase가 매겨져 있다.
    """
    kind = normalize_briefing_kind(kind)
    report = {
        "date": report_date,
        "marketScope": report_scope,
        "briefingType": briefing_type,
        "kind": kind,
        "generatedAt": generated_at,
        "summary": report_summary,
        "marketWindows": market_windows or {},
        **({
            "weekStart": str((weekly_window or {}).get("weekStart") or ""),
            "weekEnd": str((weekly_window or {}).get("weekEnd") or ""),
            "previewStart": str((weekly_window or {}).get("previewStart") or ""),
            "previewEnd": str((weekly_window or {}).get("previewEnd") or ""),
        } if kind == "weekly" else {}),
    }
    carried = (
        "marketScope", "briefingType", "kind", "generatedAt", "sessionDate",
        "publicationDate", "title", "summary", "tags",
        "weekStart", "weekEnd", "previewStart", "previewEnd",
    ) if kind == "weekly" else (
        "marketScope", "briefingType", "kind", "generatedAt", "sessionDate", "sessionMode",
        "publicationDate", "title", "summary", "tags",
    )
    enriched = {}
    for scope, raw in deepcopy(sections or {}).items():
        if scope not in SINGLE_MARKET_SCOPES or not isinstance(raw, dict):
            enriched[scope] = deepcopy(raw)
            continue
        section = deepcopy(raw)
        metadata = briefing_market_metadata(report, scope, section)
        section.update({key: metadata[key] for key in carried})
        enriched[scope] = section
    return enriched


def briefing_archive_items(report):
    normalized = normalize_briefing_contract(report)
    sections = normalized.get("briefings") or {}
    scopes = [scope for scope in SINGLE_MARKET_SCOPES if isinstance(sections.get(scope), dict)]
    if scopes:
        return [briefing_market_metadata(normalized, scope, sections[scope]) for scope in scopes]
    return [briefing_market_metadata(normalized, normalized.get("marketScope", "both"), normalized)]


def briefing_export_units(report):
    """Return immutable destination units for market-safe report exports."""
    normalized = normalize_briefing_contract(report)
    sections = normalized.get("briefings") or {}
    report_scope = normalized.get("marketScope", "both")
    if report_scope in SINGLE_MARKET_SCOPES:
        scopes = [report_scope]
    else:
        scopes = [scope for scope in SINGLE_MARKET_SCOPES if isinstance(sections.get(scope), dict)]
    if not scopes:
        scopes = [report_scope]

    units = []
    for scope in scopes:
        source = sections.get(scope) if isinstance(sections.get(scope), dict) else normalized
        unit = briefing_scope_view(normalized, scope)
        unit.update(briefing_market_metadata(normalized, scope, source))
        units.append(unit)
    return units


def briefing_scope_view(report, market_scope=None):
    out = normalize_briefing_contract(report)
    effective_market_windows = _effective_market_windows(out)
    scope = normalize_market_scope(market_scope or out.get("marketScope"))
    report_kind = normalize_briefing_kind(out.get("kind"))
    if scope in AGGREGATE_SCOPES and report_kind == "weekly":
        # 주간 종합 뷰는 시장별 본문을 그대로 잇는다. 세션 제목 정규화도, 세션 기준
        # 종합 제목도 주간에는 성립하지 않는다.
        from features.daily_briefing.weekly import WeeklyWindow

        window = WeeklyWindow(
            publication_date=str(out.get("date") or ""),
            week_start=str(out.get("weekStart") or out.get("date") or ""),
            week_end=str(out.get("weekEnd") or out.get("date") or ""),
            preview_start=str(out.get("previewStart") or ""),
            preview_end=str(out.get("previewEnd") or ""),
        )
        out["publicationDate"] = str(out.get("date") or "")
        out["title"] = f"Weekly Market Briefing — {window.label}"
        return out
    if scope in AGGREGATE_SCOPES:
        report_date = str(out.get("date") or "")
        modes = {
            target: briefing_session_mode(target, "", effective_market_windows)
            for target in market_keys_for_briefing_scope(scope)
        }
        out["markdown"] = normalize_briefing_markdown_titles(
            out.get("markdown", ""),
            report_date,
            scope,
            market_windows=effective_market_windows,
            session_modes=modes,
        )
        out["marketWindows"] = effective_market_windows
        out["publicationDate"] = report_date
        out["title"] = briefing_market_title(report_date, scope)
        return out
    report_scope = normalize_market_scope(out.get("marketScope"))
    if not out.get("briefings") and report_scope in SINGLE_MARKET_SCOPES and scope != report_scope:
        return out
    scoped = out.get("briefings", {}).get(scope)
    if not isinstance(scoped, dict):
        scoped = out
    view = deepcopy(out)
    view["marketScope"] = scope
    metadata = briefing_market_metadata(out, scope, scoped)
    if metadata.get("kind") == "weekly":
        # 주간 본문은 세션 제목 정규화를 태우지 않는다. 그 정규화는 H1을
        # `{라벨} — {세션일} {마감|장중}`으로 다시 쓰는 일이라, 주간 제목을 만나면
        # 구간이 세션일로 바뀌어 보고서가 스스로를 잘못 소개하게 된다.
        view["markdown"] = scoped.get("markdown", view.get("markdown", ""))
        view["sources"] = scoped.get("sources", view.get("sources", []))
        view["generation"] = scoped.get("generation", view.get("generation", {}))
        view.update({key: metadata[key] for key in (
            "kind", "weekStart", "weekEnd", "previewStart", "previewEnd",
            "sessionDate", "publicationDate", "title", "summary", "tags",
        )})
        return view
    view["markdown"] = normalize_briefing_markdown_titles(
        scoped.get("markdown", view.get("markdown", "")),
        metadata["reportDate"],
        scope,
        market_windows=effective_market_windows,
        session_modes={scope: metadata.get("sessionMode", "")},
    )
    view["marketWindows"] = effective_market_windows
    view["sources"] = scoped.get("sources", view.get("sources", []))
    view["generation"] = scoped.get("generation", view.get("generation", {}))
    view.update({key: metadata[key] for key in (
        "kind", "sessionDate", "sessionMode", "publicationDate", "title", "summary", "tags",
    )})
    return view


def split_market_markdown(markdown, market_scope="both"):
    """Split an agent/LLM combined response into stored market sections."""
    text = str(markdown or "").strip()
    scope = normalize_market_scope(market_scope)
    if scope in SINGLE_MARKET_SCOPES:
        return {scope: {"markdown": text}}
    patterns = [
        (key, rf"(?m)^#\s+{re.escape(label)}\b")
        for key, label in MARKET_TITLE_LABELS.items()
    ]
    # 연결 분석 제목은 계속 인식한다. 더 만들지는 않지만, 예전 종합 응답을 다시
    # 나눌 때 이 구획을 못 알아보면 그 본문이 앞 시장 섹션에 딸려 들어간다.
    patterns.append(("link", r"(?m)^##\s+(?:한미 시장 연결 요약|한미 시장 연결 분석|시장 간 연결 요약)\b"))
    starts = []
    for key, pattern in patterns:
        match = re.search(pattern, text)
        if match:
            starts.append((match.start(), key))
    starts.sort()
    if not starts:
        return {}
    result = {}
    for index, (start, key) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        result[key] = {"markdown": text[start:end].strip()}
    return result


def merge_briefing_report(report, existing, market_scope="both"):
    """Merge one regenerated market without discarding its sibling scope."""
    if not isinstance(existing, dict):
        return report
    merged = deepcopy(report)
    scope = normalize_market_scope(market_scope)
    if scope not in AGGREGATE_SCOPES:
        scopes = deepcopy(existing.get("briefings") or {})
        incoming_sections = deepcopy(report.get("briefings") or {})
        if incoming_sections:
            scopes.update(incoming_sections)
        elif scopes and report.get("markdown"):
            scopes[scope] = {
                **deepcopy(scopes.get(scope) or {}),
                "markdown": report.get("markdown", ""),
                "sources": deepcopy(report.get("sources") or []),
                "generation": deepcopy(report.get("generation") or {}),
            }
        if incoming_sections or scopes:
            merged["briefings"] = scopes
        if incoming_sections:
            ordered = [scopes.get(key, {}).get("markdown", "") for key in SINGLE_MARKET_SCOPES]
            merged["markdown"] = "\n\n---\n\n".join(part for part in ordered if part)
        target_market = scope.upper()
        for field in ("visualRecommendations", "visualSnapshots"):
            preserved = [
                item for item in deepcopy(existing.get(field) or [])
                if str(item.get("market") or "").upper() != target_market
            ]
            incoming = deepcopy(report.get(field) or [])
            merged[field] = preserved + incoming
    if existing.get("personalOverlay"):
        overlay = deepcopy(existing["personalOverlay"])
        if existing.get("markdown") != merged.get("markdown"):
            overlay["stale"] = True
        merged["personalOverlay"] = overlay
    return merged


def visual_snapshot_errors(snapshot):
    """Validate the minimum reproducibility metadata for a stored visual."""
    if not isinstance(snapshot, dict):
        return ["snapshot must be an object"]
    errors = []
    for field in ("id", "type", "market", "asOf", "provider", "freshness", "coverage"):
        if not snapshot.get(field):
            errors.append(f"missing {field}")
    market = str(snapshot.get("market") or "").upper()
    if market and market not in VISUAL_MARKETS:
        errors.append("invalid market")
    freshness = str(snapshot.get("freshness") or "").lower()
    if freshness and freshness not in FRESHNESS_STATUSES:
        errors.append("invalid freshness")
    visual_type = str(snapshot.get("type") or "").lower()
    if visual_type and visual_type not in VISUAL_TYPES:
        errors.append("invalid type")
    if visual_type in {"price_series", "market_heatmap"}:
        for field in ("marketSessionDate", "timezone", "currency"):
            if not snapshot.get(field):
                errors.append(f"missing {field}")
        coverage = snapshot.get("coverage")
        if not isinstance(coverage, dict):
            errors.append("coverage must be an object")
        elif coverage.get("status") not in {"complete", "partial", "unavailable"}:
            errors.append("invalid coverage status")
        if str(snapshot.get("asOf") or "")[:10] > str(snapshot.get("marketSessionDate") or "")[:10]:
            errors.append("asOf exceeds marketSessionDate")
    return errors


def visual_recommendation_errors(recommendation):
    if not isinstance(recommendation, dict):
        return ["recommendation must be an object"]
    errors = []
    for field in ("id", "snapshotId", "market", "role", "family", "variant", "title", "renderer"):
        if not recommendation.get(field):
            errors.append(f"missing {field}")
    if recommendation.get("family") not in VISUAL_FAMILIES:
        errors.append("invalid family")
    if str(recommendation.get("market") or "").upper() not in VISUAL_MARKETS:
        errors.append("invalid market")
    return errors
