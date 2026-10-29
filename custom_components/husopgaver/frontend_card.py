"""Registrering af dashboardkortet husopgaver-card som frontend-modul."""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

URL_BASE = "/husopgaver_static"
CARD_FILE = "husopgaver-card.js"
CARD_DIR = Path(__file__).parent / "frontend"
PANEL_URL = "husopgaver"
PANEL_ELEMENT = "husopgaver-panel"


async def async_register_card(hass: HomeAssistant) -> bool:
    """Server kortet, indlæs det i frontend og vis det i sidemenuen.

    Kræver ingen ressource- eller dashboard-opsætning.

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
    url = f"{URL_BASE}/{CARD_FILE}?v={integration.version}"
    add_extra_js_url(hass, url)
    await async_register_panel(hass, url)
    return True


async def async_register_panel(hass: HomeAssistant, module_url: str) -> None:
    """Punktet "Husopgaver" i sidemenuen for alle brugere, med kortet på hele siden.

    Så er der intet dashboard at sætte op.
    """
    from homeassistant.components import panel_custom  # noqa: PLC0415

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title="Husopgaver",
        sidebar_icon="mdi:broom",
        module_url=module_url,
        require_admin=False,
        config={},
    )
