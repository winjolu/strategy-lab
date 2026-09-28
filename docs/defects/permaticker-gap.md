# The incremental refresh stopped writing `permaticker`

**Repaired.** Found 2026-09-23, confirmed fixed 2026-09-27: every month from
2026-01 onward now carries zero null `permaticker` values, bars written after
the fix included, so both the backfill and the recurring write described
below were addressed. `lab.checks.archive_properties.stable_identity` passes
again. Left as written at the time, since the diagnosis is still the record
of what happened.

Found 2026-09-23, while proving the data-access layer returned sane bars.
Recorded here rather than only in my head because it changes what can be
joined in the window this lab cares most about.

## What is wrong

`prices.permaticker` is NULL on **every equity bar since roughly 2026-08-01**.

| Month | Bars | Null `permaticker` | Share |
|---|---|---|---|
| 2026-01 to 2026-06 | ~766,000 | 0 | 0.0% |
| 2026-07 | 138,807 | 260 | 0.2% |
| 2026-08 | 132,840 | 126,916 | 95.5% |
| 2026-09 | 94,493 | 94,493 | 100.0% |

Archive-wide the null share is only 0.48%, which is why this is easy to miss: a
check on the whole table reports a healthy number. The damage is entirely in the
recent window.

## Why it happened

The vendor's price endpoint does not return `permaticker`. The bulk loader knew
that and joined it in at load time — `build_db.py` carries the comment "tickers,
and the ticker -> permaticker map the price file lacks".

`market_core.sharadar.refresh` builds its INSERT by reading local column names
off the API row:

    payload = [tuple(r.get(c) for c in cols) for r in rows]

`cols` comes from the local table and includes `permaticker`; `r` is the API
row and has no such key. So `r.get("permaticker")` returns `None` and a NULL is
written, silently, once per bar per night. The timing matches the entitlement
change recorded in `data_coverage` — "entitlement reduced to one year 2026-08" —
so the break is the moment the bulk load stopped and the incremental path became
the only writer.

There is already a guard in `refresh` for this exact shape of failure, but only
for the date column: it raises `HistoryGap` when rows come back and none carries
the date, on the reasoning that appending them "would write NULL dates that no
later refresh can see". The reasoning generalises to any local column the API
never supplies. It was not generalised.

## Why it matters here

`permaticker` is the only stable company identity in this archive. A ticker is
rewritten retroactively by the vendor after a rename, so anything keyed on
ticker silently follows the wrong company across one. Every point-in-time
identity join in the current-regime window — which is where the out-of-sample
and paper-trading work happens — has to route around this until it is repaired.

## What this lab does about it in the meantime

- `lab.checks.archive_properties.stable_identity` measures it and **fails**. It
  looks at the last 90 days separately from the archive total, precisely because
  the total hides it. The suite therefore reports FAIL today, which is correct
  and should stay that way until the archive is repaired rather than being
  loosened.
- `lab.data.universe` never uses `permaticker`. Membership is built from bar
  presence and identity is resolved through `tickers` by ticker, which is weaker
  across renames but is available.

## The repair, which I have not run

This needs a write to the archive, and the archive has exactly one writer. It is
`~/market-data/market-archive`'s job, not this lab's, and it is a decision rather
than a chore, so it waits for a person.

Two parts, in order:

1. **Backfill.** `market-archive/loader/repair.py` already does this: it builds a
   ticker-to-permaticker map from `tickers`, falls back to the vendor's
   `permatickers()` lookup for names the map misses, and writes. The affected
   rows are dated 2026-07 onward, well above the 2025-08-11 watermark, so
   `assert_writable("prices", "2026-07-01")` permits it. Nothing archival is at
   risk.
2. **Stop it recurring.** `refresh` should fill `permaticker` from the local
   `tickers` map when the API does not supply it, which is what the bulk loader
   did. It should *not* simply raise when a local column is absent from the API
   response: `permaticker` will never come from that endpoint, so a raise turns
   one silent NULL into a nightly hard failure, and a job that reports a problem
   every night trains its reader to ignore it.
