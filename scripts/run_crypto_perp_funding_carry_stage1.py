"""Stage 1 for `crypto-perp-funding-carry`, into the real results database.

Fetches Deribit funding, perpetual prices and index values for BTC and ETH,
every request cut strictly before the registered holdout, then folds them
onto the equity calendar and evaluates both sizing rules at the registered
cell. Prints the data gaps, the perpetuals' dollar volume and a Hyperliquid
funding cross-check before the report, and writes the report to
`config.data_dir()/reports/`.

Nothing at or after the holdout is requested. The calendar ends two days
before it: the last UTC day before the cutoff has its end price stamped at
the cutoff itself, which the fetch drops.
"""
import argparse
import json
import sys

import pandas as pd
import requests

from lab.checks import archive_properties
from lab.data import funding_history as fh
from lab.data import perp_prices as pp
from lab.data.archive import default as default_archive
from lab.engine import costs, pipeline, report, returns as returns_mod
from lab.engine.registry import require_registered
from lab.results.db import default as default_db
from lab.strategies import crypto_perp_funding_carry as strat

STRATEGY_ID = "crypto-perp-funding-carry"
EXECUTION = "utc_midnight"
COINS = {"btc": ("BTC-PERPETUAL", "btc_usd", "BTC"), "eth": ("ETH-PERPETUAL", "eth_usd", "ETH")}
FETCH_START = "2018-08-01"          # earlier than either perpetual lists
HYPERLIQUID_START = "2023-05-12"
BINDING_CONSTRAINT = (
    "Venue access: Deribit does not serve US persons, so the account cannot "
    "hold the position tested. This measures whether the mechanism pays above "
    "cash on the deepest funding history reachable; whether any venue the "
    "account can use pays the same is separate, since each sets its own rule."
)


def gaps(daily, label):
    bad = daily[daily.isna()]
    print(f"{label}: {len(daily)} days, {len(bad)} missing"
          + (f", first {bad.index.min():%Y-%m-%d}, last {bad.index.max():%Y-%m-%d}" if len(bad) else ""),
          file=sys.stderr)


def cross_check(session, cutoff, deribit_daily, training_start):
    """Mean annualised daily funding, Hyperliquid against Deribit, over the
    training days both venues have complete. A flag, not a trial."""
    print("\n=== Hyperliquid cross-check (flag; funding only, no basis) ===", file=sys.stderr)
    lines = []
    for coin, (_, _, hl) in COINS.items():
        frame = fh.fetch_hyperliquid(session, hl, HYPERLIQUID_START, cutoff)
        hl_daily = fh.daily_funding(frame)
        both = pd.concat({"hl": hl_daily, "deribit": deribit_daily[coin]}, axis=1).dropna()
        both = both[both.index >= pd.Timestamp(training_start)]
        apr = both.mean() * strat.FUNDING_DAYS_PER_YEAR * 100.0
        lines.append(f"{coin.upper()}: {len(both)} common days, Hyperliquid {apr['hl']:.2f}% a year, "
                     f"Deribit {apr['deribit']:.2f}% a year, difference {apr['hl'] - apr['deribit']:.2f} points")
    for line in lines:
        print(line)
    return lines


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--produced-by", required=True,
                   help="who ran this, for the results database; never hardcoded here")
    p.add_argument("--effort", required=True)
    args = p.parse_args()

    spec = require_registered(STRATEGY_ID)
    reg = spec["registration"]
    cutoff = reg["holdout_start"]
    session = requests.Session()
    archive = default_archive()

    ratio, funding, volume = {}, {}, {}
    for coin, (instrument, index_name, _) in COINS.items():
        print(f"fetching {instrument} up to {cutoff} (exclusive)", file=sys.stderr)
        rates = fh.fetch_deribit(session, instrument, FETCH_START, cutoff)
        perp = pp.fetch_perp_hourly(session, instrument, FETCH_START, cutoff)
        index = pp.fetch_index(session, index_name, cutoff)
        fh.write(rates, f"deribit-{coin}")
        pp.write(perp.set_index("time"), f"perp-{coin}")
        pp.write(index.set_index("time"), f"index-{coin}")
        funding[coin] = fh.daily_funding(rates)
        prices = pp.day_end_prices(perp, index)
        ratio[coin] = prices["ratio"]
        daily_volume = perp.set_index("time")["usd_volume"].resample("D").sum()
        volume[coin] = daily_volume[daily_volume.index >= pd.Timestamp(reg["current_regime_start"], tz="UTC")].mean()
        gaps(funding[coin], f"{coin} funding")
        gaps(ratio[coin], f"{coin} price ratio")

    last = pd.Timestamp(cutoff) - pd.Timedelta(days=2)
    calendar = archive.trading_days(start=FETCH_START, end=last)
    calendar = pd.DatetimeIndex(calendar[calendar <= last])
    bars = archive.fund_bars(["BIL"], start=str(calendar.min().date()), end=str(calendar.max().date()),
                             columns=None)
    bil = returns_mod.close_to_close(bars)["BIL"].rename("BIL")

    # start where both coins have a complete run of rows, not where a venue's
    # listing began; a hole after that point is reported and stops the run
    inputs = strat.assemble(ratio, funding, bil, calendar)
    complete = (inputs.returns[["btc", "eth"]].notna().all(axis=1)
                & inputs.funding.notna().all(axis=1) & inputs.benchmark.notna())
    first = complete[complete].index.min()
    inputs.weights_by_sizing = {k: v.loc[first:] for k, v in inputs.weights_by_sizing.items()}
    inputs.returns, inputs.funding, inputs.benchmark = (
        inputs.returns.loc[first:], inputs.funding.loc[first:], inputs.benchmark.loc[first:])
    print(f"evaluated rows {inputs.returns.index.min():%Y-%m-%d} .. {inputs.returns.index.max():%Y-%m-%d} "
          f"({len(inputs.returns)} rows); holdout {cutoff} unseen", file=sys.stderr)
    for coin, v in volume.items():
        print(f"{coin.upper()} perpetual average daily dollar volume since "
              f"{reg['current_regime_start']}: ${v:,.0f}", file=sys.stderr)

    check = cross_check(session, cutoff, funding, reg["current_regime_start"])

    manifest = json.dumps(archive_properties.report(archive_properties.run(archive)), default=str)
    db = default_db()
    ev = pipeline.evaluate(
        STRATEGY_ID, inputs.weights_by_sizing, inputs.returns, inputs.benchmark, db,
        produced_by=args.produced_by, effort=args.effort, data_manifest=manifest,
        binding_constraint=BINDING_CONSTRAINT, base_cost=costs.CostModel(reg["decision_slippage_pct"]),
        funding=inputs.funding, execution=EXECUTION, stage=1)
    text = report.render(ev) + "\n\nCross-check (flag):\n" + "\n".join(check) + "\n"
    path = pipeline.write_report(text, STRATEGY_ID, stage=1)
    print(f"wrote {path}", file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()
