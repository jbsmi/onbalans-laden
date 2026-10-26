"""Sensoren voor Onbalans Laden."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    B_DELAY_OFF,
    B_DELAY_ON,
    B_ENABLED,
    B_END,
    B_MODE,
    B_OFFSET_HIGH,
    B_OFFSET_LOW,
    B_POWER,
    B_START,
    B_THRESHOLD,
    DOMAIN,
    MODE_ABOVE,
    ST_CHARGING,
    ST_DISABLED,
    ST_IDLE,
    ST_NO_BLOCK,
    ST_NO_PRICE,
    ST_PENDING_START,
    ST_PENDING_STOP,
)
from .controller import ChargeController
from .entity import OnbalansEntity



async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    c: ChargeController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PriceSensor(c),
            StatusSensor(c),
            BlockSensor(c),
            ThresholdSensor(c),
            PowerSensor(c),
        ]
    )


class PriceSensor(OnbalansEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:scale-unbalanced"

    def __init__(self, c: ChargeController) -> None:
        super().__init__(c, "onbalansprijs")
        self._attr_native_unit_of_measurement = c.unit.label
        self._attr_suggested_display_precision = c.unit.decimals

    @property
    def available(self) -> bool:
        return self.controller.price is not None

    @property
    def native_value(self) -> float | None:
        return self.controller.unit.show(self.controller.price)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.controller.coordinator.data
        latest = data.latest if data else None
        attrs: dict[str, Any] = {
            "tijd": self.controller.price_time,
            "leeftijd_minuten": self.controller.price_age_min,
            "opgehaald": data.fetched.isoformat() if data else None,
        }
        u = self.controller.unit
        attrs["eenheid"] = u.label
        if latest:
            attrs.update(
                {
                    "afnemen": u.show(latest.afnemen),
                    "invoeden": u.show(latest.invoeden),
                    "opregelen": latest.opregelen,
                    "afregelen": latest.afregelen,
                    "noodvermogen_op": latest.noodvermogen_op,
                    "noodvermogen_af": latest.noodvermogen_af,
                    "volgnummer": latest.volgnummer,
                    "laatste_minuten": [
                        {"tijd": r.tijd, "afnemen": u.show(r.afnemen), "invoeden": u.show(r.invoeden)} for r in data.rows[:15]
                    ],
                }
            )
        return attrs


class StatusSensor(OnbalansEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [ST_DISABLED, ST_IDLE, ST_PENDING_START, ST_CHARGING, ST_PENDING_STOP, ST_NO_BLOCK, ST_NO_PRICE]
    _attr_icon = "mdi:battery-charging-outline"

    def __init__(self, c: ChargeController) -> None:
        super().__init__(c, "status")

    @property
    def native_value(self) -> str:
        return self.controller.decision.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "reden": self.controller.decision.reason,
            "testmodus": self.controller.test_mode,
            "automatisch": self.controller.auto_enabled,
            "laatste_acties": list(self.controller.history),
        }


class BlockSensor(OnbalansEntity, SensorEntity):
    _attr_icon = "mdi:clock-outline"

    def __init__(self, c: ChargeController) -> None:
        super().__init__(c, "tijdblok")

    @property
    def native_value(self) -> str | None:
        b = self.controller.active_block
        if b is None:
            return None
        return f"{self.controller.block_index + 1}: {b[B_START]}-{b[B_END]}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        b = self.controller.active_block or {}
        u = self.controller.unit
        return {
            "eenheid": u.label,
            "actief": b.get(B_ENABLED),
            "modus": ("laden boven drempel" if b.get(B_MODE) == MODE_ABOVE else "laden onder drempel") if b else None,
            "drempel": u.show(b.get(B_THRESHOLD)),
            "offset_onder": u.show(b.get(B_OFFSET_LOW)),
            "offset_boven": u.show(b.get(B_OFFSET_HIGH)),
            "vertraging_start_s": b.get(B_DELAY_ON),
            "vertraging_stop_s": b.get(B_DELAY_OFF),
            "vermogen_kw": b.get(B_POWER),
            "actief_nr": None if self.controller.block_index is None else self.controller.block_index + 1,
            # gestructureerd overzicht, gebruikt door de tabel op het dashboard
            "blokken": [
                {
                    "nr": i + 1,
                    "start": x[B_START],
                    "eind": x[B_END],
                    "actief": x[B_ENABLED],
                    "modus": x[B_MODE],
                    "drempel": u.show(x[B_THRESHOLD]),
                    "offset_onder": u.show(x[B_OFFSET_LOW]),
                    "offset_boven": u.show(x[B_OFFSET_HIGH]),
                    "vertraging_start": x[B_DELAY_ON],
                    "vertraging_stop": x[B_DELAY_OFF],
                    "vermogen_kw": x[B_POWER],
                }
                for i, x in enumerate(self.controller.blocks)
            ],
            "alle_blokken": [
                f"{i + 1}: {x[B_START]}-{x[B_END]} {'≥' if x[B_MODE] == MODE_ABOVE else '≤'}{u.show(x[B_THRESHOLD]):g} "
                f"(-{u.show(x[B_OFFSET_LOW]):g}/+{u.show(x[B_OFFSET_HIGH]):g}) {u.label} "
                f"{x[B_POWER]:g}kW{'' if x[B_ENABLED] else ' uit'}"
                for i, x in enumerate(self.controller.blocks)
            ],
        }


class ThresholdSensor(OnbalansEntity, SensorEntity):
    _attr_icon = "mdi:arrow-collapse-vertical"

    def __init__(self, c: ChargeController) -> None:
        super().__init__(c, "drempel")
        self._attr_native_unit_of_measurement = c.unit.label
        self._attr_suggested_display_precision = c.unit.decimals

    @property
    def native_value(self) -> float | None:
        b = self.controller.active_block
        return self.controller.unit.show(b[B_THRESHOLD]) if b else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        b = self.controller.active_block
        if not b:
            return {}
        low = float(b[B_THRESHOLD]) - float(b[B_OFFSET_LOW])
        high = float(b[B_THRESHOLD]) + float(b[B_OFFSET_HIGH])
        u = self.controller.unit
        low, high = u.show(low), u.show(high)
        if b[B_MODE] == MODE_ABOVE:
            return {"startgrens": high, "stopgrens": low, "eenheid": u.label}
        return {"startgrens": low, "stopgrens": high, "eenheid": u.label}


class PowerSensor(OnbalansEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, c: ChargeController) -> None:
        super().__init__(c, "laadvermogen")

    @property
    def native_value(self) -> float:
        return self.controller.sm.active_power_kw if self.controller.sm.charging else 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        lim = self.controller.limits
        vals = lim.values_for(self.native_value)
        return {
            **vals,
            "max_kw": lim.max_kw,
            "max_kw_dc_zijde": round(lim.max_dc_kw, 2),
            "max_kw_ac_aansluiting": round(lim.max_ac_kw, 2),
        }
