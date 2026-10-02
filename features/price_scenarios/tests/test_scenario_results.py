"""Ranges, decomposition and the assembled scenario blocks on synthetic histories."""
import json
import math
import unittest
from decimal import Decimal as D

from features.price_scenarios import ranges as rng
from features.price_scenarios.decomposition import decompose
from features.price_scenarios.scenarios import compute


def history(years, **series):
    """series: metric -> callable(year) -> value or None. Every row ends on Dec 31."""
    rows = []
    for year in years:
        for metric, fn in series.items():
            value = fn(year)
            if value is not None:
                rows.append({"fiscalYear": year, "metric": metric, "value": str(value),
                             "period": {"start": f"{year}-01-01", "end": f"{year}-12-31"}})
    return {"rows": rows, "excludedYears": [], "currency": "USD", "sharesBasis": "diluted_weighted_average"}


def steady(years=range(2015, 2025), growth=D("1.1"), margin=D("0.1"), payout=D("0.3"), pe=15, shares=100):
    eps = lambda y: growth ** (y - 2015)
    return history(years, **{"EPS Diluted": eps, "Shares Diluted": lambda y: shares,
                             "Net Income": lambda y: eps(y) * shares, "Revenue": lambda y: eps(y) * shares / margin,
                             "DPS": lambda y: eps(y) * payout}), {y: eps(y) * pe for y in years}


def closes(prices):
    return [{"fiscalYear": y, "close": str(v)} for y, v in prices.items()]


class RangeTests(unittest.TestCase):
    def test_continuous_ten_years_give_five_windows_at_the_true_rate(self):
        data, _ = steady()
        block, q = rng.growth_range(data)
        self.assertEqual((block["status"], block["n"]), ("available", 5))
        self.assertEqual({row["value"] for row in block["values"]}, {"0.1000"})
        self.assertEqual([(row["fiscalYear"], row["endFiscalYear"]) for row in block["values"]],
                         [(y, y + 5) for y in range(2015, 2020)])
        self.assertEqual((block["p25"], block["p50"], block["p75"]), ("0.1000",) * 3)

    def test_a_missing_middle_year_drops_only_the_windows_that_need_it(self):
        data, _ = steady()
        data["rows"] = [row for row in data["rows"] if not (row["fiscalYear"] == 2020 and row["metric"] == "EPS Diluted")]
        block, _ = rng.growth_range(data)
        self.assertEqual(block["n"], 4)
        self.assertEqual([(row["fiscalYear"], row["endFiscalYear"]) for row in block["values"]],
                         [(2016, 2021), (2017, 2022), (2018, 2023), (2019, 2024)])
        self.assertEqual(block["excluded"], [{"fiscalYear": 2015, "endFiscalYear": 2020, "reason": "missing_value"}])
        self.assertEqual({row["value"] for row in block["values"]}, {"0.1000"})  # never the 6-year span

    def test_too_few_windows_has_no_default_and_keeps_the_reason(self):
        data, _ = steady(years=range(2017, 2025))  # 8 years -> 3 windows
        self.assertEqual(rng.growth_range(data)[0]["n"], 3)
        data, _ = steady(years=range(2018, 2025))  # 7 years -> 2 windows
        block, quartiles = rng.growth_range(data)
        self.assertEqual((block["status"], block["reason"], quartiles), ("unavailable", {"code": "history_too_short"}, None))
        self.assertEqual(block["n"], 2)

    def test_non_positive_eps_endpoints_are_excluded_with_a_reason(self):
        data = history(range(2015, 2025), **{"EPS Diluted": lambda y: -1 if y in (2015, 2022) else 1 + (y - 2015)})
        block, _ = rng.growth_range(data)
        self.assertEqual([(d["fiscalYear"], d["reason"]) for d in block["excluded"]],
                         [(2015, "non_positive_eps"), (2017, "non_positive_eps")])
        self.assertEqual(block["n"], 3)

    def test_pe_range_uses_adjusted_year_end_closes_and_skips_losses(self):
        data, prices = steady()
        data["rows"] = [dict(row, value="-1") if (row["fiscalYear"] == 2016 and row["metric"] == "EPS Diluted") else row
                        for row in data["rows"]]
        block, q = rng.pe_range(data, closes(prices))
        self.assertEqual((block["n"], block["excluded"]), (9, [{"fiscalYear": 2016, "reason": "non_positive_eps"}]))
        self.assertEqual(block["p50"], "15.00")
        self.assertEqual(rng.pe_range(data, None)[0]["reason"], {"code": "price_event_unverified"})

    def test_payout_never_reads_a_missing_dividend_as_zero(self):
        data, _ = steady()
        data["rows"] = [row for row in data["rows"] if not (row["metric"] == "DPS" and row["fiscalYear"] < 2020)]
        block, _ = rng.payout_range(data)
        self.assertEqual((block["status"], block["n"], len(block["excluded"])), ("available", 5, 5))
        self.assertTrue(all(item["reason"] == "missing_value" for item in block["excluded"]))
        # 0..100% only: a 120% year is dropped; an explicit zero is a real zero
        explicit = {2015: D(0), 2016: D(0), 2017: D(0), 2018: D(0), 2019: D(0), 2020: None, 2021: D("100")}
        block, _ = rng.payout_range(data, explicit)
        self.assertEqual([row["value"] for row in block["values"]], ["0.0000"] * 5)
        self.assertEqual(block["p50"], "0.0000")
        self.assertEqual([item["reason"] for item in block["excluded"] if item["fiscalYear"] == 2021], ["payout_out_of_range"])

    def test_margin_keeps_negative_years_and_rps_growth_uses_adjusted_shares(self):
        data, _ = steady()
        block, _ = rng.margin_range(data)
        self.assertEqual((block["n"], block["p50"]), (10, "0.1000"))
        loss = history(range(2015, 2022), **{"Net Income": lambda y: -5, "Revenue": lambda y: 100})
        self.assertEqual(rng.margin_range(loss)[0]["values"][0]["value"], "-0.0500")
        block, _ = rng.rps_growth_range(data)
        self.assertEqual({row["value"] for row in block["values"]}, {"0.1000"})


class DecompositionTests(unittest.TestCase):
    def window(self, revenue, margin, shares, eps_scale=1):
        years = (2015, 2020)
        series = {"Revenue": lambda y: revenue[years.index(y)], "Net Income": lambda y: revenue[years.index(y)] * margin[years.index(y)],
                  "Shares Diluted": lambda y: shares[years.index(y)]}
        data = history(years, **series)
        for y in years:  # disclosed EPS = NI / shares (scaled for gap tests)
            i = years.index(y)
            data["rows"].append({"fiscalYear": y, "metric": "EPS Diluted",
                                 "value": str(revenue[i] * margin[i] / shares[i] * eps_scale), "period": {"start": None, "end": f"{y}-12-31"}})
        return data

    def test_three_terms_add_up_to_the_total_log_growth(self):
        out = decompose(self.window([100, 200], [D("0.10"), D("0.15")], [100, 80]))
        row = out["windows"][0]
        self.assertAlmostEqual(float(row["R"]), math.log(2), places=3)
        self.assertAlmostEqual(float(row["M"]), math.log(1.5), places=3)
        self.assertAlmostEqual(float(row["S"]), math.log(1.25), places=3)
        self.assertAlmostEqual(float(row["total"]), math.log(3.75), places=3)
        self.assertAlmostEqual(float(row["R"]) + float(row["M"]) + float(row["S"]), float(row["total"]), places=3)
        self.assertAlmostEqual(float(row["annual"]["total"]), float(row["total"]) / 5, places=3)
        self.assertEqual((out["notes"], out["recentWindow"], row["epsGap"]["state"]), ([], [2015, 2020], "within_1pct"))

    def test_margin_driven_growth_gets_the_margin_sentence_only_when_total_is_large_enough(self):
        out = decompose(self.window([100, 110], [D("0.1"), D("0.3")], [100, 90]))
        self.assertEqual([note["code"] for note in out["notes"]], ["margin_majority"])
        flat = decompose(self.window([100, 100], [D("0.1"), D("0.1")], [100, 100]))
        self.assertEqual(flat["notes"], [])  # total yearly growth 0 < 1%: no sentence

    def test_share_reduction_sentence_and_the_exact_half_boundary(self):
        out = decompose(self.window([100, 100], [D("0.1"), D("0.1")], [100, 25]))
        self.assertEqual([note["code"] for note in out["notes"]], ["share_reduction_significant"])
        tie = decompose(self.window([100, 400], [D("0.1"), D("0.4")], [100, 100]))  # R and M both ln 4: ratio exactly 0.5
        self.assertEqual([note["code"] for note in tie["notes"]], ["margin_majority"])

    def test_sentence_thresholds_sit_just_above_one_percent_and_thirty_percent(self):
        below = decompose(self.window([100, 100], [D("0.1"), D("0.105")], [100, 100]))   # total ln 1.05 -> 0.98% a year
        above = decompose(self.window([100, 100], [D("0.1"), D("0.1052")], [100, 100]))  # -> 1.03% a year
        self.assertEqual((below["notes"], [n["code"] for n in above["notes"]]), ([], ["margin_majority"]))
        # shares 8x down is ln 8; revenue 128x is ln 128: share part 0.3 of the total, just under / over
        under = decompose(self.window([100, 12800], [D("0.1"), D("0.1")], [800, 105]))
        over = decompose(self.window([100, 12800], [D("0.1"), D("0.1")], [800, 95]))
        self.assertEqual(([n["code"] for n in under["notes"]], [n["code"] for n in over["notes"]]),
                         ([], ["share_reduction_significant"]))

    def test_negative_total_gets_no_sentence_and_bad_windows_are_listed(self):
        shrink = decompose(self.window([100, 50], [D("0.1"), D("0.05")], [100, 100]))
        self.assertEqual(shrink["notes"], [])
        loss = decompose(self.window([100, 200], [D("0.1"), D("-0.1")], [100, 100]))
        self.assertEqual(loss["status"], "unavailable")
        self.assertEqual(loss["excluded"][0]["reason"], "non_positive_value")

    def test_eps_gap_and_shares_implied_from_eps(self):
        gap = decompose(self.window([100, 200], [D("0.1"), D("0.15")], [100, 80], eps_scale=D("1.02")))
        self.assertEqual(gap["windows"][0]["epsGap"]["state"], "exceeds_1pct")
        implied = self.window([100, 200], [D("0.1"), D("0.15")], [100, 80], eps_scale=D("1.02"))
        implied["sharesBasis"] = "shares_implied_from_eps"
        self.assertEqual(decompose(implied)["windows"][0]["epsGap"], {"state": "not_applicable"})


class ComputeTests(unittest.TestCase):
    PRICE = {"value": "30", "sessionDate": "2025-03-01", "currency": "USD"}

    def run_compute(self, data=None, prices=None, **kwargs):
        built, closing = steady()
        return compute(data or built, self.PRICE, fiscal_prices=closes(closing) if prices is None else prices, **kwargs)

    def test_a_steady_company_gives_one_return_for_every_scenario(self):
        out = self.run_compute()
        eps0 = D("1.1") ** 9
        self.assertEqual((out["base"]["fiscalYear"], out["base"]["monthsBeforeSession"]), (2024, 2))
        self.assertEqual(len(out["scenarios"]), 6)
        for row in out["scenarios"]:
            self.assertEqual((row["status"], row["g"], row["exitPE"], row["payout"]), ("available", "0.1000", "15.00", "0.3000"))
            flows = [-30] + [float(eps0) * 1.1 ** t * 0.3 for t in range(1, row["horizon"] + 1)]
            flows[-1] += float(eps0) * 1.1 ** row["horizon"] * 15
            low, high = -0.99, 1.0
            for _ in range(200):
                mid = (low + high) / 2
                low, high = (mid, high) if sum(f / (1 + mid) ** t for t, f in enumerate(flows)) > 0 else (low, mid)
            self.assertAlmostEqual(float(row["irr"]), (low + high) / 2, places=4)
        self.assertEqual({(row["label"], row["horizon"]) for row in out["scenarios"]},
                         {(label, horizon) for label in ("conservative", "base", "optimistic") for horizon in (5, 10)})
        self.assertEqual(out["notices"], [])
        self.assertEqual(json.loads(json.dumps(out)), out)  # storable as plain JSON

    def test_the_three_scenarios_differ_when_the_history_does(self):
        data, prices = steady()
        data["rows"] = [dict(row, value=str(D(row["value"]) * (D("1.0") if row["fiscalYear"] % 2 else D("1.3"))))
                        if row["metric"] == "EPS Diluted" else row for row in data["rows"]]
        out = self.run_compute(data, closes(prices))
        base = {row["horizon"]: row for row in out["scenarios"] if row["label"] == "base"}
        low = {row["horizon"]: row for row in out["scenarios"] if row["label"] == "conservative"}
        high = {row["horizon"]: row for row in out["scenarios"] if row["label"] == "optimistic"}
        for horizon in (5, 10):
            self.assertLessEqual(float(low[horizon]["g"]), float(base[horizon]["g"]) <= float(high[horizon]["g"]))
            self.assertEqual((low[horizon]["payout"], high[horizon]["payout"]), (base[horizon]["payout"],) * 2)  # payout is always the median
        self.assertEqual((low[5]["percentiles"], high[5]["percentiles"]), ({"g": 25, "exitPE": 25, "payout": 50}, {"g": 75, "exitPE": 75, "payout": 50}))

    def test_unverified_price_event_blocks_only_what_uses_year_end_closes(self):
        out = self.run_compute(prices=[])  # empty list is a real (empty) series: PER needs 5 years
        self.assertEqual(out["ranges"]["pe"]["reason"], {"code": "history_too_short"})
        out = compute(steady()[0], self.PRICE, fiscal_prices=None, prices_reason={"code": "price_event_unverified"})
        self.assertEqual({row["reason"]["code"] for row in out["scenarios"]}, {"price_event_unverified"})
        self.assertEqual(out["reverse"]["sensitivity"]["reason"]["code"], "price_event_unverified")
        self.assertEqual({v["reason"]["code"] for v in out["reverse"]["breakEvenMargin"].values()}, {"price_event_unverified"})
        # Growth, payout, decomposition and the 0% exit PER do not use year-end closes.
        self.assertEqual(out["ranges"]["growth"]["status"], "available")
        self.assertEqual(out["decomposition"]["status"], "available")
        self.assertEqual(out["reverse"]["breakEvenPE"]["10"]["status"], "available")

    def test_break_even_exit_pe_matches_a_hand_calculation(self):
        out = self.run_compute()
        eps0 = D("1.1") ** 9
        dividends = sum(eps0 * D("1.1") ** t * D("0.3") for t in range(1, 6))
        expected = (D(30) - dividends) / (eps0 * D("1.1") ** 5)
        entry = out["reverse"]["breakEvenPE"]["5"]
        if expected <= 0:
            self.assertEqual(entry["state"], "not_needed")
        else:
            self.assertAlmostEqual(float(entry["exitPE"]), float(expected), places=2)
        cheap = compute(steady()[0], {**self.PRICE, "value": "2"}, fiscal_prices=closes(steady()[1]))
        self.assertEqual(cheap["reverse"]["breakEvenPE"]["10"]["state"], "not_needed")

    def test_net_margin_inversion_reports_the_margin_a_zero_return_needs(self):
        out = self.run_compute()["reverse"]["breakEvenMargin"]["5"]
        self.assertEqual((out["status"], out["currentMargin"]), ("available", "0.1000"))
        self.assertEqual(out["disclosedEps"], str(D("1.1") ** 9))
        self.assertIsNotNone(out["margin"])
        self.assertIn("currentMarginPercentile", out)

    def test_sensitivity_is_ordered_by_the_size_of_the_change(self):
        data, prices = steady()
        data["rows"] = [dict(row, value=str(D(row["value"]) * (1 + D(row["fiscalYear"] % 3) / 10)))
                        if row["metric"] == "EPS Diluted" else row for row in data["rows"]]
        out = compute(data, self.PRICE, fiscal_prices=closes({y: v * (1 + D(y % 4) / 10) for y, v in prices.items()}))
        rows = out["reverse"]["sensitivity"]["rows"]
        self.assertEqual({(row["horizon"], row["input"], row["to"]) for row in rows},
                         {(h, field, to) for h in (5, 10) for field in ("growth", "exitPE", "payout") for to in ("p25", "p75")})
        for horizon in (5, 10):
            deltas = [abs(float(row["delta"])) for row in rows if row["horizon"] == horizon and row["delta"] is not None]
            self.assertEqual(deltas, sorted(deltas, reverse=True))

    def test_losses_stale_financials_and_missing_inputs_stay_unavailable(self):
        data, prices = steady()
        loss = {**data, "rows": [dict(row, value="-2") if (row["fiscalYear"] == 2024 and row["metric"] == "EPS Diluted") else row
                                 for row in data["rows"]]}
        out = compute(loss, self.PRICE, fiscal_prices=closes(prices))
        self.assertEqual({row["reason"]["code"] for row in out["scenarios"]}, {"negative_base_eps"})
        self.assertEqual(out["reverse"]["breakEvenPE"]["5"]["reason"]["code"], "negative_base_eps")
        self.assertEqual(out["reverse"]["breakEvenMargin"]["5"]["status"], "available")  # a loss year still has revenue and margin
        stale = compute(data, {**self.PRICE, "sessionDate": "2026-04-02"}, fiscal_prices=closes(prices))
        self.assertEqual({row["reason"]["code"] for row in stale["scenarios"]}, {"stale_financials"})
        self.assertEqual({v["reason"]["code"] for v in stale["reverse"]["breakEvenMargin"].values()}, {"stale_financials"})
        fresh = compute(data, {**self.PRICE, "sessionDate": "2026-03-31"}, fiscal_prices=closes(prices))
        self.assertEqual(fresh["scenarios"][0]["status"], "available")  # exactly 15 months is still fresh
        short = compute(history(range(2020, 2025), **{"EPS Diluted": lambda y: 1}), self.PRICE, fiscal_prices=[])
        self.assertEqual({row["reason"]["code"] for row in short["scenarios"]}, {"history_too_short"})

    def test_results_are_deterministic(self):
        data, prices = steady()
        first = json.dumps(compute(data, self.PRICE, fiscal_prices=closes(prices)), sort_keys=True)
        self.assertEqual(first, json.dumps(compute(data, self.PRICE, fiscal_prices=closes(prices)), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
