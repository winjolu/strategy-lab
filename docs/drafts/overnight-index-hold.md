# overnight-index-hold — draft registration, not yet registered

Drafted 2026-10-21, before any look at overnight or intraday returns. It
becomes a registration when it moves to `registry/overnight-index-hold.md`,
and `registered_on` is the date of that commit. Queued after the re-measure of
`crypto-perp-funding-carry`.

```toml
id = "overnight-index-hold"
family = "equity-overnight-seasonality"
provenance = "literature"
source = "Cliff, Cooper & Gulen (2008, working paper), Return differences between trading and non-trading hours; Lou, Polk & Skouras (2019, JFE), A tug of war: overnight versus intraday expected returns; Boyarchenko, Larsen & Whelan (2023, RFS), The overnight drift. Citations recalled from memory; send them to the methods-review literature check before the first run."
account = "individual-margin"
enabling_step = "Confirm the broker accepts market-on-close and market-on-open (closing and opening auction) orders for ETFs. If not, the execution convention becomes last trade and first trade, and the cost cell rises."
stage = 0

[registration]
registered_on = "<date of the first commit>"
hypothesis = "SPY held only from the close to the next open earns about as much as SPY held all day, with roughly half the time exposed, because the US equity premium has been earned mostly overnight. Equivalently, SPY's open-to-close return is near zero or negative."
economic_reason = "Holding through hours when the market is closed carries jump and illiquidity risk that is paid for. End-of-day selling by dealers and institutions reverses overnight (Boyarchenko et al.). Different investor groups trade at the open and at the close (Lou et al.)."
prediction = "Written before any look. On the full archive, SPY's mean overnight return exceeds its mean intraday return. Published gaps are halved, per the shared rules. Over the training window the before-cost active return against SPY is near zero, because the training years were a strong market. At 0.01% per side the active Sharpe against SPY is below 1.0. Against BIL, the overnight book's Sharpe is positive but below buy-and-hold SPY's. My central expectation is a Stage 1 kill. The reason to run it anyway: it is cheap to test, and a clear result on whether intraday SPY has been dead money settles a question that shapes the core holding."
universe = "SPY. Declared grid, each cell a counted trial: SPY, QQQ, IWM."
horizon = "Buy at the close, sell at the next open, every trading day. Hold BIL or cash intraday."
benchmark = "SPY"
parameters = { instrument = "SPY", vol_target_pct = 10.0, vol_lookback_days = 63, gross_cap = 1.0 }
sizing_rules = ["full", "vol_target"]
slippage_sweep_pct = [0.0, 0.005, 0.01, 0.02, 0.05]
holdout_start = "2025-10-01"
kill_criteria = "Stage 1 reads the training window only (2022-10-03 to 2025-09-30), full sizing, close_to_open execution, 0.01% per side. Killed with no rescue if the active Sharpe against SPY at the 0.0% cell is below 1.0. Report BIL-relative figures as flags. The run is void if the opening-price check fails."
ruleset = "v2"
decision_sizing = "full"
decision_execution = "close_to_open"
decision_slippage_pct = 0.01
current_regime_rule = "Rule set v2's training window."
current_regime_start = "2022-10-03"
```

**Validity check, run before any returns.** Compare archive SPY, QQQ and IWM
opens against a second source (the broker's bars) on 250 random dates per
ticker. The run is void if more than 1% of dates differ by more than 0.1%. The
disagreeing dates are not filtered out: per the shared method rules, that is
not a fix.

**Flags to report.** Break-even cost per side. Turnover is 504 sides a year,
so each 1bp per side costs about 5% a year. The share of the overnight return
that comes from earnings and macro-news nights. The training figures alongside
the context history since 1998.

**Practical flag, not a gate.** In a taxable account every day is a
short-term round trip. Re-buying SPY the same evening after a losing night
triggers the wash-sale rule, which defers that loss. To be noted before any
paper slot.

**Out of scope.** Boyarchenko's drift is concentrated around the European
open, about 2 to 4 a.m. ET. Capturing it precisely needs futures with intraday
data, which the futures data purchase in the queue would unblock.

## Points to settle before registering

- The overnight return across an ex-dividend date: SPY goes ex at the open, so
  a raw close-to-open return falls by the dividend. `lab.engine.returns` puts
  the open on the `closeadj` basis, which credits it; the registration should
  say that is the convention.
- Intraday cash: holding BIL intraday means trading it twice a day at its own
  cost. Cash at zero intraday is simpler and costs about one day's bill yield
  in two; the draft should pick one.
- The engine has no close-to-open convention yet. `returns.open_to_open`
  exists; a close-to-open frame (close of `t` to open of `t + 1`, decided at
  the close of `t`) needs adding and its own look-ahead test, since the
  decision and the trade share the close.
