"""Begin- en eindtijd per tijdblok."""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import B_END, B_START, DOMAIN
from .controller import ChargeController
from .entity import BlockEntity
from .logic import parse_hhmm


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    c: ChargeController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(BlockTime(c, i, key) for i in range(len(c.blocks)) for key in (B_START, B_END))


class BlockTime(BlockEntity, TimeEntity):
    def __init__(self, c: ChargeController, idx: int, key: str) -> None:
        super().__init__(c, idx, key, "time")
        self._attr_icon = "mdi:clock-start" if key == B_START else "mdi:clock-end"

    @property
    def native_value(self) -> time | None:
        v = self.raw_value
        return parse_hhmm(v) if v else None

    async def async_set_value(self, value: time) -> None:
        await self.async_set(f"{value.hour:02d}:{value.minute:02d}")
