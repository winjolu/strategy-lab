"""Every property test is checked by deliberately breaking what it covers.

A test that passes against broken code is worse than no test, because it
reads as protection. So each check here is run twice: once against the
real archive, where it must reach a verdict, and once against an archive
mutated to violate exactly the property in question, where it must fail.
"""
import datetime as dt

import pandas as pd
import pytest

from lab.checks import archive_properties as props
from lab.data.archive import default


@pytest.fixture(scope="module")
def archive():
    return default()


class Mutant:
    """A stand-in archive that answers with whatever the test needs broken."""

    def __init__(self, frames=None, master=None, fund=None):
        self.frames = frames or []
        self._master = master
        self._fund = fund

    def frame(self, sql, params=()):
        return self.frames.pop(0) if self.frames else pd.DataFrame()

    def security_master(self, tbl="SEP"):
        return self._master

    def fund_bars(self, tickers=None, start=None, end=None, columns=None):
        return self._fund


# -- the checks reach a verdict on the real archive --------------------

@pytest.mark.parametrize("check", props.ALL_CHECKS,
                         ids=[c.__name__ for c in props.ALL_CHECKS])
def test_each_check_runs_against_the_real_archive(archive, check):
    result = check(archive)
    assert isinstance(result, props.Check)
    assert result.detail, "a verdict without its number is unfalsifiable later"
    assert result.measured is not None


def test_the_permaticker_gap_is_repaired(archive):
    """Failed here from 2026-09-23 (found) to 2026-09-27 (confirmed
    repaired: zero nulls on every month from 2026-01 onward, including bars
    written after the fix, so both the backfill and the recurring write
    were addressed). `docs/defects/permaticker-gap.md` has the incident. If
    this starts failing again, the regression is the news, not this test."""
    result = props.stable_identity(archive)
    assert result.passed
    assert result.measured["recent_null_share"] == 0.0


# -- and fail when the property is violated ----------------------------

def test_freshness_fails_on_a_stale_archive():
    stale = Mutant([pd.DataFrame({"d": ["2026-01-05"]})])
    assert not props.freshness(stale, today="2026-09-23").passed


def test_freshness_passes_over_a_long_weekend():
    """The mutation must not be so crude that the check cries wolf. A job
    that reports a problem every night trains its reader to ignore it."""
    fresh = Mutant([pd.DataFrame({"d": ["2026-09-18"]})])
    assert props.freshness(fresh, today="2026-09-21").passed


def test_bar_sanity_fails_when_a_close_sits_outside_its_own_range():
    broken = Mutant([pd.DataFrame([{
        "bad_close": 0, "inverted": 0, "outside": 3, "bad_volume": 0,
        "total": 1000}])])
    assert not props.bar_sanity(broken).passed


def test_bar_sanity_fails_on_an_inverted_bar():
    broken = Mutant([pd.DataFrame([{
        "bad_close": 0, "inverted": 7, "outside": 0, "bad_volume": 0,
        "total": 1000}])])
    assert not props.bar_sanity(broken).passed


def test_quantised_share_fails_when_the_adjustment_basis_moves():
    """A large move either way means something changed under us."""
    exploded = Mutant([pd.DataFrame([{"floored": 400, "total": 1000}])])
    assert not props.quantised_volume_share(exploded).passed
    vanished = Mutant([pd.DataFrame([{"floored": 0, "total": 1000}])])
    assert not props.quantised_volume_share(vanished).passed


def test_quantised_share_passes_at_the_recorded_level():
    ok = Mutant([pd.DataFrame([{"floored": 603, "total": 10000}])])
    assert props.quantised_volume_share(ok).passed


def test_survivorship_fails_on_a_survivor_only_archive():
    """This is the failure that inverted a result: every name still listed."""
    survivors = Mutant(
        frames=[pd.DataFrame({"ticker": ["A", "B", "C", "D"]})],
        master=pd.DataFrame({"ticker": ["A", "B", "C", "D"],
                             "isdelisted": ["N"] * 4}))
    assert not props.survivorship_coverage(survivors).passed


def test_survivorship_passes_when_the_dead_are_present():
    mixed = Mutant(
        frames=[pd.DataFrame({"ticker": ["A", "B", "C", "D"]})],
        master=pd.DataFrame({"ticker": ["A", "B", "C", "D"],
                             "isdelisted": ["Y", "Y", "N", "N"]}))
    assert props.survivorship_coverage(mixed).passed


def test_stable_identity_passes_when_permaticker_is_populated():
    """Proves the check is measuring the column and not always failing."""
    whole = Mutant([pd.DataFrame([{"nulls": 0, "total": 46_000_000}]),
                    pd.DataFrame([{"nulls": 0, "total": 400_000}])])
    assert props.stable_identity(whole).passed


def test_stable_identity_fails_on_a_recent_gap_a_whole_archive_total_would_hide():
    """0.48% of the archive overall, 100% of the last month. A check that
    looked only at the total would call this healthy."""
    gapped = Mutant([pd.DataFrame([{"nulls": 223_134, "total": 46_476_349}]),
                     pd.DataFrame([{"nulls": 400_000, "total": 400_000}])])
    result = props.stable_identity(gapped)
    assert not result.passed
    assert result.measured["overall_null_share"] < 0.01


def test_benchmarks_fail_when_one_is_missing():
    partial = Mutant(fund=pd.DataFrame({"ticker": ["SPY", "QQQ"]}))
    result = props.benchmarks_present(partial)
    assert not result.passed
    assert "IWM" in result.measured["missing"]


def test_the_report_is_a_storable_record(archive):
    record = props.report(props.run(archive))
    assert set(record) == {"run_at", "passed", "checks"}
    assert len(record["checks"]) == len(props.ALL_CHECKS)
    assert all("measured" in c for c in record["checks"])
