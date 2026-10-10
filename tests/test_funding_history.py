import os
import tempfile
import unittest
from unittest import mock

import pandas as pd

from lab.data import funding_history as fh

HOUR = 3_600_000
T0 = int(pd.Timestamp("2024-01-01", tz="UTC").timestamp() * 1000)


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class DeribitSession:
    """Serves hourly rows for any window, like the real endpoint."""

    def __init__(self, rate=1e-5, drop=()):
        self.calls, self.rate, self.drop = [], rate, set(drop)

    def request(self, method, url, headers=None, timeout=None, params=None, json=None):
        self.calls.append(params)
        lo, hi = params["start_timestamp"], params["end_timestamp"]
        lo += 1     # the real endpoint excludes a row stamped exactly at the start
        first = ((lo - T0 + HOUR - 1) // HOUR) * HOUR + T0
        rows = [{"timestamp": t, "interest_1h": self.rate, "interest_8h": 8 * self.rate}
                for t in range(first, hi + 1, HOUR) if t not in self.drop]
        return Resp(200, {"result": rows})


NOWAIT = dict(sleep=lambda s: None)


class Deribit(unittest.TestCase):
    def test_a_chunk_boundary_loses_no_hour_against_an_endpoint_that_excludes_its_start(self):
        frame = fh.fetch_deribit(DeribitSession(), "BTC-PERPETUAL", "2024-01-01", "2024-04-01", **NOWAIT)
        self.assertEqual(len(frame), 91 * 24)
        self.assertTrue(fh.daily_funding(frame).notna().all())

    def test_rows_stop_before_the_cutoff_and_none_is_requested_past_it(self):
        s = DeribitSession()
        frame = fh.fetch_deribit(s, "BTC-PERPETUAL", "2024-01-01", "2024-02-15", **NOWAIT)
        self.assertLess(frame["time"].max(), pd.Timestamp("2024-02-15", tz="UTC"))
        self.assertEqual(frame["time"].max(), pd.Timestamp("2024-02-14 23:00", tz="UTC"))
        cutoff_ms = int(pd.Timestamp("2024-02-15", tz="UTC").timestamp() * 1000)
        self.assertTrue(all(c["end_timestamp"] < cutoff_ms for c in s.calls))

    def test_a_long_range_is_chunked_with_no_gap_and_no_overlap(self):
        s = DeribitSession()
        frame = fh.fetch_deribit(s, "BTC-PERPETUAL", "2024-01-01", "2024-04-01", **NOWAIT)
        self.assertGreater(len(s.calls), 2)
        self.assertEqual(len(frame), 91 * 24)
        self.assertFalse(frame["time"].duplicated().any())
        self.assertTrue((frame["time"].diff().dropna() == pd.Timedelta(hours=1)).all())

    def test_the_shape_is_normalised(self):
        frame = fh.fetch_deribit(DeribitSession(2e-5), "ETH-PERPETUAL", "2024-01-01", "2024-01-03", **NOWAIT)
        self.assertEqual(list(frame.columns), fh.COLUMNS)
        self.assertEqual(set(frame["venue"]), {"deribit"})
        self.assertEqual(set(frame["instrument"]), {"ETH-PERPETUAL"})
        self.assertAlmostEqual(frame["rate_1h"].iloc[0], 2e-5)

    def test_a_response_with_no_result_is_a_failure_not_an_empty_history(self):
        class Bad:
            def request(self, *a, **k):
                return Resp(200, {"error": {"code": 10001}})
        with self.assertRaises(fh.FetchFailed):
            fh.fetch_deribit(Bad(), "BTC-PERPETUAL", "2024-01-01", "2024-01-03", **NOWAIT)

    def test_overlapping_pages_are_refused_not_deduplicated(self):
        class Overlap:
            def request(self, method, url, headers=None, timeout=None, params=None, json=None):
                return Resp(200, {"result": [{"timestamp": T0, "interest_1h": 1e-5},
                                             {"timestamp": T0, "interest_1h": 2e-5}]})
        with self.assertRaises(fh.FetchFailed):
            fh.fetch_deribit(Overlap(), "BTC-PERPETUAL", "2024-01-01", "2024-01-02", **NOWAIT)


class Transport(unittest.TestCase):
    def sess(self, *statuses):
        it = iter(statuses)

        class S:
            calls = 0

            def request(inner, *a, **k):
                inner.calls += 1
                return Resp(next(it), {"result": []})
        return S()

    def test_a_429_is_retried_with_backoff_then_succeeds(self):
        waits = []
        s = self.sess(429, 429, 200)
        fh._request(s, "GET", "u", sleep=waits.append)
        self.assertEqual(s.calls, 3)
        self.assertEqual(waits, [1.0, 2.0])

    def test_a_server_error_is_retried(self):
        s = self.sess(503, 200)
        fh._request(s, "GET", "u", sleep=lambda x: None)
        self.assertEqual(s.calls, 2)

    def test_a_refusal_is_not_retried_and_says_so(self):
        for code in (403, 451):
            s = self.sess(code, 200)
            with self.assertRaises(fh.FetchFailed) as cm:
                fh._request(s, "GET", "u", sleep=lambda x: None)
            self.assertEqual(s.calls, 1)
            self.assertIn("refuses this location", str(cm.exception))

    def test_a_client_error_is_a_failure_at_once(self):
        s = self.sess(400, 200)
        with self.assertRaises(fh.FetchFailed):
            fh._request(s, "GET", "u", sleep=lambda x: None)
        self.assertEqual(s.calls, 1)

    def test_persistent_failure_gives_up(self):
        s = self.sess(*[500] * fh.RETRIES)
        with self.assertRaises(fh.FetchFailed):
            fh._request(s, "GET", "u", sleep=lambda x: None)
        self.assertEqual(s.calls, fh.RETRIES)


class HyperSession:
    def __init__(self, hours=1200, jitter=48):
        self.times = [T0 + i * HOUR + jitter for i in range(hours)]
        self.calls = []

    def request(self, method, url, headers=None, timeout=None, params=None, json=None):
        self.calls.append(json)
        page = [t for t in self.times if t >= json["startTime"]][:fh.HL_PAGE]
        return Resp(200, [{"coin": "BTC", "fundingRate": "0.0000125", "premium": "0", "time": t}
                          for t in page])


class Hyperliquid(unittest.TestCase):
    def test_pages_are_followed_to_the_end_and_hours_are_unique(self):
        s = HyperSession(1200)
        frame = fh.fetch_hyperliquid(s, "BTC", "2024-01-01", "2024-03-01", **NOWAIT)
        self.assertEqual(len(frame), 1200)
        self.assertGreaterEqual(len(s.calls), 3)
        self.assertTrue((frame["time"].dt.minute == 0).all())
        self.assertAlmostEqual(frame["rate_1h"].iloc[0], 0.0000125)

    def test_the_cutoff_is_respected(self):
        s = HyperSession(1200)
        frame = fh.fetch_hyperliquid(s, "BTC", "2024-01-01", "2024-01-11", **NOWAIT)
        self.assertEqual(len(frame), 240)
        self.assertLess(frame["time"].max(), pd.Timestamp("2024-01-11", tz="UTC"))

    def test_a_page_that_does_not_advance_is_a_failure(self):
        class Stuck:
            def request(self, method, url, headers=None, timeout=None, params=None, json=None):
                return Resp(200, [{"time": json["startTime"] - 5, "fundingRate": "0.1"}])
        with self.assertRaises(fh.FetchFailed):
            fh.fetch_hyperliquid(Stuck(), "BTC", "2024-01-01", "2024-02-01", **NOWAIT)


class Daily(unittest.TestCase):
    def frame(self, drop=()):
        return fh.fetch_deribit(DeribitSession(1e-5, drop=drop), "BTC-PERPETUAL",
                                "2024-01-01", "2024-01-06", **NOWAIT)

    def test_a_complete_day_sums_its_24_hours(self):
        d = fh.daily_funding(self.frame())
        self.assertEqual(len(d), 5)
        self.assertAlmostEqual(d.iloc[0], 24e-5)

    def test_a_day_missing_an_hour_is_unknown_not_a_smaller_number(self):
        d = fh.daily_funding(self.frame(drop=[T0 + 30 * HOUR]))
        self.assertTrue(pd.isna(d.loc["2024-01-02"]))
        self.assertAlmostEqual(d.loc["2024-01-01"], 24e-5)

    def test_a_day_with_no_rows_at_all_is_present_and_unknown(self):
        d = fh.daily_funding(self.frame(drop=range(T0 + 48 * HOUR, T0 + 72 * HOUR, HOUR)))
        self.assertTrue(pd.isna(d.loc["2024-01-03"]))
        self.assertEqual(len(d), 5)

    def test_days_are_utc_and_naive(self):
        d = fh.daily_funding(self.frame())
        self.assertIsNone(d.index.tz)


class Storage(unittest.TestCase):
    def test_a_written_file_reads_back_identically(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fh, "root", lambda: tmp):
            frame = fh.fetch_deribit(DeribitSession(), "BTC-PERPETUAL", "2024-01-01", "2024-01-05", **NOWAIT)
            path = fh.write(frame, "deribit-BTC")
            self.assertTrue(os.path.exists(path))
            self.assertFalse(os.path.exists(path + ".tmp"))
            pd.testing.assert_frame_equal(fh.read("deribit-BTC"), frame)
