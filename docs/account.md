# The account this lab trades for

Read from the broker on 2026-09-23 rather than assumed. This page keeps the
constraints and leaves out balances, positions and identifiers: the real
figures live in a file that is not committed, and every percentage in the lab
is taken against net liquidation value, read when needed, never recalled.

This determines which strategies are viable, and it is established before any
capacity or cost judgment. Every Stage 1 report names the binding constraint
from this page.

## What is there

My planning notes modelled two accounts. There are five: an individual cash account,
an individual margin account, a crypto account (spot only at this broker), an
events account, and a futures account. Only the cash account is funded, at
roughly **$20k** in total.

The events account's buying power is not additional capital. It equals the
cash account's settled cash exactly, because it draws on the same pool, and
two readings taken either side of a purchase confirmed that: it fell by
exactly what the equity purchase consumed. Committing capital to event
contracts removes it from equities, and the reverse.

More than half of the cash was unsettled when I read it, so the limit on a new
purchase that day was under 10% of the book. The T+1 settlement constraint is
not hypothetical.

## The book, and why it dominates every correlation figure

The book is overwhelmingly US large-cap equity beta: broad index funds
(S&P 500, Nasdaq 100, Dow, Russell 2000, Japan) and a handful of single names,
about a fifth of it in a few discretionary positions that sit outside anything
this lab tests. Its growth tilt has risen, not fallen. The genuinely
diversifying holdings are a small-cap index fund and a Japan fund, together
well under a tenth of the equities.

Discretionary positions are recorded in a separate register with their own
entry rules and a cap on the share of the account they may take. They belong in
the correlation series because they are real exposure, and outside the
registry because no backtest supports them.

The consequence, with its reason: a
strategy at Sharpe 0.5 that is uncorrelated with this book is worth more than
one at Sharpe 0.8 that is the index in disguise, because almost anything long
US large-cap equities will correlate above 0.9 with what is already held. Every
Stage 1 report carries the correlation of the strategy's return stream to SPY
**and** to this book. The book series is built from a dated holdings file,
`book/holdings.toml`, which is not committed; `book/holdings.example.toml` shows
its shape.

## The constraints, and which one binds

**Settlement caps turnover today, and is about to stop.** Proceeds settle T+1
in a cash account, and buying with unsettled funds is a good-faith violation;
repeat violations restrict the account to settled cash for 90 days. That
constraint binds the largest number of catalogue entries right now, and
`xs-mr-khandani-lo` at 200% gross turnover per day is the clearest case.

A move to margin is planned, and it removes this. Proceeds are available
immediately, so a daily rebalance stops being blocked by settlement. Any Stage 1
report written before the move names settlement as the binding constraint and
says the move is pending.

**Shorting requires the margin account**, and no borrow-availability data
exists locally at any price. Every short result this lab produces is an upper
bound and says so in the report. Borrow is charged at both 1% general
collateral and 8% hard to borrow, on the 360-day basis brokers use.

**Pattern-day-trader rules replace settlement as the turnover constraint on
margin, and they bind differently.** They bind on *day trades* — opening and
closing the same position within one session — not on turnover as such. A
strategy that rebalances at the close and holds overnight generates no day
trades however high its turnover, so the margin move genuinely unblocks the
daily-rebalance family. What it does not unblock is anything intraday.

The threshold has been $25,000 in account equity, with accounts below it
limited to three day trades per five rolling business days and flagged on the
fourth. The account is below that line, so the limit binds from the moment the
margin account is funded. The rules have changed before and my reading of them
has a date on it: the current threshold and count are verified against the
broker's own rules before anything intraday is sized.

**Taxes.** Short holding periods generate short-term gains taxed as ordinary
income. A strategy winning 2% a year pre-tax at 200% turnover may lose to a
1.5% strategy at annual turnover. Turnover is reported so this is visible. No
tax advice is offered here.

**Margin interest becomes a real cost** the moment leverage is used, and it
belongs in the cost model rather than in a footnote. Reg T allows roughly twice
the account's equity in buying power; a strategy financed that way pays the
broker's debit rate on the borrowed half every day it is held, which falls
hardest on exactly the low-Sharpe, high-turnover designs that leverage is
tempting for. No backtest in this lab reports a levered return without
charging it.

**Capital.** A roughly $20k personal account is not a fund. That helps
capacity-constrained strategies and rules out anything needing institutional
scale. It also means a strategy holding 50 names at equal weight puts about
$400 in each, where a single commission or a wide spread is a material
fraction of the position, and a strategy holding 500 names puts about $40 in
each, where whole-share shorting rounds most of the short side away.

## All five accounts are reachable

Decided 2026-09-23. **Every one of the five accounts counts as reachable**, and
funding is treated as a cost to be stated rather than a gate. Any of them can be
funded on request, so an unfunded balance is not a reason to decline a test and
not a reason to withhold a verdict.

- Shorting, leverage and the pattern-day-trader rules are in scope, so
  dollar-neutral long/short designs are evaluated on their merits rather than
  dismissed. Short results remain upper bounds, because no borrow-availability
  data exists locally at any price — a data limit, not an account one.
- The four event-contract candidates are live candidates. The recorder was the
  first deliverable there, since order book depth is not retained anywhere.
- Crypto spot is in scope at this broker. Perpetual futures were first recorded
  here as needing an offshore venue, which was wrong: Kalshi, a US-regulated
  exchange, lists 25 perpetual series (checked 2026-09-24). Whether this account
  can trade them, how their funding works and whether any history of them is
  served are unchecked. Testing the strategy never needed the venue: its data
  is public funding-rate history from large offshore exchanges.
- The futures account makes the Carver entries tradeable in principle. They stay
  blocked on *data*, which no amount of funding fixes at this broker.

Nothing in the catalogue is excluded from testing for want of a funded account.
A result that kills a family is worth having whether or not it could be traded
tomorrow. What the venue changes is the *label*: Stage 0 records which account a
strategy needs and the concrete enabling step, and the Stage 1
binding-constraint line names it.

The genuinely unavailable cases stay recorded as such: futures and options
history is unentitled, and several data sources are priced institutionally.
Those are blockers. Unfunded accounts are not.

## A ticker-mapping note

The broker reports Berkshire as `BRKB`; the archive stores it as `BRK.B`. Any
code that reconciles live positions against archive history needs a mapping
layer, not a string comparison. The holdings file carries a `broker_symbol`
field for this.
