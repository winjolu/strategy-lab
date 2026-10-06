"""Deribit perpetual prices and index values at 00:00 UTC, cut at a holdout.

The carry's return depends on the ratio of the index (spot) price to the
perpetual's price, so each day needs both at the same instant. The
perpetual's hourly candles come from the chart endpoint and the index from
the index chart, both public. Registered convention: the price stamped for
UTC day `d` is the price at the end of that day, 00:00 UTC on `d + 1`, so
a day's price ratio, its funding and its return all describe the same 24
hours.

* **The cutoff is enforced here, twice.** The perpetual is requested in
  windows that end before it. The index endpoint serves its whole history
  in one reply with no way to ask for less, so rows at or after the cutoff
  are dropped from memory before anything is returned or written, and are
  never kept. The last day before the cutoff is therefore missing: its end
  price is stamped at the cutoff itself. One day lost beats a boundary
  value read.
* **A missing price is missing.** An hour with no candle gives no price at
  its end. Nothing is forward-filled: a stale price would manufacture a
  basis move on the day it resumed.
"""
import os
import time

import pandas as pd

from lab import config
from lab.data.funding_history import FetchFailed, _ms, _request

CHART = "https://www.deribit.com/api/v2/public/get_tradingview_chart_data"
INDEX_CHART = "https://www.deribit.com/api/v2/public/get_index_chart_data"
CHUNK_DAYS = 30            # 720 hourly candles per request
CALLS_PER_SECOND = 4.0
HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS


def root():
    return os.path.join(config.data_dir(), "perp_prices")


def _cut(frame, cutoff):
    return frame[frame["time"] < pd.Timestamp(_ms(cutoff), unit="ms", tz="UTC")]


def fetch_perp_hourly(session, instrument, start, cutoff, sleep=time.sleep, pace=None):
    """Hourly close and dollar volume for one Deribit perpetual from `start`
    up to, not including, `cutoff`. `time` is the candle's start."""
    rows, lo = [], _ms(start)
    hi_limit = _ms(cutoff) - 1
    step = CHUNK_DAYS * DAY_MS
    while lo <= hi_limit:
        hi = min(lo + step - 1, hi_limit)
        body = _request(session, "GET", CHART, sleep=sleep, params={
            "instrument_name": instrument, "start_timestamp": lo, "end_timestamp": hi,
            "resolution": "60"})
        result = body.get("result")
        if not isinstance(result, dict) or "ticks" not in result:
            raise FetchFailed(f"Deribit answered without candles: {str(body)[:120]}")
        if result.get("status") not in ("ok", "no_data"):
            raise FetchFailed(f"Deribit candle status {result.get('status')!r}")
        n = len(result["ticks"])
        if not (len(result["close"]) == len(result["cost"]) == n):
            raise FetchFailed("Deribit candle arrays differ in length")
        rows += list(zip(result["ticks"], result["close"], result["cost"]))
        lo = hi + 1
        (pace or sleep)(1.0 / CALLS_PER_SECOND)
    frame = pd.DataFrame(rows, columns=["time", "close", "usd_volume"])
    frame["time"] = pd.to_datetime(frame["time"], unit="ms", utc=True)
    frame = _cut(frame, cutoff).sort_values("time")
    if frame["time"].duplicated().any():
        raise FetchFailed("two candles for the same hour; the venue's paging overlapped")
    frame["instrument"] = instrument
    return frame.reset_index(drop=True)


def fetch_index(session, name, cutoff, sleep=time.sleep):
    """The index's values from the start of its history up to, not
    including, `cutoff`. The endpoint returns everything it has; rows at or
    after the cutoff are discarded here."""
    body = _request(session, "GET", INDEX_CHART, sleep=sleep,
                    params={"index_name": name, "range": "all"})
    result = body.get("result")
    if not isinstance(result, list):
        raise FetchFailed(f"Deribit answered without an index history: {str(body)[:120]}")
    frame = pd.DataFrame(result, columns=["time", "index_price"])
    frame["time"] = pd.to_datetime(frame["time"], unit="ms", utc=True)
    frame = _cut(frame, cutoff).sort_values("time")
    if frame["time"].duplicated().any():
        raise FetchFailed("two index values for the same instant")
    frame["index_name"] = name
    return frame.reset_index(drop=True)


def day_end_prices(perp_hourly, index):
    """One row per UTC day `d`: the perpetual's price `F` and the index `S`
    at the end of `d`, 00:00 UTC on `d + 1`, and their ratio `S / F`.

    The perpetual's price is the close of the candle that started at 23:00
    on `d`; the index is the value stamped exactly 00:00 on `d + 1`. A day
    lacking either is NaN, never filled from a neighbour.
    """
    one = perp_hourly.set_index("time")["close"]
    spot = index.set_index("time")["index_price"]
    if one.index.has_duplicates or spot.index.has_duplicates:
        raise ValueError("duplicate timestamps in a price series")
    last_hour = one[one.index.hour == 23]
    perp = pd.Series(last_hour.values, index=last_hour.index.floor("D").tz_localize(None))
    ends = spot[spot.index.hour == 0]
    spot_by_day = pd.Series(ends.values,
                            index=(ends.index - pd.Timedelta(days=1)).tz_localize(None))
    days = pd.date_range(min(perp.index.min(), spot_by_day.index.min()),
                         max(perp.index.max(), spot_by_day.index.max()), freq="D")
    out = pd.DataFrame({"perp": perp.reindex(days), "index": spot_by_day.reindex(days)})
    out["ratio"] = out["index"] / out["perp"]
    bad = out["ratio"].replace([float("inf"), float("-inf")], float("nan"))
    if ((out["perp"] <= 0) | (out["index"] <= 0)).any():
        raise ValueError("a non-positive price; a units break upstream")
    out["ratio"] = bad
    return out


def write(frame, name):
    os.makedirs(root(), exist_ok=True)
    path = os.path.join(root(), f"{name}.parquet")
    tmp = path + ".tmp"
    frame.to_parquet(tmp, index=True)
    os.replace(tmp, path)
    return path


def read(name):
    return pd.read_parquet(os.path.join(root(), f"{name}.parquet"))
