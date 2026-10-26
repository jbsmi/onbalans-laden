"""Getalwaarden per tijdblok (drempel, offsets, vertragingen, vermogen)."""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import B_DELAY_OFF, B_DELAY_ON, B_OFFSET_HIGH, B_OFFSET_LOW, B_POWER, B_THRESHOLD, DOMAIN
from .controller import ChargeController
from .entity import BlockEntity

PRICE_UNIT = "prijs"  # wordt vervangen door de gekozen prijseenheid
PRICE_KEYS = (B_THRESHOLD, B_OFFSET_LOW, B_OFFSET_HIGH)

# key: (min, max, stap, eenheid, icoon)
SPECS: dict[str, tuple[float, float, float, str, str]] = {
    B_THRESHOLD: (-10000, 10000, 0.01, PRICE_UNIT, "mdi:arrow-collapse-vertical"),
    B_OFFSET_LOW: (0, 5000, 0.01, PRICE_UNIT, "mdi:arrow-down-bold-outline"),
    B_OFFSET_HIGH: (0, 5000, 0.01, PRICE_UNIT, "mdi:arrow-up-bold-outline"),
    B_DELAY_ON: (0, 3600, 1, UnitOfTime.SECONDS, "mdi:timer-play-outline"),
    B_DELAY_OFF: (0, 3600, 1, UnitOfTime.SECONDS, "mdi:timer-stop-outline"),
    B_POWER: (0, 0, 0.1, UnitOfPower.KILO_WATT, "mdi:lightning-bolt"),  # max = installatielimiet
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    c: ChargeController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(BlockNumber(c, i, key) for i in range(len(c.blocks)) for key in SPECS)


class BlockNumber(BlockEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, c: ChargeController, idx: int, key: str) -> None:
        super().__init__(c, idx, key, "number")
        mn, mx, step, unit, icon = SPECS[key]
        self._attr_native_min_value = mn
        self._attr_native_max_value = mx
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        if key == B_POWER:
            self._attr_device_class = NumberDeviceClass.POWER
        if key in PRICE_KEYS:
            u = c.unit
            self._attr_native_unit_of_measurement = u.label
            self._attr_native_min_value = mn * u.factor
            self._attr_native_max_value = mx * u.factor
            self._attr_native_step = u.step

    @property
    def native_max_value(self) -> float:
        if self.key == B_POWER:
            return round(self.controller.limits.max_kw, 1)
        return self._attr_native_max_value

    @property
    def native_value(self) -> float | None:
        v = self.raw_value
        if v is None:
            return None
        return self.controller.unit.show(v) if self.key in PRICE_KEYS else float(v)

    async def async_set_native_value(self, value: float) -> None:
        await self.async_set(value)
