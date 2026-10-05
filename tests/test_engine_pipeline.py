import tempfile
import unittest

import pandas as pd

from lab.engine import costs, pipeline, report, sizing
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
