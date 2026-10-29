"""Tests af tildeling, fravær og pointregnskab."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging

import pytest

from homeassistant.core import State

from custom_components.husopgaver.assignment import assign, each_assignees, is_absent
from custom_components.husopgaver.const import LogAction
from custom_components.husopgaver.models import Chore, LogEntry, Person
from custom_components.husopgaver.points import (
    credited_entries,
    last_done,
    pending_entries,
    sum_points,
)

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
WINDOW = timedelta(days=30)

PERSONS = {
    "v1": Person(id="v1", name="Voksen 1", person_entity="person.voksen_1"),
    "v2": Person(id="v2", name="Voksen 2", person_entity="person.voksen_2"),
    "b1": Person(id="b1", name="Barn 1"),
    "b2": Person(id="b2", name="Barn 2", active=False),
}


def _chore(assignment, assignees=("v1", "v2", "b1"), chore_id="c1") -> Chore:
    return Chore.from_dict(
        chore_id,
        {
            "name": "Opgave",
            "assignees": list(assignees),
            "assignment": assignment,
            "schedule": {"kind": "weekly", "weekdays": [0]},
        },
    )


_counter = 0


def _log(person, action, *, days_ago=1, points=1, chore="c1", ref=None) -> LogEntry:
    global _counter  # noqa: PLW0603
    _counter += 1
    return LogEntry(
        id=f"log{_counter}",
        person_id=person,
        timestamp=NOW - timedelta(days=days_ago),
        action=action,
        points=points,
        chore_id=chore,
        ref=ref,
    )


def _assign(chore, *, absent=frozenset(), rr_index=0, log=()):
    return assign(
        chore, PERSONS, absent, rr_index, credited_entries(log), NOW, WINDOW
    )


class TestEach:
    def test_only_active(self) -> None:
        assert each_assignees(_chore("each", ("b1", "b2", "v1")), PERSONS) == [
            "b1",
            "v1",
        ]

    def test_assign_rejects_each(self) -> None:
        with pytest.raises(ValueError):
            _assign(_chore("each"))


class TestFixed:
    def test_first(self) -> None:
        assert _assign(_chore("fixed")) == ("v1", 0)

    def test_absence_keeps_assignment(self) -> None:
        assert _assign(_chore("fixed"), absent={"v1"}) == ("v1", 0)

    def test_inactive_skipped(self) -> None:
        assert _assign(_chore("fixed", ("b2", "b1"))) == ("b1", 0)


class TestRoundRobin:
    @pytest.mark.parametrize(
        ("rr_index", "expected"),
        [(0, ("v1", 1)), (1, ("v2", 2)), (2, ("b1", 0))],
    )
    def test_in_turn(self, rr_index, expected) -> None:
        assert _assign(_chore("round_robin"), rr_index=rr_index) == expected

    def test_absent_skipped_and_index_moves_on(self) -> None:
        assert _assign(_chore("round_robin"), absent={"v2"}, rr_index=1) == ("b1", 0)

    def test_inactive_skipped(self) -> None:
        chore = _chore("round_robin", ("v1", "b2", "b1"))
        assert _assign(chore, rr_index=1) == ("b1", 0)

    def test_everyone_absent_ignores_absence(self) -> None:
        chore = _chore("round_robin")
        assert _assign(chore, absent={"v1", "v2", "b1"}, rr_index=1) == ("v2", 2)

    def test_index_beyond_list_wraps(self) -> None:
        # Fx efter at en person er fjernet fra opgaven.
        assert _assign(_chore("round_robin", ("v1", "v2")), rr_index=5) == ("v2", 0)


class TestLeastPoints:
    def test_fewest_points(self) -> None:
        log = [
            _log("v1", LogAction.COMPLETED, points=3, chore="other"),
            _log("v2", LogAction.COMPLETED, points=1, chore="other"),
            _log("b1", LogAction.COMPLETED, points=2, chore="other"),
        ]
        assert _assign(_chore("least_points"), log=log) == ("v2", 0)

    def test_points_outside_window_ignored(self) -> None:
        log = [
            _log("v1", LogAction.COMPLETED, points=10, days_ago=31, chore="other"),
            _log("v2", LogAction.COMPLETED, points=1, chore="other"),
            _log("b1", LogAction.COMPLETED, points=1, chore="other"),
        ]
        assert _assign(_chore("least_points"), log=log) == ("v1", 0)

    def test_tie_goes_to_longest_since_this_chore(self) -> None:
        log = [
            _log("v1", LogAction.COMPLETED, days_ago=2),
            _log("v2", LogAction.COMPLETED, days_ago=5),
            _log("b1", LogAction.COMPLETED, days_ago=3),
        ]
        assert _assign(_chore("least_points"), log=log) == ("v2", 0)

    def test_tie_never_done_wins(self) -> None:
        log = [
            _log("v1", LogAction.COMPLETED, days_ago=9),
            _log("v2", LogAction.COMPLETED, chore="other"),
            _log("b1", LogAction.COMPLETED, days_ago=5),
        ]
        assert _assign(_chore("least_points"), log=log) == ("v2", 0)

    def test_full_tie_follows_assignee_order(self) -> None:
        assert _assign(_chore("least_points", ("b1", "v2", "v1"))) == ("b1", 0)

    def test_absent_excluded(self) -> None:
        assert _assign(_chore("least_points"), absent={"v1"}) == ("v2", 0)

    def test_pending_and_undone_not_counted(self) -> None:
        pending = _log("v1", LogAction.PENDING, points=5, chore="other")
        done = _log("v2", LogAction.COMPLETED, points=5, chore="other")
        log = [
            pending,
            done,
            _log("v2", LogAction.UNDONE, points=0, chore="other", ref=done.id),
            _log("b1", LogAction.COMPLETED, points=1, chore="other"),
        ]
        assert _assign(_chore("least_points"), log=log) == ("v1", 0)

    def test_no_active_assignees(self) -> None:
        assert _assign(_chore("least_points", ("b2",)), rr_index=2) == (None, 2)


class TestAbsence:
    @pytest.fixture
    def person(self) -> Person:
        return PERSONS["v1"]

    def _state(self, value, hours) -> State:
        return State(
            "person.voksen_1", value, last_changed=NOW - timedelta(hours=hours)
        )

    def test_away_longer_than_threshold(self, person) -> None:
        assert is_absent(person, self._state("not_home", 25), NOW, timedelta(hours=24))

    def test_away_shorter_than_threshold(self, person) -> None:
        assert not is_absent(
            person, self._state("not_home", 23), NOW, timedelta(hours=24)
        )

    def test_other_zone_counts_as_away(self, person) -> None:
        assert is_absent(person, self._state("Arbejde", 25), NOW, timedelta(hours=24))

    def test_home(self, person) -> None:
        assert not is_absent(person, self._state("home", 100), NOW, timedelta(hours=24))

    @pytest.mark.parametrize("value", ["unknown", "unavailable"])
    def test_unknown_counts_as_available_and_is_logged(
        self, person, value, caplog
    ) -> None:
        with caplog.at_level(logging.INFO):
            assert not is_absent(
                person, self._state(value, 100), NOW, timedelta(hours=24)
            )
        assert "person.voksen_1" in caplog.text

    def test_missing_state(self, person) -> None:
        assert not is_absent(person, None, NOW, timedelta(hours=24))

    def test_no_person_entity(self) -> None:
        assert not is_absent(PERSONS["b1"], None, NOW, timedelta(hours=24))


class TestPoints:
    def test_approved_counts_pending_does_not(self) -> None:
        pending = _log("b1", LogAction.PENDING, points=2)
        approved = _log("b1", LogAction.APPROVED, points=2, ref=pending.id)
        other = _log("b1", LogAction.PENDING, points=3)
        log = [pending, approved, other]
        assert credited_entries(log) == [approved]
        assert pending_entries(log) == [other]

    def test_rejected_and_undone_resolve_pending(self) -> None:
        p1 = _log("b1", LogAction.PENDING)
        p2 = _log("b1", LogAction.PENDING)
        log = [
            p1,
            _log("v1", LogAction.REJECTED, ref=p1.id),
            p2,
            _log("b1", LogAction.UNDONE, ref=p2.id),
        ]
        assert pending_entries(log) == []
        assert credited_entries(log) == []

    def test_undone_approval_removes_points(self) -> None:
        pending = _log("b1", LogAction.PENDING)
        approved = _log("b1", LogAction.APPROVED, ref=pending.id)
        log = [pending, approved, _log("v1", LogAction.UNDONE, ref=approved.id)]
        assert credited_entries(log) == []

    def test_sum_points_period(self) -> None:
        credited = [
            _log("v1", LogAction.COMPLETED, points=1, days_ago=10),
            _log("v1", LogAction.COMPLETED, points=2, days_ago=5),
            _log("v1", LogAction.COMPLETED, points=4, days_ago=1),
            _log("v2", LogAction.COMPLETED, points=8, days_ago=1),
        ]
        assert sum_points(credited, "v1") == 7
        assert sum_points(credited, "v1", since=NOW - timedelta(days=5)) == 6
        assert sum_points(credited, "v1", until=NOW - timedelta(days=5)) == 1

    def test_last_done(self) -> None:
        credited = [
            _log("v1", LogAction.COMPLETED, days_ago=10),
            _log("v1", LogAction.COMPLETED, days_ago=3),
            _log("v1", LogAction.COMPLETED, days_ago=1, chore="other"),
        ]
        assert last_done(credited, "c1", "v1") == NOW - timedelta(days=3)
        assert last_done(credited, "c1", "v2") is None
