"""Stage 1 for `overnight-index-hold`, into the real results database.

Checks the archive's opening prices against a second source first, and stops
before computing any return if the check fails. Then evaluates the grid, SPY,
QQQ and IWM, each a counted trial and only SPY the verdict, as nights held from
the close to the next open against SPY held all day, with a buy and a sell
charged on every held night. Reads bars only through the last trading day
strictly before the registered holdout.

The second source is a CSV of `ticker,date,open`, split-adjusted, written from
the broker's daily bars before the run. The archive is opened read-only.
"""
import argparse
import json
import sys

import pandas as pd

from lab.checks import archive_properties, open_prices
from lab.data.archive import default as default_archive
from lab.engine import backtest, costs, pipeline, report, stats
from lab.engine.registry import require_registered
from lab.results.db import default as default_db
from lab.strategies import overnight_index_hold as strat

STRATEGY_ID = "overnight-index-hold"
EXECUTION = "close_to_open"
START = "1998-01-01"
BINDING_CONSTRAINT = (
    "Execution at the auctions: the backtest buys at the closing auction and "
    "sells at the opening auction, which needs the broker to route "
    "market-on-close and market-on-open orders for ETFs. Not yet confirmed."
)
NOT_COMPUTED = (
    "Share of the overnight return from earnings and macro-news nights: NOT "
    "COMPUTED. The archive holds no macro release calendar, and a list recalled "
    "from memory would be a guess presented as data."
)


def bil_flags(inputs, weights, cell):
    """The decision book and SPY buy-and-hold, each against BIL. Flags only."""
    bt = backtest.run(weights, inputs.night[["SPY"]], cell, round_trip=True)
    book = stats.summarise(bt.net, inputs.bil)
    hold = stats.summarise(inputs.benchmark, inputs.bil)
    return [
        "Against BIL (flags, decide nothing):",
        f"  overnight SPY, at the decision cell: active Sharpe {book['active_sharpe_annual']:.2f}, "
        f"active {book['active_mean_pct_per_year']:.2f}% a year",
        f"  SPY held all day: active Sharpe {hold['active_sharpe_annual']:.2f}, "
        f"active {hold['active_mean_pct_per_year']:.2f}% a year",
    ]


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--produced-by", required=True,
                   help="who ran this, for the results database; never hardcoded here")
    p.add_argument("--effort", required=True)
    p.add_argument("--second-source", required=True,
                   help="CSV of ticker,date,open from the broker's daily bars")
    args = p.parse_args()

    spec = require_registered(STRATEGY_ID)
    reg = spec["registration"]
    holdout = reg["holdout_start"]
    archive = default_archive()
    calendar = archive.trading_days(start=START, end=holdout)
    end = calendar[calendar < holdout].max()

    bars = archive.fund_bars(list(strat.GRID) + ["BIL"], start=START, end=str(pd.Timestamp(end).date()))
    second = pd.read_csv(args.second_source, parse_dates=["date"])
    archive_opens = bars[bars["ticker"].isin(strat.GRID)][["ticker", "date", "open"]]
    window = (second["date"].min(), pd.Timestamp(end))
    checks = open_prices.run(archive_opens, second, strat.GRID, *window)
    check_text = open_prices.render(checks) + f"\n  sampled from {window[0]:%Y-%m-%d} to {window[1]:%Y-%m-%d}"
    print(check_text, file=sys.stderr)
    if not all(c.passed for c in checks):
        raise SystemExit("the opening-price check failed; per the registration the run is void. "
                         "No return computed, nothing recorded.")

    inputs = strat.build(bars)
    manifest = json.dumps(archive_properties.report(archive_properties.run(archive)), default=str)
    db = default_db()
    cell = costs.CostModel(reg["decision_slippage_pct"])

    for instrument in strat.GRID:
        night = inputs.night[[instrument]].dropna()
        w = {rule: strat.weights(night, instrument, rule) for rule in reg["sizing_rules"]}
        ev = pipeline.evaluate(
            STRATEGY_ID, w, night, inputs.benchmark.reindex(night.index), db,
            produced_by=args.produced_by, effort=args.effort, data_manifest=manifest,
            binding_constraint=BINDING_CONSTRAINT, base_cost=cell,
            execution=EXECUTION, stage=1, round_trip=True, run_label=f"grid cell {instrument}")
        head = ("" if instrument == reg["parameters"]["instrument"] else
                f"**Grid cell {instrument}: a counted trial, not the verdict.** "
                f"Its 'verdict reads this one' label refers to the sizing rule only.\n\n")
        text = head + report.render(ev) + "\n\n" + check_text + "\n\n"
        if instrument == "SPY":
            text += "\n".join(bil_flags(inputs, w["full"], cell)) + "\n\n" + NOT_COMPUTED + "\n"
        path = pipeline.write_report(text, f"{STRATEGY_ID}-{instrument.lower()}", stage=1)
        print(f"wrote {path}", file=sys.stderr)
        if instrument == "SPY":
            print(text)


if __name__ == "__main__":
    main()
