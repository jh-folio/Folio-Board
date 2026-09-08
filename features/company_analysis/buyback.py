"""자사주 매입의 **질**을 잰다.

금액만 있으면 매입은 언제나 주주환원으로 읽힌다. 실측(HWM 2026-08-27) 보고서는
`$700M / $500M / $250M`을 나열하고 "적극적 주주환원"이라고 적었다 — 그 돈이 주식 수를
실제로 줄였는지, 주식보상으로 늘어난 만큼을 메우는 데 그쳤는지, 얼마에 샀는지는
어디에도 없었다. **주식 수가 줄지 않는 매입은 환원이 아니라 희석 상쇄다.**

새 데이터소스가 필요 없다. SEC companyfacts에 이미 다 있다:
`PaymentsForRepurchaseOfCommonStock`, `ShareBasedCompensation`,
`WeightedAverageNumberOfDilutedSharesOutstanding`, `TreasuryStockSharesAcquired`.

경계:
- **없는 값은 만들지 않는다.** `TreasuryStockSharesAcquired`는 등재하지 않는 회사가
  많아(실측 HWM 없음) 평균 매입가는 있을 때만 낸다.
- **판정하지 않는다.** 비율을 계산해 보여줄 뿐, "좋다/나쁘다"는 결론은 근거를 본
  본문이 쓴다(§5 원칙 4 — 결론을 규칙이 확정하지 않는다).
"""
from __future__ import annotations

from features.company_analysis import financial_engine

# 이 비율을 넘으면 주식보상이 매입의 상당 부분을 먹는다는 뜻. 판정이 아니라 서술의
# 방향을 잡아 주는 눈금이며, 결론은 본문이 근거를 보고 쓴다.
_OFFSET_NOTE_THRESHOLD = 0.5


def build_buyback_quality(sec_summary: dict, *, price: float | None = None, currency: str = "USD") -> dict:
    """매입 금액·희석 상쇄·주식 수 변화·매입 수익률."""
    amount, year = financial_engine.latest_year_value(sec_summary, "Share Repurchases")
    if not amount or amount <= 0:
        return {}

    sbc = financial_engine.latest_value(sec_summary, "Stock-Based Compensation")
    shares_now = financial_engine.latest_value(sec_summary, "Shares Diluted")
    shares_prev = financial_engine.latest_value(sec_summary, "Shares Diluted", offset=1)
    repurchased = financial_engine.latest_value(sec_summary, "Shares Repurchased")

    result: dict = {
        "fiscalYear": year,
        "currency": currency,
        "amount": round(float(amount), 2),
        "history": financial_engine.annual_values(sec_summary, "Share Repurchases", limit=5),
    }

    if sbc and sbc > 0:
        result["stockBasedCompensation"] = round(float(sbc), 2)
        # 주식보상이 매입의 몇 %를 먹는가. 100%를 넘으면 매입해도 주식 수는 는다.
        result["offsetRatio"] = round(float(sbc) / float(amount), 3)
        result["offsetHeavy"] = result["offsetRatio"] >= _OFFSET_NOTE_THRESHOLD

    if shares_now and shares_prev and shares_prev > 0:
        # **주식 수가 실제로 줄었는가.** 매입의 결과는 여기서만 확인된다.
        result["dilutedShares"] = round(float(shares_now), 0)
        result["dilutedSharesChangePct"] = round((float(shares_now) / float(shares_prev) - 1) * 100, 2)

    if repurchased and repurchased > 0:
        # 있을 때만 낸다 — 등재하지 않는 회사가 많다.
        result["sharesRepurchased"] = round(float(repurchased), 0)
        result["averagePrice"] = round(float(amount) / float(repurchased), 2)

    if price and shares_now and price > 0 and shares_now > 0:
        market_cap = float(price) * float(shares_now)
        result["marketCap"] = round(market_cap, 2)
        result["buybackYieldPct"] = round(float(amount) / market_cap * 100, 2)

    return result


def render_buyback_quality(quality: dict) -> str:
    """생성 컨텍스트 블록. 금액만 주면 본문도 금액만 쓴다."""
    if not quality:
        return ""
    unit = quality.get("currency") or "통화 확인 필요"
    lines = [
        "## 자사주 매입의 질",
        "",
        f"- 최근 회계연도({quality.get('fiscalYear', '')}) 매입: {quality['amount']:,.0f} {unit}",
    ]
    if "buybackYieldPct" in quality:
        lines.append(f"- 매입 수익률(매입액 ÷ 시가총액): {quality['buybackYieldPct']}%")
    if "stockBasedCompensation" in quality:
        lines.append(
            f"- 주식보상비용: {quality['stockBasedCompensation']:,.0f} {unit} "
            f"(매입액의 {quality['offsetRatio'] * 100:.0f}%)"
        )
    if "dilutedSharesChangePct" in quality:
        change = quality["dilutedSharesChangePct"]
        lines.append(
            f"- 희석주식수 전년 대비: {change:+.2f}% "
            f"({'실제로 줄었습니다' if change < 0 else '줄지 않았습니다'})"
        )
    if "averagePrice" in quality:
        lines.append(
            f"- 평균 매입가: {quality['averagePrice']:,.2f} {unit} "
            f"({quality['sharesRepurchased']:,.0f}주)"
        )
    else:
        lines.append("- 평균 매입가: 회사가 매입 주식 수를 공시하지 않아 계산할 수 없습니다.")
    lines += [
        "",
        "- **금액만으로 주주환원을 평가하지 마세요.** 주식 수가 줄지 않았다면 그 매입은",
        "  환원이 아니라 주식보상 희석을 메운 것입니다. 위 세 값을 함께 놓고 쓰세요.",
        "- 판단은 본문이 합니다. 위 숫자는 계산 결과일 뿐 좋다·나쁘다를 말하지 않습니다.",
    ]
    return "\n".join(lines)


__all__ = ["build_buyback_quality", "render_buyback_quality"]
