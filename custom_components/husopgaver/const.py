"""Konstanter for Husopgaver."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

DOMAIN: Final = "husopgaver"

STORAGE_KEY: Final = DOMAIN
STORAGE_VERSION: Final = 1
STORAGE_MINOR_VERSION: Final = 1
SAVE_DELAY: Final = 5

SUBENTRY_PERSON: Final = "person"
SUBENTRY_CHORE: Final = "chore"

# Nøgle for den fælles forekomst, når strategien ikke er "each".
SHARED_OCCURRENCE: Final = "_shared"

DEFAULT_POINTS: Final = 1
DEFAULT_UPCOMING_DAYS: Final = 2
DEFAULT_POINTS_WINDOW_DAYS: Final = 30
DEFAULT_ABSENCE_HOURS: Final = 24
DEFAULT_UNDO_MINUTES: Final = 10

CONF_UPCOMING_DAYS: Final = "upcoming_days"
CONF_POINTS_WINDOW_DAYS: Final = "points_window_days"
CONF_ABSENCE_HOURS: Final = "absence_hours"
CONF_UNDO_MINUTES: Final = "undo_minutes"
CONF_ALL_LIST: Final = "all_list"

EVENT_DUE: Final = "husopgaver_due"
EVENT_OVERDUE: Final = "husopgaver_overdue"
EVENT_REMINDER: Final = "husopgaver_reminder"
EVENT_COMPLETED: Final = "husopgaver_completed"
EVENT_SKIPPED: Final = "husopgaver_skipped"
EVENT_NOT_NEEDED: Final = "husopgaver_not_needed"
EVENT_APPROVAL_REQUESTED: Final = "husopgaver_approval_requested"
EVENT_REJECTED: Final = "husopgaver_rejected"

# Knapper i notifikationer: "<præfiks><log_id>".
ACTION_APPROVE_PREFIX: Final = "HUSOPGAVER_APPROVE_"
ACTION_REJECT_PREFIX: Final = "HUSOPGAVER_REJECT_"


class Notification(StrEnum):
    """Tidsbestemte notifikationer for en forekomst, i rækkefølge."""

    REMINDER = "reminder"
    DUE = "due"
    OVERDUE = "overdue"


class Assignment(StrEnum):
    """Hvordan en opgave tildeles."""

    FIXED = "fixed"
    ROUND_ROBIN = "round_robin"
    LEAST_POINTS = "least_points"
    EACH = "each"


class ScheduleKind(StrEnum):
    """Typer af gentagelse."""

    NONE = "none"
    INTERVAL = "interval"
    WEEKLY = "weekly"
    YEARLY = "yearly"


class IntervalUnit(StrEnum):
    """Enhed for intervalgentagelse."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class IntervalFrom(StrEnum):
    """Hvorfra næste forfald regnes."""

    DUE = "due"
    COMPLETION = "completion"


class ApprovalMode(StrEnum):
    """Om afkrydsning kræver godkendelse."""

    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"


class ConditionKind(StrEnum):
    """Typer af betingelse for om en opgave er nødvendig."""

    CALENDAR = "calendar"
    ENTITY = "entity"


class ConditionState(StrEnum):
    """Resultat af seneste tjek af betingelsen."""

    ACTIVE = "active"
    NOT_NEEDED = "not_needed"
    UNKNOWN = "unknown"


class ChoreStatus(StrEnum):
    """Beregnet status for en forekomst."""

    UPCOMING = "upcoming"
    DUE = "due"
    OVERDUE = "overdue"
    PENDING_APPROVAL = "pending_approval"


class LogAction(StrEnum):
    """Handlinger i udførelsesloggen."""

    COMPLETED = "completed"
    SKIPPED = "skipped"
    NOT_NEEDED = "not_needed"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    UNDONE = "undone"
    SETTLED = "settled"
