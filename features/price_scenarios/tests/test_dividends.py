import unittest
from decimal import Decimal as D

from features.price_scenarios import ranges as rng
from features.price_scenarios.dividends import read_dividends

from .test_scenario_results import history


def rows(years, eps=lambda y: 2, cash=lambda y: 100, dps=lambda y: None, paid=lambda y: None):
    return history(years, **{"EPS Diluted": eps, "Operating Cash Flow": cash, "DPS": dps, "Dividends Paid": paid})


class NoDividendReadingTests(unittest.TestCase):
    def test_a_company_with_no_dividend_facts_reads_every_positive_eps_year_as_zero(self):
        data = rows(range(2015, 2025), eps=lambda y: -1 if y == 2022 else 2)
        values, zeros = read_dividends(data)
        self.assertEqual(zeros, [y for y in range(2015, 2025) if y != 2022])
        self.assertIsNone(values[2022])  # a loss year is not a payout year
        block, quartiles = rng.payout_range(data, values)
        self.assertEqual((block["n"], block["p25"], block["p50"], block["p75"]), (9, "0.0000", "0.0000", "0.0000"))
        self.assertEqual([item["reason"] for item in block["excluded"]], ["non_positive_eps"])

    def test_late_payers_mix_zero_years_with_real_values_using_type7(self):
        data = rows(range(2015, 2025), dps=lambda y: D("0.8") if y >= 2023 else None)
        values, zeros = read_dividends(data)
        self.assertEqual(zeros, list(range(2015, 2023)))
        block, _ = rng.payout_range(data, values)
        self.assertEqual((block["n"], block["p50"], block["p75"]), (10, "0.0000", "0.0000"))
        mixed = rows(range(2015, 2025), dps=lambda y: D("0.8") if y >= 2020 else None)
        block, _ = rng.payout_range(mixed, read_dividends(mixed)[0])
        self.assertEqual((block["n"], block["p25"], block["p50"]), (10, "0.0000", "0.2000"))  # 5 zeros + 5 at 40%: type 7, not "all zero"

    def test_positive_payments_without_a_dps_fact_stay_missing(self):
        data = rows(range(2015, 2025), paid=lambda y: 5)
        values, zeros = read_dividends(data)
        self.assertEqual(zeros, [])
        self.assertTrue(all(value is None for value in values.values()))
        self.assertEqual(rng.payout_range(data, values)[0]["reason"], {"code": "history_too_short"})

    def test_zero_payment_rows_dps_values_cash_flow_and_lookup_failures(self):
        data = rows(range(2015, 2025), paid=lambda y: 0, dps=lambda y: D("0.5") if y == 2024 else None, cash=lambda y: None if y == 2019 else 100)
        values, zeros = read_dividends(data, unreadable_years={2016})
        self.assertEqual(values[2024], D("0.5"))                       # a DPS fact is used as is
        self.assertIsNone(values[2019])                                # no cash-flow statement read for that year
        self.assertIsNone(values[2016])                                # a failed lookup is not "no dividend"
        self.assertEqual(zeros, [2015, 2017, 2018, 2020, 2021, 2022, 2023])
        no_eps = rows(range(2015, 2025), eps=lambda y: None)
        self.assertEqual(read_dividends(no_eps)[1], [])

    def test_the_input_history_is_not_changed(self):
        data = rows(range(2015, 2025))
        before = [dict(row) for row in data["rows"]]
        read_dividends(data)
        self.assertEqual(data["rows"], before)


if __name__ == "__main__":
    unittest.main()


class CoverageTests(unittest.TestCase):
    def test_years_outside_the_stored_dividend_coverage_are_lookup_failures(self):
        from features.price_scenarios.assemble import dividend_coverage, unreadable_dividend_years
        packets = [{"status": "000", "list": [{"se": "주당 현금배당금(원)", "stlm_dt": "2024-12-31"}]},
                   {"status": "013", "list": []}, {"status": "000", "list": [{"se": "배당성향(%)", "stlm_dt": "2021-12-31"}]}]
        self.assertEqual(dividend_coverage(packets), [2022, 2023, 2024])
        data = rows(range(2020, 2025))
        data["dividendCoverage"] = dividend_coverage(packets)
        self.assertEqual(unreadable_dividend_years(data), {2020, 2021})
        values, zeros = read_dividends(data, unreadable_years=unreadable_dividend_years(data))
        self.assertEqual((zeros, values[2021]), ([2022, 2023, 2024], None))
        self.assertEqual(unreadable_dividend_years(rows(range(2020, 2025))), set())  # US: no list, nothing to exclude
