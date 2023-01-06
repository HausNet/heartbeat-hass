""" Configuration flows. """

from typing import Any, Optional, Tuple, Dict

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_API_KEY, CONF_DEVICE
import homeassistant.helpers.config_validation as cv

from . import DOMAIN, HEARTBEAT_URL, HeartbeatService

HEARTBEAT_CONFIG_ID = "heartbeat_config"


class HeartbeatConfigFlow(ConfigFlow, domain=DOMAIN):
    """ Configure the Heartbeat service. """

    VERSION = 1

    async def async_step_user(
            self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """ User-driven discovery. """

        errors = {}
        api_key_field = None
        device_field = None
        if user_input is not None:
            success, errors = await self._validate_input(user_input)
            if success:
                await self.async_set_unique_id(user_input[CONF_API_KEY])
                return self.async_create_entry(
                    title='Heartbeat Configuration',
                    data=user_input
                )
            api_key_field = user_input[CONF_API_KEY]
            device_field = user_input[CONF_DEVICE]
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY, default=api_key_field): cv.string,
                vol.Required(CONF_DEVICE, default=device_field): cv.string,
            }),
            errors=errors
        )

    async def async_step_reauth(self, user_input=None):
        """ Perform reauth upon an API authentication error. """
        return await self.async_step_reauth_confirm(user_input)

    async def async_step_reauth_confirm(self, user_input=None):
        """ Dialog that informs the user that reauth is required. """
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema({}),
            )
        return await self.async_step_user(user_input)

    async def _validate_input(self, user_input: Dict[str, Any]) -> \
            Tuple[bool, Dict[str, str]]:
        """ Validate form input. """
        errors = {}

        success, error_code = await HeartbeatService.verify_connection(
            self.hass,
            HEARTBEAT_URL,
            user_input[CONF_API_KEY],
            user_input[CONF_DEVICE]
        )
        if error_code == HeartbeatService.CONNECT_FAILED:
            errors['base'] = 'cannot_connect'
        elif error_code == HeartbeatService.AUTH_FAILED:
            errors[CONF_API_KEY] = 'invalid_auth'
        elif error_code == HeartbeatService.DEVICE_NOT_FOUND:
            errors[CONF_DEVICE] = 'invalid_device'
        elif not success:
            errors['base'] = 'cannot_connect'
        return success, errors
