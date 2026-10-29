"""Config flow, options og subentries (personer og opgaver) for Husopgaver."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import WEEKDAYS
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    BooleanSelector,
    ColorRGBSelector,
    DateTimeSelector,
    DurationSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TimeSelector,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ABSENCE_HOURS,
    CONF_ALL_LIST,
    CONF_POINTS_WINDOW_DAYS,
    CONF_UNDO_MINUTES,
    CONF_UPCOMING_DAYS,
    DEFAULT_ABSENCE_HOURS,
    DEFAULT_POINTS,
    DEFAULT_POINTS_WINDOW_DAYS,
    DEFAULT_UNDO_MINUTES,
    DEFAULT_UPCOMING_DAYS,
    DOMAIN,
    SUBENTRY_CHORE,
    SUBENTRY_PERSON,
    ApprovalMode,
    Assignment,
    ConditionKind,
    IntervalFrom,
    IntervalUnit,
    ScheduleKind,
)
from .models import Chore, Person

ADVANCED = "advanced"
REPEAT = "repeat"
CONDITION = "condition"
NO_CONDITION = "none"
DEFAULT_CHECK_TIME = "14:00:00"


class HusopgaverConfigFlow(ConfigFlow, domain=DOMAIN):
    """Opret integrationen. Personer og opgaver tilføjes bagefter."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Husopgaver", data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HusopgaverOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_PERSON: PersonSubentryFlow, SUBENTRY_CHORE: ChoreSubentryFlow}


def _number(minimum: int, maximum: int) -> vol.All:
    return vol.All(
        NumberSelector(
            NumberSelectorConfig(min=minimum, max=maximum, mode=NumberSelectorMode.BOX)
        ),
        vol.Coerce(int),
    )


def _select(
    translation_key: str, options: list[str], multiple: bool = False
) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            translation_key=translation_key,
            multiple=multiple,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


class HusopgaverOptionsFlow(OptionsFlow):
    """Indstillinger for vinduer, fravær, fortryd og listen "Alle opgaver"."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPCOMING_DAYS,
                    default=options.get(CONF_UPCOMING_DAYS, DEFAULT_UPCOMING_DAYS),
                ): _number(0, 30),
                vol.Required(
                    CONF_POINTS_WINDOW_DAYS,
                    default=options.get(
                        CONF_POINTS_WINDOW_DAYS, DEFAULT_POINTS_WINDOW_DAYS
                    ),
                ): _number(1, 365),
                vol.Required(
                    CONF_ABSENCE_HOURS,
                    default=options.get(CONF_ABSENCE_HOURS, DEFAULT_ABSENCE_HOURS),
                ): _number(1, 720),
                vol.Required(
                    CONF_UNDO_MINUTES,
                    default=options.get(CONF_UNDO_MINUTES, DEFAULT_UNDO_MINUTES),
                ): _number(0, 120),
                vol.Required(
                    CONF_ALL_LIST, default=options.get(CONF_ALL_LIST, False)
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


# Personer


def _hex_to_rgb(value: str) -> list[int]:
    return [int(value[i : i + 2], 16) for i in (1, 3, 5)]


def _rgb_to_hex(value: list[int]) -> str:
    return "#" + "".join(f"{int(c):02x}" for c in value)


class PersonSubentryFlow(ConfigSubentryFlow):
    """Tilføj eller ret en person."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return self._form("user", user_input, None)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return self._form("reconfigure", user_input, self._get_reconfigure_subentry())

    def _schema(self) -> vol.Schema:
        notify = sorted(
            f"notify.{service}"
            for service in self.hass.services.async_services_for_domain("notify")
        )
        return vol.Schema(
            {
                vol.Required("name"): TextSelector(),
                vol.Optional("person_entity"): EntitySelector(
                    EntitySelectorConfig(domain="person")
                ),
                vol.Optional("notify_target"): SelectSelector(
                    SelectSelectorConfig(
                        options=notify,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("color"): ColorRGBSelector(),
                vol.Required("can_approve", default=False): BooleanSelector(),
                vol.Required("requires_approval", default=False): BooleanSelector(),
                vol.Required("active", default=True): BooleanSelector(),
            }
        )

    @callback
    def _form(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        subentry: ConfigSubentry | None,
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            data = dict(user_input)
            data["name"] = data["name"].strip()
            if (color := data.get("color")) is not None:
                data["color"] = _rgb_to_hex(color)
            try:
                Person.from_dict("ny", data)
            except ValueError as err:
                errors["base"] = "invalid"
                placeholders["error"] = str(err)
            else:
                if subentry is None:
                    return self.async_create_entry(title=data["name"], data=data)
                return self.async_update_and_abort(
                    self._get_entry(), subentry, title=data["name"], data=data
                )

        suggested: dict[str, Any] = dict(subentry.data) if subentry else {}
        if suggested.get("color"):
            suggested["color"] = _hex_to_rgb(suggested["color"])
        if user_input is not None:
            suggested = user_input
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(self._schema(), suggested),
            errors=errors,
            description_placeholders=placeholders,
        )


# Opgaver


def _seconds(value: Mapping[str, Any] | None) -> int | None:
    if not value:
        return None
    total = (
        value.get("days", 0) * 86400
        + value.get("hours", 0) * 3600
        + value.get("minutes", 0) * 60
        + value.get("seconds", 0)
    )
    return int(total) or None


def _duration(seconds: int | None) -> dict[str, int] | None:
    if not seconds:
        return None
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    return {"days": days, "hours": hours, "minutes": minutes, "seconds": secs}


def _schedule_schema(
    kind: ScheduleKind, others: list[SelectOptionDict] | None = None
) -> vol.Schema:
    """Felterne for gentagelsen. others: de opgaver, en opfølgende opgave kan følge efter."""
    others = others or []
    match kind:
        case ScheduleKind.NONE:
            return vol.Schema({vol.Required("due"): DateTimeSelector()})
        case ScheduleKind.INTERVAL:
            return vol.Schema(
                {
                    vol.Required("every", default=1): _number(1, 365),
                    vol.Required("unit", default=IntervalUnit.WEEK.value): _select(
                        "unit", [u.value for u in IntervalUnit]
                    ),
                    vol.Required("from", default=IntervalFrom.DUE.value): _select(
                        "from", [f.value for f in IntervalFrom]
                    ),
                }
            )
        case ScheduleKind.WEEKLY:
            return vol.Schema(
                {vol.Required("weekdays"): _select("weekdays", WEEKDAYS, multiple=True)}
            )
        case ScheduleKind.YEARLY:
            return vol.Schema(
                {vol.Required("dates"): TextSelector(TextSelectorConfig(multiple=True))}
            )
        case ScheduleKind.AFTER:
            return vol.Schema(
                {
                    vol.Required("after"): SelectSelector(
                        SelectSelectorConfig(
                            options=others, mode=SelectSelectorMode.DROPDOWN
                        )
                    ),
                    vol.Optional("delay"): DurationSelector(),
                }
            )


def _schedule_from_input(
    kind: ScheduleKind, user_input: dict[str, Any]
) -> dict[str, Any]:
    schedule: dict[str, Any] = {"kind": kind.value}
    match kind:
        case ScheduleKind.NONE:
            due = dt_util.parse_datetime(user_input["due"])
            if due is None:
                raise ValueError(f"Ugyldigt tidspunkt: {user_input['due']!r}")
            if due.tzinfo is None:
                due = due.replace(tzinfo=dt_util.get_default_time_zone())
            schedule["due"] = dt_util.as_utc(due).isoformat()
        case ScheduleKind.INTERVAL:
            schedule |= {k: user_input[k] for k in ("every", "unit", "from")}
        case ScheduleKind.WEEKLY:
            schedule["weekdays"] = [WEEKDAYS.index(d) for d in user_input["weekdays"]]
        case ScheduleKind.YEARLY:
            schedule["dates"] = [d.strip() for d in user_input["dates"] if d.strip()]
        case ScheduleKind.AFTER:
            schedule["after"] = user_input["after"]
            schedule["delay"] = _seconds(user_input.get("delay")) or 0
    return schedule


def _schedule_suggested(schedule: Mapping[str, Any]) -> dict[str, Any]:
    match schedule.get("kind"):
        case ScheduleKind.NONE.value:
            due = dt_util.parse_datetime(schedule["due"])
            assert due is not None
            return {"due": dt_util.as_local(due).strftime("%Y-%m-%d %H:%M:%S")}
        case ScheduleKind.INTERVAL.value:
            return {k: schedule[k] for k in ("every", "unit", "from")}
        case ScheduleKind.WEEKLY.value:
            return {"weekdays": [WEEKDAYS[d] for d in schedule["weekdays"]]}
        case ScheduleKind.YEARLY.value:
            return {"dates": list(schedule["dates"])}
        case ScheduleKind.AFTER.value:
            suggested: dict[str, Any] = {"after": schedule["after"]}
            if (delay := _duration(schedule.get("delay"))) is not None:
                suggested["delay"] = delay
            return suggested
    return {}


class ChoreSubentryFlow(ConfigSubentryFlow):
    """Tilføj eller ret en opgave: én formular og derefter gentagelsens felter."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._kind = ScheduleKind.WEEKLY
        self._subentry: ConfigSubentry | None = None
        self._condition: ConditionKind | None = None

    def _persons(self) -> list[SelectOptionDict]:
        return [
            SelectOptionDict(value=sid, label=subentry.title)
            for sid, subentry in self._get_entry().subentries.items()
            if subentry.subentry_type == SUBENTRY_PERSON
        ]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if not self._persons():
            return self.async_abort(reason="no_persons")
        return self._main("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._subentry = self._get_reconfigure_subentry()
        return self._main("reconfigure", user_input)

    def _main_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("name"): TextSelector(),
                vol.Optional("description"): TextSelector(
                    TextSelectorConfig(multiline=True)
                ),
                vol.Required("points", default=DEFAULT_POINTS): _number(0, 100),
                vol.Required("assignees"): SelectSelector(
                    SelectSelectorConfig(
                        options=self._persons(),
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(
                    "assignment", default=Assignment.LEAST_POINTS.value
                ): _select("assignment", [a.value for a in Assignment]),
                vol.Required(REPEAT, default=ScheduleKind.WEEKLY.value): _select(
                    "repeat", [k.value for k in ScheduleKind]
                ),
                vol.Optional("due_time"): TimeSelector(),
                vol.Optional("notify_before"): DurationSelector(),
                vol.Required(ADVANCED): section(
                    vol.Schema(
                        {
                            vol.Required(
                                "approval", default=ApprovalMode.AUTO.value
                            ): _select("approval", [a.value for a in ApprovalMode]),
                            vol.Optional("complete_window"): DurationSelector(),
                            vol.Required(
                                "builtin_notify", default=False
                            ): BooleanSelector(),
                            vol.Required(CONDITION, default=NO_CONDITION): _select(
                                "condition",
                                [NO_CONDITION, *(k.value for k in ConditionKind)],
                            ),
                        }
                    ),
                    {"collapsed": True},
                ),
            }
        )

    @callback
    def _main(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        existing = dict(self._subentry.data) if self._subentry else {}
        if user_input is not None:
            advanced = user_input.get(ADVANCED, {})
            selected = list(user_input["assignees"])
            # Rækkefølgen bruges til rotation: behold den for dem, der stadig er valgt.
            ordered = [p for p in existing.get("assignees", []) if p in selected]
            self._data = existing | {
                "name": user_input["name"].strip(),
                "description": user_input.get("description") or None,
                "points": user_input["points"],
                "assignees": ordered + [p for p in selected if p not in ordered],
                "assignment": user_input["assignment"],
                "due_time": user_input.get("due_time") or None,
                "notify_before": _seconds(user_input.get("notify_before")),
                "approval": advanced.get("approval", ApprovalMode.AUTO.value),
                "complete_window": _seconds(advanced.get("complete_window")),
                "builtin_notify": advanced.get("builtin_notify", False),
            }
            self._kind = ScheduleKind(user_input[REPEAT])
            condition = advanced.get(CONDITION, NO_CONDITION)
            self._condition = None if condition == NO_CONDITION else ConditionKind(condition)
            return self._schedule(None)

        suggested: dict[str, Any] = {}
        if existing:
            suggested = {
                k: existing[k]
                for k in ("name", "description", "points", "assignees", "assignment", "due_time")
                if existing.get(k) is not None
            }
            suggested[REPEAT] = existing["schedule"]["kind"]
            if (notify := _duration(existing.get("notify_before"))) is not None:
                suggested["notify_before"] = notify
            advanced_suggested: dict[str, Any] = {
                "approval": existing.get("approval", ApprovalMode.AUTO.value),
                "builtin_notify": existing.get("builtin_notify", False),
                CONDITION: (existing.get(CONDITION) or {}).get("kind", NO_CONDITION),
            }
            if (window := _duration(existing.get("complete_window"))) is not None:
                advanced_suggested["complete_window"] = window
            suggested[ADVANCED] = advanced_suggested
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                self._main_schema(), suggested
            ),
        )

    async def async_step_schedule_none(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return self._schedule(user_input)

    async def async_step_schedule_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return self._schedule(user_input)

    async def async_step_schedule_weekly(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return self._schedule(user_input)

    async def async_step_schedule_yearly(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return self._schedule(user_input)

    async def async_step_schedule_after(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return self._schedule(user_input)

    def _other_chores(self) -> list[SelectOptionDict]:
        own = self._subentry.subentry_id if self._subentry else None
        return [
            SelectOptionDict(value=sid, label=subentry.title)
            for sid, subentry in self._get_entry().subentries.items()
            if subentry.subentry_type == SUBENTRY_CHORE and sid != own
        ]

    @callback
    def _schedule(self, user_input: dict[str, Any] | None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            try:
                data = self._data | {
                    "schedule": _schedule_from_input(self._kind, user_input)
                }
                if self._condition is None:
                    data[CONDITION] = None
                Chore.from_dict("ny", data)
            except (KeyError, ValueError) as err:
                errors["base"] = "invalid"
                placeholders["error"] = str(err)
            else:
                self._data = data
                if self._condition is not None:
                    return self._condition_step(None)
                return self._finish()

        suggested: dict[str, Any] = {}
        previous = self._data.get("schedule", {})
        if previous.get("kind") == self._kind.value:
            suggested = _schedule_suggested(previous)
        if user_input is not None:
            suggested = user_input
        return self.async_show_form(
            step_id=f"schedule_{self._kind.value}",
            data_schema=self.add_suggested_values_to_schema(
                _schedule_schema(self._kind, self._other_chores()), suggested
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    @callback
    def _finish(self) -> SubentryFlowResult:
        data = self._data
        if self._subentry is None:
            return self.async_create_entry(title=data["name"], data=data)
        return self.async_update_and_abort(
            self._get_entry(), self._subentry, title=data["name"], data=data
        )

    async def async_step_condition_calendar(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return self._condition_step(user_input)

    async def async_step_condition_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return self._condition_step(user_input)

    @callback
    def _condition_step(self, user_input: dict[str, Any] | None) -> SubentryFlowResult:
        kind = self._condition
        assert kind is not None
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            condition = {"kind": kind.value, **user_input}
            if kind is ConditionKind.CALENDAR:
                condition["keywords"] = [
                    k.strip() for k in user_input.get("keywords", []) if k.strip()
                ]
            try:
                data = self._data | {CONDITION: condition}
                Chore.from_dict("ny", data)
            except (KeyError, ValueError) as err:
                errors["base"] = "invalid"
                placeholders["error"] = str(err)
            else:
                self._data = data
                return self._finish()

        if kind is ConditionKind.CALENDAR:
            schema = vol.Schema(
                {
                    vol.Required("calendar"): EntitySelector(
                        EntitySelectorConfig(domain="calendar")
                    ),
                    vol.Required("keywords"): TextSelector(
                        TextSelectorConfig(multiple=True)
                    ),
                    vol.Required("check_time", default=DEFAULT_CHECK_TIME): TimeSelector(),
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required("entity"): EntitySelector(),
                    vol.Required("active_state", default="on"): TextSelector(),
                    vol.Required("check_time", default=DEFAULT_CHECK_TIME): TimeSelector(),
                }
            )
        previous = self._data.get(CONDITION) or {}
        suggested = (
            {k: v for k, v in previous.items() if k != "kind"}
            if previous.get("kind") == kind.value
            else {}
        )
        if user_input is not None:
            suggested = user_input
        return self.async_show_form(
            step_id=f"condition_{kind.value}",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
            description_placeholders=placeholders,
        )
