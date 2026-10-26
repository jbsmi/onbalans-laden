"""Regelaar: koppelt prijs + tijdblok aan start/stop MQTT-commando's."""
from __future__ import annotations

import asyncio
import copy
from collections import deque
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AC_MAX_CURRENT,
    CONF_AC_PHASES,
    CONF_AC_VOLTAGE,
    CONF_BATTERY_VOLTAGE,
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
    CONF_BLOCKS,
    CONF_EFFICIENCY,
    CONF_INVERTERS,
    CONF_MAX_DC_CURRENT,
    CONF_PRICE_COLUMN,
    CONF_PRICE_STEP,
    CONF_PRICE_UNIT,
    CONF_QOS,
    CONF_REPEAT_INTERVAL,
    CONF_RETAIN,
    CONF_STALE_MINUTES,
    CONF_START_COMMANDS,
    CONF_STOP_COMMANDS,
    CONF_STOP_ON_STARTUP,
    DEFAULT_GENERAL,
    MODE_ABOVE,
    MODE_BELOW,
    SIGNAL_UPDATE,
)
from .coordinator import PriceCoordinator
from .logic import (
    ChargeStateMachine,
    Decision,
    Limits,
    PriceUnit,
    find_block,
    parse_commands,
    parse_hhmm,
    render_payload,
    row_age_minutes,
)

_LOGGER = logging.getLogger(__name__)

TICK = timedelta(seconds=5)


class ChargeController:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, coordinator: PriceCoordinator) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.sm = ChargeStateMachine()
        self.auto_enabled = True
        self.test_mode = True
        self.price: float | None = None
        self.price_time: str | None = None
        self.price_age_min: float | None = None
        self.block_index: int | None = None
        self.last_sent: datetime | None = None
        self.history: deque[dict[str, Any]] = deque(maxlen=15)
        self._unsubs: list[CALLBACK_TYPE] = []
        self._lock = asyncio.Lock()
        # aantal opties-wijzigingen vanuit de blok-entiteiten waarvoor GEEN herlaad nodig is
        self._live_updates = 0

    # ---------------- configuratie ----------------
    @property
    def opts(self) -> dict[str, Any]:
        return {**DEFAULT_GENERAL, **self.entry.options}

    @property
    def blocks(self) -> list[dict]:
        return self.opts.get(CONF_BLOCKS, [])

    @property
    def limits(self) -> Limits:
        o = self.opts
        return Limits(
            inverters=int(o[CONF_INVERTERS]),
            max_dc_current=float(o[CONF_MAX_DC_CURRENT]),
            battery_voltage=float(o[CONF_BATTERY_VOLTAGE]),
            ac_phases=int(o[CONF_AC_PHASES]),
            ac_max_current=float(o[CONF_AC_MAX_CURRENT]),
            ac_voltage=float(o[CONF_AC_VOLTAGE]),
            efficiency=float(o[CONF_EFFICIENCY]),
        )

    @property
    def unit(self) -> PriceUnit:
        return PriceUnit(self.opts.get(CONF_PRICE_UNIT), float(self.opts.get(CONF_PRICE_STEP) or 0))

    @property
    def active_block(self) -> dict | None:
        if self.block_index is None or self.block_index >= len(self.blocks):
            return None
        return self.blocks[self.block_index]

    @property
    def decision(self) -> Decision:
        return self.sm.last

    # ---------------- levenscyclus ----------------
    async def async_start(self) -> None:
        self._unsubs.append(self.coordinator.async_add_listener(self._on_price_update))
        self._unsubs.append(async_track_time_interval(self.hass, self._on_tick, TICK))
        if self.opts[CONF_STOP_ON_STARTUP]:
            # even wachten tot de schakelaars hun vorige stand hersteld hebben
            self._unsubs.append(async_call_later(self.hass, 10, self._startup_stop))

    async def _startup_stop(self, _now=None) -> None:
        if not self.test_mode and not await mqtt.async_wait_for_mqtt_client(self.hass):
            _LOGGER.error("MQTT niet beschikbaar; stop-commando bij opstarten niet verstuurd")
            return
        await self._send("stop", 0.0, "opstarten (veilige stand)")

    @callback
    def async_stop(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()

    # ---------------- events ----------------
    @callback
    def _on_price_update(self) -> None:
        self.hass.async_create_task(self.async_evaluate())

    async def _on_tick(self, _now: datetime) -> None:
        await self.async_evaluate()

    async def async_set_auto(self, on: bool) -> None:
        self.auto_enabled = on
        await self.async_evaluate()

    async def async_set_test_mode(self, on: bool) -> None:
        async with self._lock:
            if on and not self.test_mode and self.sm.charging:
                # echte installatie netjes stoppen voordat we naar testmodus gaan
                await self._send("stop", 0.0, "testmodus aangezet")
                self.test_mode = True
                await self._send("start", self.sm.active_power_kw, "testmodus aangezet (alleen log)")
            elif not on and self.test_mode and self.sm.charging:
                self.test_mode = False
                await self._send("start", self.sm.active_power_kw, "testmodus uitgezet")
            self.test_mode = on
        self._notify()

    # ---------------- tijdblokken live wijzigen (dashboard-entiteiten) ----------------
    def consume_live_update(self) -> bool:
        """True als de laatste opties-wijziging van een blok-entiteit kwam (dan niet herladen)."""
        if self._live_updates > 0:
            self._live_updates -= 1
            return True
        return False

    async def async_set_block_value(self, idx: int, key: str, value: Any) -> None:
        """Eén waarde van een tijdblok wijzigen, opslaan in de opties en direct toepassen."""
        if idx >= len(self.blocks):
            raise ValueError(f"Tijdblok {idx + 1} bestaat niet")
        if key in (B_START, B_END):
            t = parse_hhmm(str(value)[:5])
            value = f"{t.hour:02d}:{t.minute:02d}"
        elif key == B_ENABLED:
            value = bool(value)
        elif key == B_MODE:
            if value not in (MODE_BELOW, MODE_ABOVE):
                raise ValueError(f"Ongeldige modus: {value}")
        elif key in (B_THRESHOLD, B_OFFSET_LOW, B_OFFSET_HIGH):
            value = self.unit.store(value)  # dashboard levert de weergave-eenheid
        elif key in (B_DELAY_ON, B_DELAY_OFF):
            value = int(value)
        elif key == B_POWER:
            value = min(float(value), self.limits.max_kw)
        else:
            value = float(value)

        new_opts = copy.deepcopy(dict(self.entry.options))
        new_opts[CONF_BLOCKS][idx][key] = value
        self._live_updates += 1
        if not self.hass.config_entries.async_update_entry(self.entry, options=new_opts):
            self._live_updates -= 1  # niets veranderd -> er komt ook geen update-listener
        await self.async_evaluate()

    # ---------------- kern ----------------
    def _current_price(self, now: datetime) -> None:
        data = self.coordinator.data
        self.price = None
        self.price_time = None
        self.price_age_min = None
        if not data or not data.latest:
            return
        row = data.latest
        self.price_time = row.tijd
        try:
            self.price_age_min = round(row_age_minutes(row.tijd, now), 1)
        except ValueError:
            return
        if self.price_age_min > float(self.opts[CONF_STALE_MINUTES]):
            return
        self.price = row.price(self.opts[CONF_PRICE_COLUMN])

    async def async_evaluate(self) -> None:
        async with self._lock:
            await self._evaluate()

    async def _evaluate(self) -> None:
        now = dt_util.now()
        self._current_price(now)
        self.block_index = find_block(self.blocks, now.time())
        limits = self.limits
        d = self.sm.evaluate(now, self.auto_enabled, self.price, self.active_block, limits.max_kw)

        if d.action in ("start", "update"):
            await self._send("start", d.power_kw, d.reason)
        elif d.action == "stop":
            await self._send("stop", 0.0, d.reason)
        else:
            rep = int(self.opts[CONF_REPEAT_INTERVAL])
            if (
                rep > 0
                and self.sm.charging
                and self.last_sent is not None
                and (now - self.last_sent).total_seconds() >= rep
            ):
                await self._send("start", self.sm.active_power_kw, "herhaling")
        self._notify()

    async def _send(self, kind: str, power_kw: float, reason: str) -> None:
        o = self.opts
        text = o[CONF_START_COMMANDS] if kind == "start" else o[CONF_STOP_COMMANDS]
        values = self.limits.values_for(power_kw)
        values["price"] = self.price if self.price is not None else ""
        try:
            cmds = parse_commands(text)
        except ValueError as err:
            _LOGGER.error("Ongeldige %s-commando's: %s", kind, err)
            cmds = []
        self.last_sent = dt_util.now()
        sent = []
        for topic, tpl in cmds:
            payload = render_payload(tpl, values)
            sent.append(f"{topic} = {payload}")
            if self.test_mode:
                _LOGGER.info("[TESTMODUS] %s: %s %s", kind, topic, payload)
                continue
            try:
                await mqtt.async_publish(self.hass, topic, payload, int(o[CONF_QOS]), bool(o[CONF_RETAIN]))
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("MQTT publiceren naar %s mislukt: %s", topic, err)
        if not cmds:
            _LOGGER.warning("Geen %s-commando's ingesteld (opties > MQTT-commando's)", kind)
        if reason != "herhaling":
            self.history.appendleft(
                {
                    "tijd": self.last_sent.strftime("%Y-%m-%d %H:%M:%S"),
                    "actie": kind,
                    "vermogen_kw": values["power_kw"],
                    "prijs": self.price,
                    "reden": reason,
                    "testmodus": self.test_mode,
                    "berichten": sent,
                }
            )
            _LOGGER.info("Onbalans laden: %s (%s kW) - %s", kind, values["power_kw"], reason)

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(self.entry.entry_id))
