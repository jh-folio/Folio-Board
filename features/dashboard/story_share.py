"""오늘 시장에서 떠다니는 이야기의 보도량 비중.

수집된 뉴스(articles/rss) 전체를 동인별로 묶어 "어떤 이야기가 그날 장을
이끌었나"를 규칙으로 계산한다. 브리핑과 독립이다 — 브리핑을 생성하지 않아도
매일 계산되고, 브리핑용으로 상한까지 추려낸 부분집합이 아니라 그날 수집된
시장 관련 문서 전체를 쓴다.

비중 이동은 보도량 변화일 뿐 내용 변화가 아니다. 이 모듈은 LLM을 호출하지
않으며, 수집된 뉴스의 양적 분포만 표시한다.
"""
from __future__ import annotations

import datetime as dt
import threading
import time

from features.common.market_calendar import latest_trading_day_on_or_before, previous_trading_day
from features.common.markets import PRODUCT_MARKETS
from features.daily_briefing.issue_selection import documents_for_scope
from features.daily_briefing.selection import DRIVER_TERMS, infer_drivers
from features.daily_briefing.service import news_documents, select_briefing_docs

TOP_STORY_LIMIT = 4
OTHER_LABEL = "그 외 이야기"
# 분류 실패 묶음은 이야기가 아니라 나머지다.
UNCLASSIFIED_DRIVERS = {"시장 전반"}

_CACHE_TTL_SECONDS = 600
_cache_lock = threading.Lock()
_cache: dict[tuple[str, str], tuple[float, dict]] = {}
# 무효화 세대. 인덱스를 읽는 동안 RSS 수집이 캐시를 비우면, 그 사이에 읽어 온
# 낡은 문서로 만든 값을 다시 넣어선 안 된다. 네 시장을 함께 채우게 되면서
# 계산 구간이 길어져 이 창이 더 넓어졌다.
_cache_generation = 0


def _story_counts(docs: list[dict], drivers_of=None) -> tuple[dict[str, int], int]:
    """동인별 언급 문서 수. 한 문서가 여러 이야기에 속할 수 있으므로
    비중의 분모는 문서 수가 아니라 언급 수다."""
    counts: dict[str, int] = {}
    resolve = drivers_of or infer_drivers
    for doc in docs:
        drivers = [d for d in resolve(doc) if d not in UNCLASSIFIED_DRIVERS]
        for driver in drivers or [OTHER_LABEL]:
            counts[driver] = counts.get(driver, 0) + 1
    return counts, len(docs)


class _SharedWork:
    """네 시장이 같은 계산을 네 번 하지 않게 붙잡아 두는 메모.

    시장을 바꿀 때마다 6초씩 기다린 이유가 이것이다. 날짜별 문서 선별
    (`select_briefing_docs`)은 시장과 무관한데 시장마다 다시 돌았고, 문서의
    동인 추론은 같은 문서에 대해 시장 수만큼 반복됐다. 선별은 날짜로, 동인은
    문서로 기억하면 두 번째 시장부터는 남는 일이 `documents_for_scope` 필터
    하나뿐이다.
    """

    def __init__(self, documents: list[dict]):
        self._documents = documents
        self._selected: dict[str, list[dict]] = {}
        self._drivers: dict[int, list[str]] = {}

    def selected(self, date: str) -> list[dict]:
        if date not in self._selected:
            # strict: 두 날짜를 같은 잣대로 비교해야 하므로 시장 window 날짜의
            # 문서만 쓴다. 기본(비-strict) 모드는 pool을 오늘까지 확장해 직전
            # 거래일 계산을 오염시킨다.
            chosen, _, _windows = select_briefing_docs(self._documents, date, strict=True)
            self._selected[date] = chosen
        return self._selected[date]

    def drivers(self, doc: dict) -> list[str]:
        key = id(doc)
        cached = self._drivers.get(key)
        if cached is None:
            cached = infer_drivers(doc)
            self._drivers[key] = cached
        return cached


# 시장은 계약에서 파생한다. 유럽·일본 수집량이 적어 비중이 흔들리므로
# 표본이 이 수 미만이면 그 사실을 함께 내보낸다.
STORY_SHARE_MARKETS = tuple(market.value.lower() for market in PRODUCT_MARKETS)
MIN_CONFIDENT_SAMPLE = 12
# 비교 기준이 되는 직전 거래일 수. **하루가 아니라 한 주다.**
#
# 하루끼리 비교하면 그날 수집량이 흔들리는 것만으로 비중이 수십 %p 움직인다 —
# 유럽·일본은 하루 수집이 열몇 건이라 기사 두 건이 그 폭을 만든다. 직전 다섯
# 거래일을 합쳐 분모를 키우면 그 흔들림이 줄고, 남는 이동은 실제로 보도량이
# 옮겨간 것에 가깝다. 여전히 **보도량**의 이동이지 내용의 변화는 아니다.
PREVIOUS_SESSION_WINDOW = 5


def _normalized_scope(scope: str) -> str:
    token = str(scope or "us").strip().lower()
    return token if token in STORY_SHARE_MARKETS else "us"


def _scoped_docs(documents: list[dict], date: str, scope: str, work: "_SharedWork | None" = None) -> list[dict]:
    work = work or _SharedWork(documents)
    return documents_for_scope(work.selected(date), scope)


def _share_rows(counts: dict[str, int]) -> list[dict]:
    total = sum(counts.values())
    if not total:
        return []
    ranked = sorted(
        ((label, count) for label, count in counts.items() if label != OTHER_LABEL),
        key=lambda row: (-row[1], row[0]),
    )
    top = ranked[:TOP_STORY_LIMIT]
    other_count = counts.get(OTHER_LABEL, 0) + sum(count for _, count in ranked[TOP_STORY_LIMIT:])
    rows = [
        {"label": label, "count": count, "share": round(count / total, 3), "isOther": False}
        for label, count in top
    ]
    if other_count:
        rows.append({"label": OTHER_LABEL, "count": other_count, "share": round(other_count / total, 3), "isOther": True})
    return rows


def previous_session_dates(date: str, market: str, sessions: int = PREVIOUS_SESSION_WINDOW) -> list[str]:
    """비교 기준이 되는 직전 거래일들. 최신순(가까운 날이 앞).

    오늘이 휴장일이면 "직전"은 최근 거래일의 그 이전 거래일이다 — 휴장일을
    비교 대상으로 세면 수집이 거의 없는 날이 분모에 들어간다. 공휴일이 낀 주에는
    거래일 판정이 알아서 그 날들을 건너뛰므로 창이 달력으로는 5일보다 길어진다.
    """
    day = dt.date.fromisoformat(date)
    anchor = latest_trading_day_on_or_before(day, market)
    cursor = anchor if anchor < day else day
    dates: list[str] = []
    for _ in range(max(1, int(sessions))):
        cursor = previous_trading_day(cursor, market)
        dates.append(cursor.isoformat())
    return dates


def build_story_share(
    documents: list[dict], date: str, scope: str, work: "_SharedWork | None" = None,
    *, previous_sessions: int = PREVIOUS_SESSION_WINDOW,
) -> dict:
    """오늘 비중과 직전 N거래일 합산 대비 %p 델타. 순수 함수(주입식)라 DB 없이 테스트한다."""
    scope = _normalized_scope(scope)
    market = scope.upper()
    work = work or _SharedWork(documents)
    today_docs = _scoped_docs(documents, date, scope, work)
    counts, doc_count = _story_counts(today_docs, work.drivers)
    rows = _share_rows(counts)

    # 직전 N거래일을 **합쳐서** 하나의 기준 분포로 만든다. 날짜별로 비중을 내어
    # 평균 내지 않는다 — 수집이 적은 날이 많은 날과 같은 무게를 갖게 되어, 줄이려던
    # 흔들림이 그대로 돌아온다.
    #
    # **문서는 한 번만 센다.** `select_briefing_docs`가 돌려주는 것은 그 날짜 하나가
    # 아니라 세션 창(보통 이틀)이라 이웃한 기준일들의 창이 겹친다. 그대로 더하면 같은
    # 기사가 두세 번 세어지고, 겹치는 자리에 있는 문서만 무게가 커진다.
    previous_dates = previous_session_dates(date, market, previous_sessions)
    previous_docs: list[dict] = []
    seen: set = set()
    for previous_date in previous_dates:
        for doc in _scoped_docs(documents, previous_date, scope, work):
            # 경로 하나로 묶지 않는다. 같은 문서라고 말하려면 경로·URL·제목·날짜가
            # 모두 같아야 한다 — 느슨하게 잡으면 서로 다른 기사가 한 건으로 접힌다.
            key = (doc.get("path"), doc.get("url"), doc.get("title"), doc.get("date"))
            if key in seen:
                continue
            seen.add(key)
            previous_docs.append(doc)
    previous_counts, previous_doc_count = _story_counts(previous_docs, work.drivers)
    previous_total = sum(previous_counts.values())
    for row in rows:
        if row["isOther"]:
            continue
        previous_share = (previous_counts.get(row["label"], 0) / previous_total) if previous_total else None
        row["previousShare"] = round(previous_share, 3) if previous_share is not None else None
        row["deltaPp"] = round((row["share"] - previous_share) * 100) if previous_share is not None else None

    warnings = []
    if not doc_count:
        warnings.append("no_collected_news_for_date")
    if not previous_total:
        warnings.append("no_previous_session_news")
    # 표본이 적으면 기사 한두 건이 비중을 수십 %p 움직인다. 그 델타를 그대로
    # 보여주면 수집량 변동이 내용 변화처럼 읽히므로, 표본 부족을 함께 밝힌다.
    if 0 < doc_count < MIN_CONFIDENT_SAMPLE:
        warnings.append("small_sample")
    # 기준선 임계는 창 길이에 비례한다. 하루 12건이 기준이던 값을 N일 합산에
    # 그대로 쓰면 하루 두세 건씩만 모여도 "충분한 표본"이 되어, 이 경고가
    # 사실상 꺼진다.
    if 0 < previous_total < MIN_CONFIDENT_SAMPLE * len(previous_dates):
        warnings.append("small_previous_sample")
    return {
        "schemaVersion": 2,
        "date": date,
        "market": scope,
        "collectedCount": doc_count,
        # 기간형이다. 단일 날짜를 읽던 옛 화면을 위해 `previousDate`는 창의 시작일로
        # 남긴다 — 없애면 판올림 중인 화면이 비교 기준을 아예 못 읽는다.
        "previousDate": previous_dates[-1] if previous_dates else "",
        "previousDates": list(reversed(previous_dates)),
        "previousSessionCount": len(previous_dates),
        "previousCollectedCount": previous_doc_count,
        "items": rows,
        "warnings": warnings,
        "smallSample": bool({"small_sample", "small_previous_sample"} & set(warnings)),
        "minConfidentSample": MIN_CONFIDENT_SAMPLE,
        # 규칙 계산 표시용 계약: 비중 이동은 보도량 변화이지 내용 변화가 아니다.
        "basis": "collected_news_volume",
        # 동인은 고정 어휘표다. 표에 없는 주제는 나타나지 않으므로 화면이 그 사실을 밝힌다.
        "driverBasis": {"kind": "fixed_vocabulary", "count": len(DRIVER_TERMS)},
    }


def story_share_payload(date: str | None, scope: str) -> dict:
    """캐시 있는 API 진입점. 인덱스 로드가 비싸 10분 캐시한다.

    한 시장만 물어봐도 **네 시장을 모두 계산해 캐시한다.** 인덱스 로드가
    4.7초라 시장을 바꿀 때마다 그 값을 다시 치르고 있었다. 문서를 한 번
    읽어 온 김에 나머지 세 시장을 채우면 추가 비용은 시장당 0.2초 남짓이고,
    두 번째 시장부터는 기다림이 없다.
    """
    from features.common.research_library.indexing.service import load_index

    date = date or dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
    scope = _normalized_scope(scope)
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get((date, scope))
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]
        generation = _cache_generation
    documents = news_documents(load_index())
    work = _SharedWork(documents)
    payload = build_story_share(documents, date, scope, work)
    warmed = {scope: payload}
    for other in STORY_SHARE_MARKETS:
        if other == scope:
            continue
        try:
            warmed[other] = build_story_share(documents, date, other, work)
        except Exception:
            # 한 시장이 실패해도 물어본 시장의 답은 돌려준다.
            continue
    stamped = time.monotonic()
    with _cache_lock:
        # 읽는 동안 누가 비웠으면 이 결과는 이미 낡았다. 답은 돌려주되 캐시에는
        # 넣지 않는다 — 넣으면 네 시장이 10분 동안 낡은 값을 물고 있게 된다.
        if generation == _cache_generation:
            for market, value in warmed.items():
                _cache[(date, market)] = (stamped, value)
    return payload


def invalidate_story_share_cache() -> None:
    """RSS 수집 직후 다음 조회가 새 문서를 반영하도록 캐시를 비운다."""
    global _cache_generation
    with _cache_lock:
        _cache.clear()
        _cache_generation += 1


def warm_story_share_cache() -> None:
    """대시보드가 기본 탭이라 시작 직후 미리 계산해 둔다.

    인덱스를 예열해도 여기 남는 비용이 있다 — 뉴스 12,000건을 시장별로 묶는 계산이
    5.7초다. 앱을 켜고 처음 대시보드를 여는 사람이 그걸 기다리는 대신, 시작하자마자
    조용히 치른다. 한 번 계산하면 네 시장이 모두 캐시된다.
    """
    try:
        story_share_payload(None, "US")
    except Exception:  # noqa: BLE001 - 예열 실패가 서버 시작을 막지 않는다
        pass
