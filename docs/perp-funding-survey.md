# Perpetual funding-rate history: what is reachable, measured 2026-10-05

The queue called the test data for `crypto-perp-funding-carry` "free and deep
from large offshore exchanges (Binance, Bybit, OKX)". Measured from this
machine, that is wrong for all three. Public funding history is deep at one
venue and shallow or blocked at the rest.

A perpetual future is a contract with no expiry that stays near the spot price
because one side pays the other a periodic funding rate. A spot holder who is
short the perpetual collects that rate when longs are paying, with price risk
cancelled. Only public read endpoints were called, one page per venue.

| Venue | Result | Depth |
|---|---|---|
| Binance (USDT-margined) | HTTP 200 body: "service unavailable from a restricted location" | none from here |
| Bybit | HTTP 403, blocked by its CDN for this country | none from here |
| OKX | works; 8-hourly funding | 296 rows, back to 2026-06-29, about three months |
| Kraken Futures | works; hourly | 8,858 rows, back to 2025-10-01, one year |
| Hyperliquid | works; hourly, POST `info` with `fundingHistory` | BTC back to 2023-05-12, about three and a half years |
| Deribit | works; hourly, `public/get_funding_rate_history` | returned a full 240 hourly rows for a ten-day window in each of 2019 to 2023 |

Nothing here was worked around. The two blocked venues are blocked by the
operator for this location, and the test needs no route past that.

OKX daily candles for the perpetual go back to 2019-11 and for spot to
2017-10, so price history is not the limit; funding history is.

## What follows

- **Deribit is the only deep source reachable**, and it lists only BTC and ETH
  perpetuals. They are coin-margined (inverse): the contract is settled in the
  coin, not in dollars, so a hedged position carries a small convexity term
  that a dollar-margined perpetual does not. The test has to say how it treats
  that.
- **Hyperliquid covers many coins but only since 2023-05**, three and a half
  years. Under the evaluation rules that is a three-year training window and
  almost no holdout, so on its own it cannot be scored; it can only
  cross-check Deribit on the coins both list.
- **A single venue's funding is one venue's rule.** Each exchange defines the
  rate, the interval and the clamp differently, so a result on Deribit says
  nothing certain about any other venue's carry.
- **Testing never needed the venue to be tradeable from this account.** Whether
  Kalshi's 25 perpetual series are, how their funding is set and what history
  they serve is still unchecked and is the separate gate on trading it.

## Contamination note

Before this survey, one page per venue was read to measure depth. For OKX that
included two recent funding values, and for Kraken and Hyperliquid the first
rate of each listing. None of it was analysed. The registration for this
strategy states it, since the most recent year is the natural holdout.
