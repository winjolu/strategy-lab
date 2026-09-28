"""`lab.engine.report._break_even`: the slippage per side, at a fixed
borrow rate, where active t crosses a target — by interpolation between
swept points, never extrapolation past them."""
import pytest

from lab.engine import report


def row(slip, t, borrow=8.0):
    return {"slippage_pct": slip, "borrow_apr": borrow, "active_t": t}


def test_interpolates_linearly_between_the_two_bracketing_points():
    sweep = [row(0.10, 3.0), row(0.25, 1.0), row(0.50, -1.0)]
    out = report._break_even(sweep, 8.0, targets=(2.0,))
    assert out[2.0] == pytest.approx(0.10 + (2.0 - 3.0) / (1.0 - 3.0) * (0.25 - 0.10))


def test_an_exact_match_needs_no_interpolation():
    sweep = [row(0.10, 3.0), row(0.25, 2.0), row(0.50, -1.0)]
    out = report._break_even(sweep, 8.0, targets=(2.0,))
    assert out[2.0] == 0.25


def test_only_rows_at_the_requested_borrow_rate_are_considered():
    sweep = [row(0.10, 3.0, borrow=1.0), row(0.10, -3.0, borrow=8.0),
             row(0.50, -1.0, borrow=1.0), row(0.50, 1.0, borrow=8.0)]
    out = report._break_even(sweep, 1.0, targets=(0.0,))
    # at borrow=1.0 the two points are (0.10, 3.0) and (0.50, -1.0)
    assert out[0.0] == pytest.approx(0.10 + (0.0 - 3.0) / (-1.0 - 3.0) * (0.50 - 0.10))


def test_still_above_target_at_the_highest_swept_cost_is_reported_as_such():
    sweep = [row(0.10, 5.0), row(0.25, 4.0), row(0.50, 3.0)]
    out = report._break_even(sweep, 8.0, targets=(2.0,))
    assert "above every swept level" in out[2.0]


def test_already_below_target_at_the_lowest_swept_cost_is_reported_as_such():
    sweep = [row(0.10, -1.0), row(0.25, -2.0), row(0.50, -3.0)]
    out = report._break_even(sweep, 8.0, targets=(0.0,))
    assert "below the lowest swept level" in out[0.0]


def test_borrow_none_matches_a_long_only_sweep():
    sweep = [row(0.10, 3.0, borrow=None), row(0.50, -1.0, borrow=None)]
    out = report._break_even(sweep, None, targets=(0.0,))
    assert out[0.0] is not None and not isinstance(out[0.0], str)


def test_an_exact_match_at_the_last_swept_point_is_still_found():
    """The last row is never checked as the left side of a bracketing
    pair, so an exact hit there needs its own path, not just the
    bracket-crossing search."""
    sweep = [row(0.10, 3.0), row(0.25, 1.0), row(0.50, 0.0)]
    out = report._break_even(sweep, 8.0, targets=(0.0,))
    assert out[0.0] == 0.50


def test_multiple_targets_are_each_resolved_independently():
    sweep = [row(0.01, 4.0), row(0.05, 2.0), row(0.10, 0.0), row(0.25, -2.0)]
    out = report._break_even(sweep, 8.0, targets=(0.0, 2.0))
    assert out[0.0] == pytest.approx(0.10)
    assert out[2.0] == pytest.approx(0.05)


def test_break_even_appears_in_the_rendered_report():
    from datetime import date

    from lab.engine import costs, pipeline
    from tests.engine_fixtures import TODAY, fresh_db, panel, write_registration
    import numpy as np
    import pandas as pd
    import tempfile

    d = tempfile.mkdtemp()
    write_registration(d)
    ret, bench = panel()
    rng = np.random.default_rng(3)
    s = pd.DataFrame(np.sign(rng.normal(size=ret.shape)), ret.index, ret.columns)
    s = s.where(s != 0, 1.0)
    w = {"equal_weight": s.div(s.abs().sum(axis=1), axis=0),
        "inverse_vol": s.div(s.abs().sum(axis=1), axis=0)}
    ev = pipeline.evaluate("toy", w, ret, bench, fresh_db(), "analyst", "medium",
                           "synthetic", "settled cash", costs.CostModel(0.25),
                           registry_directory=d, today=TODAY)
    from lab.engine.report import render
    text = render(ev)
    assert "Break-even slippage" in text
