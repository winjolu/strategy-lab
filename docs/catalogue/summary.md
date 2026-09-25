# Strategy catalogue: what to test first

Compiled 2026-09-21, with status notes added 2026-09-24. 41 candidates.
Companion files: `strategies.json` (authoritative), `strategies.csv` (a
sortable view with an empty `my_verdict` column), and `../data-gaps.md`.

**Nothing in this file is a finding.** Every performance figure is either an
author's claim or my preliminary estimate, and both are labelled as such in the
JSON. No strategy here is recommended for real money.

## What is in the catalogue

| Verdict | Count |
|---|---|
| `test_with_tweaks` | 18 |
| `test_now` | 13 |
| `blocked_on_data` | 5 |
| `reject` | 3 |
| `manual_only` | 2 |

| Asset class | Count |
|---|---|
| Equities | 30 |
| Event contracts | 4 |
| Futures | 2 |
| Crypto | 2 |
| FX | 1 |
| Options | 1 |
| Cross-asset | 1 |

| Data availability | Count |
|---|---|
| Testable on local data today | 29 |
| Testable with a purchase | 5 |
| Manual evaluation only | 5 |
| Blocked on data | 2 |

The distribution is lopsided because of the data, not because of where the
opportunities are. Thirty of 41 entries are equities because the reference
library and the local archive support equities. Futures and options history is
unentitled, and the event-contract history was assumed not to exist. Since
then that last assumption has been checked and is partly wrong: see
`../kalshi-survey.md`.

## The ten to test first

Ranked by **information gained per day of work**, not by claimed return. A few
tests answer questions that decide many entries at once, and those are worth far
more than a test that decides only itself.

1. **`xs-mr-khandani-lo`: cross-sectional mean reversion.** Each day, buy the
   stocks that fell most against their peers and short the ones that rose most.
   Zero fitted parameters, fully testable today. It turns over 200% of gross per
   day, so it is the sharpest available test of whether any high-turnover equity
   strategy survives realistic costs. That question decides roughly ten other
   entries. Registered.
2. **Value-weighting versus equal-weighting, across any three OSAP factor
   entries.** OSAP is Open Source Asset Pricing, a public project that recreates
   published stock-return predictors. This is a methodology test, not a strategy,
   and the highest-value item on the list. Hou, Xue and Zhang's central finding is
   that most published anomalies fail once microcaps are handled properly, and all
   23 OSAP entries carry this same tweak as their first proposal. Running it on
   three tells me whether the other twenty are worth touching. It depends on the
   field map from OSAP's Compustat names to the archive's columns.
3. **`crypto-perp-funding-carry`: spot-perpetual basis.** The only non-equity
   strategy with free, deep, immediately available history. The mechanism is
   contractual: the exchange publishes the funding formula. Its risk is
   counterparty and liquidation, which no backtest shows, so the test sizes the
   carry and the risk question is settled separately.
4. **`osap-shareiss5y`: net share issuance.** Annual rebalancing gives the
   cheapest cost profile in the equity set. The mechanism, that management issues
   when the stock is expensive, rests on an information asymmetry structural to
   the corporate form.
5. **`event-internal-noarb-yesno`: Kalshi yes+no bound, as a recording job.**
   Started as a recorder because order book depth is retained nowhere. Whether
   the strategy is viable is a question for a month of data.
6. **`osap-gp`: gross profitability.** Has held up better after publication than
   most factors and is naturally long-biased, so the unverifiable borrow-cost
   problem does not bind.
7. **`pead`: post-earnings announcement drift.** The longest-surviving anomaly
   in the literature, with a clear mechanism. It depends on the fundamentals
   table carrying announcement timing (before the open or after the close), which
   is unverified, so it sits below where it would otherwise rank.
8. **`osap-idiovol3f`: idiosyncratic volatility.** The low-risk effect has a
   structural cause (leverage constraints) rather than a mispricing one, which
   predicts more persistence. Monthly rebalancing costs more than entries 4 and 6.
9. **`equity-turn-of-month`: turn-of-month seasonality.** Nearly free to test and
   to run. Its value is as a worked example of the decay methodology: test it only
   on post-1988 data against a null distribution of randomly chosen four-day
   windows, then reuse the harness on everything else.
10. **`osap-investment`: asset investment.** Survives Hou, Xue and Zhang's
    replication better than most, has a mechanism (q-theory) that requires nobody
    to be making a mistake, and rebalances annually.

Deliberately not in the top ten: anything requiring a purchase, anything in the
options section, and `xs-mr-intraday-open`, a close variant of entry 1 that
would add almost nothing to it.

## Arbitrage candidates, ranked by net-of-fee edge per unit capital per day

Seven entries carry arbitrage fields. Fee formulas are the venues' published
ones, not estimates.

| Rank | Strategy | Type | Latency | Net edge per capital per day | Verdict |
|---|---|---|---|---|---|
| 1 | `event-internal-noarb-yesno` | riskless | minutes | about 143 bps/day while held (1 cent edge, 7-day resolution), but opportunity-limited and possibly zero | test_now |
| 2 | `event-cross-venue` | statistical | minutes | about 100 bps/day on trade capital, about 50 after the idle mirror balance | test_with_tweaks |
| 3 | `event-multi-outcome-overround` | riskless | minutes | similar per trade, materially rarer, higher execution risk | test_with_tweaks |
| 4 | `crypto-perp-funding-carry` | carry | hours | about 2.7 bps/day continuous at 10% annualised funding | test_now |
| 5 | `cef-discount` | statistical | days | about 4 to 18 bps/day on converging positions | blocked_on_data |
| 6 | `adr-ordinary-parity` | statistical | minutes | approximately zero to negative | reject |
| 7 | `crypto-cross-exchange-arb` | riskless | sub-second | negative | reject: requires co-location |

The ranking is misleading in a specific way. The event-contract entries top it on
edge per day while held, but they fire rarely and possibly never. The crypto
funding carry is an order of magnitude lower per day and runs continuously with
capital fully deployed, so over a year it very likely delivers more. Frequency,
not edge, is what separates these.

### The fee arithmetic

Kalshi's taker fee is `ceil_to_cent(0.07 x M x C x P x (1 - P))` per order, where
`P` is the price in dollars, `C` the contracts and `M` a per-series multiplier.
I verified the formula and its rounding against the exchange's published fee
table on 2026-09-23 (`../kalshi-survey.md`). The fee is quadratic in price and
peaks at 50 cents, which has consequences that most writing about these markets
ignores. Buying yes and no together costs roughly `0.14 x P(1 - P)`, so the
break-even combined price is:

| Contract price | Taker break-even |
|---|---|
| 50 cents | under 96.50 cents |
| 20 cents | under 97.76 cents |
| 10 cents | under 98.74 cents |
| 5 cents | under 99.33 cents |

A 3.5-cent gap on a coin-flip contract does not occur in any market with
participants, so the trade does not exist near 50 cents. It exists, if at all, in
the price tails, where the required gap falls under a cent. That reorients the
event-contract screen toward far-from-even, short-dated contracts. For mutually
exclusive outcome sets the fee rises with the number of legs, so wide fields are
worse, not better.

Polymarket charges makers nothing in every category and takers nothing in
geopolitics. That asymmetry is the largest single cost improvement in this
section. Return on capital is dominated by time to resolution, not edge size: a
0.5-cent edge resolving in seven days (26% annualised) beats a 3-cent edge
resolving in 180 days (6%).

## What is blocked, and what unblocking costs

| Blocked | Entries | Cost to unblock |
|---|---|---|
| Futures data (Norgate, CSI) | 2 now, 6 to 8 once Carver's book is readable | $400 to 900 a year |
| Options chains (ORATS, Polygon, CBOE DataShop) | 1 now, 4 to 5 potential | $50 to 200 a month, or $500 to 2,000 once |
| CEF historical NAV | 1 | institutional pricing |
| Tick data | 1 | $200 to 2,000 a month plus storage |
| Event-contract order book history | 4 | $0, but only by recording forward |

If one thing is bought, it is the futures data: it unblocks the most entries, and
they are the ones least correlated with an all-equity book. The free item is the
Kalshi recorder, which is running.

## Findings from building it

**A widely-starred resource produced unusable numbers.** The
`paperswithbacktest/awesome-systematic-trading` repository advertises 4,843
replicated papers. Its strategies table assigns Sharpe ratios to papers that
propose no strategy (a behavioural coin-flip experiment, a database-quality paper,
two annuity-theory papers) and reports 22 to 35 years of tested history for
cryptocurrency strategies on an asset with at most 16 years of price history. An
implausible number of entries land on exactly 37 or 38 years tested, which
suggests a fixed backtest calendar rather than the asset's history. Its headline
claim of no measurable post-publication decay contradicts McLean and Pontiff
(2016). I used it as a bibliography and discarded every number.

**The quadratic fee inverts the obvious search.** The intuitive place to look for
a yes+no violation is a liquid, evenly priced contract, which is where the fee is
largest and the trade arithmetically impossible.

**OSAP's definitions are better than its returns data.** The value is in the
documentation table (actual Compustat mnemonics with stated fallbacks), which is
what makes 23 entries implementable without going back to the papers.

**The data window suits decay measurement, not replication.** Local data starts
in 1998 and the median OSAP entry was published in 2006, so most original results
cannot be replicated because their samples predate the data. About twenty years of
clean post-publication testing is available, which is what McLean and Pontiff
measured. That reframes what "test it" means for most of the equity catalogue.

## Limits

**What I may have missed.** Non-equity coverage is thin, partly because one book's
strategy specifications could not be retrieved in full. Six to eight futures
strategies that belong here are absent, and options coverage is one entry where
it should be four or five.

**Assumptions made without confirmation.**
- That the fundamentals table carries the Compustat fields the OSAP definitions
  name. This is the single assumption most likely to invalidate the ranking, and
  the field map is the item that checks it.
- That the earnings data carries before-open versus after-close timing, on which
  `pead` depends entirely.
- That equity execution costs 0.05 to 0.15% round trip. Every cost-sensitivity
  judgment scales with it.
- That Polymarket is accessible, a legal question I am not qualified to answer.

**Where the reasoning is weakest.** The `preliminary_estimate` figures are the
softest content here. They exist because ranking needs a number, but they are
informed guesses calibrated against the decay literature, not analysis. The
ordering is more reliable than any individual figure. I have also been harder on
retail and practitioner sources than on academic ones, which is a prior and not a
finding: Hou, Xue and Zhang's result that most of the anomaly literature fails
proper methodology applies to 23 of the 41 entries.
