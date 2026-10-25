"""Support for IoTaWatt Energy monitor."""

from collections.abc import Callable
from dataclasses import dataclass, replace
import logging
from typing import override

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactivePower,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util, slugify

from .const import CONF_LIVE_SENSORS, VOLT_AMPERE_REACTIVE_HOURS
from .coordinator import (
    IotawattConfigEntry,
    IotawattLiveUpdater,
    IotawattUpdater,
    iotawatt_device_info,
)
from .iotawattpy_nosignal.sensor import Sensor

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class IotaWattSensorEntityDescription(SensorEntityDescription):
    """Class describing IotaWatt sensor entities."""

    value: Callable | None = None


ENTITY_DESCRIPTION_KEY_MAP: dict[str, IotaWattSensorEntityDescription] = {
    "Amps": IotaWattSensorEntityDescription(
        key="Amps",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.CURRENT,
        entity_registry_enabled_default=False,
    ),
    "Hz": IotaWattSensorEntityDescription(
        key="Hz",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.FREQUENCY,
        icon="mdi:flash",
        entity_registry_enabled_default=False,
    ),
    "PF": IotaWattSensorEntityDescription(
        key="PF",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER_FACTOR,
        value=lambda value: value * 100,
        entity_registry_enabled_default=False,
    ),
    "Watts": IotaWattSensorEntityDescription(
        key="Watts",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
    ),
    "WattHours": IotaWattSensorEntityDescription(
        key="WattHours",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
    ),
    "VA": IotaWattSensorEntityDescription(
        key="VA",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.APPARENT_POWER,
        entity_registry_enabled_default=False,
    ),
    "VAR": IotaWattSensorEntityDescription(
        key="VAR",
        native_unit_of_measurement=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        entity_registry_enabled_default=False,
    ),
    "VARh": IotaWattSensorEntityDescription(
        key="VARh",
        native_unit_of_measurement=VOLT_AMPERE_REACTIVE_HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash",
        entity_registry_enabled_default=False,
    ),
    "Volts": IotaWattSensorEntityDescription(
        key="Volts",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_registry_enabled_default=False,
    ),
}


# Energy integrated since the start of the device datalog: a meter reading
# that never resets, unlike the daily totals.
LIFETIME_ENERGY_DESCRIPTION = IotaWattSensorEntityDescription(
    key="WattHours_lifetime",
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
    state_class=SensorStateClass.TOTAL_INCREASING,
    device_class=SensorDeviceClass.ENERGY,
)


# Live power of an input channel, from the device's ~1 s status readings.
LIVE_POWER_DESCRIPTION = IotaWattSensorEntityDescription(
    key="Watts_live",
    native_unit_of_measurement=UnitOfPower.WATT,
    state_class=SensorStateClass.MEASUREMENT,
    device_class=SensorDeviceClass.POWER,
    suggested_display_precision=0,
)
LIVE_UNIQUE_ID_SUFFIX = "-live"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IotawattConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    coordinator = config_entry.runtime_data
    created = set()

    @callback
    def _create_entity(key: str) -> IotaWattSensor:
        """Create a sensor entity."""
        created.add(key)
        data = coordinator.data["sensors"][key]
        if data.getLifetime():
            description = LIFETIME_ENERGY_DESCRIPTION
        else:
            description = ENTITY_DESCRIPTION_KEY_MAP.get(
                data.getUnit(), IotaWattSensorEntityDescription(key="base_sensor")
            )
        if data.getType() == "Output":
            # Outputs are defined by the user on the device. Core always showed
            # them (they had no registry entry), so keep them enabled.
            description = replace(description, entity_registry_enabled_default=True)

        return IotaWattSensor(
            coordinator=coordinator,
            key=key,
            entity_description=description,
        )

    async_add_entities(_create_entity(key) for key in coordinator.data["sensors"])

    @callback
    def new_data_received():
        """Check for new sensors."""
        entities = [
            _create_entity(key)
            for key in coordinator.data["sensors"]
            if key not in created
        ]
        async_add_entities(entities)

    coordinator.async_add_listener(new_data_received)

    live_entities: list[IotaWattLiveSensor] = []
    if coordinator.live is not None:
        live_entities = [
            IotaWattLiveSensor(coordinator.live, key, coordinator.data["sensors"][key])
            for key in config_entry.options.get(CONF_LIVE_SENSORS, [])
            # Skip keys no longer on the device, e.g. a renamed output.
            if key in coordinator.data["sensors"]
        ]
        async_add_entities(live_entities)
    _async_remove_stale_live_entities(
        hass, config_entry, {entity.unique_id for entity in live_entities}
    )


@callback
def _async_remove_stale_live_entities(
    hass: HomeAssistant, config_entry: IotawattConfigEntry, keep: set[str | None]
) -> None:
    """Remove live sensors that are no longer selected from the registry."""
    entity_registry = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, config_entry.entry_id
    ):
        if (
            entity_entry.domain == SENSOR_DOMAIN
            and entity_entry.unique_id.endswith(LIVE_UNIQUE_ID_SUFFIX)
            and entity_entry.unique_id not in keep
        ):
            entity_registry.async_remove(entity_entry.entity_id)


class IotaWattSensor(CoordinatorEntity[IotawattUpdater], SensorEntity):
    """Defines a IoTaWatt Energy Sensor."""

    entity_description: IotaWattSensorEntityDescription

    def __init__(
        self,
        coordinator: IotawattUpdater,
        key: str,
        entity_description: IotaWattSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)

        self._key = key
        data = self._sensor_data
        if data.getType() == "Input":
            unique_id = (
                f"{data.hub_mac_address}-input-{data.getChannel()}-{data.getUnit()}"
            )
        else:
            # Matches the llamafilm/iotawatt-hacs fork, so its users keep their
            # entity registry entries.
            unique_id = (
                f"{data.hub_mac_address}-output-{data.getName()}-{data.getUnit()}"
            )
            # Core registered outputs without a unique ID, so their entity IDs
            # came from the name alone. Suggest the same entity ID so they don't
            # gain the device name prefix when first registered.
            self.entity_id = f"{SENSOR_DOMAIN}.{slugify(data.getName())}"
        if data.getLifetime():
            unique_id += "-lifetime"
        self._attr_unique_id = unique_id
        self._attr_device_info = iotawatt_device_info(
            coordinator.config_entry, data.hub_mac_address
        )
        self.entity_description = entity_description

    @property
    def _sensor_data(self) -> Sensor:
        """Return sensor data."""
        return self.coordinator.data["sensors"][self._key]

    @property
    @override
    def name(self) -> str | None:
        """Return name of the entity."""
        return self._sensor_data.getName()

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._key not in self.coordinator.data["sensors"]:
            if self._attr_unique_id:
                er.async_get(self.hass).async_remove(self.entity_id)
            else:
                self.hass.async_create_task(self.async_remove())
            return

        if (
            not self._sensor_data.getLifetime()
            and (begin := self._sensor_data.getBegin())
            and (last_reset := dt_util.parse_datetime(begin))
        ):
            self._attr_last_reset = last_reset

        super()._handle_coordinator_update()

    @property
    @override
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the extra state attributes of the entity."""
        data = self._sensor_data
        attrs = {"type": data.getType()}
        if attrs["type"] == "Input":
            attrs["channel"] = data.getChannel()

        return attrs

    @property
    @override
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if func := self.entity_description.value:
            return func(self._sensor_data.getValue())

        return self._sensor_data.getValue()


class IotaWattLiveSensor(CoordinatorEntity[IotawattLiveUpdater], SensorEntity):
    """Defines a live IoTaWatt sensor, updated about every second."""

    entity_description: IotaWattSensorEntityDescription

    def __init__(
        self, coordinator: IotawattLiveUpdater, key: str, sensor: Sensor
    ) -> None:
        """Initialize the sensor from the matching standard sensor."""
        super().__init__(coordinator=coordinator)

        self._key = key
        self._is_input = sensor.getType() == "Input"
        mac = sensor.hub_mac_address
        if self._is_input:
            self._attr_unique_id = (
                f"{mac}-input-{sensor.getChannel()}-Watts{LIVE_UNIQUE_ID_SUFFIX}"
            )
            self.entity_description = LIVE_POWER_DESCRIPTION
        else:
            self._attr_unique_id = (
                f"{mac}-output-{sensor.getName()}-{sensor.getUnit()}"
                f"{LIVE_UNIQUE_ID_SUFFIX}"
            )
            # The user selected this output, so enable it.
            self.entity_description = replace(
                ENTITY_DESCRIPTION_KEY_MAP.get(
                    sensor.getUnit(),
                    IotaWattSensorEntityDescription(key="base_sensor"),
                ),
                entity_registry_enabled_default=True,
            )
        self._attr_name = f"{sensor.getName()} Live"
        self._attr_device_info = iotawatt_device_info(coordinator.config_entry, mac)

    @property
    @override
    def available(self) -> bool:
        """Return if the live reading is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._key in self.coordinator.data
        )

    @property
    @override
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        reading = self.coordinator.data[self._key]
        if self._is_input:
            return reading.watts
        if reading.value is not None and (func := self.entity_description.value):
            return func(reading.value)
        return reading.value
