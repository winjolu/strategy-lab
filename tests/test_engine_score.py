import math
import unittest

import numpy as np
import pandas as pd

from lab.engine import score


def stream(days, mean=0.0, sd=0.01, start="2020-01-01", seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=days)
    return pd.Series(rng.normal(mean, sd, days), idx)


ZERO = lambda s: pd.Series(0.0, s.index)


class Tiers(unittest.TestCase):
    def test_the_boundaries(self):
        cases = [(1.5, "clear"), (1.4999, "borderline"), (1.0, "borderline"),
                 (0.9999, "below"), (-2.0, "below"), (float("nan"), "undefined"), (None, "undefined")]
        for s, word in cases:
            self.assertEqual(score.tier(s), word, s)

    def test_no_tier_label_carries_a_verdict(self):
        for word in ("clear", "borderline", "below", "undefined"):
            for banned in ("pass", "fail", "kill", "drop", "advance", "reject"):
                self.assertNotIn(banned, word)


class TrainingWindow(unittest.TestCase):
    def test_it_is_three_years_ending_the_day_before_the_holdout(self):
        idx = pd.bdate_range("2015-01-01", "2026-01-01")
        start, end = score.training_window(idx, "2025-10-01")
        self.assertEqual(end, pd.Timestamp("2025-09-30"))
        self.assertGreaterEqual(start, pd.Timestamp("2022-10-01"))
        self.assertLess(start, pd.Timestamp("2022-10-05"))

    def test_the_holdout_day_itself_is_never_in_the_window(self):
        idx = pd.bdate_range("2015-01-01", "2026-01-01")
        _, end = score.training_window(idx, "2025-09-30")
        self.assertLess(end, pd.Timestamp("2025-09-30"))

    def test_a_short_history_gives_all_it_has(self):
        idx = pd.bdate_range("2024-01-01", "2025-12-31")
        start, _ = score.training_window(idx, "2025-10-01")
        self.assertEqual(start, idx[0])

    def test_no_data_before_the_holdout_is_refused(self):
        with self.assertRaises(ValueError):
            score.training_window(pd.bdate_range("2026-01-01", "2026-03-01"), "2025-10-01")


class Scores(unittest.TestCase):
    def setUp(self):
        self.net = stream(1500, mean=0.0006, sd=0.007, start="2020-01-01")
        self.bench = ZERO(self.net)
        self.holdout = str(self.net.index[1100].date())

    def test_the_training_score_uses_only_the_window_before_the_holdout(self):
        spiked = self.net.copy()
        spiked[spiked.index >= self.holdout] += 0.5
        a = score.training_score(self.net, self.bench, self.holdout)
        b = score.training_score(spiked, self.bench, self.holdout)
        self.assertEqual(a["sharpe"], b["sharpe"])
        self.assertLess(a["end"], pd.Timestamp(self.holdout))

    def test_the_pooled_score_is_the_sharpe_of_the_active_record_over_both_windows(self):
        out = score.pooled_score(self.net, self.bench, self.holdout)
        start, _ = score.training_window(self.net.index, self.holdout)
        window = self.net[self.net.index >= start]
        expected = window.mean() / window.std(ddof=1) * math.sqrt(252)
        self.assertAlmostEqual(out["sharpe"], expected, places=10)
        self.assertEqual(out["n_days"], len(window))
        self.assertEqual(out["n_holdout_days"] + out["n_training_days"], out["n_days"])

    def test_the_score_is_on_the_active_return_not_the_raw_one(self):
        out_flat = score.pooled_score(self.net, self.bench, self.holdout)
        out_active = score.pooled_score(self.net, pd.Series(0.0004, self.net.index), self.holdout)
        self.assertNotAlmostEqual(out_flat["sharpe"], out_active["sharpe"], places=3)

    def test_a_holdout_shorter_than_a_year_is_refused(self):
        late = str(self.net.index[-100].date())
        with self.assertRaises(score.HoldoutTooShort):
            score.pooled_score(self.net, self.bench, late)

    def test_a_holdout_of_exactly_a_year_is_enough_and_one_day_less_is_not(self):
        enough = str(self.net.index[-252].date())
        score.pooled_score(self.net, self.bench, enough)
        short = str(self.net.index[-251].date())
        with self.assertRaises(score.HoldoutTooShort):
            score.pooled_score(self.net, self.bench, short)

    def test_a_flat_record_has_an_undefined_score_not_a_crash(self):
        flat = pd.Series(0.001, self.net.index)
        out = score.training_score(flat, ZERO(flat), self.holdout)
        self.assertEqual(out["tier"], "undefined")

    def test_too_few_days_are_refused(self):
        with self.assertRaises(ValueError):
            score.training_score(self.net.iloc[:10], self.bench.iloc[:10], "2030-01-01")
