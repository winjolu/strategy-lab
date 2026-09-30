+++
id = "xs-mr-khandani-lo"
family = "equity-short-term-reversal"
provenance = "literature"
source = "Khandani and Lo, What Happened to the Quants in August 2007? (Journal of Investment Management, 2007); replicated in Chan, Algorithmic Trading (2013), Example 4.3. Catalogue entry xs-mr-khandani-lo."
account = "individual-margin"
enabling_step = "Fund the margin account (the planned move). Shorting needs it; the daily rebalance is held overnight, so it creates no pattern-day-trader day trades."
stage = 1

[registration]
registered_on = "2026-09-24"
hypothesis = "Among S&P 500 members, a stock's return relative to the equal-weighted index average on one day partly reverses the next, so a dollar-neutral book long the relative losers and short the relative winners earns a positive return."
economic_reason = "A one-day move against peers with no news behind it is largely the price impact of someone who needed to trade immediately. Whoever takes the other side is paid for supplying that liquidity as the impact decays. The mechanism predicts that the premium is larger in less liquid names and collapses when liquidity providers deleverage together, as in August 2007."
prediction = "Gross of costs, the linear book earns a positive return over the full in-sample period with |t| above 3, most of it before 2009, and a much smaller one in the current regime. The close-to-close version shows a clearly larger gross return than the next-open version, and the difference is bid-ask bounce rather than edge. The break-even cost is between 1 and 4 basis points per side over the full sample and lower in the current regime. At the kill cell (5 basis points per side, 1% borrow) the net result is negative or insignificant, and I expect the strategy to be killed. The decile book has a larger gross return per unit of turnover than the linear book but does not change that conclusion."
universe = "S&P 500 members as of the close of the decision date, from the archive's sp500 table (dated additions, removals and membership snapshots; point-in-time, delisted members included). A member enters the signal on a date only if it has adjusted closes on that date and the previous trading day. Membership is rebuilt every date; a position is never held because a name used to be a member. The build checks that membership counts sit near 500 on every date and stops if they do not."
horizon = "One day. Signal at the close of day t; trade at the open of t+1; hold to the open of t+2, when the book is rebuilt from the close of t+1."
benchmark = "BIL"
parameters = { universe_index = "sp500", signal_lookback_days = 1, gross_exposure = 1.0, decile_fraction = 0.1 }
sizing_rules = ["linear", "decile_equal"]
slippage_sweep_pct = [0.01, 0.02, 0.05, 0.10, 0.25]  # per side; 1,2,5,10,25bp
holdout_start = "2024-10-01"
kill_criteria = "Read on the linear book, next-open execution, at 5 basis points of slippage per side and 1% borrow. Record and drop if the Newey-West t on active return is below 1.5. Do not advance if the mean active return in the current-regime slice is not positive. The run is invalid, not a result, if held positions with no return were zero-filled on more than 0.1% of position-days: that is a data fault to fix first."
current_regime_rule = "The three years before the holdout: a fixed-length window, chosen because no single structural date marks the current state of equity liquidity provision."
current_regime_start = "2021-10-01"
data_derived_burden = ""
+++

# xs-mr-khandani-lo

## Stage 0 — definition

**Signal.** At the close of day `t`, for every member with adjusted closes on
`t` and `t−1`, `r_i = closeadj_i(t) / closeadj_i(t−1) − 1`, and `r̄` is their
equal-weighted mean. The signal is `s_i = −(r_i − r̄)`: positive for the day's
relative losers, negative for its relative winners.

**Sizing rules.** Both are dollar-neutral at 1.0 gross (0.5 long, 0.5 short),
and both are reported.

- `linear`: the published rule. Weights proportional to `s_i`, each side
  scaled to 0.5. Every member is held every day, most of them in tiny amounts.
- `decile_equal`: long the 10% of members with the highest `s_i`, short the
  10% with the lowest, equal weight within each side. Roughly 50 names a side,
  which is closer to something this account could hold.

**Execution: the next open, not the same close.** The published tests
compute the signal from the close and trade at that same close. That credits
the strategy with a price it could not have used: the close is known only
once trading has stopped, and a close that happens to print at the bid looks
like a fall and then "reverts" the next day on no information at all. A
reversal strategy is the one most flattered by that bounce. The headline
therefore trades at the next open, with returns measured open to open on
opening prices carried to the same dividend and split basis as `closeadj`
(`open × closeadj / close`, same day). In the engine, the weights dated `t`
are held over the returns row dated `t+1`, which holds the return from the
open of `t+1` to the open of `t+2`. The last row before the holdout is
dropped, since it would reach the holdout's first open. SPY and the book
series are put on the same open-to-open basis before correlating.

The close-to-close version is also run and reported beside it, labelled as
an upper bound and as what the published figures measure. It counts as a
trial. The gap between the two is a measurement of the bounce.

**Costs.** At about 2.0 of gross traded per day, the lab's standard sweep
(0.10%, 0.25% and 0.50% per side) decides this before it runs: 0.10% alone
costs roughly 50% a year, which no one-day reversal on the largest US stocks
has ever earned. A test with a foregone answer measures nothing, so this
strategy is swept finer: 1, 2, 5, 10 and 25 basis points per side, and
borrow at 1% and 8%. The kill cell is 5 basis points and 1% borrow. The
reason, written before any run: S&P 500 members typically quote half-spreads
of one to three basis points, a position here is tens of dollars and moves no
price, and S&P 500 members are general collateral to borrow, for which 1%
is already generous. The lab's standard headline cell (0.25%, 8%) is also
reported. The most useful output is the break-even cost per side, at which
the active t reaches 0 and at which it reaches 2: it tells every other
high-turnover entry in the catalogue what it would have to overcome.

The sweep is read from `slippage_sweep_pct` above: `costs.sweep` takes an
optional override, and every other strategy keeps the lab-wide default of
0.10%, 0.25% and 0.50% unaffected. The lab's standard headline cell
(0.25% slippage, 8% borrow) is unchanged and still reported, since 0.25 is
one of this strategy's own swept points.

**Amended 2026-09-27, before any run.** Three engineering details the text
above did not fix precisely. The open-to-open benchmark is BIL put through
the same forward, next-open convention as the strategy's own returns
(`lab.engine.returns.open_to_open`), not the ordinary close-to-close
series, so the active-return comparison is not contaminated by a basis
difference between the two; SPY is put on the same basis for the same
reason. The book correlation is not: `lab.engine.book` only knows the
close-to-close convention, so the open-to-open evaluation reports it as
NOT COMPUTED rather than on a mismatched basis, until an open-to-open book
series is built — a recorded gap, not a silent omission, and the
close-to-close evaluation is unaffected. And the break-even slippage the
report shows is read at a fixed borrow rate (8%, the sweep's
hard-to-borrow case, since the strategy shorts) with only slippage
varying, and is reported as "above" or "below every swept level" rather
than extrapolated when a crossing falls outside the five points actually
tested. None of this changes the hypothesis, the prediction or the kill
criteria.

**Missing returns.** A member removed from the index is almost always
acquired, and its last bar is the deal price. A held name whose next open
does not exist is zero-filled (`on_missing = "zero"`) and counted, and the
kill criteria make the run invalid if that touches more than 0.1% of
position-days.

**Parameters.**

| name | value | reason |
|---|---|---|
| universe_index | sp500 | catalogue default; the only point-in-time index membership in the archive |
| signal_lookback_days | 1 | the published definition |
| gross_exposure | 1.0 | the published definition; no leverage |
| decile_fraction | 0.1 | used only by `decile_equal`; the conventional extreme-decile cut |

None was chosen by looking at a return. Before writing this I read the
catalogue entry, the sp500 table's action counts and date ranges, and the
engine's code; no price series.

**Sample.** In-sample runs from 1998-03-31, the first membership snapshot in
the sp500 table, to 2024-09-30. The holdout, from 2024-10-01, stays unseen
until Stage 3. The current-regime slice is 2021-10-01 to 2024-09-30.

## Binding constraint

**Whole-share shorting at this account size.** At 1.0 gross on about $20k, the
linear book puts about $20 in each of 500 names, and the decile book about
$100 in each of 100. Short sales must be whole shares, and many S&P 500
members trade above $100, so neither book can be held as specified: the short
side would be rounded away. The backtest measures whether the edge exists
after costs. Whether this account can hold it is a separate question, and
the answer on these numbers is no, for either book, without far more capital
or a much narrower book. If the edge survives, the next question is the
smallest book that keeps it.

Settlement stops binding after the margin move, and the pattern-day-trader
rule does not bind, since every position is held overnight. Borrow
availability is not in the archive at any price, so short results are upper
bounds.

## Stage results

### Stage 1, 2026-09-30: killed

Runs, next-open execution: `b7b5ee2943e947438a7810a921b03f8a` (linear),
`f5806703a4414823932de9a21187a784` (decile). Same-close execution, the
published convention: `23c18299157b4e78bda0eda6f9582580` (linear),
`402e8852779e4bdbaed4369c8fa26c94` (decile). Reports in the lab's data
directory under `reports/`.

**Kill cell** (linear, next-open, 5bp per side, 1% borrow): active t =
**−5.52**, active return −13.50% a year (active). The criterion was t
below 1.5. Dropped.

**The registered benchmark truncated the sample.** BIL begins trading
2007-05-30, and `stats.summarise` keeps only dates both series share, so
every registered figure covers 2007-05-30 to 2024-09-30 (4,364 days), not
the registered 1998-03-31 start. The years the prediction said held most
of the edge are exactly the ones dropped. A diagnostic outside the
pipeline, not a registered figure and not recorded as a trial, measured
the gross return (no costs, no benchmark) over the whole sample:

| period | linear, next-open (abs) | decile, next-open (abs) |
|---|---|---|
| 1998–2006 | +9.04%/yr, t 2.8 | +18.38%/yr, t 4.8 |
| 2007–2008 | +22.19%/yr, t 1.7 | +18.57%/yr, t 1.4 |
| 2009–2020 | +3.59%/yr, t 1.4 | +4.84%/yr, t 1.6 |
| 2021–2024 | +6.10%/yr, t 1.4 | +6.44%/yr, t 1.2 |
| full | +7.15%/yr, t 3.6 | +10.57%/yr, t 4.7 |

At 1.45 (linear) and 1.71 (decile) of equity traded a day, that gross
return pays for about 1.8bp and 2.3bp per side over the full sample, and
about 4bp for the decile book in its best era, 1998–2006. The kill cell is
5bp, so the truncation does not change the verdict.

**Against the prediction.** Confirmed: a positive gross return with |t|
above 3 over the full sample; most of it before 2009; break-even between
1 and 4bp per side (1.3bp on the registered sample at 1% borrow, about
1.8bp on the full sample); killed at the kill cell; the decile book earns
more per unit of turnover (0.025% against 0.020% of gross per unit) without
changing the conclusion. Partly: the current regime is smaller than
before 2009 but larger than 2009–2020. **Wrong:** the same-close version
was predicted to earn clearly more than next-open, the difference being
bid-ask bounce. It earned less, 4.90% against 7.15% a year gross (linear).
One candidate explanation is that closing prices are auction prints with
little bounce in them; that is untested.

**What it settles beyond this strategy.** A book traded once or twice a
day on S&P 500 names needs all-in costs below roughly 2bp per side to
survive. Every other high-turnover equity entry in the catalogue faces
that bar.

## Variants

| n | change | economic reason | run id | t before | t after | trials so far |
|---|--------|-----------------|--------|----------|---------|---------------|

## Verdicts

Each verdict that advances, kills or sizes this strategy, with the run id it
rests on. The results database records who produced that run and at what
effort; a verdict with no run id is not one.

| date | verdict | run id | basis |
|------|---------|--------|-------|
| 2026-09-30 | killed at Stage 1 | `b7b5ee2943e947438a7810a921b03f8a` | kill cell t = −5.52 against a threshold of 1.5; full-sample break-even about 1.8bp per side |
