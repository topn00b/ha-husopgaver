"""Persistens af runtime-tilstand og udførelseslog."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import SAVE_DELAY, STORAGE_KEY, STORAGE_MINOR_VERSION, STORAGE_VERSION
from .models import ChoreState, LogEntry


class _HusopgaverStore(Store[dict[str, Any]]):
    """Store med migration mellem versioner."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        # Version 1.1 er den første. Nye versioner tilføjes her, trin for trin,
        # så en gammel fil altid kan løftes til den nuværende struktur.
        raise NotImplementedError(
            f"Ukendt storage-version {old_major_version}.{old_minor_version}"
        )


class HusopgaverStorage:
    """Runtime-tilstand per opgave og den fulde udførelseslog.

    Der gemmes kun, når indholdet faktisk ændrer sig. Kan filen ikke læses,
    fejler indlæsningen i stedet for at starte forfra med tomme data.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = _HusopgaverStore(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY}.{entry_id}",
            minor_version=STORAGE_MINOR_VERSION,
        )
        self._chores: dict[str, ChoreState] = {}
        self._log: list[LogEntry] = []
        self._log_ids: set[str] = set()
        self._last_saved: dict[str, Any] | None = None

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data is None:
            self._last_saved = self._as_dict()
            return
        self._chores = {
            chore_id: ChoreState.from_dict(state)
            for chore_id, state in data["chores"].items()
        }
        self._log = [LogEntry.from_dict(entry) for entry in data["log"]]
        self._log_ids = {entry.id for entry in self._log}
        if len(self._log_ids) != len(self._log):
            raise ValueError("Udførelsesloggen indeholder dublerede id'er")
        self._last_saved = self._as_dict()

    @property
    def chore_states(self) -> Mapping[str, ChoreState]:
        return MappingProxyType(self._chores)

    @property
    def log(self) -> Sequence[LogEntry]:
        return tuple(self._log)

    def get_log_entry(self, log_id: str) -> LogEntry | None:
        if log_id not in self._log_ids:
            return None
        return next(entry for entry in self._log if entry.id == log_id)

    @callback
    def set_chore_state(self, chore_id: str, state: ChoreState) -> bool:
        """Sæt tilstanden for en opgave. Returnerer True, hvis den ændrede sig."""
        if self._chores.get(chore_id) == state:
            return False
        self._chores[chore_id] = state
        self._async_schedule_save()
        return True

    @callback
    def remove_chore_state(self, chore_id: str) -> bool:
        """Fjern tilstanden for en slettet opgave. Loggen bevares."""
        if self._chores.pop(chore_id, None) is None:
            return False
        self._async_schedule_save()
        return True

    @callback
    def add_log_entry(self, entry: LogEntry) -> None:
        if entry.id in self._log_ids:
            raise ValueError(f"Log-post findes allerede: {entry.id}")
        self._log.append(entry)
        self._log_ids.add(entry.id)
        self._async_schedule_save()

    async def async_remove(self) -> None:
        await self._store.async_remove()

    def _as_dict(self) -> dict[str, Any]:
        return {
            "chores": {
                chore_id: state.to_dict()
                for chore_id, state in sorted(self._chores.items())
            },
            "log": [entry.to_dict() for entry in self._log],
        }

    @callback
    def _async_schedule_save(self) -> None:
        data = self._as_dict()
        if data == self._last_saved:
            return
        self._last_saved = data
        self._store.async_delay_save(lambda: data, SAVE_DELAY)
