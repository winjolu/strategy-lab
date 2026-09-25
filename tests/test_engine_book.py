"""The book-returns series: built from synthetic bars, no archive access,
plus one read-only look at the real archive."""
import os
from datetime import date

import numpy as np
import pandas as pd
import pytest

from lab.engine import book, pipeline, report
from tests import engine_fixtures as fx

HOLDINGS = '''as_of = "{as_of}"
source = "test"
{rows}
'''
ROW = '''[[holding]]
symbol = "{s}"
table = "{t}"
market_value = {v}
'''


class FakeArchive:
    def __init__(self, prices, funds):
        self._p, self._f = prices, funds

    @staticmethod
    def _long(wide, names):
        f = wide[[n for n in names if n in wide]].copy()
        f.index.name = "date"
        f = f.reset_index().melt("date", var_name="ticker", value_name="closeadj")
        f["date"] = f["date"].dt.strftime("%Y-%m-%d")
        return f.dropna(subset=["closeadj"])

    def bars(self, tickers, end=None, columns=None):
        return self._long(self._p, tickers)

    def fund_bars(self, tickers, end=None, columns=None):
        return self._long(self._f, tickers)


def holdings_file(tmp_path, rows, as_of="2026-06-01"):
    text = HOLDINGS.format(as_of=as_of, rows="\n".join(ROW.format(s=s, t=t, v=v) for s, t, v in rows))
    path = tmp_path / "h.toml"
    path.write_text(text)
    return str(path)


def closes(days=200, seed=3, names=("A", "B"), start="2024-01-02"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=days)
    return pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, (days, len(names))), axis=0)), idx, list(names))


def test_weights_are_market_value_shares(tmp_path):
    p = closes()
    b = book.build(FakeArchive(p[["A"]], p[["B"]]),
                   holdings_file(tmp_path, [("A", "prices", 300), ("B", "fundprices", 100)]))
    assert b.weights == pytest.approx({"A": 0.75, "B": 0.25})


def test_return_is_the_weighted_sum_of_daily_returns(tmp_path):
    p = closes()
    b = book.build(FakeArchive(p[["A"]], p[["B"]]),
                   holdings_file(tmp_path, [("A", "prices", 300), ("B", "fundprices", 100)]))
    expected = 0.75 * p["A"].pct_change() + 0.25 * p["B"].pct_change()
    pd.testing.assert_series_equal(b.returns, expected.iloc[1:], check_names=False, check_freq=False)


def test_series_starts_when_the_newest_listing_does(tmp_path):
    p = closes()
    p.loc[p.index[:50], "B"] = np.nan
    b = book.build(FakeArchive(p[["A"]], p[["B"]]),
                   holdings_file(tmp_path, [("A", "prices", 1), ("B", "fundprices", 1)]))
    assert b.first_date == p.index[51]
    assert b.returns.notna().all()


def test_a_gap_after_every_name_has_started_raises(tmp_path):
    p = closes()
    p.loc[p.index[80], "B"] = np.nan
    with pytest.raises(book.MissingBars, match="B"):
        book.build(FakeArchive(p[["A"]], p[["B"]]),
                   holdings_file(tmp_path, [("A", "prices", 1), ("B", "fundprices", 1)]))


def test_a_name_with_no_bars_raises(tmp_path):
    p = closes()
    with pytest.raises(book.BookError, match="no bars"):
        book.build(FakeArchive(p[["A"]], p[["B"]]),
                   holdings_file(tmp_path, [("A", "prices", 1), ("Z", "fundprices", 1)]))


def test_a_name_whose_bars_are_all_null_raises(tmp_path):
    p = closes()

    class Nulls(FakeArchive):
        def fund_bars(self, tickers, end=None, columns=None):
            f = super().fund_bars(["B"])
            z = f.copy()
            z["ticker"], z["closeadj"] = "Z", np.nan
            return pd.concat([f, z])

    with pytest.raises(book.BookError, match="Z has no bars"):
        book.build(Nulls(p[["A"]], p[["B"]]),
                   holdings_file(tmp_path, [("A", "prices", 1), ("Z", "fundprices", 1)]))


def test_duplicate_bars_raise(tmp_path):
    p = closes()

    class Dup(FakeArchive):
        def bars(self, tickers, end=None, columns=None):
            f = super().bars(tickers)
            return pd.concat([f, f.iloc[:1]])

    with pytest.raises(book.BookError, match="more than one bar"):
        book.build(Dup(p[["A"]], p[["B"]]),
                   holdings_file(tmp_path, [("A", "prices", 1), ("B", "fundprices", 1)]))


@pytest.mark.parametrize("rows,msg", [
    ([], "no holdings"),
    ([("A", "stocks", 1)], "table must be"),
    ([("A", "prices", 0)], "positive"),
    ([("A", "prices", 1), ("A", "prices", 2)], "twice"),
])
def test_bad_holdings_are_refused(tmp_path, rows, msg):
    with pytest.raises(book.BookError, match=msg):
        book.load_holdings(holdings_file(tmp_path, rows))


def test_missing_as_of_is_refused(tmp_path):
    path = tmp_path / "h.toml"
    path.write_text(ROW.format(s="A", t="prices", v=1))
    with pytest.raises(book.BookError, match="as_of"):
        book.load_holdings(str(path))


def _book(tmp_path):
    p = closes()
    return book.build(FakeArchive(p[["A"]], p[["B"]]),
                      holdings_file(tmp_path, [("A", "prices", 1), ("B", "fundprices", 1)], as_of="2026-06-01"))


def test_staleness_is_reported_past_the_limit(tmp_path):
    b = _book(tmp_path)
    assert not b.staleness(date(2026, 6, 1) + pd.Timedelta(days=book.STALE_AFTER_DAYS))["stale"]
    late = date(2026, 6, 1) + pd.Timedelta(days=book.STALE_AFTER_DAYS + 1)
    assert b.staleness(late)["stale"]
    assert "STALE" in b.note(late)
    assert "STALE" not in b.note(date(2026, 6, 2))


def test_report_carries_the_book_note_and_correlation(tmp_path):
    ret, bench = fx.panel()
    reg = str(tmp_path / "reg")
    import os
    os.makedirs(reg)
    fx.write_registration(reg, holdout="2030-01-01")
    w = {k: pd.DataFrame(1.0 / ret.shape[1], ret.index, ret.columns) for k in ("equal_weight", "inverse_vol")}
    bk = book.Book(bench * 0.9 + 0.001, {"A": 1.0}, date(2026, 1, 1), bench.index[0], bench.index[-1])
    ev = pipeline.evaluate("toy", w, ret, bench, fx.fresh_db(), "m", "medium", "manifest",
                           "settlement", _cost(), book=bk, registry_directory=reg, today=date(2026, 6, 1))
    text = report.render(ev)
    assert "Book series: 1 holdings as of 2026-01-01" in text
    assert "STALE" in text
    assert "To the current book: +" in text


def _cost():
    from lab.engine.costs import CostModel
    return CostModel(slippage_pct=0.25, commission_bps=0.0, borrow_apr=0.08, margin_apr=0.0)


@pytest.mark.skipif(not os.path.exists(book.HOLDINGS_PATH), reason="no local holdings file")
def test_the_real_holdings_build_from_the_real_archive():
    from lab.data.archive import Archive
    b = book.build(Archive())
    assert sum(b.weights.values()) == pytest.approx(1.0)
    assert b.returns.notna().all() and b.returns.abs().max() < 0.25


def test_a_missing_holdings_file_is_refused_and_the_example_is_not_a_fallback(tmp_path):
    with pytest.raises(book.BookError, match="holdings.example.toml"):
        book.load_holdings(str(tmp_path / "absent.toml"))


def test_the_committed_example_parses():
    as_of, rows = book.load_holdings(book.EXAMPLE_PATH)
    assert len(rows) >= 2 and as_of.year >= 2026
