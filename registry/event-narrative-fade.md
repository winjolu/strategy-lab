+++
id = "event-narrative-fade"
family = "event-contract-bias"
provenance = "literature"
source = "Favourite-longshot bias in betting markets; Snowberg and Wolfers, Examining Explanations of a Market Anomaly: Preferences or Perceptions? (NBER w15923). Catalogue entry event-narrative-fade."
account = "events-cash"
enabling_step = "None needed to test. Trading draws on the settled cash the equity account also uses, with full collateral locked until settlement."
stage = 0

[registration]
registered_on = "2026-09-23"
hypothesis = "Yes contracts on retail-heavy Kalshi markets that are quoted at 3 to 15 cents settle yes less often than their price implies, by more than the taker fee, so a seller of every such contract earns a positive return on collateral with no view on any individual event."
economic_reason = "Casual participants pay for a story and for the lottery-like payoff of a cheap contract, and in this venue there is limited professional capital willing to lock up 85 to 97 cents of collateral to earn a few cents against them. The same preference for longshots is documented across decades of racetrack and sports-betting data. The seller is paid for supplying insurance with a severe, correlated left tail."
prediction = "Contracts with a yes bid of 3 to 15 cents at the snapshot settle yes less often than the bid implies. The gross edge to the seller is 1 to 4 points of face value, roughly 1 to 4.5 percent of collateral per position, against a taker fee of 0.3 to 0.9 cents. The net active return per position is positive but modest, with a clustered |t| between 1.5 and 3 under the event-capped sizing. The edge is larger in Entertainment and in sports futures than in single-game markets, and smaller from April 2025 onward than before it. The return distribution is strongly negatively skewed: most positions win a few percent and a few lose 85 to 97 percent of their collateral."
universe = "Binary Kalshi markets in series whose category is Sports, Entertainment, Politics or Elections, excluding series with hourly or fifteen-minute frequency and excluding multivariate combination markets (KXMVE). Series category, frequency and fee terms are read from /series and are static attributes. A market enters on the first daily snapshot at which its yes bid is within the band and a yes ask also exists. The snapshot is the most recent hourly candle ending at or before 14:00 UTC, which is before nearly every US game starts, and it is used only if it ended within max_quote_age_hours. No filter uses close_time, which is the realised close and moves when a market closes early; a horizon filter on it would read the outcome."
horizon = "Hold to settlement. One entry per market. Positions open and close continuously as markets list and settle."
benchmark = "BIL"
parameters = { band_low_dollars = 0.03, band_high_dollars = 0.15, snapshot_hour_utc = 14, max_quote_age_hours = 24 }
sizing_rules = ["equal_collateral", "event_capped"]
holdout_start = "2026-04-01"
kill_criteria = "Evaluated at the headline cell (taker fee from the series schedule plus 1 cent of slippage per contract) under event_capped sizing. Record and drop if the event-clustered t on active return is below 1.5. Do not advance if the mean active return is not positive in the current-regime slice, even when the full sample passes. Do not advance if a single series supplies more than half of the net profit, since that is one mispriced series and not a population bias."
current_regime_rule = "Since per-game sports markets listed: the first month in which KXMLBGAME, KXNBAGAME and KXNHLGAME all settle markets in the historical tier. Before that the venue's retail participation was a different population."
current_regime_start = "2025-04-01"
data_derived_burden = ""
+++

# event-narrative-fade

## Stage 0 — definition

**What is tested.** The unconditional longshot bias, not the catalogue's full
strategy. The catalogue sells a longshot only when a hand-built base rate for
that class of event sits materially below the price. Building those base
rates is domain-by-domain forecasting with an unbounded number of choices,
and any one of them could be fitted to the sample. The question that decides
whether the idea is worth that effort comes first: across every retail-heavy
longshot, does selling at the quoted bid pay after the fee? If it does not,
a base-rate filter is a forecasting strategy that has to earn its keep on its
own. If it does, one base-rate filter is at most one Stage 2 variant. The
catalogue's optional early exit at a third of the entry price is dropped for
the same reason: hold to settlement only.

**Entry.** On each calendar day, for every market in the universe that has
not yet been entered, read the most recent hourly candle ending at or before
14:00 UTC from `/historical/markets/{ticker}/candlesticks` (or the live
equivalent). Enter if that candle ended within 24 hours of the snapshot, its
closing yes bid `p` is between 0.03 and 0.15 inclusive, and its closing yes
ask is present. Enter by selling yes at `p`, which is buying no at `1 − p`.
One entry per market, at the first qualifying snapshot.

**Exit.** Settlement. A no result pays `p` per contract and a yes result
loses `1 − p`. Collateral is `1 − p` per contract. A voided market returns
the collateral and is counted, not dropped, with the fee still paid; the
count is reported, because voiding that correlates with the outcome would
bias the result.

**Costs.** Taker fee, from the exchange's July 2026 fee schedule:
`ceil_to_cent(0.07 × M × C × p × (1 − p))` per order of `C` contracts, where
`M` is the series multiplier. Checked on 2026-09-23 against every row of the
schedule's general fees table, and against its per-series list for the
series it shows; the rounding is per order to the whole cent (one contract
at 10 cents costs 1 cent, not 0.63). There is no settlement fee. `M` is the
value in force on the day of entry, taken from `/series/fee_changes`, not
the series' current listing: 19 series in the universe, KXMLBGAME among
them, moved from 1 to 0.5 on 2026-08-07, and today's value would halve
their in-sample fee. Before a series' first recorded change, which is
2025-10-04 at the earliest, `M = 1`, the schedule's stated default; that
errs towards a higher fee. Slippage is swept at 0 and 1 cent per contract,
and the headline cell is 1 cent. This paragraph was amended on 2026-09-23,
after the fee check and before any run, from an earlier version that applied
the current listing to all history.

**Return and benchmark.** Return on collateral per position, net of fee and
slippage. Active return subtracts BIL's total return over the same holding
period on the same collateral, which is the cash the position ties up.
Kalshi may pay interest on balances; if it does, subtracting BIL is the fair
comparison, and if it does not, it correctly charges the opportunity cost.

**Parameters, with where each came from.**

| name | value | reason |
|---|---|---|
| band_low_dollars | 0.03 | catalogue default; below 3 cents the tick is a third of the price |
| band_high_dollars | 0.15 | catalogue default; the racetrack evidence concerns long odds |
| snapshot_hour_utc | 14 | 10:00 New York time: markets are awake and US games have not started, so in-play pricing is mostly excluded |
| max_quote_age_hours | 24 | a quote older than a day is not a price anyone could trade at |

None of these was chosen by looking at Kalshi prices or outcomes. Before
writing this I read only metadata: series categories and fee terms, and
counts of markets by month.

**Sizing rules.** `equal_collateral`: every position carries the same
collateral. `event_capped`: every event carries the same total collateral,
split equally across its qualifying markets. An event with twenty longshot
candidates is one bet, not twenty, and the second rule says so. Both are
reported; `event_capped` is the one the kill criteria read.

**Statistics.** The engine's daily-weights path does not apply: positions
are per event, held to an uneven settlement. The test statistic is the mean
active return per position with standard errors clustered by
`event_ticker`. Also reported: a calibration table of realised yes frequency
against mean entry price in 1-cent bins; the same split by category; a daily
profit-and-loss series by settlement date with its Newey-West t, as a check
on cross-event dependence; the worst single day; and the maximum drawdown
of that series. Sharpe is reported but is the wrong summary for a payoff
that sells insurance, and the skew and the worst losses stand beside it.

**Sample.** In-sample is every market that settled before 2026-04-01, using
candles before that date. Markets settling on or after it, and every candle
on or after it, are the holdout. Coverage measured on 2026-09-23: per-game
sports series from 2025-04; entertainment and politics series from 2022.
The in-sample population before the current regime is therefore mostly
entertainment and politics, and is reported separately.

**What would make the result misleading.**

- The candle's closing bid is the last bid in the hour, not a fill. With no
  depth history, whether a position of a given size could have been sold
  there is unknown. Every result is an upper bound on what was executable,
  and the 1-cent slippage cell is the only allowance for it.
- `close_time`, `settlement_ts` and `result` must not reach the entry rule.
  The evaluator enforces that structurally, not by convention.
- Category is the series' current classification. A series reclassified
  after the fact would move between universes; this is not checkable from
  the API and is noted, not fixed.

## Binding constraint

**Capital, and it is shared.** Events Cash buying power is the equity
account's settled cash, under a tenth of the book on 2026-09-23, not additional money.
Every position locks 85 to 97 cents of collateral per contract until
settlement, so the book the account can carry is small and competes
directly with equity purchases. The step that relaxes it is funding the
events account separately, which removes that capital from equities. Depth
at 3 to 15 cents is thin by nature, and the recorder's depth snapshots are
what will say how thin.

## Stage results

None yet. The evaluator for per-event positions does not exist; it is the
next build.

## Variants

| n | change | economic reason | run id | t before | t after | trials so far |
|---|--------|-----------------|--------|----------|---------|---------------|

## Verdicts

| date | verdict | run id | basis |
|------|---------|--------|-------|
