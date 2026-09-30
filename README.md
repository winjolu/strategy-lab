# strategy-lab

A laboratory for deciding, before any money is at risk, whether a trading
strategy deserves capital, and for killing it cheaply when it does not. It is
built for a small personal account, around one rule: **nothing is measured
until its pass/fail conditions were written down first.**

It follows [weinstein-screener](https://github.com/winjolu/weinstein-screener)
spent 237 registered experiments learning that a plausible strategy can look
convincing for reasons that have nothing to do with the strategy. This one
starts from those lessons: the refusals are built first, and the strategies
come after.

## Where it stands

**One strategy has been tested, and killed.** Cross-sectional mean
reversion on the S&P 500 (`xs-mr-khandani-lo`) has a real edge before costs,
+7.15% a year over 1998–2024 with t = 3.6, but it trades its whole book
about one and a half times a day and pays for only about 1.8 basis points of
cost per side. At its registered kill threshold, 5 basis points and 1%
borrow, the t-statistic on active return is −5.52. The result sets a bar for
every other high-turnover strategy in the catalogue, and the prediction
written before the run got one thing wrong (see `registry/`).

| | |
|---|---|
| Candidate strategies catalogued | 41, ranked by information gained per day of work |
| Strategies registered (prediction and kill criteria fixed before any run) | 2 |
| Strategies tested at Stage 1 | 1, killed |
| Tests | 283 |
| Guards deliberately broken to prove the tests notice | 128, all caught |
| Data collected forward that no vendor sells | Kalshi quotes and order book depth, recorded continuously |

## What building it has already found

Each of these was a wrong belief, caught before it became a number:

- **The first cost model charged every strategy for daily rebalancing.** A
  portfolio set once and never changed paid 1.5% a year in phantom trading cost,
  because each row of weights was traded back to daily. A second implementation
  written from scratch, tracking dollars and cash rather than weights, found it,
  along with three more: rounding error read as leverage, a book that could lose
  more than all its equity and keep going, and an infinite return that passed
  straight through. None of the 150 tests that existed then could have caught the
  first, because every one supplied a row per day.
- **The catalogue's premise about event-contract data was wrong.** It said
  settled Kalshi markets are purged and untestable. Measuring the API showed
  settled prices, outcomes and candlesticks are served back to 2023. Only order
  book depth is unrecoverable, which changed what is urgent.
- **A published fee schedule hid a time dependence.** Kalshi's per-series fee
  multiplier is listed only as today's value. Its change history shows 19 series
  halved on 2026-08-07, so pricing history at the current value would have halved
  their in-sample fees. The published fee table is now the test oracle, including a
  case where binary floating point adds a spurious cent.
- **A survivorship-safe universe cannot use the obvious membership rule.** The
  security master's `lastpricedate` is not refreshed daily and would empty the
  universe for the most recent seven weeks, silently, in exactly the window
  current-regime tests run in. Membership is built from bar presence instead.
- **The archive has a live defect.** Every equity bar since about 2026-08-01 has a
  NULL `permaticker`, the only stable company identity. A property test fails on
  it on purpose; the diagnosis is in `docs/defects/`.

## Method

**Registration.** A strategy is one file in `registry/` with its hypothesis,
economic reason, prediction, parameters (five at most), at least two sizing
rules, holdout date and kill criteria. The evaluation pipeline refuses anything
unregistered or incomplete, and refuses a benchmark or sizing rules that differ
from what was registered. The template is deliberately invalid, so a copy with a
forgotten field fails instead of running against a placeholder.

**No look-ahead by construction.** Strategies hand over weights indexed by
decision date and never touch returns. The engine applies them to a later day's
returns, at least one row later, and a lag below one raises. A signal built from
today's return earns nothing once the engine shifts it, and a test proves it.

**A sealed holdout.** The registered holdout date is enforced twice: the
pipeline refuses data on or after it before Stage 3, and the data fetcher drops
it before writing, so it is never on disk to be read by mistake.

**Costs are stated, not assumed.** Slippage, commission, borrow on short gross
and margin interest on the debit all accrue on a 360-day basis over calendar
days, and slippage and borrow are swept. A rate the positions need but the caller
left blank raises instead of defaulting to zero, because a silent zero is the one
assumption that always flatters. Event contracts use the exchange's fee formula
priced by the multiplier in force on the day.

**Significance and deflation.** The t-statistic is on active return over a
required, size-appropriate benchmark, with Newey-West errors. Results fall in
bands (|t| of 3 or more strong, 2 promising, 1.5 underpowered, below that drop),
and the Sharpe ratio is deflated by the number of trials, per strategy family and
across the whole lab, with the dispersion measured from the results database.
Fewer than two trials reports "not deflated" instead of assuming a variance.

**Provenance.** Every run records the lab's commit, the shared library's commit,
the state of the archive it read and its full configuration. A reported figure
traces back to the run that produced it.

**Mutation testing.** Every guard is deliberately broken to confirm a test fails.
A test that passes against broken code is worse than none, because it reads as
protection.

## Architecture

```
lab/
  data/        read-only archive access, point-in-time universe, Kalshi history fetch
  engine/      backtest, costs, sizing, statistics, registry, pipeline, report,
               event-contract fees, book-returns series
  results/     runs, trials and figures, behind a backend seam for the move to Postgres
  strategies/  one module per registered strategy: its signal and sizing
  recorders/   the forward Kalshi recorder
  checks/      property tests on the archive itself
registry/      one file per strategy, and the template
book/          the shape of the holdings file the correlation series reads
ops/           installer for the recorder's scheduled jobs
scripts/       the Stage 1 runners, one per strategy
docs/          the audit trail: account constraints, archive survey, defects,
               reviews, the catalogue and its ranking
tests/         283 tests
```

The shared data layer, `market_core`, is a separate private package used by this
and a sibling project. It holds the vendor client with its archival write
guards, the performance statistics and the alignment and vintage checks, because
the same helper was written twice and drifted. Two versions of a guard is worse
than one.

## Stack

Python 3.13 · NumPy · pandas · SciPy · statsmodels · PyArrow · SQLite

Versions are pinned in `requirements.txt`. An unannounced upgrade once changed a
library's return type and cost a run.

## Running it

The lab cannot be run from a bare clone. It reads a licensed market-data archive
(Sharadar, held locally as SQLite) and depends on `market_core`, which is not
published.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e "$HOME/market-data/market-core"

.venv/bin/python -m pytest                             # 283 tests
cp book/holdings.example.toml book/holdings.toml       # then fill in real holdings
.venv/bin/python -m lab.recorders.kalshi status        # forward recorder health
```

Holdings are gitignored; only the example is committed. Kalshi data comes from
the exchange's public API and needs no credentials.

## Where to start reading

- `QUEUE.md`: what happens next and why it is in that order
- `registry/`: the two registered strategies, prediction and kill criteria included
- `docs/reviews/cost-model-2026-09-23.md`: how the cost model was broken and fixed
- `docs/kalshi-survey.md`: what the exchange's API serves, and the fee check
- `docs/account.md`: the account constraints every report must name
- `docs/catalogue/summary.md`: the 41 candidates and how they were ranked
- `CHANGELOG.md`: what has changed, newest first

## Scope

This is a personal research project. It is not investment advice, it makes no
claim to profitability, and until a strategy survives its own kill criteria on
data it has not seen, it claims nothing at all.
