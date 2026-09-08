"""DCF — 정상화 기준 FCF, 회사별 할인율, 성장 감쇠, 역산 성장률.

예전 모델의 문제는 정교함이 아니라 **모든 회사에 같은 답을 준다**는 것이었다. 실측
5개사(2026-08-27, SEC companyfacts):

    회사    내재가치/주   현재가    터미널 비중   성장률(클램프 후)
    HWM     $70.61       $188     76.3%        10.0%  ← 상한에 물림
    NVDA    $85.45       $180     76.3%        10.0%  ← 상한에 물림(실제 FCF CAGR 89%)
    AAPL    $87.75       $230     72.3%        -0.4%
    MSFT    $108.61      $430     71.1%        -3.0%  ← 하한에 물림
    LRCX    $76.24        $95     75.3%         7.2%

다섯 곳 전부 "현재가의 37~62%"라고 말한다. 매번 심한 고평가를 말하는 모델은 판단의
재료가 아니라 상수다. 원인이 넷이었다.

1. **성장률이 사실상 상수였다.** `[-3%, +10%]` 클램프에 6개사 중 5개가 물렸다.
2. **성장이 5년 평탄 후 터미널로 급락했다.** 실제 기업은 그렇게 꺾이지 않는다.
3. **할인율이 9% 고정이었다.** 실측 부채비용은 3.03%(NVDA)~7.28%(MSFT)로 2.4배,
   세율은 12.1%~19.4%로 갈리는데 전부 같은 값을 받았다.
4. **기준 FCF가 최근 1년이었다.** NVDA 96.7B는 3년 중앙값 60.9B의 1.6배, HWM 1.43B는
   중앙값 0.98B의 1.5배다. 한 해가 회사 전체의 가치를 정했다.

그리고 가치의 71~76%가 터미널인데 **보고서 어디에도 그 사실이 없었다.** 사실상 5년
뒤 배수에 건 베팅인데 독자는 정밀한 현금흐름 모델을 봤다고 생각한다.

### 무엇을 바꿨나

- **기준 FCF를 정상화한다.** FCF 마진은 안정적인데(실측 3년 변동 NVDA 2.3%p, TSLA
  2.9%p, AAPL 4.1%p) FCF 금액은 아니다. 중앙값 마진 × 최근 매출을 쓴다.
- **성장은 매출에서 온다.** FCF 성장률은 매출과 심하게 어긋난다(실측 MSFT 매출 +10%
  vs FCF −3.0%, TSLA −1.0% vs +10%로 부호까지 반대). 정상화 FCF가 `마진 × 매출`이므로
  마진을 중앙값에 고정하면 성장의 출처는 매출이다 — 모델이 스스로와 일관된다.
- **성장을 감쇠시킨다.** 1년차 초기 성장률에서 마지막 해 영구성장률까지 선형으로
  내린다. 감쇠가 극단값을 스스로 눌러 주므로 클램프를 넓힐 수 있다.
- **명시적 예측 기간을 10년으로 늘렸다.** 5년이면 터미널 비중이 65~75%라 DCF가 사실상
  터미널 베팅이고, 고성장 기업 둘은 역산 성장률이 탐색 범위 밖으로 나가 답 자체가
  없었다. 10년에서는 47~60%로 내려가고 다섯 곳 모두 풀린다.
- **할인율을 회사별로 만든다.** 무위험수익률 + 베타×위험프리미엄, 세후 부채비용,
  시가 기준 가중. 입력이 없으면 예전 값으로 내려가되 **그 사실을 남긴다**.
- **터미널 비중을 공시한다.** 70%를 넘으면 그것이 무엇을 뜻하는지 함께 적는다.
- **베타를 블룸 조정한다.** 원시 베타를 CAPM에 그대로 넣으면 베타 2.12인 회사가
  할인율 14.8%를 받아 어떤 성장률로도 현재가가 설명되지 않는다.
- **역산 성장률을 낸다.** "현재가가 정당화되려면 성장률이 몇 %여야 하는가". 모델이
  "62% 고평가"라고 판정하는 것보다 "시장은 연 23% 성장을 가격에 넣고 있다"가 정보다
  — 그 숫자가 말이 되는지는 사업을 아는 사람이 판단한다(§5 원칙 4).

### 경계

- **무위험수익률과 위험프리미엄은 가정이다.** 통화별 상수이며 `assumptions`가 그 사실을
  밝힌다. 살아 있는 금리를 주입할 수 있게 인자로 열어 두되 여기서 조회하지 않는다.
- **판정하지 않는다.** 고평가·저평가를 말하지 않고 숫자와 그 숫자가 선 가정을 낸다.
- 입력이 없으면 계산하지 않는다. 채워 넣지 않는다.
"""
from __future__ import annotations

from statistics import median

from features.company_analysis import financial_engine

# 통화별 무위험수익률 가정. **살아 있는 값이 아니다** — 주입되면 그것을 쓴다.
# 근거는 `riskFreeSource`가 밝힌다.
#
# **기준일을 반드시 적는다.** 날짜 없는 상수는 몇 년이고 조용히 낡는다. 아래 값은
# 2026-08-27 실측(FRED `DGS10` 4.68%, `IRLTLT01{KR,JP,GB,DE}M156N`)보다 다섯 통화
# 모두 0.05~0.58%p 낮다 — 오차가 한 방향이면 노이즈가 아니라 편향이고, 낮은 무위험
# 수익률은 할인율을 낮춰 내재가치를 높인다(실측 USD 0.46%p가 내재가치 5.0~7.2%).
# 살아 있는 금리를 물리는 방법은 `plan/COMPANY_ANALYSIS_QUALITY_TRANSFER_PLAN.md` §9.
RISK_FREE_BY_CURRENCY = {"USD": 0.042, "KRW": 0.032, "EUR": 0.025, "JPY": 0.015, "GBP": 0.040}
_DEFAULT_RISK_FREE = 0.042
# 주식 위험프리미엄. 학계·실무 추정이 4~6%에 몰려 있어 가운데를 쓴다.
#
# **이 상수가 DCF에서 가장 큰 지렛대다.** 실측 MSFT 기준 시나리오가 ERP 4%에서 $379,
# 6%에서 $276으로 **37% 벌어진다.** 그런데 무료로 기계가 읽을 수 있는 ERP 출처가 없어
# 지금은 더 정확하게 만들 길이 없다 — 그래서 값을 맞히는 대신 **그 범위가 답을 얼마나
# 지배하는지를 가정 감도표(`assumptionSensitivity`)가 보여준다.** 하나의 숫자로 눌러
# 두면 독자는 그 숫자가 답을 얼마나 지배하는지 알 수 없다.
EQUITY_RISK_PREMIUM = 0.05
# 가정 감도의 탐색 범위. ERP는 "합리적인 사람들이 실제로 쓰는 범위"(4~6%)이고,
# 무위험은 실측 편향 크기(±0.5%p, 2026-08-27 다섯 통화 −0.05~−0.58%p)를 덮는다.
ERP_SENSITIVITY_RANGE = (0.04, 0.05, 0.06)
RISK_FREE_SENSITIVITY_STEP = 0.005
# 영구성장률은 장기 명목 성장을 넘을 수 없다. 넘으면 회사가 결국 경제보다 커진다.
TERMINAL_GROWTH_CAP = {"USD": 0.025, "KRW": 0.025, "EUR": 0.020, "JPY": 0.010, "GBP": 0.020}
_DEFAULT_TERMINAL_CAP = 0.020
# 감쇠가 극단값을 눌러 주므로 예전 `[-3%, +10%]`보다 넓게 잡는다. 그 좁은 띠에
# 6개사 중 5개가 물려 성장률이 사실상 상수였다.
GROWTH_FLOOR, GROWTH_CEILING = -0.10, 0.30
# **추정의 상한과 시나리오의 상한은 다르다.** 앞엣것은 3년 CAGR이 노이즈로 튀는 것을
# 막는 장치이고, 뒤엣것은 의도적인 what-if다. 같은 값을 쓰면 추정이 상한에 물린
# 회사에서 낙관 시나리오가 기준과 똑같아진다(실측 NVDA 둘 다 30.0%).
SCENARIO_CEILING = 0.45
SCENARIO_STEP = 0.05
# 할인율이 이 밖으로 나가면 입력이 이상한 것이다. 계산을 버리지 않고 가둔다.
DISCOUNT_FLOOR, DISCOUNT_CEILING = 0.06, 0.16
# 예전 고정 할인율. 입력이 없을 때 여기로 내려가되 그 사실을 남긴다.
FALLBACK_DISCOUNT_RATE = 0.09
# 이 비중을 넘으면 DCF가 현금흐름 모델이라기보다 터미널 가정에 건 베팅이다.
TERMINAL_SHARE_WARN = 0.70
# **명시적 예측 기간이 짧으면 DCF가 터미널 베팅이 된다.** 실측 5개사에서 5년이면
# 터미널 비중이 65~75%이고 고성장 기업 둘은 역산 성장률이 탐색 범위 밖으로 나가
# 답 자체가 없었다. 10년으로 늘리면 47~60%로 내려가고 다섯 곳 모두 풀린다
# (12.3%~47.6%). 성장 기업이 GDP 성장률로 5년 만에 꺾인다는 가정이 무리였다.
PROJECTION_YEARS = 10
# 블룸 조정. 베타는 1로 평균회귀하는 것이 실증적으로 확인돼 있어 실무(블룸버그
# `adjusted beta`)가 `2/3×원시 + 1/3×1`을 쓴다. 조정 없이 CAPM에 그대로 넣으면
# 원시 베타 2.12인 회사가 할인율 14.8%를 받아 어떤 성장률로도 현재가가 설명되지
# 않는다 — 모델이 답을 못 내는 것이지 그 회사가 그만큼 위험한 것이 아니다.
BETA_SHRINK, BETA_ANCHOR = 2 / 3, 1.0


def _positive(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def normalized_base_fcf(sec_summary: dict, *, years: int = 5) -> dict:
    """정상화 기준 FCF.

    **마진은 안정적이고 금액은 아니다.** 중앙값 FCF 마진에 최근 매출을 곱한다. 매출이
    없으면 FCF 중앙값으로 내려가고, 그것도 없으면 최근값을 쓴다 — 어느 쪽인지 `method`가
    말한다.
    """
    cfo = financial_engine.annual_year_values(sec_summary, "Operating Cash Flow")
    capex = financial_engine.annual_year_values(sec_summary, "Capital Expenditure")
    revenue = financial_engine.annual_year_values(sec_summary, "Revenue")
    aligned = sorted(set(cfo) & set(capex), reverse=True)[:years]
    if not aligned:
        return {}
    fcf_by_year = {year: cfo[year] - capex[year] for year in aligned}
    recent = fcf_by_year[aligned[0]]

    margins = [fcf_by_year[y] / revenue[y] for y in aligned if _positive(revenue.get(y))]
    latest_revenue = _positive(revenue.get(aligned[0]))
    result = {
        "recent": round(recent, 2),
        "recentYear": aligned[0],
        "years": len(aligned),
        "series": [round(fcf_by_year[y], 2) for y in aligned],
    }
    if len(margins) >= 2 and latest_revenue:
        margin = median(margins)
        result.update({
            "value": round(margin * latest_revenue, 2),
            "method": "median_margin",
            "medianMargin": round(margin, 4),
            "marginSpread": round(max(margins) - min(margins), 4),
            "revenue": round(latest_revenue, 2),
        })
    elif len(fcf_by_year) >= 2:
        result.update({"value": round(median(fcf_by_year.values()), 2), "method": "median_fcf"})
    else:
        result.update({"value": round(recent, 2), "method": "recent_only"})

    base = result["value"]
    # 정상화가 최근값과 크게 다르면 그 사실이 곧 판단 재료다.
    result["deviationFromRecent"] = round(base / recent - 1, 3) if recent else None
    return result


def growth_driver(sec_summary: dict) -> dict:
    """성장률과 그 출처.

    **매출을 먼저 본다.** FCF 성장률은 매출과 부호까지 어긋난다(실측 MSFT 매출 +10% vs
    FCF −3.0%). 정상화 FCF가 `중앙값 마진 × 매출`이므로 성장의 출처도 매출이어야
    모델이 스스로와 일관된다.
    """
    revenue = financial_engine.annual_values(sec_summary, "Revenue", limit=5)
    if len([v for v in revenue if v and v > 0]) >= 2:
        rate = _cagr(revenue)
        if rate is not None:
            return {"rate": round(rate, 4), "basis": "revenue_cagr"}
    fcf = financial_engine.fcf_series(sec_summary, limit=5)
    rate = _cagr(fcf)
    if rate is not None:
        return {"rate": round(rate, 4), "basis": "fcf_cagr"}
    return {"rate": 0.04, "basis": "fallback"}


def _cagr(values: list[float]) -> float | None:
    positives = [v for v in values if v and v > 0]
    if len(positives) < 2:
        return None
    periods = min(len(positives) - 1, 3)
    recent, old = positives[0], positives[periods]
    if old <= 0:
        return None
    try:
        rate = (recent / old) ** (1 / periods) - 1
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    return max(GROWTH_FLOOR, min(GROWTH_CEILING, rate))


def estimate_discount_rate(
    *,
    beta: float | None,
    tax_rate: float | None,
    debt_cost: float | None,
    market_cap: float | None,
    debt: float | None,
    currency: str = "USD",
    risk_free: float | None = None,
    equity_risk_premium: float | None = None,
) -> dict:
    """회사별 WACC. 입력이 없으면 예전 고정값으로 내려가되 그 사실을 남긴다."""
    unit = (currency or "USD").upper()
    rf = risk_free if risk_free is not None else RISK_FREE_BY_CURRENCY.get(unit, _DEFAULT_RISK_FREE)
    rf_source = "injected" if risk_free is not None else f"assumption_{unit}"
    erp = equity_risk_premium if equity_risk_premium is not None else EQUITY_RISK_PREMIUM
    cap = _positive(market_cap)
    if beta is None or cap is None:
        return {
            "rate": FALLBACK_DISCOUNT_RATE,
            "method": "fallback_fixed",
            "missing": [
                name for name, value in (("beta", beta), ("marketCap", cap)) if value is None
            ],
            "riskFree": rf,
            "riskFreeSource": rf_source,
        }

    adjusted_beta = BETA_SHRINK * float(beta) + (1 - BETA_SHRINK) * BETA_ANCHOR
    equity_cost = rf + adjusted_beta * erp
    debt_value = _positive(debt) or 0.0
    total = cap + debt_value
    if debt_value and debt_cost is not None:
        # 이자는 손비라 세후로 본다. 세율이 없으면 차감하지 않는다(할인율을 낮추는
        # 쪽으로 추측하지 않는다).
        after_tax = float(debt_cost) * (1 - float(tax_rate)) if tax_rate is not None else float(debt_cost)
        rate = (cap / total) * equity_cost + (debt_value / total) * after_tax
    else:
        after_tax = None
        rate = equity_cost

    bounded = max(DISCOUNT_FLOOR, min(DISCOUNT_CEILING, rate))
    return {
        "rate": round(bounded, 4),
        "method": "wacc",
        "beta": round(float(beta), 3),
        "adjustedBeta": round(adjusted_beta, 3),
        "equityCost": round(equity_cost, 4),
        "afterTaxDebtCost": round(after_tax, 4) if after_tax is not None else None,
        "equityWeight": round(cap / total, 3),
        "riskFree": rf,
        "riskFreeSource": rf_source,
        "equityRiskPremium": erp,
        "clamped": abs(bounded - rate) > 1e-9,
    }


def terminal_growth_for(currency: str, discount_rate: float) -> float:
    """영구성장률. 장기 명목 성장과 할인율 둘 다에 갇힌다."""
    cap = TERMINAL_GROWTH_CAP.get((currency or "USD").upper(), _DEFAULT_TERMINAL_CAP)
    # 영구성장이 할인율에 가까우면 터미널이 발산한다. 넉넉히 떼어 놓는다.
    return round(min(cap, max(0.0, discount_rate - 0.03)), 4)


def fade_path(near_growth: float, terminal_growth: float, years: int = PROJECTION_YEARS) -> list[float]:
    """1년차 초기 성장률에서 마지막 해 영구성장률까지 선형 감쇠.

    평탄하게 5년을 두고 터미널에서 급락시키면 6년차에 불연속이 생긴다. 감쇠는
    표준이면서 극단적인 초기 성장률을 스스로 눌러 준다.
    """
    if years <= 1:
        return [terminal_growth]
    step = (near_growth - terminal_growth) / (years - 1)
    return [round(near_growth - step * i, 5) for i in range(years)]


def dcf_value(
    base_fcf: float,
    net_debt: float,
    shares: float,
    near_growth: float,
    discount_rate: float,
    terminal_growth: float,
    years: int = PROJECTION_YEARS,
) -> dict:
    """감쇠 경로를 따라 현금흐름을 할인한다. 터미널 비중을 함께 낸다."""
    if base_fcf <= 0 or shares <= 0 or discount_rate <= terminal_growth:
        return {"ok": False}
    projected, pv_fcf, fcf = [], 0.0, float(base_fcf)
    for index, rate in enumerate(fade_path(near_growth, terminal_growth, years), start=1):
        fcf *= 1 + rate
        pv = fcf / ((1 + discount_rate) ** index)
        projected.append({"year": index, "growth": rate, "fcf": fcf, "pv": pv})
        pv_fcf += pv
    terminal_value = projected[-1]["fcf"] * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / ((1 + discount_rate) ** years)
    enterprise_value = pv_fcf + pv_terminal
    equity_value = enterprise_value - net_debt
    return {
        "ok": True,
        "projected": projected,
        "pvFcf": pv_fcf,
        "terminalValue": terminal_value,
        "pvTerminal": pv_terminal,
        "enterpriseValue": enterprise_value,
        "equityValue": equity_value,
        "perShare": equity_value / shares,
        # 가치의 몇 %가 6년차 이후 가정에서 오는가. 숨기면 독자는 정밀한 현금흐름
        # 모델을 봤다고 생각한다.
        "terminalShare": pv_terminal / enterprise_value if enterprise_value else None,
    }


def implied_growth(
    price: float,
    base_fcf: float,
    net_debt: float,
    shares: float,
    discount_rate: float,
    terminal_growth: float,
    years: int = PROJECTION_YEARS,
) -> dict:
    """현재가를 정당화하는 초기 성장률.

    모델이 "62% 고평가"라고 판정하는 것보다 "시장은 연 23% 성장을 가격에 넣고 있다"가
    정보다 — 그 숫자가 말이 되는지는 사업을 아는 사람이 판단한다(§5 원칙 4).
    """
    if price <= 0 or base_fcf <= 0 or shares <= 0:
        return {}

    def per_share(growth: float) -> float | None:
        row = dcf_value(base_fcf, net_debt, shares, growth, discount_rate, terminal_growth, years)
        return row.get("perShare") if row.get("ok") else None

    low, high = -0.30, 1.50
    low_value, high_value = per_share(low), per_share(high)
    if low_value is None or high_value is None:
        return {}
    if price < low_value:
        return {"status": "below_range", "bound": round(low, 4)}
    if price > high_value:
        return {"status": "above_range", "bound": round(high, 4)}
    for _ in range(60):  # 이분법. 단조 증가라 수렴이 보장된다.
        mid = (low + high) / 2
        value = per_share(mid)
        if value is None:
            return {}
        if value < price:
            low = mid
        else:
            high = mid
    return {"status": "solved", "growth": round((low + high) / 2, 4)}


def net_debt_from(sec_summary: dict) -> dict:
    """순부채. **단기차입을 빼먹지 않는다.**

    장기부채만 보면 유동성 차입이 많은 회사의 부채가 통째로 사라진다.
    """
    long_term = financial_engine.latest_value(sec_summary, "Long-Term Debt") or 0.0
    short_term = financial_engine.latest_value(sec_summary, "Short-Term Debt") or 0.0
    cash = financial_engine.latest_value(sec_summary, "Cash & Equivalents") or 0.0
    return {
        "netDebt": round(long_term + short_term - cash, 2),
        "longTermDebt": round(long_term, 2),
        "shortTermDebt": round(short_term, 2),
        "cash": round(cash, 2),
        "totalDebt": round(long_term + short_term, 2),
    }


def assumption_sensitivity(
    *,
    discount: dict,
    base_fcf: float,
    net_debt: float,
    shares: float,
    near_growth: float,
    currency: str,
    price: float | None,
    discount_inputs: dict,
) -> list[dict]:
    """무위험수익률·ERP가 답을 얼마나 지배하는지의 감도표 (§9.4).

    **두 입력을 더 정확하게 만드는 것보다 그 입력이 답을 얼마나 지배하는지 보이는
    쪽이 먼저다.** 실측 ERP 4~6%가 MSFT 내재가치를 $276~$379(37%)로 흔드는데 지금까지
    그 폭이 하나의 숫자에 눌려 보이지 않았다. 역산 성장률도 같은 이유로 밴드로 낸다 —
    "시장이 가격에 넣은 성장률"이 ERP 가정에 따라 얼마나 다르게 읽히는지가 정보다.

    WACC 경로에서만 의미가 있다(고정 할인율은 두 입력을 읽지 않는다). 시나리오 표
    (성장률)·민감도 표(할인율·영구성장)와 겹치지 않게 **기준 성장률만 쓴다.**
    """
    if discount.get("method") != "wacc":
        return []
    rf = float(discount["riskFree"])
    erp_used = float(discount["equityRiskPremium"])
    variants = [
        {"axis": "riskFree", "riskFree": rf - RISK_FREE_SENSITIVITY_STEP, "erp": erp_used},
        {"axis": "base", "riskFree": rf, "erp": erp_used},
        {"axis": "riskFree", "riskFree": rf + RISK_FREE_SENSITIVITY_STEP, "erp": erp_used},
    ] + [
        {"axis": "erp", "riskFree": rf, "erp": erp}
        for erp in ERP_SENSITIVITY_RANGE
        if abs(erp - erp_used) > 1e-9
    ]
    rows = []
    for variant in variants:
        row_discount = estimate_discount_rate(
            **discount_inputs, risk_free=variant["riskFree"], equity_risk_premium=variant["erp"],
        )
        rate = row_discount["rate"]
        terminal = terminal_growth_for(currency, rate)
        value = dcf_value(base_fcf, net_debt, shares, near_growth, rate, terminal)
        row = {
            "axis": variant["axis"],
            "riskFree": round(variant["riskFree"], 4),
            "equityRiskPremium": round(variant["erp"], 4),
            "discountRate": rate,
            # 상·하한에 물린 행을 표시 없이 내면, 모든 행이 같은 값일 때 "가정이
            # 무관하다"로 읽힌다 — 실제로는 모델이 경계에 눌린 것이다.
            "clamped": bool(row_discount.get("clamped")),
            "perShare": round(value["perShare"], 2) if value.get("ok") else None,
        }
        if _positive(price):
            implied = implied_growth(float(price), base_fcf, net_debt, shares, rate, terminal)
            if implied.get("status") == "solved":
                row["impliedGrowth"] = implied["growth"]
        rows.append(row)
    return rows


def build_dcf(
    sec_summary: dict,
    *,
    price: float | None = None,
    shares: float | None = None,
    market_cap: float | None = None,
    beta: float | None = None,
    currency: str = "USD",
    risk_free: float | dict | None = None,
) -> dict:
    """정상화 → 할인율 → 감쇠 → 시나리오 → 역산. 하나라도 빠지면 빈 dict.

    `risk_free`는 소수(0.0466) 또는 `risk_free.current_risk_free()`의 meta dict
    (`{"rate", "source", "asOf", ...}`)를 받는다. dict로 받으면 출처를 결과의
    `riskFreeMeta`에 **이 함수가** 싣는다 — 호출부 두 곳이 각자 사후 주입하던 시절,
    한쪽은 markdown만 반환하는 함수라 그 기록이 어디에도 남지 않았다.
    """
    risk_free_meta = risk_free if isinstance(risk_free, dict) else None
    if risk_free_meta is not None:
        risk_free = risk_free_meta.get("rate")
    if risk_free is not None:
        try:
            risk_free = float(risk_free)
        except (TypeError, ValueError):
            risk_free = None
    base = normalized_base_fcf(sec_summary)
    base_value = _positive(base.get("value"))
    share_count = _positive(shares) or _positive(financial_engine.latest_value(sec_summary, "Shares Diluted"))
    if not base_value or not share_count:
        return {"ok": False, "reason": "insufficient_inputs", "baseFcf": base}

    derived = financial_engine.derived_financials(sec_summary)
    debt = net_debt_from(sec_summary)
    cap = _positive(market_cap) or (_positive(price) * share_count if _positive(price) else None)
    discount_inputs = {
        "beta": beta,
        "tax_rate": derived.get("taxRate"),
        "debt_cost": derived.get("debtCost"),
        "market_cap": cap,
        "debt": debt["totalDebt"],
        "currency": currency,
    }
    discount = estimate_discount_rate(**discount_inputs, risk_free=risk_free)
    rate = discount["rate"]
    terminal = terminal_growth_for(currency, rate)
    growth = growth_driver(sec_summary)

    # **시나리오는 사업 가정만 흔든다.** 성장·할인율·영구성장을 한꺼번에 움직이면
    # 세 가정이 같은 방향으로 겹쳐 범위가 인위적으로 넓어지고, 무엇 때문에 차이가
    # 났는지 알 수 없다. 평가 가정(할인율·영구성장)은 민감도 표가 맡는다.
    near = growth["rate"]
    cases = [
        ("보수", max(GROWTH_FLOOR, near - SCENARIO_STEP)),
        ("기준", near),
        ("낙관", min(SCENARIO_CEILING, near + SCENARIO_STEP)),
    ]
    scenarios = []
    for name, case_growth in cases:
        row = dcf_value(base_value, debt["netDebt"], share_count, case_growth, rate, terminal)
        scenarios.append({
            "name": name,
            "growth": round(case_growth, 4),
            "discount": rate,
            "terminal": terminal,
            **{k: v for k, v in row.items() if k != "projected"},
        })

    base_case = next((row for row in scenarios if row["name"] == "기준"), {})
    result = {
        "ok": bool(base_case.get("ok")),
        "baseFcf": base,
        "netDebt": debt,
        "shares": round(share_count, 0),
        "currency": currency,
        "discountRate": discount,
        "terminalGrowth": terminal,
        "growth": growth,
        "fadePath": fade_path(near, terminal),
        "scenarios": scenarios,
        "terminalShare": base_case.get("terminalShare"),
        "terminalHeavy": bool(
            base_case.get("terminalShare") and base_case["terminalShare"] >= TERMINAL_SHARE_WARN
        ),
        "assumptionSensitivity": assumption_sensitivity(
            discount=discount,
            base_fcf=base_value,
            net_debt=debt["netDebt"],
            shares=share_count,
            near_growth=near,
            currency=currency,
            price=price,
            discount_inputs=discount_inputs,
        ),
    }
    if risk_free_meta is not None:
        result["riskFreeMeta"] = dict(risk_free_meta)
    if _positive(price):
        result["price"] = round(float(price), 2)
        result["impliedGrowth"] = implied_growth(
            float(price), base_value, debt["netDebt"], share_count, rate, terminal,
        )
    return result


def render_dcf_context(dcf: dict) -> str:
    """생성 컨텍스트 블록. 숫자와 **그 숫자가 선 가정**을 함께 준다."""
    if not dcf or not dcf.get("ok"):
        if (dcf or {}).get("status") == "unavailable":
            return "\n".join([
                "## DCF",
                "",
                f"- 계산하지 않음 — {dcf.get('reason') or '필요한 단위 정보를 확인하지 못했습니다.'}",
                "- 계산하지 않은 내재가치·현재가 비교 숫자를 추정하거나 다시 계산하지 마세요.",
            ])
        return ""
    unit = dcf.get("currency") or "USD"
    base, discount = dcf["baseFcf"], dcf["discountRate"]
    lines = [
        "## DCF (이 값을 그대로 쓰세요)",
        "",
        f"- 기준 FCF: {base['value']:,.0f} {unit} — {_BASE_METHOD_LABELS.get(base.get('method'), base.get('method'))}",
    ]
    if base.get("deviationFromRecent") is not None:
        lines.append(
            f"  최근 연도 실제 FCF {base['recent']:,.0f} 대비 {base['deviationFromRecent'] * 100:+.1f}%"
        )
    if discount["method"] == "wacc":
        lines.append(
            f"- 할인율 {discount['rate'] * 100:.1f}% (WACC) — 무위험 {discount['riskFree'] * 100:.1f}% + "
            f"조정베타 {discount['adjustedBeta']}(원시 {discount['beta']})×{discount['equityRiskPremium'] * 100:.0f}%, "
            f"자기자본 비중 {discount['equityWeight'] * 100:.0f}%"
        )
    else:
        lines.append(
            f"- 할인율 {discount['rate'] * 100:.1f}% — **회사별 계산에 실패해 고정값을 썼습니다**"
            f"(없는 입력: {', '.join(discount.get('missing') or []) or '알 수 없음'})"
        )
    lines += [
        f"- 영구성장률 {dcf['terminalGrowth'] * 100:.1f}% · 성장률 {dcf['growth']['rate'] * 100:.1f}%"
        f"({_GROWTH_BASIS_LABELS.get(dcf['growth']['basis'], dcf['growth']['basis'])})",
        f"- 성장 감쇠 경로({len(dcf['fadePath'])}년): "
        + " → ".join(f"{g * 100:.1f}%" for g in dcf["fadePath"][:3])
        + f" … {dcf['fadePath'][-1] * 100:.1f}%",
        "",
        "| 시나리오 | 초기 성장률 | 자기자본가치 | 내재가치/주 |",
        "|---|---:|---:|---:|",
    ]
    for row in dcf["scenarios"]:
        if row.get("ok"):
            lines.append(
                f"| {row['name']} | {row['growth'] * 100:.1f}% | {row['equityValue']:,.0f} | {row['perShare']:,.2f} |"
            )
        else:
            lines.append(f"| {row['name']} | {row['growth'] * 100:.1f}% | 계산 불가 | 계산 불가 |")

    lines.append("")
    share = dcf.get("terminalShare")
    if share is not None:
        lines.append(f"- **터미널 비중 {share * 100:.0f}%** — 가치의 그만큼이 6년차 이후 가정에서 옵니다.")
        if dcf.get("terminalHeavy"):
            lines.append(
                "  절반을 크게 넘으므로 이 DCF는 현금흐름 추정이라기보다 영구성장률 가정에"
                " 건 값입니다. 본문에 그 사실을 밝히세요."
            )
    implied = dcf.get("impliedGrowth") or {}
    if implied.get("status") == "solved":
        lines.append(
            f"- **역산 성장률 {implied['growth'] * 100:.1f}%** — 현재가 {dcf['price']:,.2f} {unit}가"
            f" 정당화되려면 초기 FCF 성장률이 이 값이어야 합니다."
        )
        lines.append(
            "  이 숫자가 그 회사의 사업으로 가능한지를 근거를 들어 논하세요. **적정가와"
            " 현재가를 비교해 고평가·저평가라고 단정하지 마세요** — DCF는 가정 위에 섰고"
            " 위 항목이 그 가정입니다."
        )
    elif implied.get("status") in {"above_range", "below_range"}:
        lines.append(
            f"- 역산 성장률: 탐색 범위(±{abs(implied['bound']) * 100:.0f}%) 밖이라 풀리지 않습니다."
            " 현재가가 이 모델의 가정과 크게 어긋난다는 뜻이며, 그 자체를 본문에 적으세요."
        )
    sensitivity = dcf.get("assumptionSensitivity") or []
    if sensitivity:
        lines += [
            "",
            "가정 감도 — 무위험수익률·위험프리미엄은 가정이며, 아래가 그 가정이 답을 움직이는 폭입니다"
            "(기준 시나리오 성장률 고정):",
            "",
            "| 가정 | 할인율 | 내재가치/주 | 역산 성장률 |",
            "|---|---:|---:|---:|",
        ]
        for row in sensitivity:
            per_share = f"{row['perShare']:,.2f}" if row.get("perShare") is not None else "계산 불가"
            implied_cell = (
                f"{row['impliedGrowth'] * 100:.1f}%" if row.get("impliedGrowth") is not None else "—"
            )
            lines.append(
                f"| {assumption_row_label(row)} | {row['discountRate'] * 100:.1f}% | {per_share} | {implied_cell} |"
            )
        if sensitivity_band_collapsed(sensitivity):
            lines.append(
                "  **모든 행의 할인율이 모델의 상·하한에 물려 같습니다.** 이 표에서 두"
                " 가정의 영향을 읽을 수 없다는 뜻이지, 가정이 무관하다는 뜻이 아닙니다."
                " 그 사실을 본문에 적으세요."
            )
        else:
            lines.append(
                "  내재가치 하나가 아니라 이 **범위**를 본문에 쓰세요. 범위가 현재가를 걸치면"
                " 그 사실 자체가 결론입니다."
            )
    lines.append("- 이 표를 다시 계산하지 마세요. 화면의 차트가 같은 값을 씁니다.")
    return "\n".join(lines)


def assumption_row_label(row: dict) -> str:
    """감도 행의 라벨. **axis 어휘는 이 모듈이 소유한다** — 렌더러 두 곳(LLM 컨텍스트·
    규칙 보고서)이 각자 분기하면 같은 행이 두 이름을 갖고, 새 축이 생기면 catch-all
    else가 그것을 ERP로 잘못 부른다."""
    axis = row.get("axis")
    if axis == "base":
        return "기준"
    if axis == "riskFree":
        return f"무위험 {float(row.get('riskFree') or 0) * 100:.1f}%"
    if axis == "erp":
        return f"ERP {float(row.get('equityRiskPremium') or 0) * 100:.1f}%"
    return str(axis or "?")


def sensitivity_band_collapsed(rows: list[dict]) -> bool:
    """모든 행이 클램프에 물려 같은 할인율이면 이 표는 범위를 말하지 못한다."""
    if not rows:
        return False
    return all(row.get("clamped") for row in rows) and len(
        {row.get("discountRate") for row in rows}
    ) == 1


_BASE_METHOD_LABELS = {
    "median_margin": "3년 이상 FCF 마진 중앙값 × 최근 매출로 정상화",
    "median_fcf": "매출을 못 읽어 FCF 중앙값으로 정상화",
    "recent_only": "연도가 하나뿐이라 최근값 그대로",
}
_GROWTH_BASIS_LABELS = {
    "revenue_cagr": "매출 CAGR",
    "fcf_cagr": "매출을 못 읽어 FCF CAGR",
    "fallback": "자료 부족으로 기본값",
}

__all__ = [
    "assumption_row_label",
    "assumption_sensitivity",
    "build_dcf",
    "sensitivity_band_collapsed",
    "dcf_value",
    "estimate_discount_rate",
    "fade_path",
    "growth_driver",
    "implied_growth",
    "net_debt_from",
    "normalized_base_fcf",
    "render_dcf_context",
    "terminal_growth_for",
]
