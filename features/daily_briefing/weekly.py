"""주간 브리핑이 무엇을 덮는지 — 창 계산과 다음주 일정 컨텍스트.

일간 브리핑의 정체성은 `(시장, 세션일, 상태)`다. **주간에는 세션 개념이 없다.**
한 주는 세션 다섯 개를 덮고, 다음주 프리뷰는 아직 열리지 않은 세션을 다룬다. 그래서
세션에서 파생되는 것(세션일 저장 키, `마감`/`장중` 제목, 세션 창 자료 선별)을 그대로
쓸 수 없고, 여기서 주간용 값을 따로 만든다.

창은 두 개다.

    지난주 = 발행일 기준 7일(P-6 … P)
    다음주 = 발행일 다음 월요일부터 그 주 일요일까지

발행 요일은 사용자가 고른다(2026-08-20 결정). 일요일 발행이면 지난주 창이 정확히
월~일이고, 다른 요일을 골라도 "지난 7일"이라는 뜻은 유지된다.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from features.daily_briefing.schema import MARKET_TITLE_LABELS

# 다음주 프리뷰에 싣는 일정. `filing`은 개별 종목 공시라 주간 시장 프리뷰에서
# 신호 대비 잡음이 크고, 나머지 다섯 종이 "다음주에 무엇이 예정돼 있나"를 덮는다.
PREVIEW_EVENT_KINDS = ("macro", "central_bank", "holiday", "earnings", "dividend")
PREVIEW_EVENT_LABELS = {
    "macro": "지표",
    "central_bank": "중앙은행",
    "holiday": "휴장",
    "earnings": "실적",
    "dividend": "배당",
}
_MARKET_CODES = {"us": "US", "kr": "KR", "europe": "EUROPE", "jp": "JP"}
# 시장별 프리뷰에 GLOBAL 태그 일정도 함께 싣는다. 유가·달러 같은 일정은 특정 시장
# 소유가 아니다(관심 시장 범위가 GLOBAL 자료를 늘 보여주는 것과 같은 이유).
_PREVIEW_MARKET_CODES = {
    key: (code, "GLOBAL") for key, code in _MARKET_CODES.items()
}


@dataclass(frozen=True, slots=True)
class WeeklyWindow:
    """주간 브리핑 하나가 덮는 두 구간. 만들어진 뒤에는 바뀌지 않는다."""

    publication_date: str
    week_start: str
    week_end: str
    preview_start: str
    preview_end: str

    @property
    def source_dates(self) -> list[str]:
        """지난주 자료 날짜(KST 달력, 오름차순).

        세션 창이 아니라 달력 7일이다. 주간은 시장 마감 시각과 무관하게 "지난 한 주에
        무슨 이야기가 있었나"를 덮으므로, 시장마다 창을 다르게 잡을 이유가 없다.
        """
        start = dt.date.fromisoformat(self.week_start)
        end = dt.date.fromisoformat(self.week_end)
        return [
            (start + dt.timedelta(days=offset)).isoformat()
            for offset in range((end - start).days + 1)
        ]

    @property
    def label(self) -> str:
        """제목에 쓰는 구간 표기. `MM.DD~MM.DD`."""
        return f"{_dotted(self.week_start)}~{_dotted(self.week_end)}"

    def to_dict(self) -> dict:
        return {
            "publicationDate": self.publication_date,
            "weekStart": self.week_start,
            "weekEnd": self.week_end,
            "previewStart": self.preview_start,
            "previewEnd": self.preview_end,
        }


def _dotted(value: str) -> str:
    day = dt.date.fromisoformat(str(value)[:10])
    return f"{day.month:02d}.{day.day:02d}"


def weekly_window(publication_date: str) -> WeeklyWindow:
    published = dt.date.fromisoformat(str(publication_date)[:10])
    # 발행일 다음 월요일. 월요일 발행이면 **그 다음** 월요일이다 — 오늘이 낀 주를
    # "다음주"라고 부르면 이미 지나간 이틀이 프리뷰에 들어간다.
    ahead = (7 - published.weekday()) % 7 or 7
    next_monday = published + dt.timedelta(days=ahead)
    return WeeklyWindow(
        publication_date=published.isoformat(),
        week_start=(published - dt.timedelta(days=6)).isoformat(),
        week_end=published.isoformat(),
        preview_start=next_monday.isoformat(),
        preview_end=(next_monday + dt.timedelta(days=6)).isoformat(),
    )


def weekly_title(market: str, window: WeeklyWindow) -> str:
    """제목은 코드가 만든다. 마감·장중 상태가 없는 대신 구간이 그 자리를 갖는다."""
    label = MARKET_TITLE_LABELS.get(str(market or "").lower(), "Market Briefing")
    return f"{label} 주간 — {window.label}"


def weekly_documents(documents, window: WeeklyWindow):
    """지난주 창에 드는 기사만 고른다.

    **빈 목록을 그대로 돌려준다.** 일간의 세션 창은 비면 호출부가 예전 풀로 되돌아가지만,
    주간에서 창을 넓히면 "지난주"라는 말이 거짓이 된다 — 자료가 없으면 없다고 말하는
    쪽이 맞다(규칙 fallback이 그 한계를 본문에 적는다).
    """
    dates = set(window.source_dates)
    return [row for row in (documents or []) if str(row.get("date") or "") in dates]


def calendar_preview(db_path, market: str, window: WeeklyWindow, *, limit: int = 60) -> dict:
    """다음주 일정. 실패해도 예외를 올리지 않는다 — 브리핑이 결과물이다."""
    from features.market_calendar.service import list_events

    codes = _PREVIEW_MARKET_CODES.get(str(market or "").lower(), ())
    events: list[dict] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for code in codes:
        try:
            payload = list_events(
                db_path,
                start=window.preview_start,
                end=f"{window.preview_end}T23:59:59+09:00",
                market=code,
                kinds=list(PREVIEW_EVENT_KINDS),
                limit=limit,
            )
        except Exception:  # noqa: BLE001 - 일정을 못 읽어도 주간 요약은 나온다
            warnings.append(f"{code} 다음주 일정을 불러오지 못했습니다.")
            continue
        for event in payload.get("events") or []:
            key = str(event.get("id") or "")
            if key and key in seen:
                continue
            seen.add(key)
            events.append(event)
    events.sort(key=lambda row: (str(row.get("startsAt") or ""), str(row.get("title") or "")))
    return {"events": events[:limit], "warnings": warnings}


def render_calendar_preview(preview: dict, window: WeeklyWindow) -> str:
    """프리뷰를 표로 쓴다. **확정과 예정치를 구분해서 싣는다.**

    yfinance에서 온 실적·배당은 `estimated`라 날짜가 움직인다. 그것을 확정 일정과
    같은 모양으로 적으면 독자가 달력에 적어 둘 근거가 없다.
    """
    rows = preview.get("events") or []
    header = f"다음주 구간: {window.preview_start} ~ {window.preview_end}"
    if not rows:
        return "\n".join([
            header,
            "- 등록된 다음주 일정이 없습니다. 시장 캘린더 수집 상태를 확인하세요.",
        ])
    lines = [header, "", "| 날짜 | 종류 | 일정 | 시장 | 확정도 |", "| --- | --- | --- | --- | --- |"]
    for event in rows:
        starts = str(event.get("startsAt") or "")[:10]
        kind = PREVIEW_EVENT_LABELS.get(str(event.get("kind") or ""), str(event.get("kind") or ""))
        title = str(event.get("title") or "").replace("|", "/")
        company = str(event.get("companyName") or "").replace("|", "/")
        if company and company not in title:
            title = f"{title} ({company})"
        market = str(event.get("market") or "")
        status = str(event.get("status") or "")
        lines.append(f"| {starts} | {kind} | {title} | {market} | {status} |")
    for warning in preview.get("warnings") or []:
        lines.append(f"- 경고: {warning}")
    return "\n".join(lines)


def _driver_lines(market_drivers, limit: int = 5) -> list[str]:
    rows = []
    for driver in (market_drivers or [])[:limit]:
        name = str(driver.get("driver") or "").strip()
        if not name:
            continue
        sources = ", ".join(driver.get("sources", [])[:3]) or "미상"
        count = int(driver.get("docTotal") or len(driver.get("docs") or []))
        rows.append(f"- **{name}** — 관련 자료 {count}건 / 주요 출처: {sources}")
    return rows or ["- 지난주 자료에서 반복 확인된 시장 동인을 분리하지 못했습니다."]


def _issue_lines(issue_coverage, limit: int = 6) -> list[str]:
    rows = []
    for issue in (issue_coverage or [])[:limit]:
        title = str(issue.get("title") or issue.get("issueId") or "").strip()
        if not title:
            continue
        publishers = int(issue.get("publisherCount") or 0)
        rows.append(f"- {title} (독립 매체 {publishers}곳)")
    return rows or ["- 지난주 이슈 묶음이 확인되지 않았습니다."]


def build_weekly_rules_markdown(
    market: str,
    window: WeeklyWindow,
    *,
    docs,
    market_drivers=None,
    issue_coverage=None,
    calendar_block: str = "",
    memory_context: str = "",
    source_lines: str = "",
) -> str:
    """LLM 없이 만드는 주간 보고서.

    **해석 문장을 규칙으로 지어내지 않는다.** 한 주의 이야기를 엮는 일은 LLM 산출물이고,
    규칙이 흉내 내면 근거 없는 문장이 보고서 본문에 남는다(§5 원칙 3·4). 대신 규칙이
    확실히 아는 것 — 어떤 자료가 몇 건 있었는지, 어떤 동인이 반복됐는지, 다음주에 무엇이
    예정돼 있는지 — 만 싣고 해석이 비었다는 사실을 본문에 적는다. 빈 보고서보다 낫고,
    지어낸 해석보다 훨씬 낫다.
    """
    label = {"us": "미국장", "kr": "한국장", "europe": "유럽장", "jp": "일본장"}.get(
        str(market or "").lower(), "시장"
    )
    parts = [
        f"# {weekly_title(market, window)}",
        "",
        f"## 0. 지난주 {label} 한 줄 요약",
        "",
        f"**한 줄 결론:** {window.week_start} ~ {window.week_end} 구간의 자료 {len(docs or [])}건을 모았습니다. "
        "이 보고서는 AI 없이 규칙으로 만들어져 한 주의 해석 문장이 비어 있습니다.",
        "",
        "· 아래 항목은 규칙으로 확인된 사실이며 시장 해석이 아닙니다.",
        "· 해석과 인사이트를 채우려면 설정에서 LLM API Key나 Agent CLI를 연결한 뒤 다시 생성하세요.",
        "· 다음주 일정 표는 AI 없이도 그대로 유효합니다.",
        "",
        f"## 1. 지난주 {label} 흐름",
        "",
        f"**한 줄 결론:** 규칙 생성에서는 주간 등락 해석을 만들지 않습니다. 자료 범위는 {window.label}입니다.",
        "",
        f"· 수집 자료 {len(docs or [])}건 / 구간 {window.week_start} ~ {window.week_end}",
        "· 주간 등락률과 시장 성격 판단은 LLM 생성에서 채워집니다.",
        "· 아래 핵심 변수와 이슈 목록이 그 판단의 재료입니다.",
        "",
        f"## 2. 지난주 {label}을 움직인 핵심 변수",
        "",
        "**한 줄 결론:** 반복 확인된 동인만 나열합니다. 우선순위 해석은 포함하지 않습니다.",
        "",
        *_driver_lines(market_drivers),
        "",
        f"## 3. 지난주 {label}을 주도한 기업·업종",
        "",
        "**한 줄 결론:** 지난주 이슈 묶음입니다. 어느 기업이 지수를 끌었는지에 대한 판단은 LLM 생성에서 채워집니다.",
        "",
        *_issue_lines(issue_coverage),
        "",
        "## 4. 이야기의 변화 — 강해진 것과 약해진 것",
        "",
        "**한 줄 결론:** 강화·약화 판단은 규칙으로 만들지 않습니다. 아래는 시장 메모리에 누적된 상태입니다.",
        "",
        memory_context.strip() or "- 누적된 시장 내러티브 상태가 없습니다.",
        "",
        f"## 5. 다음주 {label} 일정",
        "",
        "**한 줄 결론:** 아래 표는 시장 캘린더에 등록된 확정·예정 일정입니다.",
        "",
        calendar_block or "- 등록된 다음주 일정이 없습니다.",
        "",
        f"## 6. 다음주 {label} 확인할 것",
        "",
        "**한 줄 결론:** 위 일정 표의 `confirmed` 행이 다음주에 실제로 확인할 항목입니다.",
        "",
        "· `estimated`로 표시된 실적·배당 일정은 움직일 수 있으므로 회사 IR로 재확인하세요.",
        "· 위 핵심 변수 목록이 다음주에도 반복되는지 확인하세요.",
        "· 해석이 필요한 항목은 LLM 생성으로 다시 만들면 채워집니다.",
        "",
        "## 이번 주 결론",
        "",
        "**한 주의 시장 성격:** 규칙 생성에서는 판단하지 않습니다.",
        "",
        f"**핵심 변수:** {', '.join(str(d.get('driver') or '') for d in (market_drivers or [])[:3] if d.get('driver')) or '확인되지 않음'}",
        "",
        "**시장 해석:** 이 보고서는 AI 없이 만들어져 해석 문장이 비어 있습니다.",
        "",
        "**다음주 확인점:** 위 다음주 일정 표를 참고하세요.",
        "",
        "## 참고자료",
        "",
        source_lines or "- 참고자료를 선별하지 못했습니다.",
        "",
        "## Source & Data Notes",
        "",
        f"- 로컬 articles/rss 자료 {len(docs or [])}건({window.week_start} ~ {window.week_end})을 기준으로 만들었습니다.",
        "- 브리핑은 filings/reports를 직접 근거로 사용하지 않습니다.",
        "- **시장 해석 문장은 LLM이 필요합니다.** 이 보고서는 규칙 fallback이라 사실 목록만 담고 있습니다.",
        "- 다음주 일정의 `estimated` 행은 제3자 예정치이며 확정 일정이 아닙니다.",
    ]
    return "\n".join(parts)
