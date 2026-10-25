"""Config flow for iotawatt integration."""

import logging
from typing import Any, override

import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import httpx_client

from .const import CONNECTION_ERRORS, DOMAIN
from .iotawattpy_nosignal.iotawatt import Iotawatt

_LOGGER = logging.getLogger(__name__)


async def validate_input(
    hass: HomeAssistant, data: dict[str, str]
) -> tuple[dict[str, str], str]:
    """Validate the user input allows us to connect.

    Return the errors and the device MAC address.
    """
    iotawatt = Iotawatt(
        "",
        data[CONF_HOST],
        httpx_client.get_async_client(hass),
        data.get(CONF_USERNAME),
        data.get(CONF_PASSWORD),
    )
    try:
        is_connected = await iotawatt.connect()
    except CONNECTION_ERRORS:
        return {"base": "cannot_connect"}, ""
    except Exception:
        _LOGGER.exception("Unexpected exception")
        return {"base": "unknown"}, ""

    if not is_connected:
        return {"base": "invalid_auth"}, ""

    return {}, iotawatt.getMacAddress()


class IOTaWattConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for iotawatt."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._data: dict[str, Any] = {}

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is None:
            user_input = {}

        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_HOST, default=user_input.get(CONF_HOST, "")
                ): str,
            }
        )
        if not user_input:
            return self.async_show_form(step_id="user", data_schema=schema)

        errors, mac = await validate_input(self.hass, user_input)
        if not errors:
            return await self._async_create_iotawatt_entry(mac, user_input)

        if errors == {"base": "invalid_auth"}:
            self._data.update(user_input)
            return await self.async_step_auth()

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Authenticate user if authentication is enabled on the IoTaWatt device."""
        if user_input is None:
            user_input = {}

        data_schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_USERNAME, default=user_input.get(CONF_USERNAME, "")
                ): str,
                probatio.Required(
                    CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, "")
                ): str,
            }
        )
        if not user_input:
            return self.async_show_form(step_id="auth", data_schema=data_schema)

        data = {**self._data, **user_input}

        errors, mac = await validate_input(self.hass, data)
        if errors:
            return self.async_show_form(
                step_id="auth", data_schema=data_schema, errors=errors
            )

        return await self._async_create_iotawatt_entry(mac, data)

    async def _async_create_iotawatt_entry(
        self, mac: str, data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Create the entry, or update the host of an already configured device."""
        if mac:
            await self.async_set_unique_id(mac)
            self._abort_if_unique_id_configured(updates={CONF_HOST: data[CONF_HOST]})
        return self.async_create_entry(title=data[CONF_HOST], data=data)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
