# Data gaps

What cannot be tested, why, and what would unblock it. A distinction that
matters: **attempted and failed** is different from **identified but not
attempted**, and most of the purchases below are the second. Listing an
un-attempted paywall as a failed retrieval would overstate how much was tried.

## Needs a person

- **Chan's example code for *Algorithmic Trading* (epchan.com/book2).** Three
  catalogue entries (`xs-mr-khandani-lo`, `xs-mr-intraday-open`,
  `equity-buy-on-gap`) reproduce his rules from printed fragments whose helper
  functions (`smartMovingStd`, `backshift`, `smartsum`) are not shown. The
  download is gated behind a registration step.
- **Carver, *Advanced Futures Trading Strategies*.** Only the names and numbering
  of all 27 strategies and the detail of three (9, 10, 11) were extracted. The
  catalogue carries two Carver entries and should carry six to eight.
- **Quantpedia.** Identified, not attempted. The free tier shows a subset and the
  full database is a subscription. It is one of few sources that index non-equity
  strategies in a structured way.

## A purchase decision

Ordered by what each unblocks per dollar.

| Item | Approximate cost | What it unblocks |
|---|---|---|
| Futures data (Norgate, CSI) | $400 to 900 a year | `futures-carry-carver10`, `futures-trend-ewmac` and the Carver strategies above. The largest single unlock. No adequate free source: free futures history is neither survivorship-clean nor roll-consistent. |
| Retail options data (ORATS, Polygon) | $50 to 200 a month | `vrp-short-vol` and the options section (1 entry now, 4 to 5 potential). Cboe's free BXM and PUT indices are a rough proxy for the premium, not chains. |
| CBOE DataShop SPX options | $500 to 2,000 once | The same, with the depth a volatility study needs. Buy one of this and the line above, not both. |
| CEF historical NAV | institutional | `cef-discount`. CEFConnect shows current and partial history with no bulk download. |
| Tick data (Databento, Polygon, WRDS TAQ) | $200 to 2,000 a month | `equity-order-flow-imbalance`, which sits near the boundary where retail execution costs exceed the available edge. |

If one item is bought, it is futures data, then options. Tick data is not worth
buying.

## Corrected since first written

- **`prices.permaticker`.** Was NULL on every equity bar since about 2026-08-01, the only stable company identity in the archive. Repaired as of 2026-09-27; see `defects/permaticker-gap.md`.

- **Kalshi settled-market history.** First recorded as purged and untestable. It
  is not: settled markets, candlesticks with bid and ask, and trade prints are
  served back to at least 2023 through the exchange's historical tier. Only order
  book depth at a past moment is unrecoverable, which is why the recorder exists.
  See `kalshi-survey.md`.
- **Perpetual futures venue.** First recorded as needing an offshore exchange.
  Kalshi lists 25 perpetual series. Access from this account, funding rules and
  any history remain unchecked. See `account.md`.

## Gone

Order book history for Kalshi and Polymarket before the recorder started does
not exist in any retrievable form. It is not a paywall or a scraping problem, and
the only remedy is recording forward.
