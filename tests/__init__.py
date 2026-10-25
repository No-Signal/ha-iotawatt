"""Tests for the IoTaWatt integration."""

from custom_components.iotawatt.iotawattpy_nosignal.sensor import Sensor

INPUT_SENSOR = Sensor(
    channel="1",
    base_name="My Sensor",
    suffix=None,
    io_type="Input",
    unit="Watts",
    value=23,
    begin="",
    mac_addr="mock-mac",
)
OUTPUT_SENSOR = Sensor(
    channel="N/A",
    base_name="My WattHour Sensor",
    suffix=None,
    io_type="Output",
    unit="WattHours",
    value=243,
    begin="",
    mac_addr="mock-mac",
    fromStart=True,
)
VAR_OUTPUT_SENSOR = Sensor(
    channel="N/A",
    base_name="My VAR Sensor",
    suffix=None,
    io_type="Output",
    unit="VAR",
    value=500,
    begin="",
    mac_addr="mock-mac",
)
INPUT_LIFETIME_SENSOR = Sensor(
    channel="1",
    base_name="My Sensor",
    suffix=".wh",
    io_type="Input",
    unit="WattHours",
    value=1234567.891,
    begin="2020-09-13T14:26:40",
    mac_addr="mock-mac",
    lifetime=True,
)
INPUT_TOTAL_SENSOR = Sensor(
    channel="1",
    base_name="My Sensor",
    suffix=".wh",
    io_type="Input",
    unit="WattHours",
    value=4567,
    begin="2025-10-25T00:00:00",
    mac_addr="mock-mac",
    fromStart=True,
)
