# Changelog

What has actually changed in this project, newest first.

There are no version numbers or releases yet. This is a single-user tool that I
run rather than ship, so entries are grouped by date instead, and I'll add
versioning if that ever stops being true.

This file is deliberately backward-looking. What comes next lives in
[QUEUE.md](QUEUE.md) and what cannot be tested lives in
[docs/data-gaps.md](docs/data-gaps.md). Keeping them apart means this file can't
go stale: what happened stays true, whereas a list of intentions needs pruning to
stay honest.

## [Unreleased]

Nothing yet.

## 2026-10-05

### Added
- Rule set v2 is enforced by code. A registration under it names its sizing
  rule, execution convention, slippage and borrow, and the pipeline computes
  every headline figure, the current-regime slice and the Sharpe stored for
  deflation at that cell, refusing a cell the sweep did not compute. The
  score is the annualised active Sharpe, net of cost, over the three-year
  training window and the holdout pooled, with tiers at 1.0 and 1.5. The
  holdout's half is withheld until it holds a year, read once per strategy
  under the registered execution convention, and every read is recorded in
  the results database under a uniqueness constraint and counted in the report.
- A random-thinning control (`lab/engine/controls.py`): where a filter's
  result falls among random masks that keep the same number of names on every
  date.
- The report prints the window actually evaluated, and break-even slippage at
  every swept borrow rate.

### Changed
- Band labels describe a t-statistic's size and decide nothing; the label
  that read "record and drop" is now "weak". The minimum track record is
  computed and printed for every run, not only one band. CAGR is out of the
  report body in favour of Sharpe.

### Fixed
- A benchmark that starts late no longer shortens the evaluated sample
  silently. The pipeline refuses one with no observation on more than two
  percent of the return dates, unless the registration carries a written
  acknowledgement. The first Stage 1 run lost nine of twenty-six years this way.
- A constant return record has an undefined score instead of a float-noise one.

## 2026-10-03

### Added
- A review of the lab's evaluation rules, `docs/reviews/stage-rules-2026-10-02.md`.
  It found nine places where the rules disagreed with each other or with the
  code, the worst being that the kill verdict was read at 5bp and 1% borrow
  while the report's headline, its current-regime slice and the Sharpe stored
  for deflation were computed at 25bp and 8%. It also measured what a
  two-window gate costs: requiring two short windows to pass separately
  rejects a strategy with a true Sharpe of 1.5 three times in four. The
  general rules it settled on now live in the shared method file under
  "Evaluation stages"; the review keeps the findings, the arithmetic and the
  list of code changes, none of which is built yet.

## 2026-09-30

### Added
- The first Stage 1 result. `xs-mr-khandani-lo`, cross-sectional mean
  reversion on the S&P 500, is killed. Before costs the edge is real: +7.15%
  a year over 1998–2024 (t 3.6), most of it before 2009. But the book trades
  1.45 times its equity a day, and that return pays for only about 1.8 basis
  points of cost per side. At the registered kill cell (5bp per side, 1%
  borrow) the t-statistic on active return is −5.52 against a threshold of
  +1.5. The result settles a question for the whole catalogue: a book turned
  over daily on the most liquid US stocks needs all-in costs under about 2bp
  per side to survive.
- One prediction failed. Trading at the same close, the published
  convention, was expected to earn clearly more than trading at the next
  open, the difference being bid-ask bounce. It earned less: 4.90% against
  7.15% a year before costs.

### Fixed
- The runner passed the holdout date itself as the end of the fetch window,
  which the archive reads inclusively, so the close-to-close series ended on
  the first holdout day. The pipeline's holdout guard refused to run, which
  is what it is for. The window now ends on the last trading day strictly
  before the holdout, taken from the archive's calendar. The docstrings that
  claimed the open-to-open construction made this impossible whatever date
  was passed were wrong and are corrected: dropping the last row guards
  against reading past the fetch, not against fetching too far.

### Known
- The registered benchmark silently truncated the sample. BIL begins trading
  2007-05-30, and the statistics keep only dates both series share, so every
  registered figure covers 2007–2024, not 1998–2024. The report showed it
  only as a day count. A full-sample diagnostic confirmed the verdict does
  not depend on the missing years. Making the pipeline refuse, or at least
  print, a window shorter than the returns supplied is queued.
- The report's break-even line is read at 8% borrow, where a short book is
  already negative at the cheapest cost, so it said nothing. At 1% it is
  about 1.3bp. Queued.

## 2026-09-27

### Added
- Everything `xs-mr-khandani-lo` needed to run: point-in-time S&P 500
  membership reconstructed from the index's event history and checked
  against every real quarterly snapshot; two return conventions,
  close-to-close and next-open; a per-strategy cost sweep that leaves every
  other strategy's default alone; the signal and its two sizing rules; and a
  break-even cost figure in every report.

### Fixed
- The `permaticker` gap in the archive is repaired: zero nulls on every
  month from January onward, confirmed against the archive directly.

## 2026-09-24

### Added
- The registration of `xs-mr-khandani-lo`, cross-sectional mean reversion. It
  departs from the published version in two ways, both argued before any run. It
  trades at the next open instead of the same close, because signalling and
  trading on one close credits a reversal strategy with bid-ask bounce it could
  not have captured; the same-close version still runs beside it, labelled as an
  upper bound, so the gap measures the bounce. And it sweeps costs from 1 to 25
  basis points a side, because at about twice its size traded every day the lab's
  standard 0.10% floor would decide the answer before the test ran. The
  prediction, written first, is that it earns money before costs, mostly before
  2009, and fails at 5 basis points.
- `book/holdings.example.toml`, the shape of the file the book-returns series
  reads. The real file is gitignored, and a missing one raises rather than
  falling back to the example, because a correlation to a made-up book would look
  real.

### Changed
- The Kalshi history fetch is paused. After it was restarted it shared an address
  with the recorder, and from 03:00 UTC the recorder lost about 112 of 196 quote
  polls to HTTP 429. The recorder holds the data that cannot be recovered and the
  history can be fetched any day, so the history waits. It was 3,716 of 10,461
  series in, and resumes from the manifest.
- The Kalshi longshot-bias evaluator is tabled. The events account can only use
  the settled cash it shares with the equity account, under a tenth of the book,
  so even a real edge is worth tens of dollars a year. The recorder stays on.
- The queue is ordered by dependency: mean reversion first because everything it
  needs exists, then the perpetual funding carry, then the OSAP field map, then
  the value-weighting test that depends on it.
- Run records now say who produced a run and at what effort (`produced_by`,
  `effort`), and the strategy provenance label `operator` became
  `own_observation`.
- Personal balances, positions and the detailed account notes moved out of
  tracked files. `docs/account.md` keeps every constraint and drops the figures.

### Fixed
- The perpetual futures venue was recorded as offshore-only. Kalshi lists 25
  perpetual series. Whether this account can trade them, how their funding is
  set and whether any history exists are still unchecked; the strategy's test
  data, public funding history from large offshore exchanges, never depended on
  the venue.

## 2026-09-23

### Added
- The project skeleton, and measurements of the archive against my planning
  table. All eleven tables checked directly; three spans were narrower than
  assumed, and one of them changes what is testable (corporate events start in
  1993, years before prices, so prices are the binding constraint).
- Property tests on the archive itself. Six of seven pass: zero OHLC arithmetic
  violations across 46,476,349 bars, the volume storage floor at 6.03% of bars,
  and 62.1% of the names trading on 2010-06-30 since delisted and still present,
  so the archive supports a survivorship-complete universe. The seventh fails on
  the missing `permaticker` deliberately.
- The data layer: archive access that is read-only by construction, behind a
  backend seam so the move to Postgres changes one file.
- A point-in-time universe built from bar presence rather than the security
  master, whose `lastpricedate` is not refreshed daily and would have returned an
  empty universe for the most recent seven weeks.
- The results database: runs, trials and figures. A run id is minted only by
  recording a run, every other write is refused against an unregistered one, and
  the trial counter is what deflation needs.
- The registry and the backtest engine. Registration is enforced by the pipeline
  rather than by habit; decisions are shifted by the engine so a strategy cannot
  read the return it is paid; the holdout is refused before Stage 3; costs are
  swept; the t-statistic is on active return over a required benchmark; the
  Sharpe ratio is deflated per family and lab-wide.
- A daily return series for the current book, so every report can carry its
  correlation to what is already held. It starts when the newest listing does,
  raises on any later gap instead of filling it, and warns past 30 days of
  holdings age. Applying today's holdings to the past is hindsight by design.
- The forward Kalshi recorder: best quotes with sizes for about 128,700 open
  markets every five minutes, storing only rows that changed, plus full depth for
  the 300 most liquid markets every fifteen. A failed page aborts the poll rather
  than writing a partial listing, and every attempt is logged so a sleeping
  laptop shows as a gap rather than a quiet market.
- A fetcher for Kalshi's settled history, cut at a registration's holdout before
  anything is written, resumable by series, with a shared rate limit.
- Kalshi's taker fee as a function, tested against every row of the exchange's
  published fee table, and a timeline of each series' multiplier from the
  exchange's change history.
- The registration of `event-narrative-fade`, an unconditional test of the
  favourite-longshot bias. Entry reads only a candle at 14:00 UTC, since the
  realised close time is an outcome for markets that close early.

### Changed
- The catalogue's statement that settled Kalshi markets are purged. They are
  served back to 2023; only order book depth is perishable. This moved the
  urgency from the longshot test to the depth recorder.

### Fixed
- The cost model treated every row of weights as a daily rebalance. A portfolio
  decided once and never changed paid about 1.5% a year in phantom cost, and a
  strategy with monthly rows was charged for trading it would never do. Each row
  is now a rebalance and positions drift between rows. Found by writing a second
  implementation that tracks dollars and cash; the existing suite could not have
  caught it, because every test supplied a row per day. Three more came out of
  the same review: weights summing to 1 plus a rounding error were read as
  leverage and demanded a margin rate, a levered book could lose more than its
  equity and keep compounding, and an infinite return passed through to the net
  series.
- The history fetch died after 93 series on an unthrottled rate limit and then
  sat idle for hours because nothing was watching it. Calls are now capped across
  threads, a 429 waits at least as long as the server's `Retry-After`, and the
  exit is watched.

## 2026-09-21

### Added
- A catalogue of 41 candidate strategies with complete entry, exit and sizing
  rules, parameter counts and data requirements, ranked by information gained per
  day of work rather than by claimed return. A few tests decide many entries at
  once and go first: whether any high-turnover equity strategy survives realistic
  costs, and whether most published factor anomalies survive value-weighting.
