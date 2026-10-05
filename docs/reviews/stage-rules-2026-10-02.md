# Stage rules review and proposal, 2026-10-02

Status: **the general rules were adopted on 2026-10-03 and moved into
the shared method file, `~/market-data/market-core/METHODOLOGY.md`, under
"Evaluation stages". That file is authoritative; where this one differs,
it is out of date.** This document is the review record: the findings in
this lab, the reasoning, the numbers, and the build list. None of the
code is built yet. A registration keeps the rules it was registered
under, so the killed strategy stays killed and no registered threshold is
changed after the fact.

## Why

The first real Stage 1 run showed that a strategy can pass a significance
test before costs and fail it after, and raised a harder question: a
test that needs decades of history locks out anything that has only
worked recently. Answering that by adding a second premise next to the
first would repeat the problem this review found. The rules have been
accumulating from several sources, and nobody has checked that they agree.

## What disagrees today

Each row was checked against the code or the registry, not recalled.

| # | Finding | Where |
|---|---|---|
| 1 | The t-statistic is a gate in three places. The registrations kill below t = 1.5; the template limits adjustments "below |t| = 2.0"; and `stats.band()` returns the phrase "record and drop" as the label for a statistic, which puts a verdict inside a descriptive function. | `registry/*.md`, `registry/TEMPLATE.md`, `lab/engine/stats.py` |
| 2 | "In-sample" and "current regime" have no shared definition. One registration uses the three years before its holdout; the other uses a structural date in its own market. Two strategies are not measured on comparable windows. | `current_regime_rule` in both registrations |
| 3 | Holdout lengths differ without a rule. One holdout is about two years; the other started 2026-04-01, so it holds about six months, too short for any Sharpe to be informative. | `holdout_start` in both registrations |
| 4 | The shared method says to report Sharpe, drawdown and MAR, not CAGR. The report prints CAGR in the absolute line and as a column in every cost sweep. MAR is itself CAGR over drawdown, so the shared rule's premises need reconciling, not just the report. | `lab/engine/report.py`, `METHODOLOGY.md` |
| 5 | The shared method requires a random-thinning control on every filter. No code, test or registration mentions one. It has never been exercised. | `METHODOLOGY.md`; nothing in the lab |
| 6 | The minimum track record length is computed only when the t band reads "underpowered". A diagnostic that exists only when a gate lands in a certain place is a gate by another name. | `lab/engine/stats.py` |
| 7 | Stages 2 to 5 exist as numbers in the template and nowhere else. The only enforced rule is that data on or after the holdout is refused before Stage 3. There is no rule that the holdout is spent once, none for what a Stage 2 adjustment may be, and nothing at all for paper trading. | `registry/TEMPLATE.md`, `lab/engine/pipeline.py` |
| 8 | Significance is estimated differently per universe (Newey-West on daily equity returns; clustering by event for event contracts) without the rule set saying so. Legitimate, but undeclared. | registrations |
| 9 | The decision and the report are computed at different cost cells. Kill criteria are prose, read by hand, and the first registration's decision cell is 5 basis points with 1% borrow. The engine knows only its own headline cell, 25 basis points with 8% borrow, and computes the report's headline significance, the current-regime slice and the Sharpe stored for deflation there. Deflation's dispersion is therefore estimated from figures at a cell no decision uses. Which sizing rule and execution convention the decision reads is also prose only. | `lab/engine/costs.py`, `lab/engine/pipeline.py`, `kill_criteria` |

## Principle: one rule set

Every threshold, window and statistic used in a run comes from one
numbered rule set. A registration names the version it is under, and the
engine refuses a run whose registration and code disagree. A premise from
outside, a paper or a book, enters only by being written into the rule
set with its reasoning and with every conflict against the existing rules
resolved in writing. Citing it in passing does not count.

Every number in a report is one of two things:

- **A gate.** It has a threshold written before the run, and it decides
  whether the strategy advances.
- **A flag.** It is reported with a plain label and never decides anything.

A number must not be both, and the wording of a flag contains no verdict.

## Proposed rule set, version 2

### Windows

- **Training window.** The fixed length of three years ending on the last
  trading day before the holdout. The same rule for every universe,
  replacing each registration's own regime rule.
- **Context history.** Everything earlier, reported as a flag and never
  a gate. It says whether the edge existed before, which is the
  existence question the long sample is good for.
- **Out-of-sample window.** The holdout date to the present. Each
  candidate sees it once. The results database records every look, and
  the report states how many candidates have seen it so far.
- **Holdout length.** The out-of-sample score is not computed until the
  holdout holds a minimum length of data; until then the strategy waits.
  Stating that a short holdout "cannot discriminate" and running it anyway
  would leave the gate undefined. The minimum is an open decision.
- **Known conflict.** A uniform three-year window collides with a
  structural break inside it. The event-contract registration says its
  market held a different population before 2025-04-01, so three years
  before its holdout would include two years of data that registration
  itself calls unrepresentative. One stated exception is needed, written
  once in the rule set and not per strategy: open decision below.

### Gates

`S` = 1.5 is a target, not a cliff. A measured Sharpe of 1.48 and one of
1.52 differ by far less than the margin of error on either (about 0.6 to
0.9), so a hard line at 1.5 would sort strategies on noise. The decision
instead rests on a score, a ranking and a cap.

1. **Score.** Net-of-cost Sharpe of the active return over the training
   and out-of-sample windows pooled into one record. The out-of-sample
   part is still read once. Each window's own figure is reported as a
   flag. (Decided 2026-10-03 in place of the lower of the two windows,
   which rejected most real edges; see "What two windows cost".) The registration
   names, in machine-read fields, the one sizing rule, the one execution
   convention and the one cost cell the score is read at. Every other
   combination is a flag. Scoring whichever sizing rule came out better
   would be selection, and leaving the cell in prose is finding 9.
2. **Tiers, written before any run.**
   - *Clear*: score at or above 1.5.
   - *Borderline*: score from 1.0 up to 1.5. Eligible only for a slot left
     free after every clear candidate, and labelled borderline in every
     report that mentions it.
   - *Below 1.0*: not eligible. Recorded, with its flags, like any other
     result.
3. **The run is valid.** The existing validity conditions (zero-filled
   position-days under 0.1%, concentration limits where registered) void
   a run instead of failing a strategy.
4. **The cap.** At most three strategies are in paper trading at once.
   Eligible candidates fill the slots in score order, so a borderline
   strategy gets in only when fewer than three clear ones exist.

The cap, not the 1.5, is what actually limits selection. Paper trading is
cheap, so a soft zone costs little, and the borderline zone is where
strategies that would be lost to a cliff get a look.

The 1.0 floor is a cliff of its own. On the pooled score a strategy with
no edge clears it 1.5% of the time, so across the catalogue a luck pass
into the borderline tier is more likely than not to happen at least once;
the ranking, the cap and the paper stage's stop rule are what catch it. It is arbitrary in the same
way 1.5 is, and I have put it there only because some floor must exist or
the ranking has no edge. It is an open decision below.

Passing makes a strategy eligible for paper trading. It does not make it
eligible for real money.

### Flags

The t-statistic on active return and its band; deflated Sharpe by family
and lab-wide; the minimum track record length, always computed; the full
history and its sub-period table; gross against net return; break-even
cost at every swept borrow rate; correlation to the benchmark, SPY and
the book; drawdown, MAR and turnover; the quarter-Kelly bound.

The t-statistic stays because it answers "how sure", which Sharpe does
not. On the gate windows themselves it adds little: t is roughly Sharpe
times the square root of the years, so a Sharpe of 1.5 over 2.75 years
is a t near 2.5 almost by construction, and only autocorrelation moves
the Newey-West figure off that. The t that carries information is the
one on the context history, where the window is long enough for it to
differ from what the Sharpe already says.

### Paper stage

- The number of strategies in paper trading at once has a cap, and each
  has a stop rule written before it starts. Without both, promoting
  whichever did best rebuilds the selection problem on forward data.
- Paper trading measures execution: whether fills match the assumed
  costs. It cannot test borrow availability or the market impact of the
  strategy's own orders.
- Real size is a separate stage. It scales with the forward record, using
  the minimum track record length and a haircut applied to the measured
  Sharpe, since the best recent performers are overstated by selection.

### Hypotheses from the literature

A published result is a source of hypotheses, not evidence. Published
anomalies are selected from very large searches on the sample they were
found in, and they are reported as losing a large share of their return
after publication. The figures I have in mind are about half after
publication, and most anomalies failing once micro-caps are down-weighted.
They are quoted from memory and must be checked against the papers before
anything leans on them. The rules:

- **Discount the claim.** The prediction is written from the published
  effect size cut by half, and says so.
- **Costs are always in.** Most papers report gross returns, and a gross
  result from one is never used.
- **List the paper's universe filters.** The registration says which of
  them are kept, which are dropped, and why, before the run.
- **Define the universe by what the account can trade, not by what the
  paper traded and not by what a fund can trade.** An institution is
  limited by capacity: it cannot buy a meaningful position in a small or
  thin name without moving the price. A small account is not, so names
  that are uninvestable at institutional size are legitimate here, and an
  edge that persists because it is too small for a fund to bother with is
  a good reason for it to persist. The registration says when an edge is
  plausibly capacity-limited, and predicts that it weakens as size grows.
- **A name is eligible when an order of the account's size is a small,
  stated fraction of its average daily dollar volume**, read from
  `market_core.liquidity`. A name whose volume cannot be measured is
  ineligible, not assumed liquid.
- **What does not scale down is cost per trade.** A thin name has a wider
  spread however small the order. Spreads are charged at the level for
  that tier of liquidity and swept wider than the large-cap cases. Whole
  shares round at small size. Borrow availability is not in the archive, so
  a short book in small names is an upper bound and probably cannot be
  held; a long-only or long-biased form is the honest test there.

### Rescuing a result near the line

Eligibility for a rescue is itself a gate, so it is stated here and not
read off a flag. A strategy is eligible when its score is borderline, or
when the same score computed before costs is at least the borderline
floor. Below that, no cost-reducing change can help: cutting cost can
lift the net score at most to the gross one, and cutting turnover usually
lowers the gross one too. It does not apply to a strategy with no edge,
and it is not a way to keep trying.

- **One change per variant**, each a trial counted in deflation. At most
  two variants per strategy; after that it is dropped. The parameter count
  stays at five or fewer including the added one.
- **The change targets the diagnosed failure.** If costs ate the edge, the
  change reduces cost, such as turnover, and not the signal. The reason is
  written in the registration before the run.
- **No sweeping and keeping the best.** A value comes from reasoning. If a
  grid is run, it is declared in advance and every cell counts as a trial.
- **Nothing read from the holdout may motivate a variant.** A variant's
  look at the holdout is its own, counted separately. If the parent has
  already used the holdout, the variant waits for forward data.
- **Analytical opinion is a hypothesis, with a stated confidence.** A guess
  about what would work is recorded in the variant's reason before the run
  and scored against the result afterward, so the lab accumulates a record
  of how good such guesses are.
- **Not allowed:** adding conditions until it passes, or choosing a change
  because one sub-period looked better.

Worked example, `xs-mr-khandani-lo`. Under version 1 costs, not edge,
were the failure. Under version 2 it is not eligible for a rescue at all.
The out-of-pipeline diagnostic put the linear book's gross return over
2021–2024 at +6.10% a year (absolute) with t 1.4, which over roughly
three to three and three-quarter years is a gross Sharpe of about 0.7 to
0.8 before the benchmark is even subtracted. That is below the 1.0 floor
before any cost is charged. The figure is approximate, from a diagnostic
rather than a registered run, and it is the only reading of this window
that exists.

The turnover arithmetic, kept because it applies to any daily-rebuilt
book. Turnover here is the sum of absolute weight changes, so a full
flip of a book at 1.0 gross is 2.0 a day, and the daily rebuild's 1.45
already nets some trades. An overlapping hold of `h` days, rebuilding
one `h`-th of the book each day, turns over at most about 2/`h`: 0.4 a
day for five days, a cut of about 3.6 times, not 5. Against the
full-sample break-even (1.8 basis points) a five-day hold would have to
keep about 77% of the daily edge to clear 5 basis points; against the
registered sample's 1.3 it would have to keep more than all of it. A
ten-day hold would need 38% to 53%. Two- and three-day holds cannot
close the gap at any retention. Netting between tranches lowers turnover
somewhat, so these are upper bounds on what is needed.

## What two windows buy

Passing both windows is the mechanism that makes a short sample usable.
For a strategy with a true Sharpe of zero, with the training window at
2.75 years and the out-of-sample window at 2.0:

| `S` | chance one candidate passes both by luck | chance at least one of 41 does |
|---|---|---|
| 1.0 | 0.38% | 14.5% |
| 1.5 | 0.011% | 0.45% |
| 2.0 | about 0.0001% | about 0% |

The chance is the product of the two windows' tail probabilities. It
assumes returns are independent and the windows share no information; real
returns have fat tails and autocorrelation, so these odds are optimistic.

Passing is evidence against pure luck, not a measurement of the Sharpe. A
measured Sharpe of 1.5 has a 95% range of roughly −0.2 to 3.2 on the
training window and −0.5 to 3.5 out of sample.

## What two windows cost

The table above counts only false passes. The other error matters as
much: a real edge failing the gate. Under the same assumptions, the
chance that a strategy with a given true Sharpe reaches each tier:

| true Sharpe | clear (score 1.5 or more) | at least borderline (1.0 or more) |
|---|---|---|
| 0.5 | 0.5% | 5.5% |
| 1.0 | 7% | 25% |
| 1.5 | 25% | 49% |
| 2.0 | 45% | 66% |
| 2.5 | 60% | 76% |

A strategy whose true Sharpe is exactly the target clears a quarter of
the time. Taking the weaker of two short windows is what buys the low
false-pass rate, and this is its price. The limit is not the t-statistic
or any threshold: under five years of data cannot tell a Sharpe of 1
from one of 0 reliably, under any rule.

The alternative is to pool the two windows into one Sharpe over 4.75
years. At a 1.0 threshold a strategy with true Sharpe 1.5 passes 77% of
the time, but a strategy with no edge passes 1.5% of the time, which
across 41 candidates is a luck pass about 45% of the time. At 1.25 the
luck figures are 0.3% and 12%; at 1.5, 0.05% and 2%. Pooling also gives
up the separate confirmation the out-of-sample window was meant to
provide. Since paper slots are capped and cheap, a more permissive score
costs a slot's time rather than money, which argues for leaning that
way; it is an open decision below.

The candidate count of 41 is a floor. Each variant is another candidate,
so with two per strategy the count could reach about 120. With only the
named sizing rule scored, sizing rules do not add to it.

## Open decisions

Decided 2026-10-02: `S` = 1.5 as a target and not a hard gate; training
window of three years; at most three strategies in paper trading at once.

Decided 2026-10-03: the score pools the two windows. A paper slot costs
compute and time, not money, so a more permissive score is the cheaper
error.

Decided 2026-10-03: the borderline floor is 1.0, about twice the
smoothness of holding the index, below which a strategy is not clearly
worth a slot. The out-of-sample score is not computed until the holdout
holds at least one year of data. The holdout boundary moves forward once
a year; the year it covered becomes training data, which is allowed to
have been seen, and a fresh holdout begins.

Decided 2026-10-03: a structural break shortens the training window only
on two pieces of evidence, both required. First, a dated, documented
cause: a rule change, a new product, a new kind of participant. Second,
a measurable step in the market itself around that date, in volume,
listings, participants or spreads, and never in the strategy's own
returns. A story without a measured step does not count, and neither
does a step without a cause. The case is written as a short memo of
those facts with a recommendation, the decision is made by judgment, and
it goes into the registration with its date and reasons before any
result of the strategy exists. The engine already refuses to run an
unregistered strategy, which enforces that order. With no break argued,
the three-year default applies, and every report on a shortened window
says so.

Decided 2026-10-05, taking the proposed defaults: the holdout boundary
moves on 1 October, so equities move to 2025-10-01 (nothing had opened
the 2024 holdout), and a strategy registered before a move keeps the
holdout it registered with; a measured Sharpe is halved before sizing; a
published effect size is halved before a prediction is written; a name
is tradeable when an order is at most 1% of its average daily dollar
volume; at most two variants per strategy.

Still open:

- The two existing registrations. The killed one stays under version 1.
  The unrun one can be re-registered under version 2 before its first
  run, with its holdout length addressed first.

## Code this would need

Built 2026-10-05 and recorded in `QUEUE.md`: the rule-set field and the
registered decision cell with the report computed there; the pooled score
and its tiers; the holdout's one-year minimum, single read and look counter;
band labels that describe and decide nothing; the minimum track record
always reported; CAGR out of the report body; the benchmark-coverage refusal;
break-even at every borrow rate; and the random-thinning control, which was
built and not removed from the shared method.

Not built: a per-name spread estimate for the thin-name tiers, since the
archive holds no quotes. Estimators built from daily high, low and close
exist in the literature (Corwin and Schultz 2012 and Abdi and Ranaldo 2017
as I recall them, to be checked), and they inherit the archive's volume and
split-rounding defects.
