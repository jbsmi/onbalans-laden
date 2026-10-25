# Onbalans Laden (Victron) – Home Assistant custom integratie

Laadt de accu's via de Victron MultiPlus-omvormers (standaard 3× 10 kVA) op basis van de actuele
onbalansprijs van Tenergy (`https://services.tenergy.nl/public.aspx/actualimbalanceprices`).
De integratie **laadt alleen**: ze stuurt start-, vermogens- en stopcommando's via MQTT naar de Cerbo GX en geeft nooit een ontlaadcommando.

## Installatie

1. Kopieer de map `custom_components/onbalans_laden` naar `/config/custom_components/` van Home Assistant
   (of zet deze repo als *custom repository* in HACS).
2. Herstart Home Assistant.
3. Ga naar **Instellingen → Apparaten & diensten → Integratie toevoegen → "Onbalans Laden"**.
4. Laat de URL staan. Het ophaalinterval staat standaard op **20 s** (minimaal 10 s).
5. Vereist: de **MQTT-integratie** in HA moet de broker van de Cerbo GX kunnen bereiken
   (HA rechtstreeks met de Cerbo laten verbinden, of een Mosquitto-bridge van je eigen broker naar de Cerbo).

> **Testmodus staat bij de eerste installatie AAN.** Dan worden de commando's alleen gelogd en in de status-sensor
> (`laatste_acties`) getoond, en niet verstuurd. Zet de schakelaar *Testmodus (niet versturen)* pas uit als je
> de MQTT-regels hebt gecontroleerd.

## Instellen (Instellingen → Onbalans Laden → Configureren)

Het optiemenu bevat:

| Menu | Wat |
|---|---|
| **Tijdblok instellen** | Kies een blok (bv. `06:00–08:00`) en vul de waarden in |
| **Standaardregel** | Eén set waarden die je met één vinkje in **alle** tijdblokken zet |
| **Indeling tijdblokken** | De tijden zelf, één per regel `HH:MM-HH:MM` (standaard 9 blokken: 00-06, 06-08, 08-10, 10-12, 12-16, 16-18, 18-20, 20-23, 23-00) |
| **MQTT-commando's** | Start- en stopberichten (vrij in te vullen) |
| **Installatie & limieten** | Aantal omvormers, 140 A per omvormer, accuspanning, 3×32 A, rendement |
| **Prijsbron** | URL, interval (20 s), prijskolom (Afnemen/Invoeden), verouderingsgrens |
| **💾 Opslaan en sluiten** | Pas hier worden de wijzigingen bewaard |

### Waarden per tijdblok

- **Tijdblok actief**: staat dit uit, dan wordt er in dat blok niet geladen.
- **Laden wanneer prijs**: *onder drempel* (goedkoop/negatief laden) of *boven drempel*.
- **Drempel (€/MWh)**.
- **Offset onder / boven (€/MWh)**: de hysterese tegen pendelen.
  - *Onder drempel*: **start** als prijs ≤ drempel − offset onder, **stop** als prijs ≥ drempel + offset boven.
  - *Boven drempel*: **start** als prijs ≥ drempel + offset boven, **stop** als prijs ≤ drempel − offset onder.
- **Vertraging vóór start / vóór stop (s)**: zo lang moet de voorwaarde onafgebroken gelden. Onderbreking zet de teller terug.
- **Laadvermogen (kW)**: wordt automatisch begrensd op het minimum van
  - DC: omvormers × 140 A × accuspanning (3 × 140 × 52 V = 21,8 kW)
  - AC: 3 × 32 A × 230 V × rendement (93 % → 20,5 kW)

Wisselt het tijdblok tijdens het laden, dan worden de nieuwe drempels direct gebruikt en wordt bij een ander
vermogen het startcommando opnieuw verstuurd met het nieuwe vermogen.

### Veiligheid

Er wordt gestopt (stopcommando) als:
- de schakelaar **Automatische sturing** uit gaat,
- het tijdblok uitgeschakeld is of de tijd in geen enkel blok valt,
- de nieuwste prijsregel ouder is dan *verouderd na* (standaard 5 min) of de site niet bereikbaar is,
- Home Assistant (her)start of de instellingen worden opgeslagen (optie *stopcommando bij opstarten*, standaard aan).

## MQTT-commando's

Eén bericht per regel: `topic = payload`. Regels die met `#` beginnen zijn commentaar.
In de payload kun je deze variabelen gebruiken:

| Variabele | Betekenis |
|---|---|
| `{power_kw}` / `{power_w}` | laadvermogen (DC-zijde) |
| `{ac_power_w}` | benodigd AC-vermogen (= vermogen / rendement) |
| `{ac_power_w_per_phase}` | AC-vermogen per fase |
| `{current_a}` | totale DC-laadstroom (A) |
| `{current_a_per_inverter}` | DC-laadstroom per omvormer (A) |
| `{ac_current_a}` | AC-stroom per fase |
| `{price}` | actuele onbalansprijs |

Start-commando's gaan uit bij **start** en bij een **vermogenswijziging**; stel *herhalen elke … s* in als de Cerbo
het setpoint na een time-out loslaat (bijv. ESS mode 3 → elke 20–30 s).

### Voorbeelden (controleren op jouw Venus OS-versie!)

`<portal-id>` = VRM-portal-ID van de Cerbo, `<vebus>` = VE.Bus-instance (meestal 276 of 288).

**A. ESS "Keep batteries charged" + DVCC-laadstroom**
```
# start
W/<portal-id>/settings/0/Settings/SystemSetup/MaxChargeCurrent = {"value": {current_a}}
W/<portal-id>/settings/0/Settings/CGwacs/BatteryLife/State = {"value": 9}
# stop
W/<portal-id>/settings/0/Settings/CGwacs/BatteryLife/State = {"value": 10}
```

**B. ESS mode 3 (externe sturing) – setpoint per fase, herhalen elke 20 s**
```
# start
W/<portal-id>/vebus/<vebus>/Hub4/L1/AcPowerSetpoint = {"value": {ac_power_w_per_phase}}
W/<portal-id>/vebus/<vebus>/Hub4/L2/AcPowerSetpoint = {"value": {ac_power_w_per_phase}}
W/<portal-id>/vebus/<vebus>/Hub4/L3/AcPowerSetpoint = {"value": {ac_power_w_per_phase}}
# stop
W/<portal-id>/vebus/<vebus>/Hub4/L1/AcPowerSetpoint = {"value": 0}
W/<portal-id>/vebus/<vebus>/Hub4/L2/AcPowerSetpoint = {"value": 0}
W/<portal-id>/vebus/<vebus>/Hub4/L3/AcPowerSetpoint = {"value": 0}
```

## Entiteiten

| Entiteit | Inhoud |
|---|---|
| `sensor.…_onbalansprijs` | actuele prijs (€/MWh) + attributen: afnemen, invoeden, op/afregelen, laatste 15 minuten |
| `sensor.…_status` | uit / wachten / startvertraging / laden / stopvertraging / geen_tijdblok / geen_prijs + `reden`, `laatste_acties` |
| `sensor.…_actief_tijdblok` | actief blok + alle instellingen + overzicht van alle blokken |
| `sensor.…_drempel` | drempel van het actieve blok + `startgrens` / `stopgrens` (handig in een grafiek) |
| `sensor.…_laadvermogen_setpoint` | kW + stromen, max-limieten |
| `binary_sensor.…_laden` | wordt er geladen |
| `switch.…_automatische_sturing` | hoofdschakelaar |
| `switch.…_testmodus_niet_versturen` | alleen loggen, niets publiceren |

## Testen

```
pip install pytest-homeassistant-custom-component
pytest
```
