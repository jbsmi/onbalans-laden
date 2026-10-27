"""Config- en optiesflow voor Onbalans Laden."""
from __future__ import annotations

import copy
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector as sel

from .const import (
    B_CONTROL,
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
    CONF_AC_MAX_CURRENT,
    CONF_AC_PHASES,
    CONF_AC_VOLTAGE,
    CONF_BATTERY_VOLTAGE,
    CONF_BLOCKS,
    CONF_DEFAULTS,
    CONF_EFFICIENCY,
    CONF_INVERTERS,
    CONF_MAX_DC_CURRENT,
    CONF_PRICE_COLUMN,
    CONF_PRICE_STEP,
    CONF_PRICE_UNIT,
    CONF_QOS,
    CONF_REPEAT_INTERVAL,
    CONF_RETAIN,
    CONF_SCAN_INTERVAL,
    CONF_STALE_MINUTES,
    CONF_START_COMMANDS,
    CONF_STOP_COMMANDS,
    CONF_STOP_ON_STARTUP,
    CONF_URL,
    CTRL_AUTO,
    CTRL_OFF,
    CTRL_ON,
    DEFAULT_BLOCK_PARAMS,
    DEFAULT_BLOCK_TIMES,
    DEFAULT_GENERAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    MODE_ABOVE,
    MODE_BELOW,
    PRICE_AFNEMEN,
    PRICE_INVOEDEN,
    PRICE_MAX,
    PRICE_STEPS,
    PRICE_UNITS,
)
from .logic import Limits, PriceUnit, parse_block_layout, parse_commands

APPLY_ALL = "apply_all"
BLOCK_SELECT = "block"
LAYOUT = "layout"

PARAM_KEYS = (B_ENABLED, B_MODE, B_THRESHOLD, B_OFFSET_LOW, B_OFFSET_HIGH, B_DELAY_ON, B_DELAY_OFF, B_POWER)


def _num(min_v: float, max_v: float, step: float, unit: str | None = None) -> sel.NumberSelector:
    cfg = sel.NumberSelectorConfig(min=min_v, max=max_v, step=step, mode=sel.NumberSelectorMode.BOX)
    if unit:
        cfg["unit_of_measurement"] = unit
    return sel.NumberSelector(cfg)


def _limits(o: dict) -> Limits:
    return Limits(
        inverters=int(o[CONF_INVERTERS]),
        max_dc_current=float(o[CONF_MAX_DC_CURRENT]),
        battery_voltage=float(o[CONF_BATTERY_VOLTAGE]),
        ac_phases=int(o[CONF_AC_PHASES]),
        ac_max_current=float(o[CONF_AC_MAX_CURRENT]),
        ac_voltage=float(o[CONF_AC_VOLTAGE]),
        efficiency=float(o[CONF_EFFICIENCY]),
    )


def _unit(o: dict) -> PriceUnit:
    return PriceUnit(o.get(CONF_PRICE_UNIT), float(o.get(CONF_PRICE_STEP) or 0))


def _block_schema(cur: dict, max_kw: float, u: PriceUnit) -> dict:
    """Prijsvelden worden getoond in de gekozen eenheid (intern €/MWh)."""
    return {
        vol.Required(B_ENABLED, default=cur[B_ENABLED]): sel.BooleanSelector(),
        vol.Required(B_MODE, default=cur[B_MODE]): sel.SelectSelector(
            sel.SelectSelectorConfig(options=[MODE_BELOW, MODE_ABOVE], translation_key="mode")
        ),
        vol.Required(B_THRESHOLD, default=u.show(cur[B_THRESHOLD])): _num(
            -10000 * u.factor, 10000 * u.factor, u.step, u.label
        ),
        vol.Required(B_OFFSET_LOW, default=u.show(cur[B_OFFSET_LOW])): _num(0, 5000 * u.factor, u.step, u.label),
        vol.Required(B_OFFSET_HIGH, default=u.show(cur[B_OFFSET_HIGH])): _num(0, 5000 * u.factor, u.step, u.label),
        vol.Required(B_DELAY_ON, default=cur[B_DELAY_ON]): _num(0, 3600, 1, "s"),
        vol.Required(B_DELAY_OFF, default=cur[B_DELAY_OFF]): _num(0, 3600, 1, "s"),
        vol.Required(B_POWER, default=min(float(cur[B_POWER]), max_kw)): _num(0, max_kw, 0.1, "kW"),
    }


def _clean_params(user_input: dict, u: PriceUnit) -> dict:
    p = {k: user_input[k] for k in PARAM_KEYS}
    p[B_DELAY_ON] = int(p[B_DELAY_ON])
    p[B_DELAY_OFF] = int(p[B_DELAY_OFF])
    p[B_POWER] = float(p[B_POWER])
    for k in (B_THRESHOLD, B_OFFSET_LOW, B_OFFSET_HIGH):
        p[k] = u.store(p[k])
    return p


def default_options() -> dict:
    opts = copy.deepcopy(DEFAULT_GENERAL)
    opts[CONF_DEFAULTS] = dict(DEFAULT_BLOCK_PARAMS)
    opts[CONF_BLOCKS] = [{B_START: s, B_END: e, **DEFAULT_BLOCK_PARAMS} for s, e in DEFAULT_BLOCK_TIMES]
    return opts


class OnbalansConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            opts = default_options()
            opts[CONF_URL] = user_input[CONF_URL]
            opts[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            return self.async_create_entry(title="Onbalans Laden", data={}, options=opts)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=DEFAULT_GENERAL[CONF_URL]): sel.TextSelector(),
                    vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_GENERAL[CONF_SCAN_INTERVAL]): _num(
                        MIN_SCAN_INTERVAL, 3600, 1, "s"
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OnbalansOptionsFlow()


class OnbalansOptionsFlow(OptionsFlow):
    def __init__(self) -> None:
        self._opts: dict[str, Any] | None = None
        self._block_idx: int = 0

    @property
    def opts(self) -> dict[str, Any]:
        if self._opts is None:
            base = default_options()
            base.update(copy.deepcopy(dict(self.config_entry.options)))
            self._opts = base
        return self._opts

    # ------------------------------------------------------------ menu
    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["blokken", "standaard", "indeling", "mqtt", "installatie", "algemeen", "opslaan"],
            description_placeholders={"max_kw": str(_limits(self.opts).max_kw)},
        )

    async def async_step_opslaan(self, user_input=None) -> ConfigFlowResult:
        return self.async_create_entry(title="", data=self.opts)

    # ------------------------------------------------------------ tijdblok kiezen + bewerken
    def _block_label(self, i: int, b: dict) -> str:
        teken = "≤" if b[B_MODE] == MODE_BELOW else "≥"
        aan = "" if b[B_ENABLED] else " [uit]"
        ctrl = b.get(B_CONTROL, CTRL_AUTO)
        if ctrl == CTRL_ON:
            aan += " [handmatig aan]"
        elif ctrl == CTRL_OFF:
            aan += " [handmatig uit]"
        u = _unit(self.opts)
        return (
            f"{i + 1}. {b[B_START]}–{b[B_END]}: laden bij prijs {teken} {u.show(b[B_THRESHOLD]):g} "
            f"(−{u.show(b[B_OFFSET_LOW]):g}/+{u.show(b[B_OFFSET_HIGH]):g}) {u.label}, {b[B_POWER]:g} kW{aan}"
        )

    async def async_step_blokken(self, user_input=None) -> ConfigFlowResult:
        blocks = self.opts[CONF_BLOCKS]
        if user_input is not None:
            self._block_idx = int(user_input[BLOCK_SELECT])
            return await self.async_step_blok()
        return self.async_show_form(
            step_id="blokken",
            data_schema=vol.Schema(
                {
                    vol.Required(BLOCK_SELECT, default="0"): sel.SelectSelector(
                        sel.SelectSelectorConfig(
                            options=[
                                sel.SelectOptionDict(value=str(i), label=self._block_label(i, b))
                                for i, b in enumerate(blocks)
                            ],
                            mode=sel.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_blok(self, user_input=None) -> ConfigFlowResult:
        idx = self._block_idx
        block = self.opts[CONF_BLOCKS][idx]
        max_kw = _limits(self.opts).max_kw
        if user_input is not None:
            block.update(_clean_params(user_input, _unit(self.opts)))
            return await self.async_step_init()
        return self.async_show_form(
            step_id="blok",
            data_schema=vol.Schema(_block_schema(block, max_kw, _unit(self.opts))),
            description_placeholders={
                "nr": str(idx + 1),
                "van": block[B_START],
                "tot": block[B_END],
                "max_kw": str(max_kw),
            },
        )

    # ------------------------------------------------------------ standaardregel
    async def async_step_standaard(self, user_input=None) -> ConfigFlowResult:
        max_kw = _limits(self.opts).max_kw
        if user_input is not None:
            params = _clean_params(user_input, _unit(self.opts))
            self.opts[CONF_DEFAULTS] = params
            if user_input.get(APPLY_ALL):
                for b in self.opts[CONF_BLOCKS]:
                    b.update(params)
            return await self.async_step_init()
        schema = _block_schema({**DEFAULT_BLOCK_PARAMS, **self.opts[CONF_DEFAULTS]}, max_kw, _unit(self.opts))
        schema[vol.Required(APPLY_ALL, default=True)] = sel.BooleanSelector()
        return self.async_show_form(
            step_id="standaard",
            data_schema=vol.Schema(schema),
            description_placeholders={"max_kw": str(max_kw)},
        )

    # ------------------------------------------------------------ indeling tijdblokken
    async def async_step_indeling(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                layout = parse_block_layout(user_input[LAYOUT])
            except ValueError:
                errors[LAYOUT] = "invalid_layout"
            else:
                old = self.opts[CONF_BLOCKS]
                defaults = {**DEFAULT_BLOCK_PARAMS, **self.opts[CONF_DEFAULTS]}
                new = []
                for i, (s, e) in enumerate(layout):
                    if i < len(old):
                        params = {k: old[i][k] for k in PARAM_KEYS}
                        params[B_CONTROL] = old[i].get(B_CONTROL, CTRL_AUTO)
                    else:
                        params = {**dict(defaults), B_CONTROL: CTRL_AUTO}
                    new.append({B_START: s, B_END: e, **params})
                self.opts[CONF_BLOCKS] = new
                return await self.async_step_init()
        current = "\n".join(f"{b[B_START]}-{b[B_END]}" for b in self.opts[CONF_BLOCKS])
        return self.async_show_form(
            step_id="indeling",
            data_schema=vol.Schema(
                {vol.Required(LAYOUT, default=current): sel.TextSelector(sel.TextSelectorConfig(multiline=True))}
            ),
            errors=errors,
        )

    # ------------------------------------------------------------ MQTT
    async def async_step_mqtt(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        o = self.opts
        if user_input is not None:
            for key in (CONF_START_COMMANDS, CONF_STOP_COMMANDS):
                try:
                    parse_commands(user_input.get(key, ""))
                except ValueError:
                    errors[key] = "invalid_commands"
            if not errors:
                o[CONF_START_COMMANDS] = user_input.get(CONF_START_COMMANDS, "")
                o[CONF_STOP_COMMANDS] = user_input.get(CONF_STOP_COMMANDS, "")
                o[CONF_REPEAT_INTERVAL] = int(user_input[CONF_REPEAT_INTERVAL])
                o[CONF_QOS] = int(user_input[CONF_QOS])
                o[CONF_RETAIN] = bool(user_input[CONF_RETAIN])
                o[CONF_STOP_ON_STARTUP] = bool(user_input[CONF_STOP_ON_STARTUP])
                return await self.async_step_init()
            o = {**o, **user_input}
        multiline = sel.TextSelector(sel.TextSelectorConfig(multiline=True))
        return self.async_show_form(
            step_id="mqtt",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_START_COMMANDS, description={"suggested_value": o[CONF_START_COMMANDS]}): multiline,
                    vol.Optional(CONF_STOP_COMMANDS, description={"suggested_value": o[CONF_STOP_COMMANDS]}): multiline,
                    vol.Required(CONF_REPEAT_INTERVAL, default=o[CONF_REPEAT_INTERVAL]): _num(0, 3600, 1, "s"),
                    vol.Required(CONF_QOS, default=str(o[CONF_QOS])): sel.SelectSelector(
                        sel.SelectSelectorConfig(options=["0", "1", "2"])
                    ),
                    vol.Required(CONF_RETAIN, default=o[CONF_RETAIN]): sel.BooleanSelector(),
                    vol.Required(CONF_STOP_ON_STARTUP, default=o[CONF_STOP_ON_STARTUP]): sel.BooleanSelector(),
                }
            ),
            errors=errors,
            description_placeholders={
                "vars": ", ".join(
                    "{" + v + "}"
                    for v in (
                        "power_w", "power_kw", "current_a", "current_a_per_inverter",
                        "ac_power_w", "ac_power_w_per_phase", "ac_current_a", "price",
                    )
                ),
                "example": 'W/<portal-id>/settings/0/Settings/CGwacs/AcPowerSetPoint = {"value": {ac_power_w}}',
            },
        )

    # ------------------------------------------------------------ installatie / limieten
    async def async_step_installatie(self, user_input=None) -> ConfigFlowResult:
        o = self.opts
        if user_input is not None:
            o[CONF_INVERTERS] = int(user_input[CONF_INVERTERS])
            o[CONF_MAX_DC_CURRENT] = float(user_input[CONF_MAX_DC_CURRENT])
            o[CONF_BATTERY_VOLTAGE] = float(user_input[CONF_BATTERY_VOLTAGE])
            o[CONF_AC_PHASES] = int(user_input[CONF_AC_PHASES])
            o[CONF_AC_MAX_CURRENT] = float(user_input[CONF_AC_MAX_CURRENT])
            o[CONF_AC_VOLTAGE] = float(user_input[CONF_AC_VOLTAGE])
            o[CONF_EFFICIENCY] = float(user_input[CONF_EFFICIENCY])
            # vermogens begrenzen op nieuwe max
            max_kw = _limits(o).max_kw
            for b in [*o[CONF_BLOCKS], o[CONF_DEFAULTS]]:
                b[B_POWER] = min(float(b[B_POWER]), max_kw)
            return await self.async_step_init()
        lim = _limits(o)
        return self.async_show_form(
            step_id="installatie",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_INVERTERS, default=o[CONF_INVERTERS]): _num(1, 12, 1),
                    vol.Required(CONF_MAX_DC_CURRENT, default=o[CONF_MAX_DC_CURRENT]): _num(1, 500, 1, "A"),
                    vol.Required(CONF_BATTERY_VOLTAGE, default=o[CONF_BATTERY_VOLTAGE]): _num(10, 1000, 0.1, "V"),
                    vol.Required(CONF_AC_PHASES, default=o[CONF_AC_PHASES]): _num(1, 3, 1),
                    vol.Required(CONF_AC_MAX_CURRENT, default=o[CONF_AC_MAX_CURRENT]): _num(1, 250, 1, "A"),
                    vol.Required(CONF_AC_VOLTAGE, default=o[CONF_AC_VOLTAGE]): _num(100, 400, 1, "V"),
                    vol.Required(CONF_EFFICIENCY, default=o[CONF_EFFICIENCY]): _num(50, 100, 1, "%"),
                }
            ),
            description_placeholders={
                "max_dc": f"{lim.max_dc_kw:.2f}",
                "max_ac": f"{lim.max_ac_kw:.2f}",
                "max_kw": f"{lim.max_kw:.2f}",
            },
        )

    # ------------------------------------------------------------ algemeen
    async def async_step_algemeen(self, user_input=None) -> ConfigFlowResult:
        o = self.opts
        if user_input is not None:
            o[CONF_URL] = user_input[CONF_URL]
            o[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            o[CONF_PRICE_COLUMN] = user_input[CONF_PRICE_COLUMN]
            o[CONF_PRICE_UNIT] = user_input[CONF_PRICE_UNIT]
            o[CONF_PRICE_STEP] = user_input[CONF_PRICE_STEP]
            o[CONF_STALE_MINUTES] = int(user_input[CONF_STALE_MINUTES])
            return await self.async_step_init()
        return self.async_show_form(
            step_id="algemeen",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=o[CONF_URL]): sel.TextSelector(),
                    vol.Required(CONF_SCAN_INTERVAL, default=o[CONF_SCAN_INTERVAL]): _num(
                        MIN_SCAN_INTERVAL, 3600, 1, "s"
                    ),
                    vol.Required(CONF_PRICE_COLUMN, default=o[CONF_PRICE_COLUMN]): sel.SelectSelector(
                        sel.SelectSelectorConfig(
                            options=[PRICE_AFNEMEN, PRICE_INVOEDEN, PRICE_MAX], translation_key="price_column"
                        )
                    ),
                    vol.Required(CONF_PRICE_UNIT, default=o[CONF_PRICE_UNIT]): sel.SelectSelector(
                        sel.SelectSelectorConfig(options=list(PRICE_UNITS), translation_key="price_unit")
                    ),
                    vol.Required(CONF_PRICE_STEP, default=str(o[CONF_PRICE_STEP])): sel.SelectSelector(
                        sel.SelectSelectorConfig(options=PRICE_STEPS, mode=sel.SelectSelectorMode.DROPDOWN)
                    ),
                    vol.Required(CONF_STALE_MINUTES, default=o[CONF_STALE_MINUTES]): _num(1, 60, 1, "min"),
                }
            ),
        )
