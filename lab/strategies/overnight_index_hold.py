"""Sizing and data assembly for `overnight-index-hold`.

The registered strategy in one sentence: own the index from each close to the
next open and hold cash, earning nothing, through the trading day. The
reasoning is in `registry/overnight-index-hold.md`; this module is the code
that reasoning describes and nothing more.

A row of the night series dated `t` is the night that ended at the open of
`t`, known by the time any order for the close of `t` is entered. Weights
dated `t` are applied by the engine to the night after the close of `t`.
"""
from dataclasses import dataclass
import math

import pandas as pd

from lab.engine import returns as returns_mod

GRID = ("SPY", "QQQ", "IWM")
VOL_TARGET_PCT = 10.0      # registered parameters, kept here because the
VOL_LOOKBACK_DAYS = 63     # sizing needs the numbers and not just the table
GROSS_CAP = 1.0
NIGHTS_PER_YEAR = 252


def weights(night, instrument, rule, target_pct=VOL_TARGET_PCT,
            lookback=VOL_LOOKBACK_DAYS, cap=GROSS_CAP):
    """Decision weights for one instrument, one column, dated like `night`.

    `full` holds 1.0 every night. `vol_target` scales to the target over the
    trailing `lookback` nights ending with the one dated `t`, capped at `cap`;
    until a full window exists it holds nothing, since no signal is cash.
    """
    if rule == "full":
        w = pd.Series(1.0, index=night.index)
    elif rule == "vol_target":
        vol = night[instrument].rolling(lookback, min_periods=lookback).std() * math.sqrt(NIGHTS_PER_YEAR)
        w = (target_pct / 100.0 / vol).clip(upper=cap).fillna(0.0)
    else:
        raise ValueError(f"unknown sizing rule {rule!r}")
    return w.to_frame(instrument)


@dataclass
class Inputs:
    night: pd.DataFrame        # close-to-open, every instrument in the grid
    day: pd.DataFrame          # open-to-close, for reporting
    benchmark: pd.Series       # SPY close to close, named SPY
    bil: pd.Series             # BIL close to close, for the flags


def build(fund_bars):
    """Night, day and benchmark series from `fundprices` bars of the grid and
    BIL. The benchmark is SPY held all day, on the same dates as the nights."""
    grid = fund_bars[fund_bars["ticker"].isin(GRID)]
    night = returns_mod.close_to_open(grid)
    day = returns_mod.open_to_close(grid).reindex(night.index)
    whole = returns_mod.close_to_close(fund_bars[fund_bars["ticker"].isin(GRID + ("BIL",))])
    benchmark = whole["SPY"].reindex(night.index).rename("SPY")
    bil = whole["BIL"].reindex(night.index).rename("BIL")
    return Inputs(night[list(GRID)], day[list(GRID)], benchmark, bil)
