from __future__ import annotations

try:
    import polars as pl
except Exception:  # pragma: no cover - optional dependency fallback
    pl = None


def annual_metric_frame(sec_summary: dict):
    rows = []
    for metric_row in sec_summary.get("rows", []) or []:
        metric = metric_row.get("metric", "")
        concept = metric_row.get("concept", "")
        for item in metric_row.get("annual", []) or []:
            try:
                value = float(item.get("val"))
            except Exception:
                continue
            year = str(str(item.get("end", ""))[:4] or item.get("fy") or "")
            if not year:
                continue
            rows.append({
                "metric": metric,
                "concept": concept,
                "year": year,
                "end": item.get("end", ""),
                "value": value,
            })
    if pl is not None:
        return pl.DataFrame(rows) if rows else pl.DataFrame(schema={"metric": pl.Utf8, "concept": pl.Utf8, "year": pl.Utf8, "end": pl.Utf8, "value": pl.Float64})
    return rows


def latest_value(sec_summary: dict, metric: str, offset: int = 0) -> float | None:
    frame = annual_metric_frame(sec_summary)
    if pl is not None:
        rows = (
            frame
            .filter(pl.col("metric") == metric)
            .sort(["end", "year"], descending=True)
            .select("value")
            .to_series()
            .to_list()
        )
    else:
        rows = [r["value"] for r in sorted([r for r in frame if r["metric"] == metric], key=lambda r: (r["end"], r["year"]), reverse=True)]
    if len(rows) <= offset:
        return None
    return rows[offset]


def latest_end(sec_summary: dict, metric: str) -> str:
    """그 지표의 가장 최근 연차 기준일. 없으면 빈 문자열."""
    for metric_row in (sec_summary or {}).get("rows", []) or []:
        if metric_row.get("metric") == metric:
            ends = [str(item.get("end") or "") for item in metric_row.get("annual", []) or []]
            return max(ends or [""])
    return ""


# 회사의 최신 회계연도는 손익·현금흐름의 핵심 지표가 말한다. 한 지표만 오래된 태그로
# 남으면(HWM: 이자비용 2023년, 배당 2015년) 그 값은 이 연도와 어긋난다.
_REFERENCE_FLOW_METRICS = ("Revenue", "Net Income", "Operating Cash Flow")


def reference_year(sec_summary: dict) -> str:
    years = [latest_year_value(sec_summary, metric)[1] for metric in _REFERENCE_FLOW_METRICS]
    return max([year for year in years if year] or [""])


def current_year_value(sec_summary: dict, metric: str) -> tuple[float | None, str, str]:
    """최신 회계연도의 값만 돌려준다: (값, 그 연도, 값이 오래됐으면 마지막 연도).

    오래된 값은 역사적 정보로는 남지만 **지금의** 비율·판단의 입력으로 쓰지 않는다.
    기준 연도를 알 수 없으면 판단하지 않고 최신 값을 그대로 쓴다.
    """
    value, year = latest_year_value(sec_summary, metric)
    reference = reference_year(sec_summary)
    if value is None:
        return None, "", ""
    if reference and year and year < reference:
        return None, reference, year
    return value, year, ""


def annual_values(sec_summary: dict, metric: str, limit: int = 5) -> list[float]:
    frame = annual_metric_frame(sec_summary)
    if pl is not None:
        return (
            frame
            .filter(pl.col("metric") == metric)
            .sort(["end", "year"], descending=True)
            .select("value")
            .head(limit)
            .to_series()
            .to_list()
        )
    return [r["value"] for r in sorted([r for r in frame if r["metric"] == metric], key=lambda r: (r["end"], r["year"]), reverse=True)[:limit]]


def annual_year_values(sec_summary: dict, metric: str) -> dict[str, float]:
    """연도 → 값. 같은 해끼리 빼려면 값에 연도가 붙어 있어야 한다."""
    frame = annual_metric_frame(sec_summary)
    if pl is not None:
        rows = frame.filter(pl.col("metric") == metric).sort(["end", "year"], descending=True).to_dicts()
    else:
        rows = sorted([r for r in frame if r["metric"] == metric], key=lambda r: (r["end"], r["year"]), reverse=True)
    out: dict[str, float] = {}
    for row in rows:
        year = str(row.get("year") or "")
        if year and year not in out:
            out[year] = float(row["value"])
    return out


def latest_year_value(sec_summary: dict, metric: str) -> tuple[float | None, str]:
    """최신 값과 그 값의 연도. 연도를 함께 돌려줘야 같은 해끼리만 뺄 수 있다."""
    values = annual_year_values(sec_summary, metric)
    for year, value in values.items():  # annual_year_values는 최신 연도부터 담는다
        return value, year
    return None, ""


def fcf_series(sec_summary: dict, limit: int = 5) -> list[float]:
    # 연도 키를 버리고 순서대로 빼면 2025년 CFO에서 2022년 CapEx를 빼는 일이
    # 생긴다. 두 지표의 보고 연도가 갈리는 제출사에서 실제로 발생한다.
    cfo = annual_year_values(sec_summary, "Operating Cash Flow")
    capex = annual_year_values(sec_summary, "Capital Expenditure")
    years = sorted(set(cfo) & set(capex), reverse=True)[:limit]
    return [cfo[year] - capex[year] for year in years]


def derived_financials(sec_summary: dict) -> dict:
    cfo = latest_value(sec_summary, "Operating Cash Flow")
    capex = latest_value(sec_summary, "Capital Expenditure")
    revenue = latest_value(sec_summary, "Revenue")
    pretax = latest_value(sec_summary, "Pretax Income")
    tax = latest_value(sec_summary, "Income Tax")
    # 이자비용은 최신 회계연도 값만, 부채는 **같은 해** 연말 잔액으로 나눈다. 2023년 이자를
    # 2025년 부채로 나눈 7.1%가 차입비용으로 할인율에 들어간 적이 있다(HWM 실측).
    interest, interest_year, _stale = current_year_value(sec_summary, "Interest Expense")
    debt = latest_value(sec_summary, "Long-Term Debt")
    debt_same_year = annual_year_values(sec_summary, "Long-Term Debt").get(interest_year) if interest_year else None
    cash = latest_value(sec_summary, "Cash & Equivalents")
    current_assets = latest_value(sec_summary, "Current Assets")
    current_liabilities = latest_value(sec_summary, "Current Liabilities")
    # 연도가 갈린 CFO와 CapEx를 빼면 어느 해의 것도 아닌 FCF가 된다. 같은 해일 때만 뺀다.
    cfo_value, cfo_year = latest_year_value(sec_summary, "Operating Cash Flow")
    capex_value, capex_year = latest_year_value(sec_summary, "Capital Expenditure")
    fcf = (
        cfo_value - capex_value
        if cfo_value is not None and capex_value is not None and cfo_year and cfo_year == capex_year
        else None
    )
    tax_rate = tax / pretax if tax is not None and pretax not in {None, 0} and pretax > 0 else None
    debt_cost = (
        interest / debt_same_year
        if interest is not None and debt_same_year not in {None, 0} and debt_same_year > 0
        else None
    )
    current_ratio = current_assets / current_liabilities if current_assets is not None and current_liabilities not in {None, 0} else None
    return {
        "revenue": revenue,
        "cfo": cfo,
        "capex": capex,
        "fcf": fcf,
        "fcfMargin": fcf / revenue if fcf is not None and revenue not in {None, 0} else None,
        "taxRate": tax_rate,
        "debtCost": debt_cost,
        "currentRatio": current_ratio,
        "cash": cash,
        "debt": debt,
    }


def growth_rate(values: list[float], fallback: float = 0.04) -> float:
    positives = [v for v in values if v and v > 0]
    if len(positives) < 2:
        return fallback
    recent = positives[0]
    old = positives[min(len(positives) - 1, 2)]
    if old <= 0:
        return fallback
    periods = min(len(positives) - 1, 2)
    try:
        cagr = (recent / old) ** (1 / periods) - 1
    except Exception:
        return fallback
    return max(-0.03, min(0.10, cagr))


# DCF는 `features/company_analysis/dcf.py`가 소유한다. 여기 있던 5년 평탄 모델은
# 모든 회사에 사실상 같은 답을 줬다(실측 5개사가 전부 "현재가의 37~62%"). 되살리지
# 않는다 — 두 벌이 있으면 어느 표가 어느 모델에서 왔는지 알 수 없게 된다.
