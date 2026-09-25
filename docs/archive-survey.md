# The archive, measured rather than assumed

Verified 2026-09-23 against `~/market-data/sharadar.db` (19.7 GB), opened
read-only. My planning notes carry a table of spans that I decided to verify
rather than trust, because the archive grows and has been repaired more than
once. This is that verification.

## Spans and row counts, as measured

| Table | Date column | First | Last | Rows |
|---|---|---|---|---|
| `prices` | `date` | 1997-12-31 | 2026-09-22 | 46,476,349 |
| `fundprices` | `date` | 1997-12-31 | 2026-09-22 | 15,657,520 |
| `dailyfundamentals` | `date` | 2016-01-04 | 2026-09-22 | 14,683,788 |
| `fundamentals` | `datekey` | 1990-06-06 | 2026-09-22 | 3,305,150 |
| `insiders` | `filingdate` | 2008-01-02 | 2026-09-21 | 11,550,444 |
| `actions` | `date` | 1997-12-31 | 2026-09-22 | 684,516 |
| `events` | `date` | 1993-11-08 | 2026-09-22 | 2,550,979 |
| `sp500` | `date` | 1957-03-04 | 2026-09-21 | 65,212 |
| `holdings` | `calendardate` | 2013-06-30 | 2026-06-30 | 79,638,808 |
| `tickers` | — | — | — | 78,904 |

## Three corrections to the planning table

The planning table is right about every span that matters. Three entries are narrower
there than the archive actually is, and one of them changes what is testable:

- **`events` starts 1993-11-08, not "full".** Nearly five years of corporate
  event history predates the price data, so events alone cannot anchor a study;
  the price table is the binding constraint at 1997-12-31.
- **`sp500` starts 1957-03-04.** Index membership reaches back forty years
  before the prices do. Useful for identifying what a name *was*, never for a
  backtest window.
- **`holdings` ends 2026-06-30, not "current".** Quarterly with a 45-day filing
  lag, so the most recent usable quarter is nearly three months stale at any
  moment. Any 13F study must treat the last quarter as unavailable rather than
  as zero.

Everything else matches: `insiders` genuinely starts 2008-01-02 and silently
caps every insider study; `dailyfundamentals` genuinely starts 2016-01-04 and is
the binding constraint on any market-cap-conditioned work.

## Watermarks

Every table in `data_coverage` is frozen before **2025-08-11**, with the note
"full-depth bulk load; entitlement reduced to one year 2026-08". The entitlement
now reaches back one year; everything before that date was downloaded when the
subscription was deeper and cannot be re-fetched at any price.

That is the whole reason the archive is treated as an archive rather than a
cache. `market_core.sharadar.assert_writable(table, earliest_affected)` is
called at the top of anything that deletes, drops or reloads, and the bulk
loaders are never run.

The file sits at mode 444 between refresh runs and has exactly one writer, the
job in `~/market-data/market-archive`. Everything here opens it read-only.

## Schema notes that will matter later

- `prices` carries `permaticker`, so a study can be keyed on stable company
  identity rather than on a ticker the vendor rewrites after a rename.
- `tickers` carries `firstpricedate` and `lastpricedate`, which is what a
  point-in-time universe is built from. It carries `sector`, `industry`,
  `scalemarketcap`, `exchange` and `isdelisted`, but no SIC code.
- `dailyfundamentals.marketcap` is stored as text and denominated in millions.
  It is computed by the vendor from raw price and raw shares and is correct;
  market cap is never to be derived from the adjusted close.
- `close` is split-adjusted; `closeadj` adds dividends.
- ETF and fund bars live in `fundprices`, not `prices`. Every benchmark comes
  from there.

## Not in the archive

Options, futures, commodities, intraday or tick data, order book,
short-interest or borrow costs, news, sentiment, FX. Every short result this lab
produces is therefore an upper bound, and says so.
