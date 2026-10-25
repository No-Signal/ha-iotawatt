"""Constants for the IoTaWatt integration."""

import json

import httpx

DOMAIN = "iotawatt"
VOLT_AMPERE_REACTIVE_HOURS = "VARh"

CONNECTION_ERRORS = (KeyError, json.JSONDecodeError, httpx.HTTPError)

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 3600
# The IoTaWatt datalog has a 5 second resolution.
SCAN_INTERVAL_STEP = 5

CONF_LIFETIME_SENSORS = "lifetime_sensors"
