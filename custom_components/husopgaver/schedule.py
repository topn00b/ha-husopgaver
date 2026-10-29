"""Forfald og status for opgaver.

Alt regnes på lokale datoer i HA's tidszone og konverteres til UTC til sidst.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta

from homeassistant.util import dt as dt_util

from .const import ChoreStatus, IntervalFrom, IntervalUnit, ScheduleKind
from .models import Chore, Schedule

# En årlig dato findes altid inden for et år (29. februar er ikke tilladt).
_MAX_SEARCH_DAYS = 366


def local_date(moment: datetime) -> date:
    """Den lokale dato for et tidspunkt."""
    return dt_util.as_local(moment).date()


def local_datetime(day: date, at: time | None = None) -> datetime:
    """Et lokalt klokkeslæt på en dato som UTC. Uden klokkeslæt: midnat.

    Et klokkeslæt, der ikke findes (skift til sommertid), rykkes frem med
    springets længde. Ved skift til vintertid bruges den første forekomst.
    """
    naive = datetime.combine(day, at or time())
    local = naive.replace(tzinfo=dt_util.get_default_time_zone(), fold=0)
    return dt_util.as_utc(local)


def add_months(day: date, months: int) -> date:
    """Læg måneder til. Findes dagen ikke, bruges månedens sidste dag."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _add_interval(day: date, every: int, unit: IntervalUnit) -> date:
    match unit:
        case IntervalUnit.DAY:
            return day + timedelta(days=every)
        case IntervalUnit.WEEK:
            return day + timedelta(weeks=every)
        case IntervalUnit.MONTH:
            return add_months(day, every)


def _first_step_on_or_after(
    anchor: date, every: int, unit: IntervalUnit, earliest: date
) -> int:
    """Det mindste antal intervaller fra anchor, der lander på eller efter earliest."""
    if unit is IntervalUnit.MONTH:
        months = (earliest.year - anchor.year) * 12 + earliest.month - anchor.month
        step = max(0, months // every)
        while add_months(anchor, step * every) < earliest:
            step += 1
        return step
    step_days = every * (7 if unit is IntervalUnit.WEEK else 1)
    return max(0, -(-(earliest - anchor).days // step_days))


def _matches(schedule: Schedule, day: date) -> bool:
    match schedule.kind:
        case ScheduleKind.WEEKLY:
            return day.weekday() in schedule.weekdays
        case ScheduleKind.YEARLY:
            return (day.month, day.day) in schedule.dates
        case _:
            return True


def _first_matching(chore: Chore, earliest: date, now: datetime) -> datetime:
    """Første dag fra earliest, der passer til gentagelsen, og hvis tidspunkt er efter now."""
    for offset in range(_MAX_SEARCH_DAYS + 1):
        day = earliest + timedelta(days=offset)
        if not _matches(chore.schedule, day):
            continue
        due = local_datetime(day, chore.due_time)
        if chore.due_time is None or due > now:
            return due
    raise ValueError(f"Ingen forfaldsdato fundet for {chore.name!r}")


def first_due(chore: Chore, now: datetime) -> datetime | None:
    """Første forfald for en ny opgave.

    Det er den første dag fra i dag, der passer til gentagelsen. Er
    tidspunktet allerede passeret i dag, bliver det næste passende dag.
    """
    if chore.schedule.kind is ScheduleKind.NONE:
        return chore.schedule.due
    if chore.schedule.kind is ScheduleKind.AFTER:
        return None  # venter på den opgave, den følger efter
    return _first_matching(chore, local_date(now), now)


def followup_due(chore: Chore, completed_at: datetime) -> datetime:
    """Forfald for en opfølgende opgave, når den opgave, den følger efter, er udført.

    Med klokkeslæt: på det klokkeslæt den dag, ventetiden løber ud.
    """
    ready = completed_at + chore.schedule.delay
    if chore.due_time is None:
        return ready
    return local_datetime(local_date(ready), chore.due_time)


def next_due(
    chore: Chore,
    previous_due: datetime,
    completed_at: datetime,
    now: datetime,
    anchor: date | None = None,
) -> datetime | None:
    """Næste forfald, efter at en forekomst er udført, sprunget over eller ikke nødvendig.

    Overskredne forekomster hobes ikke op: datoer, der er sprunget over,
    hoppes frem, indtil næste forfald ligger efter now. Udføres en opgave før
    tid, tæller det for den forekomst, der var forfalden.
    """
    schedule = chore.schedule
    if schedule.kind in (ScheduleKind.NONE, ScheduleKind.AFTER):
        return None  # engangs; eller venter på næste udførelse af forgængeren

    # Datoer før i dag ligger altid før now.
    earliest = max(local_date(previous_due) + timedelta(days=1), local_date(now))

    if schedule.kind is not ScheduleKind.INTERVAL:
        return _first_matching(chore, earliest, now)

    assert schedule.every is not None and schedule.unit is not None
    if schedule.from_ is IntervalFrom.COMPLETION:
        day = _add_interval(local_date(completed_at), schedule.every, schedule.unit)
        return local_datetime(day, chore.due_time)

    if anchor is None:
        raise ValueError(f"Interval fra forfald kræver en startdato: {chore.name!r}")
    step = _first_step_on_or_after(anchor, schedule.every, schedule.unit, earliest)
    while True:
        day = _step(anchor, schedule.every, schedule.unit, step)
        due = local_datetime(day, chore.due_time)
        if chore.due_time is None or due > now:
            return due
        step += 1


def _step(anchor: date, every: int, unit: IntervalUnit, step: int) -> date:
    """Dato for et bestemt antal intervaller fra anchor, altid regnet fra den oprindelige dag."""
    if unit is IntervalUnit.MONTH:
        return add_months(anchor, every * step)
    return _add_interval(anchor, every * step, unit)


def due_window(chore: Chore, due: datetime) -> tuple[datetime, datetime]:
    """Hvornår forekomsten bliver forfalden, og hvornår den bliver overskredet.

    Med klokkeslæt: fra klokkeslættet og 1 time senere. Uden: fra midnat på
    forfaldsdagen og midnat dagen efter.
    """
    if chore.due_time is not None:
        return due, due + timedelta(hours=1)
    day = local_date(due)
    return local_datetime(day), local_datetime(day + timedelta(days=1))


def status(
    chore: Chore, due: datetime | None, now: datetime, pending_approval: bool
) -> ChoreStatus | None:
    """Status for en forekomst. None: engangsopgaven er udført."""
    if pending_approval:
        return ChoreStatus.PENDING_APPROVAL
    if due is None:
        return None
    due_from, overdue_from = due_window(chore, due)
    if now >= overdue_from:
        return ChoreStatus.OVERDUE
    if now >= due_from:
        return ChoreStatus.DUE
    return ChoreStatus.UPCOMING


def week_start(now: datetime) -> datetime:
    """Mandag kl. 00:00 lokal tid i den aktuelle uge, som UTC."""
    today = local_date(now)
    return local_datetime(today - timedelta(days=today.weekday()))


def month_start(now: datetime) -> datetime:
    """Den 1. kl. 00:00 lokal tid i den aktuelle måned, som UTC."""
    return local_datetime(local_date(now).replace(day=1))
