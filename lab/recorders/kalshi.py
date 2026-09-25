"""Forward recorder for Kalshi, writing to the lab's recorder directory.

Prices and outcomes of settled markets are served by the API, so they are
not what this exists for. What is not served anywhere is the order book as
it stood at a past moment, so that is what accumulates here: the best
quotes with their sizes across every open market, and full depth for the
most liquid ones.

Design constraints, each from the failure it prevents:

* **Only changes are stored.** A full snapshot of the ~128,000 open
  markets is a few megabytes and most rows do not move between polls, so
  a poll writes the rows whose quote changed. State is a full snapshot and
  is replaced atomically.
* **A failed poll writes nothing.** A partial listing would look like a
  full one with markets missing. Any page that cannot be fetched after
  retries aborts the poll and leaves the state as it was.
* **Gaps are visible.** Every attempt, including failures, appends a line
  to `runs.jsonl`, so a laptop asleep for six hours shows as six hours
  rather than as a quiet market.
* **Combination markets are dropped.** The API fills its listings with
  `KXMVE` multivariate combinations, which no candidate trades.
* **Nothing is written inside the checkout.** The directory is the lab's
  recorder directory under Application Support, outside any synced folder.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from lab import config

BASE = "https://api.elections.kalshi.com/trade-api/v2"
PAGE = 1000
RETRIES = 5
DEPTH_MARKETS = 300

QUOTE_COLUMNS = ["yes_bid_dollars", "yes_ask_dollars", "yes_bid_size_fp", "yes_ask_size_fp",
                 "no_bid_dollars", "no_ask_dollars", "last_price_dollars", "volume_fp",
                 "open_interest_fp"]
KEY = "ticker"
STATIC_COLUMNS = ["ticker", "event_ticker", "title", "subtitle", "market_type", "open_time",
                  "close_time", "rules_primary"]
SETTLED_COLUMNS = ["ticker", "event_ticker", "result", "settlement_ts", "settlement_value_dollars",
                   "close_time", "volume_fp"]


class FetchFailed(RuntimeError):
    """A page could not be fetched after retries; the poll writes nothing."""


def root():
    return os.path.join(config.recorder_dir(), "kalshi")


def _now():
    return datetime.now(timezone.utc)


def _get(session, path, params, retries=None):
    last = None
    for attempt in range(retries or RETRIES):
        wait = min(2 ** attempt, 30)
        try:
            r = session.get(BASE + path, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
            if r.status_code not in (429, 500, 502, 503, 504):
                break
            if r.status_code == 429:
                try:
                    wait = max(wait, min(float(r.headers.get("Retry-After", 0)), 120))
                except (TypeError, ValueError, AttributeError):
                    pass
        except requests.RequestException as exc:
            last = type(exc).__name__
        time.sleep(wait)
    raise FetchFailed(f"{path} {params.get('cursor', '')[:12]}: {last}")


def _pages(session, path, params, key):
    cursor, out = None, []
    while True:
        q = dict(params, limit=PAGE, **({"cursor": cursor} if cursor else {}))
        body = _get(session, path, q)
        out += [m for m in body.get(key, []) if not m["ticker"].startswith("KXMVE")]
        cursor = body.get("cursor")
        if not cursor:
            return out


def fetch_open(session):
    rows = _pages(session, "/markets", {"status": "open", "mve_filter": "exclude"}, "markets")
    frame = pd.DataFrame(rows)
    for c in QUOTE_COLUMNS:
        if c not in frame:
            frame[c] = None
    return frame


def changed(previous, current):
    """Rows of `current` that are new or whose quote differs from `previous`."""
    cur = current[[KEY] + QUOTE_COLUMNS].astype({c: "string" for c in QUOTE_COLUMNS})
    if previous is None or previous.empty:
        return cur
    prev = previous[[KEY] + QUOTE_COLUMNS].astype({c: "string" for c in QUOTE_COLUMNS})
    merged = cur.merge(prev, on=KEY, how="left", suffixes=("", "_prev"), indicator=True)
    same = (merged["_merge"] == "both")
    for c in QUOTE_COLUMNS:
        same &= (merged[c].fillna("") == merged[c + "_prev"].fillna(""))
    return cur[~same.values].reset_index(drop=True)


def _atomic_parquet(frame, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    frame.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _log(entry):
    os.makedirs(root(), exist_ok=True)
    with open(os.path.join(root(), "runs.jsonl"), "a") as handle:
        handle.write(json.dumps(entry) + "\n")


def _state_path():
    return os.path.join(root(), "state.parquet")


def _load_state():
    path = _state_path()
    return pd.read_parquet(path) if os.path.exists(path) else None


def record_quotes(session=None, now=None):
    session, now, t0 = session or requests.Session(), now or _now(), time.time()
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    try:
        current = fetch_open(session)
        previous = _load_state()
        delta = changed(previous, current)
        if len(delta):
            delta.insert(0, "ts", now.isoformat())
            _atomic_parquet(delta, os.path.join(root(), "quotes", f"date={now:%Y-%m-%d}", f"{stamp}.parquet"))
        known = set(previous[KEY]) if previous is not None else set()
        new = current[~current[KEY].isin(known)]
        if len(new):
            statics = new.reindex(columns=STATIC_COLUMNS)
            statics.insert(0, "first_seen", now.isoformat())
            _atomic_parquet(statics, os.path.join(root(), "markets", f"date={now:%Y-%m-%d}", f"{stamp}.parquet"))
        _atomic_parquet(current[[KEY] + QUOTE_COLUMNS], _state_path())
    except Exception as exc:
        _log({"ts": now.isoformat(), "job": "quotes", "ok": False, "error": f"{type(exc).__name__}: {exc}",
              "seconds": round(time.time() - t0, 1)})
        raise
    entry = {"ts": now.isoformat(), "job": "quotes", "ok": True, "markets": int(len(current)),
             "changed": int(len(delta)), "new": int(len(new)), "seconds": round(time.time() - t0, 1)}
    _log(entry)
    return entry


def record_settlements(session=None, now=None):
    """Outcomes of recently settled markets. The API serves these, so the
    log is a convenience and a cross-check rather than the perishable part."""
    session, now, t0 = session or requests.Session(), now or _now(), time.time()
    mark = os.path.join(root(), "settled.watermark")
    since = int(open(mark).read()) if os.path.exists(mark) else int(now.timestamp()) - 86400
    try:
        rows = _pages(session, "/markets", {"status": "settled", "min_settled_ts": since,
                                            "mve_filter": "exclude"}, "markets")
        frame = pd.DataFrame(rows).reindex(columns=SETTLED_COLUMNS)
        if len(frame):
            frame.insert(0, "recorded", now.isoformat())
            _atomic_parquet(frame, os.path.join(root(), "settled", f"date={now:%Y-%m-%d}",
                                                f"{now:%Y%m%dT%H%M%SZ}.parquet"))
        os.makedirs(root(), exist_ok=True)
        with open(mark, "w") as handle:
            handle.write(str(int(now.timestamp()) - 300))  # overlap; readers deduplicate on ticker
    except Exception as exc:
        _log({"ts": now.isoformat(), "job": "settled", "ok": False, "error": f"{type(exc).__name__}: {exc}"})
        raise
    entry = {"ts": now.isoformat(), "job": "settled", "ok": True, "settled": int(len(frame)),
             "seconds": round(time.time() - t0, 1)}
    _log(entry)
    return entry


def depth_targets(state, n=DEPTH_MARKETS):
    """The n most liquid markets by open interest among those quoted both sides."""
    s = state.copy()
    s["oi"] = pd.to_numeric(s["open_interest_fp"], errors="coerce").fillna(0.0)
    two = (pd.to_numeric(s["yes_bid_dollars"], errors="coerce") > 0) & \
          (pd.to_numeric(s["yes_ask_dollars"], errors="coerce") > 0)
    return s[two].nlargest(n, "oi")[KEY].tolist()


def record_depth(session=None, now=None, n=DEPTH_MARKETS):
    session, now, t0 = session or requests.Session(), now or _now(), time.time()
    state = _load_state()
    if state is None:
        raise FetchFailed("no quote state yet; run `quotes` first")
    levels, failed = [], 0
    for ticker in depth_targets(state, n):
        try:
            book = _get(session, f"/markets/{ticker}/orderbook", {})["orderbook_fp"]
        except FetchFailed:
            failed += 1
            continue
        for side in ("yes", "no"):
            for price, size in book.get(f"{side}_dollars") or []:
                levels.append((ticker, side, price, size))
    frame = pd.DataFrame(levels, columns=["ticker", "side", "price_dollars", "size_fp"])
    if len(frame):
        frame.insert(0, "ts", now.isoformat())
        _atomic_parquet(frame, os.path.join(root(), "depth", f"date={now:%Y-%m-%d}", f"{now:%Y%m%dT%H%M%SZ}.parquet"))
    entry = {"ts": now.isoformat(), "job": "depth", "ok": failed == 0, "markets": n, "levels": int(len(frame)),
             "failed_books": failed, "seconds": round(time.time() - t0, 1)}
    _log(entry)
    return entry


def status():
    path = os.path.join(root(), "runs.jsonl")
    if not os.path.exists(path):
        return "no runs recorded"
    runs = pd.read_json(path, lines=True)
    out = []
    for job, g in runs.groupby("job"):
        ok = g[g["ok"]]
        last = ok["ts"].max() if len(ok) else None
        out.append(f"{job}: {len(ok)} ok, {len(g) - len(ok)} failed, last ok {last}")
    return "\n".join(out)


def main(argv=None):
    argv = argv or sys.argv[1:]
    job = argv[0] if argv else "quotes"
    if job == "status":
        print(status())
        return 0
    fn = {"quotes": lambda: (record_quotes(), record_settlements()), "depth": record_depth}.get(job)
    if fn is None:
        print("usage: python -m lab.recorders.kalshi [quotes|depth|status]", file=sys.stderr)
        return 2
    try:
        print(fn())
        return 0
    except FetchFailed as exc:
        print(f"poll failed, nothing written: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
