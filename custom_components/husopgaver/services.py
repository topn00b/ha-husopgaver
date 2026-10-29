"""Services for Husopgaver.

Opgaver kan angives med id, todo-punkt eller navn, og personer med id, navn
eller person-entitet. Brugeren bag kaldet (context.user_id) bruges til
godkendelse og revision.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

import voluptuous as vol

from homeassistant.const import WEEKDAYS
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    ApprovalMode,
    Assignment,
    IntervalFrom,
    IntervalUnit,
    ScheduleKind,
)
from .coordinator import HusopgaverCoordinator, validation_error
from .models import LogEntry

ATTR_CHORE = "chore"
ATTR_PERSON = "person"
ATTR_LOG_ID = "log_id"
ATTR_DURATION = "duration"
ATTR_CHORE_ID = "chore_id"

_CHORE_FIELDS: dict[vol.Marker, Any] = {
    vol.Optional("description"): vol.Any(None, cv.string),
    vol.Optional("points"): vol.All(vol.Coerce(int), vol.Range(min=0)),
    vol.Optional("assignment"): vol.In([a.value for a in Assignment]),
    vol.Optional("repeat"): vol.In([k.value for k in ScheduleKind]),
    vol.Optional("due"): cv.datetime,
    vol.Optional("every"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("unit"): vol.In([u.value for u in IntervalUnit]),
    vol.Optional("from"): vol.In([f.value for f in IntervalFrom]),
    vol.Optional("weekdays"): cv.weekdays,
    vol.Optional("dates"): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("after"): cv.string,
    vol.Optional("delay"): cv.time_period,
    vol.Optional("due_time"): vol.Any(None, cv.time),
    vol.Optional("notify_before"): vol.Any(None, cv.time_period),
    vol.Optional("complete_window"): vol.Any(None, cv.time_period),
    vol.Optional("approval"): vol.In([a.value for a in ApprovalMode]),
    vol.Optional("builtin_notify"): cv.boolean,
}
_ASSIGNEES = vol.All(cv.ensure_list, [cv.string], vol.Length(min=1))

_SCHEMAS: dict[str, vol.Schema] = {
    "complete": vol.Schema(
        {vol.Required(ATTR_CHORE): cv.string, vol.Optional(ATTR_PERSON): cv.string}
    ),
    "skip": vol.Schema(
        {vol.Required(ATTR_CHORE): cv.string, vol.Optional(ATTR_PERSON): cv.string}
    ),
    "reassign": vol.Schema(
        {vol.Required(ATTR_CHORE): cv.string, vol.Required(ATTR_PERSON): cv.string}
    ),
    "snooze": vol.Schema(
        {
            vol.Required(ATTR_CHORE): cv.string,
            vol.Required(ATTR_DURATION): cv.positive_time_period,
            vol.Optional(ATTR_PERSON): cv.string,
        }
    ),
    "settle": vol.Schema({vol.Required(ATTR_PERSON): cv.string}),
    "create_chore": vol.Schema(
        {
            vol.Required("name"): cv.string,
            vol.Required("assignees"): _ASSIGNEES,
            vol.Required("repeat"): vol.In([k.value for k in ScheduleKind]),
            **_CHORE_FIELDS,
        }
    ),
    "update_chore": vol.Schema(
        {
            vol.Required(ATTR_CHORE): cv.string,
            vol.Optional("name"): cv.string,
            vol.Optional("assignees"): _ASSIGNEES,
            **_CHORE_FIELDS,
        }
    ),
    "delete_chore": vol.Schema({vol.Required(ATTR_CHORE): cv.string}),
}
# approve, reject og undo: log-id eller opgave.
for _service in ("approve", "reject", "undo"):
    _SCHEMAS[_service] = vol.All(
        vol.Schema(
            {vol.Optional(ATTR_LOG_ID): cv.string, vol.Optional(ATTR_CHORE): cv.string}
        ),
        cv.has_at_least_one_key(ATTR_LOG_ID, ATTR_CHORE),
    )


def _coordinator(hass: HomeAssistant) -> HusopgaverCoordinator:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise validation_error("not_loaded")
    return entries[0].runtime_data


def _log_response(entry: LogEntry | None) -> ServiceResponse:
    return {ATTR_LOG_ID: None if entry is None else entry.id}


def _seconds(value: timedelta | None) -> int | None:
    return None if value is None else int(value.total_seconds())


def _as_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_util.get_default_time_zone())
    return dt_util.as_utc(value).isoformat()


def _apply_fields(
    coordinator: HusopgaverCoordinator, data: dict[str, Any], fields: dict[str, Any]
) -> dict[str, Any]:
    """Læg service-felterne oven på opgavens rå data."""
    data = dict(data)
    for key in ("name", "description", "points", "assignment", "approval", "builtin_notify"):
        if key in fields:
            data[key] = fields[key]
    if "assignees" in fields:
        data["assignees"] = [
            coordinator.resolve_person(ref).id for ref in fields["assignees"]
        ]
    if "due_time" in fields:
        due_time: time | None = fields["due_time"]
        data["due_time"] = None if due_time is None else due_time.isoformat()
    for key in ("notify_before", "complete_window"):
        if key in fields:
            data[key] = _seconds(fields[key])

    schedule = dict(data.get("schedule", {}))
    if "repeat" in fields and fields["repeat"] != schedule.get("kind"):
        schedule = {"kind": fields["repeat"]}
    for key in ("every", "unit", "from", "dates"):
        if key in fields:
            schedule[key] = fields[key]
    if "weekdays" in fields:
        schedule["weekdays"] = [WEEKDAYS.index(day) for day in fields["weekdays"]]
    if "due" in fields:
        schedule["due"] = _as_utc_iso(fields["due"])
    if "after" in fields:
        schedule["after"] = coordinator.resolve_chore(fields["after"]).id
    if "delay" in fields:
        schedule["delay"] = _seconds(fields["delay"])
    data["schedule"] = schedule
    return data


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Registrér services. Kaldes én gang fra async_setup."""

    def _person_id(coordinator: HusopgaverCoordinator, call: ServiceCall) -> str | None:
        ref = call.data.get(ATTR_PERSON)
        return None if ref is None else coordinator.resolve_person(ref).id

    @callback
    def complete(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass)
        chore = coordinator.resolve_chore(call.data[ATTR_CHORE])
        return _log_response(
            coordinator.complete(
                chore.id, _person_id(coordinator, call), call.context.user_id
            )
        )

    @callback
    def skip(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass)
        chore = coordinator.resolve_chore(call.data[ATTR_CHORE])
        return _log_response(
            coordinator.skip(chore.id, _person_id(coordinator, call), call.context.user_id)
        )

    @callback
    def reassign(call: ServiceCall) -> None:
        coordinator = _coordinator(hass)
        chore = coordinator.resolve_chore(call.data[ATTR_CHORE])
        person = coordinator.resolve_person(call.data[ATTR_PERSON])
        coordinator.reassign(chore.id, person.id)

    @callback
    def snooze(call: ServiceCall) -> None:
        coordinator = _coordinator(hass)
        chore = coordinator.resolve_chore(call.data[ATTR_CHORE])
        coordinator.snooze(
            chore.id, call.data[ATTR_DURATION], _person_id(coordinator, call)
        )

    def _by_log_or_chore(action: str) -> Any:
        @callback
        def handler(call: ServiceCall) -> ServiceResponse:
            coordinator = _coordinator(hass)
            chore_ref = call.data.get(ATTR_CHORE)
            chore_id = None if chore_ref is None else coordinator.resolve_chore(chore_ref).id
            method = getattr(coordinator, action)
            return _log_response(
                method(
                    log_id=call.data.get(ATTR_LOG_ID),
                    chore_id=chore_id,
                    user_id=call.context.user_id,
                )
            )

        return handler

    @callback
    def settle(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass)
        person = coordinator.resolve_person(call.data[ATTR_PERSON])
        return _log_response(coordinator.settle(person.id, call.context.user_id))

    @callback
    def create_chore(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass)
        data = _apply_fields(coordinator, {}, dict(call.data))
        return {ATTR_CHORE_ID: coordinator.create_chore(data)}

    @callback
    def update_chore(call: ServiceCall) -> None:
        coordinator = _coordinator(hass)
        chore = coordinator.resolve_chore(call.data[ATTR_CHORE])
        fields = {k: v for k, v in call.data.items() if k != ATTR_CHORE}
        data = _apply_fields(coordinator, coordinator.chore_data(chore.id), fields)
        coordinator.update_chore(chore.id, data)

    @callback
    def delete_chore(call: ServiceCall) -> None:
        coordinator = _coordinator(hass)
        coordinator.delete_chore(coordinator.resolve_chore(call.data[ATTR_CHORE]).id)

    with_response = {
        "complete": complete,
        "skip": skip,
        "approve": _by_log_or_chore("approve"),
        "reject": _by_log_or_chore("reject"),
        "undo": _by_log_or_chore("undo"),
        "settle": settle,
        "create_chore": create_chore,
    }
    without_response = {
        "reassign": reassign,
        "snooze": snooze,
        "update_chore": update_chore,
        "delete_chore": delete_chore,
    }
    for name, handler in with_response.items():
        hass.services.async_register(
            DOMAIN,
            name,
            handler,
            schema=_SCHEMAS[name],
            supports_response=SupportsResponse.OPTIONAL,
        )
    for name, handler in without_response.items():
        hass.services.async_register(DOMAIN, name, handler, schema=_SCHEMAS[name])
