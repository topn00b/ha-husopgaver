"""Todo-lister: én per person, "Alle opgaver" og afventende godkendelser."""

from __future__ import annotations

from datetime import date, datetime

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from . import HusopgaverConfigEntry
from .const import CONF_ALL_LIST, ChoreStatus, ConditionState, LogAction, ScheduleKind
from .coordinator import HusopgaverCoordinator, OccurrenceView, validation_error
from .entity import HusopgaverEntity
from .models import Chore, LogEntry, Person
from .points import pending_entries
from .schedule import local_date, local_datetime
from .texts import text

_LOG_PREFIX = "log:"
_PENDING_PREFIX = "pending:"
_DESCRIPTION_SEPARATOR = "\n\n"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HusopgaverConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[TodoListEntity] = [
        PersonTodoList(coordinator, person) for person in coordinator.persons.values()
    ]
    if entry.options.get(CONF_ALL_LIST, False):
        entities.append(AllTodoList(coordinator))
    entities.append(ApprovalTodoList(coordinator))
    async_add_entities(entities)


def _item_due(chore: Chore, due: datetime) -> date | datetime:
    if chore.due_time is None:
        return local_date(due)
    return dt_util.as_local(due)


def _as_utc(value: datetime) -> datetime:
    """Et tidspunkt fra en todo-liste som UTC. Uden tidszone er det lokal tid."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_util.get_default_time_zone())
    return dt_util.as_utc(value)


def _due_from_item(chore: Chore, value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return _as_utc(value)
    return local_datetime(value, chore.due_time)


def _occurrence_uid(entry: LogEntry) -> str | None:
    """Uid for den forekomst, en afkrydsning gjaldt (samme som OccurrenceView.uid)."""
    snapshot = entry.previous_state
    if snapshot is None or entry.occurrence is None:
        return None
    due = snapshot["occurrence"].get("next_due")
    if due is None:
        return None
    return f"{entry.chore_id}|{entry.occurrence}|{due}"


class _ChoreTodoList(HusopgaverEntity, TodoListEntity):
    """Fælles logik for lister med opgaver."""

    def __init__(
        self, coordinator: HusopgaverCoordinator, key: str, owner: Person | None
    ) -> None:
        super().__init__(coordinator, key)
        self._owner = owner
        self._done_uids: dict[str, str] = {}

    def _summary(self, chore: Chore, person_id: str | None) -> str:
        if self._owner is not None or person_id is None:
            return chore.name
        person = self.coordinator.persons.get(person_id)
        if person is None:
            return chore.name
        return text(self.hass, "with_person", chore=chore.name, person=person.name)

    def _generated(
        self, points: int, status: ChoreStatus | None, unknown: bool = False
    ) -> str:
        parts = [text(self.hass, "points", points=points)]
        if status is not None:
            parts.append(text(self.hass, f"status_{status.value}"))
        if unknown:
            parts.append(text(self.hass, "condition_unknown"))
        return " · ".join(parts)

    def _view_generated(self, view: OccurrenceView) -> str:
        unknown = view.occurrence.condition_state is ConditionState.UNKNOWN
        return self._generated(view.chore.points, view.status, unknown)

    def _description(self, view: OccurrenceView) -> str:
        chore = view.chore
        generated = self._view_generated(view)
        if chore.description:
            return f"{generated}{_DESCRIPTION_SEPARATOR}{chore.description}"
        return generated

    def _includes(self, view: OccurrenceView) -> bool:
        return self._owner is None or view.person_id == self._owner.id

    def _includes_entry(self, entry: LogEntry) -> bool:
        return self._owner is None or entry.person_id == self._owner.id

    def _update_from_coordinator(self) -> None:
        now = dt_util.utcnow()
        items: list[TodoItem] = []
        views = sorted(self.coordinator.occurrences(now), key=lambda v: v.due)
        for view in views:
            if not self._includes(view) or view.occurrence.pending_log_id is not None:
                continue
            if now < self.coordinator.visible_from(view.chore, view.due):
                continue
            items.append(
                TodoItem(
                    summary=self._summary(view.chore, view.person_id),
                    uid=view.uid,
                    status=TodoItemStatus.NEEDS_ACTION,
                    due=_item_due(view.chore, view.due),
                    description=self._description(view),
                )
            )
        done = self._done_today(now)
        self._done_uids = {uid: log_id for uid, log_id, _ in done}
        self._attr_todo_items = items + [item for _, _, item in done]

    def _done_today(self, now: datetime) -> list[tuple[str, str, TodoItem]]:
        """Dagens afkrydsninger som (uid, log-id, punkt).

        Punktet beholder forekomstens uid, så et ekstra tryk rammer et udført
        punkt (no-op) i stedet for et, der er forsvundet. Fjernes fluebenet,
        fortrydes afkrydsningen.
        """
        log = self.coordinator.storage.log
        undone = {e.ref for e in log if e.action is LogAction.UNDONE}
        pending = {e.id for e in pending_entries(log)}
        today = local_datetime(local_date(now))
        items = []
        for entry in reversed(log):
            if entry.timestamp < today:
                break
            if entry.id in undone or not self._includes_entry(entry):
                continue
            if entry.action is LogAction.PENDING and entry.id in pending:
                status: ChoreStatus | None = ChoreStatus.PENDING_APPROVAL
            elif entry.action in (LogAction.COMPLETED, LogAction.APPROVED):
                status = None
            else:
                continue
            chore = self.coordinator.chores.get(entry.chore_id or "")
            if chore is None:
                continue
            uid = _occurrence_uid(entry) or f"{_LOG_PREFIX}{entry.id}"
            items.append(
                (uid, entry.id, TodoItem(
                    summary=self._summary(chore, entry.person_id),
                    uid=uid,
                    status=TodoItemStatus.COMPLETED,
                    completed=dt_util.as_local(entry.timestamp),
                    description=self._generated(entry.points, status),
                ))
            )
        return items

    def _view(self, uid: str | None) -> OccurrenceView | None:
        now = dt_util.utcnow()
        return next(
            (v for v in self.coordinator.occurrences(now) if v.uid == uid), None
        )

    def _credit_person(self, view: OccurrenceView) -> str | None:
        """Hvem afkrydsningen krediteres."""
        if self._owner is not None:
            return self._owner.id
        if view.key in self.coordinator.persons:
            return view.key  # "each": forekomstens person
        return None  # den tildelte

    async def async_update_todo_item(self, item: TodoItem) -> None:
        user_id = self._context.user_id if self._context else None
        uid = item.uid or ""
        if (log_id := self._done_uids.get(uid)) is not None:
            if item.status == TodoItemStatus.NEEDS_ACTION:
                self.coordinator.undo(log_id=log_id, user_id=user_id)
            return

        view = self._view(uid)
        if item.status == TodoItemStatus.COMPLETED:
            if view is None:
                return  # allerede krydset af, fx dobbelt tryk
            self.coordinator.complete(
                view.chore.id,
                person_id=self._credit_person(view),
                user_id=user_id,
                expected_due=view.occurrence.next_due,
            )
            return

        if view is None:
            raise validation_error("item_gone")
        if item.due is not None and item.due != _item_due(view.chore, view.due):
            self.coordinator.set_due(
                view.chore.id, view.key, _due_from_item(view.chore, item.due)
            )
        description = item.description or None
        if description is not None:
            # Den genererede første linje (point og status) er ikke en del af opgaven.
            generated = self._view_generated(view)
            if description.startswith(generated):
                description = (
                    description.removeprefix(generated)
                    .removeprefix(_DESCRIPTION_SEPARATOR)
                    .strip()
                    or None
                )
        self.coordinator.update_chore_text(
            view.chore.id, item.summary or view.chore.name, description
        )

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Kun engangsopgaver kan slettes fra listen."""
        views = [self._view(uid) for uid in uids]
        if any(
            v is None or v.chore.schedule.kind is not ScheduleKind.NONE for v in views
        ):
            raise validation_error("cannot_delete")
        for view in views:
            assert view is not None
            self.coordinator.delete_chore(view.chore.id)


class PersonTodoList(_ChoreTodoList):
    """Personens opgaver. Afkrydsning krediteres listens ejer."""

    _attr_translation_key = "person"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
        | TodoListEntityFeature.SET_DUE_DATETIME_ON_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, coordinator: HusopgaverCoordinator, person: Person) -> None:
        super().__init__(coordinator, f"todo_{person.id}", person)
        self._attr_translation_placeholders = {"person": person.name}
        self.entity_id = f"todo.husopgaver_{slugify(person.name)}"

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Et nyt punkt bliver en engangsopgave hos ejeren med 1 point."""
        assert self._owner is not None
        value = item.due or dt_util.now().date()
        if isinstance(value, datetime):
            due = _as_utc(value)
            due_time = dt_util.as_local(due).time().replace(second=0, microsecond=0)
        else:
            due, due_time = local_datetime(value), None
        self.coordinator.create_one_off(
            self._owner.id, item.summary or "", item.description or None, due, due_time
        )


class AllTodoList(_ChoreTodoList):
    """Alle opgaver. Afkrydsning krediteres den tildelte."""

    _attr_translation_key = "all"
    _attr_supported_features = (
        TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
        | TodoListEntityFeature.SET_DUE_DATETIME_ON_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, coordinator: HusopgaverCoordinator) -> None:
        super().__init__(coordinator, "todo_all", None)
        self.entity_id = "todo.husopgaver_alle"


class ApprovalTodoList(HusopgaverEntity, TodoListEntity):
    """Afventende godkendelser. Afkrydsning godkender."""

    _attr_translation_key = "approvals"
    _attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM

    def __init__(self, coordinator: HusopgaverCoordinator) -> None:
        super().__init__(coordinator, "todo_approvals")
        self.entity_id = "todo.husopgaver_godkendelse"

    def _update_from_coordinator(self) -> None:
        items = []
        for entry in pending_entries(self.coordinator.storage.log):
            chore = self.coordinator.chores.get(entry.chore_id or "")
            person = self.coordinator.persons.get(entry.person_id)
            name = chore.name if chore else str(entry.chore_id)
            items.append(
                TodoItem(
                    summary=text(
                        self.hass,
                        "with_person",
                        chore=name,
                        person=person.name if person else entry.person_id,
                    ),
                    uid=f"{_PENDING_PREFIX}{entry.id}",
                    status=TodoItemStatus.NEEDS_ACTION,
                    description=text(self.hass, "points", points=entry.points),
                )
            )
        self._attr_todo_items = items

    async def async_update_todo_item(self, item: TodoItem) -> None:
        if item.status != TodoItemStatus.COMPLETED:
            return
        user_id = self._context.user_id if self._context else None
        self.coordinator.approve(
            log_id=(item.uid or "").removeprefix(_PENDING_PREFIX), user_id=user_id
        )

