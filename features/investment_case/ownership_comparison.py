"""Compare preserved inputs without reconstructing a historical decision."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .ownership import content
from .paths import digest


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def _difference(before, after):
    left, right = number(before), number(after)
    return str(right - left) if left is not None and right is not None else None


def _input(body, slot):
    return (body or {}).get("inputs", {}).get(slot) or {"status": "unavailable", "reason": "original_not_recorded", "content": None, "ref": {}}


def _comparison_key(slot, item):
    reference = dict(item.get("ref") or {})
    value = dict(item.get("content") or {})
    if slot == "readiness":
        # Viewing time is retained for provenance, not a new owner input.
        value.pop("evaluatedAt", None)
        reference.pop("asOf", None)
        reference.pop("contentHash", None)
    elif slot == "macro":
        # Capture's contentHash excludes query times while retaining source
        # revisions and interpretation changes. Do not hash those times again.
        value = None
    return digest({"ref": reference, "content": value, "dependencies": item.get("dependencies") or []})


def _axis(before, after, slots):
    rows = []
    for slot in slots:
        left, right = _input(before, slot), _input(after, slot)
        if left.get("status") != "preserved" or right.get("status") != "preserved":
            state = "unavailable"
        elif left["ref"].get("methodVersion") != right["ref"].get("methodVersion"):
            state = "incomparable"
        else:
            state = "unchanged_input" if _comparison_key(slot, left) == _comparison_key(slot, right) else "changed_input"
        rows.append({"slot": slot, "status": state, "before": left, "after": right})
    return rows


def _annual(snapshot):
    inputs = (snapshot or {}).get("inputs") or {}
    history = inputs.get("history") or {}
    rows = history.get("rows") or []
    result = {}
    duplicates = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("metric") not in {"Revenue", "Net Income", "EPS Diluted"}:
            continue
        period = row.get("period") or {}
        key = (row.get("metric"), period.get("start"), period.get("end"))
        if key in result:
            duplicates.add(key)
        unit = row.get("unit") or history.get("currency")
        result[key] = {"metric": key[0], "period": period, "fiscalYear": row.get("fiscalYear"), "value": row.get("value"),
                       "unit": unit, "definition": row.get("concept") or row.get("metric"),
                       "sourceRef": {key: row.get(key) for key in ("accession", "filed", "form", "concept")},
                       "basis": history.get("sharesBasis") if key[0] == "EPS Diluted" else None,
                       "statementBasis": history.get("basis"),
                       "role": "observation", "ambiguous": False}
    for key in duplicates:
        result[key]["ambiguous"] = True
    for (metric, start, end), row in list(result.items()):
        net = result.get(("Net Income", start, end))
        if metric == "Revenue" and net:
            revenue, income = number(row["value"]), number(net["value"])
            eligible = bool(revenue and income is not None and row["unit"] and row["unit"] == net["unit"] and not (row["ambiguous"] or net["ambiguous"]))
            result[("Net Margin", start, end)] = {**row, "metric": "Net Margin", "value": str(income / revenue * 100) if eligible else None,
                "unit": "%", "definition": f"{net['definition']} / {row['definition']} * 100", "ambiguous": not eligible, "basis": None,
                "sourceRef": {"revenue": row["sourceRef"], "netIncome": net["sourceRef"]}}
    return {key: row for key, row in result.items() if key[0] != "Net Income"}


def quantitative(before, after):
    left = (content(before, "price") or {}).get("snapshot") or {}
    right = (content(after, "price") or {}).get("snapshot") or {}
    a, b = left.get("inputs") or {}, right.get("inputs") or {}
    left_results, right_results = left.get("results") or {}, right.get("results") or {}
    method_ok = bool(a.get("methodVersion") and a.get("methodVersion") == b.get("methodVersion") and a.get("specSha256") == b.get("specSha256"))
    identity_ok = bool(a.get("instrumentId") and a.get("instrumentId") == b.get("instrumentId"))
    unit_ok = bool((a.get("price") or {}).get("currency") and (a.get("price") or {}).get("currency") == (b.get("price") or {}).get("currency"))
    left_events, right_events = left_results.get("shareEvents") or {}, right_results.get("shareEvents") or {}
    share_ok = bool(left_events.get("state") in {"none_confirmed", "present"} and digest(left_events) == digest(right_events))
    def financial_definitions(inputs):
        history = inputs.get("history") or {}
        definitions = sorted({(str(row.get("metric") or ""), str(row.get("concept") or row.get("metric") or ""), str(row.get("unit") or history.get("currency") or "")) for row in history.get("rows") or [] if isinstance(row, dict)})
        return history.get("basis"), history.get("sharesBasis"), definitions
    definitions_ok = financial_definitions(a) == financial_definitions(b)
    scenarios = []
    for old in left_results.get("scenarios") or []:
        new = next((row for row in right_results.get("scenarios") or [] if row.get("label") == old.get("label") and row.get("horizon") == old.get("horizon")), None)
        for metric, unit in (("g", "ratio"), ("exitPE", "multiple"), ("payout", "ratio"), ("irr", "ratio")):
            valid = method_ok and identity_ok and unit_ok and share_ok and definitions_ok and old.get("status") == "available" and (new or {}).get("status") == "available"
            change = _difference(old.get(metric), (new or {}).get(metric)) if valid else None
            scenarios.append({"metric": metric, "label": old.get("label"), "horizon": old.get("horizon"), "unit": unit,
                              "before": old.get(metric), "after": (new or {}).get(metric), "difference": change,
                              "status": "comparable" if change is not None else "incomparable",
                              "role": "scenario_assumption" if metric != "irr" else "scenario_result",
                              "beforeSnapshotId": left.get("snapshotId"), "afterSnapshotId": right.get("snapshotId")})
    annual = []
    original_rows, current_rows = _annual(left), _annual(right)
    for key in sorted(set(original_rows) | set(current_rows), key=lambda key: (key[2] or "", key[0]), reverse=True):
        old, new = original_rows.get(key), current_rows.get(key)
        same_basis = bool(old and new and old["unit"] and old["unit"] == new["unit"] and old["definition"] == new["definition"] and old["statementBasis"] == new["statementBasis"] and key[1] and key[2] and not (old["ambiguous"] or new["ambiguous"]))
        if key[0] == "EPS Diluted":
            same_basis = same_basis and share_ok and bool(old and new and old["basis"] and old["basis"] == new["basis"])
        change = _difference(old["value"], new["value"]) if method_ok and identity_ok and same_basis else None
        annual.append({"metric": key[0], "period": {"start": key[1], "end": key[2]}, "before": old, "after": new,
                       "difference": change, "status": "comparable" if change is not None else "new_period" if old is None else "incomparable",
                       "meaning": "same_period_observation_revision" if change is not None else "comparison_gap"})
    return {"scenarios": scenarios, "annual": annual,
            "userExpectation": {"status": "unavailable", "reason": "structured_expectation_not_preserved"},
            "companyGuidance": {"status": "unavailable", "reason": "structured_guidance_not_preserved"},
            "notice": "시나리오는 계산 가정이며 사용자 명시 기대·회사 가이던스·실현 성과와 다릅니다. 같은 기간 관측의 차이는 자료 정정일 수 있습니다."}


def compare(before, after):
    original_reason, current_reason = content(before, "reason"), content(after, "reason")
    return {"business": _axis(before, after, ("reason", "company", "research", "delta")),
            "price": _axis(before, after, ("price", "readiness")), "macro": _axis(before, after, ("macro",)),
            "portfolio": _axis(before, after, ("review",)), "quantitative": quantitative(before, after),
            "reason": {"before": original_reason, "after": current_reason,
                       "revisionChanged": bool(original_reason and current_reason and original_reason.get("revisionId") != current_reason.get("revisionId"))},
            "notice": "입력의 변화는 이유 훼손이나 유지 판정이 아닙니다. 자료 없음·오래된 자료·신호 없음은 조건 미발생을 뜻하지 않습니다."}
