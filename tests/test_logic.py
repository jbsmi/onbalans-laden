from datetime import datetime, time, timedelta

import pytest

from custom_components.onbalans_laden.const import DEFAULT_BLOCK_TIMES, MODE_ABOVE, MODE_BELOW
from custom_components.onbalans_laden.logic import (
    ChargeStateMachine, Limits, find_block, parse_block_layout, parse_commands,
    parse_number, parse_tenergy_html, render_payload, row_age_minutes,
)
from .helpers import make_html


def test_parse_number():
    assert parse_number("1.234,56") == 1234.56
    assert parse_number("-12,00") == -12.0
    assert parse_number("220,00") == 220.0
    assert parse_number("0") == 0.0
    assert parse_number("") is None


def test_parse_html():
    now = datetime(2026, 10, 20, 15, 49)
    rows = parse_tenergy_html(make_html(now, ["220,00", "-15,50", "1.050,00"]))
    assert len(rows) == 3
    assert rows[0].tijd == "15:49" and rows[0].afnemen == 220.0
    assert rows[1].afnemen == -15.5
    assert rows[2].invoeden == 1050.0
    assert rows[0].volgnummer == 950


def test_row_age_midnight():
    assert row_age_minutes("23:59", datetime(2026, 10, 21, 0, 1)) == pytest.approx(2)
    assert row_age_minutes("15:49", datetime(2026, 10, 20, 15, 50, 30)) == pytest.approx(1.5)


def test_commands_and_payload():
    cmds = parse_commands('# comment\nW/abc/settings/0/Settings/CGwacs/AcPowerSetPoint = {"value": {ac_power_w}}\n')
    assert cmds == [("W/abc/settings/0/Settings/CGwacs/AcPowerSetPoint", '{"value": {ac_power_w}}')]
    assert render_payload(cmds[0][1], {"ac_power_w": 1000}) == '{"value": 1000}'
    with pytest.raises(ValueError):
        parse_commands("zonder is-teken")
    with pytest.raises(ValueError):
        parse_commands("a b = 1")


def test_limits():
    lim = Limits()
    # 3*140A*52V = 21.84 kW ; 3*32*230*0.93 = 20.54 kW
    assert lim.max_kw == pytest.approx(20.54, abs=0.01)
    v = lim.values_for(100)
    assert v["power_kw"] == lim.max_kw
    assert v["ac_current_a"] <= 32.0
    v = lim.values_for(7.28)
    assert v["current_a_per_inverter"] == 47  # 7280/52/3


def test_blocks():
    blocks = [{"start": s, "end": e} for s, e in DEFAULT_BLOCK_TIMES]
    assert find_block(blocks, time(0, 0)) == 0
    assert find_block(blocks, time(5, 59)) == 0
    assert find_block(blocks, time(6, 0)) == 1
    assert find_block(blocks, time(22, 59)) == 7
    assert find_block(blocks, time(23, 30)) == 8
    assert parse_block_layout("00:00-12:00\n12:00 - 24:00") == [("00:00", "12:00"), ("12:00", "00:00")]
    with pytest.raises(ValueError):
        parse_block_layout("bla")


P = dict(enabled=True, mode=MODE_BELOW, threshold=50.0, offset_low=10.0, offset_high=10.0,
         delay_on=60, delay_off=30, power_kw=10.0)


def test_statemachine_below_with_delays_and_hysteresis():
    sm = ChargeStateMachine()
    t0 = datetime(2026, 10, 20, 12, 0, 0)
    assert sm.evaluate(t0, True, 45, P, 20).action is None          # 45 > 40: geen start
    d = sm.evaluate(t0, True, 39, P, 20)
    assert d.status == "startvertraging" and d.action is None
    assert sm.evaluate(t0 + timedelta(seconds=59), True, 38, P, 20).action is None
    d = sm.evaluate(t0 + timedelta(seconds=60), True, 38, P, 20)
    assert d.action == "start" and d.power_kw == 10.0
    # binnen hysteresisband: blijven laden
    assert sm.evaluate(t0 + timedelta(seconds=70), True, 55, P, 20).action is None
    assert sm.charging
    # boven 60: stopvertraging
    d = sm.evaluate(t0 + timedelta(seconds=80), True, 61, P, 20)
    assert d.status == "stopvertraging" and sm.charging
    # prijs zakt weer: stopvertraging reset
    sm.evaluate(t0 + timedelta(seconds=90), True, 59, P, 20)
    sm.evaluate(t0 + timedelta(seconds=100), True, 61, P, 20)
    assert sm.evaluate(t0 + timedelta(seconds=129), True, 61, P, 20).action is None
    d = sm.evaluate(t0 + timedelta(seconds=130), True, 61, P, 20)
    assert d.action == "stop" and not sm.charging


def test_statemachine_start_delay_reset():
    sm = ChargeStateMachine()
    t0 = datetime(2026, 10, 20, 12, 0, 0)
    sm.evaluate(t0, True, 30, P, 20)
    sm.evaluate(t0 + timedelta(seconds=30), True, 45, P, 20)   # onderbroken
    assert sm.evaluate(t0 + timedelta(seconds=61), True, 30, P, 20).action is None
    assert sm.evaluate(t0 + timedelta(seconds=121), True, 30, P, 20).action == "start"


def test_statemachine_above_mode_power_update_and_safety():
    p = {**P, "mode": MODE_ABOVE, "delay_on": 0, "delay_off": 0}
    sm = ChargeStateMachine()
    t = datetime(2026, 10, 20, 12, 0, 0)
    assert sm.evaluate(t, True, 55, p, 20).action is None
    assert sm.evaluate(t, True, 61, p, 20).action == "start"
    d = sm.evaluate(t, True, 61, {**p, "power_kw": 30}, 20)       # nieuw blok, hoger vermogen -> begrensd
    assert d.action == "update" and d.power_kw == 20
    assert sm.evaluate(t, True, None, p, 20).action == "stop"      # geen prijs = stoppen
    sm.evaluate(t, True, 61, p, 20)
    assert sm.charging
    assert sm.evaluate(t, False, 61, p, 20).action == "stop"       # schakelaar uit
    sm.evaluate(t, True, 61, p, 20)
    assert sm.evaluate(t, True, 61, None, 20).action == "stop"     # geen tijdblok
    sm.evaluate(t, True, 61, p, 20)
    assert sm.evaluate(t, True, 61, {**p, "enabled": False}, 20).action == "stop"


def test_effective_control():
    from custom_components.onbalans_laden.logic import effective_control
    blk = {"enabled": True, "control": "aan"}
    assert effective_control("per_tijdblok", blk) == "aan"
    assert effective_control("per_tijdblok", {"enabled": True}) == "auto"  # oude opties zonder sturing
    assert effective_control("per_tijdblok", {"enabled": False, "control": "aan"}) == "auto"
    assert effective_control("per_tijdblok", None) == "auto"
    assert effective_control("uit", blk) == "uit"  # algemeen overrulet het tijdblok
    assert effective_control("auto", blk) == "auto"
    assert effective_control("aan", {"enabled": False, "control": "uit"}) == "aan"
    assert effective_control("aan", None) == "aan"


def test_state_machine_manual():
    sm = ChargeStateMachine()
    now = datetime(2026, 10, 27, 12, 0)
    p = dict(threshold=0.0, offset_low=5.0, offset_high=5.0, delay_on=60, delay_off=60, power_kw=8.0,
             mode=MODE_BELOW, enabled=True)
    # handmatig aan: direct laden, ook bij hoge of ontbrekende prijs, zonder vertraging
    d = sm.evaluate(now, True, 500.0, p, 20.0, "aan")
    assert d.action == "start" and d.power_kw == 8.0 and d.status == "handmatig_aan"
    d = sm.evaluate(now, True, None, p, 20.0, "aan")
    assert d.action is None and sm.charging
    # vermogen wijzigt -> update
    d = sm.evaluate(now, True, None, {**p, "power_kw": 5.0}, 20.0, "aan")
    assert d.action == "update" and d.power_kw == 5.0
    # buiten tijdblokken: max vermogen
    d = sm.evaluate(now, True, None, None, 20.0, "aan")
    assert d.action == "update" and d.power_kw == 20.0
    # handmatig uit: direct stoppen, ook bij lage prijs
    d = sm.evaluate(now, True, -500.0, p, 20.0, "uit")
    assert d.action == "stop" and d.status == "handmatig_uit" and not sm.charging
    d = sm.evaluate(now, True, -500.0, p, 20.0, "uit")
    assert d.action is None
    # hoofdschakelaar uit wint van handmatig aan
    d = sm.evaluate(now, False, None, p, 20.0, "aan")
    assert d.status == "uit" and not sm.charging
    # terug naar auto: normale startvertraging
    d = sm.evaluate(now, True, -10.0, p, 20.0, "auto")
    assert d.status == "startvertraging"


def test_limit_value():
    from custom_components.onbalans_laden.logic import limit_value
    assert limit_value(15.66, 1, 0, 100) == 15.0  # naar beneden op stap 1
    assert limit_value(15.66, 0.1, 0, 100) == 15.6
    assert limit_value(150, 1, 0, 100) == 100
    assert limit_value(0, 1, 0, 100) == 0
    assert limit_value(-3, None, None, None) == 0
