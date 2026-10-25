"""Test the IoTaWatt live power sensors."""

from datetime import timedelta
import logging
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
import httpx
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.iotawatt.const import (
    CONF_LIFETIME_SENSORS,
    CONF_LIVE_INTERVAL,
    CONF_LIVE_SENSORS,
    CONF_SCAN_INTERVAL,
)
from custom_components.iotawatt.iotawattpy_nosignal.status import LiveReading
from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorStateClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import (
    INPUT_LIFETIME_SENSOR,
    INPUT_SENSOR,
    INPUT_TOTAL_SENSOR,
    INPUT_VOLTAGE_SENSOR,
    OUTPUT_POWER_SENSOR,
)

INPUT_LIVE = "sensor.test_device_my_sensor_live"
OUTPUT_LIVE = "sensor.test_device_total_power_live"
INPUT_STANDARD = "sensor.test_device_my_sensor"

LIVE_STATUS = {
    "input_0": LiveReading(volts=121.4, hz=59.98),
    "input_1": LiveReading(watts=1523.0, power_factor=0.98),
    "output_Total_power": LiveReading(value=2365.2, unit="Watts"),
}


@pytest.fixture
def mock_sensors(mock_iotawatt: MagicMock) -> MagicMock:
    """Mock a device with voltage, power, energy and output sensors."""
    mock_iotawatt.getSensors.return_value["sensors"].update(
        {
            "input_0": INPUT_VOLTAGE_SENSOR,
            "input_1": INPUT_SENSOR,
            "input_1_total_energy": INPUT_TOTAL_SENSOR,
            "input_1_lifetime_energy": INPUT_LIFETIME_SENSOR,
            "output_Total_power": OUTPUT_POWER_SENSOR,
        }
    )
    mock_iotawatt.getLiveStatus.return_value = LIVE_STATUS
    return mock_iotawatt


def _entry(
    hass: HomeAssistant, entry: MockConfigEntry, **options: object
) -> MockConfigEntry:
    """Set the options of the config entry."""
    hass.config_entries.async_update_entry(entry, options=options)
    return entry


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _live_unique_ids(
    entity_registry: er.EntityRegistry, entry: MockConfigEntry
) -> set[str]:
    """Return the unique IDs of the live sensors in the registry."""
    return {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        if entity.unique_id.endswith("-live")
    }


async def test_no_live_sensors_by_default(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_sensors: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test no live sensors exist and nothing is polled without a selection."""
    entry = _entry(hass, entry)
    await _setup(hass, entry)

    assert entry.runtime_data.live is None
    assert _live_unique_ids(entity_registry, entry) == set()
    mock_sensors.getLiveStatus.assert_not_awaited()


async def test_live_sensors(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    mock_sensors: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test selecting an input and an output creates exactly those sensors."""
    entry = _entry(
        hass, entry, **{CONF_LIVE_SENSORS: ["input_1", "output_Total_power"]}
    )
    await _setup(hass, entry)

    assert _live_unique_ids(entity_registry, entry) == {
        "mock-mac-input-1-Watts-live",
        "mock-mac-output-Total_power-Watts-live",
    }

    state = hass.states.get(INPUT_LIVE)
    assert state is not None
    assert state.state == "1523.0"
    assert state.attributes[ATTR_DEVICE_CLASS] == "power"
    assert state.attributes[ATTR_STATE_CLASS] is SensorStateClass.MEASUREMENT
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfPower.WATT
    state = hass.states.get(OUTPUT_LIVE)
    assert state is not None
    assert state.state == "2365.2"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfPower.WATT

    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert len(devices) == 1
    for entity_id in (INPUT_LIVE, OUTPUT_LIVE, INPUT_STANDARD):
        registry_entry = entity_registry.async_get(entity_id)
        assert registry_entry is not None
        assert registry_entry.device_id == devices[0].id
        assert registry_entry.disabled_by is None

    # The live sensors share the main coordinator's library instance.
    assert entry.runtime_data.live.api is mock_sensors


@pytest.mark.parametrize(
    ("options", "seconds"), [({}, 1), ({CONF_LIVE_INTERVAL: 5}, 5)]
)
async def test_live_interval(
    hass: HomeAssistant,
    mock_sensors: MagicMock,
    options: dict[str, int],
    seconds: int,
    entry: MockConfigEntry,
) -> None:
    """Test the live poll interval follows the option."""
    entry = _entry(hass, entry, **{CONF_LIVE_SENSORS: ["input_1"], **options})
    await _setup(hass, entry)

    assert entry.runtime_data.live.update_interval == timedelta(seconds=seconds)


async def test_live_sensor_updates(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_sensors: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test live sensors follow the live poll."""
    entry = _entry(hass, entry, **{CONF_LIVE_SENSORS: ["input_1"]})
    await _setup(hass, entry)
    mock_sensors.getLiveStatus.return_value = {"input_1": LiveReading(watts=12.0)}

    freezer.tick(timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(INPUT_LIVE)
    assert state is not None
    assert state.state == "12.0"


async def test_live_failure_only_affects_live_sensors(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    mock_sensors: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test a failing live poll makes only live sensors unavailable, quietly."""
    entry = _entry(hass, entry, **{CONF_LIVE_SENSORS: ["input_1"]})
    await _setup(hass, entry)
    mock_sensors.getLiveStatus.side_effect = httpx.ConnectError("timeout")

    caplog.clear()
    with caplog.at_level(logging.INFO):
        for _ in range(5):
            freezer.tick(timedelta(seconds=1))
            async_fire_time_changed(hass)
            await hass.async_block_till_done()

        state = hass.states.get(INPUT_LIVE)
        assert state is not None
        assert state.state == STATE_UNAVAILABLE
        state = hass.states.get(INPUT_STANDARD)
        assert state is not None
        assert state.state != STATE_UNAVAILABLE
        assert mock_sensors.getLiveStatus.await_count >= 5

        mock_sensors.getLiveStatus.side_effect = None
        for _ in range(3):
            freezer.tick(timedelta(seconds=1))
            async_fire_time_changed(hass)
            await hass.async_block_till_done()

    state = hass.states.get(INPUT_LIVE)
    assert state is not None
    assert state.state == "1523.0"
    messages = [record.getMessage() for record in caplog.records]
    assert len([m for m in messages if "Error fetching Test Device live" in m]) == 1
    assert len([m for m in messages if "Test Device live data recovered" in m]) == 1


async def test_live_failure_at_setup(
    hass: HomeAssistant, mock_sensors: MagicMock, entry: MockConfigEntry
) -> None:
    """Test a live failure during setup doesn't block it."""
    mock_sensors.getLiveStatus.side_effect = httpx.ConnectError("timeout")
    entry = _entry(hass, entry, **{CONF_LIVE_SENSORS: ["input_1"]})
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get(INPUT_LIVE)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE
    state = hass.states.get(INPUT_STANDARD)
    assert state is not None
    assert state.state == "23"


async def test_live_key_missing_from_reading(
    hass: HomeAssistant, mock_sensors: MagicMock, entry: MockConfigEntry
) -> None:
    """Test a sensor is unavailable while its key is missing from the reading."""
    mock_sensors.getLiveStatus.return_value = {"input_1": LiveReading(watts=5.0)}
    entry = _entry(
        hass, entry, **{CONF_LIVE_SENSORS: ["input_1", "output_Total_power"]}
    )
    await _setup(hass, entry)

    state = hass.states.get(OUTPUT_LIVE)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


async def test_selected_key_missing_from_device(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_sensors: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test a selected key the device no longer has is skipped."""
    entry = _entry(hass, entry, **{CONF_LIVE_SENSORS: ["input_1", "output_Renamed"]})
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert _live_unique_ids(entity_registry, entry) == {"mock-mac-input-1-Watts-live"}


async def test_deselected_live_sensor_removed(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_sensors: MagicMock,
    entry: MockConfigEntry,
) -> None:
    """Test deselecting a channel removes its live sensor after the reload."""
    entry = _entry(
        hass, entry, **{CONF_LIVE_SENSORS: ["input_1", "output_Total_power"]}
    )
    await _setup(hass, entry)
    assert entity_registry.async_get(OUTPUT_LIVE) is not None

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCAN_INTERVAL: 30,
            CONF_LIFETIME_SENSORS: False,
            CONF_LIVE_SENSORS: ["input_1"],
            CONF_LIVE_INTERVAL: 1,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.state is ConfigEntryState.LOADED
    assert entity_registry.async_get(OUTPUT_LIVE) is None
    assert _live_unique_ids(entity_registry, entry) == {"mock-mac-input-1-Watts-live"}

    # Deselecting everything stops live polling and removes the rest.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCAN_INTERVAL: 30,
            CONF_LIFETIME_SENSORS: False,
            CONF_LIVE_SENSORS: [],
            CONF_LIVE_INTERVAL: 1,
        },
    )
    await hass.async_block_till_done()

    assert entry.runtime_data.live is None
    assert _live_unique_ids(entity_registry, entry) == set()


async def test_options_flow_live_channel_choices(
    hass: HomeAssistant, mock_sensors: MagicMock, entry: MockConfigEntry
) -> None:
    """Test the selector lists power inputs and outputs, not energy sensors."""
    entry = _entry(hass, entry, **{CONF_LIVE_SENSORS: ["input_1", "output_Renamed"]})
    await _setup(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    schema = result["data_schema"].schema
    key = next(key for key in schema if key == CONF_LIVE_SENSORS)
    options = schema[key].config["options"]
    assert options == [
        {"value": "input_1", "label": "My Sensor"},
        {"value": "output_Total_power", "label": "Total_power"},
    ]
    # Keys no longer on the device are not offered as the default.
    assert key.default() == ["input_1"]


async def test_options_flow_device_offline(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Test the other options can be changed while the device is offline."""
    entry = _entry(
        hass,
        entry,
        **{
            CONF_SCAN_INTERVAL: 30,
            CONF_LIVE_SENSORS: ["input_1"],
            CONF_LIVE_INTERVAL: 1,
        },
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert CONF_LIVE_SENSORS not in result["data_schema"].schema
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 60, CONF_LIFETIME_SENSORS: False, CONF_LIVE_INTERVAL: 2},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_SCAN_INTERVAL: 60,
        CONF_LIFETIME_SENSORS: False,
        CONF_LIVE_SENSORS: ["input_1"],
        CONF_LIVE_INTERVAL: 2,
    }


async def test_options_flow_invalid_live_interval(
    hass: HomeAssistant, mock_sensors: MagicMock, entry: MockConfigEntry
) -> None:
    """Test a fractional live interval shows an error."""
    entry = _entry(hass, entry)
    await _setup(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 30, CONF_LIFETIME_SENSORS: False, CONF_LIVE_INTERVAL: 1.5},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_LIVE_INTERVAL: "invalid_live_interval"}
