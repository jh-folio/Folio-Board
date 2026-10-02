"""Scenario return mathematics (spec §3.2-§3.3): IRR and the three inversions.

Cash flows are annual: t = 0 is the reference price date, EPS_t = EPS_0 (1+g)^t,
DPS_t = EPS_t * payout, P_N = EPS_N * exitPE. Everything is Decimal at 28 digits.
`above_range` / `below_range` mark a solution outside the searched interval; they
are never clipped into a number.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, Overflow, ROUND_HALF_EVEN, localcontext

from .decimal_ops import number

ABOVE_RANGE = "above_range"
BELOW_RANGE = "below_range"
NOT_NEEDED = "not_needed"

IRR_LOW, IRR_HIGH, IRR_TOLERANCE, IRR_MAX_ITERATIONS = Decimal("-0.99"), Decimal("1.00"), Decimal("1e-10"), 200
GROWTH_LOW, GROWTH_HIGH, GROWTH_TOLERANCE = Decimal("-0.50"), Decimal("1.00"), Decimal("1e-8")
MARGIN_LOW, MARGIN_HIGH, MARGIN_TOLERANCE = Decimal(0), Decimal(1), Decimal("1e-8")


def eps_path(eps0, growth, years: int) -> list[Decimal]:
    base, rate = number(eps0), Decimal(1) + number(growth)
    return [base * rate ** t for t in range(1, years + 1)]


def cash_flows(price, eps0, growth, exit_pe, payout, years: int) -> list[Decimal]:
    """[-P0, DPS_1, ..., DPS_{N-1}, DPS_N + P_N]."""
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        eps = eps_path(eps0, growth, years)
        flows = [-number(price)] + [value * number(payout) for value in eps]
        flows[-1] += eps[-1] * number(exit_pe)
        return flows


def npv(flows, rate) -> Decimal:
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        factor = Decimal(1) + number(rate)
        return sum((flow / factor ** t for t, flow in enumerate(flows)), Decimal(0))


def irr(flows):
    """Bisection on [-0.99, 1.00], tolerance 1e-10, at most 200 iterations."""
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        low, high = IRR_LOW, IRR_HIGH
        f_low, f_high = npv(flows, low), npv(flows, high)
        if f_high > 0:
            return ABOVE_RANGE
        if f_low < 0:
            return BELOW_RANGE
        if f_high == 0:
            return high
        for _ in range(IRR_MAX_ITERATIONS):
            if high - low <= IRR_TOLERANCE:
                break
            mid = (low + high) / 2
            if npv(flows, mid) > 0:
                low = mid
            else:
                high = mid
        return (low + high) / 2


def scenario_irr(price, eps0, growth, exit_pe, payout, years: int):
    try:
        return irr(cash_flows(price, eps0, growth, exit_pe, payout, years))
    except (Overflow, InvalidOperation):  # an assumption far beyond the search range is a range state, never an error
        return ABOVE_RANGE


def required_exit_pe(price, eps0, growth, payout, years: int, target):
    """Exit PER at which the cash flows return exactly `target` (annual, fraction).

    not_needed: dividends alone already return the target (no non-positive PER).
    """
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        rate = Decimal(1) + number(target)
        if rate <= 0:
            raise ValueError("invalid_target_return")
        eps = eps_path(eps0, growth, years)
        dividends = sum((value * number(payout) / rate ** t for t, value in enumerate(eps, start=1)), Decimal(0))
        exit_price = (number(price) - dividends) * rate ** years
        if exit_price <= 0:
            return NOT_NEEDED
        return exit_price / eps[-1]


def _npv_for_growth(price, eps0, growth, exit_pe, payout, years, target):
    return npv(cash_flows(price, eps0, growth, exit_pe, payout, years), target)


def required_growth(price, eps0, exit_pe, payout, years: int, target):
    """EPS growth that returns `target`; NPV at the target is increasing in growth."""
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        if number(eps0) <= 0:
            raise ValueError("non_positive_base_eps")
        low, high = GROWTH_LOW, GROWTH_HIGH
        args = (price, eps0)
        if _npv_for_growth(*args, high, exit_pe, payout, years, target) < 0:
            return ABOVE_RANGE
        if _npv_for_growth(*args, low, exit_pe, payout, years, target) > 0:
            return BELOW_RANGE
        while high - low > GROWTH_TOLERANCE:
            mid = (low + high) / 2
            if _npv_for_growth(*args, mid, exit_pe, payout, years, target) < 0:
                low = mid
            else:
                high = mid
        return (low + high) / 2


def margin_path_flows(price, rps0, rps_growth, margin0, margin_n, exit_pe, payout, years: int) -> list[Decimal]:
    """Per-share revenue grows at a fixed rate; the margin moves in a straight line."""
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        base, rate, start, end = number(rps0), Decimal(1) + number(rps_growth), number(margin0), number(margin_n)
        flows = [-number(price)]
        eps_n = Decimal(0)
        for t in range(1, years + 1):
            eps_n = base * rate ** t * (start + (end - start) * t / years)
            flows.append(max(eps_n, Decimal(0)) * number(payout))
        flows[-1] += max(eps_n, Decimal(0)) * number(exit_pe)
        return flows


def required_margin(price, rps0, rps_growth, margin0, exit_pe, payout, years: int, target):
    """Margin in year N at which the path returns `target`; NPV never falls as it rises."""
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        if number(rps0) <= 0:
            raise ValueError("non_positive_revenue")

        def value(margin_n):
            return npv(margin_path_flows(price, rps0, rps_growth, margin0, margin_n, exit_pe, payout, years), target)

        low, high = MARGIN_LOW, MARGIN_HIGH
        if value(high) < 0:
            return ABOVE_RANGE
        if value(low) > 0:
            return BELOW_RANGE
        while high - low > MARGIN_TOLERANCE:
            mid = (low + high) / 2
            if value(mid) < 0:
                low = mid
            else:
                high = mid
        return (low + high) / 2
