"""Stage 1 evaluation: the one path from a registered strategy to a report.

Everything the methodology says must not be skipped is a check on this
path rather than a habit: the strategy is registered, the sizing rules
reported are the ones registered, the benchmark measured is the one
registered, no data on or after the holdout date is touched before
Stage 3, the binding constraint is stated, costs are swept, and every run
and figure lands in the results database with its code version.

Each sizing rule is one run and one trial. Counting them as trials errs
towards over-deflation, which is the safe direction: they are different
return streams and any of them could have been the one reported.
"""
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from lab import config
from lab.engine import backtest, costs, registry, sizing, stats
from lab.engine.book import Book

HOLDOUT_STAGE = 3


class HoldoutViolation(RuntimeError):
    """Data on or after the registered holdout date reached a pre-Stage-3 run."""


class RegistrationMismatch(RuntimeError):
    """What was passed to evaluate is not what was registered."""


@dataclass
class SizingResult:
    name: str
    run_id: str
    headline: dict
    regime: object
    sweep: list
    turnover_annual: float
    gross_used: float
    kelly_quarter: float
    zeroed_position_days: int
    has_shorts: bool
    cell: tuple = None          # (slippage_pct, borrow_apr) the figures above are read at
    decides: bool = None        # True: the verdict reads this one; None: rule set v1


@dataclass
class Evaluation:
    strategy_id: str
    stage: int
    spec: dict
    binding_constraint: str
    benchmark_name: str
    ruleset: str = "v1"
    execution: str = None
    decision_cell: tuple = None
    book_note: str = None
    results: list = field(default_factory=list)


def sharpe_variance(db, family, name="active_sharpe_periodic"):
    """Sample variance of Sharpe across the family's recorded runs, or None
    when fewer than two exist. Not assumed: with one point there is no
    dispersion to measure, and the report says it did not deflate."""
    values = db.family_figures(family, name)  # family=None: lab-wide
    return float(np.var(values, ddof=1)) if len(values) >= 2 else None


def _guard_holdout(spec, stage, *frames):
    holdout = pd.Timestamp(spec["registration"]["holdout_start"])
    if stage >= HOLDOUT_STAGE:
        return
    for f in frames:
        if len(f.index) and f.index.max() >= holdout:
            raise HoldoutViolation(
                f"data through {f.index.max():%Y-%m-%d} reaches the holdout starting "
                f"{holdout:%Y-%m-%d}; it stays unseen until Stage {HOLDOUT_STAGE}"
            )


def evaluate(strategy_id, weights_by_sizing, returns, benchmark, db, produced_by,
             effort, data_manifest, binding_constraint, base_cost,
             spy=None, book=None, stage=1, lag=1, on_missing="raise",
             registry_directory=None, today=None, execution=None):
    spec = registry.require_registered(strategy_id, registry_directory, today=today)
    reg = spec["registration"]
    if not (binding_constraint or "").strip():
        raise ValueError("every Stage 1 report states its binding constraint")
    if set(weights_by_sizing) != set(reg["sizing_rules"]):
        raise RegistrationMismatch(
            f"sizing rules passed {sorted(weights_by_sizing)} differ from "
            f"registered {sorted(reg['sizing_rules'])}"
        )
    if getattr(benchmark, "name", None) != reg["benchmark"]:
        raise RegistrationMismatch(
            f"benchmark series is named {getattr(benchmark, 'name', None)!r}; "
            f"registered benchmark is {reg['benchmark']!r}"
        )
    _guard_holdout(spec, stage, returns, benchmark, *weights_by_sizing.values())

    regime_start = pd.Timestamp(reg["current_regime_start"])
    family = spec["family"]
    version = registry.ruleset(spec)
    if version == "v2" and not (execution or "").strip():
        raise ValueError("a rule set v2 evaluation states its execution convention")
    out = Evaluation(strategy_id, stage, spec, binding_constraint, reg["benchmark"],
                     ruleset=version, execution=execution)
    if isinstance(book, Book):
        out.book_note = book.note(today)
        book = book.returns

    for name, weights in weights_by_sizing.items():
        probe = backtest.run(weights, returns, base_cost.with_(borrow_apr=0.0, margin_apr=0.0), lag, on_missing)
        models = costs.sweep(base_cost, probe.has_shorts, probe.max_long_gross > 1.0 + backtest.EXPOSURE_TOLERANCE,
                             margin_apr=base_cost.margin_apr,
                             slippage_sweep=reg.get("slippage_sweep_pct"))
        if version == "v2":
            if probe.has_shorts and reg.get("decision_borrow_apr") is None:
                raise costs.CostNotStated(
                    "this book shorts, so the registration must state decision_borrow_apr")
            head = costs.cell(models, reg["decision_slippage_pct"],
                              reg.get("decision_borrow_apr") if probe.has_shorts else None)
            decides = name == reg["decision_sizing"] and execution == reg["decision_execution"]
            out.decision_cell = (head.slippage_pct, head.borrow_apr)
        else:
            head, decides = costs.headline(models), None

        run_id = db.record_run(
            strategy_id, stage,
            {"sizing": name, "parameters": reg["parameters"], "lag": lag,
             "on_missing": on_missing, "base_cost": vars(base_cost),
             "sweep": [vars(m) for m in models]},
            produced_by, effort, data_manifest=data_manifest,
        )
        db.record_trial(run_id, family, reason=f"stage {stage} evaluation, sizing {name}")

        sweep_rows, head_bt = [], None
        for m in models:
            bt = backtest.run(weights, returns, m, lag, on_missing)
            s = stats.summarise(bt.net, benchmark)
            sweep_rows.append({"slippage_pct": m.slippage_pct, "borrow_apr": m.borrow_apr,
                               "active_t": s["active_t_newey_west"], "band": s["band"],
                               "active_pct_per_year": s["active_mean_pct_per_year"],
                               "absolute_cagr_pct": s["absolute_cagr_pct"]})
            tag = f"slip={m.slippage_pct}|borrow={m.borrow_apr}"
            db.record_figure(run_id, f"active_t|{tag}", s["active_t_newey_west"])
            if m is head:
                head_bt = bt
                db.record_figure(run_id, "active_sharpe_periodic", s["active_sharpe_periodic"], "per day")
                db.record_figure(run_id, "active_t", s["active_t_newey_west"], "t on active return")
                db.record_figure(run_id, "annual_turnover", bt.annual_turnover, "x equity per year")

        trials, var = db.trial_count(family), sharpe_variance(db, family)
        headline = stats.summarise(
            head_bt.net, benchmark, spy=spy, book=book, trials=trials, sharpe_variance=var,
            lab_trials=db.trial_count(), lab_sharpe_variance=sharpe_variance(db, None))
        regime_net = head_bt.net[head_bt.net.index >= regime_start]
        try:
            regime = stats.summarise(regime_net, benchmark)
        except ValueError as exc:
            regime = str(exc)

        gross_used = float(head_bt.held.abs().sum(axis=1).max())
        out.results.append(SizingResult(
            name, run_id, headline, regime, sweep_rows, head_bt.annual_turnover,
            gross_used, sizing.kelly_leverage(head_bt.net), head_bt.zeroed_position_days,
            head_bt.has_shorts, (head.slippage_pct, head.borrow_apr), decides,
        ))
    return out


def write_report(text, strategy_id, stage):
    d = os.path.join(config.data_dir(), "reports")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{strategy_id}-stage{stage}.md")
    with open(path, "w") as handle:
        handle.write(text)
    return path
