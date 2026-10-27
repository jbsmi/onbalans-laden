"""Keuzelijsten: laadmodus en sturing per tijdblok, plus de algemene sturing."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    B_CONTROL,
    B_MODE,
    BLOCK_CONTROLS,
    CTRL_AUTO,
    CTRL_PER_BLOCK,
    DOMAIN,
    GLOBAL_CONTROLS,
    MODE_ABOVE,
    MODE_BELOW,
)
from .controller import ChargeController
from .entity import BlockEntity, OnbalansEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    c: ChargeController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            GlobalControlSelect(c),
            *(BlockModeSelect(c, i) for i in range(len(c.blocks))),
            *(BlockControlSelect(c, i) for i in range(len(c.blocks))),
        ]
    )


class GlobalControlSelect(OnbalansEntity, SelectEntity, RestoreEntity):
    """Algemene sturing: per tijdblok, of voor álle tijdblokken onbalans / handmatig aan / handmatig uit."""

    _attr_options = GLOBAL_CONTROLS
    _attr_icon = "mdi:tune-variant"

    def __init__(self, c: ChargeController) -> None:
        super().__init__(c, "sturing")
        self.entity_id = "select.onbalans_laden_sturing"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in GLOBAL_CONTROLS:
            self.controller.global_control = last.state
        else:
            self.controller.global_control = CTRL_PER_BLOCK

    @property
    def current_option(self) -> str | None:
        return self.controller.global_control

    async def async_select_option(self, option: str) -> None:
        await self.controller.async_set_global_control(option)


class BlockModeSelect(BlockEntity, SelectEntity):
    """Laden onder of boven de drempel."""

    _attr_options = [MODE_BELOW, MODE_ABOVE]
    _attr_icon = "mdi:swap-vertical"

    def __init__(self, c: ChargeController, idx: int) -> None:
        super().__init__(c, idx, B_MODE, "select")

    @property
    def current_option(self) -> str | None:
        return self.raw_value

    async def async_select_option(self, option: str) -> None:
        await self.async_set(option)


class BlockControlSelect(BlockEntity, SelectEntity):
    """Sturing van één tijdblok: onbalans (auto), handmatig aan of handmatig uit."""

    _attr_options = BLOCK_CONTROLS
    _attr_icon = "mdi:hand-back-right-outline"

    def __init__(self, c: ChargeController, idx: int) -> None:
        super().__init__(c, idx, B_CONTROL, "select")

    @property
    def current_option(self) -> str | None:
        if self.block is None:
            return None
        v = self.raw_value
        return v if v in BLOCK_CONTROLS else CTRL_AUTO

    async def async_select_option(self, option: str) -> None:
        await self.async_set(option)
