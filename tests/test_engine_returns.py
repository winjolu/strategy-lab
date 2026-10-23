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


def test_close_to_open_is_the_night_ending_at_that_dates_open():
    b = bars([{"A": (10, 10, 10)}, {"A": (10.5, 11, 11)}, {"A": (11.55, 12, 12)}])
    out = returns.close_to_open(b)
    assert len(out) == 2
    assert out["A"].iloc[0] == pytest.approx(10.5 / 10 - 1)
    assert out["A"].iloc[1] == pytest.approx(11.55 / 11 - 1)


def test_close_to_open_credits_the_dividend_to_the_ex_date_night():
    """Raw: close 10 on day 1, opens 9.8 on the ex-date after a 0.2 dividend,
    closes 9.8. Back-adjusted, day 1's closeadj is 9.8 and the ex-date's is
    9.8, so the night is flat on the total-return basis, not a 2% loss."""
    b = bars([{"A": (10, 10, 9.8)}, {"A": (9.8, 9.8, 9.8)}])
    out = returns.close_to_open(b)
    assert out["A"].iloc[0] == pytest.approx(0.0)
    # a later dividend leaves both days' closeadj below close (factor 0.99);
    # the open has to be carried onto that basis or the night shows +1%
    b = bars([{"A": (10, 10, 9.702)}, {"A": (9.8, 9.8, 9.702)}])
    out = returns.close_to_open(b)
    assert out["A"].iloc[0] == pytest.approx(0.0)


def test_night_and_day_compound_to_the_close_to_close_return():
    rows = [{"A": (10, 10, 9.9)}, {"A": (10.3, 10.1, 10.0)}, {"A": (9.7, 10.4, 10.4)}]
    b = bars(rows)
    night, day, whole = returns.close_to_open(b), returns.open_to_close(b), returns.close_to_close(b)
    joined = (1 + night["A"]) * (1 + day["A"].loc[night.index]) - 1
    assert np.allclose(joined.values, whole["A"].values)


def test_close_to_open_is_nan_across_a_missing_bar():
    rows = [{"A": (10, 10, 10), "B": (5, 5, 5)}, {"B": (5, 5, 5)}, {"A": (11, 11, 11), "B": (5, 5, 5)}]
    idx = pd.bdate_range("2024-01-02", periods=3)
    out = []
    for d, row in zip(idx, rows):
        for t, (o, c, ca) in row.items():
            out.append({"ticker": t, "date": d, "open": o, "close": c, "closeadj": ca})
    got = returns.close_to_open(pd.DataFrame(out))
    assert got["A"].isna().all()


def test_close_to_open_refuses_a_missing_column():
    b = bars([{"A": (10, 10, 10)}, {"A": (11, 11, 11)}])
    with pytest.raises(ValueError, match="open"):
        returns.close_to_open(b.drop(columns=["open"]))


def test_a_signal_built_from_tonights_return_earns_nothing_once_lagged():
    """The decision is dated at a close and the night it is paid starts at
    that close. A rule that peeks at the night it is paid must not profit
    once the engine lags it one row."""
    from lab.engine import backtest, costs
    rng = np.random.default_rng(0)
    n = 2000
    idx = pd.bdate_range("2010-01-04", periods=n)
    night = pd.DataFrame({"A": rng.normal(0, 0.01, n)}, idx)
    peek = (night > 0).astype(float)            # knows the row it would be paid
    bt = backtest.run(peek, night, costs.CostModel(0.0))
    assert abs(bt.net.mean()) < 3 * night["A"].std() / np.sqrt(n)
    cheat = (peek * night).sum(axis=1)
    assert cheat.mean() > 0.003                 # the same rule, unlagged, would print money
