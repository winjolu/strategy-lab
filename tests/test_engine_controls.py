import unittest

import numpy as np
import pandas as pd

from lab.engine import controls

DATES = pd.bdate_range("2024-01-01", periods=60)
NAMES = [f"N{i}" for i in range(20)]


def frame(values):
    return pd.DataFrame(values, DATES, NAMES)


ELIGIBLE = frame(np.ones((60, 20), bool))
SIGNAL = frame(np.random.default_rng(3).normal(size=(60, 20)))


def keep_top(share):
    k = int(20 * share)
    ranks = SIGNAL.rank(axis=1, ascending=False)
    return ranks <= k


def picks_signal(mask):
    """A metric that rewards keeping high-signal names."""
    return float((SIGNAL.where(mask).sum(axis=1) / mask.sum(axis=1)).mean())


class RandomThinning(unittest.TestCase):
    def test_a_filter_that_selects_on_signal_scores_above_random_thinning(self):
        out = controls.random_thinning(ELIGIBLE, keep_top(0.5), picks_signal, draws=100)
        self.assertGreater(out["percentile"], 0.99)
        self.assertGreater(out["filtered"], out["random_mean"])

    def test_a_filter_that_selects_against_signal_scores_below(self):
        worst = SIGNAL.rank(axis=1, ascending=True) <= 10
        out = controls.random_thinning(ELIGIBLE, worst, picks_signal, draws=100)
        self.assertLess(out["percentile"], 0.01)

    def test_a_random_filter_lands_in_the_middle(self):
        rng = np.random.default_rng(9)
        k = frame(np.array([rng.permutation([True] * 10 + [False] * 10) for _ in range(60)]))
        out = controls.random_thinning(ELIGIBLE, k, picks_signal, draws=200)
        self.assertTrue(0.05 < out["percentile"] < 0.95, out["percentile"])

    def test_every_random_mask_keeps_the_same_count_on_every_date(self):
        seen = []

        def metric(mask):
            seen.append(mask.sum(axis=1).to_numpy())
            return 0.0

        k = keep_top(0.3)
        controls.random_thinning(ELIGIBLE, k, metric, draws=25)
        for counts in seen:
            np.testing.assert_array_equal(counts, k.sum(axis=1).to_numpy())

    def test_random_masks_stay_inside_the_eligible_cells(self):
        holes = ELIGIBLE.copy()
        holes.iloc[:, :5] = False
        k = holes & keep_top(0.5)

        def metric(mask):
            assert not (mask.to_numpy() & ~holes.to_numpy()).any()
            np.testing.assert_array_equal(mask.sum(axis=1).to_numpy(), k.sum(axis=1).to_numpy())
            return 0.0

        controls.random_thinning(holes, k, metric, draws=25)

    def test_the_same_seed_gives_the_same_answer_and_another_seed_a_different_one(self):
        a = controls.random_thinning(ELIGIBLE, keep_top(0.5), picks_signal, draws=50, seed=1)
        b = controls.random_thinning(ELIGIBLE, keep_top(0.5), picks_signal, draws=50, seed=1)
        c = controls.random_thinning(ELIGIBLE, keep_top(0.5), picks_signal, draws=50, seed=2)
        self.assertEqual(a, b)
        self.assertNotEqual(a["random_mean"], c["random_mean"])

    def test_a_filter_that_removes_nothing_is_refused(self):
        with self.assertRaises(ValueError):
            controls.random_thinning(ELIGIBLE, ELIGIBLE.copy(), picks_signal)

    def test_a_filter_keeping_ineligible_names_is_refused(self):
        holes = ELIGIBLE.copy()
        holes.iloc[:, 0] = False
        with self.assertRaises(ValueError):
            controls.random_thinning(holes, keep_top(0.5), picks_signal)

    def test_mismatched_frames_are_refused(self):
        with self.assertRaises(ValueError):
            controls.random_thinning(ELIGIBLE, keep_top(0.5).iloc[:30], picks_signal)

    def test_too_few_draws_are_refused(self):
        with self.assertRaises(ValueError):
            controls.random_thinning(ELIGIBLE, keep_top(0.5), picks_signal, draws=5)

    def test_a_metric_that_cannot_see_the_difference_is_flagged_degenerate(self):
        out = controls.random_thinning(ELIGIBLE, keep_top(0.5), lambda m: 1.0, draws=30)
        self.assertTrue(out["degenerate"])

    def test_the_share_removed_is_reported(self):
        out = controls.random_thinning(ELIGIBLE, keep_top(0.7), picks_signal, draws=30)
        self.assertAlmostEqual(out["share_removed"], 0.3, places=9)
