"""Base entity for the IoTaWatt device status entities."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import IotawattStatusUpdater, iotawatt_device_info
from .iotawattpy_nosignal.status import DeviceStatus, UploaderStatus


@dataclass(frozen=True, kw_only=True)
class IotaWattStatusEntityDescription(EntityDescription):
    """Describes an entity derived from the device status."""

    # Returns None when the firmware doesn't report the value.
    value_fn: Callable[[DeviceStatus], Any]
    # Whether the device reports the entity; defaults to having a value.
    exists_fn: Callable[[DeviceStatus], bool] | None = None
    uploader_id: str | None = None

    def exists(self, status: DeviceStatus) -> bool:
        """Return whether the device status reports this entity."""
        if self.exists_fn is not None:
            return self.exists_fn(status)
        return self.value_fn(status) is not None


def get_uploader(status: DeviceStatus, uploader_id: str) -> UploaderStatus | None:
    """Return the status of an uploader, if the device reports it."""
    return next(
        (uploader for uploader in status.uploaders or () if uploader.id == uploader_id),
        None,
    )


class IotaWattStatusEntity(CoordinatorEntity[IotawattStatusUpdater]):
    """Defines an IoTaWatt device status entity."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    entity_description: IotaWattStatusEntityDescription

    def __init__(
        self,
        coordinator: IotawattStatusUpdater,
        description: IotaWattStatusEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator=coordinator)
        self.entity_description = description
        mac = coordinator.api.getMacAddress()
        self._attr_unique_id = f"{mac}-status-{description.key}"
        self._attr_device_info = iotawatt_device_info(coordinator.config_entry, mac)
        if description.uploader_id is not None:
            self._attr_translation_placeholders = {"uploader": description.uploader_id}

    @property
    def _value(self) -> Any:
        """Return the value from the latest device status."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    @override
    def available(self) -> bool:
        """Return if the value is available, e.g. not removed by the firmware."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.entity_description.exists(self.coordinator.data)
        )


@callback
def async_add_status_entities[DescriptionT: IotaWattStatusEntityDescription](
    coordinator: IotawattStatusUpdater,
    async_add_entities: AddConfigEntryEntitiesCallback,
    descriptions_fn: Callable[[DeviceStatus], Iterable[DescriptionT]],
    entity_factory: Callable[
        [IotawattStatusUpdater, DescriptionT], IotaWattStatusEntity
    ],
) -> None:
    """Add status entities for the values the device reports.

    Values missing on older firmware get no entity. Entities are also added
    when values appear later, e.g. after a failed first poll or when an
    uploader is configured.
    """
    added: set[str] = set()

    @callback
    def _async_add_new_entities() -> None:
        if (status := coordinator.data) is None:
            return
        descriptions = [
            description
            for description in descriptions_fn(status)
            if description.key not in added and description.exists(status)
        ]
        added.update(description.key for description in descriptions)
        async_add_entities(
            entity_factory(coordinator, description) for description in descriptions
        )

    _async_add_new_entities()
    coordinator.config_entry.async_on_unload(
        coordinator.async_add_listener(_async_add_new_entities)
    )
