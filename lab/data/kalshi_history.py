"""Kalshi's settled-market history, fetched for a registered strategy.

Prices and outcomes of settled markets are served by two tiers of the API:
the live endpoints for recent settlements and `/historical` for older ones.
This pulls the universe a registration names into Parquet under the lab's
data directory, outside the checkout.

Three properties matter more than speed:

* **The holdout is cut here.** The registration's `holdout_start` is read
  from the registry, and any market that settled on or after it is dropped
  before it is written, along with every candle that ended on or after it.
  Nothing past that date is ever on disk, so no later step can read it by
  mistake. Stage 3 fetches the holdout by passing an explicit later date.
* **Resumable.** A full pull is hundreds of thousands of calls. A series is
  marked done in the manifest only after its file is written, so an
  interrupted run resumes at the first unfinished series and a failed one
  is never mistaken for an empty one.
* **Nothing derived from the outcome selects what is fetched.** The universe
  is chosen from static series attributes (category, frequency), and every
  settled market in those series is kept, winners and losers alike.
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd
import requests

from lab import config
from lab.engine import registry
from lab.recorders import kalshi as _rec
from lab.recorders.kalshi import FetchFailed

CATEGORIES = ("Sports", "Entertainment", "Politics", "Elections")
EXCLUDED_FREQUENCIES = ("hourly", "fifteen_min")
CANDLE_MINUTES = 60
CHUNK_DAYS = 150
WORKERS = 4
CALLS_PER_SECOND = 6.0
RETRIES = 10  # patient: a full pull is hours long and a 429 is a pause, not a failure


class Throttled:
    """Caps calls per second across every thread sharing it. The recorder
    polls from the same address, so the fetch leaves room for it."""

    def __init__(self, session, per_second=CALLS_PER_SECOND, clock=time.monotonic, sleep=time.sleep):
        self.session, self.gap = session, 1.0 / per_second
        self._clock, self._sleep, self._next = clock, sleep, 0.0
        self._lock = threading.Lock()

    def get(self, *args, **kwargs):
        with self._lock:
            now = self._clock()
            wait = self._next - now
            self._next = max(now, self._next) + self.gap
        if wait > 0:
            self._sleep(wait)
        return self.session.get(*args, **kwargs)


def _get(session, path, params):
    return _rec._get(session, path, params, retries=RETRIES)
PAGE = 1000

MARKET_COLUMNS = ["ticker", "event_ticker", "market_type", "title", "yes_sub_title", "result",
                  "open_time", "close_time", "latest_expiration_time", "settlement_ts",
                  "settlement_value_dollars", "volume_fp", "tier"]
CANDLE_COLUMNS = ["ticker", "end_period_ts", "yes_bid_close", "yes_ask_close", "price_close",
                  "volume", "open_interest"]


def root():
    return os.path.join(config.data_dir(), "kalshi_history")


def _epoch(text):
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())


def _holdout(strategy_id, directory=None):
    spec = registry.require_registered(strategy_id, directory)
    return int(datetime.strptime(spec["registration"]["holdout_start"], "%Y-%m-%d")
               .replace(tzinfo=timezone.utc).timestamp())


def _atomic(frame, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    frame.to_parquet(tmp, index=False)
    os.replace(tmp, path)


class Manifest:
    """Which series are finished for each stage, and against which cutoff."""

    def __init__(self, cutoff):
        self.path = os.path.join(root(), "manifest.json")
        self.cutoff = cutoff
        state = json.load(open(self.path)) if os.path.exists(self.path) else {}
        if state.get("cutoff") not in (None, cutoff):
            state = {}  # a different cutoff is a different dataset
        self.state = state
        self.state["cutoff"] = cutoff
        self.state.setdefault("markets", [])
        self.state.setdefault("candles", [])

    def done(self, stage, series):
        return series in self.state[stage]

    def mark(self, stage, series):
        self.state[stage].append(series)
        os.makedirs(root(), exist_ok=True)
        tmp = self.path + ".tmp"
        json.dump(self.state, open(tmp, "w"))
        os.replace(tmp, self.path)


def fetch_series(session):
    body = _get(session, "/series", {})
    frame = pd.DataFrame(body["series"])
    keep = ["ticker", "title", "category", "frequency", "fee_type", "fee_multiplier"]
    frame = frame.reindex(columns=keep)
    _atomic(frame, os.path.join(root(), "series.parquet"))
    return frame


def fetch_fee_changes(session):
    """Dated changes to each series' fee multiplier, historical included.
    The series listing states only today's value."""
    body = _get(session, "/series/fee_changes", {"show_historical": "true"})
    frame = pd.DataFrame(body["series_fee_change_arr"]).reindex(
        columns=["series_ticker", "scheduled_ts", "fee_type", "fee_multiplier", "id"])
    _atomic(frame, os.path.join(root(), "fee_changes.parquet"))
    return frame


def universe(series):
    """Series in the registered categories, excluding fast-cycling ones.
    Static attributes only; nothing here can see a price or an outcome."""
    return series[series["category"].isin(CATEGORIES)
                  & ~series["frequency"].isin(EXCLUDED_FREQUENCIES)]["ticker"].tolist()


def _paged(session, path, params):
    cursor, out = None, []
    while True:
        q = dict(params, limit=PAGE, **({"cursor": cursor} if cursor else {}))
        body = _get(session, path, q)
        out += body.get("markets", [])
        cursor = body.get("cursor")
        if not cursor:
            return out


def fetch_markets(session, series_ticker, cutoff):
    rows = []
    for tier, path, extra in (("historical", "/historical/markets", {}),
                              ("live", "/markets", {"status": "settled"})):
        for m in _paged(session, path, dict(extra, series_ticker=series_ticker)):
            m["tier"] = tier
            rows.append(m)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=MARKET_COLUMNS)
    frame = frame[~frame["ticker"].str.startswith("KXMVE")]
    frame = frame.drop_duplicates("ticker", keep="first")  # historical listed first
    frame = frame[frame["market_type"] == "binary"]
    frame = frame[frame["settlement_ts"].notna() & (frame["settlement_ts"] != "")]
    frame = frame[frame["settlement_ts"].map(_epoch) < cutoff]
    return frame.reindex(columns=MARKET_COLUMNS).reset_index(drop=True)


def windows(start, end, days=CHUNK_DAYS):
    step = days * 86400
    return [(a, min(a + step, end)) for a in range(start, end, step)]


def fetch_candles_for(session, market, series_ticker, cutoff):
    start = _epoch(market["open_time"])
    end = min(_epoch(market["close_time"]) + 3600, cutoff)
    if end <= start:
        return []
    rows = []
    for a, b in windows(start, end):
        if market["tier"] == "historical":
            path = f"/historical/markets/{market['ticker']}/candlesticks"
        else:
            path = f"/series/{series_ticker}/markets/{market['ticker']}/candlesticks"
        body = _get(session, path, {"start_ts": a, "end_ts": b, "period_interval": CANDLE_MINUTES})
        for c in body.get("candlesticks", []):
            if c["end_period_ts"] >= cutoff:
                continue
            rows.append({
                "ticker": market["ticker"], "end_period_ts": c["end_period_ts"],
                "yes_bid_close": (c.get("yes_bid") or {}).get("close"),
                "yes_ask_close": (c.get("yes_ask") or {}).get("close"),
                "price_close": (c.get("price") or {}).get("close"),
                "volume": c.get("volume"), "open_interest": c.get("open_interest"),
            })
    return rows


def fetch_candles(session, series_ticker, markets, cutoff, workers=WORKERS):
    traded = markets[pd.to_numeric(markets["volume_fp"], errors="coerce").fillna(0) > 0]
    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(
            lambda m: fetch_candles_for(session, m, series_ticker, cutoff),
            traded.to_dict("records")))
    rows = [r for chunk in results for r in chunk]
    return pd.DataFrame(rows, columns=CANDLE_COLUMNS)


def run(strategy_id, session=None, series_filter=None, max_series=None, registry_directory=None, log=None):
    """Fetch everything the registration's universe needs, before its holdout."""
    session = session or Throttled(requests.Session())
    cutoff = _holdout(strategy_id, registry_directory)
    manifest = Manifest(cutoff)
    series = fetch_series(session)
    fetch_fee_changes(session)
    chosen = universe(series)
    if series_filter:
        chosen = [s for s in chosen if s in series_filter]
    todo = [s for s in chosen if not (manifest.done("markets", s) and manifest.done("candles", s))]
    if max_series is not None:
        todo = todo[:max_series]
    report = {"universe": len(chosen), "attempted": 0, "markets": 0, "candles": 0, "empty": 0}
    started = time.time()
    for s in todo:
        report["attempted"] += 1
        if log:
            log(f"[{report['attempted']}/{len(todo)}] {s} after {time.time() - started:.0f}s; "
                f"{report['markets']} markets, {report['candles']} candles so far")
        mpath = os.path.join(root(), "markets", f"{s}.parquet")
        if manifest.done("markets", s):
            markets = pd.read_parquet(mpath)
        else:
            markets = fetch_markets(session, s, cutoff)
            _atomic(markets, mpath)
            manifest.mark("markets", s)
        report["markets"] += len(markets)
        if markets.empty:
            report["empty"] += 1
            _atomic(pd.DataFrame(columns=CANDLE_COLUMNS), os.path.join(root(), "candles", f"{s}.parquet"))
            manifest.mark("candles", s)
            continue
        candles = fetch_candles(session, s, markets, cutoff)
        _atomic(candles, os.path.join(root(), "candles", f"{s}.parquet"))
        manifest.mark("candles", s)
        report["candles"] += len(candles)
    return report


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("strategy")
    p.add_argument("--max-series", type=int)
    p.add_argument("--series", nargs="*")
    a = p.parse_args(argv)
    try:
        print(run(a.strategy, series_filter=a.series, max_series=a.max_series, log=lambda t: print(t, flush=True)))
    except FetchFailed as exc:
        print(f"fetch failed, series left unfinished: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
