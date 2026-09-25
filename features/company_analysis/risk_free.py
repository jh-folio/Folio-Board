"""무위험수익률 조회 — DCF에 주입할 살아 있는 10년 국채 수익률.

`dcf.py`의 통화별 상수는 실측(2026-08-27)으로 다섯 통화 전부 낮은 쪽으로 틀려 있었다
(−0.05~−0.58%p). 오차가 한 방향이면 노이즈가 아니라 편향이고, 낮은 무위험수익률은
할인율을 낮춰 내재가치를 높인다 — 실측 USD 0.46%p 차이가 내재가치를 5.0~7.2% 움직였다.

경계 (계획 §9.2·§9.5, 2026-08-29 리뷰 반영):

- **조회는 이 모듈이 하고 `dcf.py`는 주입받는다.** DCF는 순수 함수로 남아 테스트가
  쉽고, 조회 실패가 DCF를 죽이지 않는다 — 값을 못 얻으면 `None`을 돌려주고 상수로
  내려가며 `riskFreeSource`가 그 사실을 밝힌다.
- **USD만 조회한다.** 비USD OECD 계열은 월간이고 최신 관측이 9개월 뒤처져 있어
  (실측 2025-11) 지어낸 상수보다 나은지 판단이 서지 않았다. 쓰기로 결정하면 관측일을
  함께 실어야 한다.
- 경로는 `FRED_API_KEY`가 있으면 FRED `DGS10`(일간·공식), 없으면 yfinance `^TNX`
  (키 불필요 — 실측 4.660, 2026-08-27). 키는 `llm_settings.client.fred_api_key()`로
  읽는다 — `os.environ` 직접 조회는 설정 화면이 `.env`에 쓴 키를 못 본다(dotenv 로드가
  그 헬퍼 안에 있다).
- **캐시는 1일 TTL, stale 폴백은 7일까지다.** 무제한 stale은 낡은 금리를 살아 있는
  값처럼 주입한다 — 그것이 이 모듈이 없애려는 편향의 재생산이다. 7일을 넘긴 캐시는
  버리고 상수로 내려간다(다른 provider들의 stale 상한과 같은 눈금).
- **실패도 기록한다(쿨다운 1시간).** 기록하지 않으면 오프라인 환경에서 보고서마다
  FRED 8초 timeout + yfinance 재시도를 두 번씩(두 생성 경로) 다시 치른다.
- **캐시 파일은 `market-cache/` 아래다.** `data/company-analysis/` 바로 밑에 두면
  보고서 목록(`list_analysis_reports`의 `glob("*.json")`)이 캐시를 보고서 카드로
  올린다 — mtime 정렬이라 거의 항상 최신 카드가 된다.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from features.common.utils import read_json, write_json
from features.common.workspace import data_dir
from features.llm_settings.client import fred_api_key

CACHE_TTL_HOURS = 24
STALE_MAX_AGE_DAYS = 7
FAILURE_COOLDOWN_HOURS = 1
# 캐시에 담는 항목이 늘면 올린다(`MARKET_CACHE_SHAPE`와 같은 이유 — 안 올리면 옛
# 모양의 캐시가 TTL까지 조용히 내려온다).
CACHE_SHAPE = 1
# 10년 국채 수익률의 정상 범위. 밖이면 provider 응답이 깨진 것이니 버린다.
_SANE_RANGE = (0.001, 0.20)


def _cache_path() -> Path:
    return data_dir() / "company-analysis" / "market-cache" / "risk-free.json"


def _sane(rate) -> float | None:
    try:
        value = float(rate)
    except (TypeError, ValueError):
        return None
    return value if _SANE_RANGE[0] <= value <= _SANE_RANGE[1] else None


def _age(now: dt.datetime, stamp: str | None) -> dt.timedelta | None:
    try:
        return now - dt.datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None


def _fetch_fred_dgs10(api_key: str) -> tuple[float, str] | None:
    """(수익률, 관측일). 관측일이 있어야 주말·휴일에 `asOf`가 거짓말하지 않는다."""
    import requests

    response = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": "DGS10",
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": "10",
        },
        timeout=8.0,
    )
    response.raise_for_status()
    for row in response.json().get("observations") or []:
        value = row.get("value")
        if value not in (None, "", "."):
            rate = _sane(float(value) / 100.0)
            if rate is not None:
                return rate, str(row.get("date") or "")
    return None


def _fetch_tnx() -> tuple[float, str] | None:
    import yfinance as yf

    history = yf.Ticker("^TNX").history(period="5d")
    if history is None or getattr(history, "empty", True):
        return None
    closes = [value for value in history.get("Close", []) if value == value]  # NaN 제외
    if not closes:
        return None
    rate = _sane(closes[-1] / 100.0)
    if rate is None:
        return None
    try:
        observed = str(history.index[-1].date())
    except Exception:
        observed = ""
    return rate, observed


def _from_cache(cached: dict, *, prefix: str = "") -> dict:
    return {
        # 문자열 rate가 든 캐시가 그대로 나가면 `rf + beta*erp`에서 TypeError로
        # 분석 전체가 죽는다. 저장값이 아니라 강제 변환값을 돌려준다.
        "rate": _sane(cached.get("rate")),
        "source": prefix + str(cached.get("source") or "cache"),
        "asOf": cached.get("asOf"),
        "observedAt": cached.get("observedAt"),
    }


def current_risk_free(currency: str = "USD") -> dict | None:
    """살아 있는 무위험수익률. 못 얻으면 None — 호출자는 상수로 내려간다.

    반환: {"rate", "source", "asOf", "observedAt"}. `rate`는 소수(0.0466)다.
    """
    # 네트워크·실캐시 가드가 **맨 위다.** 캐시 읽기 뒤에 두면 테스트가 개발자
    # 워크스페이스의 실캐시를 읽어 DCF 수치가 머신마다 달라진다(로컬 통과·CI 실패).
    # market_universe와 같은 자리·같은 이유. 단위 테스트는 PYTEST_CURRENT_TEST를
    # 지우고 fetcher를 스텁해서 아래 로직을 검증한다.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    if str(currency or "USD").upper() != "USD":
        return None

    now = dt.datetime.now(dt.timezone.utc)
    cached = read_json(_cache_path(), None)
    if isinstance(cached, dict) and int(cached.get("shape") or 0) >= CACHE_SHAPE:
        age = _age(now, cached.get("asOf"))
        if age is not None and age < dt.timedelta(hours=CACHE_TTL_HOURS) and _sane(cached.get("rate")) is not None:
            return _from_cache(cached)
        # 실패 쿨다운 — 방금 실패했으면 네트워크를 다시 때리지 않고 stale/None으로 답한다.
        failed_age = _age(now, cached.get("failedAt"))
        if failed_age is not None and failed_age < dt.timedelta(hours=FAILURE_COOLDOWN_HOURS):
            return _stale_or_none(cached, now)
    else:
        cached = None

    fetched: tuple[float, str] | None = None
    source = None
    api_key = fred_api_key()
    if api_key:
        try:
            fetched, source = _fetch_fred_dgs10(api_key), "fred_DGS10"
        except Exception:
            fetched = None
    if fetched is None:
        try:
            fetched, source = _fetch_tnx(), "yfinance_^TNX"
        except Exception:
            fetched = None

    if fetched is None:
        # 실패를 기록해 다음 호출이 쿨다운을 타게 한다. 기존 stale 값은 보존한다.
        marker = dict(cached or {})
        marker.update({"shape": CACHE_SHAPE, "failedAt": now.isoformat()})
        _write_cache(marker)
        return _stale_or_none(cached, now)

    rate, observed = fetched
    payload = {
        "shape": CACHE_SHAPE,
        "rate": round(rate, 5),
        "source": source,
        "asOf": now.isoformat(),
        "observedAt": observed,
    }
    _write_cache(payload)
    return {"rate": payload["rate"], "source": source, "asOf": payload["asOf"], "observedAt": observed}


def _stale_or_none(cached: dict | None, now: dt.datetime) -> dict | None:
    """조회 실패 시의 폴백. **나이 상한이 있다** — 무제한 stale은 낡은 금리를 살아
    있는 값처럼 주입해, 이 모듈이 없애려는 편향을 되살린다."""
    if not cached or _sane(cached.get("rate")) is None:
        return None
    age = _age(now, cached.get("asOf"))
    if age is None or age > dt.timedelta(days=STALE_MAX_AGE_DAYS):
        return None
    return _from_cache(cached, prefix="stale_")


def _write_cache(payload: dict) -> None:
    try:
        write_json(_cache_path(), payload)
    except Exception:
        pass  # 캐시 실패가 값 자체를 버리게 하지 않는다


__all__ = ["current_risk_free", "CACHE_TTL_HOURS", "STALE_MAX_AGE_DAYS", "FAILURE_COOLDOWN_HOURS"]
