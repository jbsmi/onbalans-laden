"""HA-onafhankelijke logica: parsen van prijzen, tijdblokken, vermogen en de laad-statemachine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from html.parser import HTMLParser
import math
import re
from typing import Any

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
    BLOCK_CONTROLS,
    CTRL_AUTO,
    CTRL_OFF,
    CTRL_ON,
    MODE_ABOVE,
    PRICE_AFNEMEN,
    PRICE_INVOEDEN,
    PRICE_MAX,
    PRICE_UNITS,
    ST_CHARGING,
    ST_DISABLED,
    ST_IDLE,
    ST_MANUAL_OFF,
    ST_MANUAL_ON,
    ST_NO_BLOCK,
    ST_NO_PRICE,
    ST_PENDING_START,
    ST_PENDING_STOP,
    UNIT_EUR_MWH,
)

# ---------------------------------------------------------------------------
# Prijzen parsen (Tenergy publieke pagina)
# ---------------------------------------------------------------------------


@dataclass
class PriceRow:
    """Eén minuutregel uit de Tenergy-tabel."""

    volgnummer: int
    tijd: str
    opregelen: float | None
    afregelen: float | None
    noodvermogen_op: float | None
    noodvermogen_af: float | None
    invoeden: float | None
    afnemen: float | None

    def price(self, column: str) -> float | None:
        if column == PRICE_INVOEDEN:
            return self.invoeden
        if column == PRICE_MAX:
            vals = [v for v in (self.invoeden, self.afnemen) if v is not None]
            return max(vals) if vals else None
        return self.afnemen


def parse_number(text: str) -> float | None:
    """'1.234,56' -> 1234.56 ; '-12,00' -> -12.0 ; '' -> None."""
    t = text.strip().replace("\xa0", "").replace(" ", "")
    if not t or t in ("-", "--"):
        return None
    t = t.replace("−", "-")  # unicode minus
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0  # diepte binnen table.imbalanceprices
        self.in_target = False
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.in_target:
                self.depth += 1
            else:
                classes = (dict(attrs).get("class") or "").split()
                if "imbalanceprices" in classes:
                    self.in_target = True
                    self.depth = 1
        if not self.in_target:
            return
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if not self.in_target:
            return
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            self.depth -= 1
            if self.depth == 0:
                self.in_target = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


def parse_tenergy_html(html: str) -> list[PriceRow]:
    """Geef de regels terug, nieuwste eerst (zoals op de pagina)."""
    p = _TableParser()
    p.feed(html)
    out: list[PriceRow] = []
    for r in p.rows:
        if len(r) < 9 or not r[0].strip().isdigit() or not _TIME_RE.match(r[2].strip()):
            continue
        try:
            volg = int(r[1].strip())
        except ValueError:
            volg = -1
        out.append(
            PriceRow(
                volgnummer=volg,
                tijd=r[2].strip(),
                opregelen=parse_number(r[3]),
                afregelen=parse_number(r[4]),
                noodvermogen_op=parse_number(r[5]),
                noodvermogen_af=parse_number(r[6]),
                invoeden=parse_number(r[7]),
                afnemen=parse_number(r[8]),
            )
        )
    return out


def row_age_minutes(tijd: str, now: datetime) -> float:
    """Leeftijd van een 'HH:MM'-regel in minuten t.o.v. lokale tijd (houdt rekening met middernacht)."""
    h, m = (int(x) for x in tijd.split(":"))
    row_dt = now.replace(hour=h % 24, minute=m, second=0, microsecond=0)
    if row_dt > now + timedelta(minutes=5):
        row_dt -= timedelta(days=1)
    return (now - row_dt).total_seconds() / 60.0


# ---------------------------------------------------------------------------
# MQTT-commando's
# ---------------------------------------------------------------------------


def parse_commands(text: str) -> list[tuple[str, str]]:
    """Eén commando per regel:  topic = payload   (regels met # zijn commentaar)."""
    cmds: list[tuple[str, str]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Regel zonder '=': {line}")
        topic, payload = line.split("=", 1)
        topic = topic.strip()
        if not topic or " " in topic or "#" in topic or "+" in topic:
            raise ValueError(f"Ongeldig topic: {topic!r}")
        cmds.append((topic, payload.strip()))
    return cmds


def render_payload(template: str, values: dict[str, Any]) -> str:
    """Vervang {power_w}, {power_kw}, {current_a}, ... maar laat JSON-accolades heel."""

    def repl(m: re.Match) -> str:
        key = m.group(1)
        return str(values[key]) if key in values else m.group(0)

    return re.sub(r"\{([a-z_]+)\}", repl, template)


def limit_value(current_a: float, step: float | None, mn: float | None, mx: float | None) -> float:
    """Stroomlimiet afronden op de stap van de entiteit (naar beneden, zodat het setpoint niet overschreden wordt)."""
    v = max(0.0, float(current_a))
    st = float(step) if step else 0.0
    if st > 0:
        v = math.floor(v / st + 1e-9) * st
        v = round(v, 6)
    if mn is not None:
        v = max(v, float(mn))
    if mx is not None:
        v = min(v, float(mx))
    return v


# ---------------------------------------------------------------------------
# Vermogen / limieten
# ---------------------------------------------------------------------------


@dataclass
class Limits:
    inverters: int = 3
    max_dc_current: float = 140.0  # A per omvormer
    battery_voltage: float = 52.0
    ac_phases: int = 3
    ac_max_current: float = 32.0
    ac_voltage: float = 230.0
    efficiency: float = 93.0  # % AC -> DC

    @property
    def max_dc_kw(self) -> float:
        return self.inverters * self.max_dc_current * self.battery_voltage / 1000.0

    @property
    def max_ac_kw(self) -> float:
        """Max laadvermogen (DC-zijde) dat via de AC-aansluiting binnen kan."""
        return self.ac_phases * self.ac_max_current * self.ac_voltage * (self.efficiency / 100.0) / 1000.0

    @property
    def max_kw(self) -> float:
        return round(min(self.max_dc_kw, self.max_ac_kw), 2)

    def values_for(self, power_kw: float) -> dict[str, Any]:
        p = max(0.0, min(float(power_kw), self.max_kw))
        w = p * 1000.0
        dc_a = w / self.battery_voltage if self.battery_voltage else 0.0
        ac_w = w / (self.efficiency / 100.0) if self.efficiency else w
        ac_a = ac_w / (self.ac_phases * self.ac_voltage) if self.ac_phases and self.ac_voltage else 0.0
        per_inv = dc_a / self.inverters if self.inverters else 0.0
        return {
            "power_kw": round(p, 2),
            "power_w": int(round(w)),
            "ac_power_w": int(round(ac_w)),
            "ac_power_w_per_phase": int(round(ac_w / self.ac_phases)) if self.ac_phases else 0,
            "current_a": int(round(dc_a)),
            "current_a_per_inverter": int(round(per_inv)),
            "ac_current_a": round(ac_a, 1),
        }


# ---------------------------------------------------------------------------
# Prijseenheid (weergave)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriceUnit:
    """Omrekening tussen intern €/MWh en de gekozen weergave-eenheid."""

    key: str = UNIT_EUR_MWH
    step_size: float = 0.0  # stapgrootte invoervelden in weergave-eenheid (0 = automatisch)

    @property
    def factor(self) -> float:
        return PRICE_UNITS.get(self.key, PRICE_UNITS[UNIT_EUR_MWH])[0]

    @property
    def label(self) -> str:
        return PRICE_UNITS.get(self.key, PRICE_UNITS[UNIT_EUR_MWH])[1]

    @property
    def decimals(self) -> int:
        return PRICE_UNITS.get(self.key, PRICE_UNITS[UNIT_EUR_MWH])[2]

    @property
    def step(self) -> float:
        if self.step_size and self.step_size > 0:
            return float(self.step_size)
        return round(0.01 * self.factor, 6)

    def show(self, eur_mwh: float | None) -> float | None:
        """€/MWh -> weergave-eenheid."""
        if eur_mwh is None:
            return None
        return round(float(eur_mwh) * self.factor, self.decimals + 2)

    def store(self, value: float) -> float:
        """weergave-eenheid -> €/MWh."""
        return round(float(value) / self.factor, 4)


# ---------------------------------------------------------------------------
# Tijdblokken
# ---------------------------------------------------------------------------


def parse_hhmm(s: str) -> time:
    s = s.strip()
    if s in ("24:00", "24:00:00"):
        return time(0, 0)
    parts = s.split(":")
    return time(int(parts[0]), int(parts[1]))


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def block_contains(block: dict, now: time) -> bool:
    start = _minutes(parse_hhmm(block[B_START]))
    end = _minutes(parse_hhmm(block[B_END]))
    n = _minutes(now)
    if start == end:  # heel de dag
        return True
    if start < end:
        return start <= n < end
    return n >= start or n < end  # over middernacht, bv 23:00-00:00


def find_block(blocks: list[dict], now: time) -> int | None:
    for i, b in enumerate(blocks):
        if block_contains(b, now):
            return i
    return None


def parse_block_layout(text: str) -> list[tuple[str, str]]:
    """'00:00-06:00' per regel -> lijst (start, eind)."""
    out: list[tuple[str, str]] = []
    for raw in text.replace(",", "\n").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})$", line)
        if not m:
            raise ValueError(line)
        a, b = m.group(1), m.group(2)
        ta, tb = parse_hhmm(a), parse_hhmm(b)  # valideert
        out.append((f"{ta.hour:02d}:{ta.minute:02d}", f"{tb.hour:02d}:{tb.minute:02d}"))
    if not out:
        raise ValueError("leeg")
    return out


def effective_control(global_control: str | None, block: dict | None) -> str:
    """Welke sturing geldt nu? De algemene keuze overrulet alle tijdblokken.

    - algemeen 'aan'/'uit'/'auto' -> geldt voor elk tijdblok (ook buiten tijdblokken)
    - algemeen 'per_tijdblok'     -> sturing van het actieve tijdblok; een uitgeschakeld
      tijdblok of geen tijdblok valt terug op 'auto' (en laadt dus niet)
    """
    if global_control in (CTRL_AUTO, CTRL_ON, CTRL_OFF):
        return global_control
    if not block or not block.get(B_ENABLED, True):
        return CTRL_AUTO
    ctrl = block.get(B_CONTROL, CTRL_AUTO)
    return ctrl if ctrl in BLOCK_CONTROLS else CTRL_AUTO


# ---------------------------------------------------------------------------
# Statemachine
# ---------------------------------------------------------------------------


@dataclass
class Decision:
    status: str
    charging: bool
    action: str | None = None  # "start", "stop", "update"
    power_kw: float = 0.0
    reason: str = ""


@dataclass
class ChargeStateMachine:
    """Hysterese (offset onder/boven drempel) + vertraging voor start en stop."""

    charging: bool = False
    pending_since: datetime | None = None
    active_power_kw: float = 0.0
    last: Decision = field(default_factory=lambda: Decision(ST_IDLE, False))

    @staticmethod
    def conditions(price: float, p: dict) -> tuple[bool, bool]:
        thr = float(p[B_THRESHOLD])
        low = thr - float(p[B_OFFSET_LOW])
        high = thr + float(p[B_OFFSET_HIGH])
        if p.get(B_MODE) == MODE_ABOVE:
            return price >= high, price <= low  # (start, stop)
        return price <= low, price >= high

    def evaluate(
        self,
        now: datetime,
        enabled: bool,
        price: float | None,
        params: dict | None,
        max_kw: float,
        control: str = CTRL_AUTO,
    ) -> Decision:
        d = self._evaluate(now, enabled, price, params, max_kw, control)
        self.last = d
        return d

    def _stop(self, status: str, reason: str) -> Decision:
        self.pending_since = None
        if self.charging:
            self.charging = False
            self.active_power_kw = 0.0
            return Decision(status, False, "stop", 0.0, reason)
        return Decision(status, False, None, 0.0, reason)

    def _manual_on(self, params: dict | None, max_kw: float) -> Decision:
        """Handmatig laden: direct starten, zonder prijsvoorwaarde of vertraging."""
        self.pending_since = None
        power = float(params[B_POWER]) if params else max_kw  # buiten tijdblokken: max vermogen
        power = round(max(0.0, min(power, max_kw)), 2)
        if power <= 0:
            return self._stop(ST_MANUAL_ON, "handmatig aan, maar vermogen 0 kW")
        if not self.charging:
            self.charging = True
            self.active_power_kw = power
            return Decision(ST_MANUAL_ON, True, "start", power, "handmatig aan")
        if abs(power - self.active_power_kw) > 0.001:
            self.active_power_kw = power
            return Decision(ST_MANUAL_ON, True, "update", power, "handmatig aan: vermogen gewijzigd")
        return Decision(ST_MANUAL_ON, True, None, self.active_power_kw, "handmatig aan")

    def _evaluate(self, now, enabled, price, params, max_kw, control=CTRL_AUTO) -> Decision:
        if not enabled:
            return self._stop(ST_DISABLED, "automatische sturing uit")
        if control == CTRL_OFF:
            return self._stop(ST_MANUAL_OFF, "handmatig uit")
        if control == CTRL_ON:
            return self._manual_on(params, max_kw)
        if params is None:
            return self._stop(ST_NO_BLOCK, "geen tijdblok actief")
        if not params.get(B_ENABLED, True):
            return self._stop(ST_DISABLED, "tijdblok uitgeschakeld")
        if price is None:
            return self._stop(ST_NO_PRICE, "geen (actuele) prijs")

        power = round(max(0.0, min(float(params[B_POWER]), max_kw)), 2)
        if power <= 0:
            return self._stop(ST_IDLE, "vermogen 0 kW")

        start_ok, stop_ok = self.conditions(price, params)

        if not self.charging:
            if start_ok:
                if self.pending_since is None:
                    self.pending_since = now
                waited = (now - self.pending_since).total_seconds()
                if waited >= float(params[B_DELAY_ON]):
                    self.pending_since = None
                    self.charging = True
                    self.active_power_kw = power
                    return Decision(ST_CHARGING, True, "start", power, "startvoorwaarde vervuld")
                return Decision(
                    ST_PENDING_START, False, None, 0.0,
                    f"start over {int(float(params[B_DELAY_ON]) - waited)} s",
                )
            self.pending_since = None
            return Decision(ST_IDLE, False, None, 0.0, "startvoorwaarde niet vervuld")

        # aan het laden
        if stop_ok:
            if self.pending_since is None:
                self.pending_since = now
            waited = (now - self.pending_since).total_seconds()
            if waited >= float(params[B_DELAY_OFF]):
                return self._stop(ST_IDLE, "stopvoorwaarde vervuld")
            status, reason = ST_PENDING_STOP, f"stop over {int(float(params[B_DELAY_OFF]) - waited)} s"
        else:
            self.pending_since = None
            status, reason = ST_CHARGING, "laden"

        if abs(power - self.active_power_kw) > 0.001:
            self.active_power_kw = power
            return Decision(status, True, "update", power, "vermogen gewijzigd")
        return Decision(status, True, None, self.active_power_kw, reason)
