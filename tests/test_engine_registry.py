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
