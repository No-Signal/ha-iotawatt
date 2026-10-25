"""IoTaWatt DataUpdateCoordinator."""

from datetime import datetime, timedelta
import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, httpx_client
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_LIFETIME_SENSORS,
    CONF_LIVE_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONNECTION_ERRORS,
    DEFAULT_LIVE_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    STATUS_SCAN_INTERVAL,
)
from .iotawattpy_nosignal.iotawatt import Iotawatt
from .iotawattpy_nosignal.status import DeviceStatus, LiveReading

_LOGGER = logging.getLogger(__name__)

# Matches iotwatt data log interval
REQUEST_REFRESH_DEFAULT_COOLDOWN = 5

type IotawattConfigEntry = ConfigEntry[IotawattUpdater]


def iotawatt_device_info(entry: IotawattConfigEntry, mac: str) -> dr.DeviceInfo:
    """Return the device info shared by every entity of an IoTaWatt."""
    device_info = dr.DeviceInfo(
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        identifiers={(DOMAIN, mac)},
        manufacturer="IoTaWatt",
        model="IoTaWatt",
        name=entry.title,
        configuration_url=f"http://{entry.data[CONF_HOST]}",
    )
    # Only set when known, so a failed status poll doesn't clear it.
    if (status := entry.runtime_data.status) is not None and (
        sw_version := status.sw_version
    ):
        device_info["sw_version"] = sw_version
    return device_info


class IotawattUpdater(DataUpdateCoordinator):
    """Class to manage fetching update data from the IoTaWatt Energy Device."""

    api: Iotawatt | None = None
    config_entry: IotawattConfigEntry
    live: IotawattLiveUpdater | None = None
    status: IotawattStatusUpdater | None = None

    def __init__(self, hass: HomeAssistant, entry: IotawattConfigEntry) -> None:
        """Initialize IotaWattUpdater object."""
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=timedelta(seconds=interval),
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=REQUEST_REFRESH_DEFAULT_COOLDOWN,
                immediate=True,
            ),
        )

        self._last_run: datetime | None = None
        # Power readings are averaged over the poll interval.
        self._timespan: int = interval

    def update_last_run(self, last_run: datetime) -> None:
        """Notify coordinator of a sensor last update time."""
        # We want to fetch the data from the iotawatt since HA was last shutdown.
        # We retrieve from the sensor last updated.
        # This method is called from each sensor upon their state being restored.
        if self._last_run is None or last_run > self._last_run:
            self._last_run = last_run

    @override
    async def _async_update_data(self):
        """Fetch sensors from IoTaWatt device."""
        if self.api is None:
            api = Iotawatt(
                self.config_entry.title,
                self.config_entry.data[CONF_HOST],
                httpx_client.get_async_client(self.hass),
                self.config_entry.data.get(CONF_USERNAME),
                self.config_entry.data.get(CONF_PASSWORD),
                integratedInterval="d",
                includeNonTotalSensors=False,
                includeLifetimeSensors=self.config_entry.options.get(
                    CONF_LIFETIME_SENSORS, False
                ),
            )
            try:
                is_authenticated = await api.connect()
            except CONNECTION_ERRORS as err:
                raise UpdateFailed("Connection failed") from err

            if not is_authenticated:
                raise UpdateFailed("Authentication error")

            self.api = api

        try:
            await self.api.update(timespan=self._timespan, lastUpdate=self._last_run)
        except CONNECTION_ERRORS as err:
            raise UpdateFailed("Connection failed") from err
        self._last_run = None
        return self.api.getSensors()


class IotawattLiveUpdater(DataUpdateCoordinator[dict[str, LiveReading]]):
    """Poll live (~1 s average) readings from the IoTaWatt status endpoint."""

    config_entry: IotawattConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: IotawattConfigEntry, api: Iotawatt
    ) -> None:
        """Initialize the live updater, sharing the main coordinator's API."""
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            config_entry=entry,
            name=f"{entry.title} live",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_LIVE_INTERVAL, DEFAULT_LIVE_INTERVAL)
            ),
            always_update=False,
        )
        self.api = api

    @override
    async def _async_update_data(self) -> dict[str, LiveReading]:
        """Fetch live readings from the IoTaWatt device."""
        try:
            return await self.api.getLiveStatus()
        except CONNECTION_ERRORS as err:
            raise UpdateFailed("Connection failed") from err


class IotawattStatusUpdater(DataUpdateCoordinator[DeviceStatus]):
    """Poll device health information from the IoTaWatt status endpoint."""

    config_entry: IotawattConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: IotawattConfigEntry, api: Iotawatt
    ) -> None:
        """Initialize the status updater, sharing the main coordinator's API."""
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            config_entry=entry,
            name=f"{entry.title} status",
            update_interval=timedelta(seconds=STATUS_SCAN_INTERVAL),
        )
        self.api = api

    @property
    def sw_version(self) -> str | None:
        """Return the firmware version from the last status poll."""
        if self.data is None or self.data.stats is None:
            return None
        return self.data.stats.version

    @override
    async def _async_update_data(self) -> DeviceStatus:
        """Fetch the device status from the IoTaWatt device."""
        try:
            status = await self.api.getDeviceStatus()
        except CONNECTION_ERRORS as err:
            raise UpdateFailed("Connection failed") from err
        if status.stats is not None and status.stats.version:
            self._async_update_sw_version(status.stats.version)
        return status

    @callback
    def _async_update_sw_version(self, sw_version: str) -> None:
        """Update the device's firmware version, e.g. after a firmware update."""
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, self.api.getMacAddress())}
        )
        if device is not None and device.sw_version != sw_version:
            device_registry.async_update_device(device.id, sw_version=sw_version)
