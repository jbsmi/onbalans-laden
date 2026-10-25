"""Ophalen van onbalansprijzen bij Tenergy."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .logic import PriceRow, parse_tenergy_html

_LOGGER = logging.getLogger(__name__)


@dataclass
class PriceData:
    rows: list[PriceRow]
    fetched: datetime

    @property
    def latest(self) -> PriceRow | None:
        return self.rows[0] if self.rows else None


class PriceCoordinator(DataUpdateCoordinator[PriceData]):
    def __init__(self, hass: HomeAssistant, url: str, interval_s: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval_s),
        )
        self.url = url
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> PriceData:
        try:
            async with asyncio.timeout(15):
                resp = await self._session.get(
                    self.url,
                    headers={"User-Agent": "HomeAssistant-onbalans_laden/1.0", "Cache-Control": "no-cache"},
                )
                resp.raise_for_status()
                html = await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Ophalen onbalansprijzen mislukt: {err}") from err

        rows = await self.hass.async_add_executor_job(parse_tenergy_html, html)
        if not rows:
            raise UpdateFailed("Geen prijsregels gevonden op de Tenergy-pagina (layout gewijzigd?)")
        return PriceData(rows=rows, fetched=dt_util.now())
