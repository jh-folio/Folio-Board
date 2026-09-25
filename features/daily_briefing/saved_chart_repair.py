"""Explicit maintenance of a selected saved KR report; never run on reads."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, time
from zoneinfo import ZoneInfo

from features.common.market_data.price_history import build_price_history
from features.daily_briefing.finalize import finalize_briefing_candidate
from features.daily_briefing.reader_hygiene import strip_provider_operational_notes
from features.daily_briefing.visuals import _price_snapshot


def repair_saved_kr_company_charts(report: dict, *, price_fetcher=None) -> dict:
    """Return a candidate only; caller owns backup, concurrency and commit.

    Keep the report's session, company identities, non-company visuals,
    sources and author unchanged. No generator or sidecar writer is invoked.
    """
    if report.get("marketScope") != "kr" or report.get("kind", "daily") != "daily":
        raise ValueError("saved_chart_repair_requires_kr_daily")
    fetch = price_fetcher or build_price_history
    candidate = deepcopy(report)
    expected_body, _ = strip_provider_operational_notes(str(report.get("markdown") or ""))
    repaired = 0
    for snapshot in candidate.get("visualSnapshots") or []:
        if snapshot.get("role") != "leading_company":
            continue
        if snapshot.get("market") != "KR" or len(snapshot.get("series") or []) != 1:
            raise ValueError("saved_chart_repair_identity_invalid")
        session = str(snapshot.get("marketSessionDate") or "")
        if session != str(report.get("sessionDate") or report.get("date") or ""):
            raise ValueError("saved_chart_repair_session_mismatch")
        series = snapshot["series"][0]
        subject = snapshot.get("subject") or {}
        symbol = str(series.get("providerSymbol") or "")
        if not symbol or series.get("ticker") != subject.get("ticker"):
            raise ValueError("saved_chart_repair_identity_invalid")
        history = fetch(symbol, session)
        points = (history.get("intraday") or {}).get("points") or []
        daily = (history.get("daily") or {}).get("points") or []
        if not points or not daily or str(daily[-1].get("time")) != session:
            raise ValueError("saved_chart_repair_history_unavailable")
        if (history.get("intraday") or {}).get("interval") != "5m":
            raise ValueError("saved_chart_repair_interval_invalid")
        for point in points:
            stamp = datetime.fromisoformat(str(point.get("time") or "").replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("saved_chart_repair_timezone_missing")
            local = stamp.astimezone(ZoneInfo("Asia/Seoul"))
            if (local.date().isoformat() != session
                    or not time(9) <= local.time() < time(15, 30)
                    or local.minute % 5 or local.second):
                raise ValueError("saved_chart_repair_non_regular_candle")
        fixed_series = {**series, **history}
        snapshot.update(_price_snapshot(
            snapshot["id"], "kr", "leading_company", session,
            [subject], [fixed_series], [], subject=subject,
        ))
        repaired += 1
    if not repaired:
        raise ValueError("saved_chart_repair_no_company_chart")
    result = finalize_briefing_candidate(candidate, allow_repair=False)
    if result["markdown"] != expected_body or result.get("generation") != report.get("generation"):
        raise ValueError("saved_chart_repair_unexpected_body_change")
    return result
