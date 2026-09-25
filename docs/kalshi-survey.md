# What the Kalshi API serves, measured 2026-09-23

Read from the public API (`api.elections.kalshi.com/trade-api/v2`) without
authentication. This corrects the catalogue, which says settled markets are
purged and nothing can be backtested. That is wrong for prices and outcomes
and right for order book depth.

## Served

- **Settled markets and results.** Two tiers. The live `/markets` endpoint
  holds recent settlements; `/historical/cutoff` reports the boundary, which
  was 2026-07-25 on this date. Before it, `/historical/markets` serves them.
  Reached back at least to `FED-24DEC-T4.50` (opened 2023-07-06) and
  `PRES-2024-DJT`. Full depth not yet measured.
- **Candlesticks**, per market, at 1, 60 and 1440 minute intervals, with
  open/high/low/close for trade price, yes bid and yes ask, plus volume and
  open interest. `/historical/markets/{ticker}/candlesticks`. This is
  historical top-of-book prices, without sizes.
- **Trade prints**, `/historical/trades`, with count, both prices and the
  taker side. A quiet market returned its whole history in one page back to
  2023-08-25.
- **Order book, live only.** `/markets/{ticker}/orderbook` returns every
  level with sizes; `depth=1` returns the best. No history of it is served.

## Not served

- Order book depth at any past moment. Candlesticks give bid and ask prices
  but not the size resting at them, so anything that needs depth (whether a
  position of a given size could have been filled) cannot be reconstructed.
- Anything for multivariate combo markets is mostly noise: the first pages
  of every listing are `KXMVE...` combinations, which are not the markets
  the candidates trade.

## What that changes

The strategies whose test needs settled prices and outcomes
(`event-narrative-fade`, the longshot-bias test) are **not perishable** and
can be tested from `/historical` now. The recorder's unique value is depth
and intra-minute state, which matters for the executability of the
arbitrage candidates and not for the bias tests. The urgency stands for the
former and is withdrawn for the latter.

## Coverage, counted 2026-09-23

Counted by series across the historical and live tiers, by settlement month.
The historical endpoint ignores `min_close_ts` and `max_close_ts` and serves
newest first, so coverage has to be counted one series at a time with
`series_ticker`, which it does honour.

| series | category | markets | first | last |
|---|---|---|---|---|
| KXMLBGAME | Sports | 9,362 | 2025-04 | 2026-09 |
| KXNBAGAME | Sports | 2,898 | 2025-04 | 2026-06 |
| KXNHLGAME | Sports | 3,136 | 2025-04 | 2026-09 |
| KXNFLGAME | Sports | 828 | 2025-08 | 2026-09 |
| KXSB | Sports | 36 | 2025-02 | 2026-02 |
| KXOSCARPIC | Entertainment | 70 | 2022-03 | 2026-03 |
| KXTIME | Entertainment | 60 | 2023-12 | 2025-12 |

Per-game sports begins in April 2025. Entertainment and politics reach 2022.
There are 14,329 series; the fee is `quadratic` with a multiplier of 1 on all
but 36 of them.

**`close_time` is the realised close, not the scheduled one.** On
`PRES-2024-DJT` it is the inauguration, 2025-01-20, while
`latest_expiration_time`, fixed at listing, is 2025-11-05. Any rule that
measures time to `close_time` reads the outcome on a market that can close
early.

## The history fetcher

`lab/data/kalshi_history.py` pulls the series list, every settled binary
market in the registered universe, and hourly candles for markets that
traded, into Parquet. The universe is chosen from static series attributes
only: category in Sports, Entertainment, Politics or Elections, and a
frequency other than hourly or fifteen-minute. That is 10,461 of 14,330
series. Historical candles have no batch endpoint, so it is one call per
market, about three markets a second. Candles are dense hourly even through
hours with no trades, about 1,000 per market. The holdout is cut at fetch
time, not at read time.

## The fee, checked 2026-09-23

Against the exchange's published July 2026 schedule (12 pages, read in a
browser because the file host refuses scripted downloads):

- **Formula confirmed:** `ceil_to_cent(0.07 x M x C x P x (1 - P))` per taker
  order. The prose says the fee is rounded to a "centicent"; the general fees
  table says otherwise and the table is right, since one contract at 10
  cents is listed at $0.01 and 100 contracts at 5 cents at $0.34, both whole
  cents rounded up. All 18 rows of that table are test cases.
- **No settlement fee, no membership fee.** Maker fees exist only for series
  the schedule names.
- **Multipliers:** the API's `fee_multiplier` matched the schedule's
  per-series list on all 13 series I read, zero-fee ones included. The other
  pages of that list were not read.
- **They change over time.** `/series/fee_changes` records 149 changes across
  128 series from 2025-10-04, and its last entry per series equals the
  current listing in every case. Before 2025-10-04 nothing is recorded. 19
  series in the registered universe, KXMLBGAME among them, went from 1 to 0.5
  on 2026-08-07, so the current listing understates their earlier fees by
  half. `lab/engine/event_costs.py` reads the timeline and assumes 1, the
  schedule's default, before a series' first change.

## Open

- How far back `/historical` goes, and whether it is complete or sampled.
- Whether live-tier data moves to historical at the cutoff or is dropped.
- Rate limits; none advertised in the headers.

## The recorder, started 2026-09-23

`lab/recorders/kalshi.py`, scheduled by `ops/kalshi_launchd.py` as two user
LaunchAgents. Output is under `recordings/kalshi/` in the lab's data
directory, outside the checkout.

- **Quotes**, every 5 minutes: best yes and no bid and ask with sizes, last
  price, volume and open interest for every open non-combination market,
  about 128,700 of them, of which 43,000 have no quotes at all. Only rows
  that changed since the last poll are written. A poll takes about 22
  seconds; one a minute later wrote 8,619 rows, 0.3 MB.
- **Metadata**, once per market when first seen: title, rules, open and close
  times.
- **Settlements**, alongside quotes, from a watermark.
- **Depth**, every 15 minutes: every level on both sides for the 300 markets
  with the most open interest that quote both sides.
- **`runs.jsonl`** logs every attempt, failures included, so a machine asleep
  shows as a gap and not as a quiet market.

A failed page aborts the poll and writes nothing, since a partial listing
looks like a complete one with markets missing.

Storage is unmeasured over a day. At 0.3 to 0.5 MB per poll the projection
is 100 to 150 MB a day; check it after a day and thin the quote set if it
runs higher. launchd does not run while the machine sleeps.

Read with `python -m lab.recorders.kalshi status`. Remove with
`python ops/kalshi_launchd.py uninstall`.
