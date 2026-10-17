"""Strict structural validation of observer journals, not proof of fair play."""

import json
import math
from pathlib import Path

from .catalog import CATALOG_VERSION, GROUPS, MILESTONES


class JournalError(ValueError):
    pass


def _number(value, field):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise JournalError(f"{field} must be a finite nonnegative number")
    return value


def score(events):
    events = list(events)
    if not events or not isinstance(events[0], dict) or events[0].get("event") != "session_start":
        raise JournalError("journal must begin with session_start")
    first = events[0]
    run_id = first.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise JournalError("missing run_id")
    baseline = first.get("baseline")
    if (not isinstance(baseline, list) or any(type(m) is not str for m in baseline)
            or len(set(baseline)) != len(baseline)
            or not set(baseline) <= set(MILESTONES)):
        raise JournalError("baseline must list unique known milestones")
    synthetic = first.get("synthetic")
    if type(synthetic) is not bool:
        raise JournalError("session_start must declare synthetic true or false")
    earned = {}
    deaths = 0
    last_tick, last_elapsed = -1, -1
    ended = False
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise JournalError("every journal entry must be an object")
        if ended:
            raise JournalError("events after session_end")
        if (type(event.get("schema")) is not int or event.get("schema") != 1 or event.get("run_id") != run_id
                or event.get("source") != "TerrariaBenchObserver"):
            raise JournalError("schema, run_id or observer source mismatch")
        tick = _number(event.get("tick"), "tick")
        elapsed = _number(event.get("elapsed_seconds"), "elapsed_seconds")
        if type(tick) is not int or tick < last_tick or elapsed < last_elapsed:
            raise JournalError("tick and elapsed time must be monotonic; tick must be integer")
        last_tick, last_elapsed = tick, elapsed
        kind = event.get("event")
        if kind == "session_start":
            if index != 0 or event.get("catalog") != CATALOG_VERSION:
                raise JournalError("duplicate start or incompatible catalog")
        elif kind == "checkpoint":
            milestone = event.get("milestone")
            if type(milestone) is not str or milestone not in MILESTONES:
                raise JournalError("unknown milestone")
            if milestone in baseline:
                raise JournalError("inherited milestone cannot earn credit")
            if milestone in earned:
                raise JournalError("duplicate checkpoint")
            earned[milestone] = {"tick": tick, "elapsed_seconds": elapsed}
        elif kind == "death":
            deaths += 1
        elif kind == "heartbeat":
            pass  # Evaluator-only liveness/time diagnostics; never progress credit.
        elif kind == "session_end":
            ended = True
        else:
            raise JournalError(f"unknown event: {kind!r}")
    return {
        "run_id": run_id,
        "catalog": CATALOG_VERSION,
        "synthetic": synthetic,
        "journal_closed": ended,
        "official_eligible": False,
        "ineligibility_reason": "Development prototype: independent integrity validation and official evaluation protocol are not complete.",
        "progress_count": len(earned),
        "progress_possible": len(MILESTONES),
        "moon_lord_observed": "moon_lord" in earned,
        "deaths": deaths,
        "elapsed_seconds": last_elapsed,
        "game_updates": last_tick,
        "inherited": baseline,
        "first_unlocks": earned,
        "groups": {name: sum(m in earned for m in group) for name, group in GROUPS.items()},
    }


def read_journal(path):
    events = []
    with Path(path).open() as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise JournalError(f"line {line_number}: invalid JSON") from error
            if not isinstance(event, dict):
                raise JournalError(f"line {line_number}: expected object")
            events.append(event)
    return events
