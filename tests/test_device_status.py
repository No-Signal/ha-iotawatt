"""Test the IoTaWatt device status entities and diagnostics."""

from dataclasses import replace
from datetime import timedelta
import json
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
import httpx
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.iotawatt.const import DOMAIN
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntryDisabler
from homeassistant.setup import async_setup_component

from . import DEVICE_STATUS, EMPTY_DEVICE_STATUS, INPUT_SENSOR

INPUT_STANDARD = "sensor.test_device_my_sensor"

# entity ID: (unique ID key, device class, enabled by default)
STATUS_ENTITIES = {
    "sensor.test_device_last_restart": (
        "last_restart",
        SensorDeviceClass.TIMESTAMP,
        True,
    ),
    "sensor.test_device_wifi_signal": (
        "wifi_signal",
        SensorDeviceClass.SIGNAL_STRENGTH,
        False,
    ),
    "sensor.test_device_wifi_connected_since": (
        "wifi_connected_since",
        SensorDeviceClass.TIMESTAMP,
        False,
    ),
    "sensor.test_device_free_memory": (
        "free_memory",
        SensorDeviceClass.DATA_SIZE,
        False,
    ),
    "sensor.test_device_sample_rate": ("sample_rate", None, False),
    "sensor.test_device_samples_per_cycle": ("samples_per_cycle", None, False),
    "sensor.test_device_datalog_last_entry": (
        "datalog_last_entry",
        SensorDeviceClass.TIMESTAMP,
        False,
    ),
    "binary_sensor.test_device_rtc_battery": (
        "rtc_battery",
        BinarySensorDeviceClass.BATTERY,
        True,
    ),
    "binary_sensor.test_device_influxdb_uploader": (
        "uploader_influxDB",
        BinarySensorDeviceClass.RUNNING,
        True,
    ),
    "binary_sensor.test_device_pvoutput_uploader": (
        "uploader_PVoutput",
        BinarySensorDeviceClass.RUNNING,
        True,
    ),
    "sensor.test_device_influxdb_last_upload": (
        "uploader_influxDB_last_post",
        SensorDeviceClass.TIMESTAMP,
        True,
    ),
    "sensor.test_device_pvoutput_last_upload": (
        "uploader_PVoutput_last_post",
        SensorDeviceClass.TIMESTAMP,
        True,
    ),
}


@pytest.fixture
def mock_status(mock_iotawatt: MagicMock) -> MagicMock:
    """Mock a device with a full status report and one input."""
    mock_iotawatt.getSensors.return_value["sensors"]["input_1"] = INPUT_SENSOR
    mock_iotawatt.getDeviceStatus.return_value = DEVICE_STATUS
    return mock_iotawatt


async def _setup(hass: HomeAssistant) -> None:
    """Set up the integration."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Advance to the next status poll."""
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _status_entities(
    entity_registry: er.EntityRegistry, entry: MockConfigEntry
) -> set[str]:
    """Return the entity IDs of the status entities in the registry."""
    return {
        entity.entity_id
        for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        if "-status-" in entity.unique_id
    }


async def test_status_entities(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    mock_status: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test the status entities, their defaults and their device."""
    await _setup(hass)

    assert entry.runtime_data.status.update_interval == timedelta(seconds=60)
    assert _status_entities(entity_registry, entry) == set(STATUS_ENTITIES)
    (device,) = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    for entity_id, (key, device_class, enabled) in STATUS_ENTITIES.items():
        registry_entry = entity_registry.async_get(entity_id)
        assert registry_entry is not None
        assert registry_entry.unique_id == f"mock-mac-status-{key}"
        assert registry_entry.entity_category is EntityCategory.DIAGNOSTIC
        assert registry_entry.device_id == device.id
        assert registry_entry.original_device_class == device_class
        assert (registry_entry.disabled_by is None) is enabled
        if not enabled:
            assert registry_entry.disabled_by is RegistryEntryDisabler.INTEGRATION
            assert hass.states.get(entity_id) is None

    state = hass.states.get("sensor.test_device_last_restart")
    assert state is not None
    assert state.state == "2025-10-24T10:00:00+00:00"
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.TIMESTAMP
    state = hass.states.get("binary_sensor.test_device_rtc_battery")
    assert state is not None
    assert state.state == STATE_OFF
    state = hass.states.get("binary_sensor.test_device_influxdb_uploader")
    assert state is not None
    assert state.state == STATE_ON
    state = hass.states.get("binary_sensor.test_device_pvoutput_uploader")
    assert state is not None
    assert state.state == STATE_OFF
    state = hass.states.get("sensor.test_device_influxdb_last_upload")
    assert state is not None
    assert state.state == "2025-10-25T13:46:30+00:00"
    assert state.attributes["message"] is None
    state = hass.states.get("sensor.test_device_pvoutput_last_upload")
    assert state is not None
    # Never uploaded (lastpost 0), but the message says why.
    assert state.state == STATE_UNKNOWN
    assert state.attributes["message"] == "Invalid API key"


async def test_disabled_status_sensor_values(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_status: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test the values of the status sensors that are disabled by default."""
    await _setup(hass)
    for entity_id in STATUS_ENTITIES:
        if entity_id.startswith("sensor.") and hass.states.get(entity_id) is None:
            entity_registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    expected = {
        "sensor.test_device_wifi_signal": "-61",
        "sensor.test_device_wifi_connected_since": "2025-10-24T10:00:42+00:00",
        "sensor.test_device_free_memory": "18640",
        "sensor.test_device_sample_rate": "38.9",
        "sensor.test_device_samples_per_cycle": "412.5",
        "sensor.test_device_datalog_last_entry": "2025-10-25T13:46:35+00:00",
    }
    for entity_id, value in expected.items():
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.state == value, entity_id


async def test_sw_version(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    device_registry: dr.DeviceRegistry,
    mock_status: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test the firmware version is set on the device and follows updates."""
    await _setup(hass)
    (device,) = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert device.sw_version == "02_08_04"

    mock_status.getDeviceStatus.return_value = replace(
        DEVICE_STATUS, stats=replace(DEVICE_STATUS.stats, version="02_09_00")
    )
    await _tick(hass, freezer)

    device = device_registry.async_get(device.id)
    assert device is not None
    assert device.sw_version == "02_09_00"


async def test_old_firmware(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_status: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test fields missing on older firmware create no entity."""
    mock_status.getDeviceStatus.return_value = replace(
        DEVICE_STATUS,
        stats=replace(DEVICE_STATUS.stats, lowbat=None),
        wifi=replace(DEVICE_STATUS.wifi, rssi=None),
        datalogs=None,
        uploaders=None,
    )
    await _setup(hass)

    assert entry.state is ConfigEntryState.LOADED
    assert _status_entities(entity_registry, entry) == {
        "sensor.test_device_last_restart",
        "sensor.test_device_wifi_connected_since",
        "sensor.test_device_free_memory",
        "sensor.test_device_sample_rate",
        "sensor.test_device_samples_per_cycle",
    }


async def test_field_disappears(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_status: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test an entity becomes unavailable when its field disappears."""
    await _setup(hass)

    mock_status.getDeviceStatus.return_value = replace(DEVICE_STATUS, uploaders=())
    await _tick(hass, freezer)

    state = hass.states.get("binary_sensor.test_device_influxdb_uploader")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE
    state = hass.states.get("sensor.test_device_last_restart")
    assert state is not None
    assert state.state != STATE_UNAVAILABLE


async def test_status_failure_at_setup(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    entity_registry: er.EntityRegistry,
    mock_status: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test a status failure doesn't block setup; entities appear later."""
    mock_status.getDeviceStatus.side_effect = httpx.ConnectError("timeout")
    await _setup(hass)

    assert entry.state is ConfigEntryState.LOADED
    assert _status_entities(entity_registry, entry) == set()
    state = hass.states.get(INPUT_STANDARD)
    assert state is not None
    assert state.state == "23"

    mock_status.getDeviceStatus.side_effect = None
    await _tick(hass, freezer)

    assert _status_entities(entity_registry, entry) == set(STATUS_ENTITIES)


async def test_status_failure_later(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_status: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test a failing status poll only affects the status entities."""
    await _setup(hass)

    mock_status.getDeviceStatus.side_effect = httpx.ConnectError("timeout")
    await _tick(hass, freezer)

    state = hass.states.get("sensor.test_device_last_restart")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE
    state = hass.states.get(INPUT_STANDARD)
    assert state is not None
    assert state.state != STATE_UNAVAILABLE


async def test_empty_status(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_iotawatt: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test a status without any sections creates no entities."""
    mock_iotawatt.getDeviceStatus.return_value = EMPTY_DEVICE_STATUS
    await _setup(hass)

    assert _status_entities(entity_registry, entry) == set()


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_status: MagicMock,
) -> None:
    """Test diagnostics include the status and sensors without secrets."""
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    hass.config_entries.async_update_entry(
        entry,
        data={"host": "1.2.3.4", "username": "admin", "password": "s3cret"},
        options={"scan_interval": 30},
    )
    assert await async_setup_component(hass, "diagnostics", {})
    await _setup(hass)

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diagnostics["entry"] == {
        "data": {
            "host": "**REDACTED**",
            "username": "**REDACTED**",
            "password": "**REDACTED**",
        },
        "options": {"scan_interval": 30},
    }
    assert diagnostics["device_status"]["stats"]["version"] == "02_08_04"
    assert diagnostics["device_status"]["wifi"]["ssid"] == "**REDACTED**"
    assert diagnostics["device_status"]["wifi"]["ip"] == "**REDACTED**"
    assert diagnostics["device_status"]["wifi"]["mac"] == "**REDACTED**"
    assert diagnostics["sensors"]["input_1"]["name"] == "My Sensor"
    dumped = json.dumps(diagnostics)
    for secret in (
        "1.2.3.4",
        "admin",
        "s3cret",
        "mock-mac",
        "home-network",
        "192.168.1.50",
        "A0:20:A6",
    ):
        assert secret not in dumped
