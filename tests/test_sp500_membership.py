"""Point-in-time S&P 500 membership: reconstruction from event history,
against synthetic events, plus one check against the real archive."""
import pandas as pd
import pytest

from lab.data import sp500_membership as sp


def ev(rows):
    """rows of (date, action, ticker) -> the frame `sp500_events` returns."""
    return pd.DataFrame(rows, columns=["date", "action", "ticker"]).assign(
        date=lambda f: pd.to_datetime(f["date"]))


HISTORY = ev([
    ("2020-01-01", "historical", "A"),
    ("2020-01-01", "historical", "B"),
    ("2020-01-01", "historical", "C"),
    ("2020-02-01", "added", "D"),
    ("2020-02-01", "removed", "A"),
    ("2020-04-01", "historical", "B"),
    ("2020-04-01", "historical", "C"),
    ("2020-04-01", "historical", "D"),
])


def test_membership_before_any_change_is_the_first_snapshot():
    panel = sp.membership_panel(None, ["2020-01-15"], events=HISTORY, min_members=0, max_members=10)
    row = panel.loc[pd.Timestamp("2020-01-15")]
    assert row["A"] and row["B"] and row["C"] and not row["D"]


def test_an_added_removed_pair_between_snapshots_is_applied():
    panel = sp.membership_panel(None, ["2020-02-15"], events=HISTORY, min_members=0, max_members=10)
    row = panel.loc[pd.Timestamp("2020-02-15")]
    assert row["D"] and row["B"] and row["C"] and not row["A"]


def test_a_later_quarterly_snapshot_replaces_the_running_set_outright():
    """Reconstructing on the same day as a fresh 'historical' row must
    match that row exactly, even if incremental drift would have said
    otherwise."""
    panel = sp.membership_panel(None, ["2020-04-01"], events=HISTORY, min_members=0, max_members=10)
    row = panel.loc[pd.Timestamp("2020-04-01")]
    assert row["B"] and row["C"] and row["D"] and not row["A"]


def test_membership_as_of_a_change_date_is_inclusive_of_that_change():
    panel = sp.membership_panel(None, ["2020-02-01"], events=HISTORY, min_members=0, max_members=10)
    row = panel.loc[pd.Timestamp("2020-02-01")]
    assert row["D"] and not row["A"]


def test_a_date_before_the_first_snapshot_is_refused():
    with pytest.raises(sp.MembershipError, match="nothing to reconstruct"):
        sp.membership_panel(None, ["2019-12-01"], events=HISTORY, min_members=0, max_members=10)


def test_membership_is_correct_across_a_span_of_dates():
    panel = sp.membership_panel(None, ["2020-01-15", "2020-02-15", "2020-04-15"],
                                events=HISTORY, min_members=0, max_members=10)
    assert panel.loc[pd.Timestamp("2020-01-15")].sum() == 3
    assert panel.loc[pd.Timestamp("2020-02-15")].sum() == 3
    assert panel.loc[pd.Timestamp("2020-04-15")].sum() == 3
    assert not panel.loc[pd.Timestamp("2020-04-15"), "A"]


def test_duplicate_requested_dates_do_not_duplicate_rows():
    panel = sp.membership_panel(None, ["2020-01-15", "2020-01-15"], events=HISTORY,
                                min_members=0, max_members=10)
    assert len(panel) == 1


def test_a_count_outside_the_plausible_band_is_refused():
    huge = pd.concat([HISTORY, ev([("2020-01-01", "historical", f"X{i}")
                                   for i in range(600)])], ignore_index=True)
    with pytest.raises(sp.MembershipError, match="outside"):
        sp.membership_panel(None, ["2020-01-15"], events=huge)


def test_no_events_at_all_is_refused():
    with pytest.raises(sp.MembershipError, match="no membership events"):
        sp.membership_panel(None, ["2020-01-15"], events=ev([]), min_members=0, max_members=10)


def test_current_rows_are_never_read():
    """'current' is a daily snapshot mechanism this module deliberately
    does not trust. A 'current' row that is neither 'historical' nor
    'added' would fall into the 'removed' branch if it were processed at
    all, so a 'current' row naming an existing member (B) is the case
    that actually detects a leak: read it and B silently disappears."""
    with_current = pd.concat([HISTORY, ev([("2020-01-15", "current", "B")])],
                             ignore_index=True)
    panel = sp.membership_panel(None, ["2020-01-15"], events=with_current,
                                min_members=0, max_members=10)
    assert panel.loc[pd.Timestamp("2020-01-15"), "B"]


def test_an_empty_date_list_is_refused():
    with pytest.raises(sp.MembershipError, match="no dates requested"):
        sp.membership_panel(None, [], events=HISTORY, min_members=0, max_members=10)


def test_reconstruction_agrees_with_every_real_quarterly_snapshot():
    """The strongest check available: every quarter since 1998-03-31 has an
    independent, authoritative snapshot in the archive. Reconstructing
    membership as of each one, from the events alone, must reproduce it
    exactly — not approximately."""
    from lab.data.archive import default
    archive = default()
    events = archive.sp500_events(end="2024-12-31")
    snapshots = events[events["action"] == "historical"]
    quarters = sorted(snapshots["date"].unique())[::8]  # every other year is plenty
    panel = sp.membership_panel(archive, quarters, events=events)
    checked = 0
    for q in quarters:
        actual = set(snapshots.loc[snapshots["date"] == q, "ticker"])
        reconstructed = set(panel.columns[panel.loc[q].to_numpy()])
        assert reconstructed == actual, q
        checked += 1
    assert checked >= 3
