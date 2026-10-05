"""Perpetual-future funding history from two public venues, cut at a holdout.

A perpetual future has no expiry and stays near spot because one side pays
the other a funding rate every period. This pulls that rate from the two
venues that serve deep history to this location (see
`docs/perp-funding-survey.md`): Deribit hourly funding for the BTC and ETH
perpetuals back to 2019, and Hyperliquid hourly funding from 2023-05. Both
are normalised to one shape, a row per hour with the rate paid for that hour
as a fraction of notional, positive meaning longs pay shorts.

Two properties matter more than speed:

* **The holdout is cut here.** `cutoff` is required and has no default. Rows
  at or after it are dropped before anything is written, and no request asks
  for them, so no later step can read past the date by mistake. Stage 3
  fetches the holdout by passing a later cutoff explicitly.
* **A day with a missing hour has no funding, not a short one.** Summing the
  hours that arrived would understate the rate the position actually paid or
  received, and the shortfall would be invisible. `daily_funding` returns NaN
  for any day without all 24 hours, and the backtest refuses to hold a
  position through one.

Only public read endpoints are used. A venue that refuses the location is
left refused: nothing here routes around it.
"""
import os
import time
from datetime import datetime, timezone

import pandas as pd

from lab import config

DERIBIT = "https://www.deribit.com/api/v2/public/get_funding_rate_history"
HYPERLIQUID = "https://api.hyperliquid.xyz/info"
CHUNK_DAYS = 30            # 720 hourly rows, inside Deribit's page size
HL_PAGE = 500
CALLS_PER_SECOND = 4.0
RETRIES = 6
HOURS_PER_DAY = 24
COLUMNS = ["time", "rate_1h", "venue", "instrument"]
HEADERS = {"User-Agent": "strategy-lab/1.0", "Accept": "application/json"}


class FetchFailed(RuntimeError):
    """A request kept failing, or a venue refused. Never read as an empty result."""


def root():
    return os.path.join(config.data_dir(), "funding_history")


def _ms(ts):
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return int(t.timestamp() * 1000)


def _request(session, method, url, sleep=time.sleep, **kwargs):
    """One call with patience for a 429 and for a server error, and no
    patience for a refusal: a 403 or 451 means the venue does not serve this
    location, and retrying it would only look like evasion."""
    last = None
    for attempt in range(RETRIES):
        resp = session.request(method, url, headers=HEADERS, timeout=30, **kwargs)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (403, 451):
            raise FetchFailed(f"{url} refuses this location (HTTP {resp.status_code})")
        last = resp.status_code
        if resp.status_code == 429 or resp.status_code >= 500:
            sleep(min(2.0 ** attempt, 30.0))
            continue
        raise FetchFailed(f"{url} returned HTTP {resp.status_code}")
    raise FetchFailed(f"{url} still failing after {RETRIES} attempts (last HTTP {last})")


def _frame(rows, venue, instrument):
    frame = pd.DataFrame(rows, columns=["time", "rate_1h"])
    frame["time"] = pd.to_datetime(frame["time"], unit="ms", utc=True)
    frame["rate_1h"] = pd.to_numeric(frame["rate_1h"], errors="raise")
    frame["venue"], frame["instrument"] = venue, instrument
    return frame[COLUMNS]


def _finish(frame, cutoff):
    """Cut at the holdout, order, and refuse duplicates rather than hide them."""
    frame = frame[frame["time"] < pd.Timestamp(_ms(cutoff), unit="ms", tz="UTC")].sort_values("time")
    frame["time"] = frame["time"].dt.floor("h")
    if frame["time"].duplicated().any():
        raise FetchFailed("two funding rows for the same hour; the venue's paging overlapped")
    return frame.reset_index(drop=True)


def fetch_deribit(session, instrument, start, cutoff, sleep=time.sleep, pace=None):
    """Hourly funding for one Deribit perpetual from `start` up to, not
    including, `cutoff`."""
    rows, lo = [], _ms(start)
    hi_limit = _ms(cutoff) - 1
    step = CHUNK_DAYS * 86_400_000
    while lo <= hi_limit:
        hi = min(lo + step - 1, hi_limit)
        body = _request(session, "GET", DERIBIT, sleep=sleep, params={
            "instrument_name": instrument, "start_timestamp": lo, "end_timestamp": hi})
        if "result" not in body:
            raise FetchFailed(f"Deribit answered without a result: {str(body)[:120]}")
        rows += [(r["timestamp"], r["interest_1h"]) for r in body["result"]]
        lo = hi + 1
        (pace or sleep)(1.0 / CALLS_PER_SECOND)
    return _finish(_frame(rows, "deribit", instrument), cutoff)


def fetch_hyperliquid(session, coin, start, cutoff, sleep=time.sleep, pace=None):
    """Hourly funding for one Hyperliquid coin from `start` up to, not
    including, `cutoff`."""
    rows, lo, limit = [], _ms(start), _ms(cutoff)
    while lo < limit:
        page = _request(session, "POST", HYPERLIQUID, sleep=sleep,
                        json={"type": "fundingHistory", "coin": coin, "startTime": lo})
        if not isinstance(page, list):
            raise FetchFailed(f"Hyperliquid answered with {str(page)[:120]}")
        if not page:
            break
        rows += [(r["time"], r["fundingRate"]) for r in page]
        newest = max(r["time"] for r in page)
        if newest < lo:
            raise FetchFailed("Hyperliquid paging did not advance")
        lo = newest + 1
        (pace or sleep)(1.0 / CALLS_PER_SECOND)
    return _finish(_frame(rows, "hyperliquid", coin), cutoff)


def daily_funding(frame):
    """The funding a position held through each UTC day paid (positive: longs
    pay shorts), as a fraction of notional. NaN for a day without all 24
    hours, never a partial sum."""
    hours = frame.set_index("time")["rate_1h"]
    day = hours.index.tz_convert("UTC").floor("D").tz_localize(None)
    grouped = hours.groupby(day)
    total, count = grouped.sum(), grouped.count()
    out = total.where(count == HOURS_PER_DAY)
    full = pd.date_range(out.index.min(), out.index.max(), freq="D")
    return out.reindex(full).rename("funding")


def write(frame, name):
    os.makedirs(root(), exist_ok=True)
    path = os.path.join(root(), f"{name}.parquet")
    tmp = path + ".tmp"
    frame.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    return path


def read(name):
    return pd.read_parquet(os.path.join(root(), f"{name}.parquet"))
