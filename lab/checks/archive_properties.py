"""Property tests the archive must pass before any backtest is believed.

A backtest on a quietly broken archive is worse than no backtest, because
it produces a number rather than an error. Every real failure in this
line of work came from the data being measured wrongly, not from the
statistics being computed wrongly — a t-statistic tests whether a pattern
could arise by chance in correctly-measured data and says nothing about
whether the data was measured correctly.

So these run first, and their result is recorded beside every Stage 1
figure. A run whose property record is missing or failing is not a
result.

Each check returns a `Check` carrying the measured value, not just a
verdict, because "survivorship coverage passed" is unfalsifiable a year
later and "delisted names are 63.4% of the 2010 universe" is not.
"""
import datetime as dt
import json

import pandas as pd

from market_core import sharadar

#: Tables whose archival watermark must be present. Everything here was
#: bulk-loaded at full depth before the entitlement shrank to one year;
#: a missing watermark means an unguarded destructive write is possible.
WATERMARKED = ("prices", "fundprices", "dailyfundamentals", "fundamentals",
               "insiders", "actions", "events", "sp500", "holdings")

#: The archive's own recorded floor share, from the methodology notes:
#: 6.03% of price bars sit on the volume storage floor. A large move
#: either way means the adjustment basis changed under us.
EXPECTED_FLOOR_SHARE = 0.0603
FLOOR_SHARE_TOLERANCE = 0.02

#: How stale the newest equity bar may be before the refresh is suspect,
#: in calendar days. Long weekends and holidays make anything under four
#: a false alarm, and a job that cries wolf nightly gets ignored.
MAX_STALENESS_DAYS = 5

#: A date old enough that most of its universe has since delisted, used
#: to prove the archive is not survivor-only.
SURVIVORSHIP_PROBE = "2010-06-30"
MIN_DELISTED_SHARE = 0.25

#: Benchmarks every report needs. They live in `fundprices`, not
#: `prices`, and a benchmark read from the wrong table comes back empty
#: rather than wrong.
REQUIRED_BENCHMARKS = ("SPY", "IWM", "QQQ", "DIA", "MDY")


class Check:
    """One property, its verdict, and the number behind it."""

    def __init__(self, name, passed, measured, detail):
        self.name = name
        self.passed = bool(passed)
        self.measured = measured
        self.detail = detail

    def __repr__(self):
        mark = "pass" if self.passed else "FAIL"
        return f"[{mark}] {self.name}: {self.detail}"

    def as_dict(self):
        return {"name": self.name, "passed": self.passed,
                "measured": self.measured, "detail": self.detail}


def watermark_integrity(archive):
    """Every bulk-loaded table carries an archival watermark."""
    missing, marks = [], {}
    for table in WATERMARKED:
        mark = sharadar.frozen_before(table)
        marks[table] = mark
        if not mark:
            missing.append(table)
    return Check(
        "watermark_integrity", not missing, marks,
        "every bulk-loaded table is frozen; "
        f"watermark {sorted(set(m for m in marks.values() if m))}"
        if not missing else
        f"no archival watermark on {missing} — a destructive write against "
        f"those tables would not be refused, and the history below it cannot "
        f"be re-downloaded at any price")


def freshness(archive, today=None):
    """The newest equity bar is recent enough that the refresh is running."""
    today = pd.Timestamp(today or dt.date.today())
    newest = archive.frame("SELECT MAX(date) AS d FROM prices")["d"].iloc[0]
    newest = pd.Timestamp(newest)
    lag = (today - newest).days
    return Check(
        "freshness", lag <= MAX_STALENESS_DAYS, {"newest": str(newest.date()),
                                                 "lag_days": lag},
        f"newest equity bar {newest.date()}, {lag} days back"
        + ("" if lag <= MAX_STALENESS_DAYS else
           " — the refresh has stopped, and a lapsed refresh is the real "
           "risk here, since depth accumulates only while the daily top-up "
           "keeps running"))


def bar_sanity(archive):
    """No bar violates the arithmetic every OHLC bar must satisfy."""
    got = archive.frame("""
        SELECT
          SUM(CASE WHEN close IS NULL OR close <= 0 THEN 1 ELSE 0 END) AS bad_close,
          SUM(CASE WHEN high < low THEN 1 ELSE 0 END)                  AS inverted,
          SUM(CASE WHEN close > high OR close < low THEN 1 ELSE 0 END)  AS outside,
          SUM(CASE WHEN volume IS NULL OR volume < 0 THEN 1 ELSE 0 END) AS bad_volume,
          COUNT(*)                                                      AS total
        FROM prices""").iloc[0].to_dict()
    faults = int(got["bad_close"]) + int(got["inverted"]) + int(got["outside"])
    return Check(
        "bar_sanity", faults == 0, got,
        f"{got['total']:,} bars; {faults} violate OHLC arithmetic"
        + ("" if faults == 0 else
           " — a bar whose close sits outside its own range cannot be "
           "filled at, and any simulation touching it is fiction"))


def quantised_volume_share(archive):
    """The share of bars whose volume has bottomed out on the storage floor.

    Split adjustment divides price by the split factor and multiplies
    volume by it, so their product is invariant — right up to the point
    where the multiplied volume falls below one share and rounds up to a
    floor of 1. Then the price keeps its inflated value and the volume
    does not. This measures how much of the archive sits there.
    """
    got = archive.frame("""
        SELECT SUM(CASE WHEN volume IS NULL OR volume <= 1 THEN 1 ELSE 0 END) AS floored,
               COUNT(*) AS total
        FROM prices""").iloc[0]
    share = float(got["floored"]) / float(got["total"])
    drift = abs(share - EXPECTED_FLOOR_SHARE)
    return Check(
        "quantised_volume_share", drift <= FLOOR_SHARE_TOLERANCE,
        {"share": round(share, 5), "expected": EXPECTED_FLOOR_SHARE,
         "floored": int(got["floored"]), "total": int(got["total"])},
        f"{share:.2%} of bars sit on the volume floor "
        f"(expected about {EXPECTED_FLOOR_SHARE:.2%}); dollar volume on those "
        f"names is unmeasurable and market_core.liquidity refuses it rather "
        f"than returning a number")


def survivorship_coverage(archive, probe=SURVIVORSHIP_PROBE):
    """The archive holds companies that have since gone out of business.

    Correcting one survivorship-biased universe took an arm from +11.55%
    over buy-and-hold to −7.80%; the whole apparent edge was companies
    that had stopped existing. This proves they are here to be included.
    """
    traded = archive.frame(
        "SELECT DISTINCT ticker FROM prices WHERE date = ?", (probe,))
    master = archive.security_master("SEP")
    merged = traded.merge(master[["ticker", "isdelisted"]], on="ticker",
                          how="left")
    delisted = (merged["isdelisted"] == "Y").sum()
    share = float(delisted) / max(len(merged), 1)
    return Check(
        "survivorship_coverage", share >= MIN_DELISTED_SHARE,
        {"probe": probe, "names": int(len(merged)),
         "delisted": int(delisted), "share": round(share, 4)},
        f"{len(merged):,} names traded on {probe}; {share:.1%} have since "
        f"delisted and are still in the archive")


def stable_identity(archive):
    """`permaticker` is populated, since it is the only stable company id.

    A ticker is rewritten retroactively by the vendor after a rename, so
    anything keyed on ticker silently follows the wrong company across a
    rename. `permaticker` is the fix — where it is present.
    """
    got = archive.frame("""
        SELECT SUM(CASE WHEN permaticker IS NULL THEN 1 ELSE 0 END) AS nulls,
               COUNT(*) AS total
        FROM prices""").iloc[0]
    share = float(got["nulls"]) / float(got["total"])
    recent = archive.frame("""
        SELECT SUM(CASE WHEN permaticker IS NULL THEN 1 ELSE 0 END) AS nulls,
               COUNT(*) AS total
        FROM prices WHERE date >= date('now', '-90 day')""").iloc[0]
    recent_share = (float(recent["nulls"]) / float(recent["total"])
                    if float(recent["total"]) else 0.0)
    return Check(
        "stable_identity", recent_share <= 0.01,
        {"overall_null_share": round(share, 5),
         "recent_null_share": round(recent_share, 5),
         "recent_rows": int(recent["total"])},
        f"permaticker is null on {recent_share:.1%} of the last 90 days of "
        f"bars ({share:.2%} of the archive overall)"
        + ("" if recent_share <= 0.01 else
           " — the incremental refresh appends bars without it, because the "
           "vendor's price endpoint does not carry the column and the bulk "
           "loader joined it from `tickers` at load time. Identity joins in "
           "the current-regime window must go through `tickers` by ticker "
           "until the archive is repaired"))


def benchmarks_present(archive):
    """Every benchmark a report needs is in `fundprices` and current."""
    found = archive.fund_bars(list(REQUIRED_BENCHMARKS),
                              start="2026-01-01")
    have = set(found["ticker"].unique()) if not found.empty else set()
    missing = sorted(set(REQUIRED_BENCHMARKS) - have)
    return Check(
        "benchmarks_present", not missing,
        {"present": sorted(have), "missing": missing},
        f"benchmarks available: {sorted(have)}"
        + ("" if not missing else
           f"; missing {missing} — a benchmark read from `prices` instead of "
           f"`fundprices` comes back empty rather than wrong, which is the "
           f"one mercy in this schema"))


ALL_CHECKS = (watermark_integrity, freshness, bar_sanity,
              quantised_volume_share, survivorship_coverage,
              stable_identity, benchmarks_present)


def run(archive=None, checks=ALL_CHECKS):
    """Run every property test and return the results."""
    if archive is None:
        from lab.data.archive import default
        archive = default()
    return [check(archive) for check in checks]


def report(results):
    """A record fit to store beside a Stage 1 figure."""
    return {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "passed": all(r.passed for r in results),
        "checks": [r.as_dict() for r in results],
    }


def main():
    results = run()
    for r in results:
        print(r)
    record = report(results)
    print("\nOVERALL:", "pass" if record["passed"] else "FAIL")
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
