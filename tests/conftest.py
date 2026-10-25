"""Test fixtures for IoTaWatt."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.iotawatt.const import DOMAIN
from homeassistant.core import HomeAssistant

from . import EMPTY_DEVICE_STATUS


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in all tests."""
    yield  # noqa: PT022


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    """Mock config entry added to HA."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Test Device", data={"host": "1.2.3.4"}
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_iotawatt_class(entry: MockConfigEntry) -> Generator[MagicMock]:
    """Mock the iotawatt class."""
    with patch("custom_components.iotawatt.coordinator.Iotawatt") as mock:
        instance = mock.return_value
        instance.connect = AsyncMock(return_value=True)
        instance.update = AsyncMock()
        instance.getSensors.return_value = {"sensors": {}}
        instance.getLiveStatus = AsyncMock(return_value={})
        instance.getDeviceStatus = AsyncMock(return_value=EMPTY_DEVICE_STATUS)
        instance.getMacAddress.return_value = "mock-mac"
        yield mock


@pytest.fixture
def mock_iotawatt(mock_iotawatt_class: MagicMock) -> MagicMock:
    """Mock iotawatt."""
    return mock_iotawatt_class.return_value
