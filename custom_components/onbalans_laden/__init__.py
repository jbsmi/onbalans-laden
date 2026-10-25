"""Onbalans Laden - laad Victron accu's op basis van Tenergy onbalansprijzen."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await controller.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    controller: ChargeController = hass.data[DOMAIN][entry.entry_id]
    controller.async_stop()
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok
