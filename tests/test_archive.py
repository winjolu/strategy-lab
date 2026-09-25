"""The data layer reads, refuses to write, and types what it returns."""
import pandas as pd
import pytest

from lab.data import archive as arch


class FakeBackend(arch.Backend):
    """Records the SQL it is handed and answers with a fixed frame."""

    placeholder = "?"

    def __init__(self, frame=None):
        self.calls = []
        self._frame = frame if frame is not None else pd.DataFrame()

    def frame(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        return self._frame.copy()


def test_backend_for_recognises_sqlite_and_postgres():
    assert isinstance(arch.backend_for("sqlite:////tmp/x.db"), arch.SQLiteBackend)
    assert isinstance(arch.backend_for("postgresql://h/db"), arch.PostgresBackend)
    with pytest.raises(ValueError):
        arch.backend_for("mysql://h/db")


def test_postgres_backend_is_an_honest_stub():
    """It must fail loudly rather than return an empty frame."""
    with pytest.raises(NotImplementedError):
        arch.PostgresBackend("postgresql://h/db").frame("SELECT 1")


@pytest.mark.parametrize("statement", [
    "INSERT INTO prices VALUES (1)",
    "delete from prices",
    "DROP TABLE prices",
    "UPDATE prices SET close = 0",
    "SELECT 1; DROP TABLE prices",
])
def test_writes_are_refused(statement):
    """The archive has one writer and it is not this process."""
    backend = arch.SQLiteBackend("/nonexistent.db")
    with pytest.raises(arch.ReadOnlyViolation):
        backend.frame(statement)


def test_a_plain_read_is_not_refused():
    """The guard must not be so broad it blocks the reads it exists to allow.

    Written because a refusal that catches everything passes its own test
    and breaks the layer.
    """
    backend = arch.SQLiteBackend("/nonexistent.db")
    with pytest.raises(Exception) as caught:
        backend.frame("SELECT close FROM prices WHERE ticker = ?", ("AAPL",))
    assert not isinstance(caught.value, arch.ReadOnlyViolation)


def test_empty_ticker_list_returns_no_rows_rather_than_a_syntax_error():
    """An empty universe is a legitimate result of a filter."""
    backend = FakeBackend()
    a = arch.Archive(backend=backend)
    a.bars(tickers=[], start="2020-01-01")
    sql, _ = backend.calls[-1]
    assert "1 = 0" in sql
    assert "IN ()" not in sql


def test_long_ticker_lists_are_chunked_under_the_bind_limit():
    """SQLite's variable limit fails at execute time, not at build time."""
    backend = FakeBackend(pd.DataFrame({"ticker": [], "date": []}))
    a = arch.Archive(backend=backend)
    a.bars(tickers=[f"T{i}" for i in range(2500)], start="2020-01-01")
    assert len(backend.calls) == 3
    for _, params in backend.calls:
        assert len(params) <= arch._MAX_BIND + 1


def test_duplicate_tickers_are_not_queried_twice():
    backend = FakeBackend(pd.DataFrame({"ticker": [], "date": []}))
    arch.Archive(backend=backend).bars(tickers=["AAPL", "AAPL", "MSFT"])
    _, params = backend.calls[-1]
    assert sorted(params) == ["AAPL", "MSFT"]


def test_dates_are_parsed_and_text_numbers_coerced():
    """`marketcap` is stored as TEXT; compared as text, "9" sorts above "10"."""
    backend = FakeBackend(pd.DataFrame({
        "date": ["2020-01-02"], "marketcap": ["1234.5"], "ticker": ["AAPL"]}))
    got = arch.Archive(backend=backend).frame("SELECT 1")
    assert got["date"].dtype.kind == "M"
    assert got["marketcap"].iloc[0] == pytest.approx(1234.5)


def test_the_placeholder_comes_from_the_backend():
    """The Postgres move changes this one character, not every query."""
    backend = FakeBackend()
    backend.placeholder = "%s"
    arch.Archive(backend=backend).security_master("SEP")
    sql, _ = backend.calls[-1]
    assert "%s" in sql and "?" not in sql
