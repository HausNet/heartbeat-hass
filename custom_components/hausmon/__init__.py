"""Integration of the HausMon notification service"""

import asyncio
import datetime
import logging
import os
from typing import Optional

import voluptuous as vol
from hausmon_client.client import HausMonClient

import homeassistant.helpers.config_validation as cv
from core import HomeAssistant
from helpers.event import async_call_later
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

# The default heartbeat period, in seconds. Can be overridden for testing
# purposes. Note that the service may reject too high a rate of resets. 15
# minutes is considered adequate.
HEARTBEAT_PERIOD_SECONDS = int(os.getenv('HAUSMON_PERIOD', str(15*60)))


async def async_setup(hass, config) -> bool:
    """Set up the HausMon component."""
    LOGGER.debug("Setting up HausMon component...")
    if DOMAIN not in config:
        return True
    hass.data[DOMAIN] = config[DOMAIN]
    hass.data[DOMAIN].heartbeat_service = HeartbeatService(hass)
    LOGGER.debug(
        "Created the HausMon notification service: url=%s; device=%s",
        HAUSMON_URL, hass.data[DOMAIN].get(CONF_DEVICE)
    )
    return True


class HeartbeatService:
    """Implements a heart-beat via the HausMon monitor service. """

    def __init__(self, hass: HomeAssistant):
        """Set up the service"""
        self._hass: HomeAssistant = hass
        hass_data = hass.data[DOMAIN]
        self._api_url: str = HAUSMON_URL
        self._api_key: str = hass_data.get(CONF_API_KEY)
        self._client: Optional[HausMonClient] = None
        self._device_name: str = hass_data.get(CONF_DEVICE)
        asyncio.run_coroutine_threadsafe(self.beat_heart(), hass.loop)

    # noinspection PyUnusedLocal
    # (for arg - unused)
    async def beat_heart(self, arg: Optional[datetime.datetime] = None) -> None:
        """ Called by timer (or at object construction time, once) to beat the
        heart at the service. Sets up the call for the next beat at the end.
        """
        LOGGER.debug("Heartbeat timer triggered.")
        await self._hass.async_add_executor_job(
            self._send_heartbeat_with_retry
        )
        self._set_heartbeat_timer()

    def _set_heartbeat_timer(self) -> None:
        """Set up the next call to the heartbeat function."""
        # noinspection PyTypeChecker
        async_call_later(self._hass, HEARTBEAT_PERIOD_SECONDS, self.beat_heart)
        LOGGER.debug(
            "Heartbeat scheduled in %d seconds",
            HEARTBEAT_PERIOD_SECONDS
        )

    def _init_api_client(self) -> Optional[HausMonClient]:
        """Try to initialize the client, and either either the client instance,
         or 'None', depending on the result.
        """
        # noinspection PyBroadException
        # pylint: disable=broad-except
        try:
            client = HausMonClient(self._api_url, self._api_key)
            LOGGER.debug("HausMon client successfully initialized...")
            return client
        except Exception:
            LOGGER.exception(
                "Could not initialize HausMon client"
            )
            return None

    # noinspection PyBroadException
    def _send_heartbeat_with_retry(self):
        """Try sending the heartbeat, and if that fails, re-initialize the
        client and retry (once).
        """
        try:
            if not self._client:
                self._client = self._init_api_client()
            self._send_heartbeat()
            return
        except Exception:
            LOGGER.exception("Heartbeat send failed. Retrying...")
        try:
            self._client = None
            self._client = self._init_api_client()
            self._send_heartbeat()
        except Exception:
            LOGGER.exception("Heartbeat send failed. Skipping beat.")

    def _send_heartbeat(self):
        """Send a heartbeat to reset the heartbeat timer for a device.
        """
        heartbeat = self._client.get_heartbeat(self._device_name)
        self._client.send_heartbeat(heartbeat['id'])
        LOGGER.debug(
            "Sent a heartbeat for: device=%s; heartbeat_id=%d",
            self._device_name,
            heartbeat['id']
        )
