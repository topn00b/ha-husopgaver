"""Tildeling af opgaver og fravær."""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from datetime import UTC, datetime, timedelta
import logging

from homeassistant.const import STATE_HOME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State

from .const import Assignment
from .models import Chore, LogEntry, Person
from .points import last_done, sum_points

_LOGGER = logging.getLogger(__name__)


def is_absent(
    person: Person, state: State | None, now: datetime, threshold: timedelta
) -> bool:
    """Om personen har været væk hjemmefra længere end tærsklen.

    Væk er enhver kendt state end "home", også en zone som fx arbejde.
    Kender HA ikke personens state, regnes personen som tilgængelig.
    """
    if person.person_entity is None:
        return False
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        _LOGGER.info(
            "State for %s er ukendt; %s regnes som tilgængelig",
            person.person_entity,
            person.name,
        )
        return False
    return state.state != STATE_HOME and now - state.last_changed > threshold


def each_assignees(chore: Chore, persons: Mapping[str, Person]) -> list[str]:
    """Personer med egen forekomst ved "each": de aktive blandt assignees."""
    return [pid for pid in chore.assignees if pid in persons and persons[pid].active]


def assign(
    chore: Chore,
    persons: Mapping[str, Person],
    absent: Set[str],
    rr_index: int,
    credited: Sequence[LogEntry],
    now: datetime,
    points_window: timedelta,
) -> tuple[str | None, int]:
    """Vælg den næste person for en opgave. Returnerer (person, nyt rr_index).

    Kandidater er de aktive personer i assignees, der ikke er fraværende. Er
    alle fraværende, ses der bort fra fravær. Er ingen aktive, er resultatet None.
    """
    if chore.assignment is Assignment.EACH:
        raise ValueError("Opgaver med 'each' har en forekomst per person")

    active = each_assignees(chore, persons)
    if not active:
        return None, rr_index
    if chore.assignment is Assignment.FIXED:
        # Fast er fast: fravær ændrer ikke tildelingen.
        return active[0], rr_index

    available = [pid for pid in active if pid not in absent] or active

    if chore.assignment is Assignment.ROUND_ROBIN:
        count = len(chore.assignees)
        for offset in range(count):
            index = (rr_index + offset) % count
            if chore.assignees[index] in available:
                return chore.assignees[index], (index + 1) % count
        raise AssertionError("available er en delmængde af assignees")

    since = now - points_window
    never = datetime.min.replace(tzinfo=UTC)

    def sort_key(pid: str) -> tuple[int, datetime, int]:
        return (
            sum_points(credited, pid, since=since),
            last_done(credited, chore.id, pid) or never,
            chore.assignees.index(pid),
        )

    return min(available, key=sort_key), rr_index
