"""Apply decisions to returns, and charge for doing it.

The one rule this module exists to enforce: **a decision made at the close
of day d earns the return of a later day, never of d itself.** Strategies
hand over weights indexed by decision date and never touch returns, so a
signal cannot read the return it is being paid. The shift is here, it is
at least one row, and `lag < 1` raises. Any strategy that needs more delay
than one row says so through `lag`, visibly, not by shifting its own
signal.

Shapes: `weights` is decision dates by names, `returns` is trading dates by
names holding the simple return of the day ending on that date. Each row of
`weights` is a rebalance: on the day it takes effect the book is traded to
those weights, and between rows the positions drift with prices and nothing
is traded. A weekly strategy supplies weekly rows and pays for weekly
trading; a strategy that wants constant weights supplies a row every day.

Costs are sized on start-of-day equity, before the day's own costs are
taken out; the error is second order in the cost rate. The book is marked
to market at the end rather than liquidated, so the final exit is not
charged.

A held name whose return is missing is an error by default. A delisted
name has no return after its last bar, and silently filling it with zero is
the survivorship bias that a point-in-time universe was built to remove.
`on_missing="zero"` exists for the deliberate case and the count of
position-days it touched is carried on the result.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from lab.engine.costs import DAY_COUNT_BASIS, CostNotStated

TRADING_DAYS = 252

#: Weights summing to 1 + 1e-16 are a long-only book, not a levered one.
EXPOSURE_TOLERANCE = 1e-9


class MissingReturn(ValueError):
    """A held name has no return on a day it was held."""


class LookaheadRisk(ValueError):
    """The arguments would let a decision earn its own day's return."""


class FundingMissing(ValueError):
    """A position that pays or receives funding was held on a day with none on file."""


class EquityExhausted(ValueError):
    """The book lost all of its equity; nothing after that day is meaningful."""


@dataclass
class Backtest:
    gross: pd.Series        # return before any cost
    net: pd.Series          # return after every cost
    turnover: pd.Series     # traded notional as a fraction of equity, per day
    costs: pd.DataFrame     # slippage, commission, borrow, margin, per day
    held: pd.DataFrame      # weights actually held over each day
    zeroed_position_days: int
    lag: int

    @property
    def annual_turnover(self):
        return float(self.turnover.mean() * TRADING_DAYS)

    @property
    def has_shorts(self):
        return bool((self.held < -EXPOSURE_TOLERANCE).any().any())

    @property
    def max_long_gross(self):
        return float(self.held.clip(lower=0).sum(axis=1).max())


def _clean_weights(weights):
    if not weights.index.is_monotonic_increasing or weights.index.has_duplicates:
        raise LookaheadRisk("weights index must be sorted with no duplicate dates")
    if weights.isna().any().any():
        raise ValueError("weights contain NaN; a flat name is 0, not missing")
    return weights


def _funding_cost(funding, held, index, columns):
    """What the day's funding cost the book, signed: positive is a payment.

    `funding` is dates by names, the rate a position held through that day
    paid, as a fraction of notional, positive meaning longs pay shorts. A
    column present in it is a funding-bearing instrument, such as a
    perpetual; a column absent from it pays nothing, such as the spot leg of
    a hedge. A funding-bearing name held on a day with no rate on file is an
    error, not zero: zero would flatter a long and understate what a short
    receives, and the shortfall would not show.
    """
    if funding is None:
        return pd.Series(0.0, index)
    if not funding.index.is_monotonic_increasing or funding.index.has_duplicates:
        raise LookaheadRisk("funding index must be sorted with no duplicate dates")
    if not np.isfinite(funding.to_numpy(float)[~np.isnan(funding.to_numpy(float))]).all():
        raise ValueError("funding contains inf")
    bearing = columns.isin(funding.columns)
    rate = funding.reindex(index=index, columns=columns)
    missing = rate.isna() & (held != 0) & bearing
    if missing.any().any():
        first = missing.any(axis=1).idxmax()
        raise FundingMissing(
            f"{int(missing.sum().sum())} funding-bearing position-days have no funding rate, "
            f"first on {first:%Y-%m-%d}; a missing rate is not a zero rate")
    return (held * rate.fillna(0.0)).sum(axis=1)


def run(weights, returns, cost, lag=1, on_missing="raise", funding=None):
    if lag < 1:
        raise LookaheadRisk("lag must be at least 1: a decision cannot earn its own day")
    if on_missing not in ("raise", "zero"):
        raise ValueError("on_missing must be 'raise' or 'zero'")
    weights = _clean_weights(weights)
    if not returns.index.is_monotonic_increasing or returns.index.has_duplicates:
        raise LookaheadRisk("returns index must be sorted with no duplicate dates")
    unknown = set(weights.columns) - set(returns.columns)
    if unknown:
        raise ValueError(f"weights name {sorted(unknown)[:5]} with no return column")

    returns = returns.reindex(columns=weights.columns)
    finite = returns.isna() | np.isfinite(returns)
    if not finite.all().all():
        raise ValueError("returns contain inf; a price of zero or a units break upstream")

    slot = returns.index.searchsorted(weights.index, side="left") + lag
    keep = slot < len(returns.index)
    targets = pd.DataFrame(weights.values[keep], index=slot[keep], columns=weights.columns)
    targets = targets[~targets.index.duplicated(keep="last")]

    r = returns.fillna(0.0).values
    target_at = dict(zip(targets.index, targets.values))
    held_v = np.zeros_like(r)
    drifted_v = np.zeros_like(r)
    prev = np.zeros(r.shape[1])
    with np.errstate(divide="ignore", invalid="ignore"):
        for i in range(len(r)):
            h = target_at.get(i, prev)
            held_v[i] = h
            drifted_v[i] = prev = h * (1.0 + r[i]) / (1.0 + h @ r[i])
    held = pd.DataFrame(held_v, returns.index, weights.columns)

    missing = returns.isna() & (held != 0)
    if missing.any().any():
        if on_missing == "raise":
            n = int(missing.sum().sum())
            first = missing.any(axis=1).idxmax()
            raise MissingReturn(
                f"{n} position-days are held with no return, first on {first:%Y-%m-%d}. "
                "Filling with zero would be the survivorship bias; pass on_missing='zero' "
                "only if a zero return is the intended treatment."
            )
    zeroed = int(missing.sum().sum())

    gross = pd.Series((held_v * r).sum(axis=1), returns.index)
    previous = pd.DataFrame(drifted_v, returns.index, weights.columns).shift(1).fillna(0.0)
    turnover = (held - previous).abs().sum(axis=1)

    days = pd.Series(returns.index, index=returns.index).diff().dt.days.fillna(1).clip(lower=1)
    short_gross = (-held.clip(upper=0)).sum(axis=1)
    debit = (held.clip(lower=0).sum(axis=1) - 1.0).clip(lower=0)

    if short_gross.max() > EXPOSURE_TOLERANCE and cost.borrow_apr is None:
        raise CostNotStated("the strategy shorts; borrow_apr must be stated")
    if debit.max() > EXPOSURE_TOLERANCE and cost.margin_apr is None:
        raise CostNotStated("the strategy uses leverage; margin_apr must be stated")

    funding_cost = _funding_cost(funding, held, returns.index, weights.columns)

    parts = pd.DataFrame({
        "slippage": turnover * cost.slippage_pct / 100.0,
        "commission": turnover * cost.commission_bps / 1e4,
        "borrow": short_gross * (cost.borrow_apr or 0.0) / 100.0 / DAY_COUNT_BASIS * days,
        "margin": debit * (cost.margin_apr or 0.0) / 100.0 / DAY_COUNT_BASIS * days,
        "funding": funding_cost,
    })
    net = gross - parts.sum(axis=1)
    if (net <= -1.0).any():
        raise EquityExhausted(f"net of costs the book is wiped out on {(net <= -1.0).idxmax():%Y-%m-%d}")
    return Backtest(gross, net, turnover, parts, held, zeroed, lag)
