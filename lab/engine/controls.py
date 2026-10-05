"""The random-thinning control every filter needs.

A filter removes names. Whether it helps depends on what removing the same
number of names at random would have done, because removing names changes
concentration, turnover and cost on its own. The shared method records the
incident: removing 30% of names at random cost 1.5 points a year, while
removing the same share through an entry band gained 2.7, and without the
control the two are indistinguishable.

`random_thinning` takes the eligible cells before the filter, the cells the
filter kept, and a function that turns a keep-mask into one number. It
evaluates the filter, then evaluates `draws` random masks that keep the same
number of names on every date, and reports where the filter fell among
them. It decides nothing; the percentile is a flag.
"""
import numpy as np
import pandas as pd

MIN_DRAWS = 20


def _random_mask(eligible, counts, rng):
    n, m = eligible.shape
    scores = rng.random((n, m))
    scores[~eligible] = -1.0
    order = np.argsort(-scores, axis=1)
    rank = np.empty_like(order)
    rank[np.arange(n)[:, None], order] = np.arange(m)
    return (rank < counts[:, None]) & eligible


def random_thinning(eligible, kept, metric, draws=200, seed=0):
    """Where `metric(kept)` falls among `metric` of random masks of the same size.

    `eligible` and `kept` are boolean frames of the same shape, dates by
    names, with `kept` inside `eligible`. Every random mask keeps, on every
    date, the same number of eligible names as `kept` does. The percentile is
    the share of random draws scoring at or below the filter: a high one
    means the filter beat what thinning alone does. The result also says when
    every draw scored identically, which means the metric cannot see the
    difference and the control has measured nothing.
    """
    if draws < MIN_DRAWS:
        raise ValueError(f"at least {MIN_DRAWS} draws; {draws} cannot place a result")
    if eligible.shape != kept.shape or not (
            eligible.index.equals(kept.index) and eligible.columns.equals(kept.columns)):
        raise ValueError("eligible and kept must share the same dates and names")
    el, kp = eligible.to_numpy(bool), kept.to_numpy(bool)
    if (kp & ~el).any():
        raise ValueError("the filter kept names that were not eligible")
    counts = kp.sum(axis=1)
    if (counts == el.sum(axis=1)).all():
        raise ValueError("the filter removes nothing, so there is nothing to control for")

    rng = np.random.default_rng(seed)
    real = float(metric(kept))
    random_scores = np.array([
        float(metric(pd.DataFrame(_random_mask(el, counts, rng), eligible.index, eligible.columns)))
        for _ in range(draws)
    ])
    finite = random_scores[np.isfinite(random_scores)]
    return {
        "filtered": real,
        "random_mean": float(finite.mean()) if len(finite) else float("nan"),
        "random_sd": float(finite.std(ddof=1)) if len(finite) > 1 else float("nan"),
        "percentile": float((finite <= real).mean()) if len(finite) else float("nan"),
        "draws": int(len(finite)),
        "degenerate": bool(len(finite) and finite.max() == finite.min()),
        "share_removed": float(1.0 - kp.sum() / el.sum()),
    }
