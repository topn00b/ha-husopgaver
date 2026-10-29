"""Kalender med opgavernes kommende forekomster."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HusopgaverConfigEntry
from .const import Assignment
from .coordinator import HusopgaverCoordinator, OccurrenceView
from .entity import HusopgaverEntity
from .schedule import local_date, next_due
from .texts import text

# Øvre grænse for udvidelse af én gentagelse i en forespørgsel.
_MAX_PER_OCCURRENCE = 1000
_TIMED_DURATION = timedelta(hours=1)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HusopgaverConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ChoreCalendar(entry.runtime_data)])


def _projected_dues(view: OccurrenceView, end: datetime) -> Iterator[datetime]:
    """Forekomstens forfald og de følgende, som om hver blev lavet til tiden."""
    yield view.due
    previous = view.occurrence.next_due
    assert previous is not None
    for _ in range(_MAX_PER_OCCURRENCE):
        following = next_due(
            view.chore, previous, previous, previous, view.occurrence.anchor
        )
        if following is None or following >= end:
            return
        if following > view.due:
            yield following
        previous = following


class ChoreCalendar(HusopgaverEntity, CalendarEntity):
    """calendar.husopgaver. Ikke nødvendige forekomster vises ikke."""

    _attr_name = None

    def __init__(self, coordinator: HusopgaverCoordinator) -> None:
        super().__init__(coordinator, "calendar")
        self.entity_id = "calendar.husopgaver"
        self._event: CalendarEvent | None = None

    def _event_for(self, view: OccurrenceView, due: datetime) -> CalendarEvent:
        # Kun den aktuelle forekomst har en kendt person; ved rotation er de
        # følgende ukendte. Fast og "each" har altid samme person.
        known = due == view.due or view.chore.assignment in (
            Assignment.FIXED,
            Assignment.EACH,
        )
        person = self.coordinator.persons.get(view.person_id or "") if known else None
        summary = (
            text(self.hass, "with_person", chore=view.chore.name, person=person.name)
            if person
            else view.chore.name
        )
        if view.chore.due_time is None:
            day = local_date(due)
            return CalendarEvent(
                start=day,
                end=day + timedelta(days=1),
                summary=summary,
                description=view.chore.description,
                uid=f"{view.uid}|{due.isoformat()}",
            )
        local = dt_util.as_local(due)
        return CalendarEvent(
            start=local,
            end=local + _TIMED_DURATION,
            summary=summary,
            description=view.chore.description,
            uid=f"{view.uid}|{due.isoformat()}",
        )

    def _events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        events = []
        for view in self.coordinator.occurrences(dt_util.utcnow()):
            for due in _projected_dues(view, end):
                event = self._event_for(view, due)
                if event.end_datetime_local > start and event.start_datetime_local < end:
                    events.append(event)
        return sorted(events, key=lambda e: e.start_datetime_local)

    @property
    def event(self) -> CalendarEvent | None:
        return self._event

    def _update_from_coordinator(self) -> None:
        now = dt_util.now()
        events = [
            self._event_for(view, view.due)
            for view in self.coordinator.occurrences(dt_util.utcnow())
        ]
        current = [e for e in events if e.end_datetime_local > now]
        self._event = min(current, key=lambda e: e.start_datetime_local, default=None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return self._events(start_date, end_date)
