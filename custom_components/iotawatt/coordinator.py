"""IoTaWatt DataUpdateCoordinator."""

from datetime import datetime, timedelta
import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, httpx_client
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SCAN_INTERVAL, CONNECTION_ERRORS, DEFAULT_SCAN_INTERVAL, DOMAIN
from .iotawattpy_nosignal.iotawatt import Iotawatt

_LOGGER = logging.getLogger(__name__)

# Matches iotwatt data log interval
REQUEST_REFRESH_DEFAULT_COOLDOWN = 5

type IotawattConfigEntry = ConfigEntry[IotawattUpdater]


def iotawatt_device_info(entry: IotawattConfigEntry, mac: str) -> dr.DeviceInfo:
    """Return the device info shared by every entity of an IoTaWatt."""
    return dr.DeviceInfo(
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        identifiers={(DOMAIN, mac)},
        manufacturer="IoTaWatt",
        model="IoTaWatt",
        name=entry.title,
        configuration_url=f"http://{entry.data[CONF_HOST]}",
    )


class IotawattUpdater(DataUpdateCoordinator):
    """Class to manage fetching update data from the IoTaWatt Energy Device."""

    api: Iotawatt | None = None
    config_entry: IotawattConfigEntry

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
