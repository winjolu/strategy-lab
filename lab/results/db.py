"""The results database: every run, its code version, its configuration.

The methodology requires that any figure trace back to the data vintage
that produced it, and that deflation have a trial count that does not
live in anyone's memory. Both need one place that survives a
restart, so this exists.

Three tables. `runs` is one row per backtest run: which strategy, which
stage, which commit of this lab and of `market_core` produced it, what
the archive looked like when it ran, and the full configuration as JSON
rather than as separate columns, because the set of parameters differs
per strategy and a schema migration for every new knob is worse than a
blob that is never queried by field. `trials` is one row per variant
tried, lab-wide, because `market_core.performance.deflated_sharpe`
deflates against how many things were tried, not how many succeeded, and
a count that only lives in whoever remembers running the sweep is not a
count. `figures` is one row per reported number, tied to the run that
produced it, so "the Sharpe was 1.4" is always also "which run said so."

Backend split mirrors `lab.data.archive`: SQLite today, a Postgres stub
for the day the results database moves off a laptop too. No `sqlite3`
call appears above this layer, and no strategy code opens this database
directly — it goes through `ResultsDB`.
"""
import json
import os
import re
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone

from lab import config

_WRITE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|vacuum|pragma)\b",
    re.IGNORECASE,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    strategy_id         TEXT NOT NULL,
    stage               INTEGER NOT NULL,
    created_at          TEXT NOT NULL,
    lab_version         TEXT NOT NULL,
    market_core_version TEXT NOT NULL,
    data_manifest       TEXT NOT NULL,
    config_json         TEXT NOT NULL,
    produced_by         TEXT NOT NULL,
    effort              TEXT NOT NULL,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS trials (
    trial_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES runs(run_id),
    family      TEXT NOT NULL,
    reason      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS figures (
    figure_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES runs(run_id),
    name        TEXT NOT NULL,
    value       REAL,
    unit        TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS holdout_looks (
    look_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id   TEXT NOT NULL,
    holdout_start TEXT NOT NULL,
    run_id        TEXT NOT NULL REFERENCES runs(run_id),
    created_at    TEXT NOT NULL,
    UNIQUE (strategy_id, holdout_start)
);

CREATE INDEX IF NOT EXISTS idx_trials_family ON trials(family);
CREATE INDEX IF NOT EXISTS idx_figures_run ON figures(run_id);
"""


class ReadOnlyViolation(RuntimeError):
    """A statement that is not a read reached a read-only handle."""


class HoldoutAlreadyRead(RuntimeError):
    """This strategy has already read this holdout. Each reads it once."""


class UnknownRun(KeyError):
    """A run_id was asked for that this database has no row for."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_sha(repo_dir, short=True):
    """The commit a directory's checkout is on, or "unknown" outside git.

    A results row with no code version is a row nothing can be checked
    against later, so this never raises — an unclean read here would
    block every run from being recorded over a problem unrelated to the
    run itself. It returns a string that says why it could not answer
    rather than silently standing in a real-looking hash's place.
    """
    args = ["git", "-C", repo_dir, "rev-parse"]
    args.append("--short" if short else "HEAD")
    if short:
        args.append("HEAD")
    try:
        out = subprocess.run(
            args, capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if out.returncode != 0:
        return "unknown"
    sha = out.stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", repo_dir, "status", "--porcelain"],
        capture_output=True, text=True, timeout=5, check=False,
    )
    if dirty.returncode == 0 and dirty.stdout.strip():
        sha += "-dirty"
    return sha


class Backend:
    """What differs between SQLite and Postgres. Everything else in this
    module is backend-agnostic and stays that way."""

    placeholder = "?"

    def connect(self):
        raise NotImplementedError

    def connect_ro(self):
        raise NotImplementedError


class SQLiteBackend(Backend):
    placeholder = "?"

    def __init__(self, path):
        self.path = path

    def connect(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def connect_ro(self):
        if not os.path.exists(self.path):
            # Nothing has been written yet; a read-only open of a
            # missing file fails opaquely, so create the schema first
            # through a normal writable connection and reopen.
            self.connect().close()
        conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn


class PostgresBackend(Backend):
    """Not implemented. Raising here rather than returning an empty
    connection is the point: a caller that migrates the archive but
    forgets the results database should fail loudly on the first call,
    not read back zero rows and conclude the lab has no history."""

    placeholder = "%s"

    def __init__(self, url):
        self.url = url

    def connect(self):
        raise NotImplementedError(
            "Postgres backend for the results database is not built yet."
        )

    def connect_ro(self):
        raise NotImplementedError(
            "Postgres backend for the results database is not built yet."
        )


def backend_for(path_or_url):
    if path_or_url.startswith("postgresql://") or path_or_url.startswith("postgres://"):
        return PostgresBackend(path_or_url)
    return SQLiteBackend(path_or_url)


class ResultsDB:
    """Every run this lab has produced, and everything reported from it.

    `record_run` is the only place a `run_id` is minted; every other
    write requires one that already exists, so a figure or a trial can
    never be recorded against a run that was never registered. Reads go
    through a read-only connection where that is meaningful, matching
    the convention the archive layer uses, even though this database has
    more than one writer in principle — the session recording a run and
    nothing else.
    """

    def __init__(self, backend):
        self.backend = backend
        self._init_schema()

    def _init_schema(self):
        conn = self.backend.connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def record_run(
        self, strategy_id, stage, config, produced_by, effort,
        data_manifest=None, notes=None, lab_dir=None, market_core_dir=None,
    ):
        """Register one run and return its run_id.

        `data_manifest` should say what the archive looked like — the
        watermark reported by `lab.checks.archive_properties`, or an
        explicit string when a run predates that check. It is required
        rather than defaulted to "unknown" by this function, because a
        caller that has not looked up the watermark should be stopped
        here rather than get a row that looks complete and is not.
        """
        if data_manifest is None:
            raise ValueError(
                "data_manifest is required: state what the archive looked "
                "like, e.g. its watermark, rather than leaving this blank."
            )
        run_id = uuid.uuid4().hex
        lab_dir = lab_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        market_core_dir = market_core_dir or os.path.dirname(
            os.path.dirname(__import__("market_core").__file__)
        )
        row = (
            run_id, strategy_id, int(stage), _now(),
            git_sha(lab_dir), git_sha(market_core_dir), data_manifest,
            json.dumps(config, sort_keys=True), produced_by, effort, notes,
        )
        conn = self.backend.connect()
        try:
            conn.execute(
                f"INSERT INTO runs (run_id, strategy_id, stage, created_at, "
                f"lab_version, market_core_version, data_manifest, "
                f"config_json, produced_by, effort, notes) "
                f"VALUES ({', '.join([self.backend.placeholder] * len(row))})",
                row,
            )
            conn.commit()
        finally:
            conn.close()
        return run_id

    def _run_exists(self, conn, run_id):
        cur = conn.execute(
            f"SELECT 1 FROM runs WHERE run_id = {self.backend.placeholder}",
            (run_id,),
        )
        return cur.fetchone() is not None

    def record_trial(self, run_id, family, reason):
        """Count one variant against the lab-wide and per-family trial
        totals that `market_core.performance.deflated_sharpe` needs.

        Every variant is a trial, whatever it found — recording only the
        ones that looked promising is exactly the selection that
        deflation exists to correct for.
        """
        conn = self.backend.connect()
        try:
            if not self._run_exists(conn, run_id):
                raise UnknownRun(
                    f"no run {run_id!r}; call record_run before record_trial"
                )
            conn.execute(
                f"INSERT INTO trials (run_id, family, reason, created_at) "
                f"VALUES ({self.backend.placeholder}, {self.backend.placeholder}, "
                f"{self.backend.placeholder}, {self.backend.placeholder})",
                (run_id, family, reason, _now()),
            )
            conn.commit()
        finally:
            conn.close()

    def record_figure(self, run_id, name, value, unit=None):
        """Record one reported number against the run that produced it,
        so the number can always be traced back to its configuration and
        its data vintage rather than taken on trust."""
        conn = self.backend.connect()
        try:
            if not self._run_exists(conn, run_id):
                raise UnknownRun(
                    f"no run {run_id!r}; call record_run before record_figure"
                )
            conn.execute(
                f"INSERT INTO figures (run_id, name, value, unit, created_at) "
                f"VALUES ({self.backend.placeholder}, {self.backend.placeholder}, "
                f"{self.backend.placeholder}, {self.backend.placeholder}, "
                f"{self.backend.placeholder})",
                (run_id, name, value, unit, _now()),
            )
            conn.commit()
        finally:
            conn.close()

    def run(self, run_id):
        """The full row for one run, with its configuration parsed back
        out of JSON. Raises UnknownRun rather than returning None, so a
        typo'd run_id fails at the point of the mistake."""
        conn = self.backend.connect_ro()
        try:
            cur = conn.execute(
                f"SELECT * FROM runs WHERE run_id = {self.backend.placeholder}",
                (run_id,),
            )
            row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            raise UnknownRun(run_id)
        out = dict(row)
        out["config"] = json.loads(out.pop("config_json"))
        return out

    def figures_for_run(self, run_id):
        """Every figure recorded against one run — the re-find path a
        published number is checked against."""
        conn = self.backend.connect_ro()
        try:
            cur = conn.execute(
                f"SELECT name, value, unit, created_at FROM figures "
                f"WHERE run_id = {self.backend.placeholder} ORDER BY figure_id",
                (run_id,),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def figure(self, run_id, name):
        """One named figure from one run, or None if it was never
        recorded. Distinct from `run` raising, because asking for a
        figure that does not exist is routine and asking for a run that
        does not exist is a mistake."""
        for f in self.figures_for_run(run_id):
            if f["name"] == name:
                return f
        return None

    def trial_count(self, family=None):
        """Lab-wide trial count, or one family's, for deflation.

        `market_core.performance.deflated_sharpe` deflates per-family and
        lab-wide separately, so both counts are available and neither is
        derived from the other in application code — the family counts
        do not have to sum to the lab-wide count if a trial predates
        this database or was recorded without a family.
        """
        conn = self.backend.connect_ro()
        try:
            if family is None:
                cur = conn.execute("SELECT COUNT(*) AS n FROM trials")
            else:
                cur = conn.execute(
                    f"SELECT COUNT(*) AS n FROM trials WHERE family = "
                    f"{self.backend.placeholder}",
                    (family,),
                )
            return cur.fetchone()["n"]
        finally:
            conn.close()

    def record_holdout_look(self, strategy_id, holdout_start, run_id):
        """Record that a strategy read a holdout, or raise if it already did.

        The unique key is the strategy and the holdout together, so a variant
        under its own id gets its own look, counted separately, while a rerun
        of the same strategy cannot take a second one. Written before the
        score is computed, so a crash does not hand back the look.
        """
        conn = self.backend.connect()
        try:
            if not self._run_exists(conn, run_id):
                raise UnknownRun(f"no run {run_id!r}; call record_run first")
            p = self.backend.placeholder
            if conn.execute(
                f"SELECT 1 FROM holdout_looks WHERE strategy_id = {p} AND holdout_start = {p}",
                (strategy_id, str(holdout_start)),
            ).fetchone():
                raise HoldoutAlreadyRead(
                    f"{strategy_id!r} has already read the holdout from {holdout_start}")
            conn.execute(
                f"INSERT INTO holdout_looks (strategy_id, holdout_start, run_id, created_at) "
                f"VALUES ({p}, {p}, {p}, {p})",
                (strategy_id, str(holdout_start), run_id, _now()),
            )
            conn.commit()
        finally:
            conn.close()

    def has_read_holdout(self, strategy_id, holdout_start):
        conn = self.backend.connect_ro()
        try:
            p = self.backend.placeholder
            return conn.execute(
                f"SELECT 1 FROM holdout_looks WHERE strategy_id = {p} AND holdout_start = {p}",
                (strategy_id, str(holdout_start))).fetchone() is not None
        finally:
            conn.close()

    def holdout_look_count(self, holdout_start):
        """How many candidates have read this holdout, variants included."""
        conn = self.backend.connect_ro()
        try:
            cur = conn.execute(
                f"SELECT COUNT(*) AS n FROM holdout_looks WHERE holdout_start = "
                f"{self.backend.placeholder}", (str(holdout_start),))
            return cur.fetchone()["n"]
        finally:
            conn.close()

    def family_figures(self, family, name):
        """The latest value of one named figure from every run that has a
        trial in `family` (any family when None), one value per run.

        Deflation needs the dispersion of Sharpe ratios across everything
        tried, and that dispersion has to come from what was recorded, not
        from whoever remembers. Latest per run, so a figure re-recorded
        after a correction replaces the earlier one instead of being
        counted twice.
        """
        conn = self.backend.connect_ro()
        ph = self.backend.placeholder
        scope, params = ("", (name,)) if family is None else \
            (f" WHERE family = {ph}", (name, family))
        try:
            cur = conn.execute(
                f"SELECT f.value AS value FROM figures f "
                f"WHERE f.name = {ph} AND f.value IS NOT NULL "
                f"AND f.run_id IN (SELECT run_id FROM trials{scope}) "
                f"AND f.figure_id = (SELECT MAX(g.figure_id) FROM figures g "
                f"WHERE g.run_id = f.run_id AND g.name = f.name)",
                params,
            )
            return [float(r["value"]) for r in cur.fetchall()]
        finally:
            conn.close()

    def runs_for_strategy(self, strategy_id):
        conn = self.backend.connect_ro()
        try:
            cur = conn.execute(
                f"SELECT run_id, stage, created_at FROM runs "
                f"WHERE strategy_id = {self.backend.placeholder} "
                f"ORDER BY created_at",
                (strategy_id,),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()


def default():
    """The lab's one results database, at the path `lab.config` names."""
    return ResultsDB(backend_for(config.results_db()))
