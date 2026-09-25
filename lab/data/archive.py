"""The only place this lab talks to the market archive.

The archive is a 19.7 GB SQLite file today and becomes Postgres served
from a Linux machine later. Every strategy therefore asks *this* module
for frames and never opens a connection itself, so the migration changes
one file rather than forty. No `sqlite3` call and no connection string
appears above this layer.

Reads only, always. The file is chmod 444 between refresh runs and has
exactly one writer, the scheduled job in `~/market-data/market-archive`.
Opening read-write against a locked file happens to work for a plain
SELECT, which is worse than failing, so the open goes through
`market_core.sharadar.connect_ro` rather than being rewritten here.

Three things about this vendor's schema that a caller would otherwise
have to rediscover, and one of which silently empties a universe:

* `tickers` holds one row per security *per source table*, keyed by the
  `tbl` column. Equity bars are `SEP`, fund and ETF bars are `SFP`.
  Selecting without a `tbl` filter returns a name up to five times.
* `tickers.lastpricedate` is not refreshed daily. It maxed at 2026-08-03
  when `prices` already reached 2026-09-22. A membership rule written as
  `firstpricedate <= d <= lastpricedate` therefore drops every live name
  for the most recent seven weeks — which is exactly the window the
  current-regime tests run in. Membership is built from bar presence
  instead; see `lab.data.universe`.
* `dailyfundamentals.marketcap` is stored as TEXT and denominated in
  millions. It is the vendor's own figure computed from raw price and
  raw shares, and it is correct. Market cap is never derived from the
  adjusted close, which would read a $33.6M company as $29bn.
"""
import os
import re

import pandas as pd

from market_core import sharadar

#: Chunk size for `ticker IN (...)`. SQLite's compiled variable limit is
#: 999 on older builds, and a query that exceeds it fails at execute time
#: rather than at build time, so the chunking is not optional.
_MAX_BIND = 900

#: Columns that are dates in the archive, whatever the table.
_DATE_COLUMNS = {
    "date", "datekey", "calendardate", "reportperiod", "filingdate",
    "transactiondate", "firstpricedate", "lastpricedate", "lastupdated",
    "dateexercisable", "expirationdate",
}

#: Columns stored as TEXT that are numbers. The vendor stores several
#: this way; comparing them as strings sorts "9" above "10".
_NUMERIC_TEXT = {
    "marketcap", "ev", "evebit", "evebitda", "pb", "pe", "ps",
}


class ReadOnlyViolation(RuntimeError):
    """A statement that is not a read reached the archive layer."""


_WRITE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|vacuum|pragma)\b",
    re.IGNORECASE,
)


class Backend:
    """A source of frames. One implementation per storage engine."""

    #: The parameter marker this engine wants. SQLite takes `?`,
    #: Postgres takes `%s`. Queries above this layer are written with
    #: `?` and rendered here.
    placeholder = "?"

    def frame(self, sql, params=()):
        raise NotImplementedError

    def close(self):
        pass


class SQLiteBackend(Backend):
    """The archive as it stands: one large local file, opened read-only."""

    placeholder = "?"

    def __init__(self, path):
        self.path = path
        self._conn = None

    def connect(self):
        if self._conn is None:
            self._conn = sharadar.connect_ro(self.path)
        return self._conn

    def frame(self, sql, params=()):
        if _WRITE.search(sql):
            raise ReadOnlyViolation(
                "this layer reads; the archive has exactly one writer and it "
                "is not this process"
            )
        return pd.read_sql_query(sql, self.connect(), params=tuple(params))

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class PostgresBackend(Backend):
    """The archive after the migration. Deliberately unimplemented.

    It exists so the seam is visible and so the placeholder difference is
    written down somewhere other than a migration ticket. Filling this in
    should be the whole of the move.
    """

    placeholder = "%s"

    def __init__(self, dsn):
        self.dsn = dsn

    def frame(self, sql, params=()):
        raise NotImplementedError(
            "the archive has not moved to Postgres yet; when it does, this "
            "method and the placeholder above are the whole change"
        )


def backend_for(url):
    """Build the backend named by a connection URL."""
    if url.startswith("sqlite:///"):
        return SQLiteBackend(os.path.expanduser(url[len("sqlite:///"):]))
    if url.startswith(("postgresql://", "postgres://")):
        return PostgresBackend(url)
    raise ValueError(f"unrecognised archive URL: {url!r}")


def _typed(frame):
    """Parse dates and coerce the numbers the vendor stores as text."""
    for column in frame.columns:
        if column in _DATE_COLUMNS:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
        elif column in _NUMERIC_TEXT:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


class Archive:
    """Frames out of the market archive, by table, universe and date range."""

    def __init__(self, url=None, backend=None):
        if backend is None:
            from lab import config
            backend = backend_for(url or config.ARCHIVE_URL)
        self.backend = backend

    # -- the escape hatch -------------------------------------------------

    def frame(self, sql, params=()):
        """Run a read and return a frame.

        Here for the query a typed accessor does not cover. It is still
        inside this module's blast radius, so the migration still touches
        one file — but a caller using it has written engine-specific SQL
        and owns that.
        """
        return _typed(self.backend.frame(sql, params))

    # -- bars -------------------------------------------------------------

    def bars(self, tickers=None, start=None, end=None, columns=None):
        """Daily US equity bars from `prices`.

        `close` is split-adjusted; `closeadj` adds dividends. Carries
        `permaticker`, which is the only stable company identity — a
        ticker is rewritten by the vendor after a rename, and the
        rewrite is retroactive across the whole history.
        """
        return self._bars("prices", tickers, start, end, columns)

    def fund_bars(self, tickers=None, start=None, end=None, columns=None):
        """Daily ETF and fund bars from `fundprices`.

        Every benchmark lives here, not in `prices`. A benchmark read
        from the wrong table comes back empty rather than wrong, which
        is the one mercy in this schema.
        """
        return self._bars("fundprices", tickers, start, end, columns)

    def _bars(self, table, tickers, start, end, columns):
        default = ["ticker", "date", "open", "high", "low", "close",
                   "closeadj", "volume"]
        if table == "prices":
            default.insert(0, "permaticker")
        select = ", ".join(columns or default)
        return self._select(table, select, "date", tickers, start, end)

    # -- fundamentals -----------------------------------------------------

    def daily_fundamentals(self, tickers=None, start=None, end=None,
                           columns=None):
        """Daily market cap, EV and ratios. Starts 2016-01-04.

        That start date is the binding constraint on every
        market-cap-conditioned study in this lab, and it is eighteen
        years shorter than the price history. A design that conditions on
        size silently becomes a 2016-onwards design.
        """
        select = ", ".join(
            columns or ["ticker", "date", "marketcap", "ev", "pb", "pe", "ps"])
        return self._select("dailyfundamentals", select, "date",
                            tickers, start, end)

    def fundamentals(self, tickers=None, start=None, end=None, columns=None):
        """Quarterly financials, keyed on `datekey`.

        `datekey` is the filing date and is the only column a
        point-in-time read may use. `calendardate` is the period the
        numbers describe, and a company filing six months late carries an
        old `calendardate` with a new `datekey` — filtering on the former
        reads the future.
        """
        select = ", ".join(columns) if columns else "*"
        return self._select("fundamentals", select, "datekey",
                            tickers, start, end)

    # -- events -----------------------------------------------------------

    def insiders(self, tickers=None, start=None, end=None, columns=None):
        """SEC Form 4 transactions, keyed on `filingdate`. Starts 2008-01-02.

        `filingdate` is the only usable event date. A filing can post as
        late as 10 p.m. and still carry that date, so an entry at that
        day's close is reading information a trader could not have had:
        moving entry one day later took one study from +1.32% to +0.47%.
        """
        select = ", ".join(columns) if columns else "*"
        return self._select("insiders", select, "filingdate",
                            tickers, start, end)

    def actions(self, tickers=None, start=None, end=None):
        """Splits, dividends and ticker changes."""
        return self._select(
            "actions", "date, action, ticker, name, value, contraticker, "
            "contraname", "date", tickers, start, end)

    def events(self, tickers=None, start=None, end=None):
        """Corporate event codes. Starts 1993-11-08, before the price data."""
        return self._select("events", "ticker, date, eventcodes", "date",
                            tickers, start, end)

    # -- reference --------------------------------------------------------

    def security_master(self, tbl="SEP"):
        """One row per security from `tickers`, for a single source table.

        `tbl` is not optional in practice. The table holds one row per
        security per source table — SEP for equity bars, SFP for fund and
        ETF bars, SF1/SF2/SF3B for the fundamental, insider and holdings
        coverage — and an unfiltered select returns a name up to five
        times over.

        Use this for attributes. Do not use `lastpricedate` to decide
        whether a name was trading on a date; it is weeks stale. See the
        module docstring.
        """
        marker = self.backend.placeholder
        return self.frame(
            "SELECT tbl, permaticker, ticker, name, exchange, isdelisted, "
            "category, sector, industry, scalemarketcap, location, "
            f"firstpricedate, lastpricedate FROM tickers WHERE tbl = {marker}",
            (tbl,),
        )

    def sp500_events(self, start=None, end=None):
        """Index membership changes. Reaches back to 1957, long before prices."""
        return self._select("sp500", "date, action, ticker, name, "
                            "contraticker, contraname", "date",
                            None, start, end)

    def trading_days(self, start=None, end=None):
        """Distinct dates on which the archive holds equity bars.

        The calendar every backtest steps through. Taken from the data
        rather than from a holiday library, so a day the archive is
        missing cannot be mistaken for a day the market was open.
        """
        marker = self.backend.placeholder
        where, params = [], []
        if start is not None:
            where.append(f"date >= {marker}")
            params.append(str(start))
        if end is not None:
            where.append(f"date <= {marker}")
            params.append(str(end))
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        got = self.frame(
            f"SELECT DISTINCT date FROM prices{clause} ORDER BY date", params)
        return got["date"]

    # -- shared query construction ---------------------------------------

    def _select(self, table, select, date_column, tickers, start, end):
        marker = self.backend.placeholder
        where, params = [], []
        if start is not None:
            where.append(f"{date_column} >= {marker}")
            params.append(str(start))
        if end is not None:
            where.append(f"{date_column} <= {marker}")
            params.append(str(end))

        if tickers is None:
            clause = (" WHERE " + " AND ".join(where)) if where else ""
            return self.frame(f"SELECT {select} FROM {table}{clause}", params)

        tickers = list(dict.fromkeys(tickers))
        if not tickers:
            # An empty universe is a legitimate result of a filter, not an
            # error — but `IN ()` is a syntax error, so it is answered with
            # an empty frame carrying the right columns.
            clause = (" WHERE " + " AND ".join(where + ["1 = 0"]))
            return self.frame(f"SELECT {select} FROM {table}{clause}", params)

        parts = []
        for i in range(0, len(tickers), _MAX_BIND):
            chunk = tickers[i:i + _MAX_BIND]
            marks = ", ".join([marker] * len(chunk))
            clause = " WHERE " + " AND ".join(where + [f"ticker IN ({marks})"])
            parts.append(self.frame(
                f"SELECT {select} FROM {table}{clause}", params + list(chunk)))
        return pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]

    def close(self):
        self.backend.close()


_default = None


def default():
    """The process-wide archive handle."""
    global _default
    if _default is None:
        _default = Archive()
    return _default
