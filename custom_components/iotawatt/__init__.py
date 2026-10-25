"""The iotawatt integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_LIVE_SENSORS
from .coordinator import (
    IotawattConfigEntry,
    IotawattLiveUpdater,
    IotawattStatusUpdater,
    IotawattUpdater,
)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: IotawattConfigEntry) -> bool:
    """Set up iotawatt from a config entry."""
    coordinator = IotawattUpdater(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.api is not None
    coordinator.status = IotawattStatusUpdater(hass, entry, coordinator.api)
    # A status failure only makes the device status entities unavailable.
    await coordinator.status.async_refresh()
    if entry.options.get(CONF_LIVE_SENSORS):
        coordinator.live = IotawattLiveUpdater(hass, entry, coordinator.api)
        # A live failure only makes the live sensors unavailable.
        await coordinator.live.async_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IotawattConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
