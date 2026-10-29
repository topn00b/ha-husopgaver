"""Husopgaver: familiens opgaver, rotation og point i Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import HusopgaverCoordinator
from .storage import HusopgaverStorage

PLATFORMS = [Platform.CALENDAR, Platform.SENSOR, Platform.TODO]

type HusopgaverConfigEntry = ConfigEntry[HusopgaverCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: HusopgaverConfigEntry) -> bool:
    storage = HusopgaverStorage(hass, entry.entry_id)
    await storage.async_load()
    coordinator = HusopgaverCoordinator(hass, entry, storage)
    coordinator.async_start()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_stop)
    # Personer, opgaver og indstillinger ændres via subentries og options.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: HusopgaverConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HusopgaverConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.storage.async_flush()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: HusopgaverConfigEntry) -> None:
    await HusopgaverStorage(hass, entry.entry_id).async_remove()
