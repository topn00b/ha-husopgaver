"""Tests af websocket-API'et og registreringen af dashboardkortet."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.core import HomeAssistant

from custom_components.husopgaver.frontend_card import (
    CARD_DIR,
    CARD_FILE,
    URL_BASE,
    async_register_card,
)
from custom_components.husopgaver.websocket import build_payload

from .test_coordinator import PERSONS, _chore, _local, _tick, setup  # noqa: F401


def _groups(payload) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for item in payload["items"]:
        groups.setdefault(item["group"], []).append(item["name"])
    return groups


async def test_groups(hass, setup) -> None:
    coordinator = await setup(
        {
            "c1": _chore(name="Dagligt"),
            "c2": _chore(name="Fredag", schedule={"kind": "weekly", "weekdays": [4]}),
            "c3": _chore(name="Mandag", schedule={"kind": "weekly", "weekdays": [0]}),
            "c4": _chore(name="Barnets", assignees=["b1"], assignment="fixed"),
            "c5": _chore(name="Kl. 18", due_time="18:00"),
        }
    )
    coordinator.complete("c4")  # afventer godkendelse
    payload = build_payload(coordinator, _local(6, 10, 12))
    assert _groups(payload) == {
        "pending": ["Barnets"],
        "today": ["Dagligt", "Kl. 18"],
        "upcoming": ["Fredag"],
        "later": ["Mandag"],
    }
    # Senere på dagen er "Kl. 18" overskredet; "Dagligt" er stadig i dag.
    late = _groups(build_payload(coordinator, _local(6, 10, 19, 30)))
    assert late["overdue"] == ["Kl. 18"]
    assert late["today"] == ["Dagligt"]
    # Et længere vindue gør mandag til "kommende".
    wide = _groups(build_payload(coordinator, _local(6, 10, 12), upcoming_days=7))
    assert wide["upcoming"] == ["Fredag", "Mandag"]
    assert payload["upcoming_days"] == 2


async def test_items_persons_and_done(hass, setup) -> None:
    coordinator = await setup(
        {"c1": _chore(assignment="each", assignees=["v1", "b1"], description="Også bestik")}
    )
    entry = coordinator.complete("c1", person_id="v1")
    coordinator.complete("c1", person_id="b1")
    payload = build_payload(coordinator, _local(6, 10, 12))
    done = [i for i in payload["items"] if i["group"] == "done"]
    assert done == [
        {
            "uid": f"log:{entry.id}",
            "group": "done",
            "chore_id": "c1",
            "name": "Tøm opvaskemaskinen",
            "description": "Også bestik",
            "key": "v1",
            "each": True,
            "open": False,
            "assignees": ["v1", "b1"],
            "person_id": "v1",
            "points": 2,
            "due": entry.timestamp.isoformat(),
            "has_time": True,
            "status": None,
            "condition_unknown": False,
            "log_id": entry.id,
        }
    ]
    pending = next(i for i in payload["items"] if i["group"] == "pending")
    assert pending["key"] == "b1" and pending["log_id"] is not None
    persons = {p["id"]: p for p in payload["persons"]}
    assert persons["v1"]["week_points"] == 2
    assert persons["b1"]["week_points"] == 0 and persons["b1"]["pending_points"] == 2
    assert [p["name"] for p in payload["persons"]] == [p["name"] for p in PERSONS.values()]

    coordinator.undo(log_id=entry.id)
    payload = build_payload(coordinator, _local(6, 10, 12))
    assert not [i for i in payload["items"] if i["group"] == "done"]


async def test_viewer(hass, setup) -> None:
    coordinator = await setup({"c1": _chore()})
    assert build_payload(coordinator, _local(6, 10, 12), user_id="user_v1")["viewer"] == {
        "person_id": "v1",
        "can_approve": True,
    }
    assert build_payload(coordinator, _local(6, 10, 12), user_id="user_b1")["viewer"] == {
        "person_id": "b1",
        "can_approve": False,
    }
    assert build_payload(coordinator, _local(6, 10, 12), user_id="user_koekken")[
        "viewer"
    ] == {"person_id": None, "can_approve": False}


async def test_occurrences_command(hass, setup, hass_ws_client, hass_admin_user) -> None:
    hass.states.async_set("person.voksen_2", "home", {"user_id": hass_admin_user.id})
    await setup({"c1": _chore()})
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "husopgaver/occurrences", "upcoming_days": 5})
    response = await client.receive_json()
    assert response["success"]
    result = response["result"]
    assert result["loaded"] and result["upcoming_days"] == 5
    assert result["version"] == "0.8.0"
    assert result["viewer"]["person_id"] == "v2"
    assert result["items"][0]["name"] == "Tøm opvaskemaskinen"


async def test_subscribe_updates_and_survives_reload(
    hass, setup, hass_ws_client
) -> None:
    coordinator = await setup({"c1": _chore()})
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "husopgaver/subscribe"})
    assert (await client.receive_json())["success"]
    first = await client.receive_json()
    assert first["type"] == "event"
    assert [i["group"] for i in first["event"]["items"]] == ["today"]

    await hass.services.async_call("husopgaver", "complete", {"chore": "c1"}, blocking=True)
    await hass.async_block_till_done()
    event = await client.receive_json()
    groups = [i["group"] for i in event["event"]["items"]]
    assert "done" in groups

    # En rettelse genindlæser integrationen; abonnementet fortsætter.
    entry = coordinator.entry
    hass.config_entries.async_update_subentry(
        entry, entry.subentries["c1"], data=_chore(name="Nyt navn")
    )
    await hass.async_block_till_done()
    names = set()
    while "Nyt navn" not in names:
        event = await client.receive_json()
        names = {i["name"] for i in event["event"]["items"]}


async def test_not_loaded(hass, hass_ws_client) -> None:
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "husopgaver", {})
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "husopgaver/occurrences"})
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "not_loaded"

    await client.send_json_auto_id({"type": "husopgaver/subscribe"})
    assert (await client.receive_json())["success"]
    event = await client.receive_json()
    assert event["event"]["loaded"] is False


async def test_card_file_is_shipped() -> None:
    assert (CARD_DIR / CARD_FILE).is_file()


async def test_card_not_registered_without_frontend(hass: HomeAssistant) -> None:
    assert not await async_register_card(hass)


async def test_card_registered_with_frontend(hass: HomeAssistant) -> None:
    hass.config.components.add("frontend")
    hass.http = Mock(async_register_static_paths=AsyncMock())
    with (
        patch("homeassistant.components.frontend.add_extra_js_url") as add_js,
        patch("homeassistant.components.panel_custom.async_register_panel") as panel,
    ):
        assert await async_register_card(hass)
    (config,) = hass.http.async_register_static_paths.call_args.args[0]
    assert config.url_path == URL_BASE and config.path == str(CARD_DIR)
    url = add_js.call_args.args[1]
    assert url.startswith(f"{URL_BASE}/{CARD_FILE}?v=")
    # Siden i sidemenuen for alle brugere, med samme modul.
    kwargs = panel.call_args.kwargs
    assert kwargs["frontend_url_path"] == "husopgaver"
    assert kwargs["webcomponent_name"] == "husopgaver-panel"
    assert kwargs["sidebar_title"] == "Husopgaver"
    assert kwargs["module_url"] == url
    assert kwargs["require_admin"] is False


async def test_midnight_moves_groups(hass, setup, freezer) -> None:
    coordinator = await setup(
        {"c1": _chore(name="Fredag", schedule={"kind": "weekly", "weekdays": [4]})}
    )
    assert _groups(build_payload(coordinator, _local(6, 10, 12))) == {"upcoming": ["Fredag"]}
    await _tick(hass, freezer, _local(6, 12) + timedelta(minutes=1))
    assert _groups(build_payload(coordinator, _local(6, 12, 0, 1))) == {"today": ["Fredag"]}


async def test_chore_configs_for_the_card(hass, setup) -> None:
    coordinator = await setup(
        {
            "c1": _chore(due_time="18:00", notify_before=1800, schedule={"kind": "weekly", "weekdays": [0, 3]}),
            "c2": _chore(name="Engang", schedule={"kind": "none", "due": _local(6, 12, 9).isoformat()}),
        }
    )
    chores = {c["id"]: c for c in build_payload(coordinator, _local(6, 10, 12))["chores"]}
    assert chores["c1"] == {
        "id": "c1",
        "name": "Tøm opvaskemaskinen",
        "description": None,
        "points": 2,
        "assignees": ["v1", "v2"],
        "assignment": "least_points",
        "repeat": "weekly",
        "every": None,
        "unit": None,
        "from": None,
        "weekdays": ["mon", "thu"],
        "dates": [],
        "after": None,
        "delay": 0,
        "due": None,
        "due_time": "18:00",
        "notify_before": 30,
        "approval": "auto",
        "has_condition": False,
    }
    assert chores["c2"]["due"] == "2026-06-12 09:00"
