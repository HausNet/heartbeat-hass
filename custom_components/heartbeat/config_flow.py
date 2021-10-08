""" Configuration flows. """
from typing import Coroutine, Any, Optional

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_API_KEY, CONF_DEVICE
import homeassistant.helpers.config_validation as cv

from . import DOMAIN

HEARTBEAT_CONFIG_ID = "heartbeat_config"

HEARTBEAT_SCHEMA = vol.Schema({
    vol.Required(CONF_API_KEY): cv.string,
    vol.Required(CONF_DEVICE): cv.string,
})


class HeartbeatConfigFlow(ConfigFlow, domain=DOMAIN):
    """ Configure the Heartbeat service. """

    VERSION = 1

    async def async_step_user(
            self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """ User-driven discovery. """
        await self.async_set_unique_id(HEARTBEAT_CONFIG_ID)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title='Heartbeat Configuration',
                data=user_input
            )

        return self.async_show_form(
            step_id="user",
            data_schema=HEARTBEAT_SCHEMA
        )

    async def is_valid(self, user_input: dict[str, Any]) -> bool:
        """ Determine if user input is valid."""
