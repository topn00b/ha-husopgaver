"""Fælles fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Gør custom_components/husopgaver tilgængelig i alle tests."""


@pytest.fixture
async def copenhagen(hass):
    """Kør testen i HA's tidszone for Danmark."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    return hass
