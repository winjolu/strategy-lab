import unittest

import numpy as np
import pandas as pd

from lab.engine import sizing, stats


def sig(rows, cols):
    return pd.DataFrame(rows, pd.bdate_range("2024-01-01", periods=len(rows)), cols)


class Sizing(unittest.TestCase):
    def test_long_short_puts_half_the_gross_on_each_side(self):
        w = sizing.equal_weight(sig([[1, 1, -1, 0]], list("ABCD")), gross=1.0, long_short=True)
        self.assertAlmostEqual(w.iloc[0].clip(lower=0).sum(), 0.5)
        self.assertAlmostEqual(w.iloc[0].clip(upper=0).sum(), -0.5)

    def test_a_date_missing_a_side_is_flat_not_directional(self):
        w = sizing.equal_weight(sig([[1, 1, 0]], list("ABC")), long_short=True)
        self.assertEqual(w.iloc[0].abs().sum(), 0.0)

    def test_long_only_uses_the_full_gross(self):
        w = sizing.equal_weight(sig([[1, 1, 0]], list("ABC")), gross=1.0)
        self.assertAlmostEqual(w.iloc[0].sum(), 1.0)

    def test_a_negative_signal_in_a_long_only_sizing_is_refused(self):
        with self.assertRaises(sizing.SizingError):
            sizing.equal_weight(sig([[1, -1]], list("AB")))

    def test_nan_signal_is_refused(self):
        with self.assertRaises(sizing.SizingError):
            sizing.equal_weight(sig([[1, np.nan]], list("AB")))

    def test_inverse_vol_gives_the_calmer_name_more(self):
        s = sig([[1, 1]], list("AB"))
        v = sig([[0.01, 0.04]], list("AB"))
        w = sizing.inverse_vol(s, v)
        self.assertAlmostEqual(w["A"].iloc[0] / w["B"].iloc[0], 4.0)

    def test_a_name_with_no_volatility_is_dropped_not_filled(self):
        s = sig([[1, 1]], list("AB"))
        v = sig([[0.01, np.nan]], list("AB"))
        self.assertEqual(sizing.inverse_vol(s, v)["B"].iloc[0], 0.0)

    def test_kelly_fractions_above_a_quarter_are_refused(self):
        with self.assertRaises(sizing.SizingError):
            sizing.kelly_leverage([0.01, 0.02, 0.0], fraction=0.5)

    def test_kelly_is_a_quarter_of_mean_over_variance(self):
        r = np.array([0.01, 0.03])
        self.assertAlmostEqual(sizing.kelly_leverage(r), 0.25 * r.mean() / r.var())

    def test_kelly_is_negative_for_a_losing_stream(self):
        self.assertLess(sizing.kelly_leverage([-0.01, -0.02, 0.0]), 0)


class Bands(unittest.TestCase):
    def test_the_boundaries_use_the_methodologys_words(self):
        cases = [(3.0, "strong"), (2.999, "promising"), (2.0, "promising"),
                 (1.999, "underpowered"), (1.5, "underpowered"),
                 (1.499, stats.DROP), (0.0, stats.DROP), (-3.5, "strong")]
        for t, word in cases:
            self.assertEqual(stats.band(t), word, t)

    def test_nan_is_undefined_not_dropped(self):
        self.assertEqual(stats.band(float("nan")), "undefined")


def series(seed=0, n=1000, mean=0.0004):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.Series(rng.normal(mean, 0.01, n), idx)


class Summarise(unittest.TestCase):
    def test_a_benchmark_is_required(self):
        with self.assertRaises(stats.NoBenchmark):
            stats.summarise(series(), None)

    def test_t_is_on_active_return_not_raw_return(self):
        """A stream that is the benchmark plus noise has an enormous raw t
        and no edge. Testing the raw return would call it strong."""
        bench = series(1, mean=0.005)
        net = bench + np.random.default_rng(2).normal(0, 0.001, len(bench))
        out = stats.summarise(net, bench)
        raw_t = net.mean() / net.std() * np.sqrt(len(net))
        self.assertGreater(raw_t, 5)
        self.assertLess(abs(out["active_t_newey_west"]), 3)

    def test_a_real_edge_is_found(self):
        bench = series(1)
        net = bench + 0.002 + np.random.default_rng(2).normal(0, 0.002, len(bench))
        out = stats.summarise(net, bench)
        self.assertEqual(out["band"], "strong")
        self.assertGreater(out["active_mean_pct_per_year"], 0)

    def test_underpowered_results_carry_a_minimum_track_record(self):
        rng = np.random.default_rng(5)
        bench = series(1)
        # pick an edge that lands in 1.5 <= |t| < 2
        for edge in np.linspace(0.00005, 0.0006, 60):
            net = bench + edge + rng.normal(0, 0.004, len(bench))
            out = stats.summarise(net, bench)
            if out["band"] == "underpowered":
                self.assertIn("min_track_record_days", out)
                return
        self.fail("no edge landed in the underpowered band")

    def test_too_few_overlapping_days_are_refused(self):
        with self.assertRaises(ValueError):
            stats.summarise(series(n=10), series(1, n=10))

    def test_missing_deflation_inputs_are_reported_not_invented(self):
        out = stats.summarise(series(), series(1))
        self.assertIsNone(out["deflated"])
        self.assertIsNone(out["deflated_lab"])

    def test_deflation_needs_two_trials(self):
        out = stats.summarise(series(), series(1), trials=1, sharpe_variance=0.001)
        self.assertIsNone(out["deflated"])

    def test_more_trials_deflate_harder(self):
        few = stats.summarise(series(), series(1), trials=5, sharpe_variance=0.0004)
        many = stats.summarise(series(), series(1), trials=500, sharpe_variance=0.0004)
        self.assertLess(many["deflated"]["dsr"], few["deflated"]["dsr"])

    def test_correlations_report_their_sample_size_or_decline(self):
        out = stats.summarise(series(), series(1), spy=series(2))
        self.assertEqual(out["corr_to_spy"]["n"], 1000)
        self.assertIsNone(out["corr_to_book"])

    def test_time_under_water_and_drawdown_come_from_market_core(self):
        out = stats.summarise(series(), series(1))
        self.assertLess(out["absolute_max_drawdown_pct"], 0)
        self.assertGreater(out["time_under_water_days_longest"], 0)


if __name__ == "__main__":
    unittest.main()
