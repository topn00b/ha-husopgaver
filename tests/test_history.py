"""Tests af historik og statistik."""

from __future__ import annotations

from datetime import timedelta

from custom_components.husopgaver.history import build_history

from .test_coordinator import START, _chore, _local, setup  # noqa: F401


async def _with_history(setup, freezer):
    coordinator = await setup(
        {
            "c1": _chore(name="Opvask", assignment="open", assignees=["v1", "v2", "b1"]),
            "c2": _chore(name="Støvsug", schedule={"kind": "interval", "every": 1, "unit": "day", "from": "completion"}),
        }
    )
    # Uge 1 (onsdag 10. juni).
    coordinator.complete("c1", person_id="v1")
    coordinator.complete("c2", person_id="v2")
    # Uge 2.
    freezer.move_to(_local(6, 16, 9))
    coordinator.complete("c1", person_id="v2")
    freezer.move_to(_local(6, 17, 9))
    pending = coordinator.complete("c1", person_id="b1")
    coordinator.approve(log_id=pending.id, user_id="user_v1")
    coordinator.skip("c2")
    # Fortrudt: tæller ikke.
    freezer.move_to(_local(6, 18, 9))
    coordinator.complete("c2", person_id="v1")
    coordinator.undo(chore_id="c2")
    coordinator.settle("b1")
    return coordinator


async def test_entries(hass, setup, freezer) -> None:
    coordinator = await _with_history(setup, freezer)
    result = build_history(coordinator, _local(6, 18, 12), days=30)
    actions = [(e["action"], e["chore_name"], e["person_id"], e["points"]) for e in result["entries"]]
    assert actions == [
        ("settled", None, "b1", 0),
        ("skipped", "Støvsug", "v1", 0),
        ("approved", "Opvask", "b1", 2),
        ("completed", "Opvask", "v2", 2),
        ("completed", "Støvsug", "v2", 2),
        ("completed", "Opvask", "v1", 2),
    ]
    only_b1 = build_history(coordinator, _local(6, 18, 12), days=30, person_id="b1")
    assert {e["person_id"] for e in only_b1["entries"]} == {"b1"}


async def test_weekly_stats(hass, setup, freezer) -> None:
    coordinator = await _with_history(setup, freezer)
    result = build_history(coordinator, _local(6, 18, 12), days=14)
    assert result["bucket"] == "week"
    assert result["buckets"] == [
        {"start": "2026-06-01", "points": {}},
        {"start": "2026-06-08", "points": {"v1": 2, "v2": 2}},
        {"start": "2026-06-15", "points": {"v2": 2, "b1": 2}},
    ]
    assert result["totals"] == {
        "v1": {"points": 2, "count": 1},
        "v2": {"points": 4, "count": 2},
        "b1": {"points": 2, "count": 1},
    }
    assert result["chores"][0] == {
        "chore_id": "c1",
        "chore_name": "Opvask",
        "counts": {"v1": 1, "v2": 1, "b1": 1},
        "total": 3,
    }


async def test_short_period_and_all_time(hass, setup, freezer) -> None:
    coordinator = await _with_history(setup, freezer)
    week = build_history(coordinator, _local(6, 18, 12), days=7)
    assert all(e["timestamp"] >= _local(6, 12).isoformat() for e in week["entries"])
    assert week["totals"]["v2"] == {"points": 2, "count": 1}
    everything = build_history(coordinator, _local(6, 18, 12), days=None)
    assert everything["bucket"] == "month"
    assert everything["buckets"] == [{"start": "2026-06-01", "points": {"v1": 2, "v2": 4, "b1": 2}}]


async def test_pending_shown_until_resolved(hass, setup, freezer) -> None:
    coordinator = await setup({"c1": _chore(assignees=["b1"], assignment="fixed")})
    coordinator.complete("c1")
    (entry,) = build_history(coordinator, START + timedelta(hours=1), days=7)["entries"]
    assert entry["action"] == "pending"


async def test_deleted_chore_kept(hass, setup, freezer) -> None:
    coordinator = await setup({"c1": _chore(name="Gammel")})
    coordinator.complete("c1")
    hass.config_entries.async_remove_subentry(coordinator.entry, "c1")
    await hass.async_block_till_done()
    coordinator = coordinator.entry.runtime_data
    (entry,) = build_history(coordinator, START, days=7)["entries"]
    assert entry["chore_name"] is None and entry["chore_id"] == "c1"


async def test_ws_command(hass, setup, hass_ws_client) -> None:
    coordinator = await setup({"c1": _chore()})
    coordinator.complete("c1")
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "husopgaver/history", "days": 30, "person": "v1"})
    response = await client.receive_json()
    assert response["success"]
    assert response["result"]["entries"][0]["action"] == "completed"
