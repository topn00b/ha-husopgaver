"""Tests af "den, der har tid": ingen navn på; den, der krydser af, får pointene."""

from __future__ import annotations

from typing import Any

import pytest

from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError

from custom_components.husopgaver.const import EVENT_DUE, LogAction
from custom_components.husopgaver.points import credited_entries, sum_points
from custom_components.husopgaver.websocket import build_payload

from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    async_mock_service,
)

from .test_coordinator import _chore, _local, _occ, _tick, setup  # noqa: F401


def _open(**overrides: Any) -> dict[str, Any]:
    return _chore(assignment="open", assignees=["v1", "v2", "b1"]) | overrides


async def _items(hass, entity_id: str) -> list[dict[str, Any]]:
    result = await hass.services.async_call(
        "todo", "get_items", {}, target={"entity_id": entity_id}, blocking=True, return_response=True
    )
    return result[entity_id]["items"]


async def test_no_assignee_and_on_everyones_list(hass, setup) -> None:
    coordinator = await setup({"c1": _open()})
    assert _occ(coordinator).assignee is None
    for entity_id in ("todo.husopgaver_voksen_1", "todo.husopgaver_voksen_2", "todo.husopgaver_barn_1"):
        assert [i["summary"] for i in await _items(hass, entity_id)] == ["Tøm opvaskemaskinen"]


async def test_whoever_completes_gets_points_and_it_stays_open(hass, setup, freezer) -> None:
    coordinator = await setup({"c1": _open()})
    coordinator.complete("c1", person_id="v2")
    credited = credited_entries(coordinator.storage.log)
    assert sum_points(credited, "v2") == 2
    occ = _occ(coordinator)
    assert occ.assignee is None
    assert occ.next_due == _local(6, 11)


async def test_complete_without_person_asks_who(hass, setup) -> None:
    coordinator = await setup({"c1": _open()})
    with pytest.raises(ServiceValidationError) as err:
        coordinator.complete("c1")
    assert err.value.translation_key == "who_did_it"


async def test_own_list_credits_owner(hass, setup) -> None:
    coordinator = await setup({"c1": _open()})
    uid = (await _items(hass, "todo.husopgaver_voksen_2"))[0]["uid"]
    await hass.services.async_call(
        "todo",
        "update_item",
        {"item": uid, "status": "completed"},
        target={"entity_id": "todo.husopgaver_voksen_2"},
        blocking=True,
        context=Context(user_id="user_koekken"),
    )
    assert coordinator.storage.log[0].person_id == "v2"
    # Afkrydsningen står som udført på den lagde liste, ikke de andres.
    done = [i for i in await _items(hass, "todo.husopgaver_voksen_2") if i["status"] == "completed"]
    assert len(done) == 1
    assert not [i for i in await _items(hass, "todo.husopgaver_voksen_1") if i["status"] == "completed"]


@pytest.mark.parametrize(("user", "expected"), [("user_v1", "v1"), ("user_koekken", None)])
async def test_all_list_credits_logged_in_person(hass, setup, user, expected) -> None:
    coordinator = await setup({"c1": _open()}, options={"all_list": True})
    item = (await _items(hass, "todo.husopgaver_alle"))[0]
    assert item["summary"] == "Tøm opvaskemaskinen"
    call = hass.services.async_call(
        "todo",
        "update_item",
        {"item": item["uid"], "status": "completed"},
        target={"entity_id": "todo.husopgaver_alle"},
        blocking=True,
        context=Context(user_id=user),
    )
    if expected is None:
        with pytest.raises(ServiceValidationError):
            await call
        assert coordinator.storage.log == ()
    else:
        await call
        assert coordinator.storage.log[0].person_id == expected


async def test_skip_and_reassign(hass, setup) -> None:
    coordinator = await setup({"c1": _open()})
    entry = coordinator.skip("c1")
    assert entry.action is LogAction.SKIPPED and entry.person_id is None
    with pytest.raises(ServiceValidationError):
        coordinator.reassign("c1", "v1")


async def test_child_completing_needs_approval(hass, setup) -> None:
    coordinator = await setup({"c1": _open()})
    entry = coordinator.complete("c1", person_id="b1")
    assert entry.action is LogAction.PENDING


async def test_notifications_go_to_everyone(hass, setup, freezer) -> None:
    dues = async_capture_events(hass, EVENT_DUE)
    calls = async_mock_service(hass, "notify", "mobile_app_voksen_1")
    await setup({"c1": _open(due_time="18:00", builtin_notify=True)})
    await _tick(hass, freezer, _local(6, 10, 18))
    assert dues[0].data["person_id"] is None
    assert len(calls) == 1  # kun Voksen 1 har et notify-mål


async def test_card_payload(hass, setup) -> None:
    coordinator = await setup({"c1": _open()})
    (item,) = build_payload(coordinator, _local(6, 10, 12))["items"]
    assert item["open"] is True
    assert item["person_id"] is None
    assert item["assignees"] == ["v1", "v2", "b1"]


async def test_overdue_counts_for_everyone_on_it(hass, setup, freezer) -> None:
    await setup({"c1": _open(due_time="08:00")})
    await _tick(hass, freezer, _local(6, 12))
    for sensor in ("sensor.husopgaver_voksen_1_point", "sensor.husopgaver_barn_1_point"):
        assert hass.states.get(sensor).attributes["overdue_count"] == 1
