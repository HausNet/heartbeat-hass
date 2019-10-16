"""Integration of the HausMon notification service"""
import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_API_KEY, CONF_DEVICE, CONF_URL

# The HASS domain for the component.
DOMAIN = "hausmon"
# The logger for the component.
LOGGER = logging.getLogger(__package__)
# The URL for the API.
HAUSMON_URL = "http://mon.hausnet.io/api"

##
# Config looks as follows:
#
# hausmon:
#   api_key: [User's API key from service]
#   device:  [Name of the HASS device at the service]
#
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(DOMAIN): vol.Schema(
            {
                vol.Required(CONF_API_KEY): cv.string,
                vol.Required(CONF_DEVICE): cv.string,
                vol.Optional(CONF_URL): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def setup(hass, config):
    """Set up the HausMon component."""
    if DOMAIN not in config:
        return True

    hass.data[DOMAIN] = config[DOMAIN]
    return True
