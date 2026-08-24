"""Causal signatures used to distinguish company stories beyond wording."""
from __future__ import annotations

import re


_CONCEPTS = {
    "ai_investment": ("ai", "데이터센터", "인공지능"),
    "hbm_contract": ("hbm", "고대역폭", "공급계약"),
    "foundry_order": ("파운드리", "수주", "위탁생산"),
    "earnings": ("실적", "영업이익", "가이던스"),
    "export": ("수출", "출하", "통관"),
    "policy": ("정책", "규제", "보조금", "관세"),
}
_MECHANISMS = {
    "supply": ("공급", "출하", "생산능력"),
    "utilization": ("가동률", "수율"),
    "pricing": ("가격", "단가", "스프레드"),
    "capex": ("투자", "capex", "설비"),
    "demand": ("수요", "주문", "판매"),
    "flow": ("외국인", "수급", "순매수", "순매도"),
}
_OUTCOMES = {
    "profitability": ("수익성", "마진", "영업이익"),
    "revenue": ("매출", "판매액"),
    "share": ("점유율", "경쟁력"),
    "valuation": ("밸류에이션", "멀티플"),
    "price": ("주가", "상승", "하락", "강세", "약세"),
}


def _keys(text: str, catalog: dict[str, tuple[str, ...]]) -> list[str]:
    lowered = text.casefold()
    return sorted(key for key, aliases in catalog.items() if any(alias in lowered for alias in aliases))


def build_signature(group: dict, index: int = 0) -> dict:
    company = str(group.get("company") or group.get("sector") or "시장 주도주")
    ticker = ""
    evidence_ids = []
    excerpts = []
    for attribution in group.get("claimAttribution") or []:
        for unit in attribution.get("claimUnits") or []:
            if unit.get("role") == "direct":
                evidence_ids.append(f"{attribution.get('docId')}:{unit.get('claimId')}")
                excerpts.append(str(unit.get("excerpt") or ""))
    for doc in group.get("docs") or []:
        excerpts.extend(str(doc.get(key) or "") for key in ("title", "summary"))
        for item in doc.get("companies") or []:
            if isinstance(item, dict) and str(item.get("name") or "") == company:
                ticker = str(item.get("ticker") or "").upper()
    text = " ".join(excerpts)
    candidate_key = ticker or re.sub(r"[^0-9A-Za-z가-힣]+", "-", company).strip("-").lower() or str(index)
    return {
        "candidateId": f"kr-company-{candidate_key}",
        "subject": company,
        "sector": str((group.get("sectors") or [group.get("sector") or ""])[0] or ""),
        "catalysts": _keys(text, _CONCEPTS),
        "mechanisms": _keys(text, _MECHANISMS),
        "outcomes": _keys(text, _OUTCOMES),
        "horizon": "intraday" if any(token in text for token in ("장중", "오늘", "당일")) else "next_session",
        "evidenceIds": sorted(set(evidence_ids)),
        "baseLeaderScore": float(group.get("leaderScore") or group.get("briefingGroupScore") or group.get("score") or 0.0),
        "directEvidenceCount": int(group.get("directEvidenceCount") or len(evidence_ids)),
        "confidence": round(min(1.0, 0.35 + 0.12 * min(len(evidence_ids), 4) + 0.06 * bool(_keys(text, _CONCEPTS))), 3),
    }


def overlap(left: dict, right: dict) -> dict:
    def ratio(key: str) -> float:
        a, b = set(left.get(key) or []), set(right.get(key) or [])
        return len(a & b) / max(1, len(a | b))
    catalyst, mechanism, outcome, evidence = (
        ratio("catalysts"), ratio("mechanisms"), ratio("outcomes"), ratio("evidenceIds")
    )
    causal = (catalyst + mechanism + outcome) / 3
    independent = bool(set(left.get("catalysts") or []) & set(right.get("catalysts") or [])) and (
        mechanism < 0.34 or outcome < 0.34
    )
    return {
        "catalyst": round(catalyst, 3),
        "mechanism": round(mechanism, 3),
        "outcome": round(outcome, 3),
        "evidence": round(evidence, 3),
        "causal": round(causal, 3),
        "independentDimensions": independent,
    }


__all__ = ["build_signature", "overlap"]
