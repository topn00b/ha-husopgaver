"""Fælles base for Husopgavers entiteter."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import HusopgaverCoordinator


class HusopgaverEntity(Entity):
    """Opdateres, når koordinatoren melder en ændring. Der polles ikke."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: HusopgaverCoordinator, key: str) -> None:
        self.coordinator = coordinator
        entry_id = coordinator.entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Husopgaver",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self._update_from_coordinator()
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self._update_from_coordinator()
        self.async_write_ha_state()

    def _update_from_coordinator(self) -> None:
        """Beregn entitetens værdier ud fra koordinatoren."""
