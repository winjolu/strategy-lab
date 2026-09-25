"""Point-in-time universes, built from what was actually trading.

Correcting one survivorship-biased universe in a sibling project moved an
arm from +11.55% over buy-and-hold to −7.80%: the entire apparent edge
was companies that had gone out of business. So membership here is never
"what is listed today" and never a list of tickers written down once.

**Membership comes from bar presence, not from the security master.**
The obvious construction is `firstpricedate <= d <= lastpricedate` out of
`tickers`, and it is wrong on this archive. That table is not part of the
daily refresh: its `lastpricedate` maxed at 2026-08-03 while `prices`
already reached 2026-09-22. The obvious rule therefore returns an empty
universe for the most recent seven weeks — silently, and precisely in the
window the current-regime tests run in. A name is in the universe on a
date because the archive holds a bar for it, which is self-validating and
cannot go stale.

`tickers` is still used, for attributes: sector, exchange, category and
the delisting flag. Those do not rot the same way.

**Filters look strictly backwards.** Everything conditioning membership
on a date is computed from bars dated before it. A signal computed at a
scan date and applied at a fill bar removed 226 of 273 trades in one
study; the same mistake made inside a universe filter is invisible,
because the universe is not what anyone inspects when a result looks
strong.
"""
import numpy as np
import pandas as pd

from market_core import liquidity

#: Default trailing window for the liquidity measure, in trading days.
#: A quarter. Short enough to react to a name going quiet, long enough
#: that a single halted week does not evict a liquid company.
LOOKBACK = 63

#: Share of a window that may sit on the volume storage floor before the
#: measure is refused. Mirrors `market_core.liquidity.MAX_QUANTISED`, and
#: a test asserts the two agree rather than trusting the copy.
MAX_QUANTISED = liquidity.MAX_QUANTISED
VOLUME_FLOOR = liquidity.VOLUME_FLOOR


class EmptyUniverse(RuntimeError):
    """A universe came back empty where that cannot be a real answer."""


def dollar_volume_panel(bars, floor=VOLUME_FLOOR, max_quantised=MAX_QUANTISED,
                        min_bars=1):
    """Mean dollar volume per ticker, or NaN where it cannot be measured.

    The vectorised twin of `market_core.liquidity.dollar_volume`, which
    takes a list of dicts and is the authority. This exists because the
    authority cannot be run row-by-row over a 46-million-row panel in any
    reasonable time, and it returns NaN in exactly the cases the
    authority returns None. `tests/test_universe.py` asserts the two
    agree on real bars; if they ever disagree, the authority is right.

    6.03% of this archive's price bars sit on the volume floor, across
    5,265 of 21,941 tickers. Their prices keep an inflated split-adjusted
    level while their volumes do not, so the product is no longer
    invariant — JAGX carries a $84,096,088,812 close against a volume of
    1. Any ranking by liquidity computed without this refusal sorts those
    names to the top.
    """
    frame = bars.loc[:, ["ticker", "close", "volume"]].copy()
    floored = frame["volume"].isna() | (frame["volume"] <= floor)
    frame["floored"] = floored
    frame["dv"] = np.where(floored, np.nan, frame["close"] * frame["volume"])

    grouped = frame.groupby("ticker", sort=False)
    total_bars = grouped.size()
    floored_share = grouped["floored"].mean()
    usable = grouped["dv"].count()
    measured = grouped["dv"].mean()

    refuse = (
        (total_bars < min_bars)
        | (floored_share > max_quantised)
        | (usable == 0)
    )
    return measured.where(~refuse)


def members_on(archive, as_of, lookback=LOOKBACK, min_price=None,
               min_dollar_volume=None, exclude_categories=None,
               calendar=None):
    """Tickers eligible on `as_of`, decided only from data before it.

    `as_of` is the decision date. The trailing window ends on the last
    trading day strictly before it, so nothing here can read the bar a
    trade would fill on.

    :param min_price: floor on the last close in the window. A price
        filter is a crude liquidity proxy and a crude bankruptcy filter
        at once; state which is intended before choosing a number.
    :param min_dollar_volume: floor on mean dollar volume over the
        window. Names whose volume is unmeasurable are dropped rather
        than kept — the conservative direction, and the correct one,
        since a series pinned to the storage floor is thin relative to
        its own adjusted share count.
    :param exclude_categories: `tickers.category` values to drop, for
        example ADRs or non-primary share classes.
    :return: a frame of one row per eligible ticker carrying the measured
        dollar volume and the last close, so a caller can rank or band
        without a second pass.
    """
    as_of = pd.Timestamp(as_of)
    if calendar is None:
        calendar = archive.trading_days(
            start=(as_of - pd.Timedelta(days=int(lookback * 2.2) + 20)).date(),
            end=as_of.date())
    calendar = pd.Series(pd.to_datetime(pd.Series(calendar).values)).drop_duplicates()
    prior = calendar[calendar < as_of].sort_values()
    if prior.empty:
        raise EmptyUniverse(
            f"no trading day in the archive before {as_of.date()}; the "
            f"calendar is built from the data, so this means the archive "
            f"does not reach back that far")
    window = prior.iloc[-lookback:]
    first, last = window.iloc[0].date(), window.iloc[-1].date()

    bars = archive.bars(start=first, end=last,
                        columns=["ticker", "date", "close", "volume"])
    if bars.empty:
        raise EmptyUniverse(f"no bars between {first} and {last}")

    # Live on the last day of the window. A name with bars earlier in the
    # window but none on its final day has stopped trading; including it
    # is how a delisted company gets bought.
    live = set(bars.loc[bars["date"] == window.iloc[-1], "ticker"])

    measured = dollar_volume_panel(bars)
    closes = (bars.sort_values("date")
                  .groupby("ticker", sort=False)["close"].last())

    out = pd.DataFrame({
        "ticker": measured.index,
        "dollar_volume": measured.to_numpy(),
        "last_close": closes.reindex(measured.index).to_numpy(),
    })
    out = out[out["ticker"].isin(live)]

    if min_price is not None:
        out = out[out["last_close"] >= min_price]
    if min_dollar_volume is not None:
        # NaN fails this comparison, which drops the unmeasurable names.
        out = out[out["dollar_volume"] >= min_dollar_volume]

    if exclude_categories:
        master = archive.security_master("SEP")
        drop = set(master.loc[
            master["category"].isin(exclude_categories), "ticker"])
        out = out[~out["ticker"].isin(drop)]

    out = out.sort_values("ticker").reset_index(drop=True)
    out.insert(0, "as_of", as_of)
    return out


def membership(archive, dates, **kwargs):
    """`members_on` across several decision dates, stacked.

    One calendar is fetched and reused, because the trading calendar is
    the same for every date and re-reading it per date is most of the
    cost.
    """
    dates = [pd.Timestamp(d) for d in dates]
    span_start = min(dates) - pd.Timedelta(
        days=int(kwargs.get("lookback", LOOKBACK) * 2.2) + 20)
    calendar = archive.trading_days(start=span_start.date(),
                                    end=max(dates).date())
    frames = [members_on(archive, d, calendar=calendar, **kwargs)
              for d in dates]
    return pd.concat(frames, ignore_index=True)
