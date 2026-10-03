"""Hand-computed checks for percentiles, IRR and the three inversions (spec §6-3)."""
import math
import unittest
from decimal import Decimal as D

from features.price_scenarios import returns as r
from features.price_scenarios.stats import ABOVE_SAMPLE, BELOW_SAMPLE, inverse_percentile, percentile


class PercentileTests(unittest.TestCase):
    def test_type7_odd_even_small_and_tied_samples(self):
        self.assertEqual([percentile([1, 2, 3, 4, 5], p) for p in ("0.25", "0.5", "0.75")], [2, 3, 4])
        self.assertEqual([percentile([40, 10, 20], p) for p in ("0.25", "0.5", "0.75")], [15, 20, 30])
        self.assertEqual([percentile([1, 2, 3, 10], p) for p in ("0.25", "0.5", "0.75")], [D("1.75"), D("2.5"), D("4.75")])
        self.assertEqual(percentile([5, 5, 5, 5, 9], "0.25"), 5)
        self.assertEqual(percentile(["0.1", "0.3"], "0.5"), D("0.2"))

    def test_inverse_interpolates_and_reports_outside_the_sample(self):
        sample = [1, 2, 3, 4, 5]
        self.assertEqual(inverse_percentile(sample, "2.5"), D("37.5"))
        self.assertEqual(inverse_percentile(sample, 3), 50)
        self.assertEqual(inverse_percentile(sample, 1), 0)
        self.assertEqual(inverse_percentile(sample, 5), 100)
        self.assertEqual((inverse_percentile(sample, "0.5"), inverse_percentile(sample, 6)), (BELOW_SAMPLE, ABOVE_SAMPLE))
        self.assertEqual(inverse_percentile([1, 5, 5, 5, 9], 5), 50)  # a tied run is one place: its middle

    def test_inverse_is_consistent_with_percentile(self):
        sample = ["0.02", "0.05", "0.11", "0.2", "0.31", "0.4"]
        for p in ("0.25", "0.5", "0.75"):
            self.assertEqual(inverse_percentile(sample, percentile(sample, p)).quantize(D("1e-20")), D(p) * 100)

    def test_invalid_input_is_rejected(self):
        for call in (lambda: percentile([], "0.5"), lambda: percentile([1], "1.5"), lambda: percentile(["x"], "0.5")):
            with self.assertRaises(ValueError):
                call()


class IrrTests(unittest.TestCase):
    def assertRate(self, value, expected, places=9):
        self.assertIsInstance(value, D)
        self.assertAlmostEqual(float(value), expected, places=places)

    def test_par_bond_style_flows_return_the_dividend_yield(self):
        # P0=100, EPS 10 flat, payout 50%, exit PER 10: DPS 5 a year and 100 back.
        for years in (1, 2, 10):
            self.assertRate(r.scenario_irr(100, 10, 0, 10, "0.5", years), 0.05)

    def test_growth_only_return_is_the_compound_rate(self):
        self.assertRate(r.scenario_irr(100, 10, "0.1", 10, 0, 2), 0.1)       # 121 / 100 over two years
        self.assertRate(r.scenario_irr(100, 10, "0.1", 15, 0, 1), 0.65)      # 11 x 15 = 165
        self.assertRate(r.scenario_irr(100, 10, "0.1", 10, 0, 5), 0.1)       # 161.05 / 100 over five years

    def test_five_year_value_matches_closed_form(self):
        expected = (10 * 1.1 ** 5 * 10 / 100) ** (1 / 5) - 1
        self.assertRate(r.scenario_irr(100, 10, "0.1", 10, 0, 5), expected)

    def test_outside_the_search_interval_is_a_state_not_a_clipped_number(self):
        self.assertEqual(r.scenario_irr(10, 10, 0, 50, 0, 1), r.ABOVE_RANGE)       # 4900%
        self.assertEqual(r.scenario_irr(1000, "0.001", 0, 1, 0, 1), r.BELOW_RANGE)  # almost total loss
        self.assertRate(r.scenario_irr(10, 10, 0, 1, 0, 1), 0.0)             # price back unchanged: exactly 0%

    def test_flows_have_the_documented_shape(self):
        flows = r.cash_flows(100, 10, 0, 10, "0.5", 3)
        self.assertEqual(flows, [-100, 5, 5, 105])

    def test_bisection_agrees_with_an_independent_float_solver(self):
        flows = [float(x) for x in r.cash_flows("83.5", "6.2", "0.07", "17.5", "0.3", 10)]
        low, high = -0.99, 1.0
        for _ in range(200):
            mid = (low + high) / 2
            value = sum(f / (1 + mid) ** t for t, f in enumerate(flows))
            low, high = (mid, high) if value > 0 else (low, mid)
        self.assertRate(r.scenario_irr("83.5", "6.2", "0.07", "17.5", "0.3", 10), (low + high) / 2, places=8)


class InversionTests(unittest.TestCase):
    def test_exit_pe_for_zero_and_positive_targets(self):
        self.assertEqual(r.required_exit_pe(100, 10, 0, "0.5", 2, 0), 9)         # 100 - (5 + 5) back at PER 9
        self.assertAlmostEqual(float(r.required_exit_pe(100, 10, 0, "0.5", 1, "0.1")), 10.5, places=9)
        self.assertEqual(r.required_exit_pe(100, 10, 0, 1, 10, 0), r.NOT_NEEDED)  # dividends alone return the price

    def test_exit_pe_round_trips_through_the_irr(self):
        pe = r.required_exit_pe("57.3", "4.1", "0.06", "0.25", 10, "0.08")
        self.assertAlmostEqual(float(r.scenario_irr("57.3", "4.1", "0.06", pe, "0.25", 10)), 0.08, places=8)

    def test_required_growth(self):
        self.assertAlmostEqual(float(r.required_growth(100, 10, 10, 0, 1, "0.1")), 0.1, places=7)
        self.assertEqual(r.required_growth(100000, 10, 10, 0, 1, "0.1"), r.ABOVE_RANGE)
        self.assertEqual(r.required_growth("0.01", 10, 10, 0, 1, "0.1"), r.BELOW_RANGE)
        with self.assertRaises(ValueError):
            r.required_growth(100, 0, 10, 0, 1, "0.1")

    def test_required_growth_round_trips_through_the_irr(self):
        g = r.required_growth("57.3", "4.1", "13", "0.25", 10, "0.09")
        self.assertAlmostEqual(float(r.scenario_irr("57.3", "4.1", g, "13", "0.25", 10)), 0.09, places=7)

    def test_required_margin(self):
        # RPS 100 flat, margin 10% now, exit PER 10, no payout: P_1 = 100 * m * 10 = 100 -> m = 10%.
        self.assertAlmostEqual(float(r.required_margin(100, 100, 0, "0.1", 10, 0, 1, 0)), 0.1, places=7)
        self.assertEqual(r.required_margin(1000000, 100, 0, "0.1", 10, 0, 1, 0), r.ABOVE_RANGE)
        # Rich payouts on a high margin path already return more than the price even if the final margin is 0.
        self.assertEqual(r.required_margin(10, 100, 0, "0.5", 10, 1, 2, 0), r.BELOW_RANGE)
        with self.assertRaises(ValueError):
            r.required_margin(100, 0, 0, "0.1", 10, 0, 1, 0)

    def test_margin_path_is_straight_and_floors_losses_at_zero(self):
        flows = r.margin_path_flows(100, 100, 0, "0.1", "-0.1", 10, 1, 2)
        # t=1 margin 0 -> EPS 0 ; t=2 margin -0.1 -> EPS -10, floored to 0 for dividends and exit value.
        self.assertEqual(flows, [-100, 0, 0])


if __name__ == "__main__":
    unittest.main()
