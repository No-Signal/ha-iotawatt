"""Test the IoTaWatt options and polling interval."""

from datetime import timedelta
import logging
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
import httpx
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import respx

from custom_components.iotawatt.const import (
    CONF_LIFETIME_SENSORS,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData

HOST = "1.2.3.4"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_default_interval(
    hass: HomeAssistant, mock_iotawatt: MagicMock, entry: MockConfigEntry
) -> None:
    """Test without options the integration polls like core: every 30s."""
    await _setup(hass, entry)

    assert entry.runtime_data.update_interval == timedelta(seconds=30)
    mock_iotawatt.update.assert_called_once_with(timespan=30, lastUpdate=None)


async def test_options_flow(
    hass: HomeAssistant, mock_iotawatt: MagicMock, entry: MockConfigEntry
) -> None:
    """Test the options flow stores the interval and reloads the entry."""
    await _setup(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 10}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL: 10, CONF_LIFETIME_SENSORS: False}
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.update_interval == timedelta(seconds=10)
    mock_iotawatt.update.assert_called_with(timespan=10, lastUpdate=None)


async def test_options_flow_shows_current_value(
    hass: HomeAssistant, mock_iotawatt: MagicMock
) -> None:
    """Test the form defaults to the stored interval."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": HOST}, options={CONF_SCAN_INTERVAL: 60}
    )
    entry.add_to_hass(hass)
    await _setup(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    schema = result["data_schema"].schema
    key = next(key for key in schema if key == CONF_SCAN_INTERVAL)
    assert key.default() == 60


@pytest.mark.parametrize("interval", [0, 4, 3601])
async def test_options_flow_out_of_range(
    hass: HomeAssistant,
    mock_iotawatt: MagicMock,
    entry: MockConfigEntry,
    interval: int,
) -> None:
    """Test intervals outside 5-3600s are rejected."""
    await _setup(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)

    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: interval}
        )
    assert entry.options == {}


@pytest.mark.parametrize("interval", [7, 12.5, 3599])
async def test_options_flow_not_multiple_of_five(
    hass: HomeAssistant,
    mock_iotawatt: MagicMock,
    entry: MockConfigEntry,
    interval: float,
) -> None:
    """Test intervals that aren't a multiple of 5s show an error."""
    await _setup(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: interval}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_SCAN_INTERVAL: "invalid_interval"}
    assert entry.options == {}


async def test_configured_interval_used_as_timespan(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_iotawatt: MagicMock,
) -> None:
    """Test every poll averages power over the configured interval."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": HOST}, options={CONF_SCAN_INTERVAL: 15}
    )
    entry.add_to_hass(hass)
    await _setup(hass, entry)
    mock_iotawatt.update.reset_mock()

    await entry.runtime_data.async_refresh()

    assert entry.runtime_data.update_interval == timedelta(seconds=15)
    mock_iotawatt.update.assert_called_once_with(timespan=15, lastUpdate=None)


def _mock_device(router: respx.MockRouter, watts: list[float]) -> None:
    """Mock an IoTaWatt with one power input whose reading is watts[0]."""
    router.get(f"http://{HOST}/status", params={"wifi": "yes"}).respond(
        json={"wifi": {"mac": "de:ad:be:ef:00:01"}}
    )
    router.get(
        f"http://{HOST}/status", params={"inputs": "yes", "outputs": "yes"}
    ).respond(json={"inputs": [{"channel": 1, "Watts": "100"}], "outputs": []})

    def query(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("show") == "series":
            return httpx.Response(
                200, json={"series": [{"name": "Hob", "unit": "Watts"}]}
            )
        if params["select"].startswith("[time.iso"):
            return httpx.Response(200, json=[["2025-10-25T00:00:00", 1234.5]])
        return httpx.Response(200, json=[[watts[0]]])

    router.get(f"http://{HOST}/query").mock(side_effect=query)


async def test_five_second_poll_with_jitter(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a 5s poll landing twice in one datalog slot stays quiet.

    Uses the real bundled library against a mocked device.
    """
    freezer.move_to("2025-10-25 12:00:00.500+00:00")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Device",
        data={"host": HOST},
        options={CONF_SCAN_INTERVAL: 5},
    )
    entry.add_to_hass(hass)
    watts = [100.0]

    with respx.mock(assert_all_called=False) as router:
        _mock_device(router, watts)
        await _setup(hass, entry)
        state = hass.states.get("sensor.test_device_hob")
        assert state is not None
        assert state.state == "100.0"

        # Scheduling jitter: the next poll runs 4s later, in the same 5s slot.
        freezer.tick(timedelta(seconds=4))
        watts[0] = 2000.0
        with caplog.at_level(logging.DEBUG):
            await entry.runtime_data.async_refresh()
            await hass.async_block_till_done()

    assert "update() called too soon" in caplog.text
    assert not [
        record
        for record in caplog.records
        if "iotawattpy" in record.name and record.levelno >= logging.WARNING
    ]
    assert entry.runtime_data.last_update_success
    state = hass.states.get("sensor.test_device_hob")
    assert state is not None
    assert state.state != STATE_UNAVAILABLE
    assert state.state == "2000.0"


async def test_options_flow_lifetime_sensors(
    hass: HomeAssistant, mock_iotawatt_class: MagicMock, entry: MockConfigEntry
) -> None:
    """Test enabling lifetime sensors reloads with them requested."""
    await _setup(hass, entry)
    assert mock_iotawatt_class.call_args.kwargs["includeLifetimeSensors"] is False
    result = await hass.config_entries.options.async_init(entry.entry_id)

    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 30, CONF_LIFETIME_SENSORS: True}
    )
    await hass.async_block_till_done()

    assert entry.options == {CONF_SCAN_INTERVAL: 30, CONF_LIFETIME_SENSORS: True}
    assert mock_iotawatt_class.call_args.kwargs["includeLifetimeSensors"] is True
