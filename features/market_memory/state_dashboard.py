from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from features.market_memory.market_state_ref import MarketStateRefQuery, resolve_market_state_ref
from features.market_memory.memory import connect, init_db, list_states
from features.market_memory.snapshot import MARKET_VIEW_KEYS, current_market_state_snapshot, scrub_inline_refs
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[2]
MARKET_MEMORY_DB_PATH = data_dir() / "market-memory.sqlite3"

MOMENTUM_LABELS = {
    "strengthening": "강화",
    "stable": "유지",
    "fading": "약화",
    "turning": "전환",
    "conflicted": "혼재",
}

RISK_WORDS = ("금리", "달러", "국채", "유가", "에너지", "중동", "리스크", "인플레이션", "긴축")
SUPPORT_WORDS = ("AI", "반도체", "전력", "수출", "실적", "공급망", "데이터센터", "성장")


def _latest_memory_meta(db_path: str | Path) -> dict:
    conn = connect(db_path)
    try:
        init_db(conn)
        row = conn.execute(
            """
            SELECT memory_id, as_of, created_at, title
            FROM market_memory
            WHERE source_kind = 'agent'
            ORDER BY COALESCE(created_at, as_of, date) DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {}
    return {
        "id": row["memory_id"],
        "asOf": row["as_of"] or "",
        "createdAt": row["created_at"] or "",
        "title": row["title"] or "",
    }


def _attach_freshness(payload: dict, db_path: str | Path) -> dict:
    meta = _latest_memory_meta(db_path)
    snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
    snapshot_as_of = str(snapshot.get("asOf") or "")
    latest_at = str(meta.get("createdAt") or meta.get("asOf") or "")
    ref = payload.get("marketStateRef") if isinstance(payload.get("marketStateRef"), dict) else {}
    payload["freshness"] = {
        "status": ref.get("status"),
        "reason": ref.get("freshnessReason"),
        "asOf": ref.get("asOf"),
        "sourceKind": ref.get("sourceKind"),
        "resolvedAt": ref.get("resolvedAt"),
        "snapshotAsOf": snapshot_as_of,
        "latestMemoryAt": latest_at,
        "latestMemoryTitle": meta.get("title", ""),
        "stale": ref.get("status") == "stale",
    }
    return payload


def confidence_label(value) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def _confidence_pct(value) -> int:
    try:
        return max(0, min(100, int(round(float(value) * 100))))
    except (TypeError, ValueError):
        return 0


def _checkpoint_text(state: dict) -> str:
    for item in state.get("nextCheckpoints") or []:
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict):
            text = str(item.get("item") or item.get("label") or item.get("checkpoint") or item.get("description") or "").strip()
            if text:
                return text
    return ""


def _watch_items(drivers: list[dict], *, limit: int = 3) -> list[str]:
    items: list[str] = []
    for driver in drivers:
        checkpoint = str(driver.get("nextCheckpoint") or "").strip()
        if checkpoint and checkpoint not in items:
            items.append(checkpoint)
        if len(items) >= limit:
            break
    return items


def _posture(drivers: list[dict]) -> dict:
    if not drivers:
        return {
            "label": "대기",
            "tone": "wait",
            "summary": "RSS 수집과 Market Memory 정리를 먼저 실행한 뒤 판단하세요.",
        }
    momentum_values = [str(driver.get("momentum") or "stable") for driver in drivers]
    caution_count = sum(1 for value in momentum_values if value in {"fading", "turning", "conflicted"})
    strengthening_count = sum(1 for value in momentum_values if value == "strengthening")
    high_confidence_count = sum(1 for driver in drivers if driver.get("confidence") == "high")
    if caution_count >= 2:
        return {
            "label": "방어적",
            "tone": "defensive",
            "summary": "새 포지션 확대보다 리스크 점검과 다음 데이터 확인이 우선입니다.",
        }
    if strengthening_count >= 2 and high_confidence_count >= 1:
        return {
            "label": "선별적",
            "tone": "selective",
            "summary": "핵심 흐름은 살아 있지만, 추격보다 확인된 수혜와 반대 근거를 함께 점검하세요.",
        }
    if strengthening_count >= 1:
        return {
            "label": "관찰",
            "tone": "watch",
            "summary": "선별적 관찰 구간입니다. 강한 드라이버는 유지하되 약한 축의 변화를 확인하세요.",
        }
    return {
        "label": "대기",
        "tone": "wait",
        "summary": "뚜렷한 방향성보다 관찰이 우선입니다. 다음 체크포인트 확인 전까지 판단을 보류하세요.",
    }


def _stance_text(drivers: list[dict]) -> str:
    return _posture(drivers)["summary"]


def _plain_conclusion(posture: dict) -> str:
    label = posture.get("label")
    if label == "방어적":
        return "시장이 흔들릴 가능성이 크니, 당분간 방어적으로 보는 게 좋습니다."
    if label == "선별적":
        return "시장이 나쁘지는 않지만, 아무 종목이나 따라 살 장은 아닙니다."
    if label == "관찰":
        return "방향이 아직 분명하지 않으니, 새 결정을 서두르지 않는 편이 좋습니다."
    if label == "공격적":
        return "시장 분위기는 좋지만, 너무 비싸게 사지 않는지 함께 봐야 합니다."
    return "아직 판단할 자료가 부족합니다. 먼저 최신 뉴스와 시장 흐름을 더 모아야 합니다."


def _action_guide(posture: dict) -> dict:
    label = posture.get("label")
    if label == "방어적":
        return {
            "headline": "새 매수보다 리스크 점검",
            "action": "보유 종목이 흔들릴 때 버틸 수 있는지 먼저 확인하세요.",
            "timing": "새 매수는 서두르지 말고, 부담 요인이 완화되는지 본 뒤 검토하세요.",
        }
    if label == "선별적":
        return {
            "headline": "좋은 기업만 골라서 천천히 접근",
            "action": "기존 보유 종목은 유지하되, 새 매수는 실적과 수혜가 분명한 기업으로 좁히세요.",
            "timing": "한 번에 따라가기보다 가격이 쉬거나 근거가 추가될 때 분할로 검토하세요.",
        }
    if label == "관찰":
        return {
            "headline": "관망하면서 후보만 정리",
            "action": "지금은 매수보다 관심 기업 목록과 기준 가격을 정리하는 쪽이 낫습니다.",
            "timing": "방향이 확인되는 다음 업데이트 이후 행동을 정하세요.",
        }
    if label == "공격적":
        return {
            "headline": "보유를 유지하며 좋은 기업 찾기",
            "action": "좋은 기업은 계속 보유하고, 새 후보도 열어둘 수 있는 구간입니다.",
            "timing": "다만 급등한 종목은 쉬어갈 때 접근하는 편이 안전합니다.",
        }
    return {
        "headline": "판단 보류",
        "action": "아직 행동을 정하기보다 데이터를 더 모으는 단계입니다.",
        "timing": "RSS 수집과 Market Memory 정리 후 다시 판단하세요.",
    }


def _reason_summary_from_drivers(drivers: list[dict], fallback: str = "") -> str:
    parts: list[str] = []
    for driver in drivers[:3]:
        title = str(driver.get("title") or "").strip()
        reason = str(
            driver.get("evidenceSummary")
            or driver.get("whyItMatters")
            or driver.get("rationale")
            or driver.get("interpretation")
            or ""
        ).strip()
        if title and reason:
            parts.append(f"{title}: {reason}")
        elif reason:
            parts.append(reason)
    return " / ".join(parts) or fallback


def _briefs(summary: str, posture: dict, watch_items: list[str], action_guide: dict, reason_summary: str = "") -> list[dict]:
    action = action_guide.get("action") or posture.get("summary") or ""
    watch = action_guide.get("timing") or "; ".join(watch_items[:3]) or "다음 RSS 수집과 Market Memory 정리에서 새 변화가 있는지 확인합니다."
    return [
        {"label": "현재 판단", "value": summary},
        {"label": "왜 이렇게 보는가", "value": reason_summary},
        {"label": "행동 가이드", "value": action},
        {"label": "다음 확인", "value": watch},
    ]


def _snapshot_posture(snapshot: dict) -> dict:
    guide = snapshot.get("actionGuide") if isinstance(snapshot.get("actionGuide"), dict) else {}
    text = str(snapshot.get("actionPosture") or "").strip()
    regime = str(snapshot.get("marketRegime") or "").lower()
    if any(token in regime for token in ("defensive", "risk_off", "caution")) or any(token in text for token in ("방어", "리스크", "확대보다")):
        label, tone = "방어적", "defensive"
    elif any(token in regime for token in ("selective", "growth")) or any(token in text for token in ("선별", "확인된", "추격보다")):
        label, tone = "선별적", "selective"
    elif any(token in regime for token in ("risk_on", "aggressive")) or "공격" in text:
        label, tone = "공격적", "constructive"
    else:
        label, tone = "관찰", "watch"
    return {"label": label, "tone": tone, "summary": guide.get("action") or text or "주요 드라이버와 반대 근거를 함께 확인하세요."}


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word.lower() in text.lower() for word in words)


def _driver_direction(title: str, text: str, momentum: str) -> dict:
    combined = f"{title} {text}"
    is_risk = _contains_any(combined, RISK_WORDS)
    is_support = _contains_any(combined, SUPPORT_WORDS)
    if is_risk and momentum in {"fading"}:
        return {
            "label": "부담 완화",
            "tone": "support",
            "effect": "시장에는 조금 도움이 됩니다. 부담 요인이 약해지면 투자자들이 위험자산을 더 편하게 볼 수 있습니다.",
        }
    if is_risk and momentum in {"conflicted", "stable"}:
        return {
            "label": "변동성",
            "tone": "mixed",
            "effect": "시장에는 불안 요인입니다. 방향이 한쪽으로 정리되기 전까지 주가가 흔들릴 수 있습니다.",
        }
    if is_risk:
        return {
            "label": "부담",
            "tone": "risk",
            "effect": "주식시장에는 부담입니다. 이 흐름이 강해지면 투자자들이 주식보다 안전한 자산을 선호할 수 있습니다.",
        }
    if is_support and momentum in {"strengthening", "stable"}:
        return {
            "label": "도움",
            "tone": "support",
            "effect": "주식시장에는 도움이 됩니다. 관련 기업의 실적 기대를 받쳐 일부 성장주를 지지할 수 있습니다.",
        }
    if momentum in {"turning", "conflicted"}:
        return {
            "label": "혼재",
            "tone": "mixed",
            "effect": "시장 영향은 아직 섞여 있습니다. 좋은 신호와 부담 신호가 같이 나타나는지 확인해야 합니다.",
        }
    return {
        "label": "중립",
        "tone": "neutral",
        "effect": "시장 방향을 크게 바꾸는 재료라기보다, 다른 흐름과 함께 확인할 보조 요인입니다.",
    }


def _next_memory_check(checkpoint: str, direction: dict) -> str:
    if checkpoint:
        return f"다음 업데이트에서 {checkpoint} 변화가 이 판단을 강화하는지 확인합니다."
    label = direction.get("label") or "이 흐름"
    return f"다음 업데이트에서 이 요인이 실제 시장에 {label}으로 계속 작용하는지 확인합니다."


def summarize_market_state(states: list[dict], *, limit: int = 5) -> dict:
    ranked = sorted(
        states or [],
        key=lambda row: (float(row.get("confidence") or 0), row.get("momentum") == "strengthening"),
        reverse=True,
    )[: int(limit or 5)]
    drivers = []
    for state in ranked:
        title = state.get("stateLabel") or state.get("story") or "시장 내러티브"
        conclusion = str(state.get("conclusion") or "").strip()
        summary_text = str(state.get("summary") or "").strip()
        interpretation = conclusion or summary_text or str(state.get("rationale") or "").strip()
        checkpoint = _checkpoint_text(state)
        direction = _driver_direction(title, f"{interpretation} {summary_text} {state.get('rationale') or ''}", state.get("momentum") or "stable")
        drivers.append({
            "id": state.get("id") or "",
            "title": title,
            "status": state.get("status") or "watch",
            "momentum": state.get("momentum") or "stable",
            "momentumLabel": MOMENTUM_LABELS.get(state.get("momentum"), "유지"),
            "directionLabel": direction["label"],
            "directionTone": direction["tone"],
            "confidence": confidence_label(state.get("confidence")),
            "confidencePct": _confidence_pct(state.get("confidence")),
            # 판단(conclusion)이 카드 헤드라인. 근거·부연은 축소 상세로 내려간다.
            "interpretation": interpretation,
            "marketImpact": direction["effect"],
            "rationale": str(state.get("rationale") or "").strip(),
            "whyItMatters": str(state.get("rationale") or "").strip(),
            "evidenceSummary": str(state.get("rationale") or summary_text or interpretation).strip(),
            "elaboration": summary_text if summary_text and summary_text != interpretation else "",
            "evidenceCounts": {
                "d7": int(state.get("evidenceCount7d") or 0),
                "d30": int(state.get("evidenceCount30d") or 0),
                "d90": int(state.get("evidenceCount90d") or 0),
            },
            "linkedCompanies": [str(t) for t in (state.get("linkedCompanies") or [])[:4]],
            "nextCheckpoint": checkpoint,
            "whatToWatch": checkpoint,
            "nextMemoryCheck": _next_memory_check(checkpoint, direction),
            "askAgentPrompt": f"{title}가 내 포트폴리오에 주는 의미를 설명해줘",
        })
    # 드라이버가 없을 때의 안내는 posture("대기")가 갖는다 — _plain_conclusion과
    # actionGuide가 그 문구를 내므로 여기서 summary를 따로 대입하지 않는다.
    posture = _posture(drivers)
    summary = _plain_conclusion(posture)
    action_guide = _action_guide(posture)
    watch_items = _watch_items(drivers)
    reason_summary = _reason_summary_from_drivers(drivers, posture["summary"])
    return {
        "title": "현재 중기 시장 상황",
        "summary": summary,
        "plainConclusion": summary,
        "reasonSummary": reason_summary,
        "source": "state_fallback",
        "stance": posture["summary"],
        "posture": posture,
        "actionGuide": action_guide,
        "briefs": _briefs(summary, posture, watch_items, action_guide, reason_summary),
        "watchItems": watch_items,
        "drivers": drivers,
        "hiddenInternals": ["taxonomy", "storyMap", "audit", "familySuggestions", "rawEvidence"],
    }


def _snapshot_confidence_label(value) -> str:
    return confidence_label(value)


def _display_source_refs(refs) -> list[dict]:
    out = []
    for ref in refs or []:
        if not isinstance(ref, dict):
            continue
        source_id = str(ref.get("id") or "").strip()
        title = str(ref.get("title") or "").strip()
        source = str(ref.get("source") or "").strip()
        url = str(ref.get("url") or "").strip()
        if source_id.startswith("rss:item:") and title == source_id and not source and not url:
            continue
        if title or source or url:
            out.append(ref)
    return out


def _snapshot_ref_lookup(snapshot: dict) -> dict[str, dict]:
    """저장된 sourceRefs를 id→출처 표로. 본문에 박힌 내부 id를 매체명으로 바꾼다."""
    lookup = {}
    for ref in snapshot.get("sourceRefs") or []:
        if isinstance(ref, dict) and ref.get("id"):
            lookup[str(ref["id"])] = ref
    return lookup


def _dashboard_payload_from_snapshot_view(snapshot: dict, view: dict | None = None) -> dict:
    # 이미 저장된 스냅샷에는 본문에 rss:item:13 같은 내부 id가 남아 있다. 화면에서
    # 다시 걸러야 재생성 없이도 읽을 수 있는 문장이 나온다.
    lookup = _snapshot_ref_lookup(snapshot)
    snapshot = scrub_inline_refs(snapshot, lookup)
    view = scrub_inline_refs(view, lookup) if isinstance(view, dict) else {}
    confidence = _snapshot_confidence_label(snapshot.get("confidence"))
    confidence_pct = _confidence_pct(snapshot.get("confidence"))
    posture = _snapshot_posture(snapshot)
    drivers = []
    watch_items = view.get("watchItems") or snapshot.get("watchItems") or []
    for index, driver in enumerate((view.get("keyDrivers") or snapshot.get("keyDrivers") or [])[:5], 1):
        source_refs = driver.get("sourceRefs") or []
        impact = driver.get("summary") or ""
        why_it_matters = driver.get("whyItMatters") or ""
        # snapshot의 page-level watchItems는 드라이버의 checkpoint가 아니다.
        # 드라이버가 직접 쓴 nextMemoryCheck만 그 카드의 다음 확인으로 노출한다.
        next_memory_check = str(driver.get("nextMemoryCheck") or "").strip()
        direction = _driver_direction(driver.get("title") or "", f"{impact} {why_it_matters}", "agent")
        direction_label = driver.get("directionLabel") or direction["label"]
        direction_tone = driver.get("directionTone") or direction["tone"]
        drivers.append({
            "id": driver.get("id") or f"snapshot-driver:{index}",
            "title": driver.get("title") or "시장 드라이버",
            "status": "current",
            "momentum": "agent",
            "momentumLabel": "Agent 판단",
            "directionLabel": direction_label,
            "directionTone": direction_tone,
            "confidence": confidence,
            "confidencePct": confidence_pct,
            "interpretation": impact,
            "marketImpact": driver.get("marketImpact") or direction["effect"],
            "rationale": why_it_matters,
            "whyItMatters": why_it_matters,
            "evidenceSummary": driver.get("evidenceSummary") or why_it_matters or impact,
            "elaboration": "출처: " + ", ".join(source_refs[:4]) if source_refs else "",
            # 스냅샷 드라이버는 narrative state가 아니므로 7/30/90일 count를
            # 갖지 않는다. null은 기존 렌더러를 깨지 않으면서 0이라는 가짜
            # 내러티브 count로 보이지 않게 한다.
            "evidenceCounts": {"d7": None, "d30": None, "d90": None},
            "evidenceCountStatus": "unavailable",
            "linkedCompanies": [],
            "nextCheckpoint": next_memory_check,
            "whatToWatch": next_memory_check,
            "nextMemoryCheck": next_memory_check,
            "askAgentPrompt": f"{driver.get('title') or '현재 시장 상태'}가 내 투자 판단에 주는 의미를 설명해줘",
        })
    summary = view.get("actionSummary") or snapshot.get("beginnerSummary") or _plain_conclusion(posture)
    raw_guide = view.get("actionGuide") if isinstance(view.get("actionGuide"), dict) else snapshot.get("actionGuide")
    raw_guide = raw_guide if isinstance(raw_guide, dict) else {}
    action_guide = {
        **_action_guide(posture),
        **{key: value for key, value in raw_guide.items() if value},
    }
    reason_summary = view.get("marketInterpretation") or snapshot.get("oneLineSummary") or _reason_summary_from_drivers(drivers, posture["summary"])
    return {
        "title": view.get("headline") or snapshot.get("headline") or "현재 중기 시장 상황",
        "summary": summary,
        "plainConclusion": summary,
        "sourceSummary": snapshot.get("oneLineSummary") or "",
        "reasonSummary": reason_summary,
        "source": "market_state_snapshot",
        "stance": posture["summary"],
        "posture": posture,
        "actionGuide": action_guide,
        "briefs": _briefs(
            summary,
            posture,
            watch_items,
            action_guide,
            reason_summary,
        ),
        "watchItems": watch_items[:5],
        "drivers": drivers,
        "snapshot": snapshot,
        "counterEvidence": view.get("counterEvidence") or snapshot.get("counterEvidence") or [],
        "uncertainties": view.get("uncertainties") or snapshot.get("uncertainties") or [],
        "sourceRefs": _display_source_refs(snapshot.get("sourceRefs") or []),
        "hiddenInternals": ["taxonomy", "storyMap", "audit", "familySuggestions", "rawEvidence"],
    }


def dashboard_payload_from_snapshot(snapshot: dict) -> dict:
    payload = _dashboard_payload_from_snapshot_view(snapshot)
    raw_views = snapshot.get("marketViews") if isinstance(snapshot.get("marketViews"), dict) else {}
    views = {}
    if raw_views:
        for key in ("overall", *MARKET_VIEW_KEYS):
            view = raw_views.get(key)
            if isinstance(view, dict):
                views[key] = _dashboard_payload_from_snapshot_view(snapshot, view)
    if views:
        if "overall" not in views:
            views["overall"] = payload
        payload["marketViews"] = views
    return payload


def market_state_dashboard_payload(
    db_path: str | Path = MARKET_MEMORY_DB_PATH,
    *,
    limit: int = 5,
    ref_query: MarketStateRefQuery | None = None,
) -> dict:
    snapshot = current_market_state_snapshot(db_path)
    if snapshot:
        payload = dashboard_payload_from_snapshot(snapshot)
    else:
        states = list_states(db_path, status="current", limit=30)
        payload = summarize_market_state(states, limit=limit)
    query = ref_query or MarketStateRefQuery(
        Path(db_path), Path(db_path).parent / "research-index.sqlite3", "GLOBAL", datetime.now(timezone.utc),
    )
    payload["marketStateRef"] = resolve_market_state_ref(query)
    return _attach_freshness(payload, db_path)
