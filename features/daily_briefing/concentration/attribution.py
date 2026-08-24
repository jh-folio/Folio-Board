"""Claim-level evidence attribution for KR briefing company candidates."""
from __future__ import annotations

import hashlib
import re


_SENTENCE = re.compile(r"(?:다\.|[.!?。！？])\s+|[\r\n]+")
_INCIDENTAL = re.compile(r"(?:등|비롯|포함|관련주|종목은|업체로는)\s*$")


def _doc_id(doc: dict) -> str:
    return str(doc.get("id") or doc.get("documentId") or doc.get("url") or doc.get("path") or doc.get("title") or "")


def _claims(doc: dict) -> list[str]:
    text = " ".join(str(doc.get(key) or "") for key in ("title", "summary", "content"))
    rows = [re.sub(r"\s+", " ", row).strip() for row in _SENTENCE.split(text)]
    return [row[:360] for row in rows if len(row) >= 12][:24]


def _company_names(doc: dict) -> list[str]:
    names = []
    for company in doc.get("companies") or []:
        if not isinstance(company, dict):
            continue
        for value in (company.get("name"), company.get("ticker")):
            text = str(value or "").strip()
            if text and text not in names:
                names.append(text)
    return names


def attribute_document(doc: dict, company: str) -> dict:
    company = str(company or "").strip()
    all_companies = _company_names(doc)
    aliases = {company.casefold()}
    for item in doc.get("companies") or []:
        if isinstance(item, dict) and str(item.get("name") or "").strip() == company:
            aliases.add(str(item.get("ticker") or "").strip().casefold())
    aliases.discard("")
    units = []
    direct = 0
    for index, excerpt in enumerate(_claims(doc), 1):
        lowered = excerpt.casefold()
        mentions = [name for name in all_companies if name.casefold() in lowered]
        mentions_target = any(alias in lowered for alias in aliases)
        if mentions_target and not (_INCIDENTAL.search(excerpt) and len(mentions) > 1):
            role, credit = "direct", 1.0
            direct += 1
        elif not mentions_target and len(all_companies) > 1:
            role, credit = "shared_context", round(1.0 / len(all_companies), 3)
        else:
            role, credit = "incidental", 0.0
        claim_key = hashlib.sha1(f"{_doc_id(doc)}|{index}|{excerpt}".encode("utf-8")).hexdigest()[:12]
        units.append({"claimId": f"claim_{claim_key}", "excerpt": excerpt, "role": role, "credit": credit})
    body_words = int(doc.get("wordCount") or len(str(doc.get("content") or "").split()))
    confidence = 0.45 if body_words < 60 else 0.7 if body_words < 120 else 0.9
    if direct == 0:
        confidence *= 0.5
    return {
        "docId": _doc_id(doc),
        "company": company,
        "claimUnits": units,
        "directEvidenceCount": direct,
        "attributionConfidence": round(confidence, 3),
    }


def build_briefing_company_groups(groups: list[dict]) -> list[dict]:
    projected = []
    for group in groups or []:
        company = str(group.get("company") or "").strip()
        if not company:
            projected.append(dict(group))
            continue
        attributions = [attribute_document(doc, company) for doc in group.get("docs") or []]
        weighted_score = 0.0
        direct_count = 0
        for doc, attribution in zip(group.get("docs") or [], attributions, strict=True):
            direct_count += int(attribution["directEvidenceCount"])
            credit = sum(float(unit["credit"]) for unit in attribution["claimUnits"])
            weighted_score += float(doc.get("briefingDocScore") or 0.0) * min(1.0, credit)
        row = dict(group)
        row["claimAttribution"] = attributions
        row["directEvidenceCount"] = direct_count
        row["attributedBriefingScore"] = round(weighted_score, 3)
        projected.append(row)
    return projected


__all__ = ["attribute_document", "build_briefing_company_groups"]
