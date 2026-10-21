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

## Kalshi, measured 2026-10-21

Kalshi lists 29 perpetuals through a separate API under `/trade-api/v2/margin`,
public for reading, and serves its whole funding history in one request: 420
eight-hourly settlements per contract from launch on 2026-06-03, with no gaps.
The contracts are dollar-margined and linear, cleared by Kalshi Klear, with
leverage up to 6x. Each market states its rule's parameters: a cap of 2% per
interval, and for crypto a dead band of 0.01% per interval, below which the rate
is set to zero. That band is about 11% a year annualised, so funding is zero
unless the premium is large.

| Contract | Mean funding, launch to 2026-10-21 | Last 30 days | Intervals at zero |
|---|---|---|---|
| BTC | 9.0% a year | 13.0% | 49% |
| ETH | −1.0% | 1.2% | 84% |
| SOL | 3.6% | 15.6% | 81% |
| XRP | 6.1% | 19.6% | 59% |

Over 2026-06-04 to 2026-10-11, Deribit paid 3.2% a year on BTC and 2.5% on ETH,
and BIL returned 2.1% a year over June to October. Kalshi's BTC funding has run
well above both. Its open interest is small, about $19 million on BTC, and the
rate looks like the price of US retail demand for leverage on one venue.

What this does and does not settle:

- **Four and a half months is not a test.** The evaluation rules need three
  years of training and a year of holdout. Kalshi's history cannot be scored
  before mid-2027 at the earliest, and only for a strategy registered on that
  venue's own rule. Nothing needs recording in the meantime: the endpoint serves
  every settlement since launch.
- **The hedge is a different trade here.** On Deribit the coin is the
  collateral for an inverse contract, so the position cannot be liquidated by a
  rally. On Kalshi the short is dollar-margined and the coin would sit at
  another venue, so a rally drains the short's margin while the gain sits
  elsewhere. Liquidation risk returns, and the capital needed is the spot plus
  the margin, which cuts the return on capital below the funding rate.
- **Costs are not yet measured.** Kalshi's perpetual fee schedule and the spot
  leg's cost at the broker are both unchecked.
