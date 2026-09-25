"""The strategy registry, and the rule that nothing runs unregistered.

Registering before running is the cheapest protection this lab has against
explaining a result after the fact. It only works if it cannot be skipped,
so `require_registered` is called by the evaluation pipeline and raises
when the file is missing or incomplete, rather than being a convention that
gets forgotten on a tired day.

Each strategy is one Markdown file in `registry/`. The machine-read part is
a TOML block between `+++` fences at the top, parsed with the standard
library, and the body below it is prose that nothing parses. The template
is deliberately invalid: copying it and forgetting to fill a field fails
here instead of producing a run against `TODO`.
"""
import os
import re
import tomllib
from datetime import date, datetime

PROVENANCE = ("literature", "own_observation", "data_derived")
MAX_PARAMETERS = 5
MIN_SIZING_RULES = 2
STAGES = (0, 1, 2, 3, 4, 5)

_FENCE = re.compile(r"\A\+\+\+\n(.*?)\n\+\+\+\n", re.DOTALL)
_ISO = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")

_TOP_TEXT = ("id", "family", "provenance", "source", "account", "enabling_step")
_REG_TEXT = (
    "hypothesis", "economic_reason", "prediction", "universe", "horizon",
    "benchmark", "kill_criteria", "current_regime_rule",
)
_REG_DATES = ("registered_on", "holdout_start", "current_regime_start")


class NotRegistered(RuntimeError):
    """The strategy has no registry file, or its file is incomplete."""


def registry_dir():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "registry",
    )


def parse(text):
    """The TOML block of a registry file as a dict."""
    match = _FENCE.match(text)
    if not match:
        raise NotRegistered("no +++ fenced block at the top of the file")
    try:
        return tomllib.loads(match.group(1))
    except tomllib.TOMLDecodeError as exc:
        raise NotRegistered(f"the fenced block is not valid TOML: {exc}")


def _filled(value):
    return isinstance(value, str) and value.strip() != "" and not value.strip().startswith("TODO")


def _as_date(value):
    if isinstance(value, date):
        return value
    if isinstance(value, str) and _ISO.match(value):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return None


def problems(spec, today=None):
    """Everything wrong with a registration, as a list of sentences.

    Empty means it is complete. Returned as a list rather than raised on
    the first, so one pass shows the whole job instead of one error at a
    time.
    """
    today = today or date.today()
    out = []
    for key in _TOP_TEXT:
        if not _filled(spec.get(key)):
            out.append(f"{key} is missing or still a placeholder")
    if spec.get("provenance") not in PROVENANCE:
        out.append(f"provenance must be one of {PROVENANCE}")
    if spec.get("stage") not in STAGES:
        out.append(f"stage must be one of {STAGES}")

    reg = spec.get("registration")
    if not isinstance(reg, dict):
        out.append("the [registration] table is missing")
        return out
    for key in _REG_TEXT:
        if not _filled(reg.get(key)):
            out.append(f"registration.{key} is missing or still a placeholder")
    dates = {}
    for key in _REG_DATES:
        parsed = _as_date(reg.get(key))
        if parsed is None:
            out.append(f"registration.{key} must be a YYYY-MM-DD date")
        dates[key] = parsed

    params = reg.get("parameters")
    if not isinstance(params, dict):
        out.append("registration.parameters must be a table; an empty one is "
                   "a claim that the strategy has none")
    elif len(params) > MAX_PARAMETERS:
        out.append(f"{len(params)} parameters; the limit is {MAX_PARAMETERS}")

    sizing = reg.get("sizing_rules")
    if not isinstance(sizing, list) or len(set(sizing)) < MIN_SIZING_RULES:
        out.append(f"at least {MIN_SIZING_RULES} distinct sizing_rules are required")

    if dates.get("registered_on") and dates["registered_on"] > today:
        out.append("registered_on is in the future")
    if spec.get("provenance") == "data_derived" and not _filled(reg.get("data_derived_burden")):
        out.append("a data_derived idea carries a stricter burden: "
                   "data_derived_burden must say why this is not a fit to the sample")
    return out


def load(strategy_id, directory=None):
    path = os.path.join(directory or registry_dir(), f"{strategy_id}.md")
    if not os.path.exists(path):
        raise NotRegistered(f"no registry file for {strategy_id!r} at {path}")
    with open(path) as handle:
        return parse(handle.read())


def require_registered(strategy_id, directory=None, today=None):
    """The registration for `strategy_id`, or raise NotRegistered.

    Also refuses a file whose `id` does not match its filename, since a
    copy that was renamed but not edited would register one strategy
    under another's name.
    """
    spec = load(strategy_id, directory)
    if spec.get("id") != strategy_id:
        raise NotRegistered(
            f"file is named {strategy_id!r} but its id is {spec.get('id')!r}"
        )
    found = problems(spec, today=today)
    if found:
        raise NotRegistered(
            f"{strategy_id} is not fully registered:\n  - " + "\n  - ".join(found)
        )
    return spec
