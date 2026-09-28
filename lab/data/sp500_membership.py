"""Point-in-time S&P 500 membership, reconstructed from event history.

The `sp500` table holds three kinds of row: a full membership snapshot
every quarter since 1998-03-31 (`action = "historical"`), and point events
since 1957 (`added`, `removed`) that record every change between and
around those snapshots. A fourth kind, `current`, is a daily snapshot of
today's membership starting 2026-08-03; it is never read here, because the
`historical` anchors plus `added`/`removed` already reach every date this
lab asks for, and trusting two different mechanisms for the same fact is
how they drift apart unnoticed.

Membership as of a date is: take the most recent quarterly snapshot at or
before it, then replay every `added`/`removed` event between that snapshot
and the date. Reconstructing this way against the actual quarterly
snapshots agrees with them exactly on every quarter-end checked.
"""
import numpy as np
import pandas as pd

#: The reconstructed count sits at 500-505 on every date from 1998-03-31
#: onward, measured directly. A reconstruction bug is far more likely to
#: blow this up or empty it than to land it just outside a tight band, so
#: the band is wide enough to absorb a data revision and tight enough to
#: catch a real defect.
MIN_MEMBERS = 480
MAX_MEMBERS = 520


class MembershipError(RuntimeError):
    """Reconstructed membership could not be built, or landed somewhere
    implausible."""


def _checkpoints(events):
    """One (date, frozenset(tickers)) row per date membership changed,
    sorted by date.

    A `historical` row is a full snapshot and replaces the running set
    outright rather than adjusting it, so any drift from a missed or
    duplicated event is corrected every quarter rather than compounding
    for decades. `added`/`removed` rows between snapshots adjust the set
    incrementally.
    """
    events = events[events["action"].isin(("historical", "added", "removed"))]
    members = set()
    out = []
    for d, day in events.sort_values("date").groupby("date", sort=True):
        hist = day[day["action"] == "historical"]
        if len(hist):
            members = set(hist["ticker"])
        else:
            for _, row in day.iterrows():
                if row["action"] == "added":
                    members.add(row["ticker"])
                else:
                    members.discard(row["ticker"])
        out.append((d, frozenset(members)))
    return out


def membership_panel(archive, dates, events=None, min_members=MIN_MEMBERS, max_members=MAX_MEMBERS):
    """A boolean frame (dates x tickers) of S&P 500 membership as of the
    close of each requested date.

    Built once from the checkpoint history and then assigned to requested
    dates in blocks between checkpoints, rather than reconstructed from
    scratch per date — the difference between a handful of assignments and
    one per trading day, over a multi-decade panel.

    Raises `MembershipError` if a requested date is before the first
    checkpoint (there is nothing to reconstruct from) or if any date's
    membership count falls outside `[min_members, max_members]`, since a
    result this far from every measured quarter is a defect, not data.
    `min_members`/`max_members` are overridable for anything reconstructing
    a smaller, synthetic universe; every real call keeps the module
    defaults measured against the actual index.
    """
    dates = pd.DatetimeIndex(sorted(pd.Timestamp(d) for d in pd.Index(dates).unique()))
    if len(dates) == 0:
        raise MembershipError("no dates requested")
    if events is None:
        events = archive.sp500_events(end=str(dates.max().date()))
    checkpoints = _checkpoints(events)
    if not checkpoints:
        raise MembershipError("no membership events available to reconstruct from")
    checkpoint_dates = pd.DatetimeIndex([d for d, _ in checkpoints])
    if dates.min() < checkpoint_dates.min():
        raise MembershipError(
            f"{dates.min():%Y-%m-%d} is before the first membership record "
            f"({checkpoint_dates.min():%Y-%m-%d}); there is nothing to reconstruct from"
        )

    slots = checkpoint_dates.searchsorted(dates, side="right") - 1
    universe = sorted(set().union(*(members for _, members in checkpoints)))
    panel = pd.DataFrame(False, index=dates, columns=universe)
    for slot in np.unique(slots):
        members = list(checkpoints[slot][1])
        panel.loc[dates[slots == slot], members] = True

    counts = panel.sum(axis=1)
    bad = counts[(counts < min_members) | (counts > max_members)]
    if len(bad):
        raise MembershipError(
            f"{len(bad)} date(s) have a membership count outside "
            f"[{min_members}, {max_members}], e.g. {bad.index[0]:%Y-%m-%d}: {bad.iloc[0]}"
        )
    return panel
