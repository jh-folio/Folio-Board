from __future__ import annotations

from features.common.change_intelligence.basis import content_hash, normalize_basis, stable_id


def build_market_memory_basis(snapshot: dict) -> dict:
    snapshot = snapshot or {}
    refs = []
    for index, row in enumerate(snapshot.get("sourceRefs") or [], 1):
        if isinstance(row, dict):
            refs.append({
                "id": row.get("id") or row.get("sourceId") or stable_id("mmsrc", row.get("url") or row.get("path"), index),
                "title": row.get("title"), "url": row.get("url"), "path": row.get("path"), "source": row.get("source"),
                "sourceType": row.get("sourceType") or row.get("type") or "news", "reliabilityTier": row.get("reliabilityTier") or row.get("sourcePriority") or 2,
                "independentGroup": row.get("independentGroup") or row.get("source"), "intakeStage": row.get("intakeStage") or "evidence",
                "signalStatus": row.get("signalStatus"), "publishedAt": row.get("date") or row.get("publishedAt"),
                "contentHash": row.get("contentHash") or content_hash({"title": row.get("title"), "url": row.get("url")}),
            })
    ref_ids = [row["id"] for row in refs]
    units = [{
        "id": stable_id("regime", snapshot.get("horizon")), "kind": "market_regime", "subject": "시장 국면",
        # 국면 자체가 바뀌는 것은 중대하다. 크기를 confidence로 두던 시절에는
        # "이 판단을 얼마나 확신하는가"가 "얼마나 달라졌는가" 자리에 들어가 있었다.
        "currentValue": snapshot.get("marketRegime"), "direction": "state", "magnitude": 0.85,
        "horizon": snapshot.get("horizon") or "medium_term", "sourceRefIds": ref_ids[:12],
    }]
    for index, driver in enumerate(snapshot.get("keyDrivers") or [], 1):
        if isinstance(driver, dict):
            subject = driver.get("title") or driver.get("driver") or driver.get("text") or driver.get("id")
            units.append({
                "id": driver.get("id") or stable_id("mmdriver", subject, index), "kind": "market_driver", "subject": subject,
                # `summary`는 매 스냅샷 다시 쓰이는 LLM 산문이라 hash 비교에 넣으면
                # 같은 판단을 달리 표현한 것만으로 모든 드라이버가 매번 changed가 된다.
                # 내용이 실제로 달라졌는지는 의미 비교가 이 문장으로 판정한다.
                "currentValue": {key: driver.get(key) for key in ("direction", "confidence") if driver.get(key) is not None},
                "contextDocs": [str(driver.get("summary"))] if driver.get("summary") else [],
                "direction": driver.get("direction") or "active",
                "magnitude": float(driver.get("confidence") or snapshot.get("confidence") or 0.5),
                # 드라이버 목록은 스냅샷마다 LLM이 다시 뽑는 집합이다. 등장·퇴장이
                # 아니라 방향·확신도가 움직인 것만 변화의 크기로 센다.
                "continuity": "churning", "delta": {"field": "confidence", "scale": 0.5},
                "horizon": snapshot.get("horizon") or "medium_term", "sourceRefIds": driver.get("sourceRefIds") or ref_ids[:8],
            })
    return normalize_basis({
        "artifactKind": "market_memory", "artifactId": snapshot.get("id"),
        "lineageId": f"market_memory:{(snapshot.get('marketScope') or 'both')}:{snapshot.get('horizon') or 'medium_term'}",
        "scope": {"market": snapshot.get("marketScope") or "both", "horizon": snapshot.get("horizon") or "medium_term"},
        "asOf": snapshot.get("asOf"), "changeUnits": units, "sourceRefs": refs,
        "counterSignals": snapshot.get("counterEvidence") or [], "uncertainties": snapshot.get("uncertainties") or [],
        "metrics": [{"id": "confidence", "value": snapshot.get("confidence")}],
        "coverage": {"comparison": 1 if snapshot.get("marketRegime") or snapshot.get("keyDrivers") else 0, "market": 1},
    })
