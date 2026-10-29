"""Husopgaver: familiens opgaver, rotation og point i Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .storage import HusopgaverStorage

type HusopgaverConfigEntry = ConfigEntry[HusopgaverStorage]


async def async_setup_entry(hass: HomeAssistant, entry: HusopgaverConfigEntry) -> bool:
    storage = HusopgaverStorage(hass, entry.entry_id)
    await storage.async_load()
    entry.runtime_data = storage
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HusopgaverConfigEntry) -> bool:
    return True


async def async_remove_entry(hass: HomeAssistant, entry: HusopgaverConfigEntry) -> None:
    await HusopgaverStorage(hass, entry.entry_id).async_remove()
