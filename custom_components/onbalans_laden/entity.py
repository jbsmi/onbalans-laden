"""Gemeenschappelijke entiteit-basis."""
from __future__ import annotations

from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import BLOCK_ENTITY_SLUG, DOMAIN, SIGNAL_UPDATE
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


class BlockEntity(OnbalansEntity):
    """Eén instelling van één tijdblok, bedoeld om vanaf een dashboard te wijzigen."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller: ChargeController, idx: int, key: str, platform: str) -> None:
        slug = BLOCK_ENTITY_SLUG[key]
        super().__init__(controller, f"blok{idx + 1}_{key}")
        self.idx = idx
        self.key = key
        self._attr_translation_key = f"blok_{slug}"
        self._attr_translation_placeholders = {"nr": str(idx + 1)}
        # vaste, voorspelbare entity-id's zodat het meegeleverde dashboard altijd klopt
        self.entity_id = f"{platform}.onbalans_laden_blok_{idx + 1}_{slug}"

    @property
    def block(self) -> dict | None:
        blocks = self.controller.blocks
        return blocks[self.idx] if self.idx < len(blocks) else None

    @property
    def available(self) -> bool:
        return self.block is not None

    @property
    def raw_value(self):
        b = self.block
        return b.get(self.key) if b else None

    async def async_set(self, value) -> None:
        await self.controller.async_set_block_value(self.idx, self.key, value)
