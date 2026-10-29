"""Tests af services: opslag af opgaver og personer, handlinger og CRUD."""

from __future__ import annotations

from datetime import time, timedelta
from typing import Any

import pytest

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.husopgaver.const import DOMAIN, LogAction, ScheduleKind

from .test_coordinator import START, _chore, _local, _occ, setup  # noqa: F401


async def _call(
    hass: HomeAssistant, service: str, user: str | None = "user_v1", **data: Any
) -> Any:
    result = await hass.services.async_call(
        DOMAIN,
        service,
        data,
        blocking=True,
        return_response=service
        in {"complete", "skip", "approve", "reject", "undo", "settle", "create_chore"},
        context=Context(user_id=user),
    )
    await hass.async_block_till_done()
    return result


class TestLookup:
    @pytest.mark.parametrize(
        "ref", ["c1", "tøm OPVASKEMASKINEN", "c1|_shared|2026-06-09T22:00:00+00:00"]
    )
    async def test_chore_by_id_name_or_item(self, hass, setup, ref) -> None:
        coordinator = await setup({"c1": _chore()})
        result = await _call(hass, "complete", chore=ref)
        assert result["log_id"] == coordinator.storage.log[0].id

    @pytest.mark.parametrize("ref", ["v2", "voksen 2", "person.voksen_2"])
    async def test_person_by_id_name_or_entity(self, hass, setup, ref) -> None:
        coordinator = await setup({"c1": _chore()})
        await _call(hass, "complete", chore="c1", person=ref)
        assert coordinator.storage.log[0].person_id == "v2"

    async def test_unknown_and_ambiguous(self, hass, setup) -> None:
        await setup({"c1": _chore(), "c2": _chore()})
        with pytest.raises(ServiceValidationError) as err:
            await _call(hass, "complete", chore="Findes ikke")
        assert err.value.translation_key == "unknown_chore"
        with pytest.raises(ServiceValidationError) as err:
            await _call(hass, "complete", chore="Tøm opvaskemaskinen")
        assert err.value.translation_key == "ambiguous_chore"
        with pytest.raises(ServiceValidationError) as err:
            await _call(hass, "complete", chore="c1", person="Nabo")
        assert err.value.translation_key == "unknown_person"

    async def test_not_loaded(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        await hass.config_entries.async_unload(coordinator.entry.entry_id)
        with pytest.raises(ServiceValidationError) as err:
            await _call(hass, "complete", chore="c1")
        assert err.value.translation_key == "not_loaded"


class TestActions:
    async def test_complete_without_response(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        await hass.services.async_call(DOMAIN, "complete", {"chore": "c1"}, blocking=True)
        assert len(coordinator.storage.log) == 1

    async def test_double_complete_returns_no_log(self, hass, setup) -> None:
        await setup({"c1": _chore(schedule={"kind": "none", "due": _local(6, 10, 12).isoformat()})})
        await _call(hass, "complete", chore="c1")
        assert await _call(hass, "complete", chore="c1") == {"log_id": None}

    async def test_skip_reassign_snooze(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore(assignment="round_robin")})
        result = await _call(hass, "skip", chore="c1")
        assert coordinator.storage.get_log_entry(result["log_id"]).action is LogAction.SKIPPED
        await _call(hass, "reassign", chore="c1", person="Voksen 1")
        assert _occ(coordinator).assignee == "v1"
        await _call(hass, "snooze", chore="c1", duration={"days": 2})
        assert _occ(coordinator).snoozed_until == START + timedelta(days=2)

    async def test_approval_flow(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore(assignees=["b1", "v1"])})
        await _call(hass, "complete", user="user_b1", chore="c1")
        with pytest.raises(ServiceValidationError) as err:
            await _call(hass, "approve", user="user_b1", chore="c1")
        assert err.value.translation_key == "not_approver"
        with pytest.raises(ServiceValidationError) as err:
            await _call(hass, "approve", user=None, chore="c1")
        assert err.value.translation_key == "not_approver"
        result = await _call(hass, "approve", user="user_v2", chore="Tøm opvaskemaskinen")
        entry = coordinator.storage.get_log_entry(result["log_id"])
        assert entry.action is LogAction.APPROVED and entry.by_user == "user_v2"

        undone = await _call(hass, "undo", chore="c1")
        assert coordinator.storage.get_log_entry(undone["log_id"]).ref == entry.id
        rejected = await _call(hass, "reject", log_id=coordinator.storage.log[0].id)
        assert coordinator.storage.get_log_entry(rejected["log_id"]).action is (
            LogAction.REJECTED
        )

    async def test_approve_needs_log_id_or_chore(self, hass, setup) -> None:
        await setup({"c1": _chore()})
        with pytest.raises(Exception, match="at least one"):
            await _call(hass, "approve")

    async def test_settle(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        result = await _call(hass, "settle", person="Barn 1")
        entry = coordinator.storage.get_log_entry(result["log_id"])
        assert entry.action is LogAction.SETTLED and entry.person_id == "b1"


class TestChoreCrud:
    async def test_create_weekly(self, hass, setup) -> None:
        coordinator = await setup({})
        result = await _call(
            hass,
            "create_chore",
            name="Støvsug",
            assignees=["Voksen 2", "person.voksen_1"],
            assignment="round_robin",
            repeat="weekly",
            weekdays=["mon", "thu"],
            due_time="17:30",
            notify_before={"minutes": 30},
            points=3,
        )
        coordinator = coordinator.entry.runtime_data
        chore = coordinator.chores[result["chore_id"]]
        assert chore.name == "Støvsug"
        assert chore.assignees == ("v2", "v1")
        assert chore.schedule.weekdays == (0, 3)
        assert chore.due_time == time(17, 30)
        assert chore.notify_before == timedelta(minutes=30)
        assert chore.points == 3
        # Torsdag 11. juni kl. 17:30, hos den første på skift.
        occ = _occ(coordinator, chore.id)
        assert occ.next_due == _local(6, 11, 17, 30)
        assert occ.assignee == "v2"

    async def test_create_one_off(self, hass, setup) -> None:
        coordinator = await setup({})
        result = await _call(
            hass,
            "create_chore",
            name="Ring til frisøren",
            assignees=["v1"],
            repeat="none",
            due="2026-06-12 09:00:00",
        )
        chore = coordinator.entry.runtime_data.chores[result["chore_id"]]
        assert chore.schedule.due == _local(6, 12, 9)

    @pytest.mark.parametrize(
        "fields",
        [
            {"repeat": "none"},  # engangsopgave uden forfald
            {"repeat": "interval"},  # interval uden "every" og "unit"
            {"repeat": "yearly", "dates": ["02-29"]},
        ],
    )
    async def test_create_invalid(self, hass, setup, fields) -> None:
        await setup({})
        with pytest.raises(ServiceValidationError) as err:
            await _call(hass, "create_chore", name="X", assignees=["v1"], **fields)
        assert err.value.translation_key == "invalid_chore"

    async def test_update_only_given_fields(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore(description="Også bestik")})
        await _call(hass, "update_chore", chore="c1", points=5)
        chore = coordinator.entry.runtime_data.chores["c1"]
        assert chore.points == 5
        assert chore.description == "Også bestik"
        assert chore.schedule.kind is ScheduleKind.INTERVAL

    async def test_update_repeat(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        await _call(hass, "update_chore", chore="c1", repeat="yearly", dates=["12-24"])
        coordinator = coordinator.entry.runtime_data
        assert coordinator.chores["c1"].schedule.dates == ((12, 24),)
        assert _occ(coordinator).next_due == _local(12, 24)

    async def test_delete(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        await _call(hass, "complete", chore="c1")
        await _call(hass, "delete_chore", chore="Tøm opvaskemaskinen")
        coordinator = coordinator.entry.runtime_data
        assert coordinator.chores == {}
        assert len(coordinator.storage.log) == 1


class TestFromTheCard:
    """Præcis de kald, kortets formular laver (se tests/js/form.test.mjs)."""

    async def test_create_weekdays_with_time_and_reminder(self, hass, setup) -> None:
        coordinator = await setup({})
        result = await _call(
            hass,
            "create_chore",
            name="Støvsug",
            assignees=["v1", "v2"],
            points=1,
            assignment="round_robin",
            description=None,
            due_time="18:00:00",
            notify_before={"minutes": 30},
            approval="auto",
            repeat="weekly",
            weekdays=["mon", "thu"],
        )
        chore = coordinator.entry.runtime_data.chores[result["chore_id"]]
        assert chore.schedule.weekdays == (0, 3)
        assert chore.notify_before == timedelta(minutes=30)
        assert chore.due_time == time(18)

    async def test_create_once(self, hass, setup) -> None:
        coordinator = await setup({})
        result = await _call(
            hass,
            "create_chore",
            name="Ring til frisøren",
            assignees=["v1"],
            points=1,
            assignment="fixed",
            description=None,
            due_time=None,
            notify_before=None,
            approval="auto",
            repeat="none",
            due="2026-06-12 00:00:00",
        )
        chore = coordinator.entry.runtime_data.chores[result["chore_id"]]
        assert chore.schedule.due == _local(6, 12)
        assert chore.due_time is None

    async def test_update_keeps_condition(self, hass, setup) -> None:
        condition = {"kind": "entity", "entity": "input_boolean.hjemme", "check_time": "14:00"}
        coordinator = await setup({"c1": _chore(condition=condition)})
        await _call(
            hass,
            "update_chore",
            chore="c1",
            name="Aftensmad",
            assignees=["v2", "v1"],
            points=3,
            assignment="least_points",
            description=None,
            due_time="18:00:00",
            notify_before=None,
            approval="auto",
            repeat="interval",
            every=2,
            unit="week",
            **{"from": "due"},
        )
        chore = coordinator.entry.runtime_data.chores["c1"]
        assert chore.name == "Aftensmad" and chore.points == 3
        assert chore.assignees == ("v2", "v1")
        assert chore.condition is not None
