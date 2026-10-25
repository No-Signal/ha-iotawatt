"""Test setting up sensors."""

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.iotawatt.const import DOMAIN
from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfReactivePower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from . import INPUT_SENSOR, OUTPUT_SENSOR, VAR_OUTPUT_SENSOR


async def test_sensor_type_input(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, mock_iotawatt: MagicMock
) -> None:
    """Test input sensors work."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids()) == 0

    # Discover this sensor during a regular update.
    mock_iotawatt.getSensors.return_value["sensors"]["my_sensor_key"] = INPUT_SENSOR
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids()) == 1

    state = hass.states.get("sensor.test_device_my_sensor")
    assert state is not None
    assert state.state == "23"
    assert state.attributes[ATTR_STATE_CLASS] is SensorStateClass.MEASUREMENT
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Test Device My Sensor"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfPower.WATT
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.POWER
    assert state.attributes["channel"] == "1"
    assert state.attributes["type"] == "Input"

    mock_iotawatt.getSensors.return_value["sensors"].pop("my_sensor_key")
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_device_my_sensor") is None


async def test_sensor_type_output(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, mock_iotawatt: MagicMock
) -> None:
    """Tests the sensor type of Output."""
    mock_iotawatt.getSensors.return_value["sensors"]["my_watthour_sensor_key"] = (
        OUTPUT_SENSOR
    )
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids()) == 1

    state = hass.states.get("sensor.my_watthour_sensor")
    assert state is not None
    assert state.state == "243"
    assert state.attributes[ATTR_STATE_CLASS] is SensorStateClass.TOTAL
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Test Device My WattHour Sensor"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfEnergy.WATT_HOUR
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.ENERGY
    assert state.attributes["type"] == "Output"

    mock_iotawatt.getSensors.return_value["sensors"].pop("my_watthour_sensor_key")
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.my_watthour_sensor") is None


async def test_all_sensors_attached_to_device(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
    mock_iotawatt: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test input and output sensors share the IoTaWatt device."""
    mock_iotawatt.getSensors.return_value["sensors"] = {
        "my_sensor_key": INPUT_SENSOR,
        "my_watthour_sensor_key": OUTPUT_SENSOR,
    }
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert len(devices) == 1
    device = devices[0]
    assert device.identifiers == {(DOMAIN, "mock-mac")}
    assert device.name == "Test Device"
    assert device.manufacturer == "IoTaWatt"
    assert device.configuration_url == "http://1.2.3.4"

    input_entry = entity_registry.async_get("sensor.test_device_my_sensor")
    assert input_entry is not None
    assert input_entry.unique_id == "mock-mac-input-1-Watts"
    assert input_entry.device_id == device.id

    # Outputs keep the entity ID core gave them, without a device prefix.
    output_entry = entity_registry.async_get("sensor.my_watthour_sensor")
    assert output_entry is not None
    assert output_entry.unique_id == "mock-mac-output-My WattHour Sensor-WattHours"
    assert output_entry.device_id == device.id

    assert "attempts to attach a device to an entity" not in caplog.text


async def test_output_sensor_existing_registry_entry(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_iotawatt: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test an output registered by llamafilm/iotawatt-hacs keeps its entity."""
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "mock-mac-output-My WattHour Sensor-WattHours",
        config_entry=entry,
        suggested_object_id="custom_energy",
    )
    mock_iotawatt.getSensors.return_value["sensors"]["my_watthour_sensor_key"] = (
        OUTPUT_SENSOR
    )
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.custom_energy") is not None
    assert hass.states.get("sensor.my_watthour_sensor") is None


async def test_sensor_type_output_reactive_power(
    hass: HomeAssistant, mock_iotawatt: MagicMock
) -> None:
    """Test reactive power output sensors work."""
    mock_iotawatt.getSensors.return_value["sensors"]["my_var_sensor_key"] = (
        VAR_OUTPUT_SENSOR
    )
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    # Outputs are enabled even though VAR inputs are disabled by default.
    state = hass.states.get("sensor.my_var_sensor")
    assert state is not None
    assert state.state == "500"
    assert state.attributes[ATTR_STATE_CLASS] is SensorStateClass.MEASUREMENT
    assert (
        state.attributes[ATTR_UNIT_OF_MEASUREMENT]
        == UnitOfReactivePower.VOLT_AMPERE_REACTIVE
    )
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.REACTIVE_POWER
