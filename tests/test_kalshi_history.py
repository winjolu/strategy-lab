"""The history fetcher against a scripted fake API: no network."""
import os
from datetime import datetime, timezone

import pandas as pd
import pytest

from lab.data import kalshi_history as kh
from tests import engine_fixtures as fx


def ts(y, m, d, h=0):
    return int(datetime(y, m, d, h, tzinfo=timezone.utc).timestamp())


def iso(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


HOLD = "2026-04-01"


def mk(ticker, settled=(2026, 1, 10), volume="10.00", mtype="binary", opened=(2026, 1, 1), closed=(2026, 1, 9)):
    return {"ticker": ticker, "event_ticker": ticker.rsplit("-", 1)[0], "market_type": mtype, "title": "t",
            "yes_sub_title": "y", "result": "no", "open_time": iso(*opened), "close_time": iso(*closed),
            "latest_expiration_time": iso(*closed), "settlement_ts": iso(*settled) if settled else "",
            "settlement_value_dollars": "0.00", "volume_fp": volume}


def candle(end, bid="0.05", ask="0.07"):
    return {"end_period_ts": end, "yes_bid": {"close": bid}, "yes_ask": {"close": ask},
            "price": {"close": "0.06"}, "volume": "3", "open_interest": "9"}


class Resp:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


class Fake:
    def __init__(self, series, hist=None, live=None, candles=None):
        self.series, self.hist, self.live = series, hist or {}, live or {}
        self.candle_rows = candles or {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        path = url.replace(kh._rec.BASE, "")
        params = dict(params or {})
        self.calls.append((path, params))
        if path == "/series/fee_changes":
            assert params.get("show_historical") == "true"
            return Resp(200, {"series_fee_change_arr": [
                {"series_ticker": "A", "scheduled_ts": "2026-01-01T00:00:00Z", "fee_type": "quadratic",
                 "fee_multiplier": 0.5, "id": "x"}]})
        if path == "/series":
            return Resp(200, {"series": self.series})
        if path in ("/historical/markets", "/markets"):
            src = self.hist if path == "/historical/markets" else self.live
            rows = src.get(params["series_ticker"], [])
            start = int(params.get("cursor") or 0)
            nxt = start + 2
            return Resp(200, {"markets": rows[start:nxt], "cursor": str(nxt) if nxt < len(rows) else ""})
        if path.endswith("/candlesticks"):
            t = path.split("/")[-2]
            rows = [c for c in self.candle_rows.get(t, []) if params["start_ts"] <= c["end_period_ts"] <= params["end_ts"]]
            return Resp(200, {"candlesticks": rows})
        raise AssertionError(path)


def S(ticker, category="Entertainment", frequency="one_off"):
    return {"ticker": ticker, "title": ticker, "category": category, "frequency": frequency,
            "fee_type": "quadratic", "fee_multiplier": 1}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_LAB_DATA_DIR", str(tmp_path / "data"))
    import lab.recorders.kalshi as rk
    monkeypatch.setattr(rk.time, "sleep", lambda s: None)
    monkeypatch.setattr(kh, "PAGE", 2)
    reg = tmp_path / "reg"
    os.makedirs(reg)
    fx.write_registration(str(reg), id="toy", holdout=HOLD)
    return str(reg)


def read(kind, name):
    return pd.read_parquet(os.path.join(kh.root(), kind, f"{name}.parquet"))


def run(fake, reg, **kw):
    return kh.run("toy", session=fake, registry_directory=reg, **kw)


def test_universe_is_chosen_from_static_attributes():
    series = pd.DataFrame([S("A"), S("B", "Sports"), S("C", "Crypto"), S("D", frequency="hourly"),
                           S("E", frequency="fifteen_min"), S("F", "Elections", "annual")])
    assert kh.universe(series) == ["A", "B", "F"]


def test_markets_and_candles_are_written_per_series(env):
    fake = Fake([S("A")], hist={"A": [mk("A-1-X"), mk("A-1-Y")]},
                candles={"A-1-X": [candle(ts(2026, 1, 2))], "A-1-Y": [candle(ts(2026, 1, 3))]})
    r = run(fake, env)
    assert r["markets"] == 2 and r["candles"] == 2
    assert sorted(read("markets", "A")["ticker"]) == ["A-1-X", "A-1-Y"]
    assert read("candles", "A")["yes_bid_close"].tolist() == ["0.05", "0.05"]


def test_markets_settling_on_or_after_the_holdout_are_never_stored(env):
    hist = {"A": [mk("A-1-X", settled=(2026, 3, 31)), mk("A-2-X", settled=(2026, 4, 1)),
                  mk("A-3-X", settled=(2026, 9, 1))]}
    run(Fake([S("A")], hist=hist), env)
    assert read("markets", "A")["ticker"].tolist() == ["A-1-X"]


def test_candles_ending_on_or_after_the_holdout_are_never_stored(env):
    m = mk("A-1-X", settled=(2026, 3, 31), opened=(2026, 3, 20), closed=(2026, 3, 31, 23))
    c = [candle(ts(2026, 3, 31, 22)), candle(ts(2026, 4, 1, 0)), candle(ts(2026, 4, 1, 1))]
    run(Fake([S("A")], hist={"A": [m]}, candles={"A-1-X": c}), env)
    assert read("candles", "A")["end_period_ts"].tolist() == [ts(2026, 3, 31, 22)]


def test_combination_and_non_binary_markets_are_dropped(env):
    hist = {"A": [mk("KXMVE-1"), mk("A-1-X", mtype="scalar"), mk("A-2-X")]}
    run(Fake([S("A")], hist=hist), env)
    assert read("markets", "A")["ticker"].tolist() == ["A-2-X"]


def test_a_market_present_in_both_tiers_is_kept_once_from_the_historical_tier(env):
    run(Fake([S("A")], hist={"A": [mk("A-1-X")]}, live={"A": [mk("A-1-X"), mk("A-2-X")]}), env)
    m = read("markets", "A").set_index("ticker")
    assert m.loc["A-1-X", "tier"] == "historical" and m.loc["A-2-X", "tier"] == "live"


def test_unsettled_markets_are_dropped(env):
    run(Fake([S("A")], hist={"A": [mk("A-1-X", settled=None), mk("A-2-X")]}), env)
    assert read("markets", "A")["ticker"].tolist() == ["A-2-X"]


def test_markets_that_never_traded_get_no_candle_calls(env):
    fake = Fake([S("A")], hist={"A": [mk("A-1-X", volume="0.00"), mk("A-2-X")]},
                candles={"A-2-X": [candle(ts(2026, 1, 3))]})
    run(fake, env)
    assert not any("A-1-X" in p for p, _ in fake.calls)


def test_losers_are_kept_alongside_winners(env):
    a, b = mk("A-1-X"), mk("A-2-X")
    a["result"], b["result"] = "yes", "no"
    run(Fake([S("A")], hist={"A": [a, b]}), env)
    assert sorted(read("markets", "A")["result"]) == ["no", "yes"]


def test_a_long_life_is_fetched_in_chunks_without_gaps_or_overlap():
    w = kh.windows(0, 400 * 86400)
    assert w[0][0] == 0 and w[-1][1] == 400 * 86400
    assert all(w[i][1] == w[i + 1][0] for i in range(len(w) - 1))
    assert all(b - a <= kh.CHUNK_DAYS * 86400 for a, b in w)


def test_resuming_skips_finished_series_and_refetches_none(env):
    fake = Fake([S("A"), S("B")], hist={"A": [mk("A-1-X")], "B": [mk("B-1-X")]},
                candles={"A-1-X": [candle(ts(2026, 1, 3))], "B-1-X": [candle(ts(2026, 1, 3))]})
    run(fake, env, max_series=1)
    first = len(fake.calls)
    run(fake, env)
    later = [p for p, q in fake.calls[first:] if p != "/series"]
    assert later and all("A-1" not in p and q.get("series_ticker") != "A" for p, q in fake.calls[first:])
    assert read("markets", "B")["ticker"].tolist() == ["B-1-X"]


def test_a_series_that_fails_midway_is_not_marked_done(env):
    class Boom(Fake):
        def get(self, url, params=None, timeout=None):
            if "candlesticks" in url:
                return Resp(500, {})
            return super().get(url, params, timeout)

    with pytest.raises(kh.FetchFailed):
        run(Boom([S("A")], hist={"A": [mk("A-1-X")]}), env)
    assert not kh.Manifest(kh._holdout("toy", env)).done("candles", "A")


def test_a_series_with_no_settled_markets_is_recorded_as_empty_not_missing(env):
    r = run(Fake([S("A")]), env)
    assert r["empty"] == 1 and read("candles", "A").empty


def test_a_different_cutoff_starts_a_new_manifest(env):
    run(Fake([S("A")], hist={"A": [mk("A-1-X")]}), env)
    m = kh.Manifest(kh._holdout("toy", env) + 86400)
    assert not m.done("markets", "A")


def test_an_unregistered_strategy_fetches_nothing(env):
    fake = Fake([S("A")])
    with pytest.raises(Exception):
        kh.run("nope", session=fake, registry_directory=env)
    assert fake.calls == []


def test_fee_changes_are_stored_including_history(env):
    run(Fake([S("A")]), env)
    changes = pd.read_parquet(os.path.join(kh.root(), "fee_changes.parquet"))
    assert changes["series_ticker"].tolist() == ["A"] and changes["fee_multiplier"].tolist() == [0.5]


def test_the_throttle_spaces_calls_across_threads():
    from concurrent.futures import ThreadPoolExecutor
    now, slept = [0.0], []

    class Sess:
        def get(self, *a, **k):
            return "ok"

    t = kh.Throttled(Sess(), per_second=4, clock=lambda: now[0], sleep=lambda w: slept.append(w))
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: t.get(), range(8)))
    assert len(slept) == 7 and sorted(slept)[-1] == pytest.approx(7 * 0.25)


def test_a_rate_limit_waits_as_long_as_the_server_asks(monkeypatch):
    import lab.recorders.kalshi as rk
    sleeps = []
    monkeypatch.setattr(rk.time, "sleep", lambda s: sleeps.append(s))

    class R429(Resp):
        headers = {"Retry-After": "45"}

    class Sess:
        n = 0

        def get(self, url, params=None, timeout=None):
            Sess.n += 1
            return R429(429, {}) if Sess.n == 1 else Resp(200, {"ok": 1})

    assert kh._get(Sess(), "/x", {}) == {"ok": 1}
    assert sleeps == [45.0]


def test_the_history_fetch_is_more_patient_than_the_recorder():
    assert kh.RETRIES > kalshi_retries()


def kalshi_retries():
    import lab.recorders.kalshi as rk
    return rk.RETRIES


def test_a_run_without_a_session_throttles_by_default(env, monkeypatch):
    seen = []

    class Stop(Exception):
        pass

    def spy(session):
        seen.append(type(session).__name__)
        raise Stop

    monkeypatch.setattr(kh, "fetch_series", spy)
    with pytest.raises(Stop):
        kh.run("toy", registry_directory=env)
    assert seen == ["Throttled"]
