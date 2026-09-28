import unittest

import numpy as np
import pandas as pd

from lab.engine import backtest as bt
from lab.engine import costs
from lab.engine.costs import CostModel, CostNotStated

FREE = CostModel(slippage_pct=0.0)


def frame(rows, cols=("A",), start="2024-01-01"):
    idx = pd.bdate_range(start, periods=len(rows))
    return pd.DataFrame(rows, idx, list(cols))


class Alignment(unittest.TestCase):
    def test_a_decision_earns_the_next_days_return_not_its_own(self):
        r = frame([[0.10], [0.02], [0.03]])
        w = frame([[1.0], [1.0], [1.0]])
        res = bt.run(w, r, FREE)
        self.assertEqual(res.gross.tolist(), [0.0, 0.02, 0.03])

    def test_a_lag_below_one_is_refused(self):
        r = frame([[0.01]] * 3)
        with self.assertRaises(bt.LookaheadRisk):
            bt.run(frame([[1.0]] * 3), r, FREE, lag=0)

    def test_a_longer_lag_delays_further(self):
        r = frame([[0.01], [0.02], [0.03], [0.04]])
        res = bt.run(frame([[1.0]] * 4), r, FREE, lag=2)
        self.assertEqual(res.gross.tolist(), [0.0, 0.0, 0.03, 0.04])

    def test_a_signal_that_reads_todays_return_earns_nothing_from_it(self):
        """sign(today's return) as a decision is perfect foresight if it is
        applied to today, and worthless once the engine applies it to tomorrow."""
        rng = np.random.default_rng(3)
        r = pd.DataFrame(rng.normal(0, 0.01, (2000, 1)),
                         pd.bdate_range("2015-01-01", periods=2000), ["A"])
        cheat = np.sign(r)
        unshifted = (cheat * r).sum(axis=1)
        engine = bt.run(cheat, r, CostModel(0.0, borrow_apr=0.0)).gross
        self.assertGreater(unshifted.mean() / unshifted.std() * np.sqrt(2000), 20)
        self.assertLess(abs(engine.mean() / engine.std() * np.sqrt(2000)), 3)

    def test_unsorted_or_duplicated_indices_are_refused(self):
        r = frame([[0.01]] * 3)
        w = frame([[1.0]] * 3)
        with self.assertRaises(bt.LookaheadRisk):
            bt.run(w.iloc[::-1], r, FREE)
        dup = pd.concat([w, w.iloc[:1]])
        with self.assertRaises(bt.LookaheadRisk):
            bt.run(dup, r, FREE)

    def test_nan_weights_are_refused(self):
        w = frame([[1.0], [np.nan], [1.0]])
        with self.assertRaises(ValueError):
            bt.run(w, frame([[0.01]] * 3), FREE)


class Turnover(unittest.TestCase):
    def test_entry_costs_one_and_holding_costs_nothing(self):
        res = bt.run(frame([[1.0]] * 4), frame([[0.01]] * 4), FREE)
        self.assertEqual(res.turnover.round(9).tolist(), [0.0, 1.0, 0.0, 0.0])

    def test_switching_names_costs_two(self):
        w = frame([[1, 0], [1, 0], [0, 1], [0, 1]], cols=("A", "B"))
        res = bt.run(w, frame([[0.0, 0.0]] * 4, cols=("A", "B")), FREE)
        self.assertEqual(res.turnover.round(9).tolist(), [0.0, 1.0, 0.0, 2.0])  # decided on row 2, held from row 3

    def test_a_daily_row_rebalances_the_drift_back(self):
        """A row every day is a rebalance every day: after one name doubles,
        restoring 50/50 trades a third of the book."""
        w = frame([[.5, .5]] * 3, cols=("A", "B"))
        r = frame([[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]], cols=("A", "B"))
        res = bt.run(w, r, FREE)
        self.assertAlmostEqual(res.turnover.iloc[2], 1.0 / 3.0, places=6)
        # target unchanged at 0.5/0.5 while held weights drifted to 2/3, 1/3


    def test_between_rows_positions_drift_and_nothing_trades(self):
        w = pd.DataFrame([[.5, .5]], pd.bdate_range("2024-01-01", periods=1), ["A", "B"])
        r = frame([[0.0, 0.0], [1.0, 0.0], [0.0, 0.0], [0.5, 0.0]], cols=("A", "B"))
        res = bt.run(w, r, FREE)
        self.assertEqual(res.turnover.round(9).tolist(), [0.0, 1.0, 0.0, 0.0])
        self.assertAlmostEqual(res.held["A"].iloc[2], 2.0 / 3.0)
        self.assertAlmostEqual((1 + res.gross).prod(), (0.5 * 2 * 1.5 + 0.5))  # buy and hold

    def test_a_weekly_row_trades_on_its_day_only(self):
        r = frame([[0.01, -0.01]] * 11, cols=("A", "B"))
        w = frame([[.5, .5]] * 11, cols=("A", "B")).iloc[::5]
        res = bt.run(w, r, FREE)
        self.assertEqual([i for i, t in enumerate(res.turnover) if t > 1e-12], [1, 6])

    def test_a_decision_on_a_non_trading_day_takes_effect_after_the_next_session(self):
        r = frame([[0.0]] * 4, start="2024-01-04")  # Thu Fri Mon Tue
        w = pd.DataFrame([[1.0]], pd.to_datetime(["2024-01-06"]), ["A"])  # Saturday
        res = bt.run(w, r, FREE)
        self.assertEqual(res.held["A"].tolist(), [0.0, 0.0, 0.0, 1.0])

    def test_of_two_decisions_landing_on_one_session_the_later_wins(self):
        r = frame([[0.0, 0.0]] * 4, cols=("A", "B"), start="2024-01-04")  # Thu Fri Mon Tue
        w = pd.DataFrame([[1.0, 0.0], [0.0, 1.0]], pd.to_datetime(["2024-01-06", "2024-01-07"]), ["A", "B"])  # Sat, Sun
        res = bt.run(w, r, FREE)
        self.assertEqual(res.held.iloc[3].tolist(), [0.0, 1.0])


class Exposure(unittest.TestCase):
    def test_normalised_long_only_weights_are_not_leverage(self):
        rng = np.random.default_rng(0)
        for n in (7, 13, 49, 77):
            w = pd.DataFrame(rng.random((40, n)), pd.bdate_range("2024-01-01", periods=40))
            w = w.div(w.sum(axis=1), axis=0)
            r = pd.DataFrame(rng.normal(0, 0.02, (40, n)), w.index)
            res = bt.run(w, r, CostModel(0.25))
            self.assertEqual(res.costs["margin"].sum(), 0.0)

    def test_leverage_just_above_one_still_needs_a_rate(self):
        with self.assertRaises(CostNotStated):
            bt.run(frame([[1.001]] * 3), frame([[0.0]] * 3), CostModel(0.1))

    def test_a_levered_book_that_is_wiped_out_raises(self):
        r = frame([[0.0], [-0.7], [0.1]])
        with self.assertRaises(bt.EquityExhausted):
            bt.run(frame([[2.0]] * 3), r, CostModel(0.0, margin_apr=0.0))

    def test_costs_that_exhaust_equity_raise(self):
        w = frame([[1, 0], [0, 1]] * 3, cols=("A", "B"))
        with self.assertRaises(bt.EquityExhausted):
            bt.run(w, frame([[0.0, 0.0]] * 6, cols=("A", "B")), CostModel(60.0))

    def test_an_infinite_return_is_refused(self):
        with self.assertRaises(ValueError):
            bt.run(frame([[1.0]] * 3), frame([[0.0], [np.inf], [0.0]]), FREE)


class Costs(unittest.TestCase):
    def test_slippage_is_charged_on_traded_notional(self):
        res = bt.run(frame([[1.0]] * 3), frame([[0.0]] * 3), CostModel(0.25))
        self.assertAlmostEqual(res.costs["slippage"].sum(), 0.0025)

    def test_commission_is_charged_on_traded_notional(self):
        res = bt.run(frame([[1.0]] * 3), frame([[0.0]] * 3), CostModel(0.0, commission_bps=10))
        self.assertAlmostEqual(res.costs["commission"].sum(), 0.001)

    def test_borrow_accrues_over_calendar_days_on_a_360_basis(self):
        idx = pd.to_datetime(["2024-01-04", "2024-01-05", "2024-01-08"])  # Thu, Fri, Mon
        r = pd.DataFrame(0.0, idx, ["A"])
        w = pd.DataFrame(-1.0, idx, ["A"])
        res = bt.run(w, r, CostModel(0.0, borrow_apr=8.0))
        self.assertAlmostEqual(res.costs["borrow"].iloc[2], 0.08 / 360 * 3)

    def test_a_short_book_with_no_borrow_rate_is_refused(self):
        with self.assertRaises(CostNotStated):
            bt.run(frame([[-1.0]] * 3), frame([[0.0]] * 3), CostModel(0.1))

    def test_leverage_is_charged_margin_interest_on_the_debit_only(self):
        res = bt.run(frame([[2.0]] * 3), frame([[0.0]] * 3), CostModel(0.0, margin_apr=10.0))
        self.assertAlmostEqual(res.costs["margin"].iloc[2], 1.0 * 0.10 / 360)

    def test_leverage_with_no_margin_rate_is_refused(self):
        with self.assertRaises(CostNotStated):
            bt.run(frame([[2.0]] * 3), frame([[0.0]] * 3), CostModel(0.1))

    def test_net_is_gross_less_every_cost(self):
        res = bt.run(frame([[1.0]] * 3), frame([[0.01]] * 3), CostModel(0.25, commission_bps=5))
        self.assertTrue(np.allclose(res.net, res.gross - res.costs.sum(axis=1)))


class MissingReturns(unittest.TestCase):
    def setUp(self):
        self.w = frame([[1.0]] * 4)
        self.r = frame([[0.01], [0.01], [np.nan], [0.01]])

    def test_a_held_name_with_no_return_is_an_error_by_default(self):
        with self.assertRaises(bt.MissingReturn):
            bt.run(self.w, self.r, FREE)

    def test_zero_fill_is_explicit_and_counted(self):
        res = bt.run(self.w, self.r, FREE, on_missing="zero")
        self.assertEqual(res.zeroed_position_days, 1)

    def test_a_missing_return_on_a_name_not_held_is_fine(self):
        res = bt.run(frame([[0.0]] * 4), self.r, FREE)
        self.assertEqual(res.zeroed_position_days, 0)


class Sweep(unittest.TestCase):
    def test_a_short_book_gets_three_slippages_by_two_borrows(self):
        models = costs.sweep(CostModel(0.1), has_shorts=True, has_leverage=False)
        self.assertEqual(len(models), 6)
        self.assertEqual({m.borrow_apr for m in models}, {1.0, 8.0})

    def test_a_long_only_book_sweeps_slippage_alone(self):
        models = costs.sweep(CostModel(0.1), has_shorts=False, has_leverage=False)
        self.assertEqual(len(models), 3)

    def test_the_headline_is_the_middle_slippage_at_hard_to_borrow(self):
        h = costs.headline(costs.sweep(CostModel(0.1), True, False))
        self.assertEqual((h.slippage_pct, h.borrow_apr), (0.25, 8.0))

    def test_a_slippage_override_replaces_the_swept_points(self):
        models = costs.sweep(CostModel(0.1), has_shorts=False, has_leverage=False,
                             slippage_sweep=(0.01, 0.02, 0.05))
        self.assertEqual(sorted(m.slippage_pct for m in models), [0.01, 0.02, 0.05])

    def test_a_slippage_override_does_not_change_the_default_for_other_callers(self):
        costs.sweep(CostModel(0.1), False, False, slippage_sweep=(0.01,))
        models = costs.sweep(CostModel(0.1), False, False)
        self.assertEqual(sorted(m.slippage_pct for m in models), sorted(costs.SLIPPAGE_SWEEP))

    def test_the_headline_still_resolves_when_the_override_includes_it(self):
        h = costs.headline(costs.sweep(CostModel(0.1), True, False,
                                       slippage_sweep=(0.01, 0.02, 0.05, 0.10, 0.25)))
        self.assertEqual((h.slippage_pct, h.borrow_apr), (0.25, 8.0))


if __name__ == "__main__":
    unittest.main()
