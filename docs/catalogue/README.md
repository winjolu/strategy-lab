# Strategy catalogue

41 candidate strategies, compiled 2026-09-21, each with a complete entry rule,
exit rule, sizing rule, parameter count and data requirement.

`strategies.json` is authoritative and `strategies.csv` is a sortable view of
the same rows. `summary.md` carries the ranking and the reasoning behind it,
and `../data-gaps.md` records what cannot be tested and what would unblock it.

**Nothing in these files is a finding.** Every performance figure in them is
either an author's claim or my preliminary estimate, both labelled as such.
They are the source of candidate definitions, not of evidence. A candidate
enters this lab's registry only after its own Stage 0 entry is written in
`registry/`, with its prediction, holdout date and kill criteria fixed before
its first run.

Two entries have been registered so far: `xs-mr-khandani-lo` and
`event-narrative-fade`. `docs/kalshi-survey.md` corrects two statements in this
catalogue about event-contract data (settled prices are retrievable, and only
order book depth is perishable).
