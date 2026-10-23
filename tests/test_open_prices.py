import numpy as np
import pandas as pd
import pytest

from lab.checks import open_prices as op


def frame(ticker="SPY", n=600, start="2020-01-02", scale=1.0, drop=(), bump=None):
    idx = pd.bdate_range(start, periods=n)
    opens = 100 + np.arange(n) * 0.1
    df = pd.DataFrame({"ticker": ticker, "date": idx, "open": opens * scale})
    if bump:
        for d, f in bump.items():
            df.loc[df["date"] == pd.Timestamp(d), "open"] *= f
    return df[~df["date"].isin(pd.DatetimeIndex(drop))].reset_index(drop=True)


def test_identical_sources_pass():
    a = frame()
    (r,) = op.run(a, a.copy(), ["SPY"], "2020-01-01", "2022-12-31")
    assert r.passed and r.disagree == 0 and r.unpriced == 0 and r.sampled == 250


def test_a_systematic_offset_beyond_the_tolerance_fails():
    a = frame()
    (r,) = op.run(a, frame(scale=1.002), ["SPY"], "2020-01-01", "2022-12-31")
    assert not r.passed and r.disagree == 250


def test_an_offset_inside_the_tolerance_passes():
    a = frame()
    (r,) = op.run(a, frame(scale=1.0005), ["SPY"], "2020-01-01", "2022-12-31")
    assert r.passed


def test_dates_the_second_source_cannot_price_count_against_it():
    a = frame()
    dates = op.sample_dates(a, "SPY", "2020-01-01", "2022-12-31")
    b = frame(drop=dates[:5])          # 2% of the sample unpriced
    (r,) = op.run(a, b, ["SPY"], "2020-01-01", "2022-12-31")
    assert r.unpriced == 5 and not r.passed


def test_a_few_disagreements_up_to_one_percent_pass_and_beyond_it_fail():
    a = frame()
    dates = op.sample_dates(a, "SPY", "2020-01-01", "2022-12-31")
    ok = op.compare(a, frame(bump={d: 1.01 for d in dates[:2]}), "SPY", dates)
    bad = op.compare(a, frame(bump={d: 1.01 for d in dates[:3]}), "SPY", dates)
    assert ok.disagree == 2 and ok.passed          # 0.8%
    assert bad.disagree == 3 and not bad.passed    # 1.2%


def test_the_sample_is_reproducible_distinct_and_inside_the_window():
    a = frame()
    d1 = op.sample_dates(a, "SPY", "2020-06-01", "2021-12-31")
    d2 = op.sample_dates(a, "SPY", "2020-06-01", "2021-12-31")
    assert d1.equals(d2) and not d1.has_duplicates
    assert d1.min() >= pd.Timestamp("2020-06-01") and d1.max() <= pd.Timestamp("2021-12-31")


def test_too_few_archive_dates_is_refused_not_sampled_short():
    with pytest.raises(ValueError, match="needs 250"):
        op.sample_dates(frame(n=100), "SPY", "2020-01-01", "2022-12-31")


def test_every_ticker_must_pass():
    a = pd.concat([frame("SPY"), frame("QQQ")])
    b = pd.concat([frame("SPY"), frame("QQQ", scale=1.01)])
    rs = op.run(a, b, ["SPY", "QQQ"], "2020-01-01", "2022-12-31")
    assert [r.passed for r in rs] == [True, False]


def test_duplicate_opens_are_refused():
    a = frame()
    with pytest.raises(ValueError, match="more than one open"):
        op.compare(a, pd.concat([a, a.iloc[:1]]), "SPY", pd.DatetimeIndex([a["date"].iloc[0]]))
