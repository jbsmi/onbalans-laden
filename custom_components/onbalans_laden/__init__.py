"""Onbalans Laden - laad Victron accu's op basis van Tenergy onbalansprijzen."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_SCAN_INTERVAL, CONF_URL, DEFAULT_GENERAL, DOMAIN, MIN_SCAN_INTERVAL, PLATFORMS
from .controller import ChargeController
from .coordinator import PriceCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    opts = {**DEFAULT_GENERAL, **entry.options}
    interval = max(MIN_SCAN_INTERVAL, int(opts[CONF_SCAN_INTERVAL]))
    coordinator = PriceCoordinator(hass, opts[CONF_URL], interval)
    await coordinator.async_config_entry_first_refresh()

    controller = ChargeController(hass, entry, coordinator)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller

    _remove_stale_block_entities(hass, entry, len(controller.blocks))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await controller.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


def _remove_stale_block_entities(hass: HomeAssistant, entry: ConfigEntry, n_blocks: int) -> None:
    """Entiteiten van tijdblokken die niet meer bestaan (indeling verkleind) opruimen."""
    reg = er.async_get(hass)
    prefix = f"{entry.entry_id}_blok"
    for ent in er.async_entries_for_config_entry(reg, entry.entry_id):
        uid = ent.unique_id
        if not uid.startswith(prefix):
            continue
        nr = uid[len(prefix):].split("_", 1)[0]
        if nr.isdigit() and int(nr) > n_blocks:
            reg.async_remove(ent.entity_id)


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    controller: ChargeController | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if controller is not None and controller.consume_live_update():
        return  # wijziging via dashboard-entiteit: al live toegepast, niet herladen
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    controller: ChargeController = hass.data[DOMAIN][entry.entry_id]
    controller.async_stop()
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok
