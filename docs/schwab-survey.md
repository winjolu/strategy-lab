# Schwab market-data API: what it serves, measured 2026-11-24

Measured with `scripts/schwab_probe.py` and a follow-up on option history,
read-only, through an app registered for market data only. The app cannot
place orders.

## Findings

| Question | Answer |
|---|---|
| Equity daily history | SPY back to 1993-01-29, 8,514 rows, open/high/low/close/volume. Prices are not adjusted for dividends: the 2020-03-16 close is 239.85, the archive's raw close exactly, against an adjusted 218.50. |
| Current option chain | Served live, not delayed. SPY: 31 expirations from same-day to 2029-01-19, 10 strikes each side requested. Each contract carries bid, ask, sizes, last, mark, volatility, delta, gamma, theta, vega, rho, open interest, volume, quote and trade times. |
| Option price history, live contracts | Daily bars, sparse. A same-day contract returned 4 rows; a 2029-01-19 call returned 13 rows since 2026-09-14, apparently only days it traded. |
| Option price history, expired contracts | None. Contracts expired 2026-11-20, 2026-10-16 and 2025-12-19 all returned HTTP 200 with zero rows. |
| Token | Access token lasts 30 minutes and refreshes itself; the refresh token lasts 7 days, after which a browser login is needed again. |

## What follows

- **No option strategy can be backtested on Schwab data.** History disappears
  when a contract expires, and what exists for live contracts is a few sparse
  daily bars without the quotes or volatility a backtest of option selling
  needs. `vrp-short-vol` and the other option candidates stay blocked on data:
  either a purchased history or one recorded forward from today.
- **Recording forward is the free route.** A daily end-of-day snapshot of the
  SPY chain (quotes, volatility, greeks, open interest) starts a history that
  no one else is keeping for this account. It needs the browser login about
  weekly, or the recording stops; a lapsed login has to be visible as a gap,
  not as a quiet day.
- **Equity history is a second source the archive did not have.** Schwab's
  raw daily opens are the independent check `overnight-index-hold` needs
  before it runs.
