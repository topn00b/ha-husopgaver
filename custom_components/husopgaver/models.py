"""Datamodel for Husopgaver.

Konfiguration (personer og opgaver) ligger i config subentries og parses her.
Runtime-tilstand og udførelseslog ligger i Store (se storage.py).

Alle tidspunkter gemmes i UTC som ISO 8601. Ugyldige data giver ValueError:
der gættes aldrig på en værdi.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Any, Self

from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_POINTS,
    ApprovalMode,
    Assignment,
    ConditionKind,
    ConditionState,
    IntervalFrom,
    IntervalUnit,
    LogAction,
    ScheduleKind,
)


def _dt_to_str(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError(f"Tidspunkt uden tidszone: {value!r}")
    return dt_util.as_utc(value).isoformat()


def _dt_from_str(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None or parsed.tzinfo is None:
        raise ValueError(f"Ugyldigt tidspunkt: {value!r}")
    return dt_util.as_utc(parsed)


def _time_from_str(value: str | None) -> time | None:
    if value is None:
        return None
    parsed = dt_util.parse_time(value)
    if parsed is None:
        raise ValueError(f"Ugyldigt klokkeslæt: {value!r}")
    return parsed


def _date_from_str(value: str | None) -> date | None:
    if value is None:
        return None
    parsed = dt_util.parse_date(value)
    if parsed is None:
        raise ValueError(f"Ugyldig dato: {value!r}")
    return parsed


def _time_to_str(value: time | None) -> str | None:
    return None if value is None else value.isoformat()


def _duration_from(value: int | None) -> timedelta | None:
    if value is None:
        return None
    if value < 0:
        raise ValueError(f"Negativ varighed: {value!r}")
    return timedelta(seconds=value)


def _duration_to(value: timedelta | None) -> int | None:
    return None if value is None else int(value.total_seconds())


def _parse_month_day(value: str) -> tuple[int, int]:
    """Parse 'MM-DD'. 29. februar afvises, da datoen ikke findes hvert år."""
    try:
        month_str, day_str = value.split("-")
        month, day = int(month_str), int(day_str)
        datetime(2001, month, day)  # 2001 er ikke skudår
    except ValueError as err:
        raise ValueError(f"Ugyldig årlig dato: {value!r} (brug MM-DD)") from err
    return month, day


@dataclass(frozen=True, slots=True)
class Person:
    """En deltager i husholdningen."""

    id: str
    name: str
    person_entity: str | None = None
    notify_target: str | None = None
    can_approve: bool = False
    requires_approval: bool = False
    active: bool = True

    @classmethod
    def from_dict(cls, person_id: str, data: dict[str, Any]) -> Self:
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("En person skal have et navn")
        person_entity = data.get("person_entity") or None
        if person_entity is not None and not person_entity.startswith("person."):
            raise ValueError(f"Ikke en person-entitet: {person_entity!r}")
        notify_target = data.get("notify_target") or None
        if notify_target is not None and not notify_target.startswith("notify."):
            raise ValueError(f"Ikke et notify-mål: {notify_target!r}")
        return cls(
            id=person_id,
            name=name,
            person_entity=person_entity,
            notify_target=notify_target,
            can_approve=bool(data.get("can_approve", False)),
            requires_approval=bool(data.get("requires_approval", False)),
            active=bool(data.get("active", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "person_entity": self.person_entity,
            "notify_target": self.notify_target,
            "can_approve": self.can_approve,
            "requires_approval": self.requires_approval,
            "active": self.active,
        }


@dataclass(frozen=True, slots=True)
class Schedule:
    """Hvornår en opgave forfalder."""

    kind: ScheduleKind
    due: datetime | None = None  # kun for "none"
    every: int | None = None
    unit: IntervalUnit | None = None
    from_: IntervalFrom | None = None
    weekdays: tuple[int, ...] = ()  # mandag = 0
    dates: tuple[tuple[int, int], ...] = ()  # (måned, dag)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        kind = ScheduleKind(data["kind"])
        if kind is ScheduleKind.NONE:
            return cls(kind=kind, due=_dt_from_str(data.get("due")))
        if kind is ScheduleKind.INTERVAL:
            every = int(data["every"])
            if every < 1:
                raise ValueError("Interval skal være mindst 1")
            return cls(
                kind=kind,
                every=every,
                unit=IntervalUnit(data["unit"]),
                from_=IntervalFrom(data.get("from", IntervalFrom.DUE)),
            )
        if kind is ScheduleKind.WEEKLY:
            weekdays = tuple(sorted({int(d) for d in data["weekdays"]}))
            if not weekdays or any(d < 0 or d > 6 for d in weekdays):
                raise ValueError(f"Ugyldige ugedage: {data['weekdays']!r}")
            return cls(kind=kind, weekdays=weekdays)
        dates = tuple(sorted({_parse_month_day(d) for d in data["dates"]}))
        if not dates:
            raise ValueError("En årlig opgave skal have mindst én dato")
        return cls(kind=kind, dates=dates)

    def to_dict(self) -> dict[str, Any]:
        match self.kind:
            case ScheduleKind.NONE:
                return {"kind": self.kind.value, "due": _dt_to_str(self.due)}
            case ScheduleKind.INTERVAL:
                assert self.unit is not None and self.from_ is not None
                return {
                    "kind": self.kind.value,
                    "every": self.every,
                    "unit": self.unit.value,
                    "from": self.from_.value,
                }
            case ScheduleKind.WEEKLY:
                return {"kind": self.kind.value, "weekdays": list(self.weekdays)}
            case ScheduleKind.YEARLY:
                return {
                    "kind": self.kind.value,
                    "dates": [f"{m:02d}-{d:02d}" for m, d in self.dates],
                }


@dataclass(frozen=True, slots=True)
class Condition:
    """Afgør om en forekomst er nødvendig (fx aftensmad når familien er hjemme)."""

    kind: ConditionKind
    check_time: time
    calendar: str | None = None
    keywords: tuple[str, ...] = ()
    entity: str | None = None
    active_state: str = "on"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        kind = ConditionKind(data["kind"])
        check_time = _time_from_str(data.get("check_time"))
        if check_time is None:
            raise ValueError("En betingelse skal have et tidspunkt for tjek")
        if kind is ConditionKind.CALENDAR:
            calendar = data.get("calendar")
            keywords = tuple(
                k.strip() for k in data.get("keywords", []) if k and k.strip()
            )
            if not calendar or not calendar.startswith("calendar."):
                raise ValueError(f"Ugyldig kalender: {calendar!r}")
            if not keywords:
                raise ValueError("En kalenderbetingelse skal have mindst ét nøgleord")
            return cls(
                kind=kind, check_time=check_time, calendar=calendar, keywords=keywords
            )
        entity = data.get("entity")
        if not entity:
            raise ValueError("En entitetsbetingelse skal have en entitet")
        return cls(
            kind=kind,
            check_time=check_time,
            entity=entity,
            active_state=str(data.get("active_state", "on")),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": self.kind.value,
            "check_time": _time_to_str(self.check_time),
        }
        if self.kind is ConditionKind.CALENDAR:
            data |= {"calendar": self.calendar, "keywords": list(self.keywords)}
        else:
            data |= {"entity": self.entity, "active_state": self.active_state}
        return data


@dataclass(frozen=True, slots=True)
class Chore:
    """En opgave, som den er konfigureret."""

    id: str
    name: str
    assignees: tuple[str, ...]
    schedule: Schedule
    assignment: Assignment = Assignment.LEAST_POINTS
    description: str | None = None
    points: int = DEFAULT_POINTS
    due_time: time | None = None
    notify_before: timedelta | None = None
    complete_window: timedelta | None = None
    approval: ApprovalMode = ApprovalMode.AUTO
    condition: Condition | None = None
    builtin_notify: bool = False

    @classmethod
    def from_dict(cls, chore_id: str, data: dict[str, Any]) -> Self:
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("En opgave skal have et navn")
        points = int(data.get("points", DEFAULT_POINTS))
        if points < 0:
            raise ValueError("Point kan ikke være negative")
        # Rækkefølgen bevares: den bruges til round robin og tiebreak.
        assignees = tuple(dict.fromkeys(data.get("assignees", [])))
        if not assignees:
            raise ValueError("En opgave skal have mindst én person")
        condition = data.get("condition")
        return cls(
            id=chore_id,
            name=name,
            description=data.get("description") or None,
            points=points,
            assignees=assignees,
            assignment=Assignment(data.get("assignment", Assignment.LEAST_POINTS)),
            schedule=Schedule.from_dict(data["schedule"]),
            due_time=_time_from_str(data.get("due_time")),
            notify_before=_duration_from(data.get("notify_before")),
            complete_window=_duration_from(data.get("complete_window")),
            approval=ApprovalMode(data.get("approval", ApprovalMode.AUTO)),
            condition=Condition.from_dict(condition) if condition else None,
            builtin_notify=bool(data.get("builtin_notify", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "points": self.points,
            "assignees": list(self.assignees),
            "assignment": self.assignment.value,
            "schedule": self.schedule.to_dict(),
            "due_time": _time_to_str(self.due_time),
            "notify_before": _duration_to(self.notify_before),
            "complete_window": _duration_to(self.complete_window),
            "approval": self.approval.value,
            "condition": self.condition.to_dict() if self.condition else None,
            "builtin_notify": self.builtin_notify,
        }


@dataclass(frozen=True, slots=True)
class Occurrence:
    """Den aktuelle forekomst af en opgave (én per person ved "each")."""

    next_due: datetime | None  # None: engangsopgave er udført
    assignee: str | None
    snoozed_until: datetime | None = None
    pending_log_id: str | None = None
    condition_state: ConditionState | None = None
    # Første forfaldsdato i serien (lokal dato). Bruges af interval fra forfald,
    # så en månedlig opgave den 31. vender tilbage til den 31. efter februar.
    anchor: date | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        condition_state = data.get("condition_state")
        return cls(
            next_due=_dt_from_str(data.get("next_due")),
            assignee=data.get("assignee"),
            snoozed_until=_dt_from_str(data.get("snoozed_until")),
            pending_log_id=data.get("pending_log_id"),
            condition_state=ConditionState(condition_state)
            if condition_state
            else None,
            anchor=_date_from_str(data.get("anchor")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "next_due": _dt_to_str(self.next_due),
            "assignee": self.assignee,
            "snoozed_until": _dt_to_str(self.snoozed_until),
            "pending_log_id": self.pending_log_id,
            "condition_state": self.condition_state.value
            if self.condition_state
            else None,
            "anchor": None if self.anchor is None else self.anchor.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ChoreState:
    """Runtime-tilstand for en opgave."""

    occurrences: dict[str, Occurrence] = field(default_factory=dict)
    rr_index: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            occurrences={
                key: Occurrence.from_dict(value)
                for key, value in data.get("occurrences", {}).items()
            },
            rr_index=int(data.get("rr_index", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "occurrences": {
                key: occ.to_dict() for key, occ in sorted(self.occurrences.items())
            },
            "rr_index": self.rr_index,
        }

    def with_occurrence(self, key: str, occurrence: Occurrence) -> ChoreState:
        return replace(self, occurrences={**self.occurrences, key: occurrence})


@dataclass(frozen=True, slots=True)
class LogEntry:
    """En post i udførelsesloggen. Loggen tilføjes kun til og slettes aldrig."""

    id: str
    person_id: str
    timestamp: datetime
    action: LogAction
    points: int = 0
    chore_id: str | None = None  # None for "settled"
    occurrence: str | None = None
    ref: str | None = None
    by_user: str | None = None
    # Tilstand før handlingen, så "undo" kan rulle tilbage præcist.
    previous_state: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        timestamp = _dt_from_str(data["timestamp"])
        assert timestamp is not None
        return cls(
            id=data["id"],
            person_id=data["person_id"],
            timestamp=timestamp,
            action=LogAction(data["action"]),
            points=int(data.get("points", 0)),
            chore_id=data.get("chore_id"),
            occurrence=data.get("occurrence"),
            ref=data.get("ref"),
            by_user=data.get("by_user"),
            previous_state=data.get("previous_state"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "person_id": self.person_id,
            "timestamp": _dt_to_str(self.timestamp),
            "action": self.action.value,
            "points": self.points,
            "chore_id": self.chore_id,
            "occurrence": self.occurrence,
            "ref": self.ref,
            "by_user": self.by_user,
            "previous_state": self.previous_state,
        }
