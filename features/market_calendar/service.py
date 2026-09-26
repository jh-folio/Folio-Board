from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from features.market_calendar.adapters.dividends import estimated_dividend_events
from features.market_calendar.adapters.earnings import estimated_earnings_events
from features.market_calendar.adapters.exchange import official_holiday_events
from features.market_calendar.adapters.central_banks import official_central_bank_events
from features.market_calendar.adapters.fed import official_fomc_events
from features.market_calendar.adapters.filings import local_filing_events
from features.market_calendar.adapters.bok import fetch_bok_macro_events
from features.market_calendar.adapters.fred import fetch_fred_macro_events
from features.market_calendar.adapters.yf_economic import fetch_yf_economic_events
from features.market_calendar.schema import normalize_event
from features.market_calendar.projection import project_events
from features.common.market_data.major_companies import major_company_symbols
from features.portfolio.service import get_portfolio


def ensure_calendar_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS market_calendar_events (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, market TEXT NOT NULL,
            country TEXT NOT NULL, tickers_json TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
            timezone TEXT NOT NULL, all_day INTEGER NOT NULL, status TEXT NOT NULL, importance INTEGER NOT NULL,
            source TEXT NOT NULL, source_url TEXT NOT NULL, as_of TEXT NOT NULL, fetched_at TEXT NOT NULL,
            provider TEXT NOT NULL, parser_version TEXT NOT NULL,
            cancelled INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT '',
            actual_value TEXT NOT NULL DEFAULT '', previous_value TEXT NOT NULL DEFAULT '',
            unit TEXT NOT NULL DEFAULT '', observed_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(market_calendar_events)").fetchall()}
    if "cancelled" not in columns:
        connection.execute("ALTER TABLE market_calendar_events ADD COLUMN cancelled INTEGER NOT NULL DEFAULT 0")
    if "updated_at" not in columns:
        connection.execute("ALTER TABLE market_calendar_events ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
    # 발표된 지표의 실제 결과. 예정만 남기면 발표 후 캘린더를 다시 열 이유가 없다.
    for name in ("actual_value", "previous_value", "unit", "observed_at", "forecast_value", "company_name"):
        if name not in columns:
            connection.execute(f"ALTER TABLE market_calendar_events ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_market_calendar_time ON market_calendar_events(starts_at, kind)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_market_calendar_market ON market_calendar_events(market, starts_at)")


# 예전 ECOS 어댑터(parser 0.4.0)는 관측월 15일 08:00 KST라는 **합성 시각**에 행을 만들었다.
# 7월 CPI가 7월 15일 발표로, 기준금리 "결정"이 매달 15일(광복절 포함)로 보였다. 지금 어댑터는
# 관행일 종일 행만 만들고 기준금리는 한은 공시 일정에서 오므로, 이 조건에 맞는 행은 옛 행뿐이다.
#
# 이 행들은 지우지 않고 **읽을 때 뺀다**. 대체 행이 없는 옛 행(기준금리, 45일 창 밖의 과거 값,
# 옛 예정일)도 저장소에는 그대로 남아 되돌릴 수 있고, 화면·브리핑·대시보드에는 나오지 않는다.
LEGACY_BOK_ROW_SQL = (
    "provider = 'bok' AND all_day = 0 AND parser_version = '0.4.0' "
    "AND substr(starts_at, 9) = '15T08:00:00+09:00'"
)


def upsert_events(db_path: Path, events: list[dict]) -> int:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with sqlite3.connect(str(db_path)) as conn:
        ensure_calendar_table(conn)
        for value in events:
            try:
                row = normalize_event(value)
            except (TypeError, ValueError):
                continue
            conn.execute(
                """INSERT INTO market_calendar_events
                   (id,kind,title,market,country,tickers_json,starts_at,ends_at,timezone,all_day,status,importance,source,source_url,as_of,fetched_at,provider,parser_version,cancelled,updated_at,actual_value,previous_value,unit,observed_at,forecast_value,company_name)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title,market=excluded.market,country=excluded.country,
                   tickers_json=excluded.tickers_json,starts_at=excluded.starts_at,ends_at=excluded.ends_at,
                   timezone=excluded.timezone,all_day=excluded.all_day,status=excluded.status,importance=excluded.importance,
                   source=excluded.source,source_url=excluded.source_url,as_of=excluded.as_of,fetched_at=excluded.fetched_at,
                   provider=excluded.provider,parser_version=excluded.parser_version,cancelled=excluded.cancelled,
                   updated_at=excluded.updated_at,actual_value=excluded.actual_value,
                   previous_value=excluded.previous_value,unit=excluded.unit,observed_at=excluded.observed_at,
                   forecast_value=excluded.forecast_value,company_name=excluded.company_name""",
                (row["id"], row["kind"], row["title"], row["market"], row["country"], json.dumps(row["tickers"], ensure_ascii=False), row["startsAt"], row["endsAt"], row["timezone"], int(row["allDay"]), row["status"], row["importance"], row["source"], row["sourceUrl"], row["asOf"], row["fetchedAt"], row["provider"], row["parserVersion"], int(row["cancelled"]), row["updatedAt"], row["actualValue"], row["previousValue"], row["unit"], row["observedAt"], row["forecastValue"], row["companyName"]),
            )
            count += 1
        conn.commit()
    return count


# 지표 발표일은 키가 있어야 들어온다. 키가 없으면 캘린더는 그냥 빈 화면이 되는데,
# 사용자는 "이번 주에 지표가 없는 것"과 "수집 자체가 안 되는 것"을 구분할 수 없다.
# 새로고침 직후의 안내 문구로만 알리면 화면을 처음 열었을 때는 알 길이 없으므로,
# 조회 응답이 항상 공백을 함께 들고 나간다.
MACRO_COVERAGE_GAPS = {
    "US": {
        "provider": "fred",
        "requires": "FRED_API_KEY",
        # 키가 없어도 화면이 비지는 않는다. yfinance 폴백이 추정 일정으로 채우므로,
        # 공백이 아니라 정확도 차이임을 알린다.
        "severity": "degraded",
        "message": "미국 지표 일정을 Yahoo Finance 추정치로 표시하고 있습니다. FRED API Key를 등록하면 공식 확정일로 바뀝니다.",
        "settingsHint": "설정 > 외부 데이터에서 FRED API Key를 등록하세요.",
        "sourceUrl": "https://fred.stlouisfed.org/docs/api/api_key.html",
    },
    "KR": {
        "provider": "bok_ecos",
        "requires": "BOK_API_KEY",
        # 금통위 일정은 한국은행 공시 일정표라 키 없이 들어온다(`central_banks.py`).
        # 키가 필요한 것은 ECOS의 CPI·PPI 결과와 다음 발표 예정일이다.
        "severity": "degraded",
        "message": "한국 CPI·PPI 발표 결과는 한국은행 ECOS API Key를 등록해야 수집됩니다. 금통위 일정은 키 없이 표시되며, 일부 지표는 Yahoo Finance 추정치로 표시됩니다.",
        "settingsHint": "설정 > 외부 데이터에서 BOK API Key를 등록하세요.",
        "sourceUrl": "https://ecos.bok.or.kr/api/",
    },
}


def macro_coverage_gaps(markets: list[str] | None = None) -> list[dict]:
    """Report which macro calendars cannot be collected with the current keys.

    Reported per market, so a Korean user missing only the BOK key still sees
    the US indicators they do have and learns exactly what is absent.
    """
    from features.llm_settings.client import bok_api_key, fred_api_key

    present = {"US": bool(fred_api_key()), "KR": bool(bok_api_key())}
    wanted = [m for m in (markets or ["US", "KR"]) if m in MACRO_COVERAGE_GAPS]
    gaps = []
    for market in wanted:
        if present.get(market):
            continue
        gaps.append({"market": market, "kind": "macro", **MACRO_COVERAGE_GAPS[market]})
    return gaps


def list_events(db_path: Path, *, start: str = "", end: str = "", market: str = "", kinds: list[str] | None = None, tickers: list[str] | None = None, limit: int = 200) -> dict:
    requested_markets = [market.upper()] if market else ["US", "KR"]
    gaps = macro_coverage_gaps(requested_markets)
    if not Path(db_path).exists():
        return {"events": [], "count": 0, "dataGaps": gaps}
    clauses = ["1=1", f"NOT ({LEGACY_BOK_ROW_SQL})"]
    params = []
    if start:
        clauses.append("starts_at>=?")
        params.append(start)
    if end:
        clauses.append("starts_at<=?")
        params.append(end)
    if market:
        clauses.append("market=?")
        params.append(market.upper())
    kinds = [kind for kind in kinds or [] if kind]
    if kinds:
        clauses.append(f"kind IN ({','.join('?' for _ in kinds)})")
        params.extend(kinds)
    limit = max(1, min(int(limit), 500))
    wanted = {ticker.upper() for ticker in tickers or []}
    sql = f"SELECT * FROM market_calendar_events WHERE {' AND '.join(clauses)} ORDER BY starts_at"
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        ensure_calendar_table(conn)
        # 티커 판정은 파이썬에서 한다(tickers_json이 리스트라 LIKE로 거르면 `MU`가 `MUFG`를 문다).
        # 그래서 티커를 물었을 때는 SQL LIMIT을 걸지 않는다 — 걸면 티커와 무관한 앞쪽 일정이
        # LIMIT을 소진해 종목 일정이 한 건도 남지 않는다(실측: 90일 창의 앞 20건이 전부 macro라
        # `ticker=AVGO&limit=20`이 항상 빈 결과였다). 절단은 필터 뒤에 한다.
        if wanted:
            rows = conn.execute(sql, tuple(params)).fetchall()
        else:
            rows = conn.execute(f"{sql} LIMIT ?", (*params, limit)).fetchall()
    events = []
    for row in rows:
        row_tickers = json.loads(row["tickers_json"] or "[]")
        if wanted and not wanted.intersection(row_tickers):
            continue
        if len(events) >= limit:
            break
        events.append({
            "id": row["id"], "kind": row["kind"], "title": row["title"], "market": row["market"], "country": row["country"],
            "tickers": row_tickers, "startsAt": row["starts_at"], "endsAt": row["ends_at"], "timezone": row["timezone"], "allDay": bool(row["all_day"]),
            "status": row["status"], "importance": row["importance"], "source": row["source"], "sourceUrl": row["source_url"],
            "asOf": row["as_of"], "fetchedAt": row["fetched_at"], "provider": row["provider"], "parserVersion": row["parser_version"],
            "cancelled": bool(row["cancelled"]), "updatedAt": row["updated_at"],
            "actualValue": row["actual_value"], "forecastValue": row["forecast_value"],
            "previousValue": row["previous_value"],
            "unit": row["unit"], "observedAt": row["observed_at"], "companyName": row["company_name"],
        })
    events = project_events(events)
    return {"events": events, "count": len(events), "dataGaps": gaps}


def _calendar_target_tickers(data_dir: Path) -> list[str]:
    """Largest companies per market, plus the user's own positions and watchlist.

    "주요 실적"은 관심 등록 여부와 무관해야 한다. 워치리스트에 넣지 않았다는 이유로
    NVDA 실적을 놓치면 캘린더가 제 역할을 못한다. 시총 상위는 시장별로 뽑으므로
    (US 20 / KR·EU·JP 각 10) 홈 마켓이 비지 않는다.
    """
    tickers = set(major_company_symbols())
    portfolio = get_portfolio(data_dir)
    tickers.update(str(row.get("symbol") or row.get("ticker") or "").upper() for row in portfolio.get("positions") or [] if row.get("symbol") or row.get("ticker"))
    try:
        from features.dashboard.schema import native_symbol
        from features.watchlist_notes.service import get_watchlist, sec_ticker_for_name, tradingview_symbol_for_query

        for item in get_watchlist(data_dir):
            symbol = native_symbol(tradingview_symbol_for_query(item)) or sec_ticker_for_name(item)
            if symbol and not symbol.startswith("^"):
                tickers.add(symbol)
    except Exception:
        pass
    return sorted(t for t in tickers if t)


def refresh_calendar(data_dir: Path, *, include_estimates: bool = True) -> dict:
    data_dir = Path(data_dir)
    research_db = data_dir / "research-index.sqlite3"
    memory_db = data_dir / "market-memory.sqlite3"
    tickers = _calendar_target_tickers(data_dir)
    events = local_filing_events(research_db)
    providers: dict[str, int | str] = {"official_filing": len(events)}

    today = dt.date.today()
    # 지표는 앞으로만 받으면 결과가 실린 발표가 하나도 안 들어온다. 7월 지표가
    # 캘린더에 없던 이유가 이것이다 — 수집 창이 오늘부터 시작했다.
    macro_start = (today - dt.timedelta(days=45)).isoformat()
    years = sorted({today.year, (today + dt.timedelta(days=90)).year})
    holidays = official_holiday_events(years)
    fomc = official_fomc_events(years)
    # ECB·BoE·BOJ도 Fed와 같이 각 은행이 공시한 연간 일정 전사다. 키가 필요 없다.
    central_banks = official_central_bank_events(years)
    events.extend(holidays)
    events.extend(fomc)
    events.extend(central_banks)
    providers.update({
        "official_holidays": len(holidays),
        "official_fomc": len(fomc),
        "official_central_banks": len(central_banks),
    })

    from features.llm_settings.client import bok_api_key, fred_api_key

    key = fred_api_key()
    if key:
        macro = fetch_fred_macro_events(key, start=macro_start, end=(today + dt.timedelta(days=60)).isoformat())
        events.extend(macro)
        providers["fred_macro"] = len(macro)
    else:
        providers["fred_macro"] = "fred_key_required"

    # 한국은 normalizer만 있고 수집 경로가 연결된 적이 없어 금통위·지표가 0건이었다.
    # ECOS 키가 있으면 채우고, 없으면 미국과 같은 형태의 명시적 공백으로 남긴다.
    bok_key = bok_api_key()
    if bok_key:
        kr_macro = fetch_bok_macro_events(
            bok_key, start=macro_start, end=(today + dt.timedelta(days=60)).isoformat()
        )
        events.extend(kr_macro)
        providers["bok_macro"] = len(kr_macro)
    else:
        providers["bok_macro"] = "bok_key_required"

    # 일본·유럽은 FRED가 다루지 않는다. yfinance 경제 캘린더는 키 없이 이 시장을 채우는
    # 유일한 경로라 estimated로 넣는다. FRED 키가 없으면 미국까지 여기서 받아,
    # 키를 발급받지 않은 사용자도 지표 일정을 빈 화면으로 보지 않게 한다.
    overseas = fetch_yf_economic_events(
        start=macro_start,
        end=(today + dt.timedelta(days=60)).isoformat(),
        include_us=not key,
    )
    events.extend(overseas)
    providers["yfinance_economic"] = len(overseas)
    if not key:
        providers["us_macro_source"] = "yfinance_fallback"

    estimates: list[dict] = []
    queried: dict[str, set[str]] = {}
    if include_estimates and tickers:
        earnings, earnings_queried = estimated_earnings_events(tickers)
        dividends, dividends_queried = estimated_dividend_events(tickers)
        estimates = [*earnings, *dividends]
        # 두 어댑터는 서로 다른 호출(`Ticker.calendar` vs `get_info()`)이라 따로 실패한다.
        # 합집합으로 넘기면 한쪽만 성공한 날 다른 종류의 멀쩡한 행이 "물어봤는데 답에 없다"로
        # 지워진다. 종류별로 나눠 넘긴다.
        queried = {"earnings": earnings_queried, "dividend": dividends_queried}
        events.extend(estimates)
        providers.update({"yfinance_earnings": len(earnings), "yfinance_dividends": len(dividends)})
    count = upsert_events(memory_db, events)
    if any(queried.values()):
        providers["pruned_estimates"] = prune_stale_estimates(memory_db, estimates, queried)
    return {"ok": True, "stored": count, "providers": providers, "dataGaps": macro_coverage_gaps(), "agentCalled": False}


def prune_stale_estimates(db_path: Path, fresh: list[dict], queried: dict[str, set[str]] | set[str]) -> int:
    """이번에 **물어본 티커**에 한해, 답에 없던 실적·배당 추정 행을 지운다.

    `queried`는 `{"earnings": {...}, "dividend": {...}}`처럼 **종류별**로 받는다.
    실적과 배당은 서로 다른 provider 호출이라 한쪽만 실패하는 일이 흔한데, 합쳐서
    받으면 조회조차 못 한 종류의 행이 삭제 통행권을 얻는다. 집합 하나를 주면 두 종류
    모두에 적용하는 옛 계약으로 동작한다.

    이 두 종류는 매 수집마다 티커 목록에서 다시 만들어지므로, 물어봤는데 답에
    없는 행은 갱신 실패가 아니라 더는 성립하지 않는 행이다. 실제로 시장 판정을
    고친 뒤 `8316.T` 실적이 도쿄와 뉴욕 두 줄로 보였다 — id가
    `kind|provider|title|시작시각`인데 시간대가 바뀌면서 옛 행이 남았다.

    **물어본 티커로 범위를 좁히는 것이 핵심이다.** 어댑터는 티커별 예외를 삼키고
    상한(30개)에서 자르므로 "결과에 없다"가 곧 "없어졌다"가 아니다. 좁히지 않으면
    조회조차 안 된 티커의 멀쩡한 행이 지워진다 — 실측으로 대상 53개 중 앞 30개만
    조회돼 `GEV`의 유효한 실적 행이 삭제 대상이었다. rate limit으로 일부가 실패한
    날에도 같은 일이 난다.

    날짜로 자르지 않는다. yfinance가 주는 실적일은 최근 지나간 날짜일 수도 있어,
    앞으로의 행만 지우면 옛 중복이 과거 쪽에 그대로 남는다(실측: `8316.T` 두 줄
    모두 7월 31일).

    공식 일정(휴장·FOMC·지표)과 확정 상태 행은 건드리지 않는다.
    """
    def _symbols(values) -> set[str]:
        return {str(t).strip().upper() for t in (values or ()) if str(t).strip()}

    if isinstance(queried, dict):
        by_kind = {str(kind): _symbols(values) for kind, values in queried.items()}
    else:
        shared = _symbols(queried)
        by_kind = {"earnings": shared, "dividend": shared}
    if not any(by_kind.values()):
        return 0
    # id는 저장할 때 `normalize_event`가 만든다. 호출자가 정규화 전 dict를 넘기면
    # keep이 비어 방금 넣은 행까지 지워지므로, 여기서 같은 방식으로 다시 만든다.
    keep = set()
    for row in fresh:
        try:
            keep.add(normalize_event(row)["id"])
        except (TypeError, ValueError):
            continue
    with sqlite3.connect(str(db_path)) as conn:
        ensure_calendar_table(conn)
        # tickers_json은 리스트라 SQL로 정확히 매칭하기 어렵다. 후보만 SQL로 좁히고
        # 티커 판정은 파이썬에서 한다 — LIKE로 걸러내면 `MU`가 `MUFG`를 문다.
        rows = conn.execute(
            """SELECT id, kind, tickers_json FROM market_calendar_events
               WHERE kind IN ('earnings','dividend') AND status = 'estimated'
                 AND provider = 'yfinance'"""
        ).fetchall()
        doomed = []
        for row_id, kind, tickers_json in rows:
            if row_id in keep:
                continue
            symbols = by_kind.get(str(kind)) or set()
            if not symbols:
                continue
            try:
                row_tickers = {str(t).strip().upper() for t in json.loads(tickers_json or "[]")}
            except (TypeError, ValueError):
                continue
            if row_tickers and row_tickers <= symbols:
                doomed.append(row_id)
        if not doomed:
            return 0
        placeholders = ",".join("?" * len(doomed))
        cursor = conn.execute(
            f"DELETE FROM market_calendar_events WHERE id IN ({placeholders})",
            tuple(doomed),
        )
        return cursor.rowcount or 0
