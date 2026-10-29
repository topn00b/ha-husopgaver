"""Tests af storage: gemmer kun ved ændring, bevarer data, fejler ærligt."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store, UnsupportedStorageVersionError

from custom_components.husopgaver.const import (
    SAVE_DELAY,
    STORAGE_MINOR_VERSION,
    STORAGE_VERSION,
    LogAction,
)
from custom_components.husopgaver.models import ChoreState, LogEntry, Occurrence
from custom_components.husopgaver.storage import HusopgaverStorage

from pytest_homeassistant_custom_component.common import async_fire_time_changed

ENTRY_ID = "entry1"
KEY = f"husopgaver.{ENTRY_ID}"
DUE = datetime(2026, 10, 30, 5, 0, tzinfo=UTC)


def _state(next_due: datetime = DUE, assignee: str = "voksen_1") -> ChoreState:
    return ChoreState(
        occurrences={"_shared": Occurrence(next_due=next_due, assignee=assignee)}
    )


def _entry(log_id: str = "log1") -> LogEntry:
    return LogEntry(
        id=log_id,
        person_id="voksen_1",
        timestamp=datetime(2026, 10, 29, 17, 0, tzinfo=UTC),
        action=LogAction.COMPLETED,
        points=1,
        chore_id="c1",
        occurrence="_shared",
    )


async def _flush(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(seconds=SAVE_DELAY + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_empty_load(hass: HomeAssistant) -> None:
    storage = HusopgaverStorage(hass, ENTRY_ID)
    await storage.async_load()
    assert storage.chore_states == {}
    assert storage.log == ()


async def test_persist_and_reload(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    storage = HusopgaverStorage(hass, ENTRY_ID)
    await storage.async_load()
    assert storage.set_chore_state("c1", _state())
    storage.add_log_entry(_entry())
    await _flush(hass, freezer)

    saved = hass_storage[KEY]
    assert saved["version"] == STORAGE_VERSION
    assert saved["minor_version"] == STORAGE_MINOR_VERSION
    assert saved["data"]["chores"]["c1"]["occurrences"]["_shared"]["next_due"] == (
        "2026-10-30T05:00:00+00:00"
    )

    reloaded = HusopgaverStorage(hass, ENTRY_ID)
    await reloaded.async_load()
    assert reloaded.chore_states == {"c1": _state()}
    assert reloaded.log == (_entry(),)
    assert reloaded.get_log_entry("log1") == _entry()
    assert reloaded.get_log_entry("ukendt") is None


async def test_no_save_when_unchanged(hass: HomeAssistant) -> None:
    storage = HusopgaverStorage(hass, ENTRY_ID)
    await storage.async_load()
    with patch.object(Store, "async_delay_save") as delay_save:
        assert storage.set_chore_state("c1", _state())
        assert delay_save.call_count == 1
        # Samme værdi igen: ingen ændring, intet gem.
        assert not storage.set_chore_state("c1", _state())
        assert delay_save.call_count == 1
        # Ny, men lig værdi bygget fra bunden: heller intet gem.
        assert not storage.set_chore_state("c1", ChoreState.from_dict(_state().to_dict()))
        assert delay_save.call_count == 1
        assert not storage.remove_chore_state("findes_ikke")
        assert delay_save.call_count == 1
        assert storage.set_chore_state("c1", _state(assignee="voksen_2"))
        assert delay_save.call_count == 2


async def test_no_save_on_load(hass: HomeAssistant, hass_storage: dict[str, Any]) -> None:
    hass_storage[KEY] = {
        "version": STORAGE_VERSION,
        "minor_version": STORAGE_MINOR_VERSION,
        "key": KEY,
        "data": {"chores": {"c1": _state().to_dict()}, "log": []},
    }
    storage = HusopgaverStorage(hass, ENTRY_ID)
    with patch.object(Store, "async_delay_save") as delay_save:
        await storage.async_load()
        assert not storage.set_chore_state("c1", _state())
    delay_save.assert_not_called()


async def test_remove_chore_keeps_log(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    storage = HusopgaverStorage(hass, ENTRY_ID)
    await storage.async_load()
    storage.set_chore_state("c1", _state())
    storage.add_log_entry(_entry())
    assert storage.remove_chore_state("c1")
    await _flush(hass, freezer)
    assert hass_storage[KEY]["data"]["chores"] == {}
    assert len(hass_storage[KEY]["data"]["log"]) == 1


async def test_duplicate_log_id_rejected(hass: HomeAssistant) -> None:
    storage = HusopgaverStorage(hass, ENTRY_ID)
    await storage.async_load()
    storage.add_log_entry(_entry())
    with pytest.raises(ValueError):
        storage.add_log_entry(_entry())
    assert len(storage.log) == 1


async def test_corrupt_data_fails_instead_of_resetting(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage[KEY] = {
        "version": STORAGE_VERSION,
        "minor_version": STORAGE_MINOR_VERSION,
        "key": KEY,
        "data": {
            "chores": {},
            "log": [{"id": "x", "person_id": "p", "timestamp": "i går", "action": "completed"}],
        },
    }
    storage = HusopgaverStorage(hass, ENTRY_ID)
    with pytest.raises(ValueError):
        await storage.async_load()


async def test_newer_major_version_is_refused(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage[KEY] = {
        "version": STORAGE_VERSION + 1,
        "minor_version": 1,
        "key": KEY,
        "data": {"chores": {}, "log": []},
    }
    storage = HusopgaverStorage(hass, ENTRY_ID)
    with pytest.raises(UnsupportedStorageVersionError):
        await storage.async_load()


async def test_older_unknown_version_is_refused(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage[KEY] = {
        "version": 0,
        "minor_version": 1,
        "key": KEY,
        "data": {"chores": {}, "log": []},
    }
    storage = HusopgaverStorage(hass, ENTRY_ID)
    with pytest.raises(NotImplementedError):
        await storage.async_load()


async def test_remove(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    storage = HusopgaverStorage(hass, ENTRY_ID)
    await storage.async_load()
    storage.set_chore_state("c1", _state())
    await _flush(hass, freezer)
    assert KEY in hass_storage
    await storage.async_remove()
    assert KEY not in hass_storage


async def test_flush_writes_pending_save(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """En genindlæsning må ikke miste ændringer, der venter på den forsinkede gemning."""
    storage = HusopgaverStorage(hass, ENTRY_ID)
    await storage.async_load()
    storage.add_log_entry(_entry())
    assert KEY not in hass_storage
    await storage.async_flush()
    assert len(hass_storage[KEY]["data"]["log"]) == 1

    reloaded = HusopgaverStorage(hass, ENTRY_ID)
    await reloaded.async_load()
    assert reloaded.log == (_entry(),)
    with patch.object(Store, "async_save") as save:
        await reloaded.async_flush()
    save.assert_not_called()
