from __future__ import annotations

from features.common.canonical_identity import BRIEFING_KIND_SUFFIXES
from features.common.change_intelligence.basis import content_hash, normalize_basis, stable_id
from features.common.markets import PRODUCT_MARKETS
from features.common.research_schema.data_gaps import data_gap_rows


# 자산마다 평범한 하루의 크기가 다르므로 같은 %를 같은 변화로 재면 변동성 자산이
# 매일 상단을 차지한다(예전 눈금은 2.25% 이동이면 곧 major라 유가·VIX가 수시로 넘었다).
# 눈금은 자산군별로 둔다 — 종목마다 정밀하게 맞추려면 표본이 필요한데 저장된 브리핑
# 23건(2026-06~08)뿐이라 그 표에 맞추면 표본의 잔떨림까지 배운다. 대신 그 실측으로
# 검증한다: 각 지표의 일간 |등락률| **중앙값이 deadband 안에 들어와** 평범한 하루가
# 0이 되는지 본다(SPY 0.72%·^VIX 2.54%·CL=F 2.47%·^TNX 0.54%·BTC 0.78% 모두 통과).
# (deadband, scale) — deadband 이하는 0, deadband+scale에서 1.0.
_METRIC_DELTA_CLASSES = {
    "index": (0.005, 0.030),      # 주가지수·광의 ETF: 2% 이동 = 0.50
    "credit": (0.003, 0.015),     # 채권·신용 ETF
    "rate": (0.010, 0.050),       # 금리(수준값이라 %가 작다)
    "fx": (0.003, 0.012),
    "commodity": (0.015, 0.050),
    "volatility": (0.050, 0.200),  # VIX는 두 자릿수 % 이동이 평범하다
    "crypto": (0.020, 0.060),
}
_METRIC_CLASS_BY_ID = {
    "SPY": "index", "QQQ": "index", "IWM": "index", "RSP": "index",
    "KOSPI": "index", "KOSDAQ": "index", "KOSPI200": "index",
    "TLT": "credit", "HYG": "credit", "LQD": "credit",
    "^TNX": "rate", "DX-Y.NYB": "fx", "USDKRW": "fx",
    "CL=F": "commodity", "GC=F": "commodity",
    "^VIX": "volatility", "BTC-USD": "crypto",
}


def _metric_delta_spec(metric_id: str) -> dict:
    """모르는 지표는 주가지수 눈금을 쓴다. 눈금을 모른다고 변화를 크게 잡으면
    지표가 하나 늘 때마다 피드가 시끄러워진다."""
    deadband, scale = _METRIC_DELTA_CLASSES[_METRIC_CLASS_BY_ID.get(str(metric_id), "index")]
    return {"relative": True, "scale": scale, "deadband": deadband}


def _briefing_kind(report: dict) -> str:
    """`daily` 또는 `weekly`. 저장된 옛 보고서에는 이 값이 없고 그때는 일간이다."""
    value = str((report or {}).get("kind") or "").strip().lower()
    return value if value in BRIEFING_KIND_SUFFIXES else "daily"


def _briefing_artifact_id(report: dict, scope: str) -> str:
    """Briefings are stored per market, so the id has to carry the market too.

    A bare date collides in the projection's ``(artifact_kind, artifact_id)`` key —
    the KR commit would overwrite the US change event — and leaves the Change Feed
    unable to tell which briefing to open.

    **종류도 같은 이유로 실린다.** 주간 보고서의 `date`는 발행일이라 그날이 세션일인
    일간 보고서와 값이 같다. 종류가 없으면 평일에 낸 주간이 그날 일간의 변화 이벤트를
    덮어써서, Change Feed가 일간 자리에 주간 내용을 보여주고 잘못된 보고서를 연다.
    """
    base = str(report.get("id") or report.get("date") or "").strip()
    if not base:
        return base
    # **종류 접미사를 먼저 뗀다.** 안 떼면 이미 `.weekly`로 끝나는 id가 "시장 접미사가
    # 없다"로 읽혀 `2026-08-20.us.weekly.us.weekly`가 된다.
    for suffix in BRIEFING_KIND_SUFFIXES:
        if base.endswith(f".{suffix}"):
            base = base[: -len(suffix) - 1]
            break
    markets = {market.value.lower() for market in PRODUCT_MARKETS}
    if scope in markets and not base.endswith(f".{scope}"):
        base = f"{base}.{scope}"
    kind = _briefing_kind(report)
    return base if kind == "daily" else f"{base}.{kind}"


def build_briefing_basis(report: dict, *, generation_docs: list[dict] | None = None) -> dict:
    report = report or {}
    docs = generation_docs or report.get("sources") or []
    refs = []
    for index, doc in enumerate(docs[:32], 1):
        if not isinstance(doc, dict):
            continue
        refs.append({
            "id": doc.get("id") or doc.get("sourceId") or stable_id("briefsrc", doc.get("url") or doc.get("path"), index),
            "title": doc.get("title"), "url": doc.get("url"), "path": doc.get("path"),
            "source": doc.get("source"), "sourceType": doc.get("sourceType") or doc.get("source_type") or "news",
            "reliabilityTier": doc.get("reliabilityTier") or doc.get("reliability_tier") or 2,
            "independentGroup": doc.get("publisherGroup") or doc.get("source"),
            "intakeStage": doc.get("intakeStage") or doc.get("intake_stage") or "evidence",
            "signalStatus": doc.get("signalStatus") or doc.get("signal_status"),
            "publishedAt": doc.get("publishedAt") or doc.get("date"),
            "contentHash": doc.get("contentHash") or content_hash({"title": doc.get("title"), "summary": doc.get("summary"), "url": doc.get("url")}),
        })
    ref_ids = [row["id"] for row in refs]

    def _own_ref_ids(rows: list[dict], fallback: list[str]) -> list[str]:
        """topDocs와 url/path/제목이 일치하는 ref만 그 단위의 근거로 잇는다.

        모든 단위가 같은 상위 N건을 가리키면 "이 변화의 근거"가 성립하지 않는다.
        일치하는 ref가 없을 때만 전체 상위 목록으로 대신한다.
        """
        matched = []
        for doc in rows or []:
            if not isinstance(doc, dict):
                continue
            for ref in refs:
                keys = {value for value in (doc.get("url"), doc.get("path"), doc.get("title")) if value}
                if keys & {ref.get("url"), ref.get("path"), ref.get("title")} and ref["id"] not in matched:
                    matched.append(ref["id"])
        return matched or fallback

    units = []
    drivers = [row for row in report.get("marketDrivers") or [] if isinstance(row, dict)]
    # A driver score is an unbounded sum of document scores, so its absolute value
    # says nothing on its own and wobbles between two runs of the same day. Compare
    # rank and share of the day's total weight instead: bounded, and a change in
    # either actually means the day's driver mix moved.
    total_score = sum(abs(float(row.get("score") or 0)) for row in drivers)
    for rank, driver in enumerate(drivers, 1):
        subject = driver.get("driver") or driver.get("title")
        score = abs(float(driver.get("score") or 0))
        share = round(score / total_score, 2) if total_score else 0.0
        top_docs = [row for row in driver.get("topDocs") or [] if isinstance(row, dict)]
        units.append({
            "id": stable_id("driver", report.get("marketScope"), subject), "kind": "market_driver",
            "subject": subject, "currentValue": {"rank": rank, "share": share, "docCount": int(driver.get("docCount") or 0)},
            "direction": "active", "magnitude": share or 0.2,
            # 동인 이름은 고정 어휘라 정체성이 날마다 이어진다. 변화의 크기는
            # 그날의 비중이 아니라 직전 대비 비중 이동이다(0.5 이동 = 1.0).
            "delta": {"field": "share", "scale": 0.5},
            "horizon": "short_term", "sourceRefIds": _own_ref_ids(top_docs, ref_ids[:12]),
            # 의미 비교(전/후 내용 대조)의 입력. 제목만 담고 본문은 담지 않는다.
            "contextDocs": [str(row.get("title") or "") for row in top_docs if row.get("title")],
        })
    for issue in (report.get("issueCoverage") or [])[:8]:
        if isinstance(issue, dict):
            issue_docs = [row for row in issue.get("topDocs") or [] if isinstance(row, dict)]
            units.append({
                "id": stable_id("issue", issue.get("market"), issue.get("issueId") or issue.get("title")),
                "kind": "issue_coverage", "subject": issue.get("title") or issue.get("issueId"),
                "currentValue": {"market": issue.get("market"), "impact": issue.get("marketImpactStatus")},
                "direction": "observed", "magnitude": 0.35, "horizon": "short_term",
                # `issueId`는 그 클러스터의 문서 집합 해시라 기사 한 건만 달라져도
                # 값이 바뀐다. 즉 이슈 목록은 매일 통째로 새로 뽑히는 집합이고,
                # 그 등장·퇴장은 변화의 크기가 아니다. 내용이 달라졌는지는
                # 의미 비교(semantic.py)가 대표 기사 제목으로 판정한다.
                "continuity": "churning",
                "sourceRefIds": _own_ref_ids(issue_docs, ref_ids[:8]),
                "contextDocs": [str(row.get("title") or "") for row in issue_docs if row.get("title")],
            })
    metrics = []
    for item in (report.get("marketTape") or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        metric_id = item.get("id") or item.get("symbol") or item.get("label")
        value = item.get("value") if item.get("value") is not None else item.get("close")
        metrics.append({"id": metric_id, "value": value, "status": item.get("status"), "asOf": item.get("asOf")})
        if metric_id and value is not None:
            units.append({
                "id": stable_id("tape", metric_id), "kind": "market_metric", "subject": metric_id,
                # 종가는 매일 다르므로 값이 달라진 사실 자체는 변화가 아니다.
                # 크기는 전적으로 직전 값과의 차이가 정한다(`delta`). 지표가 목록에
                # 처음 등장하거나 사라지는 것은 provider 사정이지 시장의 변화가
                # 아니므로, 비교할 직전 값이 없을 때 쓰는 이 기본값은 0이다.
                "currentValue": value, "direction": "observed", "magnitude": 0.0,
                "delta": _metric_delta_spec(metric_id),
                "horizon": "short_term", "sourceRefIds": ref_ids[:4],
            })
    counter = [gap.get("message") or gap.get("title") for gap in data_gap_rows(report.get("dataGaps"))]
    scope = str(report.get("marketScope") or "both").strip().lower() or "both"
    # **계보에도 종류가 들어간다.** `select_report_baseline`은 같은 계보에서 가장 최근의
    # 다른 artifact를 기준선으로 고르는데, 종류가 없으면 주간이 직전 일간을 기준선으로
    # 잡고 — 더 나쁘게는 — 그다음 일간이 그 주간을 기준선으로 잡는다. 한 주의 동인 집합과
    # 하루의 동인 집합을 비교한 결과가 Change Feed에 실린다.
    kind = _briefing_kind(report)
    lineage = f"briefing:{scope}" if kind == "daily" else f"briefing:{scope}:{kind}"
    return normalize_basis({
        "artifactKind": "briefing", "artifactId": _briefing_artifact_id(report, scope),
        "lineageId": lineage, "scope": {"market": scope},
        "asOf": report.get("generatedAt") or report.get("date"), "changeUnits": units,
        "sourceRefs": refs, "counterSignals": [], "uncertainties": counter, "metrics": metrics,
        "coverage": {"comparison": 1 if units else 0, "market": 1 if metrics else 0},
    })
