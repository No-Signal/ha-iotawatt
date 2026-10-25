"""Diagnostics support for IoTaWatt."""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import IotawattConfigEntry

TO_REDACT = {CONF_HOST, CONF_USERNAME, CONF_PASSWORD, "mac", "ssid", "ip"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: IotawattConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    status = coordinator.status.data if coordinator.status else None
    return {
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": dict(entry.options),
        },
        "device_status": (
            async_redact_data(asdict(status), TO_REDACT) if status else None
        ),
        "sensors": {
            key: {
                "name": sensor.getName(),
                "type": sensor.getType(),
                "channel": sensor.getChannel(),
                "unit": sensor.getUnit(),
                "value": sensor.getValue(),
                "begin": sensor.getBegin(),
                "lifetime": sensor.getLifetime(),
            }
            for key, sensor in coordinator.data["sensors"].items()
        },
    }
