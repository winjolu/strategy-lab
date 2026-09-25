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

    def test_a_levered_book_without_a_stated_margin_rate_never_reports(self):
        # a margin rate left unstated on a levered book must refuse
        levered = {k: v * 3 for k, v in self.w.items()}
        with self.assertRaises(costs.CostNotStated):
            self.go(weights_by_sizing=levered)


if __name__ == "__main__":
    unittest.main()
