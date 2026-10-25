"""Tests for the IoTaWatt integration."""

from datetime import UTC, datetime

from custom_components.iotawatt.iotawattpy_nosignal.sensor import Sensor
from custom_components.iotawatt.iotawattpy_nosignal.status import (
    DatalogStatus,
    DeviceSettings,
    DeviceStats,
    DeviceStatus,
    UploaderStatus,
    WifiStatus,
)

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
OUTPUT_POWER_SENSOR = Sensor(
    channel="N/A",
    base_name="Total_power",
    suffix=None,
    io_type="Output",
    unit="Watts",
    value=2365,
    begin="",
    mac_addr="mock-mac",
)
INPUT_VOLTAGE_SENSOR = Sensor(
    channel="0",
    base_name="Mains",
    suffix=None,
    io_type="Input",
    unit="Volts",
    value=121.4,
    begin="",
    mac_addr="mock-mac",
)

DEVICE_STATUS = DeviceStatus(
    device=DeviceSettings(
        name="IotaWatt", timediff=-300, allowdst=True, update="MAJOR"
    ),
    stats=DeviceStats(
        cyclerate=412.5,
        chanrate=38.9,
        starttime=datetime(2025, 10, 24, 10, 0, tzinfo=UTC),
        currenttime=datetime(2025, 10, 25, 13, 46, 40, tzinfo=UTC),
        runseconds=100000,
        stack=18640,
        version="02_08_04",
        frequency=59.98,
        lowbat=False,
    ),
    wifi=WifiStatus(
        connecttime=datetime(2025, 10, 24, 10, 0, 42, tzinfo=UTC),
        ssid="home-network",
        ip="192.168.1.50",
        channel=6,
        rssi=-61,
        mac="A0:20:A6:00:00:01",
    ),
    datalogs=(
        DatalogStatus(
            id="Current",
            firstkey=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
            lastkey=datetime(2025, 10, 25, 13, 46, 35, tzinfo=UTC),
            size=61440000,
            interval=5,
        ),
    ),
    uploaders=(
        UploaderStatus(
            id="influxDB",
            status="running",
            lastpost=datetime(2025, 10, 25, 13, 46, 30, tzinfo=UTC),
            message=None,
        ),
        UploaderStatus(
            id="PVoutput", status="stopped", lastpost=None, message="Invalid API key"
        ),
    ),
)
# What firmware without any of the status sections would report.
EMPTY_DEVICE_STATUS = DeviceStatus(
    device=None, stats=None, wifi=None, datalogs=None, uploaders=None
)
