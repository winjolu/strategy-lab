"""The score a strategy is eligible for paper trading on, under rule set v2.

The score is the annualised Sharpe ratio of the active return, net of the
registered cost cell, over the training window and the holdout pooled into
one record. Pooling is deliberate: requiring two short windows to pass
separately rejected a strategy with a true Sharpe of 1.5 three times in
four, and under five years of data cannot tell a Sharpe of 1 from 0 under
any rule. Paper trading costs compute, not money, so the permissive error
is the cheaper one.

Tiers, written here once and never per strategy: at or above `CLEAR` a
strategy is clear, from `FLOOR` up to `CLEAR` it is borderline, below
`FLOOR` it is not eligible. 1.5 is a target and not a cliff, which is why
the middle tier exists and why the cap on paper strategies, not the line,
does the selecting. The label here describes where a number falls. What
happens to a strategy is decided elsewhere.

The training window is the three years ending on the last trading day
before the holdout. The out-of-sample part of the score is withheld until
the holdout holds a year of data, and each strategy reads it once.
"""
import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252
TRAINING_YEARS = 3
CLEAR = 1.5
FLOOR = 1.0
MIN_HOLDOUT_DAYS = 252
MIN_OBSERVATIONS = 30


class HoldoutTooShort(RuntimeError):
    """The holdout holds less than the year of data its score requires."""


def tier(sharpe):
    """Where a Sharpe falls: clear, borderline, below, or undefined."""
    if sharpe is None or not math.isfinite(sharpe):
        return "undefined"
    if sharpe >= CLEAR:
        return "clear"
    if sharpe >= FLOOR:
        return "borderline"
    return "below"


def training_window(index, holdout_start):
    """First and last date of the three years before the holdout, within
    `index`. The last date is strictly before the holdout."""
    holdout = pd.Timestamp(holdout_start)
    before = index[index < holdout]
    if not len(before):
        raise ValueError("no data before the holdout start")
    end = before.max()
    start = end - pd.DateOffset(years=TRAINING_YEARS) + pd.Timedelta(days=1)
    return max(start, before.min()), end


def _active(net, benchmark):
    joined = pd.concat({"net": net, "bench": benchmark}, axis=1, join="inner").dropna()
    return joined["net"] - joined["bench"]


def _sharpe(active):
    if len(active) < MIN_OBSERVATIONS:
        raise ValueError(f"only {len(active)} observations; need {MIN_OBSERVATIONS}")
    sd = float(active.std(ddof=1))
    if not math.isfinite(sd) or sd < 1e-12:   # a constant record, up to float noise
        return float("nan")
    return float(active.mean() / sd * math.sqrt(TRADING_DAYS))


def training_score(net, benchmark, holdout_start):
    """The training-window Sharpe. Provisional: it is half of the score, and
    the half that can be read before the holdout opens."""
    active = _active(net, benchmark)
    start, end = training_window(active.index, holdout_start)
    window = active[(active.index >= start) & (active.index <= end)]
    s = _sharpe(window)
    return {"sharpe": s, "tier": tier(s), "start": window.index.min(), "end": window.index.max(),
            "n_days": len(window)}


def holdout_days(net, benchmark, holdout_start):
    active = _active(net, benchmark)
    return int((active.index >= pd.Timestamp(holdout_start)).sum())


def require_holdout_days(index, holdout_start):
    """The same refusal from the dates alone, so a run that cannot be scored
    is refused before it is recorded as a run or a trial."""
    have = int((index >= pd.Timestamp(holdout_start)).sum())
    if have < MIN_HOLDOUT_DAYS:
        raise HoldoutTooShort(
            f"the holdout from {pd.Timestamp(holdout_start):%Y-%m-%d} holds {have} days; "
            f"its score waits for {MIN_HOLDOUT_DAYS}"
        )


def require_holdout_ready(net, benchmark, holdout_start):
    have = holdout_days(net, benchmark, holdout_start)
    if have < MIN_HOLDOUT_DAYS:
        raise HoldoutTooShort(
            f"the holdout from {pd.Timestamp(holdout_start):%Y-%m-%d} holds {have} days; "
            f"its score waits for {MIN_HOLDOUT_DAYS}"
        )


def pooled_score(net, benchmark, holdout_start):
    """The score: training window and holdout pooled into one record.

    Refuses a holdout shorter than a year. The training window and the
    holdout are adjacent by construction, so the pooled record is one
    unbroken stretch.
    """
    require_holdout_ready(net, benchmark, holdout_start)
    active = _active(net, benchmark)
    start, end = training_window(active.index, holdout_start)
    pooled = active[active.index >= start]
    s = _sharpe(pooled)
    n_holdout = int((pooled.index >= pd.Timestamp(holdout_start)).sum())
    return {"sharpe": s, "tier": tier(s), "start": pooled.index.min(), "end": pooled.index.max(),
            "n_days": len(pooled), "n_holdout_days": n_holdout,
            "n_training_days": len(pooled) - n_holdout}
