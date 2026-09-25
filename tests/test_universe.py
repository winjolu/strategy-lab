"""The universe is point-in-time, survivorship-complete, and refuses to
measure liquidity it cannot measure."""
import numpy as np
import pandas as pd
import pytest

from market_core import liquidity

from lab.data import universe
from lab.data.archive import default


@pytest.fixture(scope="module")
def archive():
    return default()


def _as_bars(frame):
    """The list-of-dicts shape `market_core.liquidity` takes."""
    return [{"close": c, "volume": v}
            for c, v in zip(frame["close"], frame["volume"])]


def test_vectorised_dollar_volume_agrees_with_the_shared_authority(archive):
    """Two implementations, one authority.

    `market_core.liquidity.dollar_volume` is the guard; the panel version
    exists only because the guard cannot be run row-by-row over 46 million
    rows. They must agree on real bars, including on which names they
    refuse to measure at all. If they ever disagree, the shared one is
    right and this one is wrong.
    """
    bars = archive.bars(start="2026-06-01", end="2026-09-01",
                        columns=["ticker", "date", "close", "volume"])
    sample = sorted(bars["ticker"].unique())[:400]
    bars = bars[bars["ticker"].isin(sample)]

    mine = universe.dollar_volume_panel(bars)
    checked = 0
    for ticker, group in bars.groupby("ticker", sort=False):
        theirs = liquidity.dollar_volume(_as_bars(group))
        ours = mine.get(ticker)
        if theirs is None:
            assert pd.isna(ours), (
                f"{ticker}: the shared guard refuses to measure this and the "
                f"panel version returned {ours}")
        else:
            assert ours == pytest.approx(theirs, rel=1e-9), ticker
        checked += 1
    assert checked > 100, "sample too small to mean anything"


def test_some_names_are_genuinely_refused(archive):
    """The agreement test is vacuous if nothing is ever refused.

    6.03% of this archive's bars sit on the volume storage floor. If no
    name in a 400-name sample is unmeasurable, the refusal has stopped
    working and the test above is passing on a technicality.
    """
    bars = archive.bars(start="2026-06-01", end="2026-09-01",
                        columns=["ticker", "date", "close", "volume"])
    refused = universe.dollar_volume_panel(bars).isna().sum()
    assert refused > 0, (
        "no name was refused across the whole panel; the quantisation "
        "refusal is not firing")


def test_membership_reads_only_bars_before_the_decision_date(archive):
    """A return may only begin after the decision that caused it.

    The trailing window must end strictly before `as_of`, so a universe
    built for a decision on a date cannot have seen that date's bar.
    """
    calls = []
    real_bars = archive.bars

    class Spy:
        def __getattr__(self, name):
            return getattr(archive, name)

        def bars(self, *args, **kwargs):
            calls.append(kwargs)
            return real_bars(*args, **kwargs)

    universe.members_on(Spy(), "2026-09-22")
    assert calls, "no bar read was made"
    assert all(pd.Timestamp(c["end"]) < pd.Timestamp("2026-09-22")
               for c in calls), (
        f"the universe read bars dated on or after its own decision date: "
        f"{[str(c['end']) for c in calls]}")


def test_a_historical_universe_contains_companies_that_no_longer_exist(archive):
    """Survivorship correction inverted a result once; this proves the
    archive can be built without the bias in the first place."""
    members = universe.members_on(archive, "2010-07-01")
    master = archive.security_master("SEP")
    delisted = set(master.loc[master["isdelisted"] == "Y", "ticker"])
    overlap = members["ticker"].isin(delisted).mean()
    assert overlap > 0.25, (
        f"only {overlap:.1%} of the 2010 universe has since delisted; a "
        f"point-in-time universe built from a survivor-only source looks "
        f"exactly like this")


def test_membership_does_not_come_from_the_stale_security_master(archive):
    """`tickers.lastpricedate` stopped at 2026-08-03 while `prices` ran to
    2026-09-22. Building membership from it empties the recent window."""
    master = archive.security_master("SEP")
    latest_master = master["lastpricedate"].max()
    members = universe.members_on(archive, "2026-09-22")
    assert len(members) > 1000, (
        f"universe of {len(members)} names on a normal trading day; the "
        f"security master only reaches {latest_master}, so a membership rule "
        f"reading it would have returned almost nothing")


def test_unmeasurable_names_are_dropped_rather_than_kept(archive):
    """The conservative direction, and the correct one."""
    unfiltered = universe.members_on(archive, "2026-09-22")
    filtered = universe.members_on(archive, "2026-09-22",
                                   min_dollar_volume=1_000_000)
    assert unfiltered["dollar_volume"].isna().sum() > 0
    assert filtered["dollar_volume"].isna().sum() == 0


def test_a_name_that_stopped_trading_is_not_in_the_universe():
    """Bars earlier in the window but none on its last day means delisted."""
    window = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
    bars = pd.DataFrame({
        "ticker": ["LIVE"] * 3 + ["GONE"] * 2,
        "date": list(window) + list(window[:2]),
        "close": [10.0] * 5,
        "volume": [1e6] * 5,
    })

    class Fake:
        def trading_days(self, start=None, end=None):
            return pd.Series(window)

        def bars(self, **kwargs):
            return bars

        def security_master(self, tbl="SEP"):
            return pd.DataFrame(columns=["ticker", "category"])

    got = universe.members_on(Fake(), "2020-01-07")
    assert list(got["ticker"]) == ["LIVE"]
