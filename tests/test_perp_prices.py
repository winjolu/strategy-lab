import unittest

import pandas as pd

from lab.data import funding_history as fh
from lab.data import perp_prices as pp

HOUR = 3_600_000
T0 = int(pd.Timestamp("2024-01-01", tz="UTC").timestamp() * 1000)
NOWAIT = dict(sleep=lambda s: None)


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class ChartSession:
    """Serves hourly candles for any window; close is the candle's hour index."""

    def __init__(self, drop=(), status="ok"):
        self.calls, self.drop, self.status = [], set(drop), status

    def request(self, method, url, headers=None, timeout=None, params=None, json=None):
        self.calls.append(params)
        lo, hi = params["start_timestamp"], params["end_timestamp"]
        first = ((lo - T0 + HOUR - 1) // HOUR) * HOUR + T0
        ticks = [t for t in range(first, hi + 1, HOUR) if t not in self.drop]
        return Resp(200, {"result": {
            "status": self.status if ticks else "no_data", "ticks": ticks,
            "close": [100.0 + (t - T0) // HOUR for t in ticks],
            "cost": [1000.0] * len(ticks)}})


class IndexSession:
    def __init__(self, hours=96, step=2):
        self.rows = [[T0 + h * HOUR, 100.0 + h] for h in range(0, hours, step)]

    def request(self, method, url, headers=None, timeout=None, params=None, json=None):
        return Resp(200, {"result": self.rows})


class Perp(unittest.TestCase):
    def test_nothing_is_requested_at_or_past_the_cutoff(self):
        s = ChartSession()
        frame = pp.fetch_perp_hourly(s, "BTC-PERPETUAL", "2024-01-01", "2024-02-15", **NOWAIT)
        cutoff = int(pd.Timestamp("2024-02-15", tz="UTC").timestamp() * 1000)
        self.assertTrue(all(c["end_timestamp"] < cutoff for c in s.calls))
        self.assertEqual(frame["time"].max(), pd.Timestamp("2024-02-14 23:00", tz="UTC"))

    def test_a_server_that_returns_past_the_cutoff_is_cut_anyway(self):
        class Greedy(ChartSession):
            def request(self, method, url, headers=None, timeout=None, params=None, json=None):
                params = dict(params, end_timestamp=params["end_timestamp"] + 10 * HOUR)
                return super().request(method, url, params=params)
        frame = pp.fetch_perp_hourly(Greedy(), "BTC-PERPETUAL", "2024-01-01", "2024-01-10", **NOWAIT)
        self.assertLess(frame["time"].max(), pd.Timestamp("2024-01-10", tz="UTC"))

    def test_chunks_leave_no_gap_and_no_overlap(self):
        s = ChartSession()
        frame = pp.fetch_perp_hourly(s, "BTC-PERPETUAL", "2024-01-01", "2024-04-01", **NOWAIT)
        self.assertGreater(len(s.calls), 2)
        self.assertEqual(len(frame), 91 * 24)
        self.assertTrue((frame["time"].diff().dropna() == pd.Timedelta(hours=1)).all())

    def test_a_malformed_reply_is_a_failure_not_an_empty_history(self):
        class Bad:
            def request(self, *a, **k):
                return Resp(200, {"error": {"code": 1}})
        with self.assertRaises(fh.FetchFailed):
            pp.fetch_perp_hourly(Bad(), "BTC-PERPETUAL", "2024-01-01", "2024-01-03", **NOWAIT)

    def test_an_error_status_is_a_failure(self):
        with self.assertRaises(fh.FetchFailed):
            pp.fetch_perp_hourly(ChartSession(status="error"), "BTC-PERPETUAL",
                                 "2024-01-01", "2024-01-03", **NOWAIT)

    def test_arrays_of_different_length_are_a_failure(self):
        class Short:
            def request(self, *a, **k):
                return Resp(200, {"result": {"status": "ok", "ticks": [T0, T0 + HOUR],
                                             "close": [1.0], "cost": [1.0, 1.0]}})
        with self.assertRaises(fh.FetchFailed):
            pp.fetch_perp_hourly(Short(), "BTC-PERPETUAL", "2024-01-01", "2024-01-02", **NOWAIT)

    def test_overlapping_pages_are_refused(self):
        class Dup:
            def request(self, *a, **k):
                return Resp(200, {"result": {"status": "ok", "ticks": [T0, T0],
                                             "close": [1.0, 1.0], "cost": [1.0, 1.0]}})
        with self.assertRaises(fh.FetchFailed):
            pp.fetch_perp_hourly(Dup(), "BTC-PERPETUAL", "2024-01-01", "2024-01-02", **NOWAIT)


class Index(unittest.TestCase):
    def test_everything_at_or_after_the_cutoff_is_discarded(self):
        frame = pp.fetch_index(IndexSession(hours=96), "btc_usd", "2024-01-03", **NOWAIT)
        self.assertLess(frame["time"].max(), pd.Timestamp("2024-01-03", tz="UTC"))
        self.assertNotIn(pd.Timestamp("2024-01-03", tz="UTC"), set(frame["time"]))

    def test_a_reply_without_a_history_is_a_failure(self):
        class Bad:
            def request(self, *a, **k):
                return Resp(200, {"result": {"oops": 1}})
        with self.assertRaises(fh.FetchFailed):
            pp.fetch_index(Bad(), "btc_usd", "2024-01-03", **NOWAIT)

    def test_a_repeated_instant_is_refused(self):
        class Dup:
            def request(self, *a, **k):
                return Resp(200, {"result": [[T0, 1.0], [T0, 2.0]]})
        with self.assertRaises(fh.FetchFailed):
            pp.fetch_index(Dup(), "btc_usd", "2024-02-01", **NOWAIT)


class DayEnd(unittest.TestCase):
    def frames(self, drop_candle=None, drop_index=None):
        perp = pp.fetch_perp_hourly(ChartSession(drop=[drop_candle] if drop_candle else ()),
                                    "BTC-PERPETUAL", "2024-01-01", "2024-01-10", **NOWAIT)
        index = pp.fetch_index(IndexSession(hours=24 * 9 + 2), "btc_usd", "2024-01-10", **NOWAIT)
        if drop_index is not None:
            index = index[index["time"] != drop_index]
        return perp, index

    def test_the_price_for_a_day_is_taken_at_the_end_of_that_day(self):
        perp, index = self.frames()
        out = pp.day_end_prices(perp, index)
        d = pd.Timestamp("2024-01-02")
        # perp: close of the 23:00 candle on Jan 2 is hour index 24+23 = 47 -> 147.0
        self.assertEqual(out.loc[d, "perp"], 100.0 + 47)
        # index: the value stamped 00:00 on Jan 3, hour index 48 -> 148.0
        self.assertEqual(out.loc[d, "index"], 100.0 + 48)
        self.assertAlmostEqual(out.loc[d, "ratio"], 148.0 / 147.0)

    def test_a_missing_candle_leaves_that_day_missing_not_filled(self):
        gone = T0 + 47 * HOUR     # the 23:00 candle on Jan 2
        perp, index = self.frames(drop_candle=gone)
        out = pp.day_end_prices(perp, index)
        self.assertTrue(pd.isna(out.loc[pd.Timestamp("2024-01-02"), "ratio"]))
        self.assertFalse(pd.isna(out.loc[pd.Timestamp("2024-01-01"), "ratio"]))
        self.assertFalse(pd.isna(out.loc[pd.Timestamp("2024-01-03"), "ratio"]))

    def test_a_missing_index_value_leaves_that_day_missing(self):
        perp, index = self.frames(drop_index=pd.Timestamp("2024-01-03", tz="UTC"))
        out = pp.day_end_prices(perp, index)
        self.assertTrue(pd.isna(out.loc[pd.Timestamp("2024-01-02"), "ratio"]))

    def test_a_non_positive_price_is_refused(self):
        perp, index = self.frames()
        perp.loc[perp["time"].dt.hour == 23, "close"] = 0.0
        with self.assertRaises(ValueError):
            pp.day_end_prices(perp, index)


if __name__ == "__main__":
    unittest.main()


class CoinbaseSession:
    """Like the real endpoint: both ends inclusive, newest candle first, at
    most 300 per reply, rows as [time_s, low, high, open, close, volume]."""

    def __init__(self, drop=(), extra=0):
        self.calls, self.drop, self.extra = [], set(drop), extra

    def request(self, method, url, headers=None, timeout=None, params=None, json=None):
        self.calls.append(params)
        lo = int(pd.Timestamp(params["start"]).timestamp())
        hi = int(pd.Timestamp(params["end"]).timestamp()) + self.extra * 3600
        rows = [[t, 1.0, 2.0, 1.5, 100.0 + (t * 1000 - T0) // HOUR, 7.0]
                for t in range(lo, hi + 1, 3600) if t * 1000 not in self.drop]
        assert len(rows) <= 300 + self.extra
        return Resp(200, list(reversed(rows)))


class Coinbase(unittest.TestCase):
    def test_pages_neither_overlap_nor_leave_a_gap(self):
        s = CoinbaseSession()
        frame = pp.fetch_coinbase_hourly(s, "BTC-USD", "2024-01-01", "2024-03-01", **NOWAIT)
        self.assertGreater(len(s.calls), 2)
        self.assertEqual(len(frame), 60 * 24)
        self.assertTrue((frame["time"].diff().dropna() == pd.Timedelta(hours=1)).all())

    def test_nothing_is_requested_at_or_past_the_cutoff(self):
        s = CoinbaseSession()
        frame = pp.fetch_coinbase_hourly(s, "BTC-USD", "2024-01-01", "2024-01-20", **NOWAIT)
        cutoff = pd.Timestamp("2024-01-20", tz="UTC")
        self.assertTrue(all(pd.Timestamp(c["end"]) < cutoff for c in s.calls))
        self.assertEqual(frame["time"].max(), pd.Timestamp("2024-01-19 23:00", tz="UTC"))

    def test_a_reply_reaching_past_the_cutoff_is_cut_anyway(self):
        frame = pp.fetch_coinbase_hourly(CoinbaseSession(extra=5), "BTC-USD",
                                         "2024-01-01", "2024-01-05", **NOWAIT)
        self.assertLess(frame["time"].max(), pd.Timestamp("2024-01-05", tz="UTC"))

    def test_overlapping_pages_are_refused(self):
        with self.assertRaises(fh.FetchFailed):
            pp.fetch_coinbase_hourly(CoinbaseSession(extra=1), "BTC-USD",
                                     "2024-01-01", "2024-02-01", **NOWAIT)

    def test_an_error_body_is_a_failure(self):
        class Bad:
            def request(self, *a, **k):
                return Resp(200, {"message": "NotFound"})
        with self.assertRaises(fh.FetchFailed):
            pp.fetch_coinbase_hourly(Bad(), "BTC-USD", "2024-01-01", "2024-01-02", **NOWAIT)

    def test_an_empty_object_is_a_failure_not_an_empty_history(self):
        class Bad:
            def request(self, *a, **k):
                return Resp(200, {})
        with self.assertRaises(fh.FetchFailed):
            pp.fetch_coinbase_hourly(Bad(), "BTC-USD", "2024-01-01", "2024-01-02", **NOWAIT)

    def test_a_malformed_row_is_a_failure(self):
        class Bad:
            def request(self, *a, **k):
                return Resp(200, [[1, 2, 3]])
        with self.assertRaises(fh.FetchFailed):
            pp.fetch_coinbase_hourly(Bad(), "BTC-USD", "2024-01-01", "2024-01-02", **NOWAIT)

    def test_the_close_is_taken_not_the_open(self):
        frame = pp.fetch_coinbase_hourly(CoinbaseSession(), "BTC-USD", "2024-01-01", "2024-01-02", **NOWAIT)
        self.assertEqual(frame["close"].iloc[0], 100.0)

    def test_as_the_index_the_23h_close_is_the_price_at_midnight(self):
        spot = pp.fetch_coinbase_hourly(CoinbaseSession(), "BTC-USD", "2024-01-01", "2024-01-10", **NOWAIT)
        perp = pp.fetch_perp_hourly(ChartSession(), "BTC-PERPETUAL", "2024-01-01", "2024-01-10", **NOWAIT)
        out = pp.day_end_prices(perp, pp.spot_as_index(spot))
        d = pd.Timestamp("2024-01-02")
        # both legs read the close of the 23:00 candle on Jan 2, hour index 47
        self.assertEqual(out.loc[d, "index"], 147.0)
        self.assertEqual(out.loc[d, "perp"], 147.0)
        self.assertAlmostEqual(out.loc[d, "ratio"], 1.0)

    def test_a_missing_23h_candle_leaves_the_day_missing(self):
        gone = T0 + 47 * HOUR
        spot = pp.fetch_coinbase_hourly(CoinbaseSession(drop=[gone]), "BTC-USD",
                                        "2024-01-01", "2024-01-10", **NOWAIT)
        perp = pp.fetch_perp_hourly(ChartSession(), "BTC-PERPETUAL", "2024-01-01", "2024-01-10", **NOWAIT)
        out = pp.day_end_prices(perp, pp.spot_as_index(spot))
        self.assertTrue(pd.isna(out.loc[pd.Timestamp("2024-01-02"), "ratio"]))


class BasisNoise(unittest.TestCase):
    def test_it_is_the_spread_of_the_basis_in_the_window_in_percent(self):
        idx = pd.date_range("2024-01-01", periods=6, freq="D")
        prices = pd.DataFrame({"ratio": [1.0, 1.01, 0.99, 1.01, 0.99, 5.0]}, idx)
        got = pp.basis_noise_pct(prices, "2024-01-01", "2024-01-05")
        self.assertAlmostEqual(got, pd.Series([0.0, 1.0, -1.0, 1.0, -1.0]).std(ddof=1), places=9)

    def test_missing_days_are_ignored_not_zeroed(self):
        idx = pd.date_range("2024-01-01", periods=4, freq="D")
        prices = pd.DataFrame({"ratio": [1.01, float("nan"), 0.99, 1.01]}, idx)
        got = pp.basis_noise_pct(prices, "2024-01-01", "2024-01-04")
        self.assertAlmostEqual(got, pd.Series([1.0, -1.0, 1.0]).std(ddof=1), places=9)
