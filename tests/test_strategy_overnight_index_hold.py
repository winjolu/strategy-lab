import math

import numpy as np
import pandas as pd
import pytest

from lab.engine import returns as returns_mod
from lab.strategies import overnight_index_hold as s


def night(n=200, sd=0.01, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-02", periods=n)
    return pd.DataFrame({"SPY": rng.normal(0, sd, n)}, idx)


def test_full_holds_one_every_night():
    w = s.weights(night(), "SPY", "full")
    assert list(w.columns) == ["SPY"] and (w["SPY"] == 1.0).all()


def test_vol_target_scales_to_the_target_and_respects_the_cap():
    calm = s.weights(night(sd=0.002), "SPY", "vol_target")
    wild = s.weights(night(sd=0.02), "SPY", "vol_target")
    assert calm["SPY"].iloc[100:].max() == pytest.approx(1.0)       # capped
    idx = pd.bdate_range("2020-01-02", periods=100)
    swing = pd.DataFrame({"SPY": [0.02 if i % 2 else -0.02 for i in range(100)]}, idx)
    exact = s.weights(swing, "SPY", "vol_target")
    sd = pd.Series([0.02 if i % 2 else -0.02 for i in range(63)]).std()
    assert exact["SPY"].iloc[80] == pytest.approx(0.10 / (sd * math.sqrt(252)), rel=1e-9)


def test_vol_target_holds_nothing_until_a_full_window():
    w = s.weights(night(), "SPY", "vol_target")
    assert (w["SPY"].iloc[:62] == 0.0).all() and w["SPY"].iloc[62] > 0


def test_vol_target_reads_no_night_after_the_one_it_is_dated():
    a = night()
    b = a.copy()
    b.iloc[120:] *= 10
    wa, wb = s.weights(a, "SPY", "vol_target"), s.weights(b, "SPY", "vol_target")
    pd.testing.assert_series_equal(wa["SPY"].iloc[:120], wb["SPY"].iloc[:120])


def test_an_unknown_rule_is_refused():
    with pytest.raises(ValueError):
        s.weights(night(), "SPY", "momentum")


def bars():
    idx = pd.bdate_range("2024-01-02", periods=4)
    rows = []
    for t, base, g in (("SPY", 100.0, 0.01), ("QQQ", 50.0, 0.03), ("IWM", 20.0, -0.02), ("BIL", 91.0, 0.0)):
        for i, d in enumerate(idx):
            o, c = base * (1 + g * i), base * (1 + g * i + 0.005)
            rows.append({"ticker": t, "date": d, "open": o, "close": c, "closeadj": c})
    return pd.DataFrame(rows)


def test_build_puts_night_benchmark_and_bil_on_the_same_dates():
    inp = s.build(bars())
    assert list(inp.night.columns) == list(s.GRID)
    for x in (inp.benchmark, inp.bil, inp.day):
        assert x.index.equals(inp.night.index)
    assert inp.benchmark.name == "SPY" and inp.bil.name == "BIL"


def test_night_and_day_compound_to_the_benchmark():
    inp = s.build(bars())
    joined = (1 + inp.night["SPY"]) * (1 + inp.day["SPY"]) - 1
    assert np.allclose(joined.values, inp.benchmark.values)


def test_the_registered_file_runs_through_the_pipeline_with_round_trips():
    import os
    import shutil
    import tempfile
    from datetime import date
    from lab.engine import costs, pipeline, registry
    from tests.engine_fixtures import fresh_db
    d = tempfile.mkdtemp()
    shutil.copy(os.path.join(registry.registry_dir(), "overnight-index-hold.md"), d)
    rng = np.random.default_rng(4)
    idx = pd.bdate_range("2019-01-02", "2025-09-30")
    n = len(idx)
    nights = pd.DataFrame({"SPY": rng.normal(0.0004, 0.006, n)}, idx)
    bench = (nights["SPY"] + rng.normal(0.0, 0.008, n)).rename("SPY")
    w = {rule: s.weights(nights, "SPY", rule) for rule in ("full", "vol_target")}
    ev = pipeline.evaluate(
        "overnight-index-hold", w, nights, bench, fresh_db(), produced_by="analyst-a",
        effort="medium", data_manifest="synthetic", binding_constraint="auctions",
        base_cost=costs.CostModel(0.01), execution="close_to_open", round_trip=True,
        registry_directory=d, today=date(2026, 10, 23))
    full = next(r for r in ev.results if r.name == "full")
    assert full.decides and ev.decision_cell[0] == pytest.approx(0.01)
    assert full.turnover_annual == pytest.approx(504, rel=0.01)
    slips = [row["slippage_pct"] for row in full.sweep]
    assert 0.0 in slips
    by = {row["slippage_pct"]: row["active_pct_per_year"] for row in full.sweep}
    # every basis point per side costs about 5% a year at 504 sides
    assert by[0.0] - by[0.01] == pytest.approx(5.04, abs=0.3)
