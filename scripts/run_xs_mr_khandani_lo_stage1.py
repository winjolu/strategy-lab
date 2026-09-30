"""Stage 1 for `xs-mr-khandani-lo`: both execution conventions, into the
real results database.

Reads bars only through the last trading day strictly before the
registered holdout, taken from the archive's own calendar. Prints the rendered report for each convention and writes it to
`config.data_dir()/reports/`.
"""
import argparse
import sys

from lab import config
from lab.checks import archive_properties
from lab.data.archive import default as default_archive
from lab.engine import costs, pipeline, report
from lab.engine.registry import require_registered
from lab.results.db import default as default_db
from lab.strategies import xs_mr_khandani_lo as strat

STRATEGY_ID = "xs-mr-khandani-lo"
BINDING_CONSTRAINT = (
    "Whole-share shorting at this account size: at 1.0 gross on roughly "
    "$20k, neither the linear nor the decile book can be held as "
    "specified, since the short side rounds away on names trading above a "
    "few tens of dollars. This backtest measures whether the edge exists "
    "after costs; whether the account can hold it is separate."
)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--produced-by", required=True,
                  help="who ran this, for the results database; never hardcoded here")
    p.add_argument("--effort", required=True)
    args = p.parse_args()

    spec = require_registered(STRATEGY_ID)
    reg = spec["registration"]
    start, holdout = "1998-03-31", reg["holdout_start"]

    archive = default_archive()
    # `build`'s `end` is inclusive (the archive layer reads `date <= end`),
    # so the holdout date itself must never be passed as `end`: that would
    # put a holdout close in the close-to-close frame's last row, which the
    # open-to-open frame's dropped last row does not protect against. The
    # last trading day strictly before the holdout is what "exclusive of
    # the holdout" actually requires.
    calendar = archive.trading_days(start=start, end=holdout)
    end = calendar[calendar < holdout].max()
    print(f"Building inputs for {start} .. {end} (holdout starts {holdout}, unseen)",
          file=sys.stderr)
    inputs = strat.build(archive, start, end)
    print(f"universe: {inputs.weights_by_sizing['linear'].shape[1]} tickers; "
          f"{len(inputs.returns_cc)} cc rows, {len(inputs.returns_oo)} oo rows", file=sys.stderr)

    manifest = archive_properties.report(archive_properties.run(archive))
    import json
    manifest_str = json.dumps(manifest, default=str)

    db = default_db()
    cost = costs.CostModel(0.25, borrow_apr=8.0)  # headline cell; the sweep covers the rest

    for label, ret, bench, spy in (
        ("open-to-open (headline, next-open execution)", inputs.returns_oo, inputs.benchmark_oo, inputs.spy_oo),
        ("close-to-close (upper bound, as published)", inputs.returns_cc, inputs.benchmark_cc, inputs.spy_cc),
    ):
        print(f"\n=== {label} ===", file=sys.stderr)
        ev = pipeline.evaluate(
            STRATEGY_ID, inputs.weights_by_sizing, ret, bench, db,
            produced_by=args.produced_by, effort=args.effort, data_manifest=manifest_str,
            binding_constraint=BINDING_CONSTRAINT, base_cost=cost,
            spy=spy, on_missing="zero", stage=1,
        )
        text = report.render(ev)
        tag = "open-to-open" if "open-to-open" in label else "close-to-close"
        path = pipeline.write_report(text, f"{STRATEGY_ID}-{tag}", stage=1)
        print(f"wrote {path}", file=sys.stderr)
        print(text)


if __name__ == "__main__":
    main()
