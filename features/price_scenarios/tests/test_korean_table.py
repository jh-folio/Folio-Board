import unittest
from decimal import Decimal as D

from features.price_scenarios import korean_table as kt
from features.price_scenarios.korean_shares import reconcile

CORP = "00126380"


def row(label, issued, decreased, ending, redc="-", profit="-", redeem="-", etc="-", end="2018-12-31", accession="20190401004781"):
    return {"rcept_no": accession, "corp_code": CORP, "se": label, "now_to_isu_stock_totqy": issued, "now_to_dcrs_stock_totqy": decreased,
            "istc_totqy": ending, "redc": redc, "profit_incnr": profit, "rdmstk_repy": redeem, "etc": etc, "stlm_dt": end}


def packet(*rows, status="000"):
    return {"status": status, "list": list(rows)}


SAMSUNG_2017 = row("보통주", "155,609,337", "26,510,843", "129,098,494", profit="26,510,843", end="2017-12-31", accession="20180402005019")
SAMSUNG_2018 = row("보통주", "7,780,466,850", "1,810,684,300", "5,969,782,550", profit="1,810,684,300")
PREFERRED = row("우선주", "0", "0", "0")


class CellTests(unittest.TestCase):
    def test_cells_read_by_the_stated_forms_only(self):
        for text, expected in (("-", "empty"), (" – ", "empty"), ("　-", "empty"), ("—", "empty"), ("0", 0), ("007", 7), ("0,000", 0),
                               ("1,234,567", 1234567), ("12\n3", 123), ("5 000", 5000)):
            self.assertEqual(kt.read_cell(text), expected, text)
        for text in ("", None, ",", " , ", "(1)", "-5", "1.5", "1,23", "abc", "１２", "1,,234"):
            self.assertIsNone(kt.read_cell(text), text)


class IdentityTests(unittest.TestCase):
    def test_label_normalisation_and_the_three_way_rule(self):
        self.assertEqual(kt.normalize_label("보통주*"), "보통주")
        self.assertEqual(kt.normalize_label("보통주(주1)(주2)"), "보통주")
        self.assertEqual(kt.normalize_label("의결권없는\n주식*"), "의결권없는주식")
        r = lambda label: row(label, "1", "0", "1")
        self.assertEqual(kt.select_common_row([r("보통주"), r("우선주")])[1], None)
        self.assertEqual(kt.select_common_row([r("보통주식*"), r("종류주식")])[0]["se"], "보통주식*")
        voting, notice = kt.select_common_row([r("의결권있는\n주식"), r("의결권없는 주식*")])
        self.assertEqual((voting["se"], notice), ("의결권있는\n주식", kt.VOTING_NOTICE))
        for rows in ([r("의결권 있는 주식")], [r("의결권 없는 주식")], [r("보통주"), r("의결권 있는 주식"), r("의결권 없는 주식")],
                     [r("보통주"), r("보통주")], [r("보통주"), r("의결권 있는 주식")], [r("보통주전환우선주")], []):
            self.assertEqual(kt.select_common_row(rows), (None, kt.IDENTITY_UNCONFIRMED))


class EquationTests(unittest.TestCase):
    def test_both_equations_must_hold_exactly(self):
        reading = kt.table_reading(SAMSUNG_2018)
        self.assertEqual(reading["zeroCells"], ["redc", "rdmstk_repy", "etc"])
        self.assertEqual(reading["cells"]["profit_incnr"], 1810684300)
        self.assertIsNone(kt.table_reading({**SAMSUNG_2018, "now_to_isu_stock_totqy": "7,780,466,851"}))   # (a) off by one
        self.assertIsNone(kt.table_reading({**SAMSUNG_2018, "now_to_dcrs_stock_totqy": "1,810,684,301"}))  # (b) off by one
        self.assertIsNone(kt.table_reading({**SAMSUNG_2018, "etc": "(1)"}))                                  # unreadable cell
        self.assertIsNone(kt.table_reading({**SAMSUNG_2018, "istc_totqy": "-"}))
        self.assertIsNotNone(kt.table_reading(row("보통주", "5", "-", "5")))                                  # nothing ever cancelled


class ObservationTests(unittest.TestCase):
    def test_a_proven_row_gives_unit_proofs_and_keeps_the_source_cells(self):
        out = kt.observation(packet(SAMSUNG_2018, PREFERRED), corp_code=CORP, as_of="2026-10-01")
        self.assertEqual(out["state"], "received")
        decreases = out["observation"]["decreases"]
        self.assertEqual(decreases["redemption"]["value"], "0")
        self.assertEqual(decreases["redemption"]["unitProof"]["statement"], "row_arithmetic_zero")
        self.assertEqual(decreases["profitCancellation"]["unitProof"]["statement"], "row_arithmetic_period_end_unit")
        self.assertEqual(decreases["profitCancellation"]["unitDate"], "2018-12-31")
        self.assertEqual(decreases["redemption"]["rawCell"], "-")
        self.assertEqual(decreases["profitCancellation"]["unitProof"]["rowCells"]["profit_incnr"], "1,810,684,300")
        zero = kt.observation(packet(row("보통주", "5", "0", "5", redc="0", profit="0", redeem="0", etc="0")), corp_code=CORP, as_of="2026-10-01")
        self.assertEqual(zero["observation"]["decreases"]["redemption"]["unitProof"]["statement"], "explicit_zero")

    def test_an_unproven_row_leaves_values_missing_and_identity_failures_stop(self):
        bad = kt.observation(packet({**SAMSUNG_2018, "now_to_isu_stock_totqy": "7,780,466,851"}), corp_code=CORP, as_of="2026-10-01")
        self.assertIsNone(bad["observation"]["decreases"]["redemption"]["value"])
        self.assertEqual(kt.observation(packet(SAMSUNG_2018, SAMSUNG_2018), corp_code=CORP, as_of="2026-10-01"),
                         {"state": "unknown", "reason": kt.IDENTITY_UNCONFIRMED})
        self.assertEqual(kt.observation(packet(SAMSUNG_2018, status="013"), corp_code=CORP, as_of="2026-10-01")["reason"], "share_count_source_unavailable")
        self.assertEqual(kt.observation(packet(SAMSUNG_2018), corp_code=CORP, as_of="2019-01-01")["reason"], "future_share_count_source")

    def test_the_samsung_split_year_reconciles_to_zero_residual_with_the_table_proof(self):
        first = kt.observation(packet(SAMSUNG_2017), corp_code=CORP, as_of="2026-10-01")["observation"]
        second = kt.observation(packet(SAMSUNG_2018), corp_code=CORP, as_of="2026-10-01")["observation"]
        split = {"kind": "split", "ratio": "50", "eventDate": "2018-05-04", "shareDate": "2018-05-04"}
        result = reconcile(first, second, [split], [], coverage={"state": "confirmed", "start": "2015-01-01", "end": "2026-10-01"}, as_of="2026-10-01")
        self.assertEqual((result["state"], D(result["residual"]), result["decreaseEnd"]), ("matched", 0, "485142150"))
        self.assertEqual(result["decreasesEnd"], {"profitCancellation": "485142150", "redemption": "0"})

    def test_an_unexplained_issue_stays_unknown_and_a_small_one_is_within_tolerance(self):
        end18 = kt.observation(packet(row("의결권있는주식", "76,579,477", "6,219,180", "70,360,297", redc="219,180", profit="6,000,000", end="2020-12-31"),
                                      row("의결권없는 주식*", "566,135", "-", "566,135", end="2020-12-31")), corp_code=CORP, as_of="2026-10-01")
        self.assertEqual(end18["notice"], kt.VOTING_NOTICE)
        start = end18["observation"]
        def later(shares, issued):
            return kt.observation(packet(row("의결권있는주식", issued, "6,219,180", shares, redc="219,180", profit="6,000,000", end="2021-12-31", accession="20220308000001"),
                                         row("의결권없는주식", "566,135", "-", "566,135", end="2021-12-31", accession="20220308000001")), corp_code=CORP, as_of="2026-10-01")["observation"]
        coverage = {"state": "confirmed", "start": "2015-01-01", "end": "2026-10-01"}
        big = reconcile(start, later("74,149,329", "80,368,509"), [], [], coverage=coverage, as_of="2026-10-01")       # +5.39%
        small = reconcile(start, later("72,470,106", "78,689,286"), [], [], coverage=coverage, as_of="2026-10-01")     # +3.0%
        self.assertEqual((big["state"], big["reason"]), ("unknown", "unexplained_share_change"))
        self.assertEqual(small["state"], "matched")


if __name__ == "__main__":
    unittest.main()


class UnfiledYearTests(unittest.TestCase):
    def test_a_report_not_filed_yet_is_skipped_but_a_middle_gap_is_not(self):
        from features.price_scenarios.assemble import _kr_share_reconciliation
        placeholder = {"status": "000", "list": [{"corp_code": CORP, "isu_dcrs_de": "-", "isu_dcrs_stle": "-", "isu_dcrs_stock_knd": "-", "isu_dcrs_qy": "-"}]}
        year = lambda y, shares: packet(row("보통주", shares, "-", shares, end=f"{y}-12-31", accession=f"{y + 1}0401000001"))
        raw = {"identity": {"corpCode": CORP}, "dart": {"coverage": {"state": "confirmed", "start": "2015-01-01", "end": "2026-10-01"},
               "stockTotqy": {"2024": year(2024, "100"), "2025": year(2025, "100"), "2026": {"status": "013", "list": []}},
               "irds": {"2025": placeholder, "2026": placeholder}}}
        out = _kr_share_reconciliation(raw, [], "2026-10-01", spec3=True)
        self.assertEqual((out["state"], len(out["pairs"])), ("matched", 1))
        raw["dart"]["stockTotqy"] = {"2023": year(2023, "100"), "2024": {"status": "013", "list": []}, "2025": year(2025, "100")}
        self.assertEqual(_kr_share_reconciliation(raw, [], "2026-10-01", spec3=True)["reason"], "share_count_gap")
