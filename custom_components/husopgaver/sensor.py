"""Pointsensor per person."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from . import HusopgaverConfigEntry
from .const import ChoreStatus, LogAction
from .coordinator import HusopgaverCoordinator
from .entity import HusopgaverEntity
from .models import Person
from .points import credited_entries, pending_entries, sum_points
from .schedule import month_start, week_start


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HusopgaverConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        PointsSensor(coordinator, person) for person in coordinator.persons.values()
    )


class PointsSensor(HusopgaverEntity, SensorEntity):
    """Godkendte point i indeværende uge (mandag til søndag, lokal tid)."""

    _attr_translation_key = "points"
    _attr_native_unit_of_measurement = "point"

    def __init__(self, coordinator: HusopgaverCoordinator, person: Person) -> None:
        super().__init__(coordinator, f"points_{person.id}")
        self._person = person
        self._attr_translation_placeholders = {"person": person.name}
        self.entity_id = f"sensor.husopgaver_{slugify(person.name)}_point"

    def _update_from_coordinator(self) -> None:
        now = dt_util.utcnow()
        pid = self._person.id
        log = self.coordinator.storage.log
        credited = credited_entries(log)
        # Efter rækkefølgen i loggen: alt før udbetalingen er afregnet.
        last_settled = max(
            (
                index
                for index, e in enumerate(log)
                if e.action is LogAction.SETTLED and e.person_id == pid
            ),
            default=-1,
        )
        after_settlement = {e.id for e in log[last_settled + 1 :]}
        self._attr_native_value = sum_points(credited, pid, since=week_start(now))
        attributes: dict[str, Any] = {
            "month": sum_points(credited, pid, since=month_start(now)),
            "all_time": sum_points(credited, pid),
            "since_settlement": sum_points(
                [e for e in credited if e.id in after_settlement], pid
            ),
            "pending": sum(e.points for e in pending_entries(log) if e.person_id == pid),
            "completed_count": sum(1 for e in credited if e.person_id == pid),
            "overdue_count": sum(
                1
                for view in self.coordinator.occurrences(now)
                if view.belongs_to(pid) and view.status is ChoreStatus.OVERDUE
            ),
        }
        self._attr_extra_state_attributes = attributes
