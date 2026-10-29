"""Websocket-API til dashboardkortet.

Kortet får forekomsterne færdiggrupperede, så grupperingen ligger ét sted og
er testet her. Abonnementet sender hele indholdet ved hver ændring; der polles
ikke.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.const import WEEKDAYS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    SIGNAL_UPDATED,
    Assignment,
    ChoreStatus,
    ConditionState,
    LogAction,
)
from .coordinator import HusopgaverCoordinator, OccurrenceView
from .models import Chore
from .points import credited_entries, pending_entries, sum_points
from .schedule import local_date, local_datetime, week_start

@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_occurrences)
    websocket_api.async_register_command(hass, ws_subscribe)


def _coordinator(hass: HomeAssistant) -> HusopgaverCoordinator | None:
    return hass.data.get(DOMAIN)


def _group(view: OccurrenceView, now: datetime, upcoming: timedelta) -> str:
    """pending, overdue, today, upcoming eller later."""
    if view.occurrence.pending_log_id is not None:
        return "pending"
    if view.status is ChoreStatus.OVERDUE:
        return "overdue"
    today = local_date(now)
    day = local_date(view.due)
    if day <= today:
        return "today"
    if day <= today + upcoming:
        return "upcoming"
    return "later"


def build_payload(
    coordinator: HusopgaverCoordinator,
    now: datetime,
    upcoming_days: int | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Alt, hvad kortet viser: personer med ugens point, grupperede opgaver og seeren."""
    upcoming = (
        coordinator.upcoming_window
        if upcoming_days is None
        else timedelta(days=upcoming_days)
    )
    log = coordinator.storage.log
    credited = credited_entries(log)
    since = week_start(now)
    persons = [
        {
            "id": person.id,
            "name": person.name,
            "color": person.color,
            "active": person.active,
            "week_points": sum_points(credited, person.id, since=since),
            "pending_points": sum(
                e.points for e in pending_entries(log) if e.person_id == person.id
            ),
        }
        for person in coordinator.persons.values()
    ]

    items: list[dict[str, Any]] = []
    for view in sorted(coordinator.occurrences(now), key=lambda v: v.due):
        chore = view.chore
        items.append(
            {
                "uid": view.uid,
                "group": _group(view, now, upcoming),
                "chore_id": chore.id,
                "name": chore.name,
                "description": chore.description,
                "key": view.key,
                "each": chore.assignment is Assignment.EACH,
                "open": view.is_open,
                "assignees": list(chore.assignees),
                "person_id": view.person_id,
                "points": chore.points,
                "due": view.due.isoformat(),
                "has_time": chore.due_time is not None,
                "status": None if view.status is None else view.status.value,
                "condition_unknown": view.occurrence.condition_state
                is ConditionState.UNKNOWN,
                "log_id": view.occurrence.pending_log_id,
            }
        )

    # Dagens afkrydsninger, så de kan fortrydes fra kortet.
    undone = {e.ref for e in log if e.action is LogAction.UNDONE}
    today_start = local_datetime(local_date(now))
    for entry in reversed(log):
        if entry.timestamp < today_start:
            break
        if entry.id in undone or entry.action not in (
            LogAction.COMPLETED,
            LogAction.APPROVED,
        ):
            continue
        chore = coordinator.chores.get(entry.chore_id or "")
        if chore is None:
            continue
        items.append(
            {
                "uid": f"log:{entry.id}",
                "group": "done",
                "chore_id": chore.id,
                "name": chore.name,
                "description": chore.description,
                "key": entry.occurrence,
                "each": chore.assignment is Assignment.EACH,
                "open": chore.assignment is Assignment.OPEN,
                "assignees": list(chore.assignees),
                "person_id": entry.person_id,
                "points": entry.points,
                "due": entry.timestamp.isoformat(),
                "has_time": True,
                "status": None,
                "condition_unknown": False,
                "log_id": entry.id,
            }
        )

    viewer = coordinator.person_for_user(user_id)
    return {
        "loaded": True,
        "version": coordinator.version,
        "persons": persons,
        "items": items,
        "chores": [_chore_config(chore) for chore in coordinator.chores.values()],
        "viewer": {
            "person_id": viewer.id if viewer else None,
            "can_approve": bool(viewer and viewer.can_approve),
        },
        "upcoming_days": upcoming.days,
    }


def _chore_config(chore: Chore) -> dict[str, Any]:
    """Opgavens indstillinger i det format, kortets dialog redigerer."""
    schedule = chore.schedule
    return {
        "id": chore.id,
        "name": chore.name,
        "description": chore.description,
        "points": chore.points,
        "assignees": list(chore.assignees),
        "assignment": chore.assignment.value,
        "repeat": schedule.kind.value,
        "every": schedule.every,
        "unit": None if schedule.unit is None else schedule.unit.value,
        "from": None if schedule.from_ is None else schedule.from_.value,
        "weekdays": [WEEKDAYS[d] for d in schedule.weekdays],
        "dates": [f"{m:02d}-{d:02d}" for m, d in schedule.dates],
        "after": schedule.after,
        "delay": int(schedule.delay.total_seconds() // 60),
        "due": None
        if schedule.due is None
        else dt_util.as_local(schedule.due).strftime("%Y-%m-%d %H:%M"),
        "due_time": None if chore.due_time is None else chore.due_time.strftime("%H:%M"),
        "notify_before": None
        if chore.notify_before is None
        else int(chore.notify_before.total_seconds() // 60),
        "approval": chore.approval.value,
        "has_condition": chore.condition is not None,
    }


_SCHEMA = {vol.Optional("upcoming_days"): vol.All(vol.Coerce(int), vol.Range(min=0, max=60))}


@websocket_api.websocket_command({vol.Required("type"): "husopgaver/occurrences", **_SCHEMA})
@callback
def ws_occurrences(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "Husopgaver er ikke sat op")
        return
    connection.send_result(
        msg["id"],
        build_payload(
            coordinator, dt_util.utcnow(), msg.get("upcoming_days"), connection.user.id
        ),
    )


@websocket_api.websocket_command({vol.Required("type"): "husopgaver/subscribe", **_SCHEMA})
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send indholdet nu og ved hver ændring, også efter en genindlæsning."""

    @callback
    def send() -> None:
        coordinator = _coordinator(hass)
        if coordinator is None:
            return  # under genindlæsning; den nye koordinator sender, når den er klar
        connection.send_message(
            websocket_api.event_message(
                msg["id"],
                build_payload(
                    coordinator,
                    dt_util.utcnow(),
                    msg.get("upcoming_days"),
                    connection.user.id,
                ),
            )
        )

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_UPDATED, send
    )
    connection.send_result(msg["id"])
    if _coordinator(hass) is None:
        connection.send_message(
            websocket_api.event_message(
                msg["id"], {"loaded": False, "persons": [], "items": [], "viewer": {}}
            )
        )
        return
    send()

