"""Tests af koordinatoren: tildeling, events, timere, godkendelse og fortryd."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
    async_mock_service,
)

from homeassistant.config_entries import ConfigEntryState, ConfigSubentryDataWithId
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.husopgaver.const import (
    DOMAIN,
    EVENT_APPROVAL_REQUESTED,
    EVENT_COMPLETED,
    EVENT_DUE,
    EVENT_OVERDUE,
    EVENT_REJECTED,
    EVENT_REMINDER,
    EVENT_SKIPPED,
    SHARED_OCCURRENCE,
    ChoreStatus,
    LogAction,
)
from custom_components.husopgaver.coordinator import HusopgaverCoordinator
from custom_components.husopgaver.points import credited_entries, sum_points

CPH = ZoneInfo("Europe/Copenhagen")
# Onsdag 10. juni 2026 kl. 10:00 lokal tid.
START = datetime(2026, 6, 10, 10, 0, tzinfo=CPH)

PERSONS: dict[str, dict[str, Any]] = {
    "v1": {
        "name": "Voksen 1",
        "person_entity": "person.voksen_1",
        "notify_target": "notify.mobile_app_voksen_1",
        "can_approve": True,
    },
    "v2": {"name": "Voksen 2", "person_entity": "person.voksen_2", "can_approve": True},
    "b1": {"name": "Barn 1", "person_entity": "person.barn_1", "requires_approval": True},
}
USERS = {"v1": "user_v1", "v2": "user_v2", "b1": "user_b1", "koekken": "user_koekken"}


def _local(month, day, hour=0, minute=0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=CPH).astimezone(UTC)


def _chore(**overrides) -> dict[str, Any]:
    data = {
        "name": "Tøm opvaskemaskinen",
        "points": 2,
        "assignees": ["v1", "v2"],
        "assignment": "least_points",
        "schedule": {"kind": "interval", "every": 1, "unit": "day", "from": "due"},
    }
    return data | overrides


def _subentries(persons, chores) -> list[ConfigSubentryDataWithId]:
    return [
        ConfigSubentryDataWithId(
            data=data, subentry_id=sid, subentry_type=kind, title=data["name"], unique_id=None
        )
        for kind, items in (("person", persons), ("chore", chores))
        for sid, data in items.items()
    ]


@pytest.fixture
async def setup(hass: HomeAssistant, copenhagen, freezer: FrozenDateTimeFactory):
    freezer.move_to(START)
    for pid, user in USERS.items():
        if pid in PERSONS:
            hass.states.async_set(
                PERSONS[pid]["person_entity"], "home", {"user_id": user}
            )

    async def _setup(chores, persons=PERSONS, options=None) -> HusopgaverCoordinator:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Husopgaver",
            options=options or {},
            subentries_data=_subentries(persons, chores),
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        return entry.runtime_data

    return _setup


def _occ(coordinator: HusopgaverCoordinator, chore_id="c1", key=SHARED_OCCURRENCE):
    return coordinator.storage.chore_states[chore_id].occurrences[key]


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: datetime):
    freezer.move_to(when)
    async_fire_time_changed(hass, when)
    await hass.async_block_till_done()


class TestSetup:
    async def test_first_due_and_assignment(self, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        occ = _occ(coordinator)
        assert occ.next_due == _local(6, 10)
        assert occ.assignee == "v1"
        assert occ.anchor == START.date()

    async def test_each_has_one_occurrence_per_active_person(self, setup) -> None:
        persons = PERSONS | {"b2": {"name": "Barn 2", "active": False}}
        coordinator = await setup(
            {"c1": _chore(assignment="each", assignees=["b1", "b2", "v1"])}, persons
        )
        occurrences = coordinator.storage.chore_states["c1"].occurrences
        assert set(occurrences) == {"b1", "v1"}
        assert occurrences["b1"].assignee == "b1"

    async def test_absent_person_not_assigned(
        self, hass, setup, freezer: FrozenDateTimeFactory
    ) -> None:
        freezer.move_to(START - timedelta(hours=30))
        hass.states.async_set("person.voksen_1", "not_home", {"user_id": "user_v1"})
        freezer.move_to(START)
        coordinator = await setup({"c1": _chore()})
        assert _occ(coordinator).assignee == "v2"

    async def test_invalid_chore_fails_setup(self, hass, setup) -> None:
        entry = MockConfigEntry(
            domain=DOMAIN,
            subentries_data=_subentries(PERSONS, {"c1": _chore(assignees=[])}),
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        assert entry.state is ConfigEntryState.SETUP_ERROR

    async def test_schedule_change_recomputes_due(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        entry = coordinator.entry
        subentry = entry.subentries["c1"]
        hass.config_entries.async_update_subentry(
            entry,
            subentry,
            data=_chore(schedule={"kind": "weekly", "weekdays": [4]}),
        )
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        # Næste fredag.
        assert _occ(coordinator).next_due == _local(6, 12)
        assert _occ(coordinator).assignee == "v1"

    async def test_deleted_chore_state_removed_log_kept(self, hass, setup) -> None:
        coordinator = await setup({"c1": _chore(), "c2": _chore(name="Støvsug")})
        coordinator.complete("c2")
        entry = coordinator.entry
        hass.config_entries.async_remove_subentry(entry, "c2")
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        assert set(coordinator.storage.chore_states) == {"c1"}
        assert len(coordinator.storage.log) == 1


class TestComplete:
    async def test_complete_advances_and_rotates(self, hass, setup) -> None:
        events = async_capture_events(hass, EVENT_COMPLETED)
        coordinator = await setup({"c1": _chore()})
        entry = coordinator.complete("c1", user_id="user_v1")
        assert entry is not None and entry.action is LogAction.COMPLETED
        assert entry.person_id == "v1" and entry.points == 2

        occ = _occ(coordinator)
        assert occ.next_due == _local(6, 11)
        # Voksen 1 har nu 2 point, så Voksen 2 får den næste.
        assert occ.assignee == "v2"

        await hass.async_block_till_done()
        assert len(events) == 1
        assert events[0].data == {
            "chore_id": "c1",
            "chore_name": "Tøm opvaskemaskinen",
            "person_id": "v1",
            "person_name": "Voksen 1",
            "person_entity": "person.voksen_1",
            "notify_target": "notify.mobile_app_voksen_1",
            "points": 2,
            "due": _local(6, 10).isoformat(),
            "log_id": entry.id,
        }

    async def test_other_person_gets_the_points(self, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        entry = coordinator.complete("c1", person_id="v2")
        assert entry is not None and entry.person_id == "v2"
        assert _occ(coordinator).assignee == "v1"

    async def test_double_complete_is_noop(self, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        due = _occ(coordinator).next_due
        assert coordinator.complete("c1", expected_due=due) is not None
        assert coordinator.complete("c1", expected_due=due) is None
        assert len(coordinator.storage.log) == 1

    async def test_one_off_done_then_noop(self, setup) -> None:
        coordinator = await setup(
            {"c1": _chore(schedule={"kind": "none", "due": _local(6, 10, 12).isoformat()})}
        )
        assert coordinator.complete("c1") is not None
        assert _occ(coordinator).next_due is None
        assert coordinator.complete("c1") is None

    async def test_too_early(self, setup) -> None:
        coordinator = await setup(
            {"c1": _chore(schedule={"kind": "weekly", "weekdays": [0]})}
        )
        # Næste mandag er om 5 dage; vinduet for "kommende" er 2 dage.
        with pytest.raises(ServiceValidationError) as err:
            coordinator.complete("c1")
        assert err.value.translation_key == "too_early"

    async def test_complete_window(self, setup, freezer) -> None:
        coordinator = await setup(
            {"c1": _chore(due_time="18:00", complete_window=3600)}
        )
        with pytest.raises(ServiceValidationError):
            coordinator.complete("c1")
        freezer.move_to(_local(6, 10, 17))
        assert coordinator.complete("c1") is not None

    async def test_each_requires_person(self, setup) -> None:
        coordinator = await setup({"c1": _chore(assignment="each")})
        with pytest.raises(ServiceValidationError) as err:
            coordinator.complete("c1")
        assert err.value.translation_key == "person_required"
        assert coordinator.complete("c1", person_id="v2") is not None
        assert _occ(coordinator, key="v2").next_due == _local(6, 11)
        assert _occ(coordinator, key="v1").next_due == _local(6, 10)

    async def test_unknown_chore(self, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        with pytest.raises(ServiceValidationError) as err:
            coordinator.complete("findes_ikke")
        assert err.value.translation_key == "unknown_chore"


class TestApproval:
    async def _pending(self, setup):
        coordinator = await setup({"c1": _chore(assignees=["b1", "v1"])})
        assert _occ(coordinator).assignee == "b1"
        pending = coordinator.complete("c1")
        assert pending is not None and pending.action is LogAction.PENDING
        return coordinator, pending

    async def test_pending_gives_no_points(self, hass, setup) -> None:
        events = async_capture_events(hass, EVENT_APPROVAL_REQUESTED)
        coordinator, pending = await self._pending(setup)
        occ = _occ(coordinator)
        assert occ.pending_log_id == pending.id
        assert coordinator.status(coordinator.chores["c1"], occ, START) is (
            ChoreStatus.PENDING_APPROVAL
        )
        assert credited_entries(coordinator.storage.log) == []
        assert coordinator.complete("c1") is None  # allerede krydset af
        await hass.async_block_till_done()
        assert events[0].data["log_id"] == pending.id

    @pytest.mark.parametrize("user_id", [None, "user_koekken", "user_b1"])
    async def test_unauthorized_cannot_approve(self, setup, user_id) -> None:
        coordinator, pending = await self._pending(setup)
        with pytest.raises(ServiceValidationError) as err:
            coordinator.approve(log_id=pending.id, user_id=user_id)
        assert err.value.translation_key == "not_approver"

    async def test_approve(self, hass, setup, freezer) -> None:
        events = async_capture_events(hass, EVENT_COMPLETED)
        coordinator, pending = await self._pending(setup)
        freezer.move_to(_local(6, 11, 9))
        approved = coordinator.approve(chore_id="c1", user_id="user_v2")
        assert approved.ref == pending.id and approved.by_user == "user_v2"
        credited = credited_entries(coordinator.storage.log)
        assert sum_points(credited, "b1") == 2
        occ = _occ(coordinator)
        assert occ.pending_log_id is None
        # Onsdagens opgave er lavet; torsdagens er forfalden, selvom godkendelsen kom torsdag.
        assert occ.next_due == _local(6, 11)
        await hass.async_block_till_done()
        assert events[0].data["person_id"] == "b1"

    async def test_reject(self, hass, setup) -> None:
        events = async_capture_events(hass, EVENT_REJECTED)
        coordinator, pending = await self._pending(setup)
        coordinator.reject(log_id=pending.id, user_id="user_v1")
        occ = _occ(coordinator)
        assert occ.pending_log_id is None
        assert occ.next_due == _local(6, 10)
        assert occ.assignee == "b1"
        assert credited_entries(coordinator.storage.log) == []
        await hass.async_block_till_done()
        assert len(events) == 1

    async def test_approve_twice_fails(self, setup) -> None:
        coordinator, pending = await self._pending(setup)
        coordinator.approve(log_id=pending.id, user_id="user_v1")
        with pytest.raises(ServiceValidationError) as err:
            coordinator.approve(log_id=pending.id, user_id="user_v1")
        assert err.value.translation_key == "not_pending"

    async def test_builtin_notify_with_buttons(self, hass, setup) -> None:
        calls = async_mock_service(hass, "notify", "mobile_app_voksen_1")
        coordinator = await setup(
            {"c1": _chore(assignees=["b1", "v1"], builtin_notify=True)}
        )
        pending = coordinator.complete("c1")
        await hass.async_block_till_done()
        assert len(calls) == 1
        actions = calls[0].data["data"]["actions"]
        assert actions[0]["action"] == f"HUSOPGAVER_APPROVE_{pending.id}"

        # Knappen på telefonen er logget ind som Voksen 1.
        hass.bus.async_fire(
            "mobile_app_notification_action",
            {"action": actions[0]["action"]},
            context=Context(user_id="user_v1"),
        )
        await hass.async_block_till_done()
        assert _occ(coordinator).pending_log_id is None
        assert sum_points(credited_entries(coordinator.storage.log), "b1") == 2
        # Notifikationen ryddes hos de voksne.
        assert calls[-1].data["message"] == "clear_notification"

    async def test_notification_button_from_child_is_refused(self, hass, setup) -> None:
        coordinator, pending = await self._pending(setup)
        hass.bus.async_fire(
            "mobile_app_notification_action",
            {"action": f"HUSOPGAVER_APPROVE_{pending.id}"},
            context=Context(user_id="user_b1"),
        )
        await hass.async_block_till_done()
        assert _occ(coordinator).pending_log_id == pending.id


class TestUndo:
    async def test_undo_restores_everything(self, setup, freezer) -> None:
        coordinator = await setup({"c1": _chore(assignment="round_robin")})
        before = coordinator.storage.chore_states["c1"]
        entry = coordinator.complete("c1")
        assert coordinator.storage.chore_states["c1"] != before
        freezer.move_to(START + timedelta(minutes=9))
        undone = coordinator.undo(chore_id="c1")
        assert undone.ref == entry.id
        assert coordinator.storage.chore_states["c1"] == before
        assert credited_entries(coordinator.storage.log) == []

    async def test_undo_expired(self, setup, freezer) -> None:
        coordinator = await setup({"c1": _chore()})
        coordinator.complete("c1")
        freezer.move_to(START + timedelta(minutes=11))
        with pytest.raises(ServiceValidationError) as err:
            coordinator.undo(chore_id="c1")
        assert err.value.translation_key == "undo_expired"

    async def test_undo_only_latest(self, setup, freezer) -> None:
        coordinator = await setup({"c1": _chore()})
        first = coordinator.complete("c1")
        freezer.move_to(_local(6, 11, 0, 1))
        coordinator.complete("c1")
        with pytest.raises(ServiceValidationError) as err:
            coordinator.undo(log_id=first.id)
        assert err.value.translation_key == "undo_not_latest"

    async def test_undo_approval_returns_to_pending(self, setup) -> None:
        coordinator = await setup({"c1": _chore(assignees=["b1", "v1"])})
        pending = coordinator.complete("c1")
        coordinator.approve(log_id=pending.id, user_id="user_v1")
        coordinator.undo(chore_id="c1")
        assert _occ(coordinator).pending_log_id == pending.id
        assert credited_entries(coordinator.storage.log) == []
        # Og afkrydsningen kan derefter selv fortrydes.
        coordinator.undo(chore_id="c1")
        assert _occ(coordinator).pending_log_id is None

    async def test_nothing_to_undo(self, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        with pytest.raises(ServiceValidationError) as err:
            coordinator.undo(chore_id="c1")
        assert err.value.translation_key == "nothing_to_undo"


class TestOtherActions:
    async def test_skip(self, hass, setup) -> None:
        events = async_capture_events(hass, EVENT_SKIPPED)
        coordinator = await setup({"c1": _chore(assignment="round_robin")})
        entry = coordinator.skip("c1")
        assert entry.points == 0
        assert _occ(coordinator).next_due == _local(6, 11)
        assert _occ(coordinator).assignee == "v2"
        await hass.async_block_till_done()
        assert len(events) == 1

    async def test_reassign(self, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        coordinator.reassign("c1", "v2")
        assert _occ(coordinator).assignee == "v2"
        with pytest.raises(ServiceValidationError) as err:
            coordinator.reassign("c1", "b1")
        assert err.value.translation_key == "not_assignee"

    async def test_reassign_each_refused(self, setup) -> None:
        coordinator = await setup({"c1": _chore(assignment="each")})
        with pytest.raises(ServiceValidationError) as err:
            coordinator.reassign("c1", "v2")
        assert err.value.translation_key == "each_reassign"

    async def test_settle(self, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        entry = coordinator.settle("v1")
        assert entry.action is LogAction.SETTLED and entry.chore_id is None

    async def test_person_for_user(self, setup) -> None:
        coordinator = await setup({"c1": _chore()})
        assert coordinator.person_for_user("user_v2").id == "v2"
        assert coordinator.person_for_user("user_koekken") is None
        assert coordinator.person_for_user(None) is None


class TestTimers:
    async def test_reminder_due_overdue(self, hass, setup, freezer) -> None:
        reminders = async_capture_events(hass, EVENT_REMINDER)
        dues = async_capture_events(hass, EVENT_DUE)
        overdues = async_capture_events(hass, EVENT_OVERDUE)
        await setup({"c1": _chore(due_time="18:00", notify_before=1800)})

        await _tick(hass, freezer, _local(6, 10, 17, 29))
        assert not reminders
        await _tick(hass, freezer, _local(6, 10, 17, 30))
        assert len(reminders) == 1 and not dues
        await _tick(hass, freezer, _local(6, 10, 18))
        assert len(dues) == 1 and not overdues
        await _tick(hass, freezer, _local(6, 10, 19))
        assert len(overdues) == 1
        assert overdues[0].data["person_id"] == "v1"
        # Ingen gentagelse.
        await _tick(hass, freezer, _local(6, 10, 20))
        assert (len(reminders), len(dues), len(overdues)) == (1, 1, 1)

    async def test_restart_sends_only_latest(self, hass, setup, freezer) -> None:
        dues = async_capture_events(hass, EVENT_DUE)
        overdues = async_capture_events(hass, EVENT_OVERDUE)
        coordinator = await setup({"c1": _chore(due_time="18:00")})
        entry = coordinator.entry
        await hass.config_entries.async_unload(entry.entry_id)
        freezer.move_to(_local(6, 10, 20))
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert (len(dues), len(overdues)) == (0, 1)
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert (len(dues), len(overdues)) == (0, 1)

    async def test_snooze_moves_notifications(self, hass, setup, freezer) -> None:
        dues = async_capture_events(hass, EVENT_DUE)
        coordinator = await setup({"c1": _chore(due_time="10:30")})
        coordinator.snooze("c1", timedelta(hours=2))
        chore, occ = coordinator.chores["c1"], _occ(coordinator)
        await _tick(hass, freezer, _local(6, 10, 10, 30))
        assert not dues
        assert coordinator.status(chore, occ, _local(6, 10, 11)) is ChoreStatus.UPCOMING
        await _tick(hass, freezer, _local(6, 10, 12))
        assert len(dues) == 1

    async def test_builtin_notify_on_due(self, hass, setup, freezer) -> None:
        calls = async_mock_service(hass, "notify", "mobile_app_voksen_1")
        await setup({"c1": _chore(due_time="18:00", builtin_notify=True)})
        await _tick(hass, freezer, _local(6, 10, 18))
        assert len(calls) == 1
        assert calls[0].data["message"] == "Tøm opvaskemaskinen is due now"

    async def test_listeners_called_at_midnight(self, hass, setup, freezer) -> None:
        coordinator = await setup({"c1": _chore()})
        calls = []
        coordinator.async_add_listener(lambda: calls.append(1))
        await _tick(hass, freezer, _local(6, 11))
        assert calls
