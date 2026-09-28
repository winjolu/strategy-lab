"""Signal, sizing and data assembly for `xs-mr-khandani-lo`.

The registered strategy in one sentence: short the S&P 500 names that beat
their peers yesterday, buy the ones that lagged, sized two ways, and
measured under two execution conventions because the published version
trades on the same close its signal is read from. Full reasoning is in
`registry/xs-mr-khandani-lo.md`; this module is the code that reasoning
describes and nothing more.
"""
from dataclasses import dataclass

import pandas as pd

from lab.data import sp500_membership
from lab.engine import returns as returns_mod
from lab.engine import sizing

#: The registered decile cut. Kept here, not just in the registry's
#: `parameters` table, because the sizing rule needs the actual number.
DECILE_FRACTION = 0.1


def signal(returns_cc, membership):
    """`s_i = -(r_i - r_bar)` against the equal-weighted mean of eligible
    members, for every date `returns_cc` and `membership` share.

    A cell is eligible only where `membership` is True there and
    `returns_cc` is not NaN. A member with no adjusted close on this date
    or the previous one — new to the archive, or a gap — contributes to
    nobody's mean and gets no signal of its own, which is what "a member
    enters the signal on a date only if it has adjusted closes on that
    date and the previous trading day" means in the registration.

    The result carries NaN in every ineligible cell, on purpose: it is
    fed to `lab.engine.sizing.decile_mask`, which reads NaN as "not
    eligible", or to `linear` after an explicit `.fillna(0.0)`, matching
    the sizing module's convention that a flat name is 0, not missing.
    """
    masked = returns_cc.where(membership)
    row_mean = masked.mean(axis=1)
    return -(masked.sub(row_mean, axis=0))


def weights(sig, rule, gross=1.0):
    """The two registered sizing rules, by name."""
    if rule == "linear":
        return sizing.linear(sig.fillna(0.0), gross=gross, long_short=True)
    if rule == "decile_equal":
        mask = sizing.decile_mask(sig, fraction=DECILE_FRACTION)
        return sizing.equal_weight(mask, gross=gross, long_short=True)
    raise ValueError(f"unknown sizing rule {rule!r}; expected 'linear' or 'decile_equal'")


@dataclass
class RunInputs:
    """Everything `lab.engine.pipeline.evaluate` needs, for both execution
    conventions, over one point-in-time universe.

    `spy_cc`/`spy_oo` are on the same basis as `returns_cc`/`returns_oo`
    respectively, so a correlation against them is not contaminated by an
    open-versus-close basis difference between the two series. The book
    series is not built here: `lab.engine.book` only knows the trailing
    close-to-close convention, and a caller passing it into the
    open-to-open evaluation would reintroduce exactly that contamination.
    Until an open-to-open book series exists, that evaluation reports the
    book correlation as NOT COMPUTED rather than a number on the wrong
    basis; the close-to-close evaluation can take the existing book series
    directly.
    """
    weights_by_sizing: dict
    returns_cc: pd.DataFrame
    returns_oo: pd.DataFrame
    benchmark_cc: pd.Series
    benchmark_oo: pd.Series
    spy_cc: pd.Series
    spy_oo: pd.Series


def build(archive, start, end, benchmark_ticker="BIL", spy_ticker="SPY",
         min_members=sp500_membership.MIN_MEMBERS, max_members=sp500_membership.MAX_MEMBERS):
    """Assemble `RunInputs` from the archive, reading bars only in
    `[start, end]`.

    That range is the whole of the look-ahead protection for the
    open-to-open frame: its last row needs an open beyond the fetched
    bars to compute and comes back NaN, so it is dropped by construction
    (see `lab.engine.returns.open_to_open`). A caller building a
    pre-holdout panel passes `end` at or before the holdout date and the
    frame this returns structurally cannot contain a holdout price,
    independent of anything the caller remembers to check.

    `min_members`/`max_members` default to the real index's measured
    band and only need overriding against a synthetic universe far
    smaller than the S&P 500.
    """
    trading_days = pd.DatetimeIndex(pd.to_datetime(archive.trading_days(start=start, end=end)))
    panel = sp500_membership.membership_panel(archive, trading_days,
                                              min_members=min_members, max_members=max_members)
    tickers = panel.columns[panel.any(axis=0)].tolist()

    bars = archive.bars(tickers, start=start, end=end,
                        columns=["ticker", "date", "open", "close", "closeadj"])
    returns_cc = returns_mod.close_to_close(bars)
    returns_oo = returns_mod.open_to_open(bars)

    aligned = panel.reindex(index=returns_cc.index, columns=returns_cc.columns, fill_value=False)
    sig = signal(returns_cc, aligned)
    weights_by_sizing = {rule: weights(sig, rule) for rule in ("linear", "decile_equal")}

    fund_bars = archive.fund_bars([benchmark_ticker, spy_ticker], start=start, end=end,
                                  columns=["ticker", "date", "open", "close", "closeadj"])
    fund_cc = returns_mod.close_to_close(fund_bars)
    fund_oo = returns_mod.open_to_open(fund_bars)
    benchmark_cc = fund_cc[benchmark_ticker].rename(benchmark_ticker)
    benchmark_oo = fund_oo[benchmark_ticker].rename(benchmark_ticker)
    spy_cc = fund_cc[spy_ticker].rename(spy_ticker)
    spy_oo = fund_oo[spy_ticker].rename(spy_ticker)

    return RunInputs(weights_by_sizing, returns_cc, returns_oo, benchmark_cc, benchmark_oo,
                     spy_cc, spy_oo)
