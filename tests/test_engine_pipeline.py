import tempfile
import unittest

import pandas as pd

from lab.engine import costs, pipeline, report, sizing
from lab.engine import score as score_mod
from lab.results import db as results_db
from tests.engine_fixtures import TODAY, fresh_db, panel, write_registration

import numpy as np


def weights_for(ret, seed=2):
    rng = np.random.default_rng(seed)
    s = pd.DataFrame(np.sign(rng.normal(size=ret.shape)), ret.index, ret.columns)
    s = s.where(s != 0, 1.0)
    vol = ret.rolling(20).std()
    return {"equal_weight": sizing.equal_weight(s, long_short=True),
            "inverse_vol": sizing.inverse_vol(s, vol, long_short=True)}


class Evaluate(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        write_registration(self.dir)
        self.ret, self.bench = panel()
        self.w = weights_for(self.ret)
        self.db = fresh_db()

    def go(self, **overrides):
        args = dict(strategy_id="toy", weights_by_sizing=self.w, returns=self.ret,
                    benchmark=self.bench, db=self.db, produced_by="analyst-a", effort="medium",
                    data_manifest="synthetic", binding_constraint="settled cash",
                    base_cost=costs.CostModel(0.25), registry_directory=self.dir, today=TODAY)
        args.update(overrides)
        return pipeline.evaluate(**args)

    def test_an_unregistered_strategy_cannot_be_evaluated(self):
        with self.assertRaises(Exception) as cm:
            self.go(strategy_id="ghost")
        self.assertEqual(type(cm.exception).__name__, "NotRegistered")

    def test_reporting_different_sizing_rules_than_registered_is_refused(self):
        with self.assertRaises(pipeline.RegistrationMismatch):
            self.go(weights_by_sizing={"equal_weight": self.w["equal_weight"]})

    def test_measuring_a_different_benchmark_than_registered_is_refused(self):
        with self.assertRaises(pipeline.RegistrationMismatch):
            self.go(benchmark=self.bench.rename("SPY"))

    def test_data_in_the_holdout_is_refused_before_stage_three(self):
        write_registration(self.dir, holdout="2023-06-01")
        with self.assertRaises(pipeline.HoldoutViolation):
            self.go()

    def test_the_holdout_opens_at_stage_three(self):
        write_registration(self.dir, holdout="2023-06-01")
        self.assertEqual(self.go(stage=3).stage, 3)

    def test_a_missing_binding_constraint_is_refused(self):
        with self.assertRaises(ValueError):
            self.go(binding_constraint="  ")

    def test_each_sizing_rule_is_one_run_and_one_trial(self):
        ev = self.go()
        self.assertEqual(len(ev.results), 2)
        self.assertEqual(self.db.trial_count("fam"), 2)

    def test_a_reported_figure_is_found_again_from_its_run_id(self):
        ev = self.go()
        r = ev.results[0]
        stored = self.db.figure(r.run_id, "active_t")["value"]
        self.assertAlmostEqual(stored, r.headline["active_t_newey_west"])
        cfg = self.db.run(r.run_id)["config"]
        self.assertEqual(cfg["sizing"], r.name)
        self.assertEqual(self.db.run(r.run_id)["produced_by"], "analyst-a")

    def test_the_sweep_covers_every_slippage_and_borrow_for_a_short_book(self):
        self.assertEqual(len(self.go().results[0].sweep), 6)

    def test_first_evaluation_is_not_deflated_and_says_so(self):
        text = report.render(self.go())
        self.assertIn("Not deflated", text)

    def test_a_second_evaluation_is_deflated_lab_wide_and_per_family(self):
        self.go()
        ev = self.go()
        h = ev.results[0].headline
        self.assertIsNotNone(h["deflated"])
        self.assertIsNotNone(h["deflated_lab"])
        self.assertGreater(h["deflated"]["trials"], 2)

    def test_lab_wide_trials_exceed_a_single_familys(self):
        write_registration(self.dir, id="other", family="elsewhere")
        self.go()
        self.go(strategy_id="other")
        ev = self.go()
        h = ev.results[0].headline
        self.assertGreater(h["deflated_lab"]["trials"], h["deflated"]["trials"])

    def test_the_report_labels_every_figure_and_names_the_constraint(self):
        text = report.render(self.go())
        for needle in ("Binding constraint", "settled cash", "(active)", "(abs)",
                       "upper bound", "Current regime", "Cost sweep", "run `"):
            self.assertIn(needle, text)

    def test_a_registered_slippage_sweep_overrides_the_lab_default(self):
        write_registration(self.dir, extra='slippage_sweep_pct = [0.01, 0.02, 0.05, 0.25]')
        ev = self.go(base_cost=costs.CostModel(0.0))
        seen = sorted({row["slippage_pct"] for row in ev.results[0].sweep})
        self.assertEqual(seen, [0.01, 0.02, 0.05, 0.25])

    def test_a_strategy_without_a_registered_sweep_keeps_the_lab_default(self):
        ev = self.go()
        seen = sorted({row["slippage_pct"] for row in ev.results[0].sweep})
        self.assertEqual(seen, sorted(costs.SLIPPAGE_SWEEP))

    def test_a_levered_book_without_a_stated_margin_rate_never_reports(self):
        # a margin rate left unstated on a levered book must refuse
        levered = {k: v * 3 for k, v in self.w.items()}
        with self.assertRaises(costs.CostNotStated):
            self.go(weights_by_sizing=levered)


if __name__ == "__main__":
    unittest.main()


class DecisionCell(unittest.TestCase):
    """Under rule set v2 the verdict's cell is registered, and everything
    the report shows beside the verdict is computed at that cell."""

    EXTRA = '''ruleset = "v2"
decision_sizing = "equal_weight"
decision_execution = "next_open"
decision_slippage_pct = 0.10
decision_borrow_apr = 1.0
slippage_sweep_pct = [0.05, 0.10, 0.25]'''

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        write_registration(self.dir, extra=self.EXTRA)
        self.ret, self.bench = panel()
        self.w = weights_for(self.ret)
        self.db = fresh_db()

    def go(self, **overrides):
        args = dict(strategy_id="toy", weights_by_sizing=self.w, returns=self.ret,
                    benchmark=self.bench, db=self.db, produced_by="analyst-a", effort="medium",
                    data_manifest="synthetic", binding_constraint="settled cash",
                    base_cost=costs.CostModel(0.25, borrow_apr=8.0), registry_directory=self.dir,
                    today=TODAY, execution="next_open")
        args.update(overrides)
        return pipeline.evaluate(**args)

    def test_the_headline_is_read_at_the_registered_cell_not_the_lab_default(self):
        ev = self.go()
        for r in ev.results:
            self.assertEqual(r.cell, (0.10, 1.0))
            row = next(x for x in r.sweep if (x["slippage_pct"], x["borrow_apr"]) == (0.10, 1.0))
            self.assertAlmostEqual(r.headline["active_t_newey_west"], row["active_t"], places=9)

    def test_the_regime_slice_and_stored_sharpe_use_the_same_cell(self):
        ev = self.go()
        r = ev.results[0]
        stored = {f["name"]: f["value"] for f in self.db.figures_for_run(r.run_id)}
        self.assertAlmostEqual(stored["active_t"], r.headline["active_t_newey_west"], places=9)
        self.assertAlmostEqual(stored["active_sharpe_periodic"],
                               r.headline["active_sharpe_periodic"], places=9)
        self.assertIn("slip=0.1|borrow=1.0", " ".join(stored))

    def test_only_the_registered_sizing_rule_and_execution_decide(self):
        ev = self.go()
        self.assertEqual({r.name: r.decides for r in ev.results},
                         {"equal_weight": True, "inverse_vol": False})
        other = self.go(execution="same_close")
        self.assertEqual({r.decides for r in other.results}, {False})

    def test_a_cell_the_sweep_did_not_compute_is_refused_not_approximated(self):
        write_registration(self.dir, extra=self.EXTRA.replace(
            "decision_slippage_pct = 0.10", "decision_slippage_pct = 0.07"))
        with self.assertRaises(LookupError):
            self.go()

    def test_v2_without_an_execution_convention_is_refused(self):
        with self.assertRaises(ValueError):
            self.go(execution=None)

    def test_a_shorting_book_with_no_registered_borrow_is_refused(self):
        write_registration(self.dir, extra=self.EXTRA.replace("decision_borrow_apr = 1.0\n", ""))
        with self.assertRaises(costs.CostNotStated):
            self.go()

    def test_the_report_says_which_run_the_verdict_reads(self):
        text = report.render(self.go())
        self.assertIn("The verdict reads this one", text)
        self.assertIn("A flag, not the verdict", text)
        self.assertIn("Decision cost cell: slippage 0.1% per side, borrow 1.0% a year", text)

    def test_a_first_rule_set_registration_is_unchanged(self):
        write_registration(self.dir)
        ev = self.go(execution=None)
        self.assertEqual(ev.ruleset, "v1")
        self.assertEqual({r.cell for r in ev.results}, {(0.25, 8.0)})
        self.assertIn("Headline cost cell: slippage 0.25% per side, borrow 8.0%",
                      report.render(ev))


class ReportFlags(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        write_registration(self.dir)
        ret, bench = panel()
        self.text = report.render(pipeline.evaluate(
            "toy", weights_for(ret), ret, bench, fresh_db(), produced_by="analyst-a",
            effort="medium", data_manifest="synthetic", binding_constraint="settled cash",
            base_cost=costs.CostModel(0.25), registry_directory=self.dir, today=TODAY))

    def test_the_minimum_track_record_is_always_in_the_report(self):
        self.assertEqual(self.text.count("Minimum track record for the active Sharpe"), 2)

    def test_the_report_body_carries_no_cagr_and_no_verdict_wording(self):
        self.assertNotIn("CAGR", self.text)
        self.assertNotIn("record and drop", self.text)


class BenchmarkCoverage(unittest.TestCase):
    """A benchmark that starts late must not silently shorten the sample."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        write_registration(self.dir)
        self.ret, self.bench = panel()
        self.w = weights_for(self.ret)

    def go(self, bench):
        return pipeline.evaluate(
            "toy", self.w, self.ret, bench, fresh_db(), produced_by="analyst-a", effort="medium",
            data_manifest="synthetic", binding_constraint="settled cash",
            base_cost=costs.CostModel(0.25), registry_directory=self.dir, today=TODAY)

    def test_a_benchmark_starting_late_is_refused_and_says_which_dates_are_lost(self):
        with self.assertRaises(pipeline.BenchmarkCoverage) as cm:
            self.go(self.bench.iloc[300:])
        message = str(cm.exception)
        self.assertIn("starts", message)
        self.assertIn(f"{self.bench.index[300]:%Y-%m-%d}", message)
        self.assertIn("42.9%", message)

    def test_a_benchmark_missing_in_the_middle_is_refused_too(self):
        gappy = self.bench.copy()
        gappy.iloc[100:250] = np.nan
        with self.assertRaises(pipeline.BenchmarkCoverage):
            self.go(gappy)

    def test_a_written_acknowledgement_in_the_registration_allows_it(self):
        write_registration(self.dir, extra='benchmark_coverage_acknowledged = "BENCH lists later; the shorter sample is accepted"')
        ev = self.go(self.bench.iloc[300:])
        self.assertEqual(ev.results[0].headline["n_days"], 400)

    def test_a_gap_of_a_few_days_is_tolerated(self):
        self.go(self.bench.iloc[5:])

    def test_a_gap_just_over_the_tolerance_is_refused(self):
        over = int(len(self.bench) * pipeline.BENCHMARK_GAP_TOLERANCE) + 2
        with self.assertRaises(pipeline.BenchmarkCoverage):
            self.go(self.bench.iloc[over:])

    def test_the_report_prints_the_window_actually_evaluated(self):
        write_registration(self.dir, extra='benchmark_coverage_acknowledged = "accepted"')
        text = report.render(self.go(self.bench.iloc[300:]))
        self.assertIn(f"Evaluated window: {self.bench.index[300]:%Y-%m-%d}", text)
        self.assertIn("400 days", text)


class BreakEvenPerBorrowRate(unittest.TestCase):
    def test_every_swept_borrow_rate_gets_its_own_line_when_the_book_shorts(self):
        d = tempfile.mkdtemp()
        write_registration(d)
        ret, bench = panel()
        text = report.render(pipeline.evaluate(
            "toy", weights_for(ret), ret, bench, fresh_db(), produced_by="analyst-a", effort="medium",
            data_manifest="synthetic", binding_constraint="settled cash",
            base_cost=costs.CostModel(0.25), registry_directory=d, today=TODAY))
        self.assertEqual(text.count("Break-even slippage, at 1% borrow"), 2)
        self.assertEqual(text.count("Break-even slippage, at 8% borrow"), 2)


class ScoreAndHoldout(unittest.TestCase):
    EXTRA = DecisionCell.EXTRA

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ret, self.bench = panel()
        self.w = weights_for(self.ret)
        self.db = fresh_db()
        self.holdout = str(self.ret.index[400].date())       # 300 days of holdout
        write_registration(self.dir, extra=self.EXTRA, holdout=self.holdout)

    def go(self, ret=None, **overrides):
        ret = self.ret if ret is None else ret
        args = dict(strategy_id="toy", weights_by_sizing=self.w, returns=ret,
                    benchmark=self.bench.loc[ret.index], db=self.db, produced_by="analyst-a",
                    effort="medium", data_manifest="synthetic", binding_constraint="settled cash",
                    base_cost=costs.CostModel(0.25, borrow_apr=8.0), registry_directory=self.dir,
                    today=TODAY, execution="next_open", stage=3)
        args.update(overrides)
        return pipeline.evaluate(**args)

    def test_stage_one_reports_the_provisional_training_score_and_no_pooled_one(self):
        ret = self.ret[self.ret.index < self.holdout]
        ev = self.go(ret=ret, stage=1, weights_by_sizing={k: v.loc[ret.index] for k, v in self.w.items()})
        for r in ev.results:
            self.assertIsNotNone(r.training)
            self.assertIsNone(r.pooled)
            self.assertLess(r.training["end"], pd.Timestamp(self.holdout))
        self.assertIn("The holdout has not been read", report.render(ev))
        self.assertIsNone(ev.holdout_candidates)

    def test_stage_three_reports_the_pooled_score_and_counts_the_look(self):
        ev = self.go()
        self.assertEqual(ev.holdout_candidates, 1)
        for r in ev.results:
            self.assertIsNotNone(r.pooled)
            stored = {f["name"]: f["value"] for f in self.db.figures_for_run(r.run_id)}
            self.assertAlmostEqual(stored["pooled_active_sharpe"], r.pooled["sharpe"], places=9)
        text = report.render(ev)
        self.assertIn("**Score**", text)
        self.assertIn("1 candidate has now read it", text)

    def test_a_second_read_of_the_holdout_by_the_same_strategy_is_refused(self):
        self.go()
        with self.assertRaises(results_db.HoldoutAlreadyRead):
            self.go()

    def test_a_refused_second_read_leaves_the_look_count_and_the_trial_count_unchanged(self):
        self.go()
        trials = self.db.trial_count()
        with self.assertRaises(results_db.HoldoutAlreadyRead):
            self.go()
        self.assertEqual(self.db.holdout_look_count(self.holdout), 1)
        self.assertEqual(self.db.trial_count(), trials)

    def test_a_holdout_under_a_year_is_refused_and_takes_no_look(self):
        write_registration(self.dir, extra=self.EXTRA, holdout=str(self.ret.index[-100].date()))
        with self.assertRaises(score_mod.HoldoutTooShort):
            self.go()
        self.assertEqual(self.db.holdout_look_count(str(self.ret.index[-100].date())), 0)
        self.assertEqual(self.db.trial_count(), 0)

    def test_the_holdout_is_read_only_under_the_registered_execution_convention(self):
        with self.assertRaises(pipeline.RegistrationMismatch):
            self.go(execution="same_close")
        self.assertEqual(self.db.holdout_look_count(self.holdout), 0)
        self.assertEqual(self.db.trial_count(), 0)

    def test_a_first_rule_set_stage_three_run_is_unchanged(self):
        write_registration(self.dir, holdout=self.holdout)
        ev = self.go(execution=None)
        self.assertIsNone(ev.holdout_candidates)
        self.assertTrue(all(r.pooled is None and r.training is None for r in ev.results))
