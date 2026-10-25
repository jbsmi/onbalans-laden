"""Binaire sensor: wordt er geladen?"""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .controller import ChargeController
from .entity import OnbalansEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    c: ChargeController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ChargingBinarySensor(c)])


class ChargingBinarySensor(OnbalansEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, c: ChargeController) -> None:
        super().__init__(c, "laden")

    @property
    def is_on(self) -> bool:
        return self.controller.sm.charging
