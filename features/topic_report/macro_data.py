"""Fetch structured economic data from FRED (US) and BOK ECOS (Korea)."""
from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from features.common.data_reliability.macro_fetch import fetch_macro_data_cached
from features.common.workspace import data_dir

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
BOK_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"

# 일간 시리즈 기준 약 7년. 분기 요약(_quarterly_history)이 이 범위를 압축해 컨텍스트에
# 싣고, 최근 상세는 앞쪽 8개만 쓴다.
FRED_OBSERVATION_LIMIT = 1900
FRED_RECENT_OBSERVATIONS = 8
FRED_HISTORY_QUARTERS = 28

# FRED series definitions
FRED_SERIES_META: dict[str, str] = {
    "FEDFUNDS": "Fed Funds Rate (%)",
    "UNRATE": "미국 실업률 (%)",
    "CPIAUCSL": "미국 CPI (지수, 2022=100)",
    "CPILFESL": "미국 근원 CPI (지수, 2022=100)",
    "PCEPI": "PCE 물가지수 (2017=100)",
    "PCEPILFE": "근원 PCE 물가지수 (2017=100)",
    "PAYEMS": "비농업고용 (천명)",
    "INDPRO": "산업생산지수 (2017=100)",
    "DGS2": "미국 2년물 금리 (%)",
    "DGS5": "미국 5년물 금리 (%)",
    "DGS10": "미국 10년물 금리 (%)",
    "DGS30": "미국 30년물 금리 (%)",
    "T10Y2Y": "10Y-2Y 스프레드 (%p)",
    "T10Y3M": "10Y-3M 스프레드 (%p)",
    # 기대인플레이션·실질금리 분해용. 이 셋이 없으면 "장기금리 상승이 실질금리 때문인가
    # 기대인플레이션 때문인가"라는 질문에 수치로 답할 수 없다 — 계획이 이 시리즈를
    # 요청했는데도 코드가 버려서, 보고서가 "분해할 자료가 없다"고 적은 적이 있다.
    "T10YIE": "10년 기대인플레이션 (BEI, %)",
    "T5YIE": "5년 기대인플레이션 (BEI, %)",
    "T5YIFR": "5y5y 선도 기대인플레이션 (%)",
    "DFII10": "미국 10년물 실질금리 (TIPS, %)",
    "DFII5": "미국 5년물 실질금리 (TIPS, %)",
    "SOFR": "SOFR (%)",
    # 국채 수급·유동성 축. 기간프리미엄 논의에서 계획이 실제로 요청한 계열이다.
    "WALCL": "연준 총자산 (백만달러)",
    "TREAST": "연준 보유 국채 (백만달러)",
    "RRPONTSYD": "연준 역레포 잔액 (십억달러)",
    "DTWEXBGS": "달러지수 (광의, 2006=100)",
    "VIXCLS": "VIX",
    "DCOILWTICO": "WTI 유가 (달러/배럴)",
}

# 계획의 requiredMacroData는 LLM이 쓴 자유 텍스트다(실측으로 규칙 힌트표에 없는
# T10YIE·DFII10을 모델이 지어냈다 — 이번엔 맞았지만 다음에도 맞으리라는 보장이 없다).
# 알려진 시리즈만 통과시킨다(§5 원칙 4).
# 이미 퍼센트로 표시되는 시리즈. 이런 계열의 변화는 %p(절대 차이)다.
# 나머지(지수·고용자 수·잔액·유가 등)는 수준값이라 변화를 **%**로 내야 한다 —
# 절대 차이를 단위 없이 내보냈더니 모델이 근원 CPI 지수의 1년 차이 8.11포인트를
# "전년 대비 +8.11%"로 읽어 보고서에 실었다(실제 상승률은 약 2.5%다).
_PERCENT_SERIES = frozenset({
    "FEDFUNDS", "UNRATE", "DGS2", "DGS5", "DGS10", "DGS30", "T10Y2Y", "T10Y3M",
    "T10YIE", "T5YIE", "T5YIFR", "DFII10", "DFII5", "SOFR",
})


def change_unit(series_id: str) -> str:
    return "%p" if str(series_id or "").upper() in _PERCENT_SERIES else "%"


MAX_FRED_SERIES = 12


def resolve_fred_series(requested, fallback: list[str] | None = None) -> list[str]:
    """요청 시리즈를 허용 목록으로 거른다. 하나도 안 남으면 fallback을 쓴다."""
    out: list[str] = []
    unknown: list[str] = []
    for raw in requested or []:
        sid = str(raw or "").strip().upper()
        if not sid or sid in out:
            continue
        if sid in FRED_SERIES_META:
            out.append(sid)
        else:
            unknown.append(sid)
        if len(out) >= MAX_FRED_SERIES:
            break
    return out or [s for s in (fallback or []) if s in FRED_SERIES_META][:MAX_FRED_SERIES]

# BOK ECOS series definitions
BOK_SERIES_META: dict[str, dict] = {
    "722Y001": {
        "label": "한국은행 기준금리 (%)",
        "cycle": "M",
        "item1": "0101000",
        "item2": "",
    },
    "731Y003": {
        "label": "소비자물가지수 (2020=100)",
        "cycle": "M",
        "item1": "0",
        "item2": "",
    },
    "301Y013": {
        "label": "경상수지 (백만달러)",
        "cycle": "M",
        "item1": "",
        "item2": "",
    },
    "732Y004": {
        "label": "외환보유액 (백만달러)",
        "cycle": "M",
        "item1": "",
        "item2": "",
    },
}


# ---------------------------------------------------------------------------
# FRED
# ---------------------------------------------------------------------------

def _fetch_fred_one(series_id: str, api_key: str, limit: int = FRED_OBSERVATION_LIMIT) -> list[tuple[str, str]]:
    """Fetch up to `limit` most recent observations for a FRED series.
    Returns list of (date, value) tuples, newest first.

    14개만 받던 시절에는 월간 시리즈가 1년 남짓, 일간 시리즈가 3주였다. 과거 국면
    (2021~2022년 긴축 같은)과 지금을 비교하려면 시리즈가 그때까지 닿아야 한다.
    FRED는 전 구간을 무료로 준다 — 아끼는 대신 못 하는 분석이 생겼다."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": str(limit),
    }
    url = FRED_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "MarketResearchArchive/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [
        (o["date"], o["value"])
        for o in data.get("observations", [])
        if o.get("value") not in (".", "", None)
    ]



def _trim_number(value: str) -> str:
    """FRED가 돌려주는 `2.3500000000` 같은 표기를 줄인다. 컨텍스트 한 줄에 28개가 들어간다."""
    text = str(value or "").strip()
    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".") or "0"


def _observation_a_year_before(obs: list[tuple[str, str]], latest_date: str):
    """최신 관측일로부터 1년 전에 가장 가까운(그보다 이르지 않은 최신) 관측치."""
    try:
        anchor = dt.date.fromisoformat(str(latest_date)[:10]) - dt.timedelta(days=365)
    except Exception:
        return (None, None)
    for date_text, value in obs:  # newest first
        try:
            when = dt.date.fromisoformat(str(date_text)[:10])
        except Exception:
            continue
        if when <= anchor:
            return (date_text, value)
    return (None, None)


def _quarterly_history(obs: list[tuple[str, str]]) -> list[list]:
    """분기마다 마지막 관측치 하나. 오래된 것부터.

    일간 시리즈를 그대로 컨텍스트에 실으면 한 시리즈가 1,900줄이다. 과거 국면과의
    비교에 필요한 것은 매일의 값이 아니라 분기 단위 궤적이다.
    """
    # 행은 tuple이 아니라 list다 — 정규화 직렬화기가 JSON 타입만 받는다.
    picked: dict[str, list] = {}
    for date_text, value in obs:  # newest first — 분기의 첫 등장이 그 분기의 마지막 관측치
        text = str(date_text)[:10]
        try:
            when = dt.date.fromisoformat(text)
        except Exception:
            continue
        key = f"{when.year}Q{(when.month - 1) // 3 + 1}"
        picked.setdefault(key, [key, _trim_number(value)])
    rows = [picked[key] for key in sorted(picked, reverse=True)][:FRED_HISTORY_QUARTERS]
    return list(reversed(rows))


def fetch_fred_data(series_ids: list[str], api_key: str) -> dict:
    """Fetch multiple FRED series. Returns {series_id: {label, observations, latest, prev, change}}."""
    if not api_key or not series_ids:
        return {"ok": False, "reason": "no_api_key" if not api_key else "no_series", "series": {}}

    result: dict[str, dict] = {}
    errors: list[str] = []

    for sid in series_ids:
        try:
            obs = _fetch_fred_one(sid, api_key, limit=FRED_OBSERVATION_LIMIT)
        except urllib.error.HTTPError as exc:
            errors.append(f"{sid}: HTTP {exc.code}")
            continue
        except Exception:
            errors.append(f"{sid}: macro_data_unavailable")
            continue

        if not obs:
            errors.append(f"{sid}: no data")
            continue

        latest_date, latest_val = obs[0]
        prev_date, prev_val = obs[1] if len(obs) >= 2 else (None, None)
        # 전년 대비는 인덱스가 아니라 날짜로 찾는다. obs[12]는 월간 시리즈에서만
        # 1년이고 일간 시리즈(DGS10)에서는 12영업일이라, 표의 "전년 대비"가 사실은
        # 2주 변화였다.
        yoy_date, yoy_val = _observation_a_year_before(obs, latest_date)

        def _f(v):
            try:
                return float(v)
            except Exception:
                return None

        latest = _f(latest_val)
        prev = _f(prev_val)
        yoy = _f(yoy_val)

        unit = change_unit(sid)

        def _delta(base):
            if latest is None or base is None:
                return None
            if unit == "%p":
                return round(latest - base, 4)
            # 수준값은 비율 변화가 뜻이 있다. 지수 포인트 차이를 그대로 내면
            # 읽는 쪽이 퍼센트로 오해한다.
            return round((latest / base - 1.0) * 100, 4) if base else None

        change_mom = _delta(prev)
        change_yoy = _delta(yoy)

        result[sid] = {
            "label": FRED_SERIES_META.get(sid, sid),
            "latestDate": latest_date,
            "latest": latest,
            "prevDate": prev_date,
            "changeMoM": change_mom,
            "yoyDate": yoy_date,
            "changeYoY": change_yoy,
            "changeUnit": unit,
            "observations": obs[:FRED_RECENT_OBSERVATIONS],
            "history": _quarterly_history(obs),
        }

    return {"ok": bool(result), "series": result, "errors": errors}


# ---------------------------------------------------------------------------
# BOK ECOS
# ---------------------------------------------------------------------------

def _bok_date_range(months_back: int = 18) -> tuple[str, str]:
    """Return (start_yyyyMM, end_yyyyMM) covering the last `months_back` months."""
    today = dt.date.today()
    end = today.strftime("%Y%m")
    # Subtract months
    year = today.year
    month = today.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    start = f"{year}{month:02d}"
    return start, end


def _fetch_bok_one(stat_code: str, meta: dict, api_key: str) -> list[tuple[str, str]]:
    """Fetch BOK ECOS series. Returns list of (period_yyyyMM, value) newest first."""
    start, end = _bok_date_range(18)
    cycle = meta.get("cycle", "M")
    item1 = meta.get("item1", "")
    item2 = meta.get("item2", "")

    # Build path: /{api_key}/json/kr/1/20/{stat_code}/{cycle}/{start}/{end}/{item1}/{item2}
    parts = [BOK_BASE, api_key, "json", "kr", "1", "20", stat_code, cycle, start, end]
    if item1:
        parts.append(item1)
    if item2:
        parts.append(item2)
    url = "/".join(parts)

    req = urllib.request.Request(url, headers={"User-Agent": "MarketResearchArchive/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    rows = data.get("StatisticSearch", {}).get("row", [])
    if not rows:
        # BOK returns error in a different key when it fails
        err = data.get("RESULT", {})
        code = err.get("CODE", "")
        msg = err.get("MESSAGE", "")
        raise ValueError(f"BOK API error {code}: {msg}")

    # Sort newest first by TIME (yyyyMM)
    pairs = [(r["TIME"], r["DATA_VALUE"]) for r in rows if r.get("DATA_VALUE") not in (None, "", " ")]
    pairs.sort(key=lambda x: x[0], reverse=True)
    return pairs


def fetch_bok_data(series_ids: list[str], api_key: str) -> dict:
    """Fetch multiple BOK ECOS series."""
    if not api_key or not series_ids:
        return {"ok": False, "reason": "no_api_key" if not api_key else "no_series", "series": {}}

    result: dict[str, dict] = {}
    errors: list[str] = []

    for sid in series_ids:
        meta = BOK_SERIES_META.get(sid)
        if not meta:
            errors.append(f"{sid}: unknown stat code")
            continue
        try:
            obs = _fetch_bok_one(sid, meta, api_key)
        except Exception:
            errors.append(f"{sid}: macro_data_unavailable")
            continue

        if not obs:
            errors.append(f"{sid}: no data")
            continue

        latest_period, latest_val = obs[0]
        prev_period, prev_val = obs[1] if len(obs) >= 2 else (None, None)
        yoy_period, yoy_val = obs[12] if len(obs) >= 13 else (None, None)

        def _f(v):
            try:
                return float(v.replace(",", "")) if v else None
            except Exception:
                return None

        latest = _f(latest_val)
        prev = _f(prev_val)
        yoy = _f(yoy_val)
        change_mom = round(latest - prev, 4) if latest is not None and prev is not None else None
        change_yoy = round(latest - yoy, 4) if latest is not None and yoy is not None else None

        result[sid] = {
            "label": meta["label"],
            "latestPeriod": latest_period,
            "latest": latest,
            "prevPeriod": prev_period,
            "changeMoM": change_mom,
            "yoyPeriod": yoy_period,
            "changeYoY": change_yoy,
            "observations": obs[:6],
        }

    return {"ok": bool(result), "series": result, "errors": errors}


# ---------------------------------------------------------------------------
# Combined fetch
# ---------------------------------------------------------------------------

def fetch_macro_data(
    fred_series: list[str],
    bok_series: list[str],
    fred_key: str,
    bok_key: str,
) -> dict:
    cache_root = data_dir() / "provider-cache" / "macro"
    return fetch_macro_data_cached(
        cache_root=cache_root,
        fred_series=fred_series,
        bok_series=bok_series,
        fred_fetcher=(lambda: fetch_fred_data(fred_series, fred_key)) if fred_series and fred_key else None,
        bok_fetcher=(lambda: fetch_bok_data(bok_series, bok_key)) if bok_series and bok_key else None,
    )


# ---------------------------------------------------------------------------
# Markdown formatter
# ---------------------------------------------------------------------------

def _fmt(v, digits=2):
    if v is None:
        return "-"
    return f"{v:.{digits}f}"


def _chg(v, unit=""):
    if v is None:
        return "-"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}{unit}"


def macro_data_to_markdown(macro: dict) -> str:
    if not macro.get("ok"):
        return "경제 지표 데이터 없음 (FRED_API_KEY / BOK_API_KEY를 설정에서 입력하세요)"

    lines: list[str] = []

    fred = macro.get("fred", {})
    if fred.get("ok") and fred.get("series"):
        lines += [
            "### 미국 경제 지표 (FRED)",
            "",
            "| 지표 | 최근값 | 기준일 | 직전 관측치 대비 | 1년 전 대비 |",
            "| --- | ---: | --- | ---: | ---: |",
        ]
        for sid, d in fred["series"].items():
            unit = d.get("changeUnit") or ""
            lines.append(
                f"| {d['label']} | {_fmt(d.get('latest'))} | {d.get('latestDate', '-')} "
                f"| {_chg(d.get('changeMoM'), unit)} | {_chg(d.get('changeYoY'), unit)} |"
            )
        history_lines = []
        for sid, d in fred["series"].items():
            rows = d.get("history") or []
            if len(rows) < 4:
                continue
            body = " | ".join(f"{period} {value}" for period, value in rows)
            history_lines.append(f"- {d['label']}: {body}")
        if history_lines:
            lines += [
                "",
                "**분기별 추이 (각 분기 마지막 관측치)** — 과거 국면과 현재 수준을 비교할 때 쓰세요.",
                "",
                *history_lines,
            ]
        if fred.get("errors"):
            lines.append(f"\n> FRED 조회 실패: {', '.join(fred['errors'][:3])}")
        lines.append("")

    bok = macro.get("bok", {})
    if bok.get("ok") and bok.get("series"):
        lines += [
            "### 한국 경제 지표 (BOK ECOS)",
            "",
            "| 지표 | 최근값 | 기준월 | 전기 대비 | 전년 대비 |",
            "| --- | ---: | --- | ---: | ---: |",
        ]
        for sid, d in bok["series"].items():
            lines.append(
                f"| {d['label']} | {_fmt(d.get('latest'))} | {d.get('latestPeriod', '-')} "
                f"| {_chg(d.get('changeMoM'))} | {_chg(d.get('changeYoY'))} |"
            )
        if bok.get("errors"):
            lines.append(f"\n> BOK 조회 실패: {', '.join(bok['errors'][:3])}")
        lines.append("")

    return "\n".join(lines) if lines else "경제 지표 데이터 없음"
