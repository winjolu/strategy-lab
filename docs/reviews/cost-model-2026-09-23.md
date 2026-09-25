# Cost model review, 2026-09-23

A second pass over `lab/engine/costs.py` and the drift, turnover and
financing arithmetic in `lab/engine/backtest.py`, written separately from
the first and aimed at breaking it rather than confirming it.

## Method

An independent implementation that tracks dollar positions and cash rather
than weights: trade to the target at the close it takes effect, pay
slippage, commission, borrow on the short book and margin interest on the
debit out of equity, then earn the next day. Run against the engine on
random panels: a daily long/short book at 342x turnover a year, a constant
1.6x levered long book, and a long-only book rebalanced weekly. Then a set
of edge cases aimed at each guard.

## Agreed

- **Slippage and commission** are charged per side on the sum of absolute
  weight changes, so a switch between two names costs two sides. Correct.
- **Borrow and margin** accrue over calendar days on a 360-day basis, so a
  Monday carries three days. Checked directly: 10bp a weekday and 30bp on
  Monday at a 36% rate.
- **Turnover against drifted weights** matches the dollar simulation. At
  zero cost the two agree to machine precision on every panel.
- **The one-row shift** holds. A decision on a non-trading day maps to the
  next session and is then shifted, which is late rather than early.
- **The sweep and headline cell** pick 0.25% slippage and 8% borrow for a
  short book, and carry no borrow rate for a long-only one.

## Disagreed, and fixed

1. **Every row was a daily rebalance.** A weight row was carried forward
   and the book was traded back to it every day, so a strategy supplying
   weekly or monthly rows paid for daily rebalancing and earned a
   constant-mix return it would never have held. A 50-name equal-weight
   book decided once and never changed ran 5.9x turnover a year and paid
   1.48% a year at the headline cell, against a 0.25% entry. For designs
   whose active edge is one to three points a year that is the whole
   result. Now each row is a rebalance and positions drift between rows,
   which is buy-and-hold between decisions. Strategies with daily rows are
   unaffected.
2. **Every normalised long-only book counted as levered.** Weights summing
   to 1 + 1e-16 produced a positive debit, and 200 of 200 random
   normalised long-only books raised `CostNotStated` for want of a margin
   rate. The obvious workaround, stating a zero margin rate, would later
   let real leverage run free. Exposure is now compared with a 1e-9
   tolerance, and leverage of 1.001 still demands a rate.
3. **A book could lose more than its equity and keep going.** At 2x on a
   -70% day equity went to -0.40 and compounded from there, and every
   statistic downstream is meaningless. It now raises `EquityExhausted`,
   as do costs that exhaust equity on their own.
4. **An infinite return passed straight through** to the net series. It
   now raises; it means a zero price or a units break upstream.

## Accepted and documented rather than changed

- **Trades are sized on start-of-day equity**, before that day's costs
  come out. Against the dollar simulation this flatters by 0.12% over 300
  days for the weekly book and 0.19% for the daily long/short book at the
  headline cell, growing to 0.74% at 0.50% slippage and 342x turnover.
  That is under 1% of the cost charged in every case.
- **The final exit is not charged**; the book is marked to market at the
  end. A single round trip is charged 0.25%, not 0.50%. Immaterial over a
  full history, and worth remembering on a short current-regime slice.
- **No short rebate and no interest on idle cash.** Both conservative.
- **The debit is long exposure beyond equity**, so short proceeds do not
  finance longs. Conservative for a 130/30 design, and right for a retail
  Reg T account.
- **The margin rate is carried, not swept.** A levered strategy's report
  should state the rate used; sweeping it is worth adding before the first
  levered design reaches Stage 1.
- **Commission has no per-order minimum.** Correct at a zero-commission
  broker; wrong anywhere else, where at $240 a position it would matter.

## Why the existing suite missed these

None of the 150 tests distinguished rebalance-daily from hold-and-drift:
every test supplied a row per day, and the test named for drift asserted
the daily-rebalance behaviour under a docstring that described the other
one. The fixes add tests for each defect, and the mutation harness now
includes carry-forward instead of drift, drift ignored in turnover, zero
and oversized tolerance, ruin undetected, and infinite returns allowed.

## Independence

The dollar simulation is the second implementation the two-implementation
rule asks for. It shares no code with the engine and represents the book
differently, as positions and cash rather than weights, so an error common
to both would have to be made twice in two forms.
