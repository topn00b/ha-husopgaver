"""Tests af næste forfald, status og tidsgrænser, inklusive sommertid.

2026: Sommertid begynder søndag 29. marts kl. 02:00 og slutter søndag 25. oktober kl. 03:00.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from custom_components.husopgaver.const import ChoreStatus
from custom_components.husopgaver.models import Chore
from custom_components.husopgaver.schedule import (
    add_months,
    due_window,
    first_due,
    local_datetime,
    month_start,
    next_due,
    status,
    week_start,
)

CPH = ZoneInfo("Europe/Copenhagen")

pytestmark = pytest.mark.usefixtures("cph_tz")


def _local(year, month, day, hour=0, minute=0) -> datetime:
    """Lokal tid i København som UTC."""
    return datetime(year, month, day, hour, minute, tzinfo=CPH).astimezone(UTC)


def _chore(schedule, due_time=None) -> Chore:
    data = {"name": "Opgave", "assignees": ["voksen_1"], "schedule": schedule}
    if due_time:
        data["due_time"] = due_time
    return Chore.from_dict("c1", data)


def _interval(every, unit, from_="due", due_time=None) -> Chore:
    return _chore(
        {"kind": "interval", "every": every, "unit": unit, "from": from_}, due_time
    )


class TestLocalDatetime:
    def test_midnight_default(self) -> None:
        assert local_datetime(date(2026, 6, 10)) == datetime(
            2026, 6, 9, 22, 0, tzinfo=UTC
        )

    def test_nonexistent_time_moves_forward(self) -> None:
        # 02:30 findes ikke den 29. marts; det bliver 03:30 sommertid.
        assert local_datetime(date(2026, 3, 29), time(2, 30)) == datetime(
            2026, 3, 29, 1, 30, tzinfo=UTC
        )

    def test_ambiguous_time_uses_first(self) -> None:
        # 02:30 forekommer to gange den 25. oktober; den første er sommertid.
        assert local_datetime(date(2026, 10, 25), time(2, 30)) == datetime(
            2026, 10, 25, 0, 30, tzinfo=UTC
        )


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),
        (date(2026, 1, 31), 2, date(2026, 3, 31)),
        (date(2026, 12, 31), 2, date(2027, 2, 28)),
        (date(2026, 5, 15), 12, date(2027, 5, 15)),
    ],
)
def test_add_months(start, months, expected) -> None:
    assert add_months(start, months) == expected


class TestFirstDue:
    def test_one_off(self) -> None:
        due = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
        chore = _chore({"kind": "none", "due": due.isoformat()})
        assert first_due(chore, _local(2026, 6, 10, 12)) == due

    def test_interval_without_time_is_due_today(self) -> None:
        chore = _interval(1, "week")
        assert first_due(chore, _local(2026, 6, 10, 15)) == _local(2026, 6, 10)

    def test_interval_time_not_passed(self) -> None:
        chore = _interval(1, "day", due_time="18:00")
        assert first_due(chore, _local(2026, 6, 10, 15)) == _local(2026, 6, 10, 18)

    def test_interval_time_passed(self) -> None:
        chore = _interval(1, "day", due_time="18:00")
        assert first_due(chore, _local(2026, 6, 10, 19)) == _local(2026, 6, 11, 18)

    def test_weekly(self) -> None:
        # Onsdag 10. juni; næste mandag eller torsdag er torsdag 11. juni.
        chore = _chore({"kind": "weekly", "weekdays": [0, 3]})
        assert first_due(chore, _local(2026, 6, 10, 12)) == _local(2026, 6, 11)

    def test_yearly(self) -> None:
        chore = _chore({"kind": "yearly", "dates": ["04-01", "10-01"]})
        assert first_due(chore, _local(2026, 6, 10, 12)) == _local(2026, 10, 1)


class TestIntervalFromDue:
    def test_day(self) -> None:
        chore = _interval(2, "day")
        now = _local(2026, 6, 1, 10)
        assert next_due(
            chore, _local(2026, 6, 1), now, now, anchor=date(2026, 6, 1)
        ) == _local(2026, 6, 3)

    def test_week(self) -> None:
        chore = _interval(1, "week", due_time="10:00")
        now = _local(2026, 6, 1, 11)
        assert next_due(
            chore, _local(2026, 6, 1, 10), now, now, anchor=date(2026, 6, 1)
        ) == _local(2026, 6, 8, 10)

    def test_skipped_dates_hop_forward_no_pile_up(self) -> None:
        # Gitter: 1., 3., 5., 7., 9. juni. Udført den 8.: næste er den 9.
        chore = _interval(2, "day")
        now = _local(2026, 6, 8, 10)
        assert next_due(
            chore, _local(2026, 6, 1), now, now, anchor=date(2026, 6, 1)
        ) == _local(2026, 6, 9)

    def test_grid_date_today_without_time_is_today(self) -> None:
        chore = _interval(2, "day")
        now = _local(2026, 6, 9, 10)
        assert next_due(
            chore, _local(2026, 6, 1), now, now, anchor=date(2026, 6, 1)
        ) == _local(2026, 6, 9)

    def test_grid_time_today_already_passed(self) -> None:
        chore = _interval(2, "day", due_time="18:00")
        now = _local(2026, 6, 9, 19)
        assert next_due(
            chore, _local(2026, 6, 1, 18), now, now, anchor=date(2026, 6, 1)
        ) == _local(2026, 6, 11, 18)

    def test_month_end_returns_to_original_day(self) -> None:
        chore = _interval(1, "month")
        anchor = date(2026, 1, 31)
        feb = next_due(
            chore, _local(2026, 1, 31), _local(2026, 1, 31, 9), _local(2026, 1, 31, 9), anchor
        )
        assert feb == _local(2026, 2, 28)
        mar = next_due(
            chore, feb, _local(2026, 2, 28, 9), _local(2026, 2, 28, 9), anchor
        )
        assert mar == _local(2026, 3, 31)

    def test_early_completion_counts_for_current(self) -> None:
        chore = _interval(1, "month")
        now = _local(2026, 6, 20, 9)
        assert next_due(
            chore, _local(2026, 7, 1), now, now, anchor=date(2026, 1, 1)
        ) == _local(2026, 8, 1)

    def test_missing_anchor_is_an_error(self) -> None:
        chore = _interval(1, "day")
        now = _local(2026, 6, 1, 10)
        with pytest.raises(ValueError):
            next_due(chore, _local(2026, 6, 1), now, now)


class TestIntervalFromCompletion:
    def test_day_keeps_due_time(self) -> None:
        chore = _interval(2, "day", from_="completion", due_time="18:00")
        done = _local(2026, 6, 10, 20)
        assert next_due(chore, _local(2026, 6, 8, 18), done, done) == _local(
            2026, 6, 12, 18
        )

    def test_uses_local_date_not_utc(self) -> None:
        # 00:30 lokal tid den 11. er 22:30 UTC den 10.
        chore = _interval(2, "day", from_="completion")
        done = _local(2026, 6, 11, 0, 30)
        assert done.day == 10
        assert next_due(chore, _local(2026, 6, 10), done, done) == _local(2026, 6, 13)

    def test_month_end(self) -> None:
        chore = _interval(1, "month", from_="completion")
        done = _local(2026, 1, 31, 12)
        feb = next_due(chore, _local(2026, 1, 31), done, done)
        assert feb == _local(2026, 2, 28)
        done = _local(2026, 2, 28, 12)
        assert next_due(chore, feb, done, done) == _local(2026, 3, 28)

    def test_approval_later_uses_completion_time(self) -> None:
        chore = _interval(1, "week", from_="completion")
        done, approved = _local(2026, 6, 1, 12), _local(2026, 6, 3, 12)
        assert next_due(chore, _local(2026, 6, 1), done, approved) == _local(
            2026, 6, 8
        )


class TestWeekly:
    def test_next_weekday(self) -> None:
        chore = _chore({"kind": "weekly", "weekdays": [0, 3]})
        now = _local(2026, 6, 8, 12)  # mandag
        assert next_due(chore, _local(2026, 6, 8), now, now) == _local(2026, 6, 11)

    def test_wraps_to_next_week(self) -> None:
        chore = _chore({"kind": "weekly", "weekdays": [0, 3]})
        now = _local(2026, 6, 11, 12)  # torsdag
        assert next_due(chore, _local(2026, 6, 11), now, now) == _local(2026, 6, 15)

    def test_early_completion_counts_for_current(self) -> None:
        # Forfald torsdag; udført tirsdag før. Næste er mandagen efter torsdag.
        chore = _chore({"kind": "weekly", "weekdays": [0, 3]})
        now = _local(2026, 6, 9, 12)
        assert next_due(chore, _local(2026, 6, 11), now, now) == _local(2026, 6, 15)

    def test_overdue_hops_forward(self) -> None:
        chore = _chore({"kind": "weekly", "weekdays": [2]}, due_time="18:00")
        now = _local(2026, 6, 24, 19)  # onsdag, efter 18:00, tre uger for sent
        assert next_due(chore, _local(2026, 6, 3, 18), now, now) == _local(
            2026, 7, 1, 18
        )


class TestYearly:
    def test_early_completion_counts_for_current(self) -> None:
        chore = _chore({"kind": "yearly", "dates": ["10-01"]})
        now = _local(2026, 9, 25, 12)
        assert next_due(chore, _local(2026, 10, 1), now, now) == _local(2027, 10, 1)

    def test_several_dates(self) -> None:
        chore = _chore({"kind": "yearly", "dates": ["10-01", "04-01"]})
        now = _local(2026, 4, 1, 12)
        assert next_due(chore, _local(2026, 4, 1), now, now) == _local(2026, 10, 1)
        now = _local(2026, 10, 1, 12)
        assert next_due(chore, _local(2026, 10, 1), now, now) == _local(2027, 4, 1)


def test_one_off_has_no_next() -> None:
    due = _local(2026, 6, 10, 12)
    chore = _chore({"kind": "none", "due": due.isoformat()})
    assert next_due(chore, due, due, due) is None


class TestDaylightSaving:
    def test_daily_across_spring_forward(self) -> None:
        chore = _interval(1, "day", due_time="18:00")
        prev = _local(2026, 3, 28, 18)
        now = _local(2026, 3, 28, 19)
        nxt = next_due(chore, prev, now, now, anchor=date(2026, 3, 1))
        assert prev == datetime(2026, 3, 28, 17, 0, tzinfo=UTC)
        assert nxt == datetime(2026, 3, 29, 16, 0, tzinfo=UTC)

    def test_daily_across_fall_back(self) -> None:
        chore = _interval(1, "day", due_time="18:00")
        prev = _local(2026, 10, 24, 18)
        now = _local(2026, 10, 24, 19)
        nxt = next_due(chore, prev, now, now, anchor=date(2026, 10, 1))
        assert prev == datetime(2026, 10, 24, 16, 0, tzinfo=UTC)
        assert nxt == datetime(2026, 10, 25, 17, 0, tzinfo=UTC)

    def test_weekly_across_both(self) -> None:
        chore = _chore({"kind": "weekly", "weekdays": [6]}, due_time="10:00")
        now = _local(2026, 3, 22, 11)
        assert next_due(chore, _local(2026, 3, 22, 10), now, now) == datetime(
            2026, 3, 29, 8, 0, tzinfo=UTC
        )
        now = _local(2026, 10, 18, 11)
        assert next_due(chore, _local(2026, 10, 18, 10), now, now) == datetime(
            2026, 10, 25, 9, 0, tzinfo=UTC
        )

    def test_nonexistent_due_time(self) -> None:
        chore = _chore({"kind": "weekly", "weekdays": [6]}, due_time="02:30")
        now = _local(2026, 3, 22, 3)
        assert next_due(chore, _local(2026, 3, 22, 2, 30), now, now) == datetime(
            2026, 3, 29, 1, 30, tzinfo=UTC
        )

    def test_ambiguous_due_time(self) -> None:
        chore = _chore({"kind": "weekly", "weekdays": [6]}, due_time="02:30")
        now = _local(2026, 10, 18, 3)
        assert next_due(chore, _local(2026, 10, 18, 2, 30), now, now) == datetime(
            2026, 10, 25, 0, 30, tzinfo=UTC
        )

    def test_midnight_on_change_days(self) -> None:
        chore = _interval(1, "day")
        now = _local(2026, 3, 28, 12)
        assert next_due(
            chore, _local(2026, 3, 28), now, now, anchor=date(2026, 3, 1)
        ) == datetime(2026, 3, 28, 23, 0, tzinfo=UTC)
        now = _local(2026, 3, 29, 12)
        assert next_due(
            chore, _local(2026, 3, 29), now, now, anchor=date(2026, 3, 1)
        ) == datetime(2026, 3, 29, 22, 0, tzinfo=UTC)

    def test_overdue_at_midnight_after_spring_forward(self) -> None:
        # Søndag 29. marts har 23 timer: overskredet fra mandag kl. 00:00 sommertid.
        chore = _interval(1, "day")
        due_from, overdue_from = due_window(chore, _local(2026, 3, 29))
        assert due_from == datetime(2026, 3, 28, 23, 0, tzinfo=UTC)
        assert overdue_from == datetime(2026, 3, 29, 22, 0, tzinfo=UTC)

    def test_overdue_at_midnight_after_fall_back(self) -> None:
        # Søndag 25. oktober har 25 timer.
        chore = _interval(1, "day")
        due_from, overdue_from = due_window(chore, _local(2026, 10, 25))
        assert due_from == datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
        assert overdue_from == datetime(2026, 10, 25, 23, 0, tzinfo=UTC)

    @pytest.mark.parametrize(
        ("now", "expected"),
        [
            # Søndag i ugen med skift til sommertid: ugen startede i normaltid.
            (_local(2026, 3, 29, 12), datetime(2026, 3, 22, 23, 0, tzinfo=UTC)),
            (_local(2026, 3, 30, 0, 30), datetime(2026, 3, 29, 22, 0, tzinfo=UTC)),
            # Søndag i ugen med skift til normaltid: ugen startede i sommertid.
            (_local(2026, 10, 25, 12), datetime(2026, 10, 18, 22, 0, tzinfo=UTC)),
            (_local(2026, 10, 26, 0, 30), datetime(2026, 10, 25, 23, 0, tzinfo=UTC)),
        ],
    )
    def test_week_start(self, now, expected) -> None:
        assert week_start(now) == expected

    def test_month_start(self) -> None:
        assert month_start(_local(2026, 4, 1, 0, 30)) == datetime(
            2026, 3, 31, 22, 0, tzinfo=UTC
        )
        assert month_start(_local(2026, 3, 31, 23, 30)) == datetime(
            2026, 2, 28, 23, 0, tzinfo=UTC
        )


class TestStatus:
    @pytest.mark.parametrize(
        ("now", "expected"),
        [
            (_local(2026, 6, 9, 23, 59), ChoreStatus.UPCOMING),
            (_local(2026, 6, 10), ChoreStatus.DUE),
            (_local(2026, 6, 10, 23, 59), ChoreStatus.DUE),
            (_local(2026, 6, 11), ChoreStatus.OVERDUE),
        ],
    )
    def test_without_time(self, now, expected) -> None:
        chore = _interval(1, "week")
        assert status(chore, _local(2026, 6, 10), now, False) is expected

    @pytest.mark.parametrize(
        ("now", "expected"),
        [
            (_local(2026, 6, 10, 17, 59), ChoreStatus.UPCOMING),
            (_local(2026, 6, 10, 18), ChoreStatus.DUE),
            (_local(2026, 6, 10, 18, 59), ChoreStatus.DUE),
            (_local(2026, 6, 10, 19), ChoreStatus.OVERDUE),
        ],
    )
    def test_with_time(self, now, expected) -> None:
        chore = _interval(1, "week", due_time="18:00")
        assert status(chore, _local(2026, 6, 10, 18), now, False) is expected

    def test_pending_approval(self) -> None:
        chore = _interval(1, "week")
        due = _local(2026, 6, 10)
        assert status(chore, due, _local(2026, 6, 12), True) is (
            ChoreStatus.PENDING_APPROVAL
        )

    def test_one_off_done(self) -> None:
        chore = _interval(1, "week")
        assert status(chore, None, _local(2026, 6, 12), False) is None
