"""Fælles fixtures."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest

from homeassistant.util import dt as dt_util


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Gør custom_components/husopgaver tilgængelig i alle tests."""


@pytest.fixture
async def copenhagen(hass):
    """Kør testen i HA's tidszone for Danmark."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    return hass


@pytest.fixture
def cph_tz():
    """Sæt HA's tidszone til Danmark i rene funktionstests uden hass."""
    previous = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(ZoneInfo("Europe/Copenhagen"))
    yield
    dt_util.set_default_time_zone(previous)
