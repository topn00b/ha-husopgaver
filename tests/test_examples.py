"""Eksemplerne skal kunne indlæses og passe til integrationens entiteter og events."""

from __future__ import annotations

from pathlib import Path
import re

import pytest
import yaml

from custom_components.husopgaver import const

EXAMPLES = Path(__file__).parent.parent / "examples"
EVENTS = {v for k, v in vars(const).items() if k.startswith("EVENT_")}
ENTITY = re.compile(r"\b(?:todo|sensor|calendar)\.husopgaver\w*")
VALID_ENTITY = re.compile(
    r"^(todo\.husopgaver_\w+|sensor\.husopgaver_\w+_point|calendar\.husopgaver)$"
)


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.yaml")), ids=lambda p: p.name)
def test_yaml_loads(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert yaml.safe_load(text)
    assert "\t" not in text
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip(" "))
        assert indent % 2 == 0, f"{path.name}: {line!r}"


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*")), ids=lambda p: p.name)
def test_entities_and_events_exist(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for entity in ENTITY.findall(text):
        assert VALID_ENTITY.match(entity), entity
    for event in re.findall(r"event_type:\s*(\S+)", text):
        assert event in EVENTS, event
    for service in re.findall(r"action:\s*husopgaver\.(\w+)", text):
        assert service in {"complete", "skip", "approve", "reject", "undo", "settle"}, service
