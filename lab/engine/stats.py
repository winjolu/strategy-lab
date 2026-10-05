"""Every statistic the methodology asks for, computed by `market_core`.

Nothing here reimplements a statistic. Sharpe, its deflation, the minimum
track record, drawdown, time under water and Newey-West errors all live in
`market_core`, where they are tested once. This module assembles them into
the labelled figures a report needs and adds the two rules that belong to
this lab rather than to the shared code: the significance bands, and the
requirement that a return be measured against a benchmark.

Every figure carries its own label. A percentage is either absolute (what
the money did) or active (the edge over the benchmark), and the same arm
has been +12.09% on one and -0.06% on the other, so the key says which.
"""
import math

import numpy as np
import pandas as pd

from market_core import performance as perf
from market_core import timeseries

TRADING_DAYS = 252
MIN_OBSERVATIONS = 30

#: Words the methodology fixes. Absolute t, so a strongly negative edge is
#: named strong rather than weak.
BANDS = ((3.0, "strong"), (2.0, "promising"), (1.5, "underpowered"))
BELOW = "weak"  # a size, not an instruction: what to do with it is a gate's job, not this label's


class NoBenchmark(ValueError):
    """A return was about to be reported with nothing to measure it against."""


def band(t):
    """The methodology's word for a t-statistic on active return."""
    if t is None or not math.isfinite(t):
        return "undefined"
    for floor, word in BANDS:
        if abs(t) >= floor:
            return word
    return BELOW


def _quantiles(x):
    qs = x.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
    return {f"q{int(q * 100):02d}": float(v) for q, v in qs.items()}


def _corr(a, b):
    both = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(both) < MIN_OBSERVATIONS:
        return None
    return {"corr": float(both.iloc[:, 0].corr(both.iloc[:, 1])), "n": int(len(both))}


def _deflate(active, trials, sharpe_variance):
    """Deflated Sharpe on the active stream, or None when it cannot be
    measured. Needs at least two trials and a measured dispersion across
    them; with either missing there is nothing to deflate against and no
    figure is invented."""
    if trials is None or sharpe_variance is None or trials < 2:
        return None
    d = perf.deflated_sharpe(active, trials, sharpe_variance)
    return {"dsr": d["dsr"], "benchmark_sharpe_periodic": d["benchmark_sharpe"],
            "trials": trials}


def summarise(net, benchmark, spy=None, book=None, trials=None, sharpe_variance=None,
              lab_trials=None, lab_sharpe_variance=None):
    """Labelled figures for one return stream against its benchmark.

    `benchmark` is required and has no default: a return with nothing to
    be measured against is exactly what this refuses to produce. `spy` and
    `book` are optional only because a caller may not have them, and the
    report says so out loud rather than omitting the line.

    Deflation needs the number of trials and the dispersion of Sharpe
    ratios across them. If either is missing the result says it was not
    deflated, and does not substitute a guess.
    """
    if benchmark is None:
        raise NoBenchmark("a benchmark is required for every reported return")
    joined = pd.concat({"net": net, "bench": benchmark}, axis=1, join="inner").dropna()
    if len(joined) < MIN_OBSERVATIONS:
        raise ValueError(f"only {len(joined)} overlapping observations; need {MIN_OBSERVATIONS}")
    r, b = joined["net"], joined["bench"]
    active = r - b
    n = len(r)

    equity = (1.0 + r).cumprod()
    years = n / TRADING_DAYS
    cagr = (float(equity.iloc[-1]) ** (1.0 / years) - 1.0) * 100.0
    max_dd = perf.max_drawdown(np.r_[1.0, equity.values])
    tuw = perf.time_under_water(np.r_[1.0, equity.values])

    fit = timeseries.ols(active.values, np.ones(n), add_constant=False)
    t_active = fit["tvalues"][0]
    active_sharpe = perf.sharpe(active)

    out = {
        "n_days": n,
        "start": joined.index.min(), "end": joined.index.max(),
        "years": years,
        "absolute_cagr_pct": cagr,
        "absolute_sharpe_annual": perf.annualise(perf.sharpe(r), TRADING_DAYS),
        "absolute_max_drawdown_pct": max_dd,
        "absolute_mar": perf.mar(cagr, max_dd),
        "time_under_water_days_longest": tuw["longest"],
        "time_under_water_days_current": tuw["current"],
        "time_under_water_share": tuw["share"],
        "active_mean_pct_per_year": float(active.mean() * TRADING_DAYS * 100.0),
        "active_t_newey_west": t_active,
        "active_hac_lags": fit["hac_lags"],
        "active_sharpe_periodic": active_sharpe,
        "active_sharpe_annual": perf.annualise(active_sharpe, TRADING_DAYS),
        "band": band(t_active),
        "distribution_daily_absolute": {
            **_quantiles(r),
            "skew": float(r.skew()), "excess_kurtosis": float(r.kurt()),
            "best": float(r.max()), "worst": float(r.min()),
            "share_positive": float((r > 0).mean()),
        },
        "corr_to_benchmark": _corr(r, b),
        "corr_to_spy": _corr(r, spy) if spy is not None else None,
        "corr_to_book": _corr(r, book) if book is not None else None,
    }

    # Always computed: a diagnostic that appears only when a gate lands in a
    # certain place is a gate by another name.
    out["min_track_record_days"] = perf.minimum_track_record_length(active)
    out["deflated"] = _deflate(active, trials, sharpe_variance)
    out["deflated_lab"] = _deflate(active, lab_trials, lab_sharpe_variance)
    return out
