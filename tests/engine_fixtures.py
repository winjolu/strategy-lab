"""Shared synthetic fixtures for the engine tests. No archive access."""
import os
import tempfile
from datetime import date

import numpy as np
import pandas as pd

from lab.results import db as results_db

TODAY = date(2026, 6, 1)

REGISTRY_TEXT = '''+++
id = "{id}"
family = "{family}"
provenance = "{provenance}"
source = "synthetic"
account = "individual-margin"
enabling_step = "none needed"
stage = 1

[registration]
registered_on = "2026-01-01"
hypothesis = "h"
economic_reason = "e"
prediction = "no edge"
universe = "u"
horizon = "daily"
benchmark = "BENCH"
parameters = {params}
sizing_rules = {sizing}
holdout_start = "{holdout}"
kill_criteria = "k"
current_regime_rule = "last year"
current_regime_start = "2024-01-01"
data_derived_burden = "{burden}"
+++
body
'''


def write_registration(directory, id="toy", family="fam", provenance="literature",
                       params='{lookback = 5}', sizing='["equal_weight", "inverse_vol"]',
                       holdout="2025-06-01", burden=""):
    path = os.path.join(directory, f"{id}.md")
    with open(path, "w") as handle:
        handle.write(REGISTRY_TEXT.format(id=id, family=family, provenance=provenance,
                                          params=params, sizing=sizing, holdout=holdout,
                                          burden=burden))
    return path


def fresh_db():
    path = tempfile.mktemp(suffix=".db")
    return results_db.ResultsDB(results_db.SQLiteBackend(path))


def panel(days=700, names=8, seed=1, start="2022-01-03"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=days)
    cols = [f"S{i}" for i in range(names)]
    ret = pd.DataFrame(rng.normal(0.0003, 0.015, (days, names)), idx, cols)
    bench = pd.Series(ret.mean(axis=1), name="BENCH")
    return ret, bench
