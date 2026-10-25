# Changelog

## 2026.10.0

First release. Based on the IoTaWatt integration in Home Assistant core
2026.10.4, with these changes:

- **Overrides the built-in integration** (same `iotawatt` domain), picking up
  existing config entries and entities.
- **Configurable polling interval**: 5–3600 s in multiples of 5 s, default 30 s
  as in core. Power values are averaged over the interval (it is passed to the
  library as the query timespan).
- **All sensors on one device**: output sensors get the unique ID
  `{mac}-output-{name}-{unit}`, compatible with `llamafilm/iotawatt-hacs`, and
  keep the entity IDs core gave them. The device has a name, configuration URL
  and firmware version. The config flow sets the entry's unique ID to the MAC
  address and aborts (updating the host) when a configured device is added again.
- **Optional lifetime energy sensors** (`TOTAL_INCREASING`, never reset).
- **Optional live power sensors**: ~1 s readings from the device's status
  endpoint for selected power inputs and outputs, polled every 1–60 s (default
  1 s). A failing live poll only makes the live sensors unavailable.
- **Device status entities** (diagnostic, polled every 60 s): last restart, RTC
  battery, uploader state and last upload, and (disabled by default) WiFi signal,
  WiFi connected since, free memory, sample rate, samples per cycle and datalog
  last entry.
- **Diagnostics** download with secrets redacted.
- **Self-contained**: bundles the
  [iotawattpy-nosignal](https://github.com/No-Signal/iotawattpy) library fork
  (v0.4.0) instead of installing `ha-iotawattpy`, so Home Assistant installs
  nothing at startup. The fork adds live readings, device status, a MAC address
  accessor, one shared digest-auth challenge, per-device request serialisation
  and a quieter log at 5 s polling.
