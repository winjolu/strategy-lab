"""Tests for the results database.

Each guard here was checked by deliberately breaking the thing it covers
and confirming the suite catches it; see the mutation notes on the
methods this exercises for the ones that matter most.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab.results import db as results_db


def fresh():
    path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    os.unlink(path)  # let ResultsDB create it fresh
    return results_db.ResultsDB(results_db.SQLiteBackend(path))


class TestRunRecording(unittest.TestCase):
    def test_record_run_returns_an_id_that_run_can_fetch(self):
        d = fresh()
        run_id = d.record_run(
            "xs-mr-khandani-lo", stage=1, config={"lookback": 5, "k": 10},
            produced_by="analyst-b", effort="high",
            data_manifest="watermark 2025-08-11",
        )
        row = d.run(run_id)
        self.assertEqual(row["strategy_id"], "xs-mr-khandani-lo")
        self.assertEqual(row["stage"], 1)
        self.assertEqual(row["config"], {"lookback": 5, "k": 10})
        self.assertEqual(row["data_manifest"], "watermark 2025-08-11")
        self.assertEqual(row["produced_by"], "analyst-b")
        self.assertEqual(row["effort"], "high")

    def test_config_round_trips_through_json_exactly(self):
        d = fresh()
        cfg = {"a": [1, 2, 3], "b": {"nested": True}, "c": None, "d": 1.5}
        run_id = d.record_run(
            "s", stage=0, config=cfg, produced_by="m", effort="low",
            data_manifest="w",
        )
        self.assertEqual(d.run(run_id)["config"], cfg)

    def test_two_runs_of_the_same_strategy_get_different_ids(self):
        d = fresh()
        a = d.record_run("s", 0, {}, "m", "low", data_manifest="w")
        b = d.record_run("s", 0, {}, "m", "low", data_manifest="w")
        self.assertNotEqual(a, b)

    def test_fetching_an_unknown_run_raises_rather_than_returning_none(self):
        d = fresh()
        with self.assertRaises(results_db.UnknownRun):
            d.run("not-a-real-id")

    def test_a_run_without_a_data_manifest_is_refused(self):
        """A caller that has not looked up the watermark is stopped here,
        not left with a row that looks complete and is not."""
        d = fresh()
        with self.assertRaises(ValueError):
            d.record_run("s", 0, {}, "m", "low")

    def test_code_versions_are_recorded_from_the_actual_checkouts(self):
        d = fresh()
        run_id = d.record_run(
            "s", 0, {}, "m", "low", data_manifest="w",
            lab_dir=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            market_core_dir=os.path.dirname(
                os.path.dirname(__import__("market_core").__file__)
            ),
        )
        row = d.run(run_id)
        self.assertNotEqual(row["lab_version"], "unknown")
        self.assertNotEqual(row["market_core_version"], "unknown")


class TestFigures(unittest.TestCase):
    """The required path: a figure can be re-found from its run id."""

    def test_a_recorded_figure_is_found_again_by_run_id(self):
        d = fresh()
        run_id = d.record_run("s", 1, {"k": 1}, "m", "low", data_manifest="w")
        d.record_figure(run_id, "sharpe", 1.42, unit="annualized")
        found = d.figure(run_id, "sharpe")
        self.assertEqual(found["value"], 1.42)
        self.assertEqual(found["unit"], "annualized")

    def test_figures_from_a_different_run_are_not_returned(self):
        d = fresh()
        a = d.record_run("s", 1, {}, "m", "low", data_manifest="w")
        b = d.record_run("s", 1, {}, "m", "low", data_manifest="w")
        d.record_figure(a, "sharpe", 1.0)
        d.record_figure(b, "sharpe", 2.0)
        self.assertEqual(d.figure(a, "sharpe")["value"], 1.0)
        self.assertEqual(d.figure(b, "sharpe")["value"], 2.0)

    def test_an_unrecorded_figure_name_returns_none_not_an_error(self):
        d = fresh()
        run_id = d.record_run("s", 1, {}, "m", "low", data_manifest="w")
        self.assertIsNone(d.figure(run_id, "nonexistent"))

    def test_a_figure_against_an_unregistered_run_is_refused(self):
        """A figure can never be recorded against a run_id that was
        never minted by record_run."""
        d = fresh()
        with self.assertRaises(results_db.UnknownRun):
            d.record_figure("made-up-id", "sharpe", 1.0)

    def test_figures_for_run_preserves_insertion_order(self):
        d = fresh()
        run_id = d.record_run("s", 1, {}, "m", "low", data_manifest="w")
        for name, value in [("sharpe", 1.0), ("mar", 0.5), ("max_dd", -0.2)]:
            d.record_figure(run_id, name, value)
        names = [f["name"] for f in d.figures_for_run(run_id)]
        self.assertEqual(names, ["sharpe", "mar", "max_dd"])


class TestTrials(unittest.TestCase):
    def test_trial_count_starts_at_zero(self):
        d = fresh()
        self.assertEqual(d.trial_count(), 0)
        self.assertEqual(d.trial_count("mean-reversion"), 0)

    def test_lab_wide_and_family_counts_both_advance(self):
        d = fresh()
        run_id = d.record_run("s", 1, {}, "m", "low", data_manifest="w")
        d.record_trial(run_id, family="mean-reversion", reason="baseline")
        d.record_trial(run_id, family="mean-reversion", reason="add stop")
        d.record_trial(run_id, family="momentum", reason="baseline")
        self.assertEqual(d.trial_count(), 3)
        self.assertEqual(d.trial_count("mean-reversion"), 2)
        self.assertEqual(d.trial_count("momentum"), 1)
        self.assertEqual(d.trial_count("carry"), 0)

    def test_a_trial_against_an_unregistered_run_is_refused(self):
        d = fresh()
        with self.assertRaises(results_db.UnknownRun):
            d.record_trial("made-up-id", family="x", reason="y")

    def test_a_negative_or_null_result_still_counts_as_a_trial(self):
        """Recording only the promising variants is exactly the
        selection deflation exists to correct for."""
        d = fresh()
        run_id = d.record_run("s", 1, {}, "m", "low", data_manifest="w")
        d.record_trial(run_id, family="f", reason="t < 1.5, dropped")
        self.assertEqual(d.trial_count("f"), 1)


class TestSchemaAndBackend(unittest.TestCase):
    def test_schema_creation_is_idempotent(self):
        path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        os.unlink(path)
        backend = results_db.SQLiteBackend(path)
        results_db.ResultsDB(backend)
        results_db.ResultsDB(backend)  # second init must not raise

    def test_backend_for_picks_sqlite_for_a_plain_path(self):
        backend = results_db.backend_for("/tmp/foo.db")
        self.assertIsInstance(backend, results_db.SQLiteBackend)

    def test_backend_for_picks_postgres_for_a_postgres_url(self):
        backend = results_db.backend_for("postgresql://host/db")
        self.assertIsInstance(backend, results_db.PostgresBackend)

    def test_postgres_backend_raises_rather_than_connecting(self):
        backend = results_db.PostgresBackend("postgresql://host/db")
        with self.assertRaises(NotImplementedError):
            backend.connect()

    def test_git_sha_on_a_non_git_directory_returns_unknown_not_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(results_db.git_sha(d), "unknown")


class TestRunsForStrategy(unittest.TestCase):
    def test_returns_only_that_strategys_runs_in_time_order(self):
        d = fresh()
        a = d.record_run("strat-a", 0, {}, "m", "low", data_manifest="w")
        b = d.record_run("strat-b", 0, {}, "m", "low", data_manifest="w")
        c = d.record_run("strat-a", 1, {}, "m", "low", data_manifest="w")
        rows = d.runs_for_strategy("strat-a")
        self.assertEqual([r["run_id"] for r in rows], [a, c])
        self.assertNotIn(b, [r["run_id"] for r in rows])


class TestFamilyFigures(unittest.TestCase):
    """The dispersion deflation reads has to come from what was recorded."""

    def _run(self, d, family, value):
        run_id = d.record_run("s", 1, {}, "m", "low", data_manifest="w")
        d.record_trial(run_id, family, "t")
        d.record_figure(run_id, "sh", value)
        return run_id

    def test_returns_one_value_per_run_in_that_family_only(self):
        d = fresh()
        self._run(d, "a", 1.0)
        self._run(d, "a", 2.0)
        self._run(d, "b", 9.0)
        self.assertEqual(sorted(d.family_figures("a", "sh")), [1.0, 2.0])

    def test_none_means_every_family(self):
        d = fresh()
        self._run(d, "a", 1.0)
        self._run(d, "b", 9.0)
        self.assertEqual(sorted(d.family_figures(None, "sh")), [1.0, 9.0])

    def test_a_re_recorded_figure_replaces_rather_than_doubles(self):
        d = fresh()
        run_id = self._run(d, "a", 1.0)
        d.record_figure(run_id, "sh", 5.0)
        self.assertEqual(d.family_figures("a", "sh"), [5.0])

    def test_a_run_without_a_trial_is_not_counted(self):
        d = fresh()
        run_id = d.record_run("s", 1, {}, "m", "low", data_manifest="w")
        d.record_figure(run_id, "sh", 3.0)
        self.assertEqual(d.family_figures(None, "sh"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class HoldoutLooks(unittest.TestCase):
    def setUp(self):
        from tests.engine_fixtures import fresh_db
        self.db = fresh_db()
        self.run = lambda sid: self.db.record_run(sid, 3, {}, "analyst-a", "medium", data_manifest="m")

    def test_a_strategy_reads_a_holdout_once(self):
        self.db.record_holdout_look("s1", "2025-10-01", self.run("s1"))
        with self.assertRaises(results_db.HoldoutAlreadyRead):
            self.db.record_holdout_look("s1", "2025-10-01", self.run("s1"))

    def test_a_variant_under_its_own_id_gets_its_own_counted_look(self):
        self.db.record_holdout_look("s1", "2025-10-01", self.run("s1"))
        self.db.record_holdout_look("s1-variant", "2025-10-01", self.run("s1-variant"))
        self.assertEqual(self.db.holdout_look_count("2025-10-01"), 2)

    def test_a_new_holdout_boundary_is_a_new_holdout(self):
        self.db.record_holdout_look("s1", "2025-10-01", self.run("s1"))
        self.db.record_holdout_look("s1", "2026-10-01", self.run("s1"))
        self.assertEqual(self.db.holdout_look_count("2025-10-01"), 1)
        self.assertEqual(self.db.holdout_look_count("2026-10-01"), 1)

    def test_a_look_against_a_run_that_does_not_exist_is_refused(self):
        with self.assertRaises(results_db.UnknownRun):
            self.db.record_holdout_look("s1", "2025-10-01", "no-such-run")

    def test_a_refused_second_look_does_not_change_the_count(self):
        self.db.record_holdout_look("s1", "2025-10-01", self.run("s1"))
        try:
            self.db.record_holdout_look("s1", "2025-10-01", self.run("s1"))
        except results_db.HoldoutAlreadyRead:
            pass
        self.assertEqual(self.db.holdout_look_count("2025-10-01"), 1)

    def test_the_database_itself_refuses_a_duplicate_look_whatever_the_application_does(self):
        import sqlite3
        run = self.run("s1")
        self.db.record_holdout_look("s1", "2025-10-01", run)
        conn = self.db.backend.connect()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO holdout_looks (strategy_id, holdout_start, run_id, created_at) "
                    "VALUES ('s1', '2025-10-01', ?, 'now')", (run,))
        finally:
            conn.close()
