"""Tests af entiteterne: todo-lister, pointsensorer og kalender."""

from __future__ import annotations

from typing import Any

import pytest

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.husopgaver.const import CONF_ALL_LIST, LogAction

from .test_coordinator import _chore, _local, _occ, _tick, setup  # noqa: F401

V1 = "todo.husopgaver_voksen_1"
V2 = "todo.husopgaver_voksen_2"
B1 = "todo.husopgaver_barn_1"
ALL = "todo.husopgaver_alle"
APPROVALS = "todo.husopgaver_godkendelse"


async def _items(hass: HomeAssistant, entity_id: str) -> list[dict[str, Any]]:
    result = await hass.services.async_call(
        "todo",
        "get_items",
        {},
        target={"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )
    return result[entity_id]["items"]


async def _update(hass, entity_id, item, user="user_v1", **fields) -> None:
    await hass.services.async_call(
        "todo",
        "update_item",
        {"item": item, **fields},
        target={"entity_id": entity_id},
        blocking=True,
        context=Context(user_id=user),
    )
    await hass.async_block_till_done()


class TestEntitiesCreated:
    async def test_default_entities(self, hass, setup) -> None:
        await setup({"c1": _chore()})
        for entity_id in (
            V1,
            V2,
            B1,
            APPROVALS,
            "sensor.husopgaver_voksen_1_point",
            "calendar.husopgaver",
        ):
            assert hass.states.get(entity_id) is not None, entity_id
        assert hass.states.get(ALL) is None

    async def test_all_list_option(self, hass, setup) -> None:
        await setup({"c1": _chore()}, options={CONF_ALL_LIST: True})
        assert hass.states.get(ALL) is not None


class TestPersonList:
    async def test_items_and_window(self, hass, setup) -> None:
        await setup(
            {
                "c1": _chore(),
                "c2": _chore(name="Ugentlig", schedule={"kind": "weekly", "weekdays": [0]}),
                "c3": _chore(name="Fredag", assignees=["v1"], schedule={"kind": "weekly", "weekdays": [4]}),
            }
        )
        items = await _items(hass, V1)
        # Mandag er uden for vinduet på 2 dage; fredag er inden for.
        assert [i["summary"] for i in items] == ["Tøm opvaskemaskinen", "Fredag"]
        assert items[0]["status"] == "needs_action"
        assert items[0]["due"] == "2026-06-10"
        assert items[0]["description"] == "2 point · Forfalden"
        assert hass.states.get(V1).state == "2"
        assert await _items(hass, V2) == []

    async def test_complete_credits_owner_and_undo(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore(assignment="each")})
        item = (await _items(hass, V2))[0]
        await _update(hass, V2, item["uid"], user="user_koekken", status="completed")
        log = coordinator.storage.log
        assert [(e.action, e.person_id, e.by_user) for e in log] == [
            (LogAction.COMPLETED, "v2", "user_koekken")
        ]
        # Dagens afkrydsning står som udført; fjernes fluebenet, fortrydes den.
        done = [i for i in await _items(hass, V2) if i["status"] == "completed"]
        assert len(done) == 1
        await _update(hass, V2, done[0]["uid"], status="needs_action")
        assert coordinator.storage.log[-1].action is LogAction.UNDONE
        assert _occ(coordinator, key="v2").next_due == _local(6, 10)

    async def test_double_check_is_noop(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        uid = (await _items(hass, V1))[0]["uid"]
        await _update(hass, V1, uid, status="completed")
        await _update(hass, V1, uid, status="completed")
        assert len(coordinator.storage.log) == 1

    async def test_too_early_shows_error(self, hass, setup, freezer) -> None:
        await setup({"c1": _chore(due_time="18:00", complete_window=600)})
        uid = (await _items(hass, V1))[0]["uid"]
        with pytest.raises(ServiceValidationError):
            await _update(hass, V1, uid, status="completed")

    async def test_new_item_becomes_one_off(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        await hass.services.async_call(
            "todo",
            "add_item",
            {"item": "Køb mælk", "due_datetime": "2026-06-10 16:00:00"},
            target={"entity_id": V2},
            blocking=True,
        )
        await hass.async_block_till_done()
        coordinator = coordinator.entry.runtime_data
        chore = next(c for c in coordinator.chores.values() if c.name == "Køb mælk")
        assert chore.points == 1 and chore.assignees == ("v2",)
        assert _occ(coordinator, chore.id).next_due == _local(6, 10, 16)
        summaries = [i["summary"] for i in await _items(hass, V2)]
        assert "Køb mælk" in summaries

        # En engangsopgave kan slettes fra listen.
        await hass.services.async_call(
            "todo", "remove_item", {"item": "Køb mælk"}, target={"entity_id": V2}, blocking=True
        )
        await hass.async_block_till_done()
        assert chore.id not in coordinator.entry.runtime_data.chores

    async def test_recurring_cannot_be_deleted(self, hass, setup) -> None:
        await setup({"c1": _chore()})
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                "todo",
                "remove_item",
                {"item": "Tøm opvaskemaskinen"},
                target={"entity_id": V1},
                blocking=True,
            )

    async def test_edit_due_and_name(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore(description="Også bestik")})
        item = (await _items(hass, V1))[0]
        assert item["description"] == "2 point · Forfalden\n\nOgså bestik"
        await _update(hass, V1, item["uid"], due_date="2026-06-11")
        assert _occ(coordinator).next_due == _local(6, 11)
        # Gentagelsen er uændret: rytmen følger stadig startdatoen.
        assert _occ(coordinator).anchor == _local(6, 10, 12).date()

        item = (await _items(hass, V1))[0]
        await _update(
            hass,
            V1,
            item["uid"],
            rename="Tøm og fyld opvaskemaskinen",
            description=f"{item['description']} og glas",
        )
        coordinator = coordinator.entry.runtime_data
        chore = coordinator.chores["c1"]
        assert chore.name == "Tøm og fyld opvaskemaskinen"
        assert chore.description == "Også bestik og glas"
        # Tilstanden overlever genindlæsningen.
        assert _occ(coordinator).next_due == _local(6, 11)


class TestAllList:
    async def test_complete_credits_assignee(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore()}, options={CONF_ALL_LIST: True})
        item = (await _items(hass, ALL))[0]
        assert item["summary"] == "Tøm opvaskemaskinen (Voksen 1)"
        await _update(hass, ALL, item["uid"], user="user_v2", status="completed")
        assert coordinator.storage.log[0].person_id == "v1"


class TestApprovalList:
    async def test_check_approves(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore(assignees=["b1", "v1"])})
        item = (await _items(hass, B1))[0]
        await _update(hass, B1, item["uid"], user="user_b1", status="completed")

        # Barnets liste viser afkrydsningen som afventende.
        done = [i for i in await _items(hass, B1) if i["status"] == "completed"]
        assert done[0]["description"] == "2 point · Afventer godkendelse"

        pending = await _items(hass, APPROVALS)
        assert [i["summary"] for i in pending] == ["Tøm opvaskemaskinen (Barn 1)"]
        with pytest.raises(ServiceValidationError):
            await _update(hass, APPROVALS, pending[0]["uid"], user="user_b1", status="completed")
        await _update(hass, APPROVALS, pending[0]["uid"], user="user_v1", status="completed")
        assert coordinator.storage.log[-1].action is LogAction.APPROVED
        assert await _items(hass, APPROVALS) == []


class TestPointsSensor:
    async def test_points_and_attributes(self, hass, setup, freezer) -> None:
        coordinator = await setup(
            {
                "c1": _chore(assignment="each", assignees=["v1", "b1"]),
                "c2": _chore(name="Gammel", assignees=["v1"], due_time="08:00", assignment="fixed"),
            }
        )
        coordinator.complete("c1", person_id="v1")
        coordinator.complete("c1", person_id="b1")  # afventer godkendelse
        await hass.async_block_till_done()
        state = hass.states.get("sensor.husopgaver_voksen_1_point")
        assert state.state == "2"
        assert state.attributes["unit_of_measurement"] == "point"
        assert state.attributes["month"] == 2
        assert state.attributes["all_time"] == 2
        assert state.attributes["since_settlement"] == 2
        assert state.attributes["completed_count"] == 1
        # "Gammel" kl. 08:00 var passeret ved oprettelsen, så første forfald er i morgen.
        assert state.attributes["overdue_count"] == 0
        barn = hass.states.get("sensor.husopgaver_barn_1_point")
        assert barn.state == "0" and barn.attributes["pending"] == 2

        coordinator.settle("v1")
        await hass.async_block_till_done()
        state = hass.states.get("sensor.husopgaver_voksen_1_point")
        assert state.attributes["since_settlement"] == 0
        assert state.state == "2"

        # Ny uge: mandag kl. 00:00 lokal tid.
        await _tick(hass, freezer, _local(6, 15))
        state = hass.states.get("sensor.husopgaver_voksen_1_point")
        assert state.state == "0"
        assert state.attributes["month"] == 2
        assert state.attributes["overdue_count"] == 2


class TestCalendar:
    async def _events(self, hass, days=7) -> list[dict[str, Any]]:
        result = await hass.services.async_call(
            "calendar",
            "get_events",
            {"start_date_time": _local(6, 10).isoformat(), "duration": {"days": days}},
            target={"entity_id": "calendar.husopgaver"},
            blocking=True,
            return_response=True,
        )
        return result["calendar.husopgaver"]["events"]

    async def test_recurring_expanded(self, hass, setup) -> None:
        await setup({"c1": _chore()})
        events = await self._events(hass)
        assert len(events) == 7
        assert events[0]["summary"] == "Tøm opvaskemaskinen (Voksen 1)"
        assert events[0]["start"] == "2026-06-10"
        # Ved rotation kendes de følgende personer ikke endnu.
        assert events[1]["summary"] == "Tøm opvaskemaskinen"

    async def test_fixed_with_time(self, hass, setup) -> None:
        await setup(
            {
                "c1": _chore(
                    assignment="fixed",
                    due_time="18:00",
                    schedule={"kind": "weekly", "weekdays": [2]},
                )
            }
        )
        events = await self._events(hass, days=14)
        assert [e["start"] for e in events] == [
            "2026-06-10T18:00:00+02:00",
            "2026-06-17T18:00:00+02:00",
        ]
        assert all(e["summary"] == "Tøm opvaskemaskinen (Voksen 1)" for e in events)
        assert events[0]["end"] == "2026-06-10T19:00:00+02:00"

    async def test_state_is_current_event(self, hass, setup) -> None:
        await setup({"c1": _chore()})
        state = hass.states.get("calendar.husopgaver")
        assert state.state == "on"
        assert state.attributes["message"] == "Tøm opvaskemaskinen (Voksen 1)"

    async def test_one_off_done_not_shown(self, hass, setup) -> None:
        coordinator = await setup(
            {"c1": _chore(schedule={"kind": "none", "due": _local(6, 10, 12).isoformat()})}
        )
        assert len(await self._events(hass)) == 1
        coordinator.complete("c1")
        assert await self._events(hass) == []

