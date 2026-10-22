+++
id = "overnight-index-hold"
family = "equity-overnight-seasonality"
provenance = "literature"
source = "Cliff, Cooper & Gulen (2008, working paper), Return differences between trading and non-trading hours; Lou, Polk & Skouras (2019, JFE), A tug of war: overnight versus intraday expected returns; Boyarchenko, Larsen & Whelan (2023, RFS), The overnight drift. Citations recalled from memory and sent to the methods-review literature check on 2026-10-22, before any run."
account = "individual-margin"
enabling_step = "Confirm the broker accepts market-on-close and market-on-open (closing and opening auction) orders for ETFs. If not, the execution convention becomes last trade and first trade, and the cost cell rises."
stage = 0

[registration]
registered_on = "2026-10-22"
hypothesis = "SPY held only from the close to the next open earns about as much as SPY held all day, with roughly half the time exposed, because the US equity premium has been earned mostly overnight. Equivalently, SPY's open-to-close return is near zero or negative."
economic_reason = "Holding through hours when the market is closed carries jump and illiquidity risk that is paid for. End-of-day selling by dealers and institutions reverses overnight (Boyarchenko et al.). Different investor groups trade at the open and at the close (Lou et al.)."
prediction = "Written before any look. On the full archive, SPY's mean overnight return exceeds its mean intraday return. Published gaps are halved, per the shared rules. Over the training window the before-cost active return against SPY is near zero, because the training years were a strong market. At 0.01% per side the active Sharpe against SPY is below 1.0. Against BIL, the overnight book's Sharpe is positive but below buy-and-hold SPY's. My central expectation is a Stage 1 kill. The reason to run it anyway: it is cheap to test, and a clear result on whether intraday SPY has been dead money settles a question that shapes the core holding."
universe = "SPY. Declared grid, each cell a counted trial: SPY, QQQ, IWM. The verdict reads SPY only."
horizon = "Buy at the close, sell at the next open, every trading day. Cash, earning nothing, intraday."
benchmark = "SPY"
parameters = { instrument = "SPY", vol_target_pct = 10.0, vol_lookback_days = 63, gross_cap = 1.0 }
sizing_rules = ["full", "vol_target"]
slippage_sweep_pct = [0.0, 0.005, 0.01, 0.02, 0.05]
holdout_start = "2025-10-01"
kill_criteria = "Stage 1 reads the training window only (2022-10-03 to 2025-09-30), full sizing, close_to_open execution, 0.01% per side. Killed with no rescue if the active Sharpe against SPY at the 0.0% cell is below 1.0. BIL-relative figures are reported as flags. The run is void if the opening-price check fails."
ruleset = "v2"
decision_sizing = "full"
decision_execution = "close_to_open"
decision_slippage_pct = 0.01
current_regime_rule = "Rule set v2's training window."
current_regime_start = "2022-10-03"
data_derived_burden = ""
+++

# overnight-index-hold

## Stage 0 — definition

**The position.** At the close of trading day `t`, buy SPY in the closing
auction; at the open of `t + 1`, sell it in the opening auction. Between the
open and the close the book holds cash, which earns nothing: a broker pays
interest on the end-of-day balance, and at every close the money is in SPY.
Holding BIL intraday instead would add two more trades a day to earn a few
hours of bill yield, so it is not done.

**Returns: close to open, a convention the engine does not have yet.** The
return earned on row `t + 1` is the open of `t + 1` over the close of `t`, minus
one, on the dividend-adjusted basis: the open is carried onto the `closeadj`
basis by `open × closeadj / close` on the same day, as `lab.engine.returns`
does for its open-to-open frame. SPY goes ex-dividend at the open, so on a raw
basis the overnight return on an ex-date falls by the dividend; on the adjusted
basis the dividend is credited to the night it is earned, which matches how the
benchmark's own total return is measured. The decision and the trade share the
close of `t`, so the convention needs its own look-ahead test: a signal built
from the return it is paid must earn nothing.

**Sizing rules.** Both are long only, at most 1.0 gross.

- `full`, the decision book: 1.0 of equity in SPY every night.
- `vol_target`: exposure set so the overnight book's trailing volatility, over
  `vol_lookback_days` overnight returns, targets `vol_target_pct` a year, capped
  at `gross_cap`. A market-on-close order has to be entered before the close is
  known, at about 3:50 p.m. ET, so the night's size uses volatility through the
  previous night's return and never the return ending at the close it trades.

**Costs.** 504 sides a year, so each basis point per side costs about 5% a year.
The sweep runs from 0 to 5 basis points per side; the decision cell is 1, the
closing and opening auctions on the most liquid ETF in the world at an
account-sized order. Nothing is short, so no borrow applies.

**Parameters.**

| name | value | reason |
|---|---|---|
| instrument | SPY | the core holding the question is about |
| vol_target_pct | 10.0 | used only by `vol_target`; a conventional round number, not tuned |
| vol_lookback_days | 63 | used only by `vol_target`; one quarter of trading days |
| gross_cap | 1.0 | no leverage |

**Validity check, run before any return is computed.** The archive's SPY, QQQ
and IWM opens are compared against a second source, the broker's daily bars, on
250 random dates per ticker. The run is void if more than 1% of dates differ by
more than 0.1%. Disagreeing dates are not filtered out: per the shared method
rules, that is not a fix.

**Flags to report.** Break-even cost per side. The share of the overnight
return that comes from earnings and macro-news nights. The training figures
alongside the context history since 1998. Every figure against BIL as well as
SPY.

**Practical flag, not a gate.** In a taxable account every day is a short-term
round trip. Re-buying SPY the same evening after a losing night triggers the
wash-sale rule, which defers that loss. To be weighed before any paper slot.

**Out of scope.** Boyarchenko's drift is concentrated around the European open,
about 2 to 4 a.m. ET. Capturing it precisely needs futures with intraday data,
which the futures data purchase in the queue would unblock.

**Before writing this.** I read the shared method rules, the engine's return
conventions and the draft this registration came from. No overnight or
intraday return was computed, and no price series was read.

## What has to be built before Stage 1

- The close-to-open return frame and its look-ahead test.
- The opening-price check against the broker's bars.
- The strategy module (both sizing rules and the cash leg) and its runner, with
  the grid over SPY, QQQ and IWM counted as trials.

## Binding constraint

Execution at the auctions. The backtest assumes the closing and opening
auction prices; whether the broker routes market-on-close and market-on-open
orders for ETFs is the enabling step above.

## Stage results

None yet.

## Variants

Every variant is a trial for deflation. One change at a time, the economic
reason written before the run.

| n | change | economic reason | run id | Sharpe before | Sharpe after | trials so far |
|---|--------|-----------------|--------|---------------|--------------|---------------|

## Verdicts

| date | verdict | run id | basis |
|------|---------|--------|-------|
