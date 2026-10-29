"""Tests af betingelser: kalender-nøgleord, entitet og ukendt."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import async_capture_events
import pytest

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.husopgaver.const import (
    EVENT_DUE,
    EVENT_NOT_NEEDED,
    ConditionState,
    LogAction,
)

from custom_components.husopgaver.coordinator import HusopgaverCoordinator

from .test_coordinator import _chore, _local, _occ, _tick, setup  # noqa: F401

CALENDAR = "calendar.familie"


@pytest.fixture
def calendar_events(hass: HomeAssistant):
    """En kalender, der returnerer alle begivenheder; integrationen filtrerer selv."""
    events: list[dict[str, Any]] = []
    hass.states.async_set(CALENDAR, "off")

    async def fetch(self, calendar, start, end):
        assert calendar == CALENDAR
        return events

    with patch.object(HusopgaverCoordinator, "_async_fetch_events", fetch):
        yield events


def _dinner(**overrides: Any) -> dict[str, Any]:
    data = _chore(
        name="Aftensmad",
        due_time="18:00",
        schedule={"kind": "weekly", "weekdays": [1, 2]},
        condition={
            "kind": "calendar",
            "calendar": CALENDAR,
            "keywords": ["besøg"],
            "check_time": "14:00",
        },
    )
    return data | overrides


def _event(start: str, end: str, summary: str = "Besøg") -> dict[str, Any]:
    return {"start": start, "end": end, "summary": summary}


class TestCalendar:
    async def test_multi_day_event_ending_before_due_time(
        self, hass, setup, freezer, calendar_events
    ) -> None:
        # Fra tirsdag morgen til onsdag kl. 15: onsdagens aftensmad kl. 18 er nødvendig.
        calendar_events.append(
            _event("2026-06-09T08:00:00+02:00", "2026-06-10T15:00:00+02:00")
        )
        coordinator = await setup({"c1": _dinner()})
        assert _occ(coordinator).condition_state is None
        await _tick(hass, freezer, _local(6, 10, 14))
        assert _occ(coordinator).condition_state is ConditionState.ACTIVE
        assert _occ(coordinator).next_due == _local(6, 10, 18)

    async def test_event_starting_after_due_time(
        self, hass, setup, freezer, calendar_events
    ) -> None:
        calendar_events.append(
            _event("2026-06-10T19:00:00+02:00", "2026-06-10T22:00:00+02:00")
        )
        coordinator = await setup({"c1": _dinner()})
        await _tick(hass, freezer, _local(6, 10, 14))
        assert _occ(coordinator).condition_state is ConditionState.ACTIVE

    async def test_event_during_due_time_not_needed(
        self, hass, setup, freezer, calendar_events
    ) -> None:
        events = async_capture_events(hass, EVENT_NOT_NEEDED)
        dues = async_capture_events(hass, EVENT_DUE)
        calendar_events.append(
            _event("2026-06-10T08:00:00+02:00", "2026-06-11T15:00:00+02:00", "BESØG af familie")
        )
        coordinator = await setup({"c1": _dinner(assignment="round_robin")})
        before = coordinator.storage.chore_states["c1"]
        await _tick(hass, freezer, _local(6, 10, 14))

        entry = coordinator.storage.log[-1]
        assert entry.action is LogAction.NOT_NEEDED and entry.points == 0
        assert len(events) == 1 and events[0].data["log_id"] == entry.id
        occ = _occ(coordinator)
        # Næste forfald er tirsdag; rotationen rykker ikke.
        assert occ.next_due == _local(6, 16, 18)
        assert occ.assignee == before.occurrences["_shared"].assignee
        assert coordinator.storage.chore_states["c1"].rr_index == before.rr_index
        assert occ.condition_state is None

        # Den er væk fra listen, og der kommer ingen "forfalden" kl. 18.
        await _tick(hass, freezer, _local(6, 10, 18))
        assert not dues

    async def test_all_day_event(self, hass, setup, freezer, calendar_events) -> None:
        calendar_events.append(_event("2026-06-10", "2026-06-11", "Besøg"))
        coordinator = await setup({"c1": _dinner()})
        await _tick(hass, freezer, _local(6, 10, 14))
        assert coordinator.storage.log[-1].action is LogAction.NOT_NEEDED

    async def test_all_day_event_previous_day_does_not_count(
        self, hass, setup, freezer, calendar_events
    ) -> None:
        calendar_events.append(_event("2026-06-09", "2026-06-10", "Besøg"))
        coordinator = await setup({"c1": _dinner()})
        await _tick(hass, freezer, _local(6, 10, 14))
        assert _occ(coordinator).condition_state is ConditionState.ACTIVE

    async def test_without_due_time_any_event_that_day(
        self, hass, setup, freezer, calendar_events
    ) -> None:
        calendar_events.append(
            _event("2026-06-10T21:00:00+02:00", "2026-06-10T23:00:00+02:00")
        )
        data = _dinner()
        del data["due_time"]
        coordinator = await setup({"c1": data})
        await _tick(hass, freezer, _local(6, 10, 14))
        assert coordinator.storage.log[-1].action is LogAction.NOT_NEEDED

    async def test_other_keywords_ignored(
        self, hass, setup, freezer, calendar_events
    ) -> None:
        calendar_events.append(
            _event("2026-06-10T08:00:00+02:00", "2026-06-10T23:00:00+02:00", "Tandlæge")
        )
        coordinator = await setup({"c1": _dinner()})
        await _tick(hass, freezer, _local(6, 10, 14))
        assert _occ(coordinator).condition_state is ConditionState.ACTIVE

    async def test_check_time_passed_at_creation(
        self, hass, setup, calendar_events
    ) -> None:
        data = _dinner()
        data["condition"] = data["condition"] | {"check_time": "09:00"}
        coordinator = await setup({"c1": data})
        await hass.async_block_till_done()
        assert _occ(coordinator).condition_state is ConditionState.ACTIVE

    async def test_unavailable_calendar_stays_with_unknown(
        self, hass, setup, freezer, calendar_events
    ) -> None:
        hass.states.async_set(CALENDAR, "unavailable")
        coordinator = await setup({"c1": _dinner()})
        await _tick(hass, freezer, _local(6, 10, 14))
        assert _occ(coordinator).condition_state is ConditionState.UNKNOWN
        result = await hass.services.async_call(
            "todo",
            "get_items",
            {},
            target={"entity_id": "todo.husopgaver_voksen_1"},
            blocking=True,
            return_response=True,
        )
        items = result["todo.husopgaver_voksen_1"]["items"]
        assert items[0]["description"] == "2 point · Kommende · Betingelse ukendt"


async def test_real_calendar_service(hass, setup, freezer) -> None:
    """Hele vejen gennem HA's calendar.get_events, med integrationens egen kalender."""
    visit = _local(6, 10, 18).isoformat()
    data = _dinner()
    data["condition"] = data["condition"] | {"calendar": "calendar.husopgaver"}
    coordinator = await setup(
        {
            "c1": data,
            "c2": _chore(name="Besøg", schedule={"kind": "none", "due": visit}, due_time="18:00"),
        }
    )
    await _tick(hass, freezer, _local(6, 10, 14))
    assert [e.action for e in coordinator.storage.log] == [LogAction.NOT_NEEDED]


class TestEntity:
    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            ("on", ConditionState.ACTIVE),
            ("unavailable", ConditionState.UNKNOWN),
        ],
    )
    async def test_states(self, hass, setup, freezer, state, expected) -> None:
        hass.states.async_set("input_boolean.hjemme", state)
        coordinator = await setup({"c1": _entity_chore()})
        await _tick(hass, freezer, _local(6, 10, 14))
        assert _occ(coordinator).condition_state is expected

    async def test_off_is_not_needed(self, hass, setup, freezer) -> None:
        hass.states.async_set("input_boolean.hjemme", "off")
        coordinator = await setup({"c1": _entity_chore()})
        await _tick(hass, freezer, _local(6, 10, 14))
        assert coordinator.storage.log[-1].action is LogAction.NOT_NEEDED


def _entity_chore() -> dict[str, Any]:
    return _dinner(
        condition={
            "kind": "entity",
            "entity": "input_boolean.hjemme",
            "active_state": "on",
            "check_time": "14:00",
        }
    )


class TestFlow:
    async def test_add_with_calendar_condition(self, hass, setup) -> None:
        coordinator = await setup({})
        entry = coordinator.entry
        flow = hass.config_entries.subentries
        result = await flow.async_init(
            (entry.entry_id, "chore"), context={"source": SOURCE_USER}
        )
        result = await flow.async_configure(
            result["flow_id"],
            {
                "name": "Aftensmad",
                "points": 2,
                "assignees": ["v1", "v2"],
                "assignment": "least_points",
                "repeat": "weekly",
                "due_time": "18:00:00",
                "advanced": {
                    "approval": "auto",
                    "builtin_notify": False,
                    "condition": "calendar",
                },
            },
        )
        result = await flow.async_configure(result["flow_id"], {"weekdays": ["mon", "thu"]})
        assert result["step_id"] == "condition_calendar"
        result = await flow.async_configure(
            result["flow_id"],
            {"calendar": CALENDAR, "keywords": [" Besøg ", ""], "check_time": "14:00:00"},
        )
        await hass.async_block_till_done()
        assert result["type"] is FlowResultType.CREATE_ENTRY
        chore = next(iter(entry.runtime_data.chores.values()))
        assert chore.condition is not None
        assert chore.condition.keywords == ("Besøg",)

    async def test_remove_condition(self, hass, setup) -> None:
        coordinator = await setup({"c1": _dinner()})
        entry = coordinator.entry
        flow = hass.config_entries.subentries
        result = await flow.async_init(
            (entry.entry_id, "chore"),
            context={"source": SOURCE_RECONFIGURE, "subentry_id": "c1"},
        )
        result = await flow.async_configure(
            result["flow_id"],
            {
                "name": "Aftensmad",
                "points": 2,
                "assignees": ["v1", "v2"],
                "assignment": "least_points",
                "repeat": "weekly",
                "advanced": {"approval": "auto", "builtin_notify": False, "condition": "none"},
            },
        )
        result = await flow.async_configure(result["flow_id"], {"weekdays": ["tue"]})
        await hass.async_block_till_done()
        assert result["type"] is FlowResultType.ABORT
        assert entry.runtime_data.chores["c1"].condition is None
