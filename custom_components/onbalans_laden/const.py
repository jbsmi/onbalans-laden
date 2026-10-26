"""Constanten voor Onbalans Laden."""
from __future__ import annotations

DOMAIN = "onbalans_laden"
PLATFORMS = ["sensor", "binary_sensor", "switch", "number", "select", "time"]

DEFAULT_URL = "https://services.tenergy.nl/public.aspx/actualimbalanceprices"

# --- algemene instellingen (options) ---
CONF_URL = "url"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_PRICE_COLUMN = "price_column"
CONF_STALE_MINUTES = "stale_minutes"
CONF_INVERTERS = "inverters"
CONF_MAX_DC_CURRENT = "max_dc_current"
CONF_BATTERY_VOLTAGE = "battery_voltage"
CONF_AC_PHASES = "ac_phases"
CONF_AC_MAX_CURRENT = "ac_max_current"
CONF_AC_VOLTAGE = "ac_voltage"
CONF_EFFICIENCY = "efficiency"

CONF_START_COMMANDS = "start_commands"
CONF_STOP_COMMANDS = "stop_commands"
CONF_REPEAT_INTERVAL = "repeat_interval"
CONF_QOS = "qos"
CONF_RETAIN = "retain"
CONF_STOP_ON_STARTUP = "stop_on_startup"

CONF_BLOCKS = "blocks"
CONF_DEFAULTS = "defaults"

# --- per tijdblok ---
B_START = "start"
B_END = "end"
B_ENABLED = "enabled"
B_MODE = "mode"
B_THRESHOLD = "threshold"
B_OFFSET_LOW = "offset_low"
B_OFFSET_HIGH = "offset_high"
B_DELAY_ON = "delay_on"
B_DELAY_OFF = "delay_off"
B_POWER = "power_kw"

# entity-id achtervoegsel per blokinstelling (number/select/switch/time per tijdblok)
BLOCK_ENTITY_SLUG = {
    B_START: "start",
    B_END: "eind",
    B_ENABLED: "actief",
    B_MODE: "modus",
    B_THRESHOLD: "drempel",
    B_OFFSET_LOW: "offset_onder",
    B_OFFSET_HIGH: "offset_boven",
    B_DELAY_ON: "vertraging_start",
    B_DELAY_OFF: "vertraging_stop",
    B_POWER: "vermogen",
}

MODE_BELOW = "below"  # laden als prijs laag is
MODE_ABOVE = "above"  # laden als prijs hoog is

PRICE_AFNEMEN = "afnemen"
PRICE_INVOEDEN = "invoeden"
PRICE_MAX = "max"

DEFAULT_SCAN_INTERVAL = 20  # seconden
MIN_SCAN_INTERVAL = 10
DEFAULT_STALE_MINUTES = 5

DEFAULT_GENERAL = {
    CONF_URL: DEFAULT_URL,
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    CONF_PRICE_COLUMN: PRICE_AFNEMEN,
    CONF_STALE_MINUTES: DEFAULT_STALE_MINUTES,
    CONF_INVERTERS: 3,
    CONF_MAX_DC_CURRENT: 140,
    CONF_BATTERY_VOLTAGE: 52.0,
    CONF_AC_PHASES: 3,
    CONF_AC_MAX_CURRENT: 32,
    CONF_AC_VOLTAGE: 230,
    CONF_EFFICIENCY: 93,
    CONF_START_COMMANDS: "",
    CONF_STOP_COMMANDS: "",
    CONF_REPEAT_INTERVAL: 0,
    CONF_QOS: 0,
    CONF_RETAIN: False,
    CONF_STOP_ON_STARTUP: True,
}

DEFAULT_BLOCK_PARAMS = {
    B_ENABLED: True,
    B_MODE: MODE_BELOW,
    B_THRESHOLD: 0.0,
    B_OFFSET_LOW: 10.0,
    B_OFFSET_HIGH: 10.0,
    B_DELAY_ON: 60,
    B_DELAY_OFF: 60,
    B_POWER: 10.0,
}

DEFAULT_BLOCK_TIMES = [
    ("00:00", "06:00"),
    ("06:00", "08:00"),
    ("08:00", "10:00"),
    ("10:00", "12:00"),
    ("12:00", "16:00"),
    ("16:00", "18:00"),
    ("18:00", "20:00"),
    ("20:00", "23:00"),
    ("23:00", "00:00"),
]

# status-waarden
ST_DISABLED = "uit"
ST_IDLE = "wachten"
ST_PENDING_START = "startvertraging"
ST_CHARGING = "laden"
ST_PENDING_STOP = "stopvertraging"
ST_NO_BLOCK = "geen_tijdblok"
ST_NO_PRICE = "geen_prijs"

SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"
