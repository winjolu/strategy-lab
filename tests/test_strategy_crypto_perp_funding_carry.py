import unittest

import numpy as np
import pandas as pd

from lab.engine import backtest, costs, pipeline
from lab.strategies import crypto_perp_funding_carry as s


def days(start, n):
    return pd.date_range(start, periods=n, freq="D")


# 2024-01-01 is a Monday; 5-9 Jan is Fri..Tue.
CAL = pd.DatetimeIndex(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04",
                        "2024-01-05", "2024-01-08", "2024-01-09"])


class UnitReturns(unittest.TestCase):
    def test_it_is_the_change_in_the_ratio(self):
        ratio = pd.Series([1.0, 1.01, 1.0], days("2024-01-01", 3))
        out = s.unit_returns(ratio)
        self.assertTrue(pd.isna(out.iloc[0]))
        self.assertAlmostEqual(out.iloc[1], 0.01)
        self.assertAlmostEqual(out.iloc[2], 1.0 / 1.01 - 1.0)

    def test_a_missing_day_makes_both_neighbouring_returns_missing(self):
        ratio = pd.Series([1.0, np.nan, 1.02, 1.03], days("2024-01-01", 4))
        out = s.unit_returns(ratio)
        self.assertTrue(pd.isna(out.iloc[1]) and pd.isna(out.iloc[2]))
        self.assertAlmostEqual(out.iloc[3], 1.03 / 1.02 - 1.0)

    def test_a_series_with_holes_in_its_dates_is_refused(self):
        ratio = pd.Series([1.0, 1.1], pd.DatetimeIndex(["2024-01-01", "2024-01-04"]))
        with self.assertRaises(ValueError):
            s.unit_returns(ratio)


class Fold(unittest.TestCase):
    def daily(self, value, start="2024-01-01", n=10):
        return pd.Series(value, days(start, n), dtype=float)

    def test_the_weekend_lands_on_monday_and_returns_compound(self):
        r = self.daily(0.01)
        out = s.fold(r, CAL, "compound")
        self.assertAlmostEqual(out["2024-01-02"], 0.01)
        # Fri 5 Jan -> Mon 8 Jan row covers Sat, Sun, Mon
        self.assertAlmostEqual(out["2024-01-08"], 1.01 ** 3 - 1.0)

    def test_funding_sums_rather_than_compounds(self):
        f = self.daily(0.001)
        out = s.fold(f, CAL, "sum")
        self.assertAlmostEqual(out["2024-01-02"], 0.001)
        self.assertAlmostEqual(out["2024-01-08"], 0.003)

    def test_one_missing_constituent_day_makes_the_row_missing(self):
        r = self.daily(0.01)
        r["2024-01-06"] = np.nan          # a Saturday
        out = s.fold(r, CAL, "compound")
        self.assertTrue(pd.isna(out["2024-01-08"]))
        self.assertFalse(pd.isna(out["2024-01-05"]))
        self.assertFalse(pd.isna(out["2024-01-09"]))

    def test_the_first_trading_day_has_no_previous_day_and_is_dropped(self):
        out = s.fold(self.daily(0.01), CAL, "compound")
        self.assertNotIn(pd.Timestamp("2024-01-01"), out.index)
        self.assertEqual(out.index[0], pd.Timestamp("2024-01-02"))

    def test_days_after_the_last_trading_day_are_not_folded_in(self):
        r = self.daily(0.01, n=14)
        out = s.fold(r, CAL, "compound")
        self.assertEqual(out.index.max(), pd.Timestamp("2024-01-09"))
        self.assertAlmostEqual(out["2024-01-09"], 0.01)

    def test_a_day_missing_from_the_series_itself_counts_as_missing(self):
        r = self.daily(0.01, n=8)         # stops on the 8th; 9 Jan is absent
        out = s.fold(r, CAL, "compound")
        self.assertTrue(pd.isna(out["2024-01-09"]))

    def test_an_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            s.fold(self.daily(0.0), CAL, "mean")

    def test_a_calendar_out_of_order_is_refused(self):
        with self.assertRaises(ValueError):
            s.fold(self.daily(0.0), CAL[::-1], "sum")


class Signal(unittest.TestCase):
    def test_it_annualises_on_calendar_days_and_in_percent(self):
        f = pd.Series(0.0003, days("2024-01-01", 40))
        apr = s.trailing_funding_apr_pct(f)
        self.assertAlmostEqual(apr.iloc[-1], 0.0003 * 365 * 100)

    def test_it_is_undefined_until_a_full_window_exists(self):
        f = pd.Series(0.0003, days("2024-01-01", 40))
        apr = s.trailing_funding_apr_pct(f)
        self.assertTrue(apr.iloc[:29].isna().all())
        self.assertFalse(pd.isna(apr.iloc[29]))

    def test_a_hole_in_the_window_leaves_it_undefined(self):
        f = pd.Series(0.0003, days("2024-01-01", 60))
        f.iloc[40] = np.nan
        apr = s.trailing_funding_apr_pct(f)
        self.assertTrue(apr.iloc[40:70].isna().all())
        self.assertFalse(pd.isna(apr.iloc[39]))

    def test_it_does_not_read_the_future(self):
        f = pd.Series(0.0003, days("2024-01-01", 60))
        a = s.trailing_funding_apr_pct(f)
        f.iloc[50:] = 0.01
        b = s.trailing_funding_apr_pct(f)
        pd.testing.assert_series_equal(a.iloc[:50], b.iloc[:50])


class Weights(unittest.TestCase):
    def apr(self, btc, eth):
        idx = days("2024-01-01", len(btc))
        return {"btc": pd.Series(btc, idx, dtype=float), "eth": pd.Series(eth, idx, dtype=float)}

    def test_threshold_holds_a_coin_only_above_the_line_and_parks_the_rest_in_cash(self):
        idx = days("2024-01-01", 3)
        w = s.weights(self.apr([20, 5, 20], [5, 5, 20]), idx, "threshold")
        self.assertEqual(list(w.loc[idx[0]]), [0.5, 0.0, 0.5])
        self.assertEqual(list(w.loc[idx[1]]), [0.0, 0.0, 1.0])
        self.assertEqual(list(w.loc[idx[2]]), [0.5, 0.5, 0.0])

    def test_exactly_at_the_threshold_is_not_held(self):
        idx = days("2024-01-01", 1)
        w = s.weights(self.apr([10.0], [10.0]), idx, "threshold")
        self.assertEqual(w.loc[idx[0], "cash"], 1.0)

    def test_an_undefined_signal_is_cash_never_carry(self):
        idx = days("2024-01-01", 2)
        w = s.weights(self.apr([np.nan, 20], [np.nan, np.nan]), idx, "threshold")
        self.assertEqual(w.loc[idx[0], "cash"], 1.0)
        self.assertEqual(list(w.loc[idx[1]]), [0.5, 0.0, 0.5])

    def test_always_on_ignores_the_signal(self):
        idx = days("2024-01-01", 2)
        w = s.weights(self.apr([np.nan, 0], [-50, 0]), idx, "always_on")
        self.assertTrue((w[["btc", "eth"]] == 0.5).all().all())
        self.assertTrue((w["cash"] == 0.0).all())

    def test_gross_is_always_one(self):
        idx = days("2024-01-01", 4)
        for rule in ("threshold", "always_on"):
            w = s.weights(self.apr([20, 5, np.nan, 11], [5, 20, 20, np.nan]), idx, rule)
            self.assertTrue(np.allclose(w.sum(axis=1), 1.0))

    def test_an_unknown_rule_is_refused(self):
        with self.assertRaises(ValueError):
            s.weights(self.apr([1], [1]), days("2024-01-01", 1), "momentum")


class Assemble(unittest.TestCase):
    def build(self, venue_rate=0.0002, ratio=1.0):
        d = days("2023-11-01", 90)
        ratio_s = pd.Series(ratio, d)
        fund = pd.Series(venue_rate, d)
        cal = pd.bdate_range("2023-12-04", "2024-01-26")
        bench = pd.Series(0.0001, cal, name="BIL")
        return s.assemble({"btc": ratio_s, "eth": ratio_s}, {"btc": fund, "eth": fund}, bench, cal)

    def test_the_funding_charged_to_the_short_is_the_negated_venue_rate(self):
        inp = self.build(venue_rate=0.0002)
        self.assertTrue((inp.funding.dropna() < 0).all().all())     # a receipt
        self.assertAlmostEqual(inp.funding["btc"].iloc[1], -0.0002)

    def test_cash_carries_the_benchmark_return_and_funding_has_no_cash_column(self):
        inp = self.build()
        self.assertTrue((inp.returns["cash"] == 0.0001).all())
        self.assertNotIn("cash", inp.funding.columns)

    def test_everything_sits_on_the_trading_calendar_after_its_first_day(self):
        inp = self.build()
        cal = pd.bdate_range("2023-12-04", "2024-01-26")[1:]
        for frame in (inp.returns, inp.funding, inp.weights_by_sizing["threshold"]):
            self.assertTrue(frame.index.equals(cal))

    def test_a_flat_ratio_means_the_hedge_earns_exactly_the_funding(self):
        inp = self.build(venue_rate=0.0002, ratio=1.05)
        cost = costs.CostModel(0.0, borrow_apr=None)
        bt = backtest.run(inp.weights_by_sizing["always_on"].iloc[5:], inp.returns, cost,
                          funding=inp.funding)
        net = bt.net.iloc[6:]
        # each trading day earns one day's funding on a fully held unit (a
        # Monday row has three days' worth), nothing from price
        for ts, v in net.items():
            n = 3 if ts.dayofweek == 0 else 1
            self.assertAlmostEqual(v, 0.0002 * n, places=12)

    def test_a_missing_funding_day_on_a_held_unit_stops_the_run(self):
        d = days("2023-11-01", 90)
        ratio = pd.Series(1.0, d)
        fund = pd.Series(0.0002, d)
        fund["2024-01-10"] = np.nan
        cal = pd.bdate_range("2023-12-04", "2024-01-26")
        inp = s.assemble({"btc": ratio, "eth": ratio}, {"btc": fund, "eth": fund},
                         pd.Series(0.0001, cal, name="BIL"), cal)
        with self.assertRaises(backtest.FundingMissing):
            backtest.run(inp.weights_by_sizing["always_on"], inp.returns,
                         costs.CostModel(0.0, borrow_apr=None), funding=inp.funding)


class RowRate(unittest.TestCase):
    def frame(self, freq):
        idx = pd.date_range("2022-01-03", periods=400 if freq == "D" else 300, freq=freq)
        return pd.DataFrame(0.0, idx, ["a"])

    def test_a_365_rows_a_year_series_is_refused(self):
        with self.assertRaises(ValueError):
            pipeline._guard_row_rate(self.frame("D"))

    def test_a_weekday_series_passes(self):
        pipeline._guard_row_rate(self.frame("B"))

    def test_a_short_series_is_not_judged(self):
        pipeline._guard_row_rate(pd.DataFrame(0.0, pd.date_range("2022-01-03", periods=40, freq="D"), ["a"]))

    def test_evaluate_refuses_a_calendar_day_series_before_computing_anything(self):
        import tempfile
        from tests.engine_fixtures import TODAY, fresh_db, panel, write_registration
        from tests.test_engine_pipeline import weights_for
        d = tempfile.mkdtemp()
        write_registration(d)
        ret, bench = panel()
        idx = pd.date_range("2022-01-03", periods=len(ret), freq="D")
        ret, bench = ret.set_axis(idx), bench.set_axis(idx)
        db = fresh_db()
        with self.assertRaises(ValueError) as caught:
            pipeline.evaluate(
                strategy_id="toy", weights_by_sizing=weights_for(ret), returns=ret,
                benchmark=bench, db=db, produced_by="analyst-a", effort="medium",
                data_manifest="synthetic", binding_constraint="settled cash",
                base_cost=costs.CostModel(0.25), registry_directory=d, today=TODAY)
        self.assertIn("rows a year", str(caught.exception))


if __name__ == "__main__":
    unittest.main()


class RegisteredFileThroughThePipeline(unittest.TestCase):
    """The real registration, synthetic data: proves the file's cell, sweep
    and execution fields are ones the pipeline can actually evaluate."""

    def run_it(self, funding_rate):
        import os
        import shutil
        import tempfile
        from datetime import date
        from lab.engine import registry
        from tests.engine_fixtures import fresh_db
        d = tempfile.mkdtemp()
        shutil.copy(os.path.join(registry.registry_dir(), "crypto-perp-funding-carry.md"), d)
        rng = np.random.default_rng(3)
        cal = pd.bdate_range("2021-10-01", "2025-09-29")
        every = pd.date_range("2021-08-01", "2025-09-30", freq="D")
        ratio = pd.Series(1.0 + np.cumsum(rng.normal(0, 0.0004, len(every))) * 0.1, every)
        fund = pd.Series(funding_rate + rng.normal(0, 0.00002, len(every)), every)
        bench = pd.Series(0.00015, cal, name="BIL")
        inp = s.assemble({"btc": ratio, "eth": ratio}, {"btc": fund, "eth": fund}, bench, cal)
        return pipeline.evaluate(
            "crypto-perp-funding-carry", inp.weights_by_sizing, inp.returns, inp.benchmark,
            fresh_db(), produced_by="analyst-a", effort="medium", data_manifest="synthetic",
            binding_constraint="venue access", base_cost=costs.CostModel(0.15),
            funding=inp.funding, execution="utc_midnight", registry_directory=d,
            today=date(2026, 10, 6))

    def test_both_sizing_rules_run_and_the_decision_cell_is_the_registered_one(self):
        ev = self.run_it(0.0004)          # about 15% a year, so the threshold holds
        self.assertEqual({r.name for r in ev.results}, {"threshold", "always_on"})
        self.assertAlmostEqual(ev.decision_cell[0], 0.15)
        decided = [r for r in ev.results if r.decides]
        self.assertEqual([r.name for r in decided], ["threshold"])

    def test_the_sweep_includes_the_before_cost_cell_and_funding_is_charged(self):
        ev = self.run_it(0.0004)
        always = next(r for r in ev.results if r.name == "always_on")
        slips = [row["slippage_pct"] for row in always.sweep]
        self.assertIn(0.0, slips)
        self.assertTrue(all(row["active_pct_per_year"] > 0 for row in always.sweep))

    def test_a_zero_funding_world_loses_the_cash_yield_it_gives_up(self):
        # collateral held in coin earns no interest, so with no funding the
        # active return over bills is minus the bill yield: 0.015% a day on
        # 252 rows is 3.78% a year
        ev = self.run_it(0.0)
        always = next(r for r in ev.results if r.name == "always_on")
        zero = next(row for row in always.sweep if row["slippage_pct"] == 0.0)
        self.assertAlmostEqual(zero["active_pct_per_year"], -3.78, delta=0.2)
