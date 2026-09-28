"""Turning a signal into weights, and how much leverage the data supports.

A backtest states its sizing rule and reports under at least two, because
a result that exists only under one sizing is partly a result about the
sizing. The rules here take a signal panel of +1, -1 and 0 (dates by
names) and return a weights panel indexed by the same decision dates.

Weights are *decisions*: row d is what I choose knowing information
through the close of d. The engine, not the strategy, applies them to the
following period's returns, so a rule that reads its own answer cannot be
written by accident here.
"""
import numpy as np
import pandas as pd

MAX_KELLY_FRACTION = 0.25


class SizingError(ValueError):
    pass


def _check(signal, long_short):
    if signal.isna().any().any():
        raise SizingError("signal has NaN; a name with no view must be 0, not missing")
    if not long_short and (signal < 0).any().any():
        raise SizingError("negative signal in a long-only sizing; pass long_short=True")


def _normalise(raw, gross, long_short):
    """Scale positive and negative books to `gross` in total.

    Long-short: each side gets half, and a date missing a side is flat.
    Taking full gross on the one side that exists would quietly turn a
    dollar-neutral design into a directional one on exactly the days
    the signal is thinnest.
    """
    pos = raw.clip(lower=0)
    neg = (-raw).clip(lower=0)
    pos_sum, neg_sum = pos.sum(axis=1), neg.sum(axis=1)
    if long_short:
        half = gross / 2.0
        long_side = pos.div(pos_sum.replace(0, np.nan), axis=0).mul(half)
        short_side = neg.div(neg_sum.replace(0, np.nan), axis=0).mul(half)
        both = (pos_sum > 0) & (neg_sum > 0)
        out = (long_side.fillna(0) - short_side.fillna(0)).where(both, 0.0)
    else:
        out = pos.div(pos_sum.replace(0, np.nan), axis=0).mul(gross).fillna(0.0)
    return out


def equal_weight(signal, gross=1.0, long_short=False):
    _check(signal, long_short)
    return _normalise(np.sign(signal).astype(float), gross, long_short)


def linear(signal, gross=1.0, long_short=True):
    """Weight proportional to the signal's own magnitude, not just its
    sign. A name that moved three times as far from the mean as another
    gets three times the weight, before the two sides are each scaled to
    their share of `gross` — unlike `equal_weight`, which reduces every
    non-zero signal to +1 or -1 first and so cannot tell a large move from
    a small one.
    """
    _check(signal, long_short)
    return _normalise(signal.astype(float), gross, long_short)


def decile_mask(signal, fraction=0.1):
    """+1 for the top `fraction` of each row's signal, -1 for the bottom
    `fraction`, 0 for the rest — including anywhere `signal` is missing.

    Ranked per row (per date), so a date's decile line is drawn only from
    the names eligible that day; a name absent from today's universe never
    displaces one that is present. `signal` may carry NaN for an
    ineligible name, unlike every other sizing function here, and the
    output never does: pandas leaves the rank of a NaN cell as NaN, and a
    NaN threshold comparison is always False, so an ineligible name falls
    through to 0 rather than needing a separate NaN check.
    """
    if not 0 < fraction <= 0.5:
        raise SizingError(f"fraction must be in (0, 0.5], got {fraction}")
    pct = signal.rank(axis=1, pct=True, na_option="keep")
    out = pd.DataFrame(0.0, index=signal.index, columns=signal.columns)
    out[pct > 1.0 - fraction] = 1.0
    out[pct <= fraction] = -1.0
    return out


def inverse_vol(signal, vol, gross=1.0, long_short=False):
    """Weight inversely to trailing volatility, within each side.

    `vol` must be known at the decision date, computed on data through
    that date. Names with no volatility estimate are dropped from the
    book rather than filled, since a made-up volatility is a made-up
    weight.
    """
    _check(signal, long_short)
    vol = vol.reindex(index=signal.index, columns=signal.columns)
    inv = (1.0 / vol.where(vol > 0)).where(signal != 0)
    raw = (np.sign(signal) * inv).fillna(0.0)
    return _normalise(raw, gross, long_short)


def kelly_leverage(returns, fraction=MAX_KELLY_FRACTION):
    """Leverage a fractional Kelly rule supports, mean over variance.

    Estimated on the same sample the strategy was found in, so it is an
    upper bound on what is defensible, not a target. Fractions above a
    quarter are refused: full Kelly is optimal only for a known
    distribution and ruinous for an estimated one.
    """
    if not 0 < fraction <= MAX_KELLY_FRACTION:
        raise SizingError(f"Kelly fraction must be in (0, {MAX_KELLY_FRACTION}]")
    r = pd.Series(returns).dropna()
    if len(r) < 2 or r.var(ddof=0) <= 0:
        return float("nan")
    return float(fraction * r.mean() / r.var(ddof=0))
