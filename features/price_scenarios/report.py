"""Canonical wording of one price snapshot, shared by the rule report, the CLI context and charts.

Every number here is read from the stored snapshot; nothing is recomputed. Only
canonical results appear: a person's criteria and assumptions never enter a
report (they are read at view time). Wording avoids the forbidden set in spec §5
(no purchase/sale/target/price-level verdicts, no likelihood language).
"""
from __future__ import annotations

import math
from decimal import Decimal

from .decimal_ops import number

REASONS = {
    "missing_value": "해당 연도의 공시 값이 없어 표시하지 않았습니다",
    "irr_above_range": "수익률이 계산 구간 상한을 넘어 세 조각으로 나누지 않았습니다",
    "irr_below_range": "수익률이 계산 구간 하한을 넘어 세 조각으로 나누지 않았습니다",
    "flat_irr_out_of_range": "PER이 그대로일 때 수익률이 계산 구간을 벗어납니다",
    "net_income_sum_not_positive": "대상 연도의 순이익 합이 0 이하라 현금 비율을 계산하지 않았습니다",
    "non_positive_normalized_earnings": "과거 보통 이익률로 계산한 주당이익이 0 이하입니다",
    "required_return_not_positive": "내 요구수익률이 0 이하라 성장 없는 가치를 계산하지 않았습니다",
    "previous_method": "이 계산 기록에는 없는 항목입니다. 다시 계산하면 볼 수 있습니다",
    "history_too_short": "과거 자료가 부족해 계산하지 않았습니다",
    "share_event_unknown": "주식 수가 바뀐 사건을 확인하지 못해 주당 계산을 하지 않았습니다",
    "price_event_unverified": "가격에 주식 수 변화가 반영됐는지 확인하지 못해 연말 PER을 쓰는 계산을 하지 않았습니다",
    "negative_base_eps": "최근 연도 주당이익이 0 이하라 수익률 계산을 하지 않았습니다",
    "base_eps_missing": "최근 회계연도의 희석 주당이익이 없어 계산하지 않았습니다",
    "stale_financials": "최근 재무제표가 15개월보다 오래돼 계산하지 않았습니다",
    "non_positive_revenue": "최근 매출이 0 이하라 계산하지 않았습니다",
    "adr_ratio_unverified": "ADR 비율을 공시에서 확인하지 못해 주당 계산을 하지 않았습니다",
    "currency_mismatch": "재무제표 통화와 주가 통화가 달라 환산 없이 비교하는 계산을 하지 않았습니다",
    "currency_unknown": "통화를 확인하지 못해 주당 계산을 하지 않았습니다",
    "share_unit_unknown": "주식 수 단위를 확인하지 못해 주당 계산을 하지 않았습니다",
    "share_unit_mismatch": "주식 수 단위가 맞지 않아 주당 계산을 하지 않았습니다",
    "non_common_listing": "보통주가 아닌 종목이라 주당 계산을 하지 않았습니다",
    "class_eps_differs": "주식 종류별 주당이익이 달라 주당 계산을 하지 않았습니다",
    "industry_not_supported": "이 업종은 이 계산 방식이 맞지 않아 지원하지 않습니다",
    "financial_holding": "금융지주는 이 계산 방식이 맞지 않아 지원하지 않습니다",
    "fund_not_supported": "ETF·펀드는 회사 이익으로 계산하는 이 방식의 대상이 아닙니다",
    "dcf_not_computable": "현금흐름 할인 계산에 필요한 입력이 부족해 계산하지 않았습니다",
    "price_stale": "최근 종가가 10거래일 넘게 갱신되지 않아 계산하지 않았습니다",
    "price_unavailable": "종가를 가져오지 못해 계산하지 않았습니다",
    "financial_history_unavailable": "공시 재무 자료를 가져오지 못해 계산하지 않았습니다",
    "company_not_found": "공식 자료에서 이 종목을 찾지 못해 계산하지 않았습니다",
    "source_credential_missing": "필요한 공시 조회 키가 설정되어 있지 않아 계산하지 않았습니다",
    "instrument_not_supported": "지원하지 않는 종목 형식이라 계산하지 않았습니다",
    "price_snapshot_failed": "가격 시나리오 계산 결과를 저장하지 못해 쓰지 않았습니다",
    "calculation_failed": "예상하지 못한 오류로 계산하지 못했습니다",
    "price_snapshot_unavailable": "가격 시나리오를 계산하지 못했습니다",
}
NOTICES = {
    "share_classes_same_eps": "같은 주당이익을 공시하는 여러 주식 종류가 있습니다.",
    "preferred_shares_exist": "우선주가 있으며 이 계산은 보통주 기준입니다.",
    "holding_company_consolidated": "지주회사: 연결 기준입니다. 자회사 가치를 합산해 보는 관점은 반영하지 않습니다.",
    "shares_implied_from_eps": "주식 수는 순이익을 주당이익으로 나눠 구한 값입니다.",
    "classification_unknown": "업종 분류를 확인하지 못했습니다.",
    "common_row_label_voting_shares": "주식 수 표의 보통주 행을 '의결권 있는 주식' 항목으로 읽었습니다.",
    "dividend_assumed_zero_from_absence": "배당 공시가 없는 해는 배당이 없었던 것으로 읽었습니다.",
    "excluded_growth_windows": "과거 5년 구간 일부는 값이 없거나 0 이하라 빼고 계산했습니다. 범위가 위로 치우칠 수 있습니다.",
}
ROWS = (("conservative", "과거 10년 중 낮은 편(하위 25%)"), ("base", "중간값"), ("optimistic", "높은 편(상위 25%)"))
ASSUMPTION_SENTENCE = ("이 표는 과거 이 회사의 5년 성장률·연말 PER이 비슷한 범위로 되풀이된다면 어떤 연환산 수익률이 되는지 계산한 것입니다. "
                       "하위 25%는 과거 값을 줄 세웠을 때 아래쪽 4분의 1 위치입니다. 예측이 아니며 각 가정이 일어날 가능성을 뜻하지 않습니다.")


def reason_text(reason: str | dict | None) -> str:
    detail = reason if isinstance(reason, dict) else {"code": reason}
    code, sub = detail.get("code"), detail.get("subCode")
    if code == "price_unavailable" and sub == "provider_error":
        return "가격 제공처가 일시적으로 응답하지 않았습니다. 잠시 뒤 다시 계산해 보세요"
    if code == "financial_history_unavailable" and sub == "provider_error":
        return "공시 제공처가 일시적으로 응답하지 않았습니다. 잠시 뒤 다시 계산해 보세요"
    if code == "history_too_short" and all(k in detail for k in ("range", "n", "required", "historyYears")):
        n, required, years = detail["n"], detail["required"], detail["historyYears"]
        windows = detail["range"] in {"growth", "rpsGrowth"}
        if sub == "years_too_few":
            if windows:
                return f"재무 기록이 {years}년뿐이라 비교할 5년 구간이 {n}개입니다(필요 {required}개). 연속 기록이라면 최소 8년이 필요합니다"
            name = {"pe": "연말 PER", "payout": "배당성향", "netMargin": "순이익률"}.get(detail["range"], "비교")
            return f"재무 기록이 {years}년뿐이라 {name}에 쓸 해가 {n}개입니다(필요 {required}개)"
        cause = {"loss_years": "주당이익이 0 이하인 해가 있어", "missing_years": "일부 연도의 공시 값이 비어"}.get(sub)
        if cause:
            unit = "5년 구간" if windows else "연도"
            return f"{cause} 비교할 {unit}이 {n}개입니다(필요 {required}개)"
    return REASONS.get(code or "", f"계산할 수 없습니다(사유 코드: {code or 'unknown'})")


def notice_text(notice: str | dict) -> str:
    detail = notice if isinstance(notice, dict) else {"code": notice}
    if detail["code"] == "derived_eps_years":
        years = "·".join(f"FY{year}" for year in detail.get("years", []))
        return f"{years} 주당이익은 공시 정리 자료에 없어 같은 해 순이익 ÷ 희석 주식 수로 계산했습니다."
    if detail["code"] == "listed_class_eps":
        return f"주식 종류가 여러 개라, 상장된 {detail.get('class', '')} 기준 주당이익을 공시 원문에서 읽었습니다."
    return NOTICES.get(detail["code"], "")


def pct(value, places: int = 1) -> str:
    return f"{number(value) * 100:.{places}f}%"


def multiple(value) -> str:
    return f"{number(value):.1f}배"


def money(value, currency: str, *, per_share: bool = False) -> str:
    amount = float(number(value))
    if per_share:
        return f"{amount:,.2f} {currency}"
    sign, amount = ("-" if amount < 0 else ""), abs(amount)
    if currency == "KRW":
        return f"{sign}{amount / 1e12:,.2f}조 원" if amount >= 1e12 else f"{sign}{amount / 1e8:,.0f}억 원"
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if amount >= limit:
            return f"{sign}{amount / limit:,.2f}{suffix} {currency}"
    return f"{sign}{amount:,.0f} {currency}"


def _irr_text(row: dict) -> str:
    if row.get("status") != "available":
        return "계산 불가"
    if row.get("irrRange") == "above_range":
        return "100% 초과"
    if row.get("irrRange") == "below_range":
        return "-99% 미만"
    return pct(row["irr"])


def _scenario_table(results: dict) -> list[str]:
    rows = {(row["label"], row["horizon"]): row for row in results["scenarios"]}
    if all(row.get("status") != "available" for row in rows.values()):
        first = next(iter(rows.values()), {})
        return [f"가정별 연환산 수익률은 계산하지 못했습니다 — {reason_text(first.get('reason'))}."]
    lines = ["| 가정 | EPS 연 성장률 | 끝날 때 PER | 배당성향 | 5년 연환산 | 10년 연환산 |", "|---|---|---|---|---|---|"]
    for label, name in ROWS:
        five, ten = rows.get((label, 5)), rows.get((label, 10))
        ref = five if five and five.get("status") == "available" else ten
        if not ref or ref.get("status") != "available":
            lines.append(f"| {name} | - | - | - | 계산 불가 | 계산 불가 |")
            continue
        lines.append(f"| {name} | {pct(ref['g'])} | {multiple(ref['exitPE'])} | {pct(ref['payout'])} | "
                     f"{_irr_text(five or {})} | {_irr_text(ten or {})} |")
    return [*lines, "", ASSUMPTION_SENTENCE]


def _decomposition(results: dict) -> list[str]:
    block = results.get("decomposition") or {}
    if block.get("status") != "available":
        return [f"과거 이익 성장의 출처는 계산하지 못했습니다 — {reason_text(block.get('reason'))}."]
    recent = block["windows"][-1]
    annual = recent["annual"]
    approx = lambda text: f"{(math.exp(float(text)) - 1) * 100:+.1f}%"
    lines = [f"가장 최근 5년({recent['start']}→{recent['end']}) 주당이익은 연 {approx(annual['total'])} 늘었습니다. "
             f"매출 {approx(annual['R'])} · 마진 {approx(annual['M'])} · 주식 수 감소 {approx(annual['S'])}가 합쳐진 값입니다."]
    for note in block.get("notes", []):
        if note["code"] == "margin_majority":
            lines.append("과거 주당이익 성장의 절반 이상이 마진 개선에서 왔습니다. 마진은 계속 오를 수 없으므로 같은 성장률이 되풀이되기 어려울 수 있습니다.")
        elif note["code"] == "share_reduction_significant":
            lines.append("성장의 상당 부분이 주식 수 감소(자사주 매입 등)에서 왔습니다.")
    return lines


def _requirements(results: dict) -> list[str]:
    reverse = results.get("reverse") or {}
    lines = []
    for horizon in ("5", "10"):
        entry = (reverse.get("breakEvenPE") or {}).get(horizon) or {}
        if entry.get("status") == "available":
            if entry["state"] == "not_needed":
                lines.append(f"- {horizon}년: 배당만으로 지금 가격을 회수할 수 있어, 손실이 나지 않기 위한 끝날 때 PER 조건이 필요 없습니다.")
            else:
                lines.append(f"- {horizon}년: 중간값 성장·배당성향이 이어진다고 할 때 손실이 나지 않으려면(손익분기) 끝날 때 PER이 {multiple(entry['exitPE'])} 이상이어야 합니다.")
        margin = (reverse.get("breakEvenMargin") or {}).get(horizon) or {}
        if margin.get("status") == "available" and margin.get("margin") is not None:
            lines.append(f"- {horizon}년: 주당 매출이 과거 중간 속도로 늘 때 손실이 나지 않으려면 {horizon}년 뒤 순이익률이 약 {pct(margin['margin'])}가 되는 가정과 맞먹습니다"
                         f"(최근 {pct(margin['currentMargin'])}). 달성 가능성은 판단하지 않습니다.")
    dcf = (results.get("dcf") or {}).get("result") or {}
    implied = dcf.get("impliedGrowth") if isinstance(dcf, dict) else None
    if isinstance(implied, dict) and implied.get("status") == "solved" and (results.get("dcf") or {}).get("marginOfSafetyJudgment") == "eligible":
        lines.append(f"- 현금흐름 할인 계산 기준: 지금 가격에 맞는 초기 FCF 성장률은 연 {pct(implied['growth'])}입니다(선택한 모델과 나머지 가정에 조건부).")
    return lines or ["지금 가격이 전제하는 조건은 계산하지 못했습니다."]


def _dcf_table(results: dict, price_currency: str) -> list[str]:
    block = results.get("dcf") or {}
    if block.get("status") != "available":
        return [f"현금흐름 할인(DCF) 계산은 하지 않았습니다 — {reason_text(block.get('reason'))}."]
    result, lines = block["result"], []
    currency = result.get("currency") or price_currency
    rows = [row for row in result.get("scenarios", []) if row.get("ok")]
    if not rows:
        return ["현금흐름 할인(DCF) 계산은 하지 않았습니다 — 계산 가능한 시나리오가 없습니다."]
    discount = result.get("discountRate", {})
    lines += ["| 시나리오 | 초기 FCF 성장률 | 할인율 | 영구성장률 | 자기자본가치 | 내재가치/주 |", "|---|---|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['name']} | {pct(row['growth'])} | {pct(row['discount'])} | {pct(row['terminal'])} | "
                     f"{money(row['equityValue'], currency)} | {money(row['perShare'], currency, per_share=True)} |")
    lines.append("")
    method = "WACC" if discount.get("method") == "wacc" else "고정값(회사별 계산에 필요한 입력이 부족해 대체)"
    lines.append(f"할인율은 {method}로 정했습니다. 초기 성장률은 과거 {result.get('growth', {}).get('basis', '')} 기반이며 "
                 f"{len(result.get('fadePath') or [])}년에 걸쳐 영구성장률로 줄어듭니다.")
    if block.get("marginOfSafetyJudgment") != "eligible":
        lines.append("이 계산은 자료 부족으로 대체한 값(성장률 또는 할인율)을 포함하므로 안전마진 판정에는 쓰지 않습니다.")
    return lines


def _notes(results: dict) -> list[str]:
    notices = [*(results.get("support") or {}).get("notices", []), *results.get("notices", [])]
    return list(dict.fromkeys(text for text in map(notice_text, notices) if text))


def _return_parts(results: dict) -> list[str]:
    parts = results.get("returnParts")
    if not isinstance(parts, list):
        return [reason_text("previous_method") + "."] if parts else []
    lines = []
    for row in parts:
        if row["label"] != "base":
            continue
        if row["status"] != "available":
            lines.append(f"- 기본 {row['horizon']}년: {reason_text(row['reason'])}.")
        else:
            signed = lambda x: f"{number(x)*100:+.2f}%"
            lines.append(f"- 기본 {row['horizon']}년: 이익 성장 {signed(row['growth'])} · 배당 {signed(row['dividend'])} · "
                         f"PER 변화 {signed(row['rerating'])} (PER {multiple(row['peNow'])} → {multiple(row['exitPE'])}). "
                         f"PER이 그대로라면 연 {pct(row['irrFlat'], 2)}입니다.")
    return lines


def cash_lines(block: dict | None) -> list[str]:
    """Display uses stored ratio, the same source as the price tab (§4.3)."""
    if not block:
        return []
    if block['status'] != 'available':
        code = (block.get('reason') or {}).get('code')
        text = ('재무제표 통화를 확인하지 못해 현금 비교를 하지 않았습니다' if code == 'currency_unknown' else reason_text(code))
        lines = [text + '.']
    else:
        ratio = number(block['ratio'])
        count = (ratio*100).quantize(Decimal(1))
        lines = ([f"순이익 100당 현금이 약 {count} 남았습니다."] if ratio >= 0 else
                 ["같은 기간 순이익은 플러스였지만 설비투자를 뺀 현금은 마이너스였습니다."])
        classification = block['class']
        if classification == 'cash_below_earnings':
            lines.append('회계 이익보다 현금이 적게 남았습니다. 설비투자나 운전자본 증가가 이유일 수 있습니다.')
        elif classification == 'cash_above_earnings':
            lines.append('회계 이익보다 현금이 많이 남았습니다. 감가상각이 설비투자보다 크거나 운전자본이 줄었을 수 있습니다.'
                         + (' 주식 보상 비용을 빼지 않았습니다.' if block['sbcBasis'] != 'deducted' else ''))
    years = [r['fiscalYear'] for r in block.get('years', [])]
    if years:
        period = f"지난 {len(years)}년" if years == list(range(years[0], years[-1]+1)) else f"{len(years)}개 회계연도"
        basis = '주식 보상 비용 차감 후' if block['sbcBasis'] == 'deducted' else '주식 보상 비용 차감 전'
        lines.append(f"{period}(FY{years[0]}–FY{years[-1]}) · {basis} · 재무제표 통화 {block['currency']}.")
    for notice in block.get('notices', []):
        code = notice['code']
        if code == 'sbc_missing_years':
            years_text = '·'.join(f"FY{y}" for y in notice['years'])
            lines.append(f"일부 연도({years_text})에 주식 보상 비용 공시가 없어, 모든 연도에서 빼지 않고 계산했습니다.")
        elif code == 'sbc_not_deducted_kr':
            lines.append('한국 공시는 주식 보상 비용을 같은 방식으로 읽을 수 없어 빼지 않고 계산했습니다.')
        elif code == 'stale_financials':
            lines.append('최근 재무제표가 15개월 넘게 지난 자료입니다. 지난 기간의 합계로 계산했습니다.')
    if years:
        lines.append('순이익은 지배주주 기준이고 영업현금에는 비지배지분이 포함될 수 있습니다. 현금흐름 할인(DCF) 계산의 현금 정의와 다릅니다.')
    return lines


def lines(view: dict) -> list[str]:
    """The one wording. `view` is `service.snapshot_view()` output."""
    results, price = view["results"], view["inputSummary"]["price"]
    currency = price.get("currency") or ""
    support = results["support"]
    head = [f"계산 시점 {view['asOf']} · 기준 가격 {money(price['value'], currency, per_share=True)} "
            f"({price['sessionDate']} 종가, 분할만 반영한 실제 종가)"]
    cash = cash_lines(results.get('cashConversion'))
    cash_section = ["", "### 이익이 현금으로 남았나", "", *cash] if cash else []
    if support["status"] != "supported":
        reason = support["reasons"][0]
        return [*head, "", f"이 종목은 가격 시나리오를 계산하지 않았습니다 — {reason_text(reason)}.", *cash_section]
    return [*head, "", "### 가정별 연환산 수익률", "", *_scenario_table(results), "", *_return_parts(results), *cash_section, "", "### 과거 이익 성장은 어디서 왔나", "",
            *_decomposition(results), "", "### 지금 가격이 전제하는 것", "", *_requirements(results), "",
            "### 현금흐름 할인(DCF) 시나리오", "", *_dcf_table(results, currency), *(["", *_notes(results)] if _notes(results) else [])]


def render_section(view: dict) -> str:
    """Body section of a rule-based report."""
    return "\n".join(["## 가격과 가정별 수익률", "", *lines(view)])


def render_context(view: dict) -> str:
    """Generation context block: the same wording, plus the rules for using it."""
    return "\n".join(["## 가격 시나리오 (이 값을 그대로 쓰세요)", "", *lines(view), "",
                      "- 위 숫자는 저장된 계산 결과입니다. 다시 계산하거나 다른 가정·기간의 값을 만들지 마세요.",
                      "- 계산하지 않았다고 적힌 항목은 추정하지 말고 그 사유만 적으세요.",
                      "- 수익률은 예측이 아니라 가정이 성립할 때의 계산입니다. 목표가격·매수·매도 지시, 가격 수준 판정, 가능성 표현은 쓰지 마세요."])


def dcf_chart(view: dict) -> dict | None:
    """The DCF chart payload for the report reader, read from the snapshot (floats for the chart layer)."""
    block = view["results"].get("dcf") or {}
    if block.get("status") != "available":
        return None
    result = block["result"]
    rows = [{"name": row["name"], "perShare": float(row["perShare"]), "growth": float(row["growth"]),
             "discount": float(row["discount"]), "terminal": float(row["terminal"])}
            for row in result.get("scenarios", []) if row.get("ok")]
    if not rows:
        return None
    implied = result.get("impliedGrowth") or {}
    return {"id": "dcf", "title": "DCF 시나리오",
            "subtitle": f"초기 FCF 성장률 가정별 주당 내재가치 (할인율 {float(result['discountRate']['rate']) * 100:.1f}%, "
                        f"{len(result.get('fadePath') or [])}년 감쇠)",
            "kind": "dcf", "scenarios": rows, "currentPrice": float(view["inputSummary"]["price"]["value"]),
            "impliedGrowth": (float(implied["growth"]) if implied.get("status") == "solved" and block.get("marginOfSafetyJudgment") == "eligible"
                              else None),
            "terminalShare": float(result["terminalShare"]) if result.get("terminalShare") is not None else None,
            "currency": view["inputSummary"]["price"].get("currency") or "", "priceSnapshotId": view["snapshotId"]}


def scenario_payload(view: dict) -> dict:
    """Structured scenario returns for the reader and Agent; no judgement and no personal layer."""
    results = view["results"]
    parts = results.get('returnParts')
    crosschecks = {'returnParts': [r for r in parts if r['label'] == 'base'] if isinstance(parts, list) else parts,
                   'cashConversion': results.get('cashConversion')}
    return {**crosschecks, "snapshotId": view["snapshotId"], "asOf": view["asOf"], "methodVersion": view["methodVersion"],
            "support": results["support"], "scenarios": results["scenarios"], "decomposition": results.get("decomposition"),
            "reverse": results.get("reverse"), "ranges": {key: {k: v for k, v in block.items() if k != "values"}
                                                           for key, block in (results.get("ranges") or {}).items()}}
