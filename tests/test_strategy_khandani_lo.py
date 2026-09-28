"""`lab.strategies.xs_mr_khandani_lo`: the signal and its two sizing rules
against a synthetic panel, plus one real-archive smoke test of `build`."""
import numpy as np
import pandas as pd
import pytest

from lab.engine import returns as returns_mod
from lab.strategies import xs_mr_khandani_lo as strat


def frame(rows, cols):
    return pd.DataFrame(rows, pd.bdate_range("2024-01-02", periods=len(rows)), cols)


def test_signal_is_the_negative_deviation_from_the_equal_weighted_mean():
    ret = frame([[0.03, 0.01, -0.02]], list("ABC"))
    members = frame([[True, True, True]], list("ABC"))
    sig = strat.signal(ret, members)
    mean = (0.03 + 0.01 - 0.02) / 3
    assert sig["A"].iloc[0] == pytest.approx(-(0.03 - mean))
    assert sig["C"].iloc[0] == pytest.approx(-(-0.02 - mean))


def test_a_relative_loser_gets_a_positive_signal():
    """The name that fell furthest behind its peers is the one this
    strategy buys, so its signal must be positive."""
    ret = frame([[0.05, 0.05, -0.10]], list("ABC"))
    sig = strat.signal(ret, frame([[True, True, True]], list("ABC")))
    assert sig["C"].iloc[0] > 0
    assert sig["A"].iloc[0] < 0


def test_a_non_member_gets_no_signal_and_does_not_enter_the_mean():
    ret = frame([[0.10, 0.00, 100.0]], list("ABC"))  # C is a wild non-member value
    members = frame([[True, True, False]], list("ABC"))
    sig = strat.signal(ret, members)
    assert np.isnan(sig["C"].iloc[0])
    # the mean must be over A and B only (0.05), not pulled toward C's 100.0
    assert sig["A"].iloc[0] == pytest.approx(-(0.10 - 0.05))


def test_a_member_with_no_return_gets_no_signal():
    ret = frame([[0.10, np.nan, -0.05]], list("ABC"))
    members = frame([[True, True, True]], list("ABC"))
    sig = strat.signal(ret, members)
    assert np.isnan(sig["B"].iloc[0])
    assert sig["A"].iloc[0] == pytest.approx(-(0.10 - (0.10 - 0.05) / 2))


def test_linear_weights_are_dollar_neutral_and_proportional_to_signal():
    sig = frame([[0.03, 0.01, -0.02, np.nan]], list("ABCD"))
    w = strat.weights(sig, "linear")
    assert w.iloc[0].sum() == pytest.approx(0.0, abs=1e-9)
    assert w["D"].iloc[0] == 0.0
    assert w["A"].iloc[0] / w["B"].iloc[0] == pytest.approx(3.0)


def test_decile_equal_weights_hold_only_the_extremes():
    sig = frame([list(range(-5, 5))], [f"S{i}" for i in range(10)])
    w = strat.weights(sig, "decile_equal")
    held = w.iloc[0][w.iloc[0] != 0]
    assert len(held) == 2
    assert set(held.round(2)) == {0.5, -0.5}


def test_an_unknown_rule_is_refused():
    with pytest.raises(ValueError, match="unknown sizing rule"):
        strat.weights(frame([[1.0]], ["A"]), "market_cap")


class FakeArchive:
    """A tiny synthetic universe: 4 names, 20 trading days, one split-off
    membership change and one gap, so `build` exercises every real path
    without touching the archive."""

    def __init__(self):
        self.idx = pd.bdate_range("2024-01-02", periods=20)
        rng = np.random.default_rng(7)
        self._px = pd.DataFrame(
            100 * np.exp(np.cumsum(rng.normal(0, 0.01, (20, 6)), axis=0)),
            self.idx, list("ABCD") + ["BIL", "SPY"])
        self._events = pd.DataFrame([
            {"date": self.idx[0], "action": "historical", "ticker": "A"},
            {"date": self.idx[0], "action": "historical", "ticker": "B"},
            {"date": self.idx[0], "action": "historical", "ticker": "C"},
            {"date": self.idx[10], "action": "added", "ticker": "D"},
        ])

    def trading_days(self, start=None, end=None):
        return pd.Series(self.idx.astype(str))

    def sp500_events(self, start=None, end=None):
        return self._events

    def bars(self, tickers, start=None, end=None, columns=None):
        rows = []
        for t in tickers:
            for i, d in enumerate(self.idx):
                if t == "B" and i == 5:
                    continue  # a gap
                p = float(self._px[t].iloc[i])
                rows.append({"ticker": t, "date": d, "open": p, "close": p, "closeadj": p})
        return pd.DataFrame(rows)

    def fund_bars(self, tickers, start=None, end=None, columns=None):
        return self.bars(tickers, start, end, columns)


def test_build_wires_a_full_synthetic_panel_end_to_end():
    inputs = strat.build(FakeArchive(), "2024-01-02", "2024-01-29", benchmark_ticker="BIL",
                         min_members=1, max_members=10)
    assert set(inputs.weights_by_sizing) == {"linear", "decile_equal"}
    assert inputs.benchmark_cc.name == "BIL" and inputs.benchmark_oo.name == "BIL"
    assert inputs.spy_cc.name == "SPY" and inputs.spy_oo.name == "SPY"
    assert "D" in inputs.weights_by_sizing["linear"].columns
    # D was not a member before day 10; its weight must be flat before then
    early = inputs.weights_by_sizing["linear"]["D"].iloc[:5]
    assert (early == 0.0).all()
    assert len(inputs.returns_cc) == len(inputs.returns_oo) == 19  # 20 raw days, one dropped on each side


@pytest.mark.skipif(not __import__("os").path.exists(
    __import__("os").path.expanduser("~/market-data/sharadar.db")), reason="no local archive")
def test_build_runs_against_the_real_archive_on_a_short_window():
    """Not a Stage 1 run: a smoke test, on a couple of months, against a
    throwaway results database, proving the real pieces fit together.
    `trial_count` here must never reach the lab's production database."""
    from lab.data.archive import Archive
    from lab.engine import costs, pipeline
    from tests.engine_fixtures import fresh_db

    archive = Archive()
    inputs = strat.build(archive, "2023-01-03", "2023-03-01")
    assert 400 <= inputs.weights_by_sizing["linear"].shape[1] <= 520
    assert len(inputs.returns_oo) == len(inputs.returns_cc)

    for name, ret, bench in (("open-to-open", inputs.returns_oo, inputs.benchmark_oo),
                             ("close-to-close", inputs.returns_cc, inputs.benchmark_cc)):
        ev = pipeline.evaluate(
            "xs-mr-khandani-lo", inputs.weights_by_sizing, ret, bench, fresh_db(),
            "smoke-test", "low", "smoke-test-manifest",
            "whole-share shorting at this account size", costs.CostModel(0.25, borrow_apr=8.0),
            on_missing="zero", registry_directory="registry",
        )
        assert len(ev.results) == 2, name
