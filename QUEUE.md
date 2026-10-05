# Queue

The single source of truth for what happens next. Read this first, before
anything else, and reconcile it against the files before acting on memory.
It is updated by the action that changes it, not afterward.

Last reconciled against disk: 2026-09-23.

---

## 1. Blocked on outside action

- **Schwab Trader API key.** Blocks: every options entry, and the only route to
  options history at retail depth. Unblocks `vrp-short-vol` and the four to five
  options candidates the catalogue says are missing. Not yet needed — raise it
  again when options work is next in the queue. Verify on arrival whether the
  advertised ~15 years of equity and options history is actually served, and
  note that Schwab carries no FX and no crypto, and futures quote-only with no
  historical bars.
- **Futures data purchase, roughly $400-900/year (Norgate or CSI).** Blocks
  `futures-carry-carver10`, `futures-trend-ewmac`, and the five to eight further
  Carver strategies. The catalogue's own recommendation is that this is the
  single largest unlock per dollar, and the one least correlated with an
  all-equity book. No action taken; recorded as a decision, not a request.
- **Chan's MATLAB example code from epchan.com/book2.** Blocks nothing outright,
  but three candidates reproduce his rules from printed fragments whose utility
  functions (`smartMovingStd`, `backshift`, `smartsum`) are not shown. Retrieval
  needs a person because the download is gated behind a registration step.
- **Confirm the pattern-day-trader threshold with the broker before the margin
  move settles.** The rules have changed before and my reading of them has a
  date on it. At about $20k the account sits below the $25,000 line as I understand
  it, which caps day trades at three per five rolling business days. This does
  not block the daily-rebalance family, because a position held overnight is not
  a day trade, but it does block anything intraday. Verify against the broker's
  own statement of the rule rather than against `docs/account.md`.

- **Polymarket accessibility.** A legal question I cannot answer. Gates the
  cross-venue event-contract entry. Does not gate the Kalshi recorder.

## 2. Next, in order

Ranked by information gained per day of work, not by claimed return.

1. **Build the evaluation rules into the engine.** The rules adopted on
   2026-10-03 (shared `METHODOLOGY.md`, "Evaluation stages"; reasoning and
   findings in `docs/reviews/stage-rules-2026-10-02.md`) are not enforced by
   any code, so no strategy can be judged under them yet. This item also
   absorbs the two defects the first Stage 1 run exposed, which turned out to
   be symptoms of the same gap. Routine builds, in this order:
   - **The decision cell as registered fields.** The registration names the
     one sizing rule, execution convention and cost cell the verdict reads,
     and the pipeline computes the headline, the current-regime slice and the
     Sharpe stored for deflation there. Today the kill rule is read at 5bp and
     1% borrow while those figures are computed at 25bp and 8%.
   - **The score and the holdout rules.** Net-of-cost Sharpe of the active
     return over training and holdout pooled, tiers at 1.0 and 1.5, the
     out-of-sample score withheld until the holdout holds a year, and every
     look at the holdout recorded in the database and counted.
   - **Gates and flags separated.** `stats.band()` stops returning a verdict
     phrase, the minimum track record is always computed, and CAGR leaves the
     report body.
   - **Refuse a benchmark that does not cover the sample.** `stats.summarise`
     inner-joins the strategy with its benchmark and drops the rest silently.
     `xs-mr-khandani-lo` registered BIL, which starts 2007-05-30, so nine of
     its 26 years vanished from every figure and the report said only
     "n=4364". Print the evaluated window in every report and refuse, or
     require a written acknowledgement, when the benchmark starts materially
     later than the returns. Pre-2007 has no Treasury-bill ETF in
     `fundprices`.
   - **Break-even at every swept borrow rate**, not only 8%, where a short
     book is already negative at the cheapest cost.
   - **The random-thinning control.** The shared method requires one on every
     filter and nothing implements it. Build it or take it out of the shared
     method; either way, decide.
   Decided 2026-10-05 (shared `METHODOLOGY.md`): new equity registrations
   use a holdout from 2025-10-01, moving each 1 October; a measured Sharpe is
   halved before sizing; published effect sizes are halved; a name is
   tradeable at no more than 1% of its average daily dollar volume; at most
   two variants per strategy.
2. **`crypto-perp-funding-carry` — spot-perpetual basis.** A perpetual future
   is a contract with no expiry that stays near the spot price because one side
   pays the other a periodic funding rate. Holding spot and shorting the
   perpetual removes price risk and collects that payment when longs are paying.
   The catalogue ranks it third overall, and its test data is free: funding
   history from large offshore exchanges (Binance, Bybit, OKX), whether or not
   a perpetual is tradeable from this account. It needs two builds first: a
   fetcher for that public history, and a funding-payment term in the cost
   model, which today has slippage, commission, borrow and margin interest only.
   The venue question was wrong in `docs/account.md` and is corrected there:
   Kalshi lists perpetuals. Still to check with Kalshi and the broker: whether
   this account can trade them, how their funding is set, and what history
   exists.
3. **Build the Compustat-to-Sharadar field map for the 23 OSAP entries.** The
   catalogue's claim that 29 entries are testable today rests on an unverified
   assumption that this archive carries the accounting fields the OSAP
   definitions name. Until the map exists, that count means nothing.
   Next concrete action: extract the field list from `SignalDoc.csv` and diff it
   against the 112 columns of `fundamentals`.
   Routine work, gates the next item and any OSAP entry.

4. **Value-weighting versus equal-weighting across three OSAP entries.** A
   methodology test rather than a strategy, and the highest-value single day in
   the catalogue: it plausibly eliminates half the equity set.
   Depends on the field map above.

## Tabled

- **Kalshi longshot-bias evaluator (`event-narrative-fade`), tabled
  2026-09-24.** Registered and the data path is half built, but the events
  account can only use the settled cash it shares with the equity
  account, under a tenth of the book, so even a real edge is worth tens of dollars a year. Resume if the
  equity work leaves room for a second asset class. To resume: finish the
  history fetch (recorder off while it runs), then build the per-event
  evaluator, with `close_time`, `settlement_ts` and `result` kept out of the
  entry step by construction. Read the remaining pages of the
  fee schedule's per-series list first. The recorder stays on.

## 3. In flight

- **The lab's spine.** Started 2026-09-23. Done and tested: the data-access
  layer (`lab/data/archive.py`), the point-in-time universe builder
  (`lab/data/universe.py`), the archive property tests
  (`lab/checks/archive_properties.py`), configuration, and the pinned
  environment at `~/.venvs/strategy-lab`. 40 tests pass, each guard checked by
  breaking what it covers.
  Also done: the results database (`lab/results/db.py`) — runs, trials and
  figures tables, backend split for the eventual Postgres move, and a test that
  a recorded figure is re-found from its run id. 61 tests pass lab-wide.
  Also done: the registry (`registry/TEMPLATE.md`, `lab/engine/registry.py`) and
  the engine (`backtest`, `costs`, `sizing`, `stats`, `pipeline`, `report`).
  135 tests pass lab-wide.
  Also done: the book-returns series, the independent cost-model review, the
  Kalshi recorder, and the registration of `event-narrative-fade`. 192 tests
  pass lab-wide.
  Still missing before a first verdict: the per-event evaluator and the
  standing summary of what is currently believed.

- **Kalshi history fetch, paused 2026-09-24.** 3,716 of 10,461 series done
  (202,190 markets, 16.1 million hourly candles, 128 MB) in about 11.7 hours.
  Stopped deliberately: it shares an address with the recorder, and from
  03:00 UTC on 2026-09-24 it starved the recorder, which lost about 112 of
  196 quote polls to HTTP 429. The recorder holds the perishable data; the
  history does not go away. Resume with
  `python -m lab.data.kalshi_history event-narrative-fade`, and only after
  giving the recorder priority (a shared limit, or run the fetch when the
  recorder is off). Remaining: about 6,700 series, roughly another 20 hours
  at the observed rate, uneven because the large sports series are still to
  come. Whether to finish it is undecided; see the evaluator question in
  section 2, item 1.

## 4. Finished, recorded

- **`xs-mr-khandani-lo` killed at Stage 1, 2026-09-30.** Kill cell (linear,
  next-open, 5bp per side, 1% borrow) active t = −5.52; the threshold was
  1.5. Before costs the edge is real, +7.15% a year over 1998–2024 (t 3.6),
  mostly before 2009, but it trades 1.45 times equity a day and pays for only
  about 1.8bp per side. What it settles for the rest of the catalogue: a book
  turned over daily on S&P 500 names needs all-in costs under about 2bp per
  side. One prediction failed: trading at the same close earned less than the
  next open, not more. Full record, run ids and the benchmark truncation in
  `registry/xs-mr-khandani-lo.md`. The runner is
  `scripts/run_xs_mr_khandani_lo_stage1.py`; the build behind it is
  `lab.strategies.xs_mr_khandani_lo`.

- **`prices.permaticker` repair confirmed, 2026-09-27.** Zero nulls on every month from 2026-01 onward, backfill and recurring write both addressed. `docs/defects/permaticker-gap.md` has the incident; `lab.checks.archive_properties.stable_identity` passes again.

- **Kalshi recorder running, 2026-09-23.** Quotes every 5 minutes, depth for
  the 300 most liquid markets every 15, settlements and metadata alongside,
  all logged to `runs.jsonl`. Design, storage estimate and how to stop it are
  in `docs/kalshi-survey.md`. 18 tests, 16 of 16 mutations caught. Check the
  daily storage after 24 hours; the projection is 100 to 150 MB a day.
  The survey also found the catalogue's premise partly wrong: settled prices
  and outcomes are served, and only order book depth is perishable.
- **Cost model reviewed and broken, 2026-09-23.** Record in
  `docs/reviews/cost-model-2026-09-23.md`. Checked against an independent
  dollar-and-cash simulation: exact at zero cost, within 1% of the cost
  charged otherwise. Four defects found and fixed. The worst: every weight
  row was treated as a daily rebalance, so a strategy with monthly rows was
  charged about 1.5% a year of trading it would never do. Rows are now
  rebalances with positions drifting between them. Also fixed: float sums of
  1 + 1e-16 read as leverage, a book could lose more than its equity and
  continue, and an infinite return passed through. The engine is now clear
  for a first Stage 1 report.
- **Book-returns series, 2026-09-23.** `lab/engine/book.py` reads
  `book/holdings.toml` (market values from the broker, dated) and builds a
  constant-weight daily series from `closeadj`. Real archive: 11 holdings,
  2018-01-31 to 2026-09-22, 23.5% annualised volatility, correlation 0.90 to
  SPY. It starts when the newest listing (TMFC) does, raises on any later gap
  rather than filling it, and warns in the report past 30 days of holdings age.
  Today's holdings are applied to the past, which is hindsight by design.
  `holdings.toml` must be refreshed from the broker when the book moves.
  15 tests, 14 of 14 mutations caught.
- **Archive spans verified against the live database, 2026-09-23.** All eleven
  tables checked directly rather than trusted from my planning notes. Findings and the
  three corrections to the planning table are in `docs/archive-survey.md`.
- **Account read from the live broker, 2026-09-23.** Five accounts, not two.
  Figures and what they imply for tradeability are in `docs/account.md`.
- **Archive property tests written and run, 2026-09-23.** Six of seven pass.
  Watermarks intact on all eleven tables at 2025-08-11. Bars fresh to
  2026-09-22. Zero OHLC arithmetic violations across 46,476,349 bars. The
  volume storage floor measured at 6.03%, matching the figure recorded in the
  shared methodology exactly. 62.1% of the names trading on 2010-06-30 have
  since delisted and are still present, so the archive supports a
  survivorship-complete universe. The seventh check fails on the permaticker
  gap above, which is a real defect rather than a test fault.
- **Strategy catalogue retrieved, 2026-09-23.** 41 candidates with entry rules,
  exit rules, parameter counts and verdicts, plus the companion notes on what is
  unretrievable. Saved to `docs/catalogue/`.
- **Results database built, 2026-09-23.** `lab/results/db.py`: `runs` carries
  strategy, stage, the lab's and `market_core`'s commit, the archive watermark
  at run time, full configuration as JSON, who produced the run and at what effort; `trials`
  is the lab-wide and per-family counter `deflated_sharpe` needs; `figures`
  ties every reported number to the run that produced it. A run_id is minted
  only by `record_run`; every other write is refused against an unregistered
  one. 21 tests, 7 mutations of the guards that matter, all caught.
- **The discretionary sleeve register built and linked, 2026-09-23.** Shared at
  `~/quant/decisions/`, outside this checkout — three re-entry positions
  already open. `sleeve.py` enforces the cap: risk at 5% of net liquidation
  value, capital deliberately uncapped pending the move to margin. Recorded
  here because `docs/account.md` and this queue both depend on its numbers.
- **Registry and backtest engine built, 2026-09-23.** A strategy is one file in
  `registry/`; `require_registered` refuses to run one whose fenced block is
  incomplete, over five parameters, under two sizing rules, or data-derived
  without its burden stated. `evaluate` in `lab/engine/pipeline.py` is the only
  path to a report: it checks the sizing rules and benchmark match what was
  registered, refuses any data on or after the holdout date before Stage 3,
  demands a stated binding constraint, sweeps slippage 0.10/0.25/0.50% and
  borrow 1%/8%, records every run, trial and figure in the results database,
  and deflates per family and lab-wide from what was recorded. Decisions are
  applied to the following day's returns by the engine, never by the strategy;
  `lag < 1` raises. A held name with no return raises rather than being zeroed.
  Statistics are `market_core`'s, not reimplemented; `time_under_water` was
  added there. 32 mutations of the guards across the engine and results
  database, all caught.
