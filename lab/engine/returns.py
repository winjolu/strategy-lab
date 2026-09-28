"""Two ways to turn adjusted bars into a return series, chosen by which
price a strategy actually trades at.

`close_to_close` is the ordinary trailing convention every other module in
this lab uses: the value at date d is the return of the day ending on d,
close over previous close. A strategy that decides and trades on the same
close reads this correctly with `lag=1` in `lab.engine.backtest`: a
decision dated t lands on row t+1, which is close(t+1) over close(t) —
held from close(t) to close(t+1).

`open_to_open` is a forward convention, deliberately not the lab's usual
one, for a strategy that decides at one close but trades at the next
session's open instead. The value stored at date d is the return from the
open of d to the open of the next trading day, so a decision dated t
applied with `lag=1` lands on this frame's row t+1 and earns exactly the
open(t+1)-to-open(t+2) period. The last row is always undefined, because it
needs an open beyond the fetched bars to compute, and is dropped rather
than filled. That is also what keeps a pre-holdout panel from ever reading
a holdout price: as long as the bars behind it are never fetched past the
holdout boundary, the row that would need a holdout open simply cannot be
built, whatever date is passed as the boundary.
"""
import numpy as np


def _pivot(bars, value):
    if bars.duplicated(["ticker", "date"]).any():
        raise ValueError("more than one bar per ticker per day")
    return bars.pivot(index="date", columns="ticker", values=value).sort_index()


def close_to_close(bars):
    """`closeadj` percent change, dates by tickers."""
    wide = _pivot(bars, "closeadj")
    return wide.pct_change(fill_method=None).iloc[1:]


def open_to_open(bars):
    """Adjusted-open forward return, dates by tickers.

    `open` and `close` are both split-adjusted already, the way this
    archive stores them; only `closeadj` also adds dividends. `open *
    closeadj / close`, same day, carries that dividend factor onto the
    open, so a name's open and close on one day sit on the same total-
    return basis and their ratio is a real move rather than an artefact
    of only the close carrying dividends.
    """
    missing = [c for c in ("open", "close", "closeadj") if c not in bars.columns]
    if missing:
        raise ValueError(f"open_to_open needs {missing} in the bars frame")
    adjusted = bars.assign(adj_open=bars["open"] * bars["closeadj"] / bars["close"])
    wide = _pivot(adjusted, "adj_open")
    with np.errstate(divide="ignore", invalid="ignore"):
        forward = wide.shift(-1) / wide - 1.0
    return forward.iloc[:-1]
