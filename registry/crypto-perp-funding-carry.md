+++
id = "crypto-perp-funding-carry"
family = "crypto-carry"
provenance = "literature"
source = "Exchange funding rules as published by Deribit and Hyperliquid; Gornall, Rinaldi and Xiao, Perpetual Futures and Basis Risk: Evidence from Cryptocurrency (SSRN working paper, 2024). Catalogue entry crypto-perp-funding-carry."
account = "none yet"
enabling_step = "A venue this account can trade whose perpetual funding is set by a published rule. Deribit, the venue tested, does not serve US persons. Kalshi's 25 perpetual series are the first to check: whether the account can trade them, how their funding is set, and what history they serve."
stage = 0

[registration]
registered_on = "2026-10-06"
hypothesis = "A position long BTC or ETH and short the same dollar amount of its perpetual future earns the perpetual's funding rate with no exposure to the coin's price, and on the evidence of the deepest venue reachable, that funding net of trading cost has exceeded the Treasury bill rate since October 2022 often enough to be worth holding."
economic_reason = "Demand for leveraged long exposure to crypto exceeds demand for leveraged short exposure most of the time, so the perpetual trades above spot and the venue's funding rule makes longs pay shorts to pull it back. Whoever holds the hedged short is paid for supplying that leverage and for bearing the venue's counterparty risk. The payment is contractual, set by a published formula; whether it is larger than cash is not."
prediction = "Written before any funding, perpetual price or index value was fetched for analysis. On the training window, gross funding received averages 3% to 9% a year across BTC and ETH, higher on ETH than on BTC, earned mostly in a few bursts when the perpetual traded well above the index, and close to zero for long stretches. Deribit adds no interest component and pays nothing while the premium sits within 0.025% per eight hours of the index, so its funding sits well below that of venues with a built-in rate. Active over Treasury bills (BIL), the decision book's mean is between -2% and +4% a year, with annualised volatility between 1% and 3%. My central expectation is a training score below the floor of 1.0, with a real chance it clears, because volatility this low turns a small mean into a large Sharpe. The absolute Sharpe (not active) exceeds 2, which is the Sharpe flattering a small, steady return. The threshold book has a higher active Sharpe than the always-on book because it sits in cash when funding is below its threshold, and it is in position on fewer than half the days. On the coins and dates both venues cover, Hyperliquid's funding averages at least 5 percentage points a year above Deribit's, because Hyperliquid builds in an interest component of about 11% a year paid to shorts; if it does not, my reading of the two rules is wrong."
universe = "BTC and ETH, as the Deribit inverse perpetuals BTC-PERPETUAL and ETH-PERPETUAL, each paired with the coin itself held on the venue as collateral. No other coin has deep funding history reachable from here. Both are eligible from the first UTC day on which funding, the perpetual's price and the index are all complete; the runner records that date."
horizon = "Decided once a day at 00:00 UTC, held at least one equity trading day. Funding accrues continuously and the hedge is reset daily. Crypto trades every day; the return series is folded onto the equity trading calendar as stated under Stage 0."
benchmark = "BIL"
parameters = { funding_threshold_apr_pct = 10.0, lookback_days = 30, coin_weight = 0.5, gross_exposure = 1.0 }
sizing_rules = ["threshold", "always_on"]
slippage_sweep_pct = [0.0, 0.05, 0.10, 0.15, 0.25, 0.50]  # per side, both legs of the unit together; 0.0 is the before-cost cell, funding included
holdout_start = "2025-10-01"
kill_criteria = "Stage 1 reads the training window only, 2022-10-03 to 2025-09-30, on the threshold book, utc_midnight execution, 0.15% per side. Killed, with no rescue, if the active Sharpe at the 0.0% cell is below 1.0: that cell keeps funding, which is the return here and not a cost, and removes all slippage, so no cheaper execution can lift the score above it. A near miss (at or above 1.0 at the 0.0% cell, below it at 0.15%) is eligible for at most two rescues under the shared rules. At or above 1.0 after slippage it goes to Stage 3, and the pooled score over training and holdout decides its tier. The run is invalid, not a result, if the basis term contributes more than half of the gross active return over the training window: that is a data fault or a different strategy, not the funding carry. A clear or borderline score makes the strategy eligible for a paper slot only once a venue the account can trade is identified; until then it takes none."
ruleset = "v2"
decision_sizing = "threshold"
decision_execution = "utc_midnight"
decision_slippage_pct = 0.15
current_regime_rule = "Rule set v2's training window: the three years ending on the last equity trading day before the holdout. No structural break is claimed."
current_regime_start = "2022-10-03"
data_derived_burden = ""
+++

# crypto-perp-funding-carry

## Stage 0 — definition

**The position, and why the inverse contract is not a problem.** A Deribit
perpetual is coin-margined: its size is in dollars, but profit, loss and
funding are settled in the coin. The position registered here holds `B`
coins on the venue as the only collateral and is short a dollar notional
`N = B × F₀` of the perpetual, where `F₀` is the perpetual's price at the
reset. With `S` the index (spot) price, the account's value in dollars is

`V_t = S_t × (B + N × (1/F_t − 1/F₀)) = B × F₀ × S_t / F_t`

so the dollar value moves only with the ratio of spot to perpetual, the
basis, and not with the coin's price. The convexity of an inverse contract
cancels exactly against the coin held as its collateral. The same algebra
gives a margin ratio that stays constant as the price moves, so a 1×
short collateralised by the coin itself cannot be liquidated by a rally,
which is the risk the catalogue entry worried about on dollar-margined
venues. The catalogue's `margin_buffer` parameter therefore has nothing to
control and is dropped. What remains unhedged is the funding and basis
profit itself, which arrives in coin. The hedge is reset daily, which
brings it back to zero.

**The carry unit's daily return.** For each coin, one column, the unit,
whose return over UTC day `d` is

`(S_d / F_d) / (S_{d−1} / F_{d−1}) − 1`

with `S` the Deribit index and `F` the perpetual's last traded price, both
at 00:00 UTC. A traded price rather than the mark price, which Deribit
does not serve as history, adds bid-ask noise to the basis term. That
raises measured volatility and lowers the Sharpe, the conservative
direction. Funding is not in this return; it enters through the engine's
funding term.

**Funding.** Deribit's hourly realised rate (`interest_1h`), summed over
the 24 hours of each UTC day, NaN for a day missing any hour
(`lab.data.funding_history.daily_funding`). The engine charges a payment
of `held × rate` to a funding-bearing column, positive meaning longs pay.
The unit is long the coin and short the perpetual, so the series passed
for the unit's column is the negated venue rate: a positive venue rate is
a receipt to the unit. That sign is pinned by a hand-computed test before
any run. Funding on an inverse contract is paid in coin on the dollar
notional, so its dollar value is the rate times `N`.

Deribit's rule, from its published specification: the premium rate is
`(mark − index) / index`; within ±0.025% per eight hours of zero the
funding is zero, beyond it funding is the premium less 0.025%; the cap is
0.5% per eight hours on BTC and 1% on ETH. There is no interest component.
Whether the dead zone or the caps changed during the sample is not
established; if the history shows funding inside the dead zone, that is
recorded as a finding, not adjusted.

**One calendar, and the annualisation it fixes.** Crypto produces 365
daily rows a year; the lab annualises with 252, the equity trading year,
and the benchmark, BIL, exists only on equity trading days. The unit's
returns are folded onto the equity calendar from the archive: the row for
equity trading day `D` compounds the unit's returns over every UTC day
after the previous trading day up to and including `D`, and sums their
funding. A weekend's crypto days land on Monday's row. A row with any
missing constituent day is missing. With rows on the equity calendar, 252
rows is a year, the benchmark lines up with no gap, the training window
and the one-year holdout minimum mean what they say elsewhere in the lab,
and the stated annualisation factor is 252. The cost is that decisions are
taken only at the end of an equity trading day, which a strategy holding
for weeks does not need otherwise. The pipeline will refuse a return
series with more than 270 rows a year, so a 365-row series is never
annualised at 252 by mistake.

**Execution: `utc_midnight`.** The decision dated `D` reads funding through
the end of UTC day `D` and is held over the next row, from 00:00 UTC on
`D + 1` onward. The engine applies the lag. BIL's row for `D` runs from
the close of the previous trading day to the close of `D`, eight hours
earlier than the strategy's row ends. The benchmark is cash, so the offset
moves nothing measurable.

**Sizing rules.** Both hold BTC and ETH at `coin_weight` each, 1.0 gross,
no leverage.

- `threshold`, the decision book, the catalogue's entry rule: a coin's
  unit is held when the trailing `lookback_days` mean of its daily funding,
  times 365, exceeds `funding_threshold_apr_pct`; otherwise that coin's half
  sits in a cash column carrying BIL's return. The ×365 is the funding
  rate's own convention, a calendar-day rate, and has nothing to do with
  the Sharpe's annualisation. Moving between unit and cash pays slippage
  on both.
- `always_on`: both units held every day. The control for the threshold:
  it answers whether selectivity adds anything beyond trading.

The decision book is the threshold because it is the strategy the
catalogue describes and the one that would be traded. I expect it to score
higher than the always-on book. It is the decision book because it is the
strategy, not because of that expectation.

**Costs.** Slippage is per side on the unit's traded notional and covers
both legs together, since the unit is one column: a taker fee on the
perpetual of 0.05% and on spot of 0.05% to 0.10% at retail tiers,
plus spread. The decision cell is 0.15%. Commission is folded into it and
set to zero separately. Nothing is short in the engine's sense, so no
borrow applies, and the funding of the short perpetual is in the funding
term. The always-on book trades almost nothing after entry, so cost
decides very little about it; for the threshold book it decides how much
each entry and exit loses. Withdrawal and transfer fees are not modelled.

**Parameters.**

| name | value | reason |
|---|---|---|
| funding_threshold_apr_pct | 10.0 | the catalogue's default, not tuned |
| lookback_days | 30 | the catalogue's default, not tuned |
| coin_weight | 0.5 | equal weight across the only two coins with history |
| gross_exposure | 1.0 | no leverage; at 1× the coin-collateralised short cannot be liquidated by price |

**Universe and size.** The shared rule makes eligible what the account can
trade, sized at no more than 1% of average daily dollar volume.
`market_core.liquidity` measures the equity archive only. The runner
measures each perpetual's average daily dollar volume from Deribit's own
daily volume over the training window and records it in the report; an
order of this account's size is many orders of magnitude below 1% of it.
The rule's other half fails, and the registration says so instead of
working around it: Deribit does not serve US persons, so the account
cannot trade the venue tested. What this test can establish is whether the
mechanism pays above cash on the deepest funding history reachable. It
cannot establish that any venue the account can use pays the same, since
each venue sets its own rule. Eligibility for a paper slot waits on such a
venue, and a venue found later is tested on its own history.

**Windows.** Training is 2022-10-03 to 2025-09-30. The holdout is
2025-10-01 onward, the boundary the shared rules set for equities on
adoption, and as of registration it holds just over a year, enough for its
score to be read once at Stage 3. Everything from each instrument's first
complete day up to 2022-09-30 is context: its t-statistic is reported as a
flag. Context includes 2021, when funding ran several times its later
level, and it decides nothing.

**Cross-check, a flag.** Hyperliquid's hourly funding for BTC and ETH from
2023-05-12 to 2025-09-30, applied to the always-on book with no basis term,
since only funding is fetched there. Hyperliquid's rule is the average
premium plus a clamp of an interest component, 0.01% per eight hours, paid
hourly. It differs from Deribit's by construction, which is what the
prediction tests. It is a printed comparison of mean funding on the days both venues have complete, not a pipeline run, since the prediction it tests is about funding and not about a score.

**What no figure here measures.** A venue that failed is not in the data:
only venues that survived serve history, and FTX, which failed in November
2022, would have served the same mechanism up to the day its customers'
coins were gone. The dominant risk of this trade is a jump to a large
loss, from venue failure or a suspended withdrawal, and a history of small
steady returns says nothing about its size. A high Sharpe here is the
least informative number in the lab.

**Before writing this.** I read the catalogue entry, the two venues'
published funding rules, and `docs/perp-funding-survey.md`, which records
what was read while measuring depth on 2026-10-05. That covered one page
per venue: two recent OKX funding values, falling inside the holdout; the
first rate of Kraken's listing, dated 2025-10-01, the holdout's first day;
the first rate of Hyperliquid's BTC listing, 2023-05-12, inside training;
and row counts from Deribit for one ten-day window in each of 2019 to 2023.
Whether individual Deribit values were displayed while counting rows is
not recorded, so I assume they were. None was analysed. Separately, I
carry a general knowledge of the crypto market through 2026, including
broadly when prices rose and fell, which cannot be set aside. The holdout
is therefore not blind to the market's direction, and weighs as less
evidence than a holdout I knew nothing about.

**Amended 2026-10-06, before any run.** Four engineering details the text
above did not fix. The pipeline's refusal threshold for rows a year is 270, not
260: weekdays with no holidays give 261, crypto's own calendar 365, and 270
separates them. The last UTC day before the cutoff has its end price stamped at
the cutoff itself, which the fetch drops, so the evaluated rows end on the last
trading day at least two days before the holdout. The Hyperliquid cross-check is
the printed funding comparison described above, not a counted run. And one
consequence of the design is stated here so it is not read as a result later: the
unit holds its collateral in coin, which earns no cash interest, so its return is
funding plus the basis move and the active return is that less the Treasury bill
yield. With no funding at all it would show about minus the bill yield. No
parameter, sizing rule, cell, window or kill criterion changed.

## Build state

Built 2026-10-06, not yet run: the price fetch (`lab/data/perp_prices.py`),
the strategy module and the fold (`lab/strategies/crypto_perp_funding_carry.py`),
the rows-a-year refusal in the pipeline, and the runner
(`scripts/run_crypto_perp_funding_carry_stage1.py`). Every new guard was
broken once and a test caught it.

## Binding constraint

Venue access. The account holds crypto spot at its broker and cannot use
Deribit. Relaxed by a venue the account can trade with published funding
history, which is the enabling step above.

## Stage results

### Stage 1, run 2026-10-10 (training window only; the holdout was never requested)

Runs: `983da5285511487abee728ff8841b00a` (threshold, the decision book) and
`3eadc052be034b4e8b05f4b368081f89` (always-on). Report in the lab's data
directory under `reports/`.

**A void run precedes them.** `4c2f3bc6f23c43509d7ff8ccbd8db468` was recorded
before the fetcher was fixed and is void. Deribit's funding endpoint excludes a
row stamped exactly at `start_timestamp`, so the fetcher dropped the first hour
of every 30-day chunk and every boundary day had 23 hours and therefore no
funding. The backtest refused to hold through those days, as designed, and
stopped. Its threshold-book figures had been written before it stopped; I did
not read them. Its trial stays counted. The fake endpoint in the tests had
included its start, which is why the tests passed; it now excludes it, and the
fetcher asks from one millisecond earlier.

**One genuine venue gap.** Deribit serves no funding for 06:00 and 07:00 UTC on
2020-08-27, for either coin. A day is never filled, so the evaluated rows start
on the first equity trading day after it, 2020-08-28, and the sample is 1,277
rows to 2025-09-29. The training window, 2022-09-30 to 2025-09-29, is
complete. The first 16 months of the original sample are dropped from context.

**What was measured, training window, 751 rows.** Decision book (threshold),
net of 0.15% per side: active Sharpe 0.32, active return 2.48% a year, active
volatility 7.7%; before slippage, 0.46. Always-on: 0.16 and 0.16. Funding
received, always-on, was 6.4% a year on BTC and 5.1% on ETH; the basis term
added 1.4% and 1.9%. The decision book was in position on 28% of days for BTC
and 23% for ETH. Context history, 2020-08-28 on: t 2.48 on the decision book,
a flag. Hyperliquid's funding averaged 9.2 points a year above Deribit's on
BTC and 11.2 on ETH over 843 common days.

**Prediction scored.** Right: funding of 3% to 9% a year; the decision book's
active mean inside minus 2% to plus 4%; a training score below the floor; the
threshold book above the always-on book; in position fewer than half the days;
Hyperliquid at least 5 points above Deribit. Wrong: ETH was expected to pay
more than BTC and paid less; volatility was expected at 1% to 3% and was
7.7% and 16.8%; the absolute Sharpe was expected above 2 and was 0.93 and 0.43.
The invalid-run clause did not fire: the basis term was well under half of the
gross return.

**The kill criterion fires on the measurement, and I do not trust the
measurement.** The Sharpe at the 0.0% cell on the training window is 0.46,
below the 1.0 the registration set, which by its letter ends the strategy with
no rescue. But the volatility is five to ten times what a hedged position
should show, and I have not recorded a verdict. The cause I can see is
the spot leg: the index series Deribit serves for its full history is spaced
every six hours, not hourly, and its stamp convention is not documented. The
basis level it implies (index over perpetual, minus one) has a standard
deviation of 0.65% on BTC at the stamp as registered, falling to 0.42% when
the index is read two hours later, and still falling, which is what a stamp
that is early would produce. Noise in the basis adds volatility without adding
return and lowers the Sharpe, the direction the registration called
conservative; it did not expect it to be this large. Whether a cleaner spot
series would lift the score above 1.0 is unknown, and whether to look is a
change to a registered measurement made after seeing a result, so it is
recorded here as that and not as a rescue.

## Variants

Every variant is a trial for deflation. One change at a time, the economic
reason written before the run.

| n | change | economic reason | run id | Sharpe before | Sharpe after | trials so far |
|---|--------|-----------------|--------|---------------|--------------|---------------|

## Verdicts

| date | verdict | run id | basis |
|------|---------|--------|-------|
