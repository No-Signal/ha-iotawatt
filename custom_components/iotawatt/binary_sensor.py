"""Support for IoTaWatt device status binary sensors."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IotawattConfigEntry
from .entity import (
    IotaWattStatusEntity,
    IotaWattStatusEntityDescription,
    async_add_status_entities,
    get_uploader,
)
from .iotawattpy_nosignal.status import DeviceStatus


@dataclass(frozen=True, kw_only=True)
class IotaWattStatusBinarySensorEntityDescription(
    IotaWattStatusEntityDescription, BinarySensorEntityDescription
):
    """Describes an IoTaWatt device status binary sensor."""


RTC_BATTERY_DESCRIPTION = IotaWattStatusBinarySensorEntityDescription(
    key="rtc_battery",
    translation_key="rtc_battery",
    device_class=BinarySensorDeviceClass.BATTERY,
    value_fn=lambda status: status.stats.lowbat if status.stats else None,
)


def _uploader_description(
    uploader_id: str,
) -> IotaWattStatusBinarySensorEntityDescription:
    """Return the description of an uploader's running state."""

    def is_running(status: DeviceStatus) -> bool | None:
        if (uploader := get_uploader(status, uploader_id)) is None:
            return None
        if uploader.status is None:
            return None
        return uploader.status == "running"

    return IotaWattStatusBinarySensorEntityDescription(
        key=f"uploader_{uploader_id}",
        translation_key="uploader",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=is_running,
        uploader_id=uploader_id,
    )


def _descriptions(
    status: DeviceStatus,
) -> Iterator[IotaWattStatusBinarySensorEntityDescription]:
    """Return the binary sensor descriptions for a device status."""
    yield RTC_BATTERY_DESCRIPTION
    for uploader in status.uploaders or ():
        yield _uploader_description(uploader.id)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IotawattConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add binary sensors for passed config_entry in HA."""
    status = config_entry.runtime_data.status
    assert status is not None
    async_add_status_entities(
        status, async_add_entities, _descriptions, IotaWattStatusBinarySensor
    )


class IotaWattStatusBinarySensor(IotaWattStatusEntity, BinarySensorEntity):
    """Defines an IoTaWatt device status binary sensor."""

    entity_description: IotaWattStatusBinarySensorEntityDescription

    @property
    @override
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self._value
