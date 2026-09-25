"""The recorder against a scripted fake API: no network."""
import json
import os
from datetime import datetime, timezone

import pandas as pd
import pytest

from lab.recorders import kalshi

T1 = datetime(2026, 9, 23, 22, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 9, 23, 22, 5, tzinfo=timezone.utc)


def market(ticker, bid="0.40", ask="0.45", oi="100.00", **extra):
    base = {"ticker": ticker, "event_ticker": ticker.split("-")[0], "title": "t", "subtitle": "s",
            "market_type": "binary", "open_time": "x", "close_time": "y", "rules_primary": "r",
            "yes_bid_dollars": bid, "yes_ask_dollars": ask, "yes_bid_size_fp": "10.00",
            "yes_ask_size_fp": "12.00", "no_bid_dollars": "0.55", "no_ask_dollars": "0.60",
            "last_price_dollars": "0.42", "volume_fp": "5.00", "open_interest_fp": oi}
    return {**base, **extra}


class Resp:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


class Fake:
    """Serves scripted pages per (path, status); `script` maps a key to a
    list of responses consumed in order."""

    def __init__(self, markets=None, settled=None, books=None, fail_page=None, codes=None):
        self.markets, self.settled, self.books = markets or [], settled or [], books or {}
        self.fail_page, self.calls, self.codes = fail_page, [], list(codes or [])

    def get(self, url, params=None, timeout=None):
        path = url.replace(kalshi.BASE, "")
        self.calls.append((path, dict(params or {})))
        if self.codes:
            code = self.codes.pop(0)
            if code != 200:
                return Resp(code, {})
        if path == "/markets":
            rows = self.markets if params["status"] == "open" else self.settled
            size = 2  # tiny pages so pagination is exercised
            start = int(params.get("cursor") or 0)
            if self.fail_page is not None and start == self.fail_page:
                return Resp(500, {})
            nxt = start + size
            return Resp(200, {"markets": rows[start:nxt], "cursor": str(nxt) if nxt < len(rows) else ""})
        if path.endswith("/orderbook"):
            t = path.split("/")[2]
            if t not in self.books:
                return Resp(404, {})
            return Resp(200, {"orderbook_fp": self.books[t]})
        raise AssertionError(path)


@pytest.fixture(autouse=True)
def tmp_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_LAB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(kalshi.time, "sleep", lambda s: None)
    monkeypatch.setattr(kalshi, "PAGE", 2)
    return tmp_path


def read(dirname):
    base = os.path.join(kalshi.root(), dirname)
    files = [os.path.join(d, f) for d, _, fs in os.walk(base) for f in fs] if os.path.exists(base) else []
    return pd.concat([pd.read_parquet(f) for f in sorted(files)], ignore_index=True) if files else pd.DataFrame()


def test_first_poll_records_every_market_across_pages():
    fake = Fake([market(f"A-{i}") for i in range(5)])
    e = kalshi.record_quotes(fake, T1)
    assert e["markets"] == e["changed"] == e["new"] == 5
    assert len(read("quotes")) == 5 and len(read("markets")) == 5


def test_an_unchanged_poll_writes_no_quote_rows():
    fake = Fake([market(f"A-{i}") for i in range(5)])
    kalshi.record_quotes(fake, T1)
    e = kalshi.record_quotes(fake, T2)
    assert e["changed"] == 0 and e["new"] == 0
    assert len(read("quotes")) == 5


def test_only_the_market_that_moved_is_written_and_only_a_new_one_gets_metadata():
    ms = [market(f"A-{i}") for i in range(4)]
    kalshi.record_quotes(Fake(ms), T1)
    ms[2] = market("A-2", bid="0.41")
    ms.append(market("A-9"))
    e = kalshi.record_quotes(Fake(ms), T2)
    assert e["changed"] == 2 and e["new"] == 1
    later = read("quotes")
    later = later[later["ts"] == T2.isoformat()]
    assert sorted(later["ticker"]) == ["A-2", "A-9"]
    assert read("markets")["ticker"].tolist().count("A-9") == 1


@pytest.mark.parametrize("field,value", [("yes_ask_size_fp", "99.00"), ("volume_fp", "6.00"),
                                         ("open_interest_fp", "101.00"), ("no_bid_dollars", "0.50")])
def test_a_change_in_any_recorded_field_is_a_change(field, value):
    kalshi.record_quotes(Fake([market("A-1")]), T1)
    e = kalshi.record_quotes(Fake([market("A-1", **{field: value})]), T2)
    assert e["changed"] == 1


def test_combination_markets_are_dropped():
    fake = Fake([market("A-1"), market("KXMVECROSSCATEGORY-S1-X"), market("B-1")])
    assert kalshi.record_quotes(fake, T1)["markets"] == 2


def test_a_failed_page_writes_nothing_and_keeps_the_previous_state():
    ms = [market(f"A-{i}") for i in range(6)]
    kalshi.record_quotes(Fake(ms), T1)
    before = read("quotes")
    ms[0] = market("A-0", bid="0.10")
    with pytest.raises(kalshi.FetchFailed):
        kalshi.record_quotes(Fake(ms, fail_page=4), T2)
    assert len(read("quotes")) == len(before)
    assert pd.read_parquet(kalshi._state_path()).set_index("ticker").loc["A-0", "yes_bid_dollars"] == "0.40"
    last = json.loads(open(os.path.join(kalshi.root(), "runs.jsonl")).read().splitlines()[-1])
    assert last["ok"] is False and "HTTP 500" in last["error"]


def test_a_transient_rate_limit_is_retried():
    fake = Fake([market("A-1")], codes=[429, 503, 200])
    assert kalshi.record_quotes(fake, T1)["markets"] == 1


def test_a_client_error_is_not_retried():
    fake = Fake([market("A-1")], codes=[403])
    with pytest.raises(kalshi.FetchFailed):
        kalshi.record_quotes(fake, T1)
    assert len(fake.calls) == 1


def test_a_vanished_market_leaves_the_state_and_is_not_reported_new_on_return():
    kalshi.record_quotes(Fake([market("A-1"), market("A-2")]), T1)
    kalshi.record_quotes(Fake([market("A-1")]), T2)
    assert pd.read_parquet(kalshi._state_path())["ticker"].tolist() == ["A-1"]


def test_every_attempt_is_logged_so_gaps_are_visible():
    kalshi.record_quotes(Fake([market("A-1")]), T1)
    kalshi.record_quotes(Fake([market("A-1")]), T2)
    runs = pd.read_json(os.path.join(kalshi.root(), "runs.jsonl"), lines=True)
    assert runs["ok"].all() and len(runs) == 2


def test_settlements_are_recorded_with_a_watermark():
    fake = Fake(settled=[{"ticker": "A-1", "event_ticker": "A", "result": "yes", "settlement_ts": "z",
                          "settlement_value_dollars": "1.00", "close_time": "c", "volume_fp": "1"}])
    assert kalshi.record_settlements(fake, T1)["settled"] == 1
    assert read("settled")["result"].tolist() == ["yes"]
    assert os.path.exists(os.path.join(kalshi.root(), "settled.watermark"))
    assert fake.calls[0][1]["min_settled_ts"] == int(T1.timestamp()) - 86400
    kalshi.record_settlements(fake, T2)
    assert fake.calls[-1][1]["min_settled_ts"] == int(T1.timestamp()) - 300


def test_depth_targets_are_the_most_liquid_two_sided_markets():
    state = pd.DataFrame([market("A-1", oi="5"), market("A-2", oi="50"), market("A-3", oi="500", bid="0.00"),
                          market("A-4", oi="20")])
    assert kalshi.depth_targets(state, 2) == ["A-2", "A-4"]


def test_depth_writes_every_level_on_both_sides():
    kalshi.record_quotes(Fake([market("A-1", oi="9"), market("A-2", oi="8")]), T1)
    books = {"A-1": {"yes_dollars": [["0.40", "10.00"], ["0.39", "5.00"]], "no_dollars": [["0.55", "7.00"]]},
             "A-2": {"yes_dollars": [], "no_dollars": [["0.50", "1.00"]]}}
    e = kalshi.record_depth(Fake(books=books), T2)
    assert e["levels"] == 4 and e["ok"]
    d = read("depth")
    assert set(zip(d["ticker"], d["side"])) == {("A-1", "yes"), ("A-1", "no"), ("A-2", "no")}


def test_a_book_that_cannot_be_fetched_is_counted_not_hidden():
    kalshi.record_quotes(Fake([market("A-1", oi="9"), market("A-2", oi="8")]), T1)
    e = kalshi.record_depth(Fake(books={"A-1": {"yes_dollars": [["0.4", "1"]], "no_dollars": []}}), T2)
    assert e["failed_books"] == 1 and e["ok"] is False


def test_depth_before_any_quotes_refuses():
    with pytest.raises(kalshi.FetchFailed):
        kalshi.record_depth(Fake(), T1)
