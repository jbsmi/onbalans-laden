"""Gemeenschappelijke entiteit-basis."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_UPDATE
from .controller import ChargeController


class OnbalansEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: ChargeController, key: str) -> None:
        self.controller = controller
        entry_id = controller.entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Onbalans Laden",
            manufacturer="Smit-ICTdiensten",
            model="Victron MultiPlus laadsturing (Tenergy onbalans)",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_UPDATE.format(self.controller.entry.entry_id), self.async_write_ha_state
            )
        )
