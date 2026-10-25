# IoTaWatt for Home Assistant (custom integration)

[![Validate](https://github.com/No-Signal/ha-iotawatt/actions/workflows/validate.yml/badge.svg)](https://github.com/No-Signal/ha-iotawatt/actions/workflows/validate.yml)
[![Test](https://github.com/No-Signal/ha-iotawatt/actions/workflows/test.yml/badge.svg)](https://github.com/No-Signal/ha-iotawatt/actions/workflows/test.yml)

This is Home Assistant's built-in [IoTaWatt](https://iotawatt.com) integration
with extra features:

- **Configurable polling interval**: 30 s by default, as in core, adjustable from
  5 s to 1 hour.
- **All sensors on one device**: output (calculated) channels get unique IDs, so
  they belong to the IoTaWatt device and can be renamed and edited in the UI.
- **Optional lifetime energy sensors**: meter readings that never reset, for the
  Energy dashboard.
- **Optional live power sensors**: about 1 second readings for the channels you
  choose, for automations that must react quickly.
- **Device status sensors** (firmware, uptime, WiFi, uploaders and more) and a
  **diagnostics** download.

It **overrides** the built-in `iotawatt` integration: it uses the same domain, so
your existing IoTaWatt config entries and entities are picked up as they are.
Home Assistant logs a warning at startup that a custom integration overrides a
core one. That is expected.

## Installation

1. In HACS, open the menu → **Custom repositories**, add
   `https://github.com/No-Signal/ha-iotawatt` with category **Integration**.
2. Install **IoTaWatt** from HACS.
3. Restart Home Assistant.

Existing IoTaWatt entries are picked up automatically. To add a new device, go to
**Settings → Devices & services → Add integration → IoTaWatt**.

## Options

Open **Settings → Devices & services → IoTaWatt → Configure**. Saving reloads the
integration.

| Option | Default | Range | What it does |
|---|---|---|---|
| Polling interval | 30 s | 5–3600 s, multiples of 5 | How often all sensors are read. Power values are averaged over this interval. Each poll makes 4 requests to the device (5 with lifetime sensors). |
| Lifetime energy sensors | off | | Adds an energy sensor per power channel that counts up from the start of the device's datalog. |
| Live power channels | none | | Power inputs and outputs to read live (see below). Hidden while the device is offline; your selection is kept. |
| Live interval | 1 s | 1–60 s | How often live channels are read. |

The polling interval must be a multiple of 5 seconds because the IoTaWatt logs
data every 5 seconds.

## Live power

A live sensor ("*name* Live") reports the device's own ~1 second average, the
value its web Status page shows. It comes from the device's status endpoint, not
from its datalog, so it reacts to a load change within about a second. The
standard sensors read the datalog, which has a 5 second resolution, so even a
5 s polling interval gives readings that are 5–10 s old.

Use live sensors when an automation needs to react within a second or two. For
dashboards, history and energy, the standard sensors are the better choice, and a
shorter polling interval is enough for "fresher" values.

Each live sensor records a state change roughly every live interval: at 1 s, up
to 86,400 states per sensor per day. Select only the channels you need. To keep
them out of history entirely, exclude them from the recorder:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.*_live
```

The device serves one connection at a time, so the integration sends its
requests one after another: live polls wait while a regular poll is running, and
the device never sees overlapping requests.

### Example: extractor fan for an induction hob

Turn the fan on quickly when the hob draws power, but turn it off slowly:
induction hobs pulse on and off at low settings, and steam lingers after cooking.

The examples assume a live sensor `sensor.iotawatt_hob_live` and a fan
`fan.extractor`; use your own entity IDs.

With a **Threshold** helper named "Hob in use" (Settings → Devices & services →
Helpers → Create helper → Threshold) on the live sensor, with upper limit 150 W
and hysteresis 50 W, the fan follows `binary_sensor.hob_in_use`:

```yaml
automation:
  - alias: Extractor fan on with the hob
    triggers:
      - trigger: state
        entity_id: binary_sensor.hob_in_use
        to: "on"
        for: "00:00:02"
    actions:
      - action: fan.turn_on
        target:
          entity_id: fan.extractor

  - alias: Extractor fan off after the hob
    triggers:
      - trigger: state
        entity_id: binary_sensor.hob_in_use
        to: "off"
        for: "00:04:00"
    actions:
      - action: fan.turn_off
        target:
          entity_id: fan.extractor
```

Or without a helper, with numeric state triggers:

```yaml
automation:
  - alias: Extractor fan follows the hob
    triggers:
      - trigger: numeric_state
        entity_id: sensor.iotawatt_hob_live
        above: 150
        for: "00:00:02"
        id: "on"
      - trigger: numeric_state
        entity_id: sensor.iotawatt_hob_live
        below: 150
        for: "00:04:00"
        id: "off"
    actions:
      - choose:
          - conditions:
              - condition: trigger
                id: "on"
            sequence:
              - action: fan.turn_on
                target:
                  entity_id: fan.extractor
        default:
          - action: fan.turn_off
            target:
              entity_id: fan.extractor
```

## Device status

These diagnostic entities are polled every 60 seconds from the device's status
endpoint. Entities for values your firmware doesn't report are not created.

| Entity | Enabled by default | Meaning |
|---|---|---|
| Last restart | yes | When the IoTaWatt firmware last started. A timestamp rather than an uptime counter, so it only changes on a restart. |
| RTC battery | yes | On when the real-time clock battery is low. |
| *id* uploader | yes | On while that uploader (influxDB, Emoncms, PVoutput, …) is running. |
| *id* last upload | yes | When that uploader last sent data. The `message` attribute holds its latest status or error message. |
| WiFi signal | no | Signal strength in dBm. |
| WiFi connected since | no | When the current WiFi connection was made. |
| Free memory | no | Free heap on the device, in bytes. |
| Sample rate | no | AC cycles sampled per second. |
| Samples per cycle | no | Samples taken per AC cycle. |
| Datalog last entry | no | Time of the newest datalog record. If it falls behind, the datalog has stalled. |

The device's firmware version is shown on the device page and updated after a
firmware update.

**Diagnostics**: on the device page, **Download diagnostics** gives the options,
latest device status and sensor list, with the host, credentials, MAC address,
SSID and IP address redacted.

## Migration notes

- **From the built-in integration**: output sensors become entity registry
  entries attached to the device. Their entity IDs normally stay the same, but
  check automations and dashboards that use them. Their friendly names now start
  with the device name, like the input sensors' already did.
- **From `llamafilm/iotawatt-hacs`**: remove that HACS repository first, then
  install this one. Output unique IDs are compatible, so your entities keep their
  IDs and settings. The per-interval "energy" entities that fork created are gone;
  core dropped them because they broke long-term statistics. Use the daily totals
  or the lifetime sensors.
- **Renaming an output on the IoTaWatt** creates a new entity, and drops the old
  name from the live channel selection. Outputs are identified by name.

## Compatibility

Requires Home Assistant 2026.10.0 or later. Each release tracks a specific Home
Assistant core version of the integration (currently 2026.10.4); see the
[changelog](CHANGELOG.md).

## Self-contained

The IoTaWatt library is bundled with the integration: a fork of `iotawattpy`,
[No-Signal/iotawattpy](https://github.com/No-Signal/iotawattpy), at
`custom_components/iotawatt/iotawattpy_nosignal/`. Home Assistant installs
nothing for this integration and needs no internet access to start it. The
`ha-iotawattpy` package that core installs may stay installed; it is not used and
doesn't clash.

## Credits and licence

The integration is derived from Home Assistant core's IoTaWatt integration
(Apache-2.0). The bundled library is GPL-3.0-or-later. The repository and the
release zip, which contain both, are distributed under GPL-3.0-or-later; the
integration's own files keep their Apache-2.0 notice. See [NOTICE](NOTICE).
