"""Render an evaluation as the Stage 1 report.

The report is a view. Every number in it was already recorded against a run
id in the results database, and the run id is printed beside it, so a
figure quoted from here can always be traced to its code version, its data
manifest and its configuration.

Every figure carries its own label at the point it appears, because a
convention set three tables earlier fails silently exactly once, in the
table that matters. "abs" is what the money did; "active" is the edge over
the registered benchmark.
"""
import math

from lab.engine.costs import HEADLINE_BORROW, HEADLINE_SLIPPAGE


def _f(x, spec=".2f"):
    return "n/a" if x is None or (isinstance(x, float) and not math.isfinite(x)) else format(x, spec)


def _days_to_years(days):
    return "never (observed Sharpe does not exceed zero)" if days == float("inf") \
        else f"{days:,.0f} days, {days / 252:.1f} years"


def _corr(c):
    return "NOT COMPUTED (no series supplied)" if c is None else f"{c['corr']:+.2f} (n={c['n']})"


def _sizing_block(r, benchmark):
    h = r.headline
    lines = [f"### Sizing rule: {r.name}   (run `{r.run_id}`)", ""]
    lines += [
        f"Headline cost cell: slippage {HEADLINE_SLIPPAGE}% per side"
        + (f", borrow {HEADLINE_BORROW}% a year" if r.has_shorts else ", no shorts") + ".",
        "",
        f"- **Significance (active return vs {benchmark}):** t = {_f(h['active_t_newey_west'])} "
        f"Newey-West, {h['active_hac_lags']} lags. Band: **{h['band']}**"
        + (" (negative: the edge is below the benchmark)" if h['active_t_newey_west'] < 0 else "") + ".",
        f"- Active return: {_f(h['active_mean_pct_per_year'])}% a year (active); "
        f"active Sharpe {_f(h['active_sharpe_annual'])} annualised (active).",
        f"- Absolute: CAGR {_f(h['absolute_cagr_pct'])}% (abs), Sharpe "
        f"{_f(h['absolute_sharpe_annual'])} annualised (abs).",
        f"- Risk: max drawdown {_f(h['absolute_max_drawdown_pct'])}% (abs), MAR {_f(h['absolute_mar'])}. "
        f"Longest time under water {h['time_under_water_days_longest']:,} days; "
        f"{h['time_under_water_share'] * 100:.0f}% of days under water; "
        f"currently {h['time_under_water_days_current']:,} days.",
        f"- Turnover: {_f(r.turnover_annual, '.1f')}x equity a year. "
        f"Gross exposure used {_f(r.gross_used)}x; "
        + (f"quarter-Kelly supports {_f(r.kelly_quarter)}x on this same sample, an upper bound and not a target."
           if r.kelly_quarter > 0 else
           "the sample mean return is not positive, so Kelly supports no exposure at all."),
    ]
    if r.gross_used > r.kelly_quarter > 0:
        lines.append("  **Gross exposure exceeds quarter-Kelly.**")
    if "min_track_record_days" in h:
        lines.append(f"- Underpowered, so: minimum track record for the active Sharpe to be "
                     f"distinguishable from zero at 95% is {_days_to_years(h['min_track_record_days'])}.")
    for label, key in (("family", "deflated"), ("lab-wide", "deflated_lab")):
        d = h[key]
        if d:
            lines.append(f"- Deflated over {d['trials']} {label} trials: DSR = {_f(d['dsr'])} against an "
                         f"expected best-of-noise Sharpe of {_f(d['benchmark_sharpe_periodic'], '.4f')} per day (active).")
        else:
            lines.append(f"- **Not deflated ({label}):** fewer than two trials with a recorded Sharpe, "
                         "so their dispersion cannot be measured. No figure is assumed.")
    lines += [
        f"- Correlation to {benchmark}: {_corr(h['corr_to_benchmark'])}. "
        f"To SPY: {_corr(h['corr_to_spy'])}. To the current book: {_corr(h['corr_to_book'])}.",
        f"- Daily return distribution (abs): 1st pct {_f(h['distribution_daily_absolute']['q01'], '.4f')}, "
        f"median {_f(h['distribution_daily_absolute']['q50'], '.4f')}, 99th "
        f"{_f(h['distribution_daily_absolute']['q99'], '.4f')}; skew "
        f"{_f(h['distribution_daily_absolute']['skew'])}, excess kurtosis "
        f"{_f(h['distribution_daily_absolute']['excess_kurtosis'])}; worst day "
        f"{_f(h['distribution_daily_absolute']['worst'], '.4f')}.",
    ]
    if isinstance(r.regime, dict):
        lines.append(f"- **Current regime** (rule in the registry): t = {_f(r.regime['active_t_newey_west'])} "
                     f"active, band **{r.regime['band']}**, over {r.regime['n_days']:,} days; "
                     f"active return {_f(r.regime['active_mean_pct_per_year'])}% a year (active).")
    else:
        lines.append(f"- Current regime: not reported ({r.regime}).")
    if r.zeroed_position_days:
        lines.append(f"- **{r.zeroed_position_days:,} position-days had no return and were set to zero** "
                     "by explicit choice.")
    lines += ["", "Cost sweep, t on active return (Newey-West):", "",
              "| slippage / side | borrow APR | active t | band | active %/yr | abs CAGR % |",
              "|---|---|---|---|---|---|"]
    for row in r.sweep:
        lines.append(f"| {row['slippage_pct']}% | {_f(row['borrow_apr'], '.0f') if row['borrow_apr'] is not None else '-'} "
                     f"| {_f(row['active_t'])} | {row['band']} | {_f(row['active_pct_per_year'])} "
                     f"| {_f(row['absolute_cagr_pct'])} |")
    lines.append("")
    return "\n".join(lines)


def render(ev):
    reg = ev.spec["registration"]
    head = [
        f"# {ev.strategy_id} — Stage {ev.stage} report", "",
        f"Provenance: **{ev.spec['provenance']}**. Family: {ev.spec['family']}. "
        f"Registered {reg['registered_on']}; holdout from {reg['holdout_start']}, unseen.", "",
        f"**Binding constraint:** {ev.binding_constraint}", "",
        "Prediction, written before the run:", "", f"> {reg['prediction']}", "",
    ]
    if any(r.has_shorts for r in ev.results):
        head += ["**Short book: every figure here is an upper bound.** No borrow-availability "
                 "data exists locally; borrow is charged at 1% and 8%.", ""]
    if ev.book_note:
        head += [ev.book_note, ""]
    body = [_sizing_block(r, ev.benchmark_name) for r in ev.results]
    tail = ["---", "Figures above are recorded against the run ids shown. Not a recommendation; "
            "not financial advice. A verdict needs the run id recorded in the registry."]
    return "\n".join(head + body + tail) + "\n"
