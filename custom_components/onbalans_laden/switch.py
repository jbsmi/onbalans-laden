"""Schakelaars: automatische sturing en testmodus."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .controller import ChargeController
from .entity import OnbalansEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    c: ChargeController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AutoSwitch(c), TestModeSwitch(c)])


class AutoSwitch(OnbalansEntity, SwitchEntity, RestoreEntity):
    _attr_icon = "mdi:robot"

    def __init__(self, c: ChargeController) -> None:
        super().__init__(c, "automatisch")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        self.controller.auto_enabled = last.state == "on" if last else True

    @property
    def is_on(self) -> bool:
        return self.controller.auto_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.controller.async_set_auto(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.controller.async_set_auto(False)


class TestModeSwitch(OnbalansEntity, SwitchEntity, RestoreEntity):
    """Aan = commando's alleen loggen, niet via MQTT versturen."""

    _attr_icon = "mdi:test-tube"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, c: ChargeController) -> None:
        super().__init__(c, "testmodus")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        self.controller.test_mode = last.state == "on" if last else True

    @property
    def is_on(self) -> bool:
        return self.controller.test_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.controller.async_set_test_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.controller.async_set_test_mode(False)
