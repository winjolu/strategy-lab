"""Signal, sizing and data assembly for `crypto-perp-funding-carry`.

The registered strategy in one sentence: hold a coin as the collateral for an
equal-dollar short of its inverse perpetual, collecting the perpetual's
funding with no exposure to the coin's price, either always or only while
trailing funding is high. The reasoning, including why the inverse contract's
convexity cancels, is in `registry/crypto-perp-funding-carry.md`; this
module is the code that reasoning describes and nothing more.

Crypto produces a row every calendar day. The lab's annualisation and its
cash benchmark are on the equity trading calendar, so every daily series is
folded onto that calendar before anything is evaluated: the row for trading
day `D` covers the UTC days after the previous trading day up to and
including `D`, and a row with any missing constituent day is missing.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

COINS = ("btc", "eth")
CASH = "cash"
THRESHOLD_APR_PCT = 10.0     # registered parameters, kept here because the
LOOKBACK_DAYS = 30           # signal needs the numbers and not just the table
COIN_WEIGHT = 0.5
FUNDING_DAYS_PER_YEAR = 365  # funding is quoted per calendar day


def unit_returns(ratio):
    """Daily return of the carry unit from the index-to-perpetual price
    ratio: `ratio_d / ratio_{d-1} - 1`. NaN wherever either day is missing,
    so a gap never becomes a return that spans it."""
    previous = ratio.shift(1)
    # shift(1) pairs a day with its calendar predecessor only if the index is
    # continuous; refuse a series with holes in its dates instead of
    # comparing day d with day d-3.
    if len(ratio) > 1 and not (ratio.index.to_series().diff().dropna() == pd.Timedelta(days=1)).all():
        raise ValueError("price ratio index is not one row per calendar day")
    return (ratio / previous - 1.0).rename("unit_return")


def fold(daily, calendar, how):
    """Fold a calendar-day series onto `calendar`. `how` is "compound" for
    returns or "sum" for funding. A trading day with any constituent day
    missing is NaN; the first trading day has no previous one and is
    dropped."""
    if how not in ("compound", "sum"):
        raise ValueError("how must be 'compound' or 'sum'")
    calendar = pd.DatetimeIndex(calendar)
    if not calendar.is_monotonic_increasing or calendar.has_duplicates:
        raise ValueError("calendar must be sorted with no duplicates")
    full = pd.date_range(calendar[0] + pd.Timedelta(days=1), calendar[-1], freq="D")
    s = daily.reindex(full)
    pos = calendar.searchsorted(full, side="left")
    key = calendar[pos]
    expected = pd.Series(1, index=full).groupby(key).sum()
    present = s.notna().groupby(key).sum()
    x = np.log1p(s) if how == "compound" else s
    total = x.groupby(key).sum(min_count=1)
    out = np.expm1(total) if how == "compound" else total
    out = out.where(present == expected)
    return out.reindex(calendar[1:])


def trailing_funding_apr_pct(daily_funding, lookback=LOOKBACK_DAYS):
    """Trailing mean of daily funding, annualised on the funding convention
    (calendar days) and in percent. NaN until a full window of complete days
    exists: a window with a hole is not a mean of a shorter one."""
    mean = daily_funding.rolling(lookback, min_periods=lookback).mean()
    return mean * FUNDING_DAYS_PER_YEAR * 100.0


def weights(apr_pct_by_coin, calendar, rule, threshold=THRESHOLD_APR_PCT,
            coin_weight=COIN_WEIGHT):
    """Decision weights on `calendar`, columns btc, eth and cash.

    `threshold` holds a coin's unit when its trailing funding exceeds the
    threshold and parks that half in cash otherwise, the registered
    decision book. `always_on` holds both units every day. A day on which the
    trailing figure is undefined is not held: absence of a signal is cash,
    never carry.
    """
    if rule not in ("threshold", "always_on"):
        raise ValueError(f"unknown sizing rule {rule!r}")
    out = pd.DataFrame(0.0, index=calendar, columns=[*COINS, CASH])
    for coin in COINS:
        if rule == "always_on":
            held = pd.Series(True, index=calendar)
        else:
            apr = apr_pct_by_coin[coin].reindex(calendar)
            held = apr > threshold     # NaN compares False: no signal is cash
        out[coin] = held.astype(float) * coin_weight
        out[CASH] += (~held).astype(float) * coin_weight
    return out


@dataclass
class Inputs:
    weights_by_sizing: dict
    returns: pd.DataFrame
    funding: pd.DataFrame
    benchmark: pd.Series
    daily_funding: dict       # venue-signed, calendar days, for reporting


def assemble(ratio_by_coin, funding_by_coin, benchmark, calendar):
    """Everything `pipeline.evaluate` needs, on the equity `calendar`.

    `funding_by_coin` is the venue's daily funding, positive meaning longs
    pay shorts. The unit is short the perpetual, so the series charged to it
    is the negation: a positive venue rate is a receipt. `benchmark` is the
    cash return on the same calendar, carried by the cash column.
    """
    calendar = pd.DatetimeIndex(calendar)
    returns, charged, apr = {}, {}, {}
    for coin in COINS:
        returns[coin] = fold(unit_returns(ratio_by_coin[coin]), calendar, "compound")
        charged[coin] = fold(-funding_by_coin[coin], calendar, "sum")
        apr[coin] = trailing_funding_apr_pct(funding_by_coin[coin])
    bench = benchmark.reindex(calendar[1:])
    returns[CASH] = bench
    frame = pd.DataFrame(returns)
    decisions = {rule: weights(apr, calendar[1:], rule) for rule in ("threshold", "always_on")}
    return Inputs(decisions, frame, pd.DataFrame(charged), bench.rename(benchmark.name),
                  dict(funding_by_coin))
