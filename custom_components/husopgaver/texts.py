"""Tekster i notifikationer og todo-beskrivelser.

HA's oversættelser dækker kun brugerfladens egne felter, så tekster, der
sendes eller vises som indhold, ligger her.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

_TEXTS: dict[str, dict[str, str]] = {
    "da": {
        "reminder": "{chore} skal snart laves",
        "due": "{chore} skal laves nu",
        "overdue": "{chore} er overskredet",
        "approval": "{person} har lavet {chore}. Godkend?",
        "approve": "Godkend",
        "reject": "Afvis",
        "points": "{points} point",
        "status_upcoming": "Kommende",
        "status_due": "Forfalden",
        "status_overdue": "Overskredet",
        "status_pending_approval": "Afventer godkendelse",
        "with_person": "{chore} ({person})",
    },
    "en": {
        "reminder": "{chore} is coming up",
        "due": "{chore} is due now",
        "overdue": "{chore} is overdue",
        "approval": "{person} did {chore}. Approve?",
        "approve": "Approve",
        "reject": "Reject",
        "points": "{points} points",
        "status_upcoming": "Upcoming",
        "status_due": "Due",
        "status_overdue": "Overdue",
        "status_pending_approval": "Awaiting approval",
        "with_person": "{chore} ({person})",
    },
}


def text(hass: HomeAssistant, key: str, **placeholders: Any) -> str:
    """Tekst på HA's sprog. Andre sprog end dansk får engelsk."""
    language = hass.config.language.split("-")[0]
    return _TEXTS.get(language, _TEXTS["en"])[key].format(**placeholders)
