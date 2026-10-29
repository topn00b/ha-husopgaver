"""Tests af datamodellen: parsing, validering og serialisering."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from custom_components.husopgaver.const import (
    ApprovalMode,
    Assignment,
    ConditionKind,
    ConditionState,
    IntervalFrom,
    IntervalUnit,
    LogAction,
    ScheduleKind,
)
from custom_components.husopgaver.models import (
    Chore,
    ChoreState,
    Condition,
    LogEntry,
    Occurrence,
    Person,
    Schedule,
)


def _chore_data(**overrides):
    data = {
        "name": "Start en tøjvask",
        "points": 1,
        "assignees": ["voksen_1", "voksen_2"],
        "assignment": "least_points",
        "schedule": {"kind": "interval", "every": 2, "unit": "day", "from": "completion"},
    }
    return data | overrides


class TestPerson:
    def test_defaults(self) -> None:
        person = Person.from_dict("p1", {"name": "Barn 1"})
        assert person == Person(id="p1", name="Barn 1")
        assert person.active
        assert not person.can_approve

    def test_roundtrip(self) -> None:
        person = Person.from_dict(
            "p1",
            {
                "name": "Voksen 1",
                "person_entity": "person.voksen_1",
                "notify_target": "notify.mobile_app_voksen_1",
                "can_approve": True,
            },
        )
        assert Person.from_dict("p1", person.to_dict()) == person

    def test_empty_strings_mean_none(self) -> None:
        person = Person.from_dict(
            "p1", {"name": "Barn 1", "person_entity": "", "notify_target": ""}
        )
        assert person.person_entity is None
        assert person.notify_target is None

    @pytest.mark.parametrize(
        "data",
        [
            {"name": "  "},
            {"name": "Barn 1", "person_entity": "sensor.barn_1"},
            {"name": "Barn 1", "notify_target": "mobile_app_barn_1"},
        ],
    )
    def test_invalid(self, data) -> None:
        with pytest.raises(ValueError):
            Person.from_dict("p1", data)


class TestSchedule:
    def test_interval(self) -> None:
        schedule = Schedule.from_dict(
            {"kind": "interval", "every": 2, "unit": "week", "from": "due"}
        )
        assert schedule.kind is ScheduleKind.INTERVAL
        assert schedule.every == 2
        assert schedule.unit is IntervalUnit.WEEK
        assert schedule.from_ is IntervalFrom.DUE
        assert Schedule.from_dict(schedule.to_dict()) == schedule

    def test_interval_defaults_to_from_due(self) -> None:
        schedule = Schedule.from_dict({"kind": "interval", "every": 1, "unit": "day"})
        assert schedule.from_ is IntervalFrom.DUE

    def test_weekly_sorted_and_deduplicated(self) -> None:
        schedule = Schedule.from_dict({"kind": "weekly", "weekdays": [6, 0, 3, 0]})
        assert schedule.weekdays == (0, 3, 6)
        assert Schedule.from_dict(schedule.to_dict()) == schedule

    def test_yearly(self) -> None:
        schedule = Schedule.from_dict({"kind": "yearly", "dates": ["10-01", "04-01"]})
        assert schedule.dates == ((4, 1), (10, 1))
        assert schedule.to_dict()["dates"] == ["04-01", "10-01"]

    def test_none_keeps_utc(self) -> None:
        due = datetime(2026, 10, 30, 16, 0, tzinfo=UTC)
        schedule = Schedule.from_dict({"kind": "none", "due": due.isoformat()})
        assert schedule.due == due
        assert Schedule.from_dict(schedule.to_dict()) == schedule

    @pytest.mark.parametrize(
        "data",
        [
            {"kind": "interval", "every": 0, "unit": "day"},
            {"kind": "interval", "every": 1, "unit": "year"},
            {"kind": "weekly", "weekdays": []},
            {"kind": "weekly", "weekdays": [7]},
            {"kind": "yearly", "dates": []},
            {"kind": "yearly", "dates": ["13-01"]},
            {"kind": "yearly", "dates": ["04-31"]},
            {"kind": "yearly", "dates": ["02-29"]},
            {"kind": "yearly", "dates": ["1. april"]},
            {"kind": "none", "due": "2026-10-30T16:00:00"},
            {"kind": "monthly"},
        ],
    )
    def test_invalid(self, data) -> None:
        with pytest.raises(ValueError):
            Schedule.from_dict(data)


class TestCondition:
    def test_calendar(self) -> None:
        condition = Condition.from_dict(
            {
                "kind": "calendar",
                "check_time": "14:00:00",
                "calendar": "calendar.familie",
                "keywords": ["Besøg", " ", ""],
            }
        )
        assert condition.kind is ConditionKind.CALENDAR
        assert condition.check_time == time(14, 0)
        assert condition.keywords == ("Besøg",)
        assert Condition.from_dict(condition.to_dict()) == condition

    def test_entity(self) -> None:
        condition = Condition.from_dict(
            {"kind": "entity", "check_time": "14:00", "entity": "group.familie",
             "active_state": "home"}
        )
        assert condition.active_state == "home"
        assert Condition.from_dict(condition.to_dict()) == condition

    @pytest.mark.parametrize(
        "data",
        [
            {"kind": "calendar", "calendar": "calendar.familie", "keywords": ["x"]},
            {"kind": "calendar", "check_time": "14:00", "calendar": "calendar.familie",
             "keywords": []},
            {"kind": "calendar", "check_time": "14:00", "calendar": "sensor.x",
             "keywords": ["x"]},
            {"kind": "entity", "check_time": "14:00"},
            {"kind": "entity", "check_time": "25:00", "entity": "group.familie"},
        ],
    )
    def test_invalid(self, data) -> None:
        with pytest.raises(ValueError):
            Condition.from_dict(data)


class TestChore:
    def test_defaults(self) -> None:
        chore = Chore.from_dict(
            "c1",
            {
                "name": "Tøm opvaskeren",
                "assignees": ["voksen_1"],
                "schedule": {"kind": "interval", "every": 1, "unit": "day"},
            },
        )
        assert chore.points == 1
        assert chore.assignment is Assignment.LEAST_POINTS
        assert chore.approval is ApprovalMode.AUTO
        assert chore.condition is None
        assert chore.due_time is None

    def test_roundtrip_full(self) -> None:
        chore = Chore.from_dict(
            "c1",
            _chore_data(
                description="Mørk vask først",
                due_time="18:00:00",
                notify_before=7200,
                complete_window=3600,
                approval="always",
                builtin_notify=True,
                condition={
                    "kind": "calendar",
                    "check_time": "14:00:00",
                    "calendar": "calendar.familie",
                    "keywords": ["Besøg"],
                },
            ),
        )
        assert chore.notify_before == timedelta(hours=2)
        assert chore.complete_window == timedelta(hours=1)
        assert Chore.from_dict("c1", chore.to_dict()) == chore

    def test_assignee_order_kept_and_deduplicated(self) -> None:
        chore = Chore.from_dict(
            "c1", _chore_data(assignees=["barn_2", "barn_1", "barn_2"])
        )
        assert chore.assignees == ("barn_2", "barn_1")

    @pytest.mark.parametrize(
        "overrides",
        [
            {"name": ""},
            {"points": -1},
            {"assignees": []},
            {"assignment": "random"},
            {"approval": "sometimes"},
            {"notify_before": -60},
            {"due_time": "kl. 18"},
        ],
    )
    def test_invalid(self, overrides) -> None:
        with pytest.raises(ValueError):
            Chore.from_dict("c1", _chore_data(**overrides))


class TestRuntime:
    def test_chore_state_roundtrip(self) -> None:
        state = ChoreState(
            occurrences={
                "barn_1": Occurrence(
                    next_due=datetime(2026, 10, 30, 5, 0, tzinfo=UTC),
                    assignee="barn_1",
                    pending_log_id="log1",
                    condition_state=ConditionState.ACTIVE,
                    anchor=date(2026, 1, 31),
                ),
                "barn_2": Occurrence(next_due=None, assignee=None),
            },
            rr_index=3,
        )
        assert ChoreState.from_dict(state.to_dict()) == state

    def test_invalid_anchor_rejected(self) -> None:
        with pytest.raises(ValueError):
            Occurrence.from_dict({"next_due": None, "anchor": "2026-02-30"})

    def test_with_occurrence_does_not_mutate(self) -> None:
        state = ChoreState()
        new = state.with_occurrence("_shared", Occurrence(next_due=None, assignee=None))
        assert state.occurrences == {}
        assert "_shared" in new.occurrences

    def test_log_entry_roundtrip(self) -> None:
        entry = LogEntry(
            id="log1",
            person_id="barn_1",
            timestamp=datetime(2026, 10, 29, 17, 30, tzinfo=UTC),
            action=LogAction.PENDING,
            points=2,
            chore_id="c1",
            occurrence="barn_1",
            by_user="user123",
            previous_state={"occurrences": {}, "rr_index": 0},
        )
        assert LogEntry.from_dict(entry.to_dict()) == entry

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValueError):
            Occurrence(next_due=datetime(2026, 10, 30, 6, 0), assignee=None).to_dict()
