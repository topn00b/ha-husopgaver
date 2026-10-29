"""Registrering af dashboardkortet husopgaver-card som frontend-modul."""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

URL_BASE = "/husopgaver_static"
CARD_FILE = "husopgaver-card.js"
CARD_DIR = Path(__file__).parent / "frontend"


async def async_register_card(hass: HomeAssistant) -> bool:
    """Server kortet og indlæs det i frontend. Kræver ingen ressource-opsætning.

    Returnerer False, hvis frontend ikke kører (fx i tests).
    """
    if "frontend" not in hass.config.components or hass.http is None:
        return False
    # Importeres først her, så integrationen kan indlæses uden frontend.
    from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415
    from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_BASE, str(CARD_DIR), cache_headers=False)]
    )
    # Versionen i adressen sørger for, at en opdatering ikke hentes fra cache.
    add_extra_js_url(hass, f"{URL_BASE}/{CARD_FILE}?v={integration.version}")
    return True
