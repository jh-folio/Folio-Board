"""브리핑 하나가 무엇에 대한 것인지를 먼저 정한다.

`(market, sessionDate, state)` 하나가 1차 키다. 여기서 제목·자료 창·수치 조회·저장 키가
전부 파생된다. 지금까지는 반대였다 — 발행일이 먼저 정해지고 나머지가 그 뒤를 따라가며
각자 세션을 되짚었고, 그래서 제목·본문 수치·자료 범위·파일명이 서로 다른 날짜를 가리켰다.
실측된 사례:

    2026-08-10.kr.json   세션 08-10을 08-07 종가로 서술
    2026-08-11.kr.json   같은 세션 08-10인데 파일명은 08-11

**세션은 입력이 아니라 판정 결과다.** 사용자가 날짜를 고르면 그것이 세션일이고, 예약처럼
날짜가 없으면 생성 시각에서 시장마다 독립으로 판정한다. 한 순간이 시장마다 다른 세션을
가리킨다 — 08-12 20:00 KST면 한국장은 08-12 마감이고 미국장은 08-11 마감이다(그 시각
뉴욕은 08-12 07:00, 아직 개장 전).

**상태는 `closed`와 `intraday` 둘뿐이다**(2026-08-11 결정). 개장 전 요청은 그 시장의 직전
완료 세션으로 떨어진다. 그래서 07:45 예약이 만드는 것은 전일 세션 요약이며, 그것이 의도된
동작이다. 개장 전 전망을 따로 두고 싶으면 별도 artifact 유형이 되어야 하고, 열리지도 않은
거래일을 세션일로 빌려 쓰지 않는다.

계산은 `market_calendar.briefing_market_windows()`가 이미 시장별로 하고 있다. 여기서
다시 하지 않는다 — 달력 규칙이 두 벌이 되면 그 둘이 어긋나는 날이 온다.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable

from features.common.market_calendar import (
    briefing_market_windows,
    market_open_status,
)
from features.daily_briefing.schema import SINGLE_MARKET_SCOPES

KST = dt.timezone(dt.timedelta(hours=9))

CLOSED = "closed"
INTRADAY = "intraday"
STATES = (CLOSED, INTRADAY)

# 시장 코드는 `market_calendar`가 대문자를 쓰고 저장·라우트는 소문자를 쓴다.
_MARKET_CODES = {"us": "US", "kr": "KR", "europe": "EUROPE", "jp": "JP"}


class TargetError(ValueError):
    """요청이 성립하지 않는다. 조용히 다른 날짜로 옮겨 진행하지 않는다."""

    def __init__(self, market: str, reason: str, message: str):
        self.market = market
        self.reason = reason
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class BriefingTarget:
    """브리핑 하나의 정체성. 만들어진 뒤에는 바뀌지 않는다."""

    market: str
    session_date: str
    state: str
    resolved_at: str
    calendar_provider: str

    @property
    def artifact_id(self) -> str:
        """저장 키이자 라우트 키. `YYYY-MM-DD.market`."""
        return f"{self.session_date}.{self.market}"

    @property
    def is_intraday(self) -> bool:
        return self.state == INTRADAY

    def to_dict(self) -> dict:
        return {
            "market": self.market,
            "sessionDate": self.session_date,
            "state": self.state,
            "resolvedAt": self.resolved_at,
            "calendarProvider": self.calendar_provider,
            "artifactId": self.artifact_id,
        }


def _normalize_markets(markets: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for raw in markets or []:
        key = str(raw or "").strip().lower()
        if key in SINGLE_MARKET_SCOPES and key not in seen:
            seen.append(key)
    return seen


def _now(now: dt.datetime | None) -> dt.datetime:
    return now if now is not None else dt.datetime.now(KST)


def _session_view(now: dt.datetime, calendar_fetcher=None) -> tuple[str, dict]:
    """지금 이 순간 각 시장이 어느 세션에 있는지. `(앵커 날짜, marketSessions)`.

    `briefing_market_windows`는 대상일 기준으로 시장별 세션을 이미 계산한다. 오늘 날짜를
    앵커로 주고 생성 시각을 함께 넘기면 그 결과가 곧 "지금 기준"이다.
    """
    anchor = now.astimezone(KST).date().isoformat()
    windows = briefing_market_windows(anchor, exchange_calendar_fetcher=calendar_fetcher, as_of=now)
    return anchor, (windows.get("marketSessions") or {})


def _latest_session(session: dict, anchor: str) -> tuple[str, str]:
    """그 시장의 지금 대상 세션과 상태.

    **`marketSessions[*].sessionDate`를 그대로 쓰면 안 된다.** 그 값은 *마지막 완료* 세션이라
    장중에는 전일을 가리킨다(`briefing_market_windows`가 `phase == "closed"`일 때만 대상일을
    넣는다). 장중이면 진행 중인 세션은 앵커 날짜 자체다 — `phase == "intraday"`가 뜻하는
    것이 바로 "앵커 날짜의 장이 열려 있다"이기 때문이다.

    미국·유럽은 `phase`가 없다. 한국시간 자정 이후에 마감하므로 브리핑 시점에는 언제나
    직전 완료 세션이고, 그 값이 이미 `sessionDate`에 들어 있다.
    """
    if session.get("phase") == "intraday":
        return anchor, INTRADAY
    return str(session.get("sessionDate") or "")[:10], CLOSED


def resolve_targets(
    markets: Iterable[str],
    *,
    session_date: str = "",
    now: dt.datetime | None = None,
    calendar_fetcher=None,
) -> tuple[list[BriefingTarget], list[TargetError]]:
    """요청을 시장별 `BriefingTarget`으로 확정한다.

    `session_date`를 주면 **그 시장의 세션일**로 읽는다. 발행일이 아니다 — 변환하지 않는다.
    주지 않으면 생성 시각에서 시장마다 독립으로 판정하므로, 한 요청이 서로 다른 날짜를
    가리키는 target 여러 개를 만들 수 있다.

    성립하지 않는 시장은 target을 만들지 않고 `TargetError`로 돌려준다. 그 시장만 빠지고
    나머지는 진행한다 — 한 시장이 휴장이라고 다른 시장 브리핑까지 막을 이유가 없다.
    """
    resolved_at = _now(now).astimezone(KST).isoformat()
    requested = _normalize_markets(markets)
    if not requested:
        return [], []

    anchor, view = _session_view(_now(now), calendar_fetcher)
    targets: list[BriefingTarget] = []
    errors: list[TargetError] = []

    for market in requested:
        session = view.get(market) or {}
        latest, latest_state = _latest_session(session, anchor)
        provider = str(session.get("provider") or "")
        if not latest:
            errors.append(TargetError(
                market, "calendar_unavailable",
                f"{market.upper()} 거래일 달력을 읽지 못해 대상 세션을 정할 수 없습니다.",
            ))
            continue

        if not session_date:
            targets.append(BriefingTarget(
                market=market,
                session_date=latest,
                state=latest_state,
                resolved_at=resolved_at,
                calendar_provider=provider,
            ))
            continue

        try:
            requested_day = dt.date.fromisoformat(str(session_date)[:10])
        except ValueError:
            errors.append(TargetError(
                market, "invalid_date",
                f"세션일을 읽을 수 없습니다: {session_date!r}",
            ))
            continue

        latest_day = dt.date.fromisoformat(latest)
        state = latest_state
        if requested_day > latest_day:
            # 아직 열리지 않았거나 끝나지 않은 장이다. 직전 세션 수치로 메워 진행하는
            # 것이 지난 사고의 원인이었다.
            errors.append(TargetError(
                market, "session_not_available",
                f"{market.upper()} {requested_day.isoformat()} 장은 아직 마감되지 않았습니다. "
                f"가장 최근 세션은 {latest}입니다.",
            ))
            continue
        if requested_day < latest_day:
            # 지난 세션이다. 그날 장이 실제로 열렸는지 확인한다.
            status = market_open_status(requested_day, _MARKET_CODES[market], calendar_fetcher)
            if not status.get("isOpen"):
                errors.append(TargetError(
                    market, "not_a_session",
                    f"{market.upper()} {requested_day.isoformat()}은 거래일이 아닙니다.",
                ))
                continue
            provider = str(status.get("provider") or provider)
            state = CLOSED

        targets.append(BriefingTarget(
            market=market,
            session_date=requested_day.isoformat(),
            state=state,
            resolved_at=resolved_at,
            calendar_provider=provider,
        ))

    return targets, errors


@dataclass(frozen=True, slots=True)
class WeeklyBriefingTarget:
    """주간 브리핑 하나의 정체성.

    **세션이 없다.** 그래서 `resolve_targets`의 거부 규칙(`session_not_available`,
    `not_a_session`)을 태우지 않는다 — 주말 발행이 정상인 산출물을 "그날은 거래일이
    아니다"로 막으면 주간 브리핑을 만들 길이 아예 없다. 대신 발행일이 미래이면
    거부한다. 아직 오지 않은 주를 요약할 수는 없다.
    """

    market: str
    publication_date: str
    week_start: str
    week_end: str
    preview_start: str
    preview_end: str
    resolved_at: str

    @property
    def artifact_id(self) -> str:
        """저장 키이자 라우트 키. `YYYY-MM-DD.market.weekly`."""
        return f"{self.publication_date}.{self.market}.weekly"

    def to_dict(self) -> dict:
        return {
            "market": self.market,
            "kind": "weekly",
            "publicationDate": self.publication_date,
            "weekStart": self.week_start,
            "weekEnd": self.week_end,
            "previewStart": self.preview_start,
            "previewEnd": self.preview_end,
            "resolvedAt": self.resolved_at,
            "artifactId": self.artifact_id,
        }


def resolve_weekly_targets(
    markets: Iterable[str],
    *,
    publication_date: str = "",
    now: dt.datetime | None = None,
) -> tuple[list[WeeklyBriefingTarget], list[TargetError]]:
    """주간 요청을 시장별 target으로 확정한다.

    발행일을 주지 않으면 오늘이다. 시장마다 창이 같으므로 판정도 같지만, 실패를
    시장별로 돌려주는 모양은 일간과 맞춘다 — 호출부가 두 경로를 다르게 다루지 않게 한다.
    """
    from features.daily_briefing.weekly import weekly_window

    moment = _now(now).astimezone(KST)
    resolved_at = moment.isoformat()
    requested = _normalize_markets(markets)
    if not requested:
        return [], []
    raw = str(publication_date or "").strip()[:10] or moment.date().isoformat()
    try:
        published = dt.date.fromisoformat(raw)
    except ValueError:
        return [], [
            TargetError(market, "invalid_date", f"발행일을 읽을 수 없습니다: {publication_date!r}")
            for market in requested
        ]
    if published > moment.date():
        return [], [
            TargetError(
                market, "week_not_available",
                f"{published.isoformat()}은 아직 오지 않은 날짜라 주간 브리핑을 만들 수 없습니다.",
            )
            for market in requested
        ]
    window = weekly_window(published.isoformat())
    targets = [
        WeeklyBriefingTarget(
            market=market,
            publication_date=window.publication_date,
            week_start=window.week_start,
            week_end=window.week_end,
            preview_start=window.preview_start,
            preview_end=window.preview_end,
            resolved_at=resolved_at,
        )
        for market in requested
    ]
    return targets, []


def briefing_title(target: BriefingTarget) -> str:
    """제목은 코드가 만든다. LLM이 시장·날짜·상태를 다시 정하지 못한다.

    형식은 `{시장 표시명} — {YYYY.MM.DD} {마감|장중}`이며 저장 제목과 프롬프트에 넣는
    기대 제목이 같은 함수에서 나온다.
    """
    from features.daily_briefing.schema import MARKET_TITLE_LABELS

    label = MARKET_TITLE_LABELS[target.market]
    dotted = target.session_date.replace("-", ".")
    return f"{label} — {dotted} {'장중' if target.is_intraday else '마감'}"
