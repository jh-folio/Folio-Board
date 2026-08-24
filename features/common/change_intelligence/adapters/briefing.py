from __future__ import annotations

from features.common.canonical_identity import BRIEFING_KIND_SUFFIXES
from features.common.change_intelligence.basis import content_hash, normalize_basis, stable_id
from features.common.markets import PRODUCT_MARKETS
from features.common.research_schema.data_gaps import data_gap_rows


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
                "currentValue": value, "direction": "observed", "magnitude": min(1.0, abs(float(item.get("changePct") or 0)) / 5),
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
