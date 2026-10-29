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
| **Prijsbron** | URL, interval (20 s), prijskolom (Afnemen/Invoeden), **prijseenheid** (€/MWh, ct/kWh of €/kWh), verouderingsgrens |
| **💾 Opslaan en sluiten** | Pas hier worden de wijzigingen bewaard |

### Prijseenheid

Onder *Prijsbron* kies je of prijzen worden getoond in **€/MWh** (zoals Tenergy), **ct/kWh** of **€/kWh**.
Dit geldt voor de prijs- en drempelsensor, de blok-entiteiten, het optiemenu en de dashboardtabel.
Met **Stapgrootte drempel/offset** (1, 0,1, 0,01 of 0,001; standaard 1) bepaal je in welke stappen je drempel en offsets invult.
Intern blijft alles in €/MWh opgeslagen (1 €/MWh = 0,1 ct/kWh = 0,001 €/kWh), dus je drempels blijven kloppen.
De MQTT-variabele `{price}` blijft in €/MWh. Na het wisselen meldt HA eenmalig dat de eenheid van de
prijsstatistiek is veranderd; los dat op via *Ontwikkelhulpmiddelen → Statistieken*.

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

### Sturing: onbalans, handmatig aan of handmatig uit

Per tijdblok kies je de **sturing** (`select.onbalans_laden_blok_n_sturing`):

- **Onbalans (auto)** – laden volgens drempel, offsets en vertragingen hierboven (standaard).
- **Handmatig aan** – direct laden met het laadvermogen van dat tijdblok; de onbalansprijs en vertragingen worden genegeerd.
- **Handmatig uit** – in dat tijdblok wordt niet geladen.

Daarboven staat de algemene **Sturing laden** (`select.onbalans_laden_sturing`), die alle tijdblokken overrulet:

- **Per tijdblok** – elk tijdblok volgt zijn eigen sturing (standaard).
- **Alle blokken: onbalans (auto)** / **handmatig aan** / **handmatig uit** – geldt voor alle tijdblokken tegelijk,
  ongeacht wat per blok is ingesteld (ook voor uitgeschakelde tijdblokken en tijden buiten de tijdblokken;
  handmatig aan laadt dan met het vermogen van het actieve blok, of met het maximum als er geen blok actief is).

De schakelaar **Automatische sturing** blijft de hoofdschakelaar: staat die uit, dan wordt er nooit geladen, ook niet handmatig.

### Veiligheid

Er wordt gestopt (stopcommando) als:
- de schakelaar **Automatische sturing** uit gaat,
- het tijdblok uitgeschakeld is of de tijd in geen enkel blok valt,
- de nieuwste prijsregel ouder is dan *verouderd na* (standaard 5 min) of de site niet bereikbaar is,
- Home Assistant (her)start of de instellingen worden opgeslagen (optie *stopcommando bij opstarten*, standaard aan).

## Dashboard met tijdblokken in tabelvorm

Elke instelling van elk tijdblok is ook een entiteit, zodat je de blokken vanaf een dashboard kunt bekijken en wijzigen
(zonder het optiemenu te openen). Wijzigingen worden **direct opgeslagen en toegepast**, zonder herladen.

| Entiteit (n = bloknummer) | Instelling |
|---|---|
| `switch.onbalans_laden_blok_n_actief` | tijdblok aan/uit |
| `select.onbalans_laden_blok_n_sturing` | onbalans (auto) / handmatig aan / handmatig uit |
| `time.onbalans_laden_blok_n_start` / `time.onbalans_laden_blok_n_eind` | begin- en eindtijd |
| `select.onbalans_laden_blok_n_modus` | laden onder / boven drempel |
| `number.onbalans_laden_blok_n_drempel` | drempel (€/MWh) |
| `number.onbalans_laden_blok_n_offset_onder` / `_offset_boven` | hysterese (€/MWh) |
| `number.onbalans_laden_blok_n_vertraging_start` / `_vertraging_stop` | vertraging (s) |
| `number.onbalans_laden_blok_n_vermogen` | laadvermogen (kW, max = installatielimiet) |

Het attribuut `blokken` van `sensor.onbalans_laden_actief_tijdblok` bevat alle blokken als lijst (voor eigen kaarten/templates).

Kant-en-klaar dashboard: [`dashboard/onbalans_laden.yaml`](dashboard/onbalans_laden.yaml) – een overzichtstabel van alle
blokken (actief blok gemarkeerd, met start- en stopgrens) en daaronder per blok een kaart met invoervelden.
Installeren: **Instellingen → Dashboards → Dashboard toevoegen → Nieuw dashboard vanaf nul** → openen → potlood →
⋮ → **Ruwe configuratie-editor** → inhoud vervangen → Opslaan.

Wijzig je het **aantal** blokken (menu *Indeling tijdblokken*), dan worden de entiteiten aangepast; voeg zo nodig
blokken toe aan of verwijder ze uit het dashboard.
Let op: een open optiemenu dat je daarna opslaat, overschrijft dashboardwijzigingen die je in de tussentijd deed.

### Gebruikersdashboard "Onbalans energie"

[`dashboard/onbalans_energie.yaml`](dashboard/onbalans_energie.yaml): status in gewone taal, tegels (prijs, status,
laden, kW, accu-SOC, drempel, tijdblok, automatisch aan/uit), één grafiek van de laatste 24 uur met onbalansprijs,
start- en stopgrens, laadmomenten (groen vlak), laadvermogen en SOC, en een tabel met de laatste start/stop-momenten.
Vereist **apexcharts-card** (HACS → Frontend). De SOC-sensor staat op `sensor.rs_system_0_dc_battery_charge`;
vervang die als je een andere accu wilt tonen.

## Aansturing via Home Assistant-entiteiten (Victron MQTT-integratie)

Praat de MQTT-integratie van Home Assistant met een eigen broker (bv. Mosquitto) in plaats van met de Cerbo,
dan komen MQTT-commando's niet bij de omvormers aan. Kies dan in **Opties → Aansturing omvormers** voor
**Home Assistant-entiteiten** en wijs de entiteiten van de Victron MQTT-integratie aan:

| Veld | Voorbeeld (MultiPlus-II 3-fase VE.Bus) |
|---|---|
| AC-ingangsstroomlimiet | `number.multiplus_ii_48_10000_140_100_id_276_current_limit` |
| Modus omvormer | `select.multiplus_ii_48_10000_140_100_id_276` |
| Modus bij start / stop | `charger_only` / `off` |
| Stroomlimiet bij stop | 0 A |

Bij **start** wordt eerst de stroomlimiet gezet op laadvermogen ÷ rendement ÷ (fasen × netspanning), naar beneden
afgerond op de stap van de entiteit (10 kW → 15 A per fase), en daarna de modus. Bij **stop** gaat eerst de limiet
naar de stopwaarde en daarna eventueel de modus. Een waarde die al goed staat wordt niet opnieuw geschreven.
In testmodus wordt alleen gelogd.

> Let op: VE.Bus dwingt een minimale stroomlimiet af (bij een MultiPlus-II 48/10000 met PowerAssist is 0 A in de
> praktijk 8,6 A, en blijft hij dus ~5 kW laden). Kies daarom bij stop de modus `off`; dan stopt het laden wel.

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
| `sensor.…_status` | uit / wachten / startvertraging / laden / stopvertraging / geen_tijdblok / geen_prijs / handmatig_aan / handmatig_uit + `reden`, `sturing`, `laatste_acties` |
| `sensor.…_actief_tijdblok` | actief blok + alle instellingen + overzicht van alle blokken |
| `sensor.…_drempel` | drempel van het actieve blok + `startgrens` / `stopgrens` (handig in een grafiek) |
| `sensor.…_laadvermogen_setpoint` | kW + stromen, max-limieten |
| `binary_sensor.…_laden` | wordt er geladen |
| `switch.…_automatische_sturing` | hoofdschakelaar |
| `select.onbalans_laden_sturing` | algemene sturing: per tijdblok / alle blokken onbalans, handmatig aan of uit |
| `switch.…_testmodus_niet_versturen` | alleen loggen, niets publiceren |

## Testen

```
pip install pytest-homeassistant-custom-component
pytest
```
