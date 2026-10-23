"""Whether the archive's opening prices agree with a second source.

A strategy that trades at the open is paid on a price most daily-bar studies
never use, and an archive's open is the field least checked by anyone. This
compares a random sample of dates per ticker against an independent source and
says whether the disagreement exceeds a stated limit.

Two rules matter more than the arithmetic:

* **A disagreeing date is never dropped.** Filtering to the dates that agree
  would keep the clean half of a broken field and report it as checked.
* **A date the second source cannot price counts against the check**, and is
  reported separately, so a thin second source cannot pass the archive by
  saying nothing.

Both frames are long: `ticker`, `date`, `open`, on the same split basis.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

SAMPLE_PER_TICKER = 250
TOLERANCE = 0.001        # 0.1%
MAX_BAD_SHARE = 0.01     # void if more than 1% of sampled dates disagree


@dataclass
class TickerCheck:
    ticker: str
    sampled: int
    disagree: int
    unpriced: int
    worst: float

    @property
    def bad_share(self):
        return (self.disagree + self.unpriced) / self.sampled if self.sampled else 1.0

    @property
    def passed(self):
        return self.sampled > 0 and self.bad_share <= MAX_BAD_SHARE


def sample_dates(archive_opens, ticker, start, end, n=SAMPLE_PER_TICKER, seed=0):
    """`n` distinct dates, drawn without replacement and reproducibly, from
    the archive's own dates for `ticker` between `start` and `end`."""
    d = archive_opens.loc[archive_opens["ticker"] == ticker, "date"]
    d = pd.DatetimeIndex(d[(d >= pd.Timestamp(start)) & (d <= pd.Timestamp(end))]).unique().sort_values()
    if len(d) < n:
        raise ValueError(f"{ticker} has only {len(d)} archive dates in the window; the check needs {n}")
    rng = np.random.default_rng(seed)
    return pd.DatetimeIndex(sorted(rng.choice(d.values, size=n, replace=False)))


def compare(archive_opens, second_opens, ticker, dates):
    a = archive_opens[archive_opens["ticker"] == ticker].set_index("date")["open"]
    b = second_opens[second_opens["ticker"] == ticker].set_index("date")["open"]
    if a.index.has_duplicates or b.index.has_duplicates:
        raise ValueError(f"more than one open per date for {ticker}")
    a, b = a.reindex(dates), b.reindex(dates)
    if a.isna().any():
        raise ValueError(f"{ticker}: sampled dates missing from the archive itself")
    unpriced = int(b.isna().sum())
    gap = (a / b - 1.0).abs()
    disagree = int((gap > TOLERANCE).sum())
    worst = float(gap.max()) if gap.notna().any() else float("nan")
    return TickerCheck(ticker, len(dates), disagree, unpriced, worst)


def run(archive_opens, second_opens, tickers, start, end, n=SAMPLE_PER_TICKER, seed=0):
    """One `TickerCheck` per ticker. The check passes only if every ticker does."""
    return [compare(archive_opens, second_opens, t,
                    sample_dates(archive_opens, t, start, end, n, seed)) for t in tickers]


def render(results):
    lines = ["Opening-price check against a second source "
             f"(void if more than {MAX_BAD_SHARE:.0%} of dates differ by more than {TOLERANCE:.1%}):"]
    for r in results:
        lines.append(f"  {r.ticker}: {r.sampled} dates, {r.disagree} disagree, {r.unpriced} unpriced, "
                     f"worst {r.worst:.4%}, {'pass' if r.passed else 'FAIL'}")
    return "\n".join(lines)
