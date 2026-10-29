"""Historik og statistik over længere tid, ud fra udførelsesloggen."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from .const import LogAction
from .coordinator import HusopgaverCoordinator
from .models import LogEntry
from .points import credited_entries, pending_entries
from .schedule import local_date, local_datetime, month_start, week_start

# Handlinger, der vises i historikken. "undone" og fortrudte poster udelades;
# en godkendt afkrydsning vises som den godkendte post.
_SHOWN = frozenset(
    {
        LogAction.COMPLETED,
        LogAction.APPROVED,
        LogAction.PENDING,
        LogAction.SKIPPED,
        LogAction.NOT_NEEDED,
        LogAction.REJECTED,
        LogAction.SETTLED,
    }
)
MAX_ENTRIES = 500
# Op til så mange dage vises statistikken per uge, ellers per måned.
WEEKLY_UP_TO_DAYS = 120


def _bucket_start(moment: datetime, weekly: bool) -> date:
    start = week_start(moment) if weekly else month_start(moment)
    return local_date(start)


def _buckets(since: datetime, now: datetime, weekly: bool) -> list[date]:
    """Alle uger eller måneder i perioden, også dem uden point."""
    buckets: list[date] = []
    current = _bucket_start(since, weekly)
    last = _bucket_start(now, weekly)
    while current <= last:
        buckets.append(current)
        if weekly:
            current += timedelta(days=7)
        else:
            year, month = divmod(current.month, 12)
            current = date(current.year + year, month + 1, 1)
    return buckets


def build_history(
    coordinator: HusopgaverCoordinator,
    now: datetime,
    days: int | None,
    person_id: str | None = None,
) -> dict[str, Any]:
    """Historik og statistik for de seneste `days` dage (None: alt)."""
    log = coordinator.storage.log
    if days is None:
        first = min((e.timestamp for e in log), default=now)
        since = local_datetime(local_date(first))
    else:
        since = local_datetime(local_date(now) - timedelta(days=days - 1))

    undone = {e.ref for e in log if e.action is LogAction.UNDONE}
    still_pending = {e.id for e in pending_entries(log)}

    def wanted(entry: LogEntry) -> bool:
        return entry.timestamp >= since and (
            person_id is None or entry.person_id == person_id
        )

    def chore_name(entry: LogEntry) -> str | None:
        chore = coordinator.chores.get(entry.chore_id or "")
        return chore.name if chore else None

    entries: list[dict[str, Any]] = []
    for entry in reversed(log):
        if len(entries) >= MAX_ENTRIES:
            break
        if not wanted(entry) or entry.action not in _SHOWN or entry.id in undone:
            continue
        if entry.action is LogAction.PENDING and entry.id not in still_pending:
            continue  # vises som den godkendte eller afviste post
        entries.append(
            {
                "id": entry.id,
                "timestamp": entry.timestamp.isoformat(),
                "action": entry.action.value,
                "chore_id": entry.chore_id,
                "chore_name": chore_name(entry),
                "person_id": entry.person_id,
                "points": entry.points
                if entry.action in (LogAction.COMPLETED, LogAction.APPROVED, LogAction.PENDING)
                else 0,
            }
        )

    credited = [e for e in credited_entries(log) if wanted(e)]
    weekly = days is not None and days <= WEEKLY_UP_TO_DAYS
    buckets = _buckets(since, now, weekly)
    per_bucket: dict[date, dict[str, int]] = {b: defaultdict(int) for b in buckets}
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"points": 0, "count": 0})
    per_chore: dict[str, dict[str, Any]] = {}
    for entry in credited:
        pid = entry.person_id or ""
        bucket = _bucket_start(entry.timestamp, weekly)
        if bucket in per_bucket:
            per_bucket[bucket][pid] += entry.points
        totals[pid]["points"] += entry.points
        totals[pid]["count"] += 1
        key = entry.chore_id or ""
        row = per_chore.setdefault(
            key, {"chore_id": entry.chore_id, "chore_name": chore_name(entry), "counts": defaultdict(int)}
        )
        row["counts"][pid] += 1

    chores = sorted(
        (
            {**row, "counts": dict(row["counts"]), "total": sum(row["counts"].values())}
            for row in per_chore.values()
        ),
        key=lambda row: (-row["total"], row["chore_name"] or ""),
    )
    return {
        "since": since.isoformat(),
        "days": days,
        "bucket": "week" if weekly else "month",
        "entries": entries,
        "truncated": len(entries) >= MAX_ENTRIES,
        "totals": {pid: dict(values) for pid, values in totals.items()},
        "buckets": [
            {"start": bucket.isoformat(), "points": dict(per_bucket[bucket])}
            for bucket in buckets
        ],
        "chores": chores,
    }
