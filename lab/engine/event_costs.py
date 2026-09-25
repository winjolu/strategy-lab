"""Kalshi's taker fee, and which multiplier applied to a series on a date.

The formula is from the exchange's published fee schedule (July 2026
edition), and its general trading fees table is the oracle the tests use:

    fee = ceil_to_cent(0.07 x M x C x P x (1 - P))

`P` is the contract price in dollars, `C` the contracts in one order, `M`
the series multiplier (1 unless the schedule says otherwise, and 0 for
series that charge nothing). The rounding is per order, up to the whole
cent: the table shows one contract at 10 cents costing $0.01 where the
formula gives $0.0063, and 100 contracts at 5 cents costing $0.34 where it
gives $0.3325. There is no settlement fee.

Arithmetic is exact. In floating point 0.07 x 100 x 0.10 x 0.90 comes out a
hair above 0.63 and rounds up to 0.64, a cent that the published table does
not charge.

A series' multiplier changes over time and the series listing states only
the current one. `/series/fee_changes` gives dated changes back to
2025-10-04. Before a series' first recorded change the default of 1 is
assumed, which is the schedule's stated default and errs towards charging
more. That assumption is wrong for a series that was zero-fee from listing
and had a later change recorded; the direction of the error is a higher fee
than was paid.
"""
from decimal import ROUND_CEILING, Decimal

RATE = Decimal("0.07")
DEFAULT_MULTIPLIER = 1.0


def taker_fee(price, contracts, multiplier=DEFAULT_MULTIPLIER):
    """Dollars charged for one taker order. `price` is dollars, given as a
    string or Decimal so it is not re-rounded by binary floating point."""
    p = Decimal(str(price))
    if not Decimal(0) < p < Decimal(1):
        raise ValueError(f"price must be strictly between 0 and 1 dollars, got {price}")
    if contracts < 1 or int(contracts) != contracts:
        raise ValueError("an order is a whole number of contracts, at least 1")
    raw = RATE * Decimal(str(multiplier)) * int(contracts) * p * (1 - p)
    return float((raw * 100).to_integral_value(rounding=ROUND_CEILING) / 100)


class FeeSchedule:
    """Multiplier in force for a series at a moment.

    `changes` is rows of (series_ticker, scheduled_ts ISO string,
    fee_multiplier); `current` maps series ticker to the multiplier the
    listing states today, used only to check that the timeline ends where
    the listing says it does.
    """

    def __init__(self, changes, current=None):
        self._by_series = {}
        for series, when, multiplier in changes:
            self._by_series.setdefault(series, []).append((when, float(multiplier)))
        for rows in self._by_series.values():
            rows.sort()
        self.current = dict(current or {})

    def multiplier(self, series, when_iso):
        """`when_iso` in the same ISO 8601 UTC format the API uses. A change
        applies from its scheduled time inclusive."""
        applied = DEFAULT_MULTIPLIER
        for when, multiplier in self._by_series.get(series, []):
            if when <= when_iso:
                applied = multiplier
            else:
                break
        return applied

    def disagreements(self):
        """Series whose latest recorded change differs from the current
        listing: the timeline and the listing cannot both be right."""
        out = {}
        for series, rows in self._by_series.items():
            if series in self.current and rows[-1][1] != float(self.current[series]):
                out[series] = (rows[-1][1], float(self.current[series]))
        return out
