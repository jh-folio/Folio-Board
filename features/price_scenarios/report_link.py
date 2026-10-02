"""How a company-analysis report points at its price snapshot (spec §4.1, §5).

A new report names the stored snapshot it was written from and reads the PER
scenarios and the DCF from it; the old current-multiple x0.7 / x1.3 table and the
second DCF calculation are not produced. Charts, rule body and CLI context all
come from the same snapshot view. When no valid snapshot exists the report is
still written, says why, and carries no snapshot id.
"""
from __future__ import annotations

from . import report

SUPERSEDED = "price_snapshot_owns_valuation"
LEGACY_HEADING = "## 앱 계산 Valuation 및 DCF"
NEXT_HEADING = "## 공식 숫자 데이터"
POINTER = ("이 보고서의 PER 시나리오와 DCF 계산은 아래 '가격 시나리오' 블록 하나뿐입니다. "
           "이 자리에 따로 계산한 밸류에이션·DCF 표는 만들지 않았으니 다시 계산하거나 추정하지 마세요.")


def replace_legacy_valuation(materials: dict) -> None:
    """The materials context carries a second valuation/DCF calculation; a snapshot report has exactly one."""
    context = materials.get("context")
    if isinstance(context, str) and LEGACY_HEADING in context and NEXT_HEADING in context:
        start = context.index(LEGACY_HEADING)
        end = context.index(NEXT_HEADING, start)
        materials["context"] = "\n".join([context[:start] + LEGACY_HEADING, POINTER, "", context[end:]])
    if "computedValuation" in materials:
        materials["computedValuation"] = POINTER


def _price(view: dict | None) -> tuple[float | None, str]:
    if not view:
        return None, ""
    price = view["inputSummary"]["price"]
    return float(price["value"]), price.get("currency") or ""


def unavailable_lines(reason: dict | None) -> list[str]:
    return [f"가격 시나리오는 계산하지 못했습니다 — {report.reason_text((reason or {}).get('code'))}."]


def apply_price_snapshot(charts, materials: dict, snapshot: dict | None):
    """Return (charts, state, context). `snapshot` None leaves the legacy path untouched."""
    if snapshot is None:
        return charts, {}, ""
    out = dict(charts) if isinstance(charts, dict) else {}
    saved = snapshot.get("status") == "saved" and snapshot.get("view")
    view = snapshot["view"] if saved else None
    price, currency = _price(view)
    chart_list, placed = [], False
    for chart in out.get("charts", []):
        if chart.get("id") == "scenario_price":
            continue  # the current-multiple scenario table is retired for new reports
        if chart.get("id") == "dcf":
            replacement = report.dcf_chart(view) if view else None
            if replacement and not placed:
                chart_list.append(replacement)
            placed = True
            continue
        chart_list.append(chart)
    if view and not placed and (replacement := report.dcf_chart(view)):
        chart_list.insert(0, replacement)
    out.update(charts=chart_list, available=bool(chart_list),
               valuation={"status": "superseded", "reasonCodes": [SUPERSEDED], "currentPrice": price, "currency": currency},
               dcf={"ok": False, "status": "superseded", "reasonCodes": [SUPERSEDED], "currency": currency})
    if view:
        out.update(priceSnapshotId=view["snapshotId"], priceScenario=report.scenario_payload(view))
        state = {"status": "saved", "snapshotId": view["snapshotId"], "asOf": view["asOf"], "methodVersion": view["methodVersion"]}
        context = report.render_context(view)
        materials["priceSnapshot"] = {"status": "saved", "snapshotId": view["snapshotId"], "view": view}
    else:
        reason = snapshot.get("reason") or {"code": "price_snapshot_unavailable"}
        state = {"status": "unavailable", "reason": reason}
        context = "\n".join(["## 가격 시나리오", "", f"- {unavailable_lines(reason)[0]}",
                             "- 계산하지 않은 수익률·내재가치 숫자를 추정하거나 다시 계산하지 마세요."])
        materials["priceSnapshot"] = {"status": "unavailable", "reason": reason}
    replace_legacy_valuation(materials)
    return out, state, context


def rule_section(snapshot: dict | None) -> str | None:
    """Body of the rule report's valuation section, or None when the legacy path applies."""
    if not isinstance(snapshot, dict):
        return None
    if snapshot.get("status") == "saved" and snapshot.get("view"):
        return "\n".join(report.lines(snapshot["view"]))
    return "\n".join(unavailable_lines(snapshot.get("reason")))
