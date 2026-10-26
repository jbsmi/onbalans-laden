"""Laadmodus per tijdblok (laden onder of boven de drempel)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import B_MODE, DOMAIN, MODE_ABOVE, MODE_BELOW
from .controller import ChargeController
from .entity import BlockEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    c: ChargeController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(BlockModeSelect(c, i) for i in range(len(c.blocks)))


class BlockModeSelect(BlockEntity, SelectEntity):
    _attr_options = [MODE_BELOW, MODE_ABOVE]
    _attr_icon = "mdi:swap-vertical"

    def __init__(self, c: ChargeController, idx: int) -> None:
        super().__init__(c, idx, B_MODE, "select")

    @property
    def current_option(self) -> str | None:
        return self.raw_value

    async def async_select_option(self, option: str) -> None:
        await self.async_set(option)
