"""Conservative, market-scoped final checks for generated briefings.

Production finalization performs only structural, source-safety, storage, and
cancellation/deadline checks. It does not fetch data, assess prose, call a
model, or rewrite authored Markdown. The fact evaluator below remains an
explicit offline diagnostic surface and is not part of the production write
gate.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date as calendar_date
import math
import re
from typing import Any

from features.common.quality_generation.call_budget import SharedRepairBudget
from features.daily_briefing.source_integrity import (
    MANIFEST_END,
    MANIFEST_START,
    markdown_external_links,
    normalize_source_url,
    stable_source_id,
)


_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-./](\d{1,2})[-./](\d{1,2})(?!\d)")
_PERCENT_RE = re.compile(
    r"(?<![\d.])([+-]?\s*(?:(?:\d{1,3}(?:,\d{3})+)|\d+)(?:\.\d+)?)\s*%"
)
_FLOW_RE = re.compile(
    r"(?P<sign>[+-])?\s*(?:(?P<trillion>\d+(?:\.\d+)?)\s*조\s*)?"
    r"(?P<eok>\d+(?:,\d+)?(?:\.\d+)?)\s*억\s*원"
)
_NUMBER_RE = re.compile(
    r"(?<![\d.])([+-]?\s*(?:(?:\d{1,3}(?:,\d{3})+)|\d+)(?:\.\d+)?)(?![\d.])"
)
# 변동폭은 시세가 아니다.  이 가드가 포인트에만 걸려 있어 "전일 대비 22.0원
# 하락한 1,341.73원"의 22.0이 환율 자체로 읽혔고, 사실이 맞는 문장이
# value_mismatch로 거절돼 CLI 브리핑이 규칙 대체로 떨어졌다.  원화도 같은
# 가드를 받는다.
_CHANGE_UNIT_RE = re.compile(r"\s*(?:포인트|원|₩|(?:points?|pt|won|krw)\b)")
_CHANGE_CONTEXT_RE = re.compile(r"(?:전일보다|대비|보다|rose|fell|up|down)\s*$", re.I)
# 단위 뒤에 붙은 등락 서술도 변동폭을 가리킨다 — "308.18포인트 오른 6,995.39에
# 마감했다"의 308.18은 시세가 아니다.  앞의 "전일 대비"가 없는 형태가 실제로 나왔다.
_CHANGE_MOVE_RE = re.compile(
    r"\s*(?:오른|올라|올랐|상승|내린|내려|내렸|하락|급등|급락|rose|fell|up|down)"
)
# 라운드 지수대는 시세 주장이 아니다 — "7,000선 접근", "7,000선에", "WTI 90달러선".
# 조사가 바로 붙으므로(선에/선을/대의) 뒤 글자를 막으면 안 된다.  "대비"만 뺀다 —
# 그것은 비교 서술이지 지수대가 아니다.
_THRESHOLD_RE = re.compile(r"\s*(?:선|대(?!비))")
# 개장 서술의 숫자는 종가가 아니다 — "6,910.78로 3.34% 상승 출발한 뒤 …
# 6,995.39에 마감했다"의 앞 절은 시가를 말한다.
_OPEN_CLAUSE_RE = re.compile(r"출발|개장|시초|장\s*초반|거래를?\s*시작|at the open|opened", re.I)
_OPEN_TRANSITION_RE = re.compile(r"(?:출발|개장|거래를?\s*시작)(?:한\s*뒤|하고|해)")
# 절 경계.  숫자 안의 쉼표(1,094억원)와 소수점(1.71)은 경계가 아니다.
# 값을 그 지표에서 떼어 놓는 문자는 경계가 아니다 — 표의 칸 구분자(|),
# USD/KRW의 /, 그리고 "KOSPI: 6,995.39"의 :.  경계로 보면 표의 값이 그 지표에서
# 떨어져 나가 required_omission이 된다.
_CLAUSE_BREAK_RE = re.compile(r"(?<!\d)[,;](?!\d)|[.!?](?=\s)")
_UNIT_RE = re.compile(r"\s*(원|krw|₩|달러|usd|\$|포인트|points?|pt)")

_POSITIVE_WORDS = (
    "상승", "오름", "올랐", "반등", "강세", "선방", "우위", "방어",
    "rise", "rises", "rose", "up", "outperform", "strength", "defensive",
)
_NEGATIVE_WORDS = (
    "하락", "내림", "떨어", "내렸", "약세", "급락", "부진",
    "fall", "falls", "fell", "down", "underperform", "decline", "weak",
)
_RELATIVE_WORDS = (
    "상대 강세", "상대강세", "상대 우위", "상대우위", "상대 방어", "상대방어",
    "방어", "선방", "outperform", "relative strength", "relative defense",
    "우위",
)
_FUTURE_WORDS = (
    "오르면", "상승하면", "하락하면", "경우", "예상", "전망", "앞으로",
    "if ", "would", "could", "might", "expected", "forecast", "will ",
)
# 조건절과 관전 포인트는 오늘 세션에 대한 주장이 아니다.  "환율이 상승하면",
# "확대되는지 살핀다"를 오늘의 방향 주장으로 읽어 direction_mismatch가 났다.
# 단어 목록만으로는 한국어 조건 어미를 못 덮어서 어미 자체를 본다.
_CONDITIONAL_RE = re.compile(
    r"(?:되면|하면|지면|으면|다면|라면|는지|을지)(?![가-힣])"
    r"|다음\s*장|관전|살핀다|지켜본다|주목한다"
)
_HISTORICAL_WORDS = (
    "과거", "당시", "지난", "이전", "historical", "previously", "earlier",
)
_INTRADAY_WORDS = (
    "장중", "현재까지", "오전", "오후", "중간", "실시간", "intraday", "during the session",
)
_CURRENT_WORDS = (
    "현재", "오늘", "종가", "마감", "전일 대비", "기준", "as of", "close", "closing", "latest",
)
_METRIC_WORDS = (
    "매출", "매출액", "성장률", "성장", "점유율", "시장 점유", "영업이익", "순이익",
    "revenue", "revenue growth", "growth", "market share", "marketshare", "margin",
    "operating profit", "net income", "profit", "earnings",
)
_PRICE_WORDS = (
    "주가", "가격", "종가", "시세", "stock price", "share price", "price", "shares",
)

_ALIASES = {
    "KOSPI": ("KOSPI", "코스피"),
    "KOSDAQ": ("KOSDAQ", "코스닥"),
    "KOSPI200": ("KOSPI200", "코스피200", "KOSPI 200"),
    "NVDA": ("NVDA", "NVIDIA", "엔비디아"),
    "HYUNDAI": ("HYUNDAI", "현대차", "현대자동차", "005380"),
    "SPY": ("SPY",),
    "QQQ": ("QQQ",),
    "^GSPC": ("^GSPC", "S&P 500", "S&P500"),
    "^IXIC": ("^IXIC", "Nasdaq Composite", "나스닥 종합"),
    "^N225": ("^N225", "Nikkei 225", "니케이225"),
    "^STOXX50E": ("^STOXX50E", "EURO STOXX 50"),
}


class BriefingFinalizationError(ValueError):
    """Raised when a market candidate cannot safely be committed."""

    def __init__(self, message: str, *, validation: dict | None = None, candidate: dict | None = None):
        super().__init__(message)
        self.validation = validation or {}
        self.candidate = candidate


@dataclass(frozen=True)
class _Fact:
    key: str
    label: str
    aliases: tuple[str, ...]
    value: float | None = None
    change_pct: float | None = None
    date: str = ""
    unit: str = ""
    source: str = ""
    source_id: str = ""
    required: bool = False
    raw_value: Any = None


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _scope(candidate: dict) -> str:
    value = str(candidate.get("marketScope") or candidate.get("market") or "both").strip().lower()
    return {"korea": "kr", "kor": "kr", "us_market": "us", "usa": "us"}.get(value, value)


def _aliases(key: str, label: str = "") -> tuple[str, ...]:
    values = [key, label, *_ALIASES.get(key.upper(), ())]
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _unit(value: Any, default: str = "") -> str:
    text = str(value or "").strip().lower()
    if text in {"krw", "won", "원", "₩"}:
        return "krw"
    if text in {"usd", "dollar", "달러", "$"}:
        return "usd"
    if text in {"points", "point", "pt", "지수"}:
        return "points"
    if text in {"percent", "%", "pct"}:
        return "percent"
    return text or default


def _date(value: Any) -> str:
    return str(value or "")[:10]


def _fact_from_row(
    key: str,
    row: dict,
    *,
    source: str,
    required: bool = False,
    weekly: bool = False,
    default_date: str = "",
) -> _Fact | None:
    if not isinstance(row, dict):
        return None
    if str(row.get("status") or "").lower() in {"stale", "missing", "unavailable", "conflicting", "estimated"}:
        return None
    label = str(row.get("label") or key)
    value = row.get("last", row.get("close", row.get("value")))
    if weekly:
        change = row.get("weeklyPct", row.get("weeklyReturn"))
    else:
        change = row.get("oneDayPct", row.get("changePct"))
    if _finite(value) is None and _finite(change) is None:
        return None
    price_unit = _unit(row.get("priceUnit"), "points" if source == "koreaMarketData" else "")
    if price_unit == "quote":
        # Provider "quote" is a unit role, not a currency. USD/KRW is quoted
        # in won per dollar; a reader's 원 is not a contradiction.
        quote_currency = row.get("quoteCurrency") or ("KRW" if key.upper() in {"USDKRW", "USDKRW=X", "KRW=X"} else "")
        price_unit = _unit(quote_currency)
    return _Fact(
        key=str(key), label=label, aliases=_aliases(str(key), label),
        value=_finite(value), change_pct=_finite(change),
        date=_date(
            row.get("asOfDate")
            or row.get("asOf")
            or row.get("sessionDate")
            or row.get("date")
            or default_date
        ),
        unit=price_unit,
        source=source, source_id=str(row.get("sourceId") or ""),
        required=required, raw_value=value,
    )


def _facts(candidate: dict) -> list[_Fact]:
    result: list[_Fact] = []
    scope = _scope(candidate)
    weekly = str(candidate.get("kind") or "daily").lower() == "weekly"
    snapshot = candidate.get("marketSnapshot") or {}
    snapshot_date = _date(snapshot.get("asOfDate") or snapshot.get("asOf") or snapshot.get("date"))
    if scope not in {"kr", "korea"}:
        for key, row in (snapshot.get("tickers") or {}).items():
            fact = _fact_from_row(str(key), row, source="marketSnapshot", required=bool(row.get("required") if isinstance(row, dict) else False), weekly=weekly, default_date=snapshot_date)
            if fact:
                result.append(fact)

    korea = candidate.get("koreaMarketData") or {}
    korea_date = _date(korea.get("asOfDate") or korea.get("asOf") or korea.get("date"))
    if scope == "kr" or scope in {"both", "multi", ""}:
        for key, row in (korea.get("indices") or {}).items():
            required = (
                str(key).upper() in {"KOSPI", "KOSDAQ"}
                and _finite((row or {}).get("changePct", (row or {}).get("oneDayPct"))) is not None
            )
            fact = _fact_from_row(str(key), row, source="koreaMarketData", required=required and not weekly, weekly=weekly, default_date=korea_date)
            if fact:
                result.append(fact)

        for market, flows in (korea.get("investorFlows") or {}).items():
            if not isinstance(flows, dict):
                continue
            for role, raw in flows.items():
                if str(role).lower() not in {"foreign", "institution", "individual", "외국인", "기관", "개인"}:
                    continue
                if _flow_value(raw) is None:
                    continue
                label = f"{market} {role}"
                result.append(_Fact(
                    key=f"flow:{market}:{role}", label=label,
                    aliases=_aliases(str(role), label), value=_flow_value(raw),
                    unit="krw", source="koreaMarketData", date=korea_date,
                    required=(str(role).lower() in {"foreign", "institution", "외국인", "기관"}) and not weekly, raw_value=raw,
                ))
            for role, raw in flows.items():
                role_text = str(role).lower()
                if not any(token in role_text for token in ("reversal", "reverse", "전환", "반전")):
                    continue
                value = _reversal_value(raw)
                if value is None:
                    continue
                result.append(_Fact(
                    key=f"reversal:{market}:{role}",
                    label=f"{market} 수급 전환",
                    aliases=_aliases(str(role), f"{market} 수급 전환") + ("수급", "전환", "반전", "reversal", "거래일"),
                    value=value, unit="days", source="koreaMarketData", date=korea_date,
                    required=not weekly, raw_value=raw,
                ))

    for item in (candidate.get("marketTape") or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or item.get("id") or item.get("label") or "")
        if not symbol:
            continue
        item_market = str(item.get("market") or "").lower()
        if scope == "kr" and item_market in {"us", "usa"}:
            continue
        tape = candidate.get("marketTape") or {}
        tape_date = _date(tape.get("asOfDate") or tape.get("asOf") or tape.get("date"))
        fact = _fact_from_row(symbol, item, source="marketTape", required=bool(item.get("mandatory") or item.get("required")) and not weekly, weekly=weekly, default_date=tape_date)
        if fact:
            result.append(fact)

    if weekly:
        visual_rows = list(candidate.get("visualSnapshots") or [])
        visual_rows.extend((candidate.get("_validationVisuals") or {}).get("snapshots", {}).values())
        for visual in visual_rows:
            if not isinstance(visual, dict) or str(visual.get("market") or "").lower() != scope:
                continue
            for series in visual.get("series") or []:
                if not isinstance(series, dict) or series.get("proxyFor") or series.get("weeklyReturnReason"):
                    continue
                value = _finite(series.get("weeklyReturn"))
                if value is None:
                    continue
                key = str(series.get("ticker") or "")
                result.append(_Fact(key=key, label=str(series.get("label") or key), aliases=_aliases(key, str(series.get("label") or key)), change_pct=value, date=_date(series.get("weeklyEndDate")), source="weeklyVisual"))
    for row in _verified_web_rows(candidate):
        metric = row["metric"]
        value = _finite(str(row.get("value") or "").replace(",", "").replace("%", ""))
        if value is None or (weekly and metric != "weeklyPct") or (not weekly and metric == "weeklyPct"):
            continue
        symbol = row["instrument"]
        result.append(_Fact(key=symbol, label=symbol, aliases=_aliases(symbol),
            value=value if metric == "close" else None,
            change_pct=value if metric in {"oneDayPct", "changePct", "weeklyPct"} else None,
            date=row["sessionDate"], unit=_unit(row.get("unit")),
            source="verifiedWeb", source_id=row["sourceId"]))
    result.extend(_writer_facts(candidate, weekly=weekly))
    target = _target_session_date(candidate, scope)
    unique: dict[tuple[str, str, str], _Fact] = {}
    for fact in result:
        # A date-bearing fact from any source must describe the selected
        # session.  An excerpt without an explicit date is retained as an
        # unknown-quality writer input; it is never silently assigned the
        # report date here.
        if fact.source != "writerExcerpt" and not fact.date:
            # Structured price/flow data without an as-of date cannot be
            # safely compared to a session-scoped sentence.
            continue
        if fact.date and target and fact.date != target:
            if fact.source != "weeklyVisual":
                continue
            try:
                if not 0 <= (calendar_date.fromisoformat(target) - calendar_date.fromisoformat(fact.date)).days <= 6:
                    continue
            except ValueError:
                continue
        core_indices = {"us": {"^GSPC", "^IXIC"}, "kr": {"KOSPI", "KOSDAQ"}, "jp": {"^N225"}, "europe": {"^STOXX50E", "^GDAXI"}}
        if fact.key in core_indices.get(scope, set()) and fact.change_pct is not None:
            fact = replace(fact, required=True)
        unique[(fact.key, fact.source, fact.date)] = fact
    # An article publication date does not establish the session of every
    # percentage inside its excerpt. A same-session structured return owns
    # that instrument's current comparison; nearby article numbers must not
    # become competing mandatory closing returns. The structured value still
    # rejects a genuinely wrong claim in the report.
    structured_returns = {
        (fact.key.upper(), fact.date)
        for fact in unique.values()
        if fact.source != "writerExcerpt" and fact.change_pct is not None
    }
    return [
        fact for fact in unique.values()
        if not (
            fact.source == "writerExcerpt" and fact.change_pct is not None
            and (fact.label.upper(), fact.date) in structured_returns
        )
    ]


def _target_session_date(candidate: dict, scope: str) -> str:
    windows = candidate.get("marketWindows") or {}
    if str(candidate.get("kind") or "daily").lower() == "weekly":
        weekly_window = candidate.get("weeklyWindow") or {}
        return _date(
            candidate.get("weekEnd")
            or (windows.get("weekEnd") if isinstance(windows, dict) else "")
            or (weekly_window.get("weekEnd") if isinstance(weekly_window, dict) else "")
        )
    if scope == "us":
        snapshot = candidate.get("marketSnapshot") or {}
        return _date(
            windows.get("usRegularSessionDate")
            or candidate.get("sessionDate")
            or candidate.get("date")
            or snapshot.get("sessionDate")
            or snapshot.get("date")
            or snapshot.get("asOfDate")
            or snapshot.get("asOf")
        )
    if scope == "kr":
        korea = candidate.get("koreaMarketData") or {}
        return _date(
            windows.get("krCurrentSessionDate")
            or windows.get("krLatestCompletedSessionDate")
            or windows.get("krPreviousSessionDate")
            or candidate.get("sessionDate")
            or candidate.get("date")
            or korea.get("sessionDate")
            or korea.get("date")
            or korea.get("asOfDate")
            or korea.get("asOf")
        )
    sessions = windows.get("marketSessions") if isinstance(windows, dict) else {}
    session = (sessions or {}).get(scope) if isinstance(sessions, dict) else {}
    return _date((session or {}).get("sessionDate") or candidate.get("sessionDate") or candidate.get("date"))


def _writer_facts(candidate: dict, *, weekly: bool = False) -> list[_Fact]:
    """Extract only bounded facts from Q2's retained ``writerExcerpt``.

    Summary/title/content numbers are intentionally excluded.  Provider flow
    payloads are sometimes empty while the selected writer excerpt contains a
    clearly labelled KOSPI/KOSDAQ flow; those labels are safe to preserve as
    evidence, but no unrelated number is promoted into a required fact.
    """
    if weekly:
        return []
    result: list[_Fact] = []
    scope = _scope(candidate)
    for index, row in enumerate(_source_rows(candidate), 1):
        excerpt = str(row.get("writerExcerpt") or "").strip()
        if not excerpt:
            continue
        source_id = str(row.get("sourceId") or stable_source_id(row, index))
        if scope == "kr":
            writer_keys = {"KOSPI", "KOSDAQ"}
        elif scope == "us":
            writer_keys = {"SPY", "QQQ", "NVDA"}
        else:
            writer_keys = set(_ALIASES)
        aliases: dict[str, tuple[str, ...]] = {key: _aliases(key, key) for key in writer_keys}
        for company in row.get("companies") or []:
            if isinstance(company, dict):
                key = str(company.get("ticker") or company.get("name") or "").strip()
                label = str(company.get("name") or key).strip()
                if key:
                    aliases[key] = _aliases(key, label)
        excerpt_lines = excerpt.splitlines() or [excerpt]
        row_date = _date(row.get("asOfDate") or row.get("sessionDate") or row.get("date") or row.get("publishedAt"))
        for line in excerpt_lines:
            flags = _line_flags(line, _Fact(key="writer", label="writer", aliases=(), date=row_date))
            if flags["historical"] or flags["intraday"] or flags["future"]:
                continue
            for key, key_aliases in aliases.items():
                positions = _alias_positions(line, key_aliases)
                if not positions:
                    continue
                percentages = _line_percentages(line)
                spans = _alias_spans(line, key_aliases)
                percentages = [
                    item for item in percentages
                    if not _metric_percent_context(line, item[2])
                    and any(
                        0 <= item[2] - end <= 48
                        and not re.search(r"[;|!?]|\.(?!\d)", line[end:item[2]])
                        and not any(
                            end <= other < item[2]
                            for other_key, other_aliases in aliases.items() if other_key != key
                            for other in _alias_positions(line, other_aliases)
                        )
                        for _start, end in spans
                    )
                ]
                if percentages:
                    item = min(percentages, key=lambda value: min(abs(value[2] - position) for position in positions))
                    line_date = _date(_DATE_RE.search(line).group(0)) if _DATE_RE.search(line) else row_date
                    result.append(_Fact(
                        key=f"writer:{source_id}:{key}", label=key,
                        aliases=key_aliases, change_pct=item[0], date=line_date,
                        source="writerExcerpt", source_id=source_id,
                        required=(scope in {"kr", "both", "multi", ""} and str(key).upper() in {"KOSPI", "KOSDAQ"}),
                    ))
        if scope not in {"kr", "both", "multi", ""}:
            continue
        for role, role_aliases in (("foreign", ("외국인", "foreign")), ("institution", ("기관", "institution"))):
            role_match = None
            for line in excerpt_lines:
                flags = _line_flags(line, _Fact(key="writer", label="writer", aliases=(), date=row_date))
                if flags["historical"] or flags["intraday"] or flags["future"]:
                    continue
                role_match = re.search(
                    rf"(?:(?:{'|'.join(map(re.escape, role_aliases))})[^\n,:;]{{0,24}}?(?P<value>[+-]?\s*(?:\d+(?:,\d+)?\s*조\s*)?\d+(?:,\d+)?\s*억\s*원))",
                    line,
                    re.IGNORECASE,
                )
                if role_match:
                    break
            if role_match:
                raw = role_match.group("value")
                value = _flow_value(raw)
                if value is not None:
                    suffix = re.split(r",|;|외국인|기관|foreign|institution", line[role_match.end():], maxsplit=1, flags=re.IGNORECASE)[0]
                    if re.search(r"순매도|net\s+sell", role_match.group(0) + suffix, re.IGNORECASE):
                        value = -abs(value)
                        raw = "-" + raw.lstrip("+- ")
                    result.append(_Fact(
                        key=f"writer:{source_id}:flow:{role}", label=role_aliases[0],
                        aliases=role_aliases, value=value, unit="krw",
                        source="writerExcerpt", source_id=source_id, date=row_date,
                        required=True, raw_value=raw,
                    ))
        reversal = re.search(r"(?P<value>\d+)\s*(?:거래일|일|day|days)[^\n]{0,20}(?:전환|반전|reversal)", excerpt, re.IGNORECASE)
        if reversal:
            result.append(_Fact(
                key=f"writer:{source_id}:reversal", label="수급 전환",
                aliases=("수급", "전환", "반전", "reversal", "거래일"),
                value=float(reversal.group("value")), unit="days", source="writerExcerpt",
                source_id=source_id, date=row_date, required=True, raw_value=reversal.group(0),
            ))
    return result


def _flow_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return _finite(value)
    text = str(value or "").replace(",", "").strip()
    if not text:
        return None
    match = _FLOW_RE.fullmatch(text)
    if match:
        sign = -1 if match.group("sign") == "-" else 1
        trillion = float(match.group("trillion") or 0) * 1_000_000_000_000
        eok = float(match.group("eok")) * 100_000_000
        return sign * (trillion + eok)
    return _finite(text)


def _reversal_value(value: Any) -> float | None:
    """Extract a day count from a structured reversal marker."""
    if isinstance(value, (int, float)):
        return _finite(value)
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:거래일|일|day|days)?", str(value or ""), re.IGNORECASE)
    return _finite(match.group(1)) if match else None


def _flow_display(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    number = _finite(value)
    if number is None:
        return "확인 안 됨"
    sign = "-" if number < 0 else ""
    number = abs(number)
    if number >= 1_000_000_000_000:
        trillion = int(number // 1_000_000_000_000)
        remainder = int(round((number - trillion * 1_000_000_000_000) / 100_000_000))
        return f"{sign}{trillion}조{remainder:04d}억원" if remainder else f"{sign}{trillion}조원"
    if number >= 100_000_000:
        return f"{sign}{int(round(number / 100_000_000))}억원"
    return f"{sign}{int(round(number)):,}원"


def _num(value: str) -> float | None:
    try:
        return float(value.replace(",", "").replace(" ", ""))
    except (TypeError, ValueError):
        return None


def _decimals(raw: str) -> int:
    text = raw.replace(" ", "").replace(",", "")
    return len(text.split(".", 1)[1]) if "." in text else 0


def _comparable_unit(written: str, expected: str) -> bool:
    """Whether a written number is the same kind of quantity as the fact.

    다른 단위로 적힌 숫자는 이 지표의 값을 틀리게 적은 것이 아니라 다른 대상의
    값이다 — "WTI 90달러선, 원·달러 환율"의 90이 환율 오기로 읽혀 거절이 났다.
    단위를 모르는 사실(예전 marketTape 행)에는 단위 없는 지수 레벨만 견준다.
    값이 맞는데 통화만 다른 경우는 unit_mismatch가 그대로 잡는다.
    """
    if written and expected:
        return _unit(written) == _unit(expected)
    if written:
        return False
    return _unit(expected) in {"points", "usd"}


def _explicit_sign(raw: str) -> bool:
    """Did the writer spell the direction into the number itself?"""
    return raw.strip().startswith(("+", "-"))


def _percent_agrees(actual: float, raw: str, expected: float, tolerance: float) -> bool:
    """Compare a written percentage against the measured change.

    본문은 "1.71% 하락"처럼 부호 없이 크기만 적는다.  그 크기를 부호 있는
    실측치에서 그대로 빼면 |1.71 - (-1.71)| = 3.42가 나와, 사실이 맞는 문장이
    전부 value_mismatch가 됐다.  부호를 직접 적은 경우에만 부호까지 대조하고,
    아니면 크기끼리 비교한다.  방향은 아래 direction 검사가 따로 본다.
    """
    if _explicit_sign(raw):
        return abs(actual - expected) <= tolerance
    return abs(abs(actual) - abs(expected)) <= tolerance


def _line_flags(line: str, fact: _Fact) -> dict[str, bool]:
    low = line.lower()
    dates = [f"{y}-{int(m):02d}-{int(d):02d}" for y, m, d in _DATE_RE.findall(line)]
    historical = any(word in low for word in _HISTORICAL_WORDS)
    intraday = any(word in low for word in _INTRADAY_WORDS)
    future = any(word in low for word in _FUTURE_WORDS)
    # A dated sentence such as ``2026-08-30 종가`` is historical even though
    # it contains the generic word "close". Explicit current anchors keep a
    # mismatched date blocking (``현재 종가 ... 2026-08-30``).
    explicit_current = ("현재", "오늘", "latest", "as of", "전일 대비", "기준일", "this session")
    if dates and fact.date and any(value != fact.date for value in dates) and not any(word in low for word in explicit_current):
        historical = True
    return {
        "historical": historical,
        "intraday": intraday,
        "future": future,
        "current": any(word in low for word in _CURRENT_WORDS),
    }


def _alias_spans(line: str, aliases: tuple[str, ...] | list[str]) -> list[tuple[int, int]]:
    """Return whole-token alias spans, never substring matches.

    Market symbols are short enough that substring matching creates dangerous
    collisions (``KOSPI`` in ``KOSPI200`` and ``SPY`` in ``SPYword``).  The
    ASCII-word boundaries keep ``KOSPI`` out of ``KOSPI200`` and allow normal
    Korean particles after Latin tickers (``NVDA는``).
    """
    text = str(line or "")
    spans: list[tuple[int, int]] = []
    for alias in aliases or ():
        value = str(alias or "").strip()
        if not value:
            continue
        pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(value)}(?![A-Za-z0-9_])", re.IGNORECASE)
        spans.extend(match.span() for match in pattern.finditer(text))
    return sorted(set(spans))


def _alias_positions(line: str, aliases: tuple[str, ...] | list[str]) -> list[int]:
    return sorted({start for start, _end in _alias_spans(line, aliases)})


def _metric_percent_context(line: str, position: int) -> bool:
    """Whether a percent belongs to an operating metric, not price return."""
    text = str(line or "").lower()
    # Keep the clause local so an earlier ``매출 20%`` cannot reclassify a
    # later ``주가 +1.48%``.  ``share`` alone is deliberately excluded:
    # ``NVDA shares rose 1.48%`` describes price performance, while
    # ``market share rose 1.48%`` is an operating metric.
    point = int(position)
    before = text[max(0, point - 64):point]
    after = text[point:min(len(text), point + 16)]
    before_clause = re.split(r"[,;:/|]", before)[-1]
    after_clause = re.split(r"[,;:/|]", after)[0]
    clause = f"{before_clause} {after_clause}"
    metric_present = any(token in clause for token in _METRIC_WORDS)
    price_present = any(token in clause for token in _PRICE_WORDS)
    return metric_present and not price_present


def _contains_alias(line: str, fact: _Fact) -> bool:
    return bool(_alias_positions(line, fact.aliases))


def _line_percentages(line: str) -> list[tuple[float, str, int]]:
    return [(value, raw, match.start()) for match in _PERCENT_RE.finditer(line) if (value := _num(match.group(1))) is not None for raw in [match.group(1)]]


def _line_values(line: str) -> list[tuple[float, str, str, int]]:
    values: list[tuple[float, str, str, int]] = []
    consumed: list[tuple[int, int]] = []
    date_spans = [match.span() for match in _DATE_RE.finditer(line)]
    for match in _FLOW_RE.finditer(line):
        value = _flow_value(match.group(0))
        if value is not None:
            values.append((value, match.group(0), "krw", match.start()))
            consumed.append(match.span())
    for match in _NUMBER_RE.finditer(line):
        if any(start <= match.start() < end for start, end in (*consumed, *date_spans)):
            continue
        # Dates, heading numbers and percentages are not prices/flows.
        if _DATE_RE.search(line[max(0, match.start() - 5):match.end() + 5]):
            continue
        if match.end() < len(line) and line[match.end():].lstrip().startswith("%"):
            continue
        value = _num(match.group(1))
        if value is None:
            continue
        tail = line[match.end():match.end() + 12].lower()
        # Calendar components and explicitly labelled point changes are not
        # absolute prices. Keep the following close eligible for comparison.
        if re.match(r"\s*(?:일|월|년|시|분)(?![가-힣])", tail):
            continue
        unit_match = _CHANGE_UNIT_RE.match(tail)
        if unit_match and (
            _CHANGE_CONTEXT_RE.search(line[max(0, match.start() - 20):match.start()])
            or _CHANGE_MOVE_RE.match(tail[unit_match.end():])
        ):
            continue
        if _THRESHOLD_RE.match(tail[unit_match.end():] if unit_match else tail):
            continue
        # 단위는 숫자 바로 뒤 토큰이다.  12자 앞을 통째로 훑던 탓에 "WTI 90달러선,
        # 원·달러 환율"의 90이 뒤따르는 '원'을 보고 원화로 분류됐다.
        unit = ""
        unit_match = _UNIT_RE.match(tail)
        if unit_match:
            token = unit_match.group(1)
            if token in {"원", "krw", "₩"}:
                unit = "krw"
            elif token in {"달러", "usd", "$"}:
                unit = "usd"
            else:
                unit = "points"
        values.append((value, match.group(1), unit, match.start()))
    return values


def _verified_web_rows(candidate: dict) -> list[dict]:
    scope = _scope(candidate)
    lookup = candidate.get("webLookup") or {}
    if isinstance(lookup.get(scope), dict):
        lookup = lookup[scope]
    return [row for row in lookup.get("facts", []) if isinstance(row, dict)
        and row.get("verified") is True and row.get("market") == scope
        and row.get("evidenceMethod") in {"public_quote_exact", "structured_provider"}
        and row.get("instrument") and row.get("metric") and row.get("sessionDate") and row.get("sourceId")
        and re.fullmatch(r"[0-9a-f]{64}", str(row.get("sourceEvidenceHash") or ""))]


def _source_rows(candidate: dict) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def add(value: Any) -> None:
        if not isinstance(value, dict):
            return
        marker = (str(value.get("sourceId") or ""), str(value.get("url") or ""), str(value.get("title") or ""))
        if marker in seen:
            return
        seen.add(marker)
        rows.append(value)

    for field in ("sources", "sourceLedger"):
        for row in candidate.get(field) or []:
            add(row)
    for row in _verified_web_rows(candidate):
        add({**row, "writerExcerpt": row.get("quote", ""), "title": row["instrument"]})
    for section in (candidate.get("briefings") or {}).values():
        if isinstance(section, dict):
            for row in section.get("sources") or []:
                add(row)
    return rows


def _evidence_text(row: dict) -> str:
    return " ".join(
        str(row.get(key) or "") for key in ("writerExcerpt", "excerpt", "summary", "content", "title")
    ).strip()


_REFERENCE_SECTION_WORDS = (
    "참고자료", "참고 자료", "source & data", "source and data", "sources", "references",
)
_SECTION_ID_LABELS = {
    # These are the stable IDs used by the briefing manifest contract; they
    # are admitted only when the corresponding reader heading is present.
    "market-flow": ("시장 흐름", "market flow"),
    "core-driver": ("핵심 변수", "core driver"),
    "leading-company": ("주도한 기업", "leading compan"),
    "investor-view": ("일반 투자자 관점", "investor view"),
    "checkpoint": ("체크포인트", "checkpoint"),
    "conclusion": ("오늘의 결론", "conclusion"),
}


def _body_records(markdown: str) -> list[tuple[int, int, str]]:
    """Reader sentences with original offsets, excluding reference numerics."""
    records: list[tuple[int, int, str]] = []
    in_references = False
    in_manifest = False
    offset = 0
    for raw in str(markdown or "").splitlines(keepends=True):
        begin = offset
        offset += len(raw)
        line = raw.rstrip("\r\n")
        if MANIFEST_START in line:
            in_manifest = True
        if in_manifest:
            if MANIFEST_END in line:
                in_manifest = False
            continue
        if line.lstrip().startswith("#"):
            low = line.lower()
            in_references = any(marker in low for marker in _REFERENCE_SECTION_WORDS)
            if in_references:
                continue
        if not in_references:
            start = 0
            structured = line.lstrip().startswith("#") or (line.strip().startswith("|") and line.strip().endswith("|"))
            breaks = [] if structured else list(re.finditer(r"(?<=[.!?。！？])[ \t]+", line))
            for match in breaks:
                records.append((begin + start, begin + match.start(), line[start:match.start()]))
                start = match.end()
            records.append((begin + start, begin + len(line), line[start:]))
    return records


def _body_lines(markdown: str) -> list[str]:
    return [line for _begin, _end, line in _body_records(markdown)]


def _body_text(markdown: str) -> str:
    return "\n".join(_body_lines(markdown))


def _normalized_phrase(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _phrase_in_text(phrase: Any, text: Any) -> bool:
    needle = _normalized_phrase(phrase)
    haystack = _normalized_phrase(text)
    if not needle or not haystack:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack, re.IGNORECASE))


def _section_whitelist(candidate: dict, markdown: str) -> set[str]:
    """Build the final-body section allowlist used by claim declarations."""
    sections: set[str] = set()
    in_references = False
    for line in str(markdown or "").splitlines():
        if line.lstrip().startswith("#"):
            heading = re.sub(r"^\s*#+\s*", "", line).strip()
            in_references = any(marker in heading.lower() for marker in _REFERENCE_SECTION_WORDS)
            if in_references:
                continue
            if heading:
                sections.add(_normalized_phrase(heading))
                sections.add(_normalized_phrase(line.strip()))
                section_number = re.match(r"^(\d+(?:\.\d+)?)\b", heading)
                if section_number:
                    sections.add(_normalized_phrase(section_number.group(1)))
                heading_low = heading.lower()
                for section_id, labels in _SECTION_ID_LABELS.items():
                    if any(label in heading_low for label in labels):
                        sections.add(section_id)
        elif in_references:
            continue
    return {value for value in sections if value}


def _semantic_source_check(candidate: dict) -> tuple[dict, list[dict]]:
    rows = _source_rows(candidate)
    by_id = {str(row.get("sourceId") or stable_source_id(row, index)): row for index, row in enumerate(rows, 1)}
    body = _body_text(str(candidate.get("markdown") or ""))
    section_whitelist = _section_whitelist(candidate, str(candidate.get("markdown") or ""))
    invalid: list[dict] = []
    safe_count = 0
    for row in rows:
        raw = str(row.get("url") or "").strip()
        if raw and not normalize_source_url(raw):
            invalid.append({"kind": "unsafe_url"})
        elif raw:
            safe_count += 1
    ledger = candidate.get("claimLedger") or {}
    declared = []
    if isinstance(ledger, dict):
        declared = list(ledger.get("claims") or [])
        by_market = ledger.get("byMarket") or {}
        for nested in by_market.values():
            if isinstance(nested, dict):
                declared.extend(nested.get("claims") or [])
    verified_declared = 0
    unsupported_declared = 0
    for claim in declared:
        if not isinstance(claim, dict):
            continue
        ids = claim.get("supportingSourceIds") or claim.get("sourceIds") or claim.get("sources") or []
        ids = [str(value) for value in ids if str(value).strip()]
        outside = [value for value in ids if value not in by_id]
        if outside:
            invalid.append({"kind": "source_outside_whitelist", "count": len(outside)})
            continue
        claim_raw = str(claim.get("claim") or claim.get("text") or claim.get("statement") or "").strip()
        evidence = " ".join(_evidence_text(by_id[value]) for value in ids if value in by_id)
        # A declared section is itself a whitelist reference.  It must be an
        # actual final-body heading (or an explicit allowlisted section ID),
        # never an arbitrary model-created section name.
        section_values: list[str] = []
        for field in ("section", "sectionId", "sourceSection", "supportingSection", "supportingSectionId"):
            value = claim.get(field)
            if isinstance(value, (list, tuple, set)):
                section_values.extend(str(item) for item in value if str(item).strip())
            elif str(value or "").strip():
                section_values.append(str(value))
        for field in ("sections", "sectionIds", "supportingSections", "supportingSectionIds"):
            value = claim.get(field)
            if isinstance(value, (list, tuple, set)):
                section_values.extend(str(item) for item in value if str(item).strip())
            elif str(value or "").strip():
                section_values.append(str(value))
        for section in section_values:
            normalized = _normalized_phrase(section)
            if normalized not in section_whitelist:
                invalid.append({"kind": "section_outside_whitelist"})
        # A declaration is not semantic verification.  Only an exact quoted
        # excerpt can independently verify a declaration here; ordinary token
        # overlap (``Nvidia rose`` vs ``Nvidia fell``) is intentionally unknown.
        quotation = re.fullmatch(r"\s*(?:\"([^\"]+)\"|“([^”]+)”|'([^']+)')\s*[.!?]?\s*", claim_raw)
        quoted = next((part for part in (quotation.groups() if quotation else ()) if part), "") if quotation else ""
        body_phrase = quoted or claim_raw
        body_has_claim = bool(body_phrase and _phrase_in_text(body_phrase, body))
        if quoted and body_has_claim and _phrase_in_text(quoted, evidence):
            verified_declared += 1
        elif claim_raw:
            unsupported_declared += 1
    links = markdown_external_links(str(candidate.get("markdown") or ""))
    allowed_urls = {normalize_source_url(row.get("url")) for row in rows if normalize_source_url(row.get("url"))}
    for link in links:
        url = normalize_source_url(link.get("url"))
        if not url:
            invalid.append({"kind": "unsafe_url"})
        elif url not in allowed_urls and not any(normalize_source_url(row.get("url")) == url for row in rows):
            # Existing source_integrity normally adds visible links to the
            # ledger.  Keep this as an unknown/diagnostic condition rather
            # than inventing a trusted source.
            invalid.append({"kind": "visible_link_outside_whitelist"})
    evidence_meta = candidate.get("generationEvidence") or {}
    manifest_status = str(evidence_meta.get("status") or "unknown")
    return {
        "status": "review" if invalid or unsupported_declared or manifest_status != "declared" else "pass",
        "manifestStatus": manifest_status,
        "whitelistCount": len(by_id),
        "safeUrlCount": safe_count,
        "declaredClaimCount": len(declared),
        "semanticVerifiedClaimCount": verified_declared,
        "unverifiedDeclarationCount": unsupported_declared,
        "errors": sorted({str(row.get("kind") or "unknown") for row in invalid}),
    }, invalid


def _production_source_check(candidate: dict) -> tuple[dict, list[dict]]:
    """Check only source/rendering safety needed before a production write.

    This deliberately does not compare claim text with excerpts.  The
    semantic checker above remains available through ``validate_briefing_candidate``
    for explicit offline evaluation, but production generation must not turn
    that judgment into a prose edit, rejection, or fallback.
    """
    rows = _source_rows(candidate)
    by_id = {
        str(row.get("sourceId") or stable_source_id(row, index)): row
        for index, row in enumerate(rows, 1)
    }
    invalid: list[dict] = []
    safe_count = 0
    for row in rows:
        raw = str(row.get("url") or "").strip()
        if raw and not normalize_source_url(raw):
            invalid.append({"kind": "unsafe_url"})
        elif raw:
            safe_count += 1

    section_whitelist = _section_whitelist(candidate, str(candidate.get("markdown") or ""))
    ledgers = [candidate.get("claimLedger") or {}]
    for section in (candidate.get("briefings") or {}).values():
        if isinstance(section, dict):
            ledgers.append(section.get("claimLedger") or {})
    declared_count = 0
    for ledger in ledgers:
        if not isinstance(ledger, dict):
            continue
        claims = list(ledger.get("claims") or [])
        by_market = ledger.get("byMarket") or {}
        for nested in by_market.values():
            if isinstance(nested, dict):
                claims.extend(nested.get("claims") or [])
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            declared_count += 1
            ids = claim.get("supportingSourceIds") or claim.get("sourceIds") or claim.get("sources") or []
            id_values = list(ids) if isinstance(ids, (list, tuple, set)) else ([ids] if ids else [])
            for value in id_values:
                if str(value).strip() and str(value) not in by_id:
                    invalid.append({"kind": "source_outside_whitelist"})
            section_values: list[str] = []
            for field in (
                "section", "sectionId", "sourceSection", "supportingSection",
                "supportingSectionId", "sections", "sectionIds",
                "supportingSections", "supportingSectionIds",
            ):
                value = claim.get(field)
                if isinstance(value, (list, tuple, set)):
                    section_values.extend(str(item) for item in value if str(item).strip())
                elif str(value or "").strip():
                    section_values.append(str(value))
            for value in section_values:
                if _normalized_phrase(value) not in section_whitelist:
                    invalid.append({"kind": "section_outside_whitelist"})

    links = markdown_external_links(str(candidate.get("markdown") or ""))
    allowed_urls = {
        normalize_source_url(row.get("url"))
        for row in rows
        if normalize_source_url(row.get("url"))
    }
    for link in links:
        url = normalize_source_url(link.get("url"))
        if not url:
            invalid.append({"kind": "unsafe_url"})
        elif url not in allowed_urls:
            invalid.append({"kind": "visible_link_outside_whitelist"})

    errors = sorted({str(row.get("kind") or "unknown") for row in invalid})
    return {
        "status": "review" if errors else "pass",
        "assessmentStatus": "not_assessed",
        "manifestStatus": str((candidate.get("generationEvidence") or {}).get("status") or "unknown"),
        "whitelistCount": len(by_id),
        "safeUrlCount": safe_count,
        "declaredClaimCount": declared_count,
        "semanticVerifiedClaimCount": None,
        "unverifiedDeclarationCount": None,
        "errors": errors,
    }, invalid


def _facts_for_line(line: str, facts: list[_Fact]) -> list[_Fact]:
    return [fact for fact in facts if _contains_alias(line, fact)]


def _owned(line: str, fact: _Fact, line_facts: list[_Fact], candidates: list, offset: int) -> list:
    """Drop numbers that belong to another named subject on the same line.

    가까운 숫자 하나를 무조건 이 지표의 주장으로 읽어, "LQD가 각각 0.13%,
    0.14% 상승했다 … QQQ, IWM, RSP가 모두 하락권"의 0.14가 IWM 수치로,
    "WTI는 최근 5거래일 9.90%"의 9.90이 IWM 수치로 잡혔다.  방향 단어와 같은
    규칙을 쓴다 — 그 숫자가 선 절의 주어가 이 지표이고, 이 지표의 별칭이 그
    숫자에 가장 가까운 주어일 때만 이 지표의 주장이다.
    """
    positions = _alias_positions(line, fact.aliases)
    if not positions or not candidates:
        return candidates
    others = [other for other in line_facts if other.key.upper() != fact.key.upper()]
    rivals = [
        position for other in others for position in _alias_positions(line, other.aliases)
    ]
    # 주어를 부르지 않는 절은 앞 절의 주어를 이어받는다 — "NVDA 매출 성장률 20%,
    # 주가는 +1.48% 상승했다"의 +1.48%는 NVDA 것이다.  이어받을 앞 절이 없으면
    # 그 숫자의 주어는 이 지표가 아니다 — "삼성전자는 0.20% 하락했지만, 코스피는
    # 상승 마감했다"의 0.20%를 코스피 수치로 읽어 거절이 났다.
    carried: list[tuple[int, int, bool | None]] = []
    owner: bool | None = None
    for begin, end in _clause_spans(line):
        clause = line[begin:end]
        if _alias_positions(clause, fact.aliases):
            owner = True
        elif any(_alias_positions(clause, other.aliases) for other in others):
            owner = False
        # 시가를 말하는 절은 이 지표의 것이어도 종가 주장이 아니다.  절 단위로
        # 끊어야 같은 문장 뒤쪽의 종가는 계속 검증된다.
        carried.append((begin, end, owner and not _OPEN_CLAUSE_RE.search(clause)))
    kept = []
    for item in candidates:
        point = item[offset]
        if not any(begin <= point < end and owner for begin, end, owner in carried):
            continue
        own = min(abs(point - position) for position in positions)
        if rivals and own > min(abs(point - position) for position in rivals):
            continue
        kept.append(item)
    return kept


def _near_percent(line: str, fact: _Fact, line_facts: list[_Fact] = ()) -> list[tuple[float, str, int]]:
    positions = _alias_positions(line, fact.aliases)
    if not positions:
        return []
    candidates = _owned(line, fact, list(line_facts), [
        item for item in _line_percentages(line)
        if not _metric_percent_context(line, item[2])
        and min(abs(item[2] - pos) for pos in positions) <= 180
    ], 2)
    if not candidates:
        return []
    return [min(candidates, key=lambda item: min(abs(item[2] - pos) for pos in positions))]


def _clause_spans(line: str) -> list[tuple[int, int]]:
    """Split a line into clauses so a direction word claims only its own subject."""
    spans: list[tuple[int, int]] = []
    start = 0
    breaks = [match.span() for match in _CLAUSE_BREAK_RE.finditer(line)]
    # Keep the opening marker on the left. The following close inherits the
    # same subject but must not inherit the opening-only exclusion.
    breaks.extend((match.end(), match.end()) for match in _OPEN_TRANSITION_RE.finditer(line))
    for begin, end in sorted(set(breaks)):
        spans.append((start, begin))
        start = end
    spans.append((start, len(line)))
    return [(begin, end) for begin, end in spans if begin < end]


def _direction_words(line: str, fact: _Fact, line_facts: list[_Fact]) -> tuple[bool, bool]:
    """Return the positive/negative direction words this fact actually owns.

    한 문장에 주어가 여럿 들어간다.  줄 전체를 이 사실 하나의 주장으로 읽으면
    "삼성전자는 0.20% 하락했지만 … 코스피의 막판 회복"의 '하락'이 코스피 것이
    되고, "코스피 종가는 버텼지만 코스닥 약세"의 '약세'도 코스피 것이 된다 —
    둘 다 사실이 맞는 문장인데 direction_mismatch로 거절돼 CLI 브리핑이 규칙
    대체로 떨어졌다.  같은 절 안에서 이 사실의 별칭이 가장 가까운 주어일 때만
    그 방향 단어를 이 사실의 주장으로 읽는다.
    """
    rivals = [other for other in line_facts if other.key.upper() != fact.key.upper()]
    # 같은 절이어도 멀리 떨어진 단어는 다른 주어의 것이다 — "장기금리 상승은 …
    # 코스닥과 고평가 종목에 불리하게 작용했다"의 '상승'은 장기금리 것이고,
    # 장기금리는 추적 대상이 아니라 경쟁 별칭으로도 걸러지지 않는다.
    window = 30
    positive = negative = False
    for begin, end in _clause_spans(line):
        clause = line[begin:end]
        positions = _alias_positions(clause, fact.aliases)
        if not positions or _CONDITIONAL_RE.search(clause):
            continue
        rival_positions = [
            position
            for other in rivals
            for position in _alias_positions(clause, other.aliases)
        ]
        low = clause.lower()
        for words in (_POSITIVE_WORDS, _NEGATIVE_WORDS):
            for word in words:
                index = low.find(word)
                while index >= 0:
                    own = min(abs(index - position) for position in positions)
                    if own <= window and (
                        not rival_positions
                        or own <= min(abs(index - position) for position in rival_positions)
                    ):
                        if words is _POSITIVE_WORDS:
                            positive = True
                        else:
                            negative = True
                    index = low.find(word, index + 1)
    return positive, negative


def _directional_percent(line: str, fact: _Fact, line_facts: list[_Fact] = ()) -> float | None:
    """Return the signed change this line claims for the fact.

    부호 없는 크기는 방향을 말해 주지 않는다.  그것을 방향 판정에 그대로 쓰면
    "1.71% 하락"이 +1.71로 읽혀 direction_mismatch가 된다.  본문이 부호를 적은
    경우에만 본문 값을 쓰고, 아니면 방향은 실측치가 갖는다.
    """
    pct = _near_percent(line, fact, line_facts)
    if pct and _explicit_sign(pct[0][1]):
        return pct[0][0]
    return fact.change_pct


def _near_values(line: str, fact: _Fact, line_facts: list[_Fact] = ()) -> list[tuple[float, str, str, int]]:
    positions = _alias_positions(line, fact.aliases)
    if not positions:
        return []
    alias_spans = _alias_spans(line, fact.aliases)
    candidates = _owned(line, fact, list(line_facts), [
        item for item in _line_values(line)
        if min(abs(item[3] - pos) for pos in positions) <= 180
        and not any(start <= item[3] < end for start, end in alias_spans)
    ], 3)
    if not candidates:
        return []
    return [min(candidates, key=lambda item: min(abs(item[3] - pos) for pos in positions))]


def _same_fact(existing: list[dict], key: str, value: Any) -> bool:
    return any(row.get("factKey") == key and row.get("value") == value for row in existing)


def _evaluate(candidate: dict) -> dict:
    markdown = str(candidate.get("markdown") or "")
    facts = _facts(candidate)
    source_check, source_errors = _semantic_source_check(candidate)
    verified: list[dict] = []
    unknown: list[dict] = []
    contradictions: list[dict] = []
    missing: list[_Fact] = []
    # References can contain source titles, dates, prices, and URLs.  They are
    # whitelist material, not reader claims, so never let their numbers satisfy
    # a market fact.
    records = [record for record in _body_records(markdown) if record[2].strip()]

    for fact in facts:
        seen = False
        for begin, end, line in records:
            location = {"bodyStart": begin, "bodyEnd": end}
            if line.lstrip().startswith("#") or not _contains_alias(line, fact):
                continue
            if fact.key.upper() in {"KOSPI", "KOSDAQ", "KOSPI200"} and any(
                marker in line.lower() for marker in (
                    "foreign", "institution", "individual", "외국인", "기관", "개인",
                    "수급", "전환", "반전", "reversal",
                )
            ):
                continue
            flags = _line_flags(line, fact)
            if flags["historical"] or flags["intraday"] or flags["future"]:
                continue
            line_facts = _facts_for_line(line, facts)
            percentages = _near_percent(line, fact, line_facts)
            values = _near_values(line, fact, line_facts)
            if fact.change_pct is not None and percentages:
                seen = True
                for actual, raw, _position in percentages:
                    tolerance = 0.5 * (10 ** (-_decimals(raw))) + 1e-9
                    if _percent_agrees(actual, raw, fact.change_pct, tolerance):
                        verified.append({"factKey": fact.key, "kind": "changePct", "value": actual, "expected": fact.change_pct, "precision": _decimals(raw), "source": fact.source})
                    else:
                        contradictions.append({"kind": "value_mismatch", "factKey": fact.key, "claim": actual, "expected": fact.change_pct, "unit": "percent", "date": fact.date, **location})
            if fact.value is not None and values:
                # For flow values the formatter carries the unit and scales
                # 5034억원/1조6690억원 back to won before comparison.
                for actual, raw, unit, _position in values:
                    if abs(actual - fact.value) <= max(0.5 * (10 ** (-_decimals(raw))), 1e-9):
                        if fact.unit and unit and _unit(unit) != _unit(fact.unit):
                            contradictions.append({"kind": "unit_mismatch", "factKey": fact.key, "claim": raw, "expectedUnit": fact.unit, "actualUnit": unit, **location})
                        else:
                            seen = True
                            verified.append({"factKey": fact.key, "kind": "value", "value": actual, "expected": fact.value, "precision": _decimals(raw), "source": fact.source})
                    elif _comparable_unit(unit, fact.unit):
                        contradictions.append({"kind": "value_mismatch", "factKey": fact.key, "claim": actual, "expected": fact.value, "unit": unit or fact.unit, "date": fact.date, **location})
            dates = [f"{y}-{int(m):02d}-{int(d):02d}" for y, m, d in _DATE_RE.findall(line)]
            if dates and fact.date and any(value != fact.date for value in dates) and any(word in line.lower() for word in _CURRENT_WORDS):
                contradictions.append({"kind": "date_mismatch", "factKey": fact.key, "claimDate": dates[0], "expectedDate": fact.date, **location})
        if fact.required and not seen:
            missing.append(fact)
        elif not seen and (fact.value is not None or fact.change_pct is not None):
            unknown.append({"factKey": fact.key, "reason": "not_present_or_context_not_current"})

    # Direction and relative-strength checks use the same current line only.
    # They never infer a claim from a naked number in a URL/date/source row.
    for begin, end, line in records:
        location = {"bodyStart": begin, "bodyEnd": end}
        if line.lstrip().startswith("#"):
            continue
        line_facts = _facts_for_line(line, facts)
        if not line_facts:
            continue
        flags = _line_flags(line, line_facts[0])
        if flags["historical"] or flags["intraday"] or flags["future"]:
            continue
        low = line.lower()
        relative = any(word in low for word in _RELATIVE_WORDS)
        for fact in line_facts:
            current_pct = _directional_percent(line, fact, line_facts)
            if current_pct is None:
                continue
            # A relative/defensive statement is not an absolute direction
            # claim.  Without a known benchmark it remains unknown rather
            # than turning a negative return into a false contradiction.
            positive, negative = _direction_words(line, fact, line_facts)
            if not relative and positive and current_pct < 0 and not negative:
                contradictions.append({"kind": "direction_mismatch", "factKey": fact.key, "claim": "positive_direction", "expectedChangePct": fact.change_pct, **location})
            if not relative and negative and current_pct > 0 and not positive:
                contradictions.append({"kind": "direction_mismatch", "factKey": fact.key, "claim": "negative_direction", "expectedChangePct": fact.change_pct, **location})

        if relative and len(line_facts) >= 2:
            benchmark = next((fact for fact in line_facts if fact.key.upper() in {"KOSPI", "KOSDAQ", "SPY", "QQQ"} or "지수" in fact.label.lower()), None)
            company = next((fact for fact in line_facts if fact is not benchmark), None)
            if benchmark and company and company.change_pct is not None and benchmark.change_pct is not None:
                left = _directional_percent(line, company, line_facts)
                right = _directional_percent(line, benchmark, line_facts)
                if left < right:
                    contradictions.append({"kind": "relative_strength_mismatch", "factKey": company.key, "benchmark": benchmark.key, "claim": left, "benchmarkClaim": right, "expectedRelation": "company >= benchmark", **location})
            else:
                unknown.append({"kind": "relative_strength_without_known_benchmark", "factKey": line_facts[0].key})
        elif relative:
            unknown.append({"kind": "relative_strength_without_known_benchmark", "factKey": line_facts[0].key})

    # Unsafe/whitelist errors are blocking only when there is a concrete bad
    # value.  Missing manifests and unsupported declarations remain review
    # metadata, as a declaration is not semantic proof.
    if source_errors:
        contradictions.extend(source_errors)
    # A correct occurrence elsewhere cannot excuse an explicit wrong claim.
    # The finalizer locally corrects confirmed faulty passages before commit.
    blocking, downgraded = contradictions, []
    return {
        "version": 1,
        "market": _scope(candidate),
        # 수치가 빠진 것은 틀린 수치를 쓴 것과 다르다.  독자가 손해를 보지 않으므로
        # 경고로 남기고 저장한다(아래 보강은 그대로 시도한다).
        "status": "reject" if blocking else (
            "warn" if downgraded or missing or unknown or source_check.get("status") != "pass" else "pass"
        ),
        "downgradedContradictions": downgraded,
        "verifiedClaims": verified,
        "unknownClaims": unknown,
        "requiredOmissions": [
            {"factKey": fact.key, "label": fact.label, "value": fact.value, "changePct": fact.change_pct, "date": fact.date, "unit": fact.unit, "source": fact.source, "rawValue": fact.raw_value}
            for fact in missing
        ],
        "contradictions": blocking,
        "sourceChecks": source_check,
        "repairApplied": False,
        "repairCount": 0,
    }


def _format_fact(fact: _Fact) -> str:
    if fact.unit == "krw" or fact.key.startswith("flow:") or ":flow:" in fact.key:
        return f"- {fact.label}: {_flow_display(fact.raw_value if fact.raw_value is not None else fact.value)}"
    label = fact.label or fact.key
    bits = [label]
    if fact.value is not None:
        if fact.unit == "days":
            rendered = str(fact.raw_value or "").strip() if isinstance(fact.raw_value, str) else f"{int(fact.value)}거래일"
        else:
            rendered = f"{fact.value:,.2f}" if fact.unit == "points" or not float(fact.value).is_integer() else f"{int(fact.value):,}"
        bits.append(rendered)
    if fact.change_pct is not None:
        bits.append(f"{fact.change_pct:+.2f}%")
    if fact.date:
        bits.append(f"({fact.date})")
    return "- " + ": ".join((bits[0], " / ".join(bits[1:]))) if len(bits) > 1 else "- " + label


def _repair_markdown(markdown: str, facts: list[_Fact]) -> str:
    lines = ["", "## 확인된 시장 수치", "본문에서 빠진 입력 수치를 보완합니다."]
    lines.extend(_format_fact(fact) for fact in facts)
    block = "\n".join(lines).strip()
    marker = re.search(r"(?m)^##\s+(?:참고자료|Source & Data Notes)\b", str(markdown or ""), re.IGNORECASE)
    if marker:
        return str(markdown[: marker.start()]).rstrip() + "\n\n" + block + "\n\n" + str(markdown[marker.start():]).lstrip()
    return str(markdown or "").rstrip() + "\n\n" + block


def validate_briefing_candidate(candidate: dict) -> dict:
    """Return a no-write validation projection for one market candidate."""
    return _evaluate(dict(candidate or {}))


def _check_budget_active(budget: SharedRepairBudget) -> None:
    checker = getattr(budget, "check_active", None)
    if not callable(checker):
        return
    checker()


def _production_structure_violations(candidate: dict) -> list[str]:
    """Return production format violations for daily US/KR candidates.

    The API and Agent/CLI paths must share this final boundary. A non-empty
    one-line candidate cannot reach JSON staging merely because it avoided the
    separate CLI preflight. Weekly reports and JP/EU retain their contracts.
    """
    scope = _scope(candidate)
    kind = str(candidate.get("kind") or "daily").strip().lower()
    if kind != "daily" or scope not in {"us", "kr"}:
        return []
    from features.agent_mode.briefing_contract import (
        briefing_contract_violations,
        briefing_output_contract,
    )

    # Concentration selection is evidence for the writer, not a second name
    # authority at the shared save gate.  The Agent/CLI output contract checks
    # an authoritative expected pair before writeback; the API may carry
    # equivalent localized/ticker names (for example 삼성전자/Samsung
    # Electronics) in the authored headings.  Re-deriving exact names here
    # made valid KR reports fail only after generation and was stricter than
    # the writer contract.
    contract = briefing_output_contract(
        scope,
        str(candidate.get("briefingType") or "default"),
        markets=[scope],
        leader_section_modes={scope: "fixed_two"},
    )
    return briefing_contract_violations(str(candidate.get("markdown") or ""), contract)


def _production_validation(candidate: dict, source_check: dict, errors: list[dict]) -> dict:
    """Return bounded writeback metadata without claiming semantic proof."""
    reason_codes = sorted({
        str(row.get("kind") or "unknown")
        for row in errors
        if isinstance(row, dict)
    })
    return {
        "version": 2,
        "market": _scope(candidate),
        "status": "reject" if reason_codes else "pass",
        "assessmentStatus": "not_assessed",
        "contentAssessment": "not_assessed",
        "verifiedClaims": [],
        "verifiedClaimCount": None,
        "unknownClaimCount": None,
        "requiredOmissionCount": None,
        # None is intentional: zero would falsely mean that semantic content
        # validation ran and found no contradictions.
        "contradictionCount": None,
        "reasonCodes": reason_codes,
        "sourceChecks": source_check,
        "repairApplied": False,
        "repairCount": 0,
    }


def finalize_briefing_candidate(
    candidate: dict,
    *,
    repair_budget: SharedRepairBudget | None = None,
    deadline: float | None = None,
    cancelled: object | None = None,
    allow_repair: bool = True,
    visual_context: dict | None = None,
    require_structure: bool = False,
) -> dict:
    """Apply production-safe normalization and writeback checks only.

    Semantic fact, direction, relative-strength, claim-integrity, and quality
    judgments are intentionally absent here.  ``validate_briefing_candidate``
    remains an explicit offline evaluator; this production path preserves
    authored Markdown and only blocks unsafe source references, malformed
    storage input, or cancellation/deadline boundaries.
    """
    working = deepcopy(candidate or {})
    from features.daily_briefing.reader_hygiene import strip_provider_operational_notes

    working["markdown"], _ = strip_provider_operational_notes(str(working.get("markdown") or ""))
    # Some callers carry a reader section alongside the canonical body.
    for section in (working.get("briefings") or {}).values():
        if isinstance(section, dict) and isinstance(section.get("markdown"), str):
            section["markdown"], _ = strip_provider_operational_notes(section["markdown"])
    if visual_context:
        working["_validationVisuals"] = visual_context
    budget = repair_budget or SharedRepairBudget(deadline=deadline, cancelled=cancelled)
    try:
        _check_budget_active(budget)
    except (RuntimeError, TimeoutError) as exc:
        code = "cancelled" if "cancel" in str(exc).lower() else "deadline_expired"
        validation = {
            "version": 2, "market": _scope(working), "status": "reject",
            "assessmentStatus": "not_assessed", "contentAssessment": "not_assessed",
            "verifiedClaims": [], "requiredOmissions": [], "contradictions": [],
            "sourceChecks": {"status": "review", "assessmentStatus": "not_assessed", "errors": [code]},
            "reasonCodes": [code], "repairApplied": False, "repairCount": 0,
        }
        raise BriefingFinalizationError("briefing final validation unavailable", validation=validation, candidate=candidate) from exc
    if not str(working.get("markdown") or "").strip():
        validation = {
            "version": 2, "market": _scope(working), "status": "reject",
            "assessmentStatus": "not_assessed", "contentAssessment": "not_assessed",
            "verifiedClaims": [], "requiredOmissions": [], "contradictions": [],
            "sourceChecks": {"status": "review", "assessmentStatus": "not_assessed", "errors": ["format_empty"]},
            "reasonCodes": ["format_empty"], "repairApplied": False, "repairCount": 0,
        }
        raise BriefingFinalizationError("briefing production format is empty", validation=validation, candidate=candidate)
    if require_structure:
        structure_violations = _production_structure_violations(working)
        if structure_violations:
            from features.agent_mode.briefing_contract import contract_reason_codes

            validation = {
                "version": 2, "market": _scope(working), "status": "reject",
                "assessmentStatus": "not_assessed", "contentAssessment": "not_assessed",
                "verifiedClaims": [], "requiredOmissions": [], "contradictions": [],
                "sourceChecks": {"status": "not_run", "assessmentStatus": "not_assessed", "errors": []},
                "reasonCodes": contract_reason_codes(structure_violations),
                "structureViolations": structure_violations,
                "repairApplied": False, "repairCount": 0,
            }
            raise BriefingFinalizationError("briefing production structure failed", validation=validation, candidate=candidate)
    source_check, source_errors = _production_source_check(working)
    if source_errors:
        validation = {
            "version": 2, "market": _scope(working), "status": "reject",
            "assessmentStatus": "not_assessed", "contentAssessment": "not_assessed",
            "verifiedClaims": [], "requiredOmissions": [], "contradictions": source_errors,
            "sourceChecks": source_check, "reasonCodes": source_check.get("errors") or [],
            "repairApplied": False, "repairCount": 0,
        }
        raise BriefingFinalizationError("briefing production source safety failed", validation=validation, candidate=candidate)
    try:
        _check_budget_active(budget)
    except (RuntimeError, TimeoutError) as exc:
        code = "cancelled" if "cancel" in str(exc).lower() else "deadline_expired"
        validation = {
            "version": 2, "market": _scope(working), "status": "reject",
            "assessmentStatus": "not_assessed", "contentAssessment": "not_assessed",
            "verifiedClaims": [], "requiredOmissions": [], "contradictions": [],
            "sourceChecks": {**source_check, "status": "review", "errors": [code]},
            "reasonCodes": [code], "repairApplied": False, "repairCount": 0,
        }
        raise BriefingFinalizationError("briefing final validation interrupted", validation=validation, candidate=candidate) from exc
    working["finalValidation"] = _production_validation(working, source_check, [])
    from hashlib import sha256
    import json
    evidence_input = sorted(
        [(str(row.get("sourceId") or ""), str(row.get("writerExcerpt") or row.get("excerpt") or ""))
         for row in _source_rows(working)], key=lambda row: row[0],
    )
    encoded = json.dumps({"sources": evidence_input}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    input_hash = sha256(encoded).hexdigest()
    markdown_hash = sha256(str(working.get("markdown") or "").encode("utf-8")).hexdigest()
    working["validationRun"] = {
        "policyVersion": "briefing-production-structure-v2",
        "inputHash": input_hash,
        "markdownHash": markdown_hash,
        "sessionDate": _target_session_date(working, _scope(working)),
        "market": _scope(working), "kind": working.get("kind", "daily"),
        "writerSourceIds": [row[0] for row in evidence_input if row[0]],
        "repairCount": 0,
        "assessmentStatus": "not_assessed",
        "contentAssessment": "not_assessed",
        "semanticStatus": "not_assessed",
        "finalStatus": working["finalValidation"]["status"],
        "observedModel": None,
        "observedToolUse": "unknown",
    }
    working.pop("_validationVisuals", None)
    return working


# Friendly aliases for callers/tests that describe the operation as a final
# validator rather than a finalizer.
finalize_briefing = finalize_briefing_candidate
final_validate_briefing = validate_briefing_candidate


__all__ = [
    "BriefingFinalizationError",
    "SharedRepairBudget",
    "final_validate_briefing",
    "finalize_briefing",
    "finalize_briefing_candidate",
    "validate_briefing_candidate",
]
