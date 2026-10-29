"""Tests af opfølgende opgaver: vask tøj → hæng op → tag ned."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.husopgaver.const import LogAction, ScheduleKind
from custom_components.husopgaver.models import Chore

from .test_coordinator import START, _chore, _local, _occ, setup  # noqa: F401


def _laundry() -> dict[str, dict[str, Any]]:
    return {
        "vask": _chore(name="Vask tøj", schedule={"kind": "weekly", "weekdays": [2]}),
        "haeng": _chore(
            name="Hæng vasketøj op",
            assignment="open",
            assignees=["v1", "v2", "b1"],
            schedule={"kind": "after", "after": "vask", "delay": 0},
        ),
        "ned": _chore(
            name="Tag vasketøj ned",
            assignment="open",
            assignees=["v1", "v2", "b1"],
            due_time="17:00",
            schedule={"kind": "after", "after": "haeng", "delay": 86400},
        ),
    }


def test_model() -> None:
    chore = Chore.from_dict("haeng", _laundry()["haeng"])
    assert chore.schedule.kind is ScheduleKind.AFTER
    assert chore.schedule.after == "vask" and chore.schedule.delay == timedelta(0)
    assert Chore.from_dict("haeng", chore.to_dict()) == chore
    with pytest.raises(ValueError):
        Chore.from_dict("x", _chore(schedule={"kind": "after", "after": "x"}))
    with pytest.raises(ValueError):
        Chore.from_dict("x", _chore(schedule={"kind": "after"}))


async def test_chain(hass, setup, freezer) -> None:
    coordinator = await setup(_laundry())
    # Venter: ingen forfald, ikke på listerne.
    assert _occ(coordinator, "haeng").next_due is None
    assert {v.chore.id for v in coordinator.occurrences(START)} == {"vask"}

    coordinator.complete("vask")
    assert _occ(coordinator, "haeng").next_due == START
    assert _occ(coordinator, "ned").next_due is None

    freezer.move_to(_local(6, 10, 11))
    coordinator.complete("haeng", person_id="v2")
    # Dagen efter kl. 17.
    assert _occ(coordinator, "ned").next_due == _local(6, 11, 17)
    # Hæng op venter igen på næste vask.
    assert _occ(coordinator, "haeng").next_due is None

    freezer.move_to(_local(6, 11, 17, 30))
    coordinator.complete("ned", person_id="b1")  # barn: afventer godkendelse
    assert _occ(coordinator, "ned").pending_log_id is not None
    coordinator.approve(chore_id="ned", user_id="user_v1")
    assert _occ(coordinator, "ned").next_due is None


async def test_waiting_followup_is_not_moved(hass, setup, freezer) -> None:
    coordinator = await setup(_laundry())
    coordinator.complete("vask")
    first = _occ(coordinator, "haeng").next_due
    freezer.move_to(_local(6, 17, 10))
    coordinator.complete("vask")
    assert _occ(coordinator, "haeng").next_due == first


async def test_skip_does_not_trigger(hass, setup) -> None:
    coordinator = await setup(_laundry())
    coordinator.skip("vask")
    assert _occ(coordinator, "haeng").next_due is None


async def test_undo_withdraws_followup(hass, setup, freezer) -> None:
    coordinator = await setup(_laundry())
    coordinator.complete("vask")
    assert _occ(coordinator, "haeng").next_due is not None
    freezer.move_to(START + timedelta(minutes=2))
    coordinator.undo(chore_id="vask")
    assert _occ(coordinator, "haeng").next_due is None
    assert coordinator.storage.log[-1].action is LogAction.UNDONE


async def test_approval_triggers_from_completion_time(hass, setup, freezer) -> None:
    data = _laundry()
    data["vask"] = data["vask"] | {"assignees": ["b1"], "assignment": "fixed"}
    coordinator = await setup(data)
    coordinator.complete("vask")
    assert _occ(coordinator, "haeng").next_due is None  # ikke før godkendelse
    freezer.move_to(START + timedelta(hours=2))
    coordinator.approve(chore_id="vask", user_id="user_v1")
    assert _occ(coordinator, "haeng").next_due == START


async def test_service_create(hass, setup) -> None:
    coordinator = await setup({"vask": _laundry()["vask"]})
    result = await hass.services.async_call(
        "husopgaver",
        "create_chore",
        {
            "name": "Hæng vasketøj op",
            "assignees": ["v1", "v2"],
            "assignment": "open",
            "repeat": "after",
            "after": "Vask tøj",
            "delay": {"hours": 1},
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    chore = coordinator.entry.runtime_data.chores[result["chore_id"]]
    assert chore.schedule.after == "vask"
    assert chore.schedule.delay == timedelta(hours=1)


async def test_config_flow(hass, setup) -> None:
    coordinator = await setup({"vask": _laundry()["vask"]})
    entry = coordinator.entry
    flow = hass.config_entries.subentries
    result = await flow.async_init((entry.entry_id, "chore"), context={"source": SOURCE_USER})
    result = await flow.async_configure(
        result["flow_id"],
        {
            "name": "Hæng vasketøj op",
            "points": 1,
            "assignees": ["v1"],
            "assignment": "fixed",
            "repeat": "after",
            "advanced": {"approval": "auto", "builtin_notify": False, "condition": "none"},
        },
    )
    assert result["step_id"] == "schedule_after"
    result = await flow.async_configure(result["flow_id"], {"after": "vask"})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    chore = next(c for c in entry.runtime_data.chores.values() if c.name == "Hæng vasketøj op")
    assert chore.schedule.after == "vask" and chore.schedule.delay == timedelta(0)
