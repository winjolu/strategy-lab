"""The two return conventions `lab.engine.backtest` can be fed: trailing
close-to-close and forward open-to-open."""
import numpy as np
import pandas as pd
import pytest

from lab.engine import returns


def bars(rows, tickers=("A",), start="2024-01-02"):
    """rows: one per day, each a dict of ticker -> (open, close, closeadj)."""
    idx = pd.bdate_range(start, periods=len(rows))
    out = []
    for d, row in zip(idx, rows):
        for t in tickers:
            o, c, ca = row[t]
            out.append({"ticker": t, "date": d, "open": o, "close": c, "closeadj": ca})
    return pd.DataFrame(out)


def test_close_to_close_drops_the_first_row_with_no_previous_close():
    b = bars([{"A": (10, 10, 10)}, {"A": (10, 11, 11)}, {"A": (10, 12, 12)}])
    out = returns.close_to_close(b)
    assert len(out) == 2


def test_close_to_close_is_the_return_of_the_day_ending_on_that_date():
    b = bars([{"A": (10, 10, 10)}, {"A": (10, 11, 11)}, {"A": (10, 12.1, 12.1)}])
    out = returns.close_to_close(b)
    assert out["A"].iloc[0] == pytest.approx(0.10)
    assert out["A"].iloc[1] == pytest.approx(12.1 / 11 - 1)


def test_close_to_close_moves_on_closeadj_not_close():
    """closeadj carries dividends; close does not. A payout on day 2 must
    show up in the adjusted return even though the raw close is flat."""
    b = bars([{"A": (10, 10, 10)}, {"A": (10, 10, 10.2)}])
    out = returns.close_to_close(b)
    assert out["A"].iloc[0] == pytest.approx(0.02)


def test_close_to_close_refuses_a_duplicate_bar():
    b = bars([{"A": (10, 10, 10)}, {"A": (10, 11, 11)}])
    dup = pd.concat([b, b.iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match="more than one bar"):
        returns.close_to_close(dup)


def test_open_to_open_drops_the_last_row_with_no_forward_open():
    b = bars([{"A": (10, 10, 10)}, {"A": (11, 11, 11)}, {"A": (12, 12, 12)}])
    out = returns.open_to_open(b)
    assert len(out) == 2


def test_open_to_open_is_the_return_from_open_d_to_the_next_open():
    b = bars([{"A": (10, 10, 10)}, {"A": (11, 11, 11)}, {"A": (12.1, 12.1, 12.1)}])
    out = returns.open_to_open(b)
    assert out["A"].iloc[0] == pytest.approx(11 / 10 - 1)
    assert out["A"].iloc[1] == pytest.approx(12.1 / 11 - 1)


def test_open_to_open_carries_the_open_to_the_closeadj_basis():
    """`open` and `close` are both split-adjusted already; only `closeadj`
    also carries a dividend. A 2% dividend factor on day 2 (closeadj/close
    = 1.02) must scale day 2's open by that same 2%, giving a 12.2% return
    from day 1's open rather than the 10% a raw open ratio would show."""
    b = bars([{"A": (10, 10, 10)}, {"A": (11, 11, 11.22)}])
    out = returns.open_to_open(b)
    assert out["A"].iloc[0] == pytest.approx(11.22 / 10 - 1)


def test_open_to_open_refuses_a_missing_column():
    b = bars([{"A": (10, 10, 10)}, {"A": (11, 11, 11)}])
    with pytest.raises(ValueError, match="open"):
        returns.open_to_open(b.drop(columns=["open"]))


def test_open_to_open_produces_nan_across_a_gap_rather_than_bridging_it():
    """B trades every day, so the middle date exists as a row; A is
    missing that one bar. A's forward return either side of the gap must
    be NaN rather than silently spanning two days as if it were one."""
    idx = pd.bdate_range("2024-01-02", periods=3)
    b = pd.DataFrame([
        {"ticker": "A", "date": idx[0], "open": 10, "close": 10, "closeadj": 10},
        {"ticker": "A", "date": idx[2], "open": 12, "close": 12, "closeadj": 12},
        {"ticker": "B", "date": idx[0], "open": 5, "close": 5, "closeadj": 5},
        {"ticker": "B", "date": idx[1], "open": 5, "close": 5, "closeadj": 5},
        {"ticker": "B", "date": idx[2], "open": 5, "close": 5, "closeadj": 5},
    ])
    out = returns.open_to_open(b)
    assert np.isnan(out["A"].iloc[0])
    assert np.isnan(out["A"].iloc[1])
