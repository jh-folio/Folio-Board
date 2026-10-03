"""Lossless ten-year history adapter for the legacy DCF summary readers.

This does not run a valuation or certify share/debt/currency eligibility. The
snapshot service must supply verified inputs before calling build_dcf.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

from .decimal_ops import number


def dcf_summary(history: dict) -> dict:
    """Preserve actual periods, filing identities and zeros; never trim to 3 FY.

    Each metric can have only one selected observation per fiscal year. The
    source adapters own tag/restatement selection; ambiguity here is an error,
    rather than letting a legacy reader silently choose a row by order.
    """
    rows = defaultdict(list)
    seen = set()
    for source in history.get("rows", []):
        key = (source["metric"], source["fiscalYear"])
        if key in seen:
            raise ValueError("ambiguous_dcf_fiscal_year")
        seen.add(key)
        number(source["value"])
        if int(source["period"]["end"][:4]) != source["fiscalYear"]:
            raise ValueError("dcf_fiscal_year_end_mismatch")
        fact = {"val": source["value"], "fy": str(source["fiscalYear"]),
                "start": source["period"].get("start"), "end": source["period"]["end"],
                "form": source["form"], "filed": source["filed"], "accn": source["accession"],
                "concept": source["concept"], "unit": source["unit"], "precision": source["precision"],
                "priorValues": deepcopy(source.get("priorValues", []))}
        for field in ("rawValue", "adjustment", "derivation", "formula", "sourceAccessions", "periodEndSource"):
            if field in source:
                fact[field] = deepcopy(source[field])
        rows[source["metric"]].append(fact)
    return {"currency": history.get("currency"), "basis": history.get("basis"),
            "sharesBasis": history.get("sharesBasis"), "excludedYears": deepcopy(history.get("excludedYears", [])),
            "rows": [{"metric": metric, "annual": sorted(facts, key=lambda fact: fact["end"], reverse=True)}
                     for metric, facts in sorted(rows.items())]}
