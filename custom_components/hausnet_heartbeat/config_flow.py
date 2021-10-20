""" Configuration flows. """
from typing import Any, Optional, Tuple, Dict

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_API_KEY, CONF_DEVICE
import homeassistant.helpers.config_validation as cv

from . import DOMAIN, HEARTBEAT_URL, HeartbeatService

HEARTBEAT_CONFIG_ID = "heartbeat_config"

HEARTBEAT_SCHEMA = vol.Schema({
    vol.Required(CONF_API_KEY): cv.string,
    vol.Required(CONF_DEVICE): cv.string,
})


class HeartbeatConfigFlow(ConfigFlow, domain=DOMAIN):
    """ Configure the Heartbeat service. """

    VERSION = 1

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
            errors['base'] = 'invalid_auth'
        elif error_code == HeartbeatService.DEVICE_NOT_FOUND:
            errors['base'] = 'invalid_device'
        else:
            errors['base'] = 'unknown'
        return success, errors

    async def async_step_user(
            self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """ User-driven discovery. """
        errors = {}
        if user_input is not None:
            success, errors = await self._validate_input(user_input)
            if success:
                await self.async_set_unique_id(HEARTBEAT_CONFIG_ID)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title='Heartbeat Configuration',
                    data=user_input
                )
        return self.async_show_form(
            step_id="user",
            data_schema=HEARTBEAT_SCHEMA,
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
