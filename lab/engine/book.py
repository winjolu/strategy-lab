"""A daily return series for the book as it is held today.

Every Stage 1 report carries a strategy's correlation to the existing book,
because a stream that is the index in disguise adds nothing however good its
Sharpe. This builds that series.

What it is, and is not:

* Weights are today's market values over the invested total, held constant
  and rebalanced daily. Cash is excluded; a constant zero-return asset
  changes no correlation.
* It applies today's holdings to the whole past. That is deliberate, since
  the question is how a candidate relates to what is held now, but it is
  hindsight, and the series is not a record of what the account earned.
* Returns come from `closeadj`, which includes dividends, read in one query
  per table so every name shares one adjustment vintage.
* The series starts on the first day every holding has a bar, so the newest
  listing sets the start. A holding with a gap after that raises rather than
  being filled; renormalising over the names present would quietly change
  the book from day to day.
* It is dated. The holdings age, and a correlation to a book that has since
  moved is a correlation to something else, so `staleness` reports the age
  and the report prints a warning past `STALE_AFTER_DAYS`.
"""
import os
import tomllib
from dataclasses import dataclass
from datetime import date

import pandas as pd

HOLDINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "book", "holdings.toml")
EXAMPLE_PATH = HOLDINGS_PATH.replace("holdings.toml", "holdings.example.toml")
STALE_AFTER_DAYS = 30
TABLES = ("prices", "fundprices")


class BookError(ValueError):
    """The holdings file or the archive bars cannot support a book series."""


class MissingBars(BookError):
    """A holding has no bar on a day it must have one."""


@dataclass
class Book:
    returns: pd.Series
    weights: dict
    as_of: date
    first_date: pd.Timestamp
    last_date: pd.Timestamp

    def staleness(self, today=None):
        """Days the holdings are older than `today`, and days the return
        series ends before it. Both matter: old holdings and old prices are
        different ways for the number to be out of date."""
        today = today or date.today()
        return {"holdings_age_days": (today - self.as_of).days,
                "series_lag_days": (pd.Timestamp(today) - self.last_date).days,
                "stale": (today - self.as_of).days > STALE_AFTER_DAYS}

    def note(self, today=None):
        s = self.staleness(today)
        text = (f"Book series: {len(self.weights)} holdings as of {self.as_of}, "
                f"{self.first_date:%Y-%m-%d} to {self.last_date:%Y-%m-%d}, constant weights "
                f"rebalanced daily (today's holdings applied to the past).")
        if s["stale"]:
            text += (f" **STALE: holdings are {s['holdings_age_days']} days old "
                     f"(limit {STALE_AFTER_DAYS}); the correlation is to a book that has since moved.**")
        return text


def load_holdings(path=None):
    path = path or HOLDINGS_PATH
    if not os.path.exists(path):
        raise BookError(f"{path} does not exist; copy book/holdings.example.toml to book/holdings.toml "
                        "and fill in the real holdings. It is not committed, and the example is never "
                        "used as a fallback, since a correlation to a made-up book would look real.")
    with open(path, "rb") as handle:
        raw = tomllib.load(handle)
    rows = raw.get("holding", [])
    if not rows:
        raise BookError("no holdings listed")
    seen = set()
    for r in rows:
        if r.get("table") not in TABLES:
            raise BookError(f"{r.get('symbol')}: table must be one of {TABLES}")
        if not r.get("market_value", 0) > 0:
            raise BookError(f"{r.get('symbol')}: market_value must be positive")
        if r["symbol"] in seen:
            raise BookError(f"{r['symbol']} listed twice")
        seen.add(r["symbol"])
    try:
        as_of = date.fromisoformat(str(raw["as_of"]))
    except (KeyError, ValueError) as exc:
        raise BookError("as_of is required and must be an ISO date") from exc
    return as_of, rows


def build(archive, path=None, end=None):
    as_of, rows = load_holdings(path)
    total = sum(r["market_value"] for r in rows)
    weights = {r["symbol"]: r["market_value"] / total for r in rows}

    closes = {}
    for table, fetch in (("prices", archive.bars), ("fundprices", archive.fund_bars)):
        names = [r["symbol"] for r in rows if r["table"] == table]
        if not names:
            continue
        frame = fetch(names, end=end, columns=["ticker", "date", "closeadj"])
        if frame.duplicated(["ticker", "date"]).any():
            raise BookError(f"more than one bar per ticker per day in {table}")
        wide = frame.pivot(index="date", columns="ticker", values="closeadj")
        for name in names:
            if name not in wide or wide[name].dropna().empty:
                raise BookError(f"{name} has no bars in {table}")
            closes[name] = wide[name]

    prices = pd.DataFrame(closes).sort_index()
    prices.index = pd.to_datetime(prices.index)
    first = prices.apply(lambda s: s.first_valid_index()).max()
    window = prices.loc[first:]
    gaps = window.isna()
    if gaps.any().any():
        name = gaps.any().idxmax()
        raise MissingBars(f"{name} has no bar on {gaps[name].idxmax():%Y-%m-%d}, after every holding had started")
    rets = window.pct_change(fill_method=None).iloc[1:]
    series = sum(rets[name] * w for name, w in weights.items())
    series.name = "BOOK"
    return Book(series, weights, as_of, series.index[0], series.index[-1])
