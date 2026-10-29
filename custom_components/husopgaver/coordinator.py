"""Koordinator: runtime-tilstand, timere, events, godkendelse og fortryd.

Alle handlinger er synkrone callbacks i event-loopet. De ændrer tilstanden via
storage, der kun gemmer ved faktiske ændringer, og planlægger derefter én timer
til det næste relevante tidspunkt. Der polles aldrig.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
import json
import logging
from typing import Any
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, State, callback
from homeassistant.exceptions import ConfigEntryError, ServiceValidationError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .assignment import assign, each_assignees, is_absent
from .const import (
    ACTION_APPROVE_PREFIX,
    ACTION_REJECT_PREFIX,
    CONF_ABSENCE_HOURS,
    CONF_POINTS_WINDOW_DAYS,
    CONF_UNDO_MINUTES,
    CONF_UPCOMING_DAYS,
    DEFAULT_ABSENCE_HOURS,
    DEFAULT_POINTS_WINDOW_DAYS,
    DEFAULT_UNDO_MINUTES,
    DEFAULT_UPCOMING_DAYS,
    DOMAIN,
    EVENT_APPROVAL_REQUESTED,
    EVENT_COMPLETED,
    EVENT_DUE,
    EVENT_OVERDUE,
    EVENT_REJECTED,
    EVENT_REMINDER,
    EVENT_SKIPPED,
    SHARED_OCCURRENCE,
    SUBENTRY_CHORE,
    SUBENTRY_PERSON,
    ApprovalMode,
    Assignment,
    ChoreStatus,
    LogAction,
    Notification,
)
from .models import Chore, ChoreState, LogEntry, Occurrence, Person
from .points import credited_entries, pending_entries
from .schedule import due_window, first_due, local_date, local_datetime, next_due, status
from .storage import HusopgaverStorage

_LOGGER = logging.getLogger(__name__)

EVENT_MOBILE_APP_ACTION = "mobile_app_notification_action"

_NOTIFICATION_EVENTS = {
    Notification.REMINDER: EVENT_REMINDER,
    Notification.DUE: EVENT_DUE,
    Notification.OVERDUE: EVENT_OVERDUE,
}

# Handlinger, der kan fortrydes, og som tæller som "seneste handling" på en forekomst.
_UNDOABLE = frozenset(
    {LogAction.COMPLETED, LogAction.APPROVED, LogAction.PENDING, LogAction.SKIPPED}
)
_STATE_CHANGING = _UNDOABLE | {LogAction.REJECTED, LogAction.NOT_NEEDED}

# Notifikationstekster. Integrationens oversættelser dækker kun brugerfladen.
_TEXTS: dict[str, dict[str, str]] = {
    "da": {
        Notification.REMINDER: "{chore} skal snart laves",
        Notification.DUE: "{chore} skal laves nu",
        Notification.OVERDUE: "{chore} er overskredet",
        "approval": "{person} har lavet {chore}. Godkend?",
        "approve": "Godkend",
        "reject": "Afvis",
    },
    "en": {
        Notification.REMINDER: "{chore} is coming up",
        Notification.DUE: "{chore} is due now",
        Notification.OVERDUE: "{chore} is overdue",
        "approval": "{person} did {chore}. Approve?",
        "approve": "Approve",
        "reject": "Reject",
    },
}


def _error(key: str, **placeholders: Any) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders={k: str(v) for k, v in placeholders.items()},
    )


def _schedule_signature(chore: Chore) -> str:
    return json.dumps(
        {
            "schedule": chore.schedule.to_dict(),
            "due_time": None if chore.due_time is None else chore.due_time.isoformat(),
        },
        sort_keys=True,
    )


def effective_due(occurrence: Occurrence) -> datetime | None:
    """Forfald med udsættelse. None: engangsopgaven er udført."""
    due = occurrence.next_due
    if due is None:
        return None
    if occurrence.snoozed_until is not None and occurrence.snoozed_until > due:
        return occurrence.snoozed_until
    return due


class HusopgaverCoordinator:
    """Ejer runtime-tilstanden og alle handlinger på opgaverne."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, storage: HusopgaverStorage
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.storage = storage
        self.persons: dict[str, Person] = self._parse(SUBENTRY_PERSON, Person)
        self.chores: dict[str, Chore] = self._parse(SUBENTRY_CHORE, Chore)
        options = entry.options
        self.upcoming_window = timedelta(
            days=options.get(CONF_UPCOMING_DAYS, DEFAULT_UPCOMING_DAYS)
        )
        self.points_window = timedelta(
            days=options.get(CONF_POINTS_WINDOW_DAYS, DEFAULT_POINTS_WINDOW_DAYS)
        )
        self.absence_threshold = timedelta(
            hours=options.get(CONF_ABSENCE_HOURS, DEFAULT_ABSENCE_HOURS)
        )
        self.undo_window = timedelta(
            minutes=options.get(CONF_UNDO_MINUTES, DEFAULT_UNDO_MINUTES)
        )
        self._listeners: list[CALLBACK_TYPE] = []
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._unsub_action: CALLBACK_TYPE | None = None

    def _parse[T: (Person, Chore)](self, kind: str, cls: type[T]) -> dict[str, T]:
        parsed: dict[str, T] = {}
        for subentry in self.entry.subentries.values():
            if subentry.subentry_type != kind:
                continue
            try:
                parsed[subentry.subentry_id] = cls.from_dict(
                    subentry.subentry_id, dict(subentry.data)
                )
            except (KeyError, TypeError, ValueError) as err:
                raise ConfigEntryError(
                    f"Ugyldig {kind} {subentry.title!r}: {err}"
                ) from err
        return parsed

    # Livscyklus

    @callback
    def async_start(self) -> None:
        now = dt_util.utcnow()
        for chore_id in set(self.storage.chore_states) - set(self.chores):
            self.storage.remove_chore_state(chore_id)
        for chore in self.chores.values():
            self._reconcile(chore, now)
        self._unsub_action = self.hass.bus.async_listen(
            EVENT_MOBILE_APP_ACTION, self._handle_mobile_action
        )
        self._refresh(now)

    @callback
    def async_stop(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None
        if self._unsub_action is not None:
            self._unsub_action()
            self._unsub_action = None

    @callback
    def async_add_listener(self, listener: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Kaldes ved enhver ændring og ved hvert tidspunkt, hvor status kan skifte."""
        self._listeners.append(listener)

        @callback
        def remove() -> None:
            self._listeners.remove(listener)

        return remove

    def _occurrence_keys(self, chore: Chore) -> list[str]:
        if chore.assignment is Assignment.EACH:
            return each_assignees(chore, self.persons)
        return [SHARED_OCCURRENCE]

    @callback
    def _reconcile(self, chore: Chore, now: datetime) -> None:
        """Bring tilstanden i overensstemmelse med opgavens konfiguration."""
        state = self.storage.chore_states.get(chore.id) or ChoreState()
        signature = _schedule_signature(chore)
        schedule_changed = state.schedule_sig != signature

        occurrences: dict[str, Occurrence] = {}
        for key in self._occurrence_keys(chore):
            occ = state.occurrences.get(key)
            if occ is None or schedule_changed:
                due = first_due(chore, now)
                fresh = Occurrence(
                    next_due=due,
                    assignee=None,
                    anchor=None if due is None else local_date(due),
                )
                # En afventende godkendelse og tildelingen bevares.
                occ = (
                    fresh
                    if occ is None
                    else replace(
                        fresh,
                        assignee=occ.assignee,
                        pending_log_id=occ.pending_log_id,
                    )
                )
            occurrences[key] = occ

        rr_index = state.rr_index
        for key, occ in occurrences.items():
            if key != SHARED_OCCURRENCE:
                occurrences[key] = replace(occ, assignee=key)
                continue
            active = each_assignees(chore, self.persons)
            fixed_moved = (
                chore.assignment is Assignment.FIXED
                and active
                and occ.assignee != active[0]
            )
            if occ.assignee not in active or fixed_moved:
                assignee, rr_index = self._assign(chore, rr_index, now)
                occurrences[key] = replace(occ, assignee=assignee)

        self.storage.set_chore_state(
            chore.id,
            ChoreState(
                occurrences=occurrences, rr_index=rr_index, schedule_sig=signature
            ),
        )

    # Opslag

    def _person_state(self, person: Person) -> State | None:
        if person.person_entity is None:
            return None
        return self.hass.states.get(person.person_entity)

    def _assign(self, chore: Chore, rr_index: int, now: datetime) -> tuple[str | None, int]:
        absent = {
            pid
            for pid in chore.assignees
            if (person := self.persons.get(pid)) is not None
            and is_absent(
                person, self._person_state(person), now, self.absence_threshold
            )
        }
        return assign(
            chore,
            self.persons,
            absent,
            rr_index,
            credited_entries(self.storage.log),
            now,
            self.points_window,
        )

    def person_for_user(self, user_id: str | None) -> Person | None:
        """Personen, hvis person-entitet er knyttet til HA-brugeren."""
        if user_id is None:
            return None
        for person in self.persons.values():
            state = self._person_state(person)
            if state is not None and state.attributes.get("user_id") == user_id:
                return person
        return None

    def _chore(self, chore_id: str) -> Chore:
        chore = self.chores.get(chore_id)
        if chore is None:
            raise _error("unknown_chore", chore=chore_id)
        return chore

    def _occurrence(
        self, chore: Chore, person_id: str | None
    ) -> tuple[str, Occurrence]:
        if chore.assignment is Assignment.EACH:
            if person_id is None:
                raise _error("person_required", chore=chore.name)
            key = person_id
        else:
            key = SHARED_OCCURRENCE
        occ = self.storage.chore_states[chore.id].occurrences.get(key)
        if occ is None:
            raise _error("not_assignee", chore=chore.name, person=self._name(key))
        return key, occ

    def _name(self, person_id: str | None) -> str:
        person = self.persons.get(person_id) if person_id else None
        return person.name if person else str(person_id)

    def status(self, chore: Chore, occurrence: Occurrence, now: datetime) -> ChoreStatus | None:
        return status(
            chore, effective_due(occurrence), now, occurrence.pending_log_id is not None
        )

    # Handlinger

    @callback
    def complete(
        self,
        chore_id: str,
        person_id: str | None = None,
        user_id: str | None = None,
        expected_due: datetime | None = None,
    ) -> LogEntry | None:
        """Kryds en forekomst af. None: den er allerede krydset af (no-op).

        Ved "each" vælger person_id forekomsten. Ellers krediteres person_id,
        eller den tildelte, hvis den ikke er angivet. expected_due er det
        forfald, brugeren så; er forekomsten rykket videre, sker der intet.
        """
        now = dt_util.utcnow()
        chore = self._chore(chore_id)
        key, occ = self._occurrence(chore, person_id)
        due = effective_due(occ)
        if occ.pending_log_id is not None or due is None:
            return None
        if expected_due is not None and expected_due != occ.next_due:
            return None
        doer = person_id or occ.assignee
        if doer is None or doer not in self.persons:
            raise _error("unknown_person", person=doer)
        self._check_window(chore, due, now)

        person = self.persons[doer]
        needs_approval = chore.approval is ApprovalMode.ALWAYS or (
            chore.approval is ApprovalMode.AUTO and person.requires_approval
        )
        entry = LogEntry(
            id=uuid.uuid4().hex,
            person_id=doer,
            timestamp=now,
            action=LogAction.PENDING if needs_approval else LogAction.COMPLETED,
            points=chore.points,
            chore_id=chore.id,
            occurrence=key,
            by_user=user_id,
            previous_state=self._snapshot(chore, key),
        )
        if needs_approval:
            self.storage.add_log_entry(entry)
            self._set_occurrence(chore, key, replace(occ, pending_log_id=entry.id))
            self._fire(EVENT_APPROVAL_REQUESTED, chore, doer, due, entry.id)
            self._notify_approvers(chore, person, entry)
        else:
            self._advance(chore, key, entry, completed_at=now, now=now)
            self._fire(EVENT_COMPLETED, chore, doer, due, entry.id)
        self._refresh(now)
        return entry

    def _check_window(self, chore: Chore, due: datetime, now: datetime) -> None:
        """Afvis afkrydsning, før forekomsten er synlig eller inden for vinduet."""
        due_from, _ = due_window(chore, due)
        if chore.complete_window is not None:
            opens = due_from - chore.complete_window
        else:
            opens = local_datetime(local_date(due_from) - self.upcoming_window)
        if now < opens:
            raise _error(
                "too_early",
                chore=chore.name,
                time=dt_util.as_local(opens).strftime("%d-%m-%Y %H:%M"),
            )

    @callback
    def skip(
        self, chore_id: str, person_id: str | None = None, user_id: str | None = None
    ) -> LogEntry:
        now = dt_util.utcnow()
        chore = self._chore(chore_id)
        key, occ = self._occurrence(chore, person_id)
        due = effective_due(occ)
        if due is None:
            raise _error("already_done", chore=chore.name)
        if occ.pending_log_id is not None:
            raise _error("pending_approval", chore=chore.name)
        doer = occ.assignee
        if doer is None:
            raise _error("unknown_person", person=None)
        entry = LogEntry(
            id=uuid.uuid4().hex,
            person_id=doer,
            timestamp=now,
            action=LogAction.SKIPPED,
            chore_id=chore.id,
            occurrence=key,
            by_user=user_id,
            previous_state=self._snapshot(chore, key),
        )
        self._advance(chore, key, entry, completed_at=now, now=now)
        self._fire(EVENT_SKIPPED, chore, doer, due, entry.id)
        self._refresh(now)
        return entry

    @callback
    def reassign(self, chore_id: str, person_id: str) -> None:
        chore = self._chore(chore_id)
        if chore.assignment is Assignment.EACH:
            raise _error("each_reassign", chore=chore.name)
        if person_id not in each_assignees(chore, self.persons):
            raise _error("not_assignee", chore=chore.name, person=self._name(person_id))
        key, occ = self._occurrence(chore, None)
        self._set_occurrence(chore, key, replace(occ, assignee=person_id))
        self._refresh(dt_util.utcnow())

    @callback
    def snooze(
        self, chore_id: str, duration: timedelta, person_id: str | None = None
    ) -> None:
        now = dt_util.utcnow()
        chore = self._chore(chore_id)
        key, occ = self._occurrence(chore, person_id)
        if occ.next_due is None:
            raise _error("already_done", chore=chore.name)
        if duration <= timedelta(0):
            raise _error("invalid_duration")
        # Notifikationerne sendes igen på det nye tidspunkt.
        self._set_occurrence(
            chore, key, replace(occ, snoozed_until=now + duration, notified=())
        )
        self._refresh(now)

    @callback
    def approve(
        self,
        log_id: str | None = None,
        chore_id: str | None = None,
        user_id: str | None = None,
    ) -> LogEntry:
        now = dt_util.utcnow()
        approver = self._check_approver(user_id)
        pending = self._pending(log_id, chore_id)
        chore = self.chores.get(pending.chore_id or "")
        key = pending.occurrence
        occ = self._pending_occurrence(chore, key, pending)
        entry = LogEntry(
            id=uuid.uuid4().hex,
            person_id=pending.person_id,
            timestamp=now,
            action=LogAction.APPROVED,
            points=pending.points,
            chore_id=pending.chore_id,
            occurrence=key,
            ref=pending.id,
            by_user=user_id,
            previous_state=None if occ is None else self._snapshot(chore, key),
        )
        if chore is not None and key is not None and occ is not None:
            due = effective_due(occ)
            # Næste forfald regnes fra, hvornår opgaven blev lavet, ikke godkendt.
            self._advance(chore, key, entry, completed_at=pending.timestamp, now=now)
            self._fire(EVENT_COMPLETED, chore, pending.person_id, due, entry.id)
        else:
            # Opgaven er slettet eller ændret: pointene gives stadig.
            self.storage.add_log_entry(entry)
        _LOGGER.debug("%s godkendte %s", approver.name, pending.id)
        self._clear_approval_notifications(pending.id)
        self._refresh(now)
        return entry

    @callback
    def reject(
        self,
        log_id: str | None = None,
        chore_id: str | None = None,
        user_id: str | None = None,
    ) -> LogEntry:
        now = dt_util.utcnow()
        self._check_approver(user_id)
        pending = self._pending(log_id, chore_id)
        chore = self.chores.get(pending.chore_id or "")
        key = pending.occurrence
        occ = self._pending_occurrence(chore, key, pending)
        entry = LogEntry(
            id=uuid.uuid4().hex,
            person_id=pending.person_id,
            timestamp=now,
            action=LogAction.REJECTED,
            chore_id=pending.chore_id,
            occurrence=key,
            ref=pending.id,
            by_user=user_id,
            previous_state=None if occ is None else self._snapshot(chore, key),
        )
        self.storage.add_log_entry(entry)
        if chore is not None and key is not None and occ is not None:
            # Forekomsten vender tilbage hos samme person med samme forfald.
            self._set_occurrence(chore, key, replace(occ, pending_log_id=None))
            self._fire(EVENT_REJECTED, chore, pending.person_id, effective_due(occ), entry.id)
        self._clear_approval_notifications(pending.id)
        self._refresh(now)
        return entry

    @callback
    def undo(
        self,
        log_id: str | None = None,
        chore_id: str | None = None,
        user_id: str | None = None,
    ) -> LogEntry:
        """Fortryd den seneste handling på en forekomst inden for fortryd-vinduet."""
        now = dt_util.utcnow()
        log = self.storage.log
        undone = {e.ref for e in log if e.action is LogAction.UNDONE}

        if log_id is not None:
            target = self.storage.get_log_entry(log_id)
            if target is None:
                raise _error("unknown_log", log_id=log_id)
        else:
            chore = self._chore(chore_id or "")
            candidates = [
                e
                for e in log
                if e.chore_id == chore.id
                and e.action in _UNDOABLE
                and e.id not in undone
            ]
            if not candidates:
                raise _error("nothing_to_undo", chore=chore.name)
            target = candidates[-1]

        if target.action not in _UNDOABLE or target.id in undone:
            raise _error("not_undoable")
        later = [
            e
            for e in log[log.index(target) + 1 :]
            if e.chore_id == target.chore_id
            and e.occurrence == target.occurrence
            and e.action in _STATE_CHANGING
            and e.id not in undone
        ]
        if later:
            raise _error("undo_not_latest", chore=self._chore_name(target.chore_id))
        if now - target.timestamp > self.undo_window:
            raise _error("undo_expired")

        entry = LogEntry(
            id=uuid.uuid4().hex,
            person_id=target.person_id,
            timestamp=now,
            action=LogAction.UNDONE,
            chore_id=target.chore_id,
            occurrence=target.occurrence,
            ref=target.id,
            by_user=user_id,
        )
        self.storage.add_log_entry(entry)
        chore = self.chores.get(target.chore_id or "")
        if (
            chore is not None
            and target.occurrence is not None
            and target.previous_state is not None
        ):
            self._restore(chore, target.occurrence, target.previous_state)
        if target.action is LogAction.PENDING:
            self._clear_approval_notifications(target.id)
        self._refresh(now)
        return entry

    @callback
    def settle(self, person_id: str, user_id: str | None = None) -> LogEntry:
        """Udbetaling: nulstil "siden udbetaling". Der slettes intet."""
        if person_id not in self.persons:
            raise _error("unknown_person", person=person_id)
        entry = LogEntry(
            id=uuid.uuid4().hex,
            person_id=person_id,
            timestamp=dt_util.utcnow(),
            action=LogAction.SETTLED,
            by_user=user_id,
        )
        self.storage.add_log_entry(entry)
        self._notify_listeners()
        return entry

    # Hjælpere til handlingerne

    def _chore_name(self, chore_id: str | None) -> str:
        chore = self.chores.get(chore_id or "")
        return chore.name if chore else str(chore_id)

    def _check_approver(self, user_id: str | None) -> Person:
        person = self.person_for_user(user_id)
        if person is None or not person.can_approve:
            raise _error("not_approver")
        return person

    def _pending(self, log_id: str | None, chore_id: str | None) -> LogEntry:
        pending = pending_entries(self.storage.log)
        if log_id is not None:
            match = [e for e in pending if e.id == log_id]
            if not match:
                raise _error("not_pending", log_id=log_id)
            return match[0]
        chore = self._chore(chore_id or "")
        match = [e for e in pending if e.chore_id == chore.id]
        if not match:
            raise _error("no_pending", chore=chore.name)
        if len(match) > 1:
            raise _error("ambiguous_pending", chore=chore.name)
        return match[0]

    def _pending_occurrence(
        self, chore: Chore | None, key: str | None, pending: LogEntry
    ) -> Occurrence | None:
        """Forekomsten, der venter på netop denne godkendelse, hvis den stadig findes."""
        if chore is None or key is None:
            return None
        occ = self.storage.chore_states[chore.id].occurrences.get(key)
        if occ is None or occ.pending_log_id != pending.id:
            return None
        return occ

    def _snapshot(self, chore: Chore, key: str) -> dict[str, Any]:
        state = self.storage.chore_states[chore.id]
        return {
            "occurrence": state.occurrences[key].to_dict(),
            "rr_index": state.rr_index,
        }

    @callback
    def _restore(self, chore: Chore, key: str, snapshot: dict[str, Any]) -> None:
        state = self.storage.chore_states[chore.id]
        if key not in state.occurrences:
            return  # personen er ikke længere med på opgaven
        restored = state.with_occurrence(key, Occurrence.from_dict(snapshot["occurrence"]))
        self.storage.set_chore_state(
            chore.id, replace(restored, rr_index=int(snapshot["rr_index"]))
        )

    @callback
    def _set_occurrence(self, chore: Chore, key: str, occurrence: Occurrence) -> None:
        state = self.storage.chore_states[chore.id]
        self.storage.set_chore_state(chore.id, state.with_occurrence(key, occurrence))

    @callback
    def _advance(
        self,
        chore: Chore,
        key: str,
        entry: LogEntry,
        completed_at: datetime,
        now: datetime,
    ) -> None:
        """Log handlingen, beregn næste forfald og den næste tildeling."""
        self.storage.add_log_entry(entry)
        state = self.storage.chore_states[chore.id]
        occ = state.occurrences[key]
        assert occ.next_due is not None
        rr_index, assignee = state.rr_index, occ.assignee
        if chore.assignment is not Assignment.EACH:
            assignee, rr_index = self._assign(chore, rr_index, now)
        new_occ = replace(
            occ,
            next_due=next_due(chore, occ.next_due, completed_at, now, occ.anchor),
            assignee=assignee,
            snoozed_until=None,
            pending_log_id=None,
            notified=(),
            condition_state=None,
        )
        self.storage.set_chore_state(
            chore.id, replace(state.with_occurrence(key, new_occ), rr_index=rr_index)
        )

    # Timer, events og notifikationer

    @callback
    def _refresh(self, now: datetime) -> None:
        """Send forfaldne notifikationer, planlæg næste timer og giv entiteterne besked."""
        # Ved midnat skifter "i dag" og ugens point, også uden andre ændringer.
        wakeup = local_datetime(local_date(now) + timedelta(days=1))
        for chore in self.chores.values():
            state = self.storage.chore_states.get(chore.id)
            if state is None:
                continue
            for key, occ in state.occurrences.items():
                times = [
                    (kind, at)
                    for kind, at in self._notification_times(chore, occ)
                    if kind not in occ.notified
                ]
                passed = [(kind, at) for kind, at in times if at <= now]
                if passed:
                    # Efter en genstart sendes kun den seneste, fx ikke både
                    # "forfalden" og "overskredet" på én gang.
                    latest = max(passed, key=lambda item: item[1])[0]
                    self._fire_notification(latest, chore, occ)
                    self._set_occurrence(
                        chore,
                        key,
                        replace(
                            occ,
                            notified=(*occ.notified, *(kind for kind, _ in passed)),
                        ),
                    )
                wakeup = min([wakeup, *(at for _, at in times if at > now)])

        if self._unsub_timer is not None:
            self._unsub_timer()
        self._unsub_timer = async_track_point_in_utc_time(
            self.hass, self._handle_timer, wakeup
        )
        self._notify_listeners()

    @callback
    def _handle_timer(self, now: datetime) -> None:
        self._unsub_timer = None
        self._refresh(dt_util.utcnow())

    def _notification_times(
        self, chore: Chore, occ: Occurrence
    ) -> list[tuple[Notification, datetime]]:
        due = effective_due(occ)
        if due is None or occ.pending_log_id is not None:
            return []
        due_from, overdue_from = due_window(chore, due)
        times = [(Notification.DUE, due_from), (Notification.OVERDUE, overdue_from)]
        if chore.notify_before is not None:
            times.insert(0, (Notification.REMINDER, due_from - chore.notify_before))
        return times

    @callback
    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            listener()

    @callback
    def _fire(
        self,
        event_type: str,
        chore: Chore,
        person_id: str | None,
        due: datetime | None,
        log_id: str | None = None,
    ) -> None:
        person = self.persons.get(person_id) if person_id else None
        data: dict[str, Any] = {
            "chore_id": chore.id,
            "chore_name": chore.name,
            "person_id": person_id,
            "person_name": person.name if person else None,
            "person_entity": person.person_entity if person else None,
            "notify_target": person.notify_target if person else None,
            "points": chore.points,
            "due": None if due is None else due.isoformat(),
        }
        if log_id is not None:
            data["log_id"] = log_id
        self.hass.bus.async_fire(event_type, data)

    @callback
    def _fire_notification(
        self, kind: Notification, chore: Chore, occ: Occurrence
    ) -> None:
        self._fire(_NOTIFICATION_EVENTS[kind], chore, occ.assignee, effective_due(occ))
        person = self.persons.get(occ.assignee) if occ.assignee else None
        if chore.builtin_notify and person is not None and person.notify_target:
            self._send(
                person.notify_target,
                {
                    "title": chore.name,
                    "message": self._text(kind).format(chore=chore.name),
                    "data": {"tag": f"husopgaver_{chore.id}"},
                },
            )

    def _text(self, key: str) -> str:
        language = self.hass.config.language.split("-")[0]
        return _TEXTS.get(language, _TEXTS["en"])[key]

    @callback
    def _send(self, notify_target: str, data: dict[str, Any]) -> None:
        service = notify_target.removeprefix("notify.")
        if not self.hass.services.has_service("notify", service):
            _LOGGER.warning("Notify-tjenesten %s findes ikke", notify_target)
            return
        self.hass.async_create_task(
            self.hass.services.async_call("notify", service, data),
            eager_start=True,
        )

    def _approvers(self) -> list[Person]:
        return [
            p for p in self.persons.values() if p.can_approve and p.notify_target and p.active
        ]

    @callback
    def _notify_approvers(self, chore: Chore, person: Person, entry: LogEntry) -> None:
        if not chore.builtin_notify:
            return
        for approver in self._approvers():
            assert approver.notify_target is not None
            self._send(
                approver.notify_target,
                {
                    "title": chore.name,
                    "message": self._text("approval").format(
                        person=person.name, chore=chore.name
                    ),
                    "data": {
                        "tag": f"husopgaver_{entry.id}",
                        "actions": [
                            {
                                "action": f"{ACTION_APPROVE_PREFIX}{entry.id}",
                                "title": self._text("approve"),
                            },
                            {
                                "action": f"{ACTION_REJECT_PREFIX}{entry.id}",
                                "title": self._text("reject"),
                            },
                        ],
                    },
                },
            )

    @callback
    def _clear_approval_notifications(self, log_id: str) -> None:
        for approver in self._approvers():
            assert approver.notify_target is not None
            self._send(
                approver.notify_target,
                {"message": "clear_notification", "data": {"tag": f"husopgaver_{log_id}"}},
            )

    @callback
    def _handle_mobile_action(self, event: Event) -> None:
        action = str(event.data.get("action", ""))
        handlers: dict[str, Callable[..., LogEntry]] = {
            ACTION_APPROVE_PREFIX: self.approve,
            ACTION_REJECT_PREFIX: self.reject,
        }
        for prefix, handler in handlers.items():
            if not action.startswith(prefix):
                continue
            log_id = action.removeprefix(prefix)
            if self.storage.get_log_entry(log_id) is None:
                return  # en anden installations knap
            try:
                # Brugeren er den, telefonen er logget ind som.
                handler(log_id=log_id, user_id=event.context.user_id)
            except ServiceValidationError as err:
                _LOGGER.warning("Knappen i notifikationen blev afvist: %s", err)
            return
