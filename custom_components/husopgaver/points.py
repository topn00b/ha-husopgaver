"""Pointregnskab ud fra udførelsesloggen.

Point gives af "completed" og af "approved" (der henviser til en "pending").
En "undone" med henvisning til en af dem trækker pointene tilbage.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from .const import LogAction
from .models import LogEntry

_CREDITING = frozenset({LogAction.COMPLETED, LogAction.APPROVED})
_RESOLVING = frozenset({LogAction.APPROVED, LogAction.REJECTED, LogAction.UNDONE})


def credited_entries(log: Iterable[LogEntry]) -> list[LogEntry]:
    """Log-poster, der giver point, og som ikke er fortrudt."""
    entries = list(log)
    undone = {e.ref for e in entries if e.action is LogAction.UNDONE}
    return [e for e in entries if e.action in _CREDITING and e.id not in undone]


def pending_entries(log: Iterable[LogEntry]) -> list[LogEntry]:
    """Afkrydsninger, der endnu hverken er godkendt, afvist eller fortrudt."""
    entries = list(log)
    resolved = {e.ref for e in entries if e.action in _RESOLVING}
    return [
        e for e in entries if e.action is LogAction.PENDING and e.id not in resolved
    ]


def sum_points(
    credited: Sequence[LogEntry],
    person_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> int:
    """Godkendte point for en person i perioden [since, until)."""
    return sum(
        e.points
        for e in credited
        if e.person_id == person_id
        and (since is None or e.timestamp >= since)
        and (until is None or e.timestamp < until)
    )


def last_done(
    credited: Sequence[LogEntry], chore_id: str, person_id: str
) -> datetime | None:
    """Hvornår personen sidst udførte netop denne opgave. None: aldrig."""
    return max(
        (
            e.timestamp
            for e in credited
            if e.chore_id == chore_id and e.person_id == person_id
        ),
        default=None,
    )
