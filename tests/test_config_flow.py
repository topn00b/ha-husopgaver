"""Tests af options og subentry-flows for personer og opgaver."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.husopgaver.const import (
    CONF_ABSENCE_HOURS,
    CONF_ALL_LIST,
    CONF_POINTS_WINDOW_DAYS,
    CONF_UNDO_MINUTES,
    CONF_UPCOMING_DAYS,
)

from .test_coordinator import _chore, _local, _occ, setup  # noqa: F401


def _suggested(result: dict[str, Any], key: str, in_section: str | None = None) -> Any:
    schema = result["data_schema"].schema
    if in_section is not None:
        schema = next(v for m, v in schema.items() if m == in_section).schema.schema
    for marker in schema:
        if marker == key:
            return (marker.description or {}).get("suggested_value")
    raise KeyError(key)


async def _start(hass: HomeAssistant, entry_id: str, kind: str, **context: Any):
    return await hass.config_entries.subentries.async_init(
        (entry_id, kind), context={"source": SOURCE_USER, **context}
    )


async def _configure(hass: HomeAssistant, flow_id: str, data: dict[str, Any]):
    result = await hass.config_entries.subentries.async_configure(flow_id, data)
    await hass.async_block_till_done()
    return result


async def test_options(hass, setup) -> None:
    coordinator = await setup({"c1": _chore()})
    entry = coordinator.entry
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_UPCOMING_DAYS: 3,
            CONF_POINTS_WINDOW_DAYS: 14,
            CONF_ABSENCE_HOURS: 48,
            CONF_UNDO_MINUTES: 5,
            CONF_ALL_LIST: True,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    coordinator = entry.runtime_data
    assert coordinator.upcoming_window == timedelta(days=3)
    assert coordinator.points_window == timedelta(days=14)
    assert coordinator.absence_threshold == timedelta(hours=48)
    assert coordinator.undo_window == timedelta(minutes=5)
    assert hass.states.get("todo.husopgaver_alle") is not None


class TestPersonFlow:
    async def test_add(self, hass, setup) -> None:
        coordinator = await setup({})
        entry = coordinator.entry
        result = await _start(hass, entry.entry_id, "person")
        assert result["type"] is FlowResultType.FORM
        result = await _configure(
            hass,
            result["flow_id"],
            {
                "name": "  Barn 2 ",
                "color": [255, 128, 0],
                "can_approve": False,
                "requires_approval": True,
                "active": True,
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        person = next(
            p for p in entry.runtime_data.persons.values() if p.name == "Barn 2"
        )
        assert person.color == "#ff8000" and person.requires_approval
        assert hass.states.get("todo.husopgaver_barn_2") is not None
        assert hass.states.get("sensor.husopgaver_barn_2_point") is not None

    async def test_invalid_notify_target(self, hass, setup) -> None:
        coordinator = await setup({})
        result = await _start(hass, coordinator.entry.entry_id, "person")
        result = await _configure(
            hass,
            result["flow_id"],
            {
                "name": "Barn 2",
                "notify_target": "mobile_app_barn_2",
                "can_approve": False,
                "requires_approval": False,
                "active": True,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid"}

    async def test_reconfigure(self, hass, setup) -> None:
        coordinator = await setup({})
        entry = coordinator.entry
        hass.config_entries.async_update_subentry(
            entry, entry.subentries["v1"], data={**entry.subentries["v1"].data, "color": "#102030"}
        )
        await hass.async_block_till_done()
        result = await _start(
            hass, entry.entry_id, "person", source=SOURCE_RECONFIGURE, subentry_id="v1"
        )
        assert _suggested(result, "name") == "Voksen 1"
        assert _suggested(result, "color") == [16, 32, 48]
        result = await _configure(
            hass,
            result["flow_id"],
            {
                "name": "Voksen 1",
                "person_entity": "person.voksen_1",
                "can_approve": True,
                "requires_approval": False,
                "active": False,
            },
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"
        assert not entry.runtime_data.persons["v1"].active
        assert entry.runtime_data.persons["v1"].color is None


def _main(*, without: tuple[str, ...] = (), **overrides: Any) -> dict[str, Any]:
    data = {
        "name": "Støvsug",
        "points": 3,
        "assignees": ["v2", "v1"],
        "assignment": "round_robin",
        "repeat": "weekly",
        "due_time": "17:30:00",
        "notify_before": {"hours": 0, "minutes": 30, "seconds": 0},
        "advanced": {"approval": "auto", "builtin_notify": False},
    }
    # Formularen udelader tomme, valgfrie felter.
    return {k: v for k, v in (data | overrides).items() if k not in without}


class TestChoreFlow:
    async def test_no_persons(self, hass, setup) -> None:
        coordinator = await setup({}, persons={})
        result = await _start(hass, coordinator.entry.entry_id, "chore")
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "no_persons"

    async def test_add_weekly(self, hass, setup) -> None:
        coordinator = await setup({})
        entry = coordinator.entry
        result = await _start(hass, entry.entry_id, "chore")
        assert result["step_id"] == "user"
        result = await _configure(hass, result["flow_id"], _main())
        assert result["step_id"] == "schedule_weekly"
        result = await _configure(hass, result["flow_id"], {"weekdays": ["mon", "thu"]})
        assert result["type"] is FlowResultType.CREATE_ENTRY

        coordinator = entry.runtime_data
        chore = next(c for c in coordinator.chores.values() if c.name == "Støvsug")
        assert chore.assignees == ("v2", "v1")
        assert chore.schedule.weekdays == (0, 3)
        assert chore.notify_before == timedelta(minutes=30)
        assert chore.points == 3
        assert _occ(coordinator, chore.id).next_due == _local(6, 11, 17, 30)

    async def test_add_one_off(self, hass, setup) -> None:
        coordinator = await setup({})
        entry = coordinator.entry
        result = await _start(hass, entry.entry_id, "chore")
        result = await _configure(
            hass, result["flow_id"], _main(repeat="none", without=("due_time", "notify_before"))
        )
        assert result["step_id"] == "schedule_none"
        result = await _configure(hass, result["flow_id"], {"due": "2026-06-12 09:00:00"})
        assert result["type"] is FlowResultType.CREATE_ENTRY
        chore = next(iter(entry.runtime_data.chores.values()))
        assert chore.schedule.due == _local(6, 12, 9)
        assert chore.due_time is None and chore.notify_before is None

    async def test_invalid_yearly_date_then_fixed(self, hass, setup) -> None:
        coordinator = await setup({})
        result = await _start(hass, coordinator.entry.entry_id, "chore")
        result = await _configure(hass, result["flow_id"], _main(repeat="yearly"))
        result = await _configure(hass, result["flow_id"], {"dates": ["02-29"]})
        assert result["errors"] == {"base": "invalid"}
        assert "02-29" in result["description_placeholders"]["error"]
        result = await _configure(hass, result["flow_id"], {"dates": ["03-01", " "]})
        assert result["type"] is FlowResultType.CREATE_ENTRY

    async def test_reconfigure_prefills_and_keeps_order(self, hass, setup) -> None:
        coordinator = await setup(
            {
                "c1": _chore(
                    assignees=["v2", "v1"],
                    schedule={"kind": "weekly", "weekdays": [1, 4]},
                    complete_window=3600,
                )
            }
        )
        entry = coordinator.entry
        result = await _start(
            hass, entry.entry_id, "chore", source=SOURCE_RECONFIGURE, subentry_id="c1"
        )
        assert _suggested(result, "name") == "Tøm opvaskemaskinen"
        assert _suggested(result, "repeat") == "weekly"
        assert _suggested(result, "complete_window", "advanced")["hours"] == 1

        # Personerne kommer tilbage i en anden rækkefølge fra formularen.
        result = await _configure(
            hass,
            result["flow_id"],
            _main(name="Tøm opvaskemaskinen", assignees=["b1", "v1", "v2"]),
        )
        assert result["step_id"] == "schedule_weekly"
        assert _suggested(result, "weekdays") == ["tue", "fri"]
        result = await _configure(hass, result["flow_id"], {"weekdays": ["tue"]})
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"

        chore = entry.runtime_data.chores["c1"]
        assert chore.assignees == ("v2", "v1", "b1")
        assert chore.schedule.weekdays == (1,)

    async def test_reconfigure_change_repeat(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        entry = coordinator.entry
        result = await _start(
            hass, entry.entry_id, "chore", source=SOURCE_RECONFIGURE, subentry_id="c1"
        )
        result = await _configure(hass, result["flow_id"], _main(repeat="interval"))
        # Samme type: felterne er udfyldt med de gamle værdier.
        assert _suggested(result, "every") == 1
        assert _suggested(result, "unit") == "day"
        result = await _configure(
            hass, result["flow_id"], {"every": 2, "unit": "week", "from": "completion"}
        )
        assert result["type"] is FlowResultType.ABORT
        schedule = entry.runtime_data.chores["c1"].schedule
        assert (schedule.every, schedule.unit.value, schedule.from_.value) == (
            2,
            "week",
            "completion",
        )
