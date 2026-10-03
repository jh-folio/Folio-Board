import datetime as dt
import unittest

from features.price_scenarios.beta import BETA_SOURCE, measure_beta

NOW = lambda: dt.datetime(2026, 10, 2, 1, 2, 3, tzinfo=dt.timezone.utc)


class BetaMeasurementTests(unittest.TestCase):
    def test_exact_symbol_value_is_stored_with_source_and_no_fetch_time(self):
        calls = []
        result = measure_beta("005930.KS", now=NOW, fetch_info=lambda s: calls.append(s) or {"symbol": "005930.KS", "beta": 1.1})
        self.assertEqual(calls, ["005930.KS"])  # no candidate guessing
        self.assertEqual(result["beta"], {"value": "1.1", "source": BETA_SOURCE,
                                          "providerSymbol": "005930.KS", "basis": "provider_current_value"})
        self.assertNotIn("fetchedAt", result["beta"])
        self.assertEqual(result["fetchedAt"], "2026-10-02T01:02:03+00:00")

    def test_unusable_values_stay_unmeasured_not_zero(self):
        for info, reason in (({"symbol": "X", "beta": None}, "beta_not_provided"), ({"beta": "n/a"}, "beta_not_numeric"),
                             ({"beta": float("nan")}, "beta_out_of_range"), ({"beta": 99}, "beta_out_of_range"),
                             ({"beta": True}, "beta_not_provided"), ({"symbol": "OTHER", "beta": 1.0}, "provider_symbol_mismatch"),
                             ([], "provider_shape_unrecognized")):
            with self.subTest(info=info):
                beta = measure_beta("X", now=NOW, fetch_info=lambda s, info=info: info)["beta"]
                self.assertIsNone(beta["value"])
                self.assertEqual((beta["source"], beta["reason"]), ("not_measured", reason))

    def test_provider_failure_and_blank_symbol_do_not_raise(self):
        def boom(_):
            raise RuntimeError("down")
        self.assertEqual(measure_beta("X", now=NOW, fetch_info=boom)["beta"]["reason"], "provider_error")
        self.assertEqual(measure_beta(" ", now=NOW)["beta"]["reason"], "provider_symbol_missing")
        self.assertEqual(measure_beta("X", now=NOW, fetch_info=lambda s: {"beta": -0.2})["beta"]["value"], "-0.2")


if __name__ == "__main__":
    unittest.main()
