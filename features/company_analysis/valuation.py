"""밸류에이션 시나리오의 **단일 출처**.

본문과 차트가 각자 계산하던 시절 한 보고서 안에 밸류에이션이 두 벌 존재했다(실측
HWM 2026-08-27):

    본문   EPS 5.54 × 30x / 45x / 60x   →  $166 / $249 / $332
    차트   EPS 4.081 × 54x / 73x / 94x  →  $222 / $296 / $385

EPS도 배수도 적정가도 전부 달랐고, 독자는 어느 쪽을 믿어야 할지 알 수 없었다. 게다가
차트의 계산법은 항등식이었다 — `forward_eps = trailing_eps × (1+성장률)`을 **trailing
기준 PER**에 곱하니 기본 시나리오가 정의상 `현재가 × (1+성장률)`이 되어, 어떤 회사든
"기본 시나리오는 상승"으로 나왔다.

여기서 한 번 계산하고 본문·차트가 그것을 읽는다.

경계:
- **배수는 여전히 가정이다.** 비교 기업·과거 밴드 자료가 없으면 근거를 만들 수 없다.
  그 사실을 객체가 스스로 밝히고(`multipleBasis`), 본문도 그렇게 쓰게 한다.
- **EPS 기준을 이름으로 남긴다.** 무엇을 EPS로 삼았는지 모르면 배수의 의미도 달라진다.
- 자료가 없으면 빈 dict를 돌려준다. 없는 것을 지어내지 않는다.
"""
from __future__ import annotations

# 배수 시나리오. 근거 자료가 없으므로 **현재 배수 대비 비율**로만 둔다.
# 절대 배수(30x/45x/60x)를 코드가 정하면 회사마다 뜻이 달라지고, 그 숫자가 어디서
# 왔는지 아무도 말할 수 없다.
_MULTIPLE_RATIOS = (("나쁜 경우", 0.70), ("기본", 1.00), ("좋은 경우", 1.30))

_EPS_BASIS_LABELS = {
    "trailing_diluted": "최근 회계연도 희석 EPS",
    "trailing_basic": "최근 회계연도 기본 EPS",
}


def build_valuation_scenarios(
    *,
    trailing_eps: float | None,
    price: float | None,
    growth: float | None,
    eps_basis: str = "trailing_diluted",
    currency: str = "USD",
) -> dict:
    """본문과 차트가 함께 읽는 시나리오 객체.

    **PER과 EPS의 기준을 맞춘다.** forward EPS에 trailing PER을 곱하면 기본 시나리오가
    항상 오른다 — 그것은 밸류에이션이 아니라 성장률을 다시 쓴 것이다. forward EPS를
    쓰면 forward PER을 쓰고, 그때 기본 시나리오는 정확히 현재가가 된다("지금 배수가
    유지되면 지금 가격").
    """
    if not trailing_eps or not price or trailing_eps <= 0 or price <= 0:
        return {}
    growth_rate = float(growth) if growth is not None else 0.05
    forward_eps = trailing_eps * (1 + growth_rate)
    if forward_eps <= 0:
        return {}
    forward_pe = price / forward_eps
    scenarios = [
        {
            "label": label,
            "per": round(forward_pe * ratio, 1),
            "eps": round(forward_eps, 3),
            "price": round(forward_eps * forward_pe * ratio, 2),
            "changePct": round((ratio - 1) * 100, 1),
        }
        for label, ratio in _MULTIPLE_RATIOS
    ]
    return {
        "currentPrice": round(price, 2),
        "currency": currency,
        "eps": {
            "value": round(forward_eps, 3),
            "basis": "forward_from_" + eps_basis,
            "label": f"{_EPS_BASIS_LABELS.get(eps_basis, eps_basis)}에 성장률 {growth_rate * 100:.1f}%를 적용한 추정",
            "trailing": round(trailing_eps, 3),
            "growth": round(growth_rate, 4),
        },
        "forwardPe": round(forward_pe, 1),
        # 배수의 출처를 반드시 남긴다. 근거가 없으면 없다고 적는다.
        "multipleBasis": "assumption_current_multiple_ratio",
        "multipleNote": "비교 기업·과거 배수 밴드 자료가 없어, 현재 배수 대비 비율(×0.7 / ×1.0 / ×1.3)로만 두었습니다.",
        "scenarios": scenarios,
    }


def render_valuation_contract(valuation: dict) -> str:
    """생성 컨텍스트에 실을 블록. 본문이 **다시 계산하지 못하게** 값을 통째로 준다."""
    scenarios = (valuation or {}).get("scenarios") or []
    if not scenarios:
        return ""
    eps = valuation.get("eps") or {}
    lines = [
        "## 밸류에이션 시나리오 (이 값을 그대로 쓰세요)",
        "",
        f"현재가 {valuation['currentPrice']:,} {valuation.get('currency', '')} · "
        f"Forward EPS {eps.get('value')} · Forward PER {valuation.get('forwardPe')}배",
        f"EPS 기준: {eps.get('label', '')}",
        "",
        "| 시나리오 | EPS | PER | 적정가 | 현재가 대비 |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in scenarios:
        lines.append(
            f"| {row['label']} | {row['eps']} | {row['per']}배 | "
            f"{row['price']:,} | {row['changePct']:+.1f}% |"
        )
    lines += [
        "",
        "- **이 표의 숫자를 다시 계산하지 마세요.** 화면의 차트가 같은 값을 그립니다 —",
        "  본문이 다른 EPS나 다른 배수를 쓰면 한 보고서가 두 가지 밸류에이션을 말하게 됩니다.",
        f"- {valuation.get('multipleNote', '')}",
        "  배수를 근거 있는 값처럼 쓰지 말고, 가정이라는 사실을 본문에도 밝히세요.",
        "- 다른 방식(EV/EBITDA, DCF 등)을 덧붙이는 것은 좋습니다. 다만 **PER 시나리오는**",
        "  위 표 하나만 씁니다.",
    ]
    return "\n".join(lines)


__all__ = ["build_valuation_scenarios", "render_valuation_contract"]
