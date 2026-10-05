import os
import tempfile
import unittest

from lab.engine import registry
from tests.engine_fixtures import TODAY, write_registration


class Registration(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_the_template_is_deliberately_invalid(self):
        text = open(os.path.join(registry.registry_dir(), "TEMPLATE.md")).read()
        self.assertGreater(len(registry.problems(registry.parse(text), TODAY)), 10)

    def test_a_complete_registration_passes(self):
        write_registration(self.dir)
        self.assertEqual(registry.require_registered("toy", self.dir, today=TODAY)["id"], "toy")

    def test_a_missing_file_is_not_registered(self):
        with self.assertRaises(registry.NotRegistered):
            registry.require_registered("nope", self.dir, today=TODAY)

    def test_a_file_whose_id_differs_from_its_name_is_refused(self):
        write_registration(self.dir, id="other")
        os.rename(os.path.join(self.dir, "other.md"), os.path.join(self.dir, "toy.md"))
        with self.assertRaises(registry.NotRegistered):
            registry.require_registered("toy", self.dir, today=TODAY)

    def test_six_parameters_are_refused(self):
        write_registration(self.dir, params="{a=1,b=2,c=3,d=4,e=5,f=6}")
        with self.assertRaises(registry.NotRegistered):
            registry.require_registered("toy", self.dir, today=TODAY)

    def test_five_parameters_and_zero_parameters_are_allowed(self):
        write_registration(self.dir, id="five", params="{a=1,b=2,c=3,d=4,e=5}")
        write_registration(self.dir, id="zero", params="{}")
        registry.require_registered("five", self.dir, today=TODAY)
        registry.require_registered("zero", self.dir, today=TODAY)

    def test_one_sizing_rule_is_refused(self):
        write_registration(self.dir, sizing='["equal_weight"]')
        with self.assertRaises(registry.NotRegistered):
            registry.require_registered("toy", self.dir, today=TODAY)

    def test_the_same_sizing_rule_twice_is_still_one(self):
        write_registration(self.dir, sizing='["equal_weight", "equal_weight"]')
        with self.assertRaises(registry.NotRegistered):
            registry.require_registered("toy", self.dir, today=TODAY)

    def test_an_unknown_provenance_is_refused(self):
        write_registration(self.dir, provenance="vibes")
        with self.assertRaises(registry.NotRegistered):
            registry.require_registered("toy", self.dir, today=TODAY)

    def test_data_derived_needs_its_burden_stated(self):
        write_registration(self.dir, provenance="data_derived")
        with self.assertRaises(registry.NotRegistered):
            registry.require_registered("toy", self.dir, today=TODAY)
        write_registration(self.dir, provenance="data_derived", burden="held-out by construction")
        registry.require_registered("toy", self.dir, today=TODAY)

    def test_registering_in_the_future_is_refused(self):
        write_registration(self.dir)
        from datetime import date
        with self.assertRaises(registry.NotRegistered):
            registry.require_registered("toy", self.dir, today=date(2025, 1, 1))

    def test_a_file_with_no_fenced_block_is_refused(self):
        with open(os.path.join(self.dir, "x.md"), "w") as h:
            h.write("# no block\n")
        with self.assertRaises(registry.NotRegistered):
            registry.require_registered("x", self.dir, today=TODAY)


if __name__ == "__main__":
    unittest.main()


V2 = '''ruleset = "v2"
decision_sizing = "equal_weight"
decision_execution = "next_open"
decision_slippage_pct = 0.05
decision_borrow_apr = 1.0'''


class RuleSetV2(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def check(self, extra):
        write_registration(self.dir, extra=extra)
        return registry.problems(registry.load("toy", self.dir), today=TODAY)

    def test_a_registration_without_a_rule_set_is_the_first(self):
        write_registration(self.dir)
        self.assertEqual(registry.ruleset(registry.load("toy", self.dir)), "v1")

    def test_a_complete_v2_registration_passes(self):
        self.assertEqual(self.check(V2), [])

    def test_an_unknown_rule_set_is_refused(self):
        self.assertTrue(any("ruleset" in p for p in self.check('ruleset = "v9"')))

    def test_v2_without_a_decision_sizing_in_the_registered_rules_is_refused(self):
        bad = V2.replace('"equal_weight"', '"kelly"')
        self.assertTrue(any("decision_sizing" in p for p in self.check(bad)))

    def test_v2_without_an_execution_convention_is_refused(self):
        bad = V2.replace('decision_execution = "next_open"', 'decision_execution = ""')
        self.assertTrue(any("decision_execution" in p for p in self.check(bad)))

    def test_v2_with_a_missing_or_nonpositive_slippage_is_refused(self):
        for bad in (V2.replace("decision_slippage_pct = 0.05\n", ""),
                    V2.replace("0.05", "0"), V2.replace("0.05", "-1")):
            self.assertTrue(any("decision_slippage_pct" in p for p in self.check(bad)))

    def test_a_negative_borrow_is_refused_and_an_absent_one_is_allowed(self):
        self.assertTrue(any("decision_borrow_apr" in p
                            for p in self.check(V2.replace("= 1.0", "= -1.0"))))
        self.assertEqual(self.check(V2.replace("decision_borrow_apr = 1.0", "")), [])


class BenchmarkAcknowledgement(unittest.TestCase):
    def test_a_blank_acknowledgement_is_refused(self):
        d = tempfile.mkdtemp()
        write_registration(d, extra='benchmark_coverage_acknowledged = ""')
        self.assertTrue(any("benchmark_coverage_acknowledged" in p
                            for p in registry.problems(registry.load("toy", d), today=TODAY)))
