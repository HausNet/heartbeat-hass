"""Integration of the HausMon notification service"""
import logging
import os

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_API_KEY, CONF_DEVICE

# The HASS domain for the component.
DOMAIN = "hausmon"
# The logger for the component.
LOGGER = logging.getLogger(DOMAIN)
# The URL for the API.
HAUSMON_URL = os.getenv('HAUSMON_URL', 'https://hausnet.io/hausmon/api')

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
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def setup(hass, config):
    """Set up the HausMon component."""
    LOGGER.debug("Setting up HausMon component...")
    if DOMAIN not in config:
        return True

    hass.data[DOMAIN] = config[DOMAIN]
    return True
