"""Config flow for iotawatt integration."""

import logging
from typing import Any, override

import probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import httpx_client
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_LIFETIME_SENSORS,
    CONF_LIVE_INTERVAL,
    CONF_LIVE_SENSORS,
    CONF_SCAN_INTERVAL,
    CONNECTION_ERRORS,
    DEFAULT_LIVE_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_LIVE_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_LIVE_INTERVAL,
    MIN_SCAN_INTERVAL,
    SCAN_INTERVAL_STEP,
)
from .coordinator import IotawattConfigEntry, IotawattUpdater
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

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> IotawattOptionsFlow:
        """Get the options flow for this handler."""
        return IotawattOptionsFlow()

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


def _live_sensor_options(coordinator: IotawattUpdater) -> list[SelectOptionDict]:
    """Return the sensors that can be read live: power inputs and all outputs."""
    return [
        SelectOptionDict(value=key, label=sensor.getName())
        for key, sensor in coordinator.data["sensors"].items()
        # Energy sensors have a suffix (.wh); the live readings are not energy.
        if sensor.getSuffix() is None
        and not sensor.getLifetime()
        and (sensor.getType() == "Output" or sensor.getUnit() == "Watts")
    ]


class IotawattOptionsFlow(OptionsFlowWithReload):
    """Handle IoTaWatt options."""

    config_entry: IotawattConfigEntry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        live_options: list[SelectOptionDict] | None = None
        if (
            self.config_entry.state is ConfigEntryState.LOADED
            and self.config_entry.runtime_data.data
        ):
            live_options = _live_sensor_options(self.config_entry.runtime_data)

        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            # NumberSelector only enforces min and max; step is a UI hint.
            if user_input[CONF_SCAN_INTERVAL] % SCAN_INTERVAL_STEP:
                errors[CONF_SCAN_INTERVAL] = "invalid_interval"
            live_interval = user_input[CONF_LIVE_INTERVAL]
            if live_interval != int(live_interval):
                errors[CONF_LIVE_INTERVAL] = "invalid_live_interval"
            user_input[CONF_LIVE_INTERVAL] = int(live_interval)
            if live_options is None:
                # The device is offline: keep the stored live selection.
                user_input[CONF_LIVE_SENSORS] = self.config_entry.options.get(
                    CONF_LIVE_SENSORS, []
                )
            if not errors:
                return self.async_create_entry(data=user_input)

        options = user_input or self.config_entry.options
        fields: dict[Any, Any] = {
            probatio.Required(
                CONF_SCAN_INTERVAL,
                default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=MAX_SCAN_INTERVAL,
                    step=SCAN_INTERVAL_STEP,
                    unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            probatio.Required(
                CONF_LIFETIME_SENSORS,
                default=options.get(CONF_LIFETIME_SENSORS, False),
            ): BooleanSelector(),
        }
        if live_options is not None:
            available = {option["value"] for option in live_options}
            fields[
                probatio.Optional(
                    CONF_LIVE_SENSORS,
                    default=[
                        key
                        for key in options.get(CONF_LIVE_SENSORS, [])
                        if key in available
                    ],
                )
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=live_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        fields[
            probatio.Required(
                CONF_LIVE_INTERVAL,
                default=options.get(CONF_LIVE_INTERVAL, DEFAULT_LIVE_INTERVAL),
            )
        ] = NumberSelector(
            NumberSelectorConfig(
                min=MIN_LIVE_INTERVAL,
                max=MAX_LIVE_INTERVAL,
                step=1,
                unit_of_measurement="s",
                mode=NumberSelectorMode.BOX,
            )
        )
        return self.async_show_form(
            step_id="init", data_schema=probatio.Schema(fields), errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
