+++
# One file per strategy, named <id>.md. The block between the +++ fences is
# machine-read; the engine refuses to run a strategy whose block is incomplete.
# Copying this file and leaving a placeholder in place is meant to fail.

id = "TODO-strategy-id"
family = "TODO-family"            # the unit deflation is computed over
provenance = "TODO"               # literature | own_observation | data_derived
source = "TODO"                   # paper, book or the observation it came from
account = "TODO"                  # which account this needs, e.g. individual-margin
enabling_step = "TODO"            # the concrete step that makes the account usable
stage = 0                         # 0 define, 1 in-sample, 2 adjust, 3 out of sample, 4 paper, 5 live

[registration]
registered_on = "TODO"            # YYYY-MM-DD, before the first run
hypothesis = "TODO"
economic_reason = "TODO"          # why this should pay, in words, before any numbers
prediction = "TODO"               # what I expect to see; written before looking
universe = "TODO"                 # point-in-time rule, stated
horizon = "TODO"                  # holding period and rebalance frequency
benchmark = "TODO"                # size- and style-matched; a ticker in fundprices
parameters = {}                   # name = value. Five or fewer in total
sizing_rules = []                 # at least two; each is reported
holdout_start = "TODO"            # YYYY-MM-DD; data on or after this stays unseen until Stage 3
kill_criteria = "TODO"            # what result ends this, decided in advance
ruleset = "v2"                    # the rule set this is registered under; see METHODOLOGY.md
decision_sizing = "TODO"          # the one sizing rule the verdict is read on; one of sizing_rules
decision_execution = "TODO"       # the one execution convention the verdict is read on, e.g. next_open
decision_slippage_pct = 0         # slippage per side, in percent, at the verdict's cost cell; must be positive
decision_borrow_apr = 0           # borrow, percent a year, at that cell; required when the book shorts
current_regime_rule = "TODO"      # the stated rule that defines "current regime"
current_regime_start = "TODO"     # YYYY-MM-DD, the date that rule produces
data_derived_burden = ""          # required when provenance is data_derived: why this is not a fit
+++

# TODO-strategy-id

## Stage 0 — definition

Entry rule, exit rule, and every parameter with its value and the reason for it.
Nothing in this section changes after the first run. Changes go in the variants
table below with their reason.

## Binding constraint

Which account limit binds this strategy, taken from `docs/account.md`, and what
step would relax it.

## Stage results

One subsection per stage run, each naming its run id from the results database.
Absolute and active figures are labelled as such at the point they appear.

## Variants

Every variant is a trial for deflation. One change at a time, the economic
reason written before the run. Below |t| = 2.0 at most one adjustment.

| n | change | economic reason | run id | t before | t after | trials so far |
|---|--------|-----------------|--------|----------|---------|---------------|

## Verdicts

Each verdict that advances, kills or sizes this strategy, with the run id it
rests on. The results database records who produced that run and at what
effort; a verdict with no run id is not one.

| date | verdict | run id | basis |
|------|---------|--------|-------|
