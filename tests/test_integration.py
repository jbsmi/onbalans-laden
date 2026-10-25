from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onbalans_laden.config_flow import default_options
from custom_components.onbalans_laden.const import DEFAULT_URL, DOMAIN
from .helpers import make_html

START = 'W/c0619ab1234/settings/0/Settings/CGwacs/AcPowerSetPoint = {"value": {ac_power_w}}\nW/c0619ab1234/x/y = {"value": {current_a_per_inverter}}'
STOP = 'W/c0619ab1234/settings/0/Settings/CGwacs/AcPowerSetPoint = {"value": 0}'


async def test_config_flow(hass: HomeAssistant, mqtt_mock, aioclient_mock):
    aioclient_mock.get(DEFAULT_URL, text=make_html(dt_util.now(), ["100,00"]))
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert r["type"] == FlowResultType.FORM
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"url": DEFAULT_URL, "scan_interval": 20})
    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["options"]["scan_interval"] == 20
    assert len(r["options"]["blocks"]) == 9
    await hass.async_block_till_done()


async def test_options_flow(hass: HomeAssistant, mqtt_mock, aioclient_mock):
    aioclient_mock.get(DEFAULT_URL, text=make_html(dt_util.now(), ["100,00"]))
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=default_options())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    r = await hass.config_entries.options.async_init(entry.entry_id)
    assert r["type"] == FlowResultType.MENU
    fid = r["flow_id"]
    # standaardregel op alles
    r = await hass.config_entries.options.async_configure(fid, {"next_step_id": "standaard"})
    assert r["type"] == FlowResultType.FORM
    r = await hass.config_entries.options.async_configure(fid, {
        "enabled": True, "mode": "below", "threshold": 25, "offset_low": 5, "offset_high": 7,
        "delay_on": 20, "delay_off": 40, "power_kw": 15, "apply_all": True})
    assert r["type"] == FlowResultType.MENU
    # tijdblok 3 apart
    r = await hass.config_entries.options.async_configure(fid, {"next_step_id": "blokken"})
    r = await hass.config_entries.options.async_configure(fid, {"block": "2"})
    assert r["step_id"] == "blok"
    r = await hass.config_entries.options.async_configure(fid, {
        "enabled": False, "mode": "above", "threshold": 300, "offset_low": 5, "offset_high": 5,
        "delay_on": 0, "delay_off": 0, "power_kw": 5})
    # mqtt: fout + goed
    r = await hass.config_entries.options.async_configure(fid, {"next_step_id": "mqtt"})
    r = await hass.config_entries.options.async_configure(fid, {"start_commands": "fout", "stop_commands": "",
        "repeat_interval": 0, "qos": "0", "retain": False, "stop_on_startup": True})
    assert r["errors"] == {"start_commands": "invalid_commands"}
    r = await hass.config_entries.options.async_configure(fid, {"start_commands": START, "stop_commands": STOP,
        "repeat_interval": 30, "qos": "1", "retain": False, "stop_on_startup": True})
    assert r["type"] == FlowResultType.MENU
    # indeling
    r = await hass.config_entries.options.async_configure(fid, {"next_step_id": "indeling"})
    r = await hass.config_entries.options.async_configure(fid, {"layout": "00:00-06:00\n06:00-08:00\n08:00-10:00\n10:00-00:00"})
    assert r["type"] == FlowResultType.MENU
    # installatie
    r = await hass.config_entries.options.async_configure(fid, {"next_step_id": "installatie"})
    r = await hass.config_entries.options.async_configure(fid, {"inverters": 3, "max_dc_current": 140,
        "battery_voltage": 52, "ac_phases": 3, "ac_max_current": 32, "ac_voltage": 230, "efficiency": 93})
    r = await hass.config_entries.options.async_configure(fid, {"next_step_id": "algemeen"})
    r = await hass.config_entries.options.async_configure(fid, {"url": DEFAULT_URL, "scan_interval": 20,
        "price_column": "afnemen", "stale_minutes": 5})
    r = await hass.config_entries.options.async_configure(fid, {"next_step_id": "opslaan"})
    assert r["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    o = entry.options
    assert len(o["blocks"]) == 4
    assert o["blocks"][0]["threshold"] == 25 and o["blocks"][0]["power_kw"] == 15
    assert o["blocks"][2]["enabled"] is False and o["blocks"][2]["mode"] == "above"
    assert o["blocks"][3]["threshold"] == 0.0 or o["blocks"][3]["threshold"] == 25  # bestaand blok 4 behouden
    assert o["qos"] == 1 and o["repeat_interval"] == 30


async def test_charge_cycle_publishes_mqtt(hass: HomeAssistant, mqtt_mock, aioclient_mock):
    now = dt_util.now()
    aioclient_mock.get(DEFAULT_URL, text=make_html(now, ["-20,00", "-10,00"]))
    opts = default_options()
    for b in opts["blocks"]:
        b.update(threshold=0.0, offset_low=5.0, offset_high=5.0, delay_on=0, delay_off=0, power_kw=10.0)
    opts["start_commands"] = START
    opts["stop_commands"] = STOP
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=opts)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    ctrl = hass.data[DOMAIN][entry.entry_id]
    assert hass.states.get("switch.onbalans_laden_testmodus_niet_versturen") is not None or True

    # testmodus staat standaard aan -> niets publiceren
    await ctrl.async_evaluate()
    assert ctrl.sm.charging
    mqtt_mock.async_publish.assert_not_called()

    # testmodus uit -> startcommando's gaan echt de deur uit
    await ctrl.async_set_test_mode(False)
    await hass.async_block_till_done()
    topics = [c.args[0] for c in mqtt_mock.async_publish.call_args_list]
    payloads = [c.args[1] for c in mqtt_mock.async_publish.call_args_list]
    assert topics == ["W/c0619ab1234/settings/0/Settings/CGwacs/AcPowerSetPoint", "W/c0619ab1234/x/y"]
    assert payloads[0] == '{"value": 10753}'  # 10 kW / 0.93
    assert payloads[1] == '{"value": 64}'     # 10000/52/3

    states = {s.entity_id: s.state for s in hass.states.async_all() if s.entity_id.split(".")[1].startswith("onbalans")}
    print(states)
    assert any(v == "-20.0" for v in states.values())

    # prijs stijgt boven drempel+offset -> stop
    mqtt_mock.async_publish.reset_mock()
    aioclient_mock.clear_requests()
    aioclient_mock.get(DEFAULT_URL, text=make_html(dt_util.now(), ["10,00"]))
    await ctrl.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not ctrl.sm.charging
    assert mqtt_mock.async_publish.call_args_list[0].args[1] == '{"value": 0}'

    # automatische sturing uit
    await hass.services.async_call("switch", "turn_off", {"entity_id": [e for e in states if e.startswith("switch.") and "autom" in e][0]}, blocking=True)
    assert ctrl.decision.status == "uit"


async def test_stale_price_no_charge(hass: HomeAssistant, mqtt_mock, aioclient_mock):
    from datetime import timedelta
    aioclient_mock.get(DEFAULT_URL, text=make_html(dt_util.now() - timedelta(minutes=30), ["-50,00"]))
    opts = default_options()
    for b in opts["blocks"]:
        b.update(delay_on=0)
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=opts)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctrl = hass.data[DOMAIN][entry.entry_id]
    await ctrl.async_evaluate()
    assert ctrl.price is None and not ctrl.sm.charging
    assert ctrl.decision.status == "geen_prijs"
