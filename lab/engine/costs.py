"""What holding and trading a portfolio costs, stated rather than assumed.

`market_core.costs` prices individual trades and is the right tool for an
event study. A daily-weights portfolio has no trades to price, only a
turnover figure, and its costs are of four kinds that behave differently:

* **Slippage** is paid on every dollar traded, at whatever the spread and
  impact cost. It is the swing factor, so it is swept, not fixed.
* **Commission** is a flat rate on traded notional. Kept separate from
  slippage because a broker can change it and the market cannot.
* **Borrow** is paid daily on the short book at an annual rate, on the
  360-day basis brokers use, and accrues over weekends. There is no
  borrow-availability data locally at any price, so every short result is
  an upper bound; the 1% and 8% cases bracket general collateral and hard
  to borrow.
* **Margin interest** is paid on the debit balance, which here is long
  exposure beyond the account's own equity. A levered return with no
  interest charged is not a return.

A rate that applies to the positions taken has to be stated. Borrow left
at `None` on a strategy that shorts raises rather than defaulting to zero,
because a silent zero is the one assumption that always flatters.
"""
import math
from dataclasses import dataclass, replace
from typing import Optional

DAY_COUNT_BASIS = 360.0

#: The sweeps the methodology requires, per side, in percent.
SLIPPAGE_SWEEP = (0.10, 0.25, 0.50)
BORROW_SWEEP = (1.0, 8.0)

#: The cell quoted as the headline. Middle slippage, and borrow at the hard
#: to borrow end when the strategy shorts: with no availability data the
#: honest headline sits at the conservative end of what is plausible.
HEADLINE_SLIPPAGE = 0.25
HEADLINE_BORROW = 8.0


class CostNotStated(ValueError):
    """The positions taken need a cost rate that was left unstated."""


@dataclass(frozen=True)
class CostModel:
    slippage_pct: float                    # per side, on traded notional
    commission_bps: float = 0.0            # on traded notional
    borrow_apr: Optional[float] = None     # percent a year, on short gross
    margin_apr: Optional[float] = None     # percent a year, on the debit

    def with_(self, **changes):
        return replace(self, **changes)


def sweep(base, has_shorts, has_leverage, margin_apr=None, slippage_sweep=None):
    """Every cost model the methodology wants reported for one strategy.

    Borrow varies only when the strategy shorts, and margin interest is
    carried through unchanged when it borrows to lever.

    `slippage_sweep` overrides the lab-wide `SLIPPAGE_SWEEP` for a
    strategy whose standard three points would decide the answer before
    the backtest runs — one trading several times its gross per day,
    where even the cheapest standard cell already consumes most of any
    plausible edge, needs finer resolution to say anything. Every other
    caller is unaffected: the default is exactly the module constant it
    always was, so nothing lab-wide changes because one strategy needed
    this.
    """
    slippage_sweep = slippage_sweep or SLIPPAGE_SWEEP
    borrows = BORROW_SWEEP if has_shorts else (None,)
    out = []
    for slip in slippage_sweep:
        for borrow in borrows:
            out.append(base.with_(
                slippage_pct=slip, borrow_apr=borrow,
                margin_apr=margin_apr if has_leverage else base.margin_apr,
            ))
    return out


def headline(models):
    """The model matching the headline cell, or the closest available."""
    for m in models:
        if m.slippage_pct == HEADLINE_SLIPPAGE and m.borrow_apr in (HEADLINE_BORROW, None):
            return m
    raise LookupError("the sweep has no headline cell")


def cell(models, slippage_pct, borrow_apr=None):
    """The swept model at exactly this slippage and borrow, or raise.

    A registration that names the cell its verdict is read at has to name
    one the sweep actually computed. Falling back to the nearest cell would
    quietly read the verdict somewhere other than where it was registered,
    which is the failure this exists to prevent.
    """
    for m in models:
        if math.isclose(m.slippage_pct, slippage_pct) and (
                m.borrow_apr is None if borrow_apr is None
                else m.borrow_apr is not None and math.isclose(m.borrow_apr, borrow_apr)):
            return m
    have = sorted({(m.slippage_pct, m.borrow_apr) for m in models}, key=str)
    raise LookupError(
        f"the sweep has no cell at slippage {slippage_pct}% and borrow {borrow_apr}; "
        f"it computed {have}"
    )
