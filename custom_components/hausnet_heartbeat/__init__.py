"""Integration of the HausNet Heartbeat notification service"""

import asyncio
import datetime
import logging
import os
from typing import Optional, Tuple

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry

import homeassistant.helpers.config_validation as cv
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_call_later
from homeassistant.const import CONF_API_KEY, CONF_DEVICE

from .client import HeartbeatClient

# The HASS domain for the component.
DOMAIN = "hausnet_heartbeat"
# The logger for the component.
LOGGER = logging.getLogger(DOMAIN)
# The URL for the API.
HEARTBEAT_URL = os.getenv(
    'HAUSNET_HEARTBEAT_URL',
    'https://app.hausnet.iop/heartbeat/api'
)
HEARTBEAT_SERVICE = 'hausnet_heartbeat'

##
# Config looks as follows:
#
# hausnet_heartbeat:
#   api_key: [User's API key from service]
#   device:  [Name of the HASS device at the service]
#
CONFIG_SCHEMA = vol.Schema({
    vol.Optional(DOMAIN): vol.Schema({
        vol.Required(CONF_API_KEY): cv.string,
        vol.Required(CONF_DEVICE): cv.string,
    })},
    extra=vol.ALLOW_EXTRA,
)

# The default hausnet_heartbeat period,
# in seconds. Can be overridden for testing
# purposes. Note that the service may reject too high a rate of resets. 15
# minutes is considered adequate.
HEARTBEAT_PERIOD_SECONDS = int(os.getenv('HEARTBEAT_PERIOD', str(15*60)))


class DeviceNotFoundError(Exception):
    """ An exception indicating that a device was not found at the service. """
    pass


async def async_setup_entry(hass: HomeAssistant, config: ConfigEntry) -> bool:
    """Set up the Heartbeat component."""
    LOGGER.debug("Setting up Heartbeat component...")
    hass.data.setdefault(DOMAIN, {})
    service = HeartbeatService(
        hass, config.data[CONF_API_KEY], config.data[CONF_DEVICE]
    )
    try:
        service._get_api_client()
    except Exception as e:
        raise ConfigEntryAuthFailed(e) from e
    hass.data[DOMAIN][HEARTBEAT_SERVICE] = service
    LOGGER.debug(
        "Created the Heartbeat notification service: url=%s; device=%s",
        HEARTBEAT_URL, hass.data[DOMAIN].get(CONF_DEVICE)
    )
    return True


class HeartbeatService:
    """Implements a heart-beat via the Heartbeat monitor service. """

    # Service connection error codes
    CONNECT_FAILED = 0
    AUTH_FAILED = 1
    DEVICE_NOT_FOUND = 2
    UNKNOWN_FAILURE =3

    def __init__(self, hass: HomeAssistant, api_key: str, device: str):
        """Set up the service"""
        self._hass: HomeAssistant = hass
        hass_data = hass.data[DOMAIN]
        self._api_url: str = HEARTBEAT_URL
        self._api_key: str = api_key
        self._device_name: str = device
        self._client: Optional[HeartbeatClient] = None
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
        """Set up the next call to the hausnet_heartbeat function."""
        # noinspection PyTypeChecker
        async_call_later(self._hass, HEARTBEAT_PERIOD_SECONDS, self.beat_heart)
        LOGGER.debug(
            "Heartbeat scheduled in %d seconds",
            HEARTBEAT_PERIOD_SECONDS
        )

    @staticmethod
    def _get_api_client(url: str, token: str) -> HeartbeatClient:
        """ Try to initialize the client and reflect an exception if it could
            not, using the given service url and access token. Return either
            the client instance, or 'None', depending on the result.
        """
        return HeartbeatClient(url, token)

    @staticmethod
    def verify_connection(url: str, token: str) -> Tuple[bool, Optional[int]]:
        """ Connects to the service, and verifies that the given token
            allows access, and that the given device exists at the service.

            Returns a tuple of (bool, str), containing (True, None) if
            connection checks out, or (True, reason) if not, with reason
            one of:
                - CONNECT_FAILED:   Could not connect to service
                - AUTH_FAILED:      Authentication failed (wrong token)
                - DEVICE_NOT_FOUND: No device with the given name
                - UNKNOWN_FAILURE:  Failure to connect for an unknown reason
        """
        try:
            api_client = HeartbeatService._get_api_client(url, token)
        except Exception as e:
            return False, HeartbeatService.CONNECT_FAILED
        return True, None

    # noinspection PyBroadException
    def _send_heartbeat_with_retry(self):
        """ Try sending the hausnet_heartbeat, and if that fails, re-initialize
            the client and retry (once).
        """
        try:
            if not self._client:
                self._client = self._get_api_client()
            self._send_heartbeat()
            return
        except Exception:
            LOGGER.exception("Heartbeat send failed. Retrying...")
        try:
            self._client = None
            self._client = self._get_api_client()
            self._send_heartbeat()
        except Exception:
            LOGGER.exception("Heartbeat send failed. Skipping beat.")

    def _send_heartbeat(self):
        """Send a hausnet_heartbeat to reset the hausnet_heartbeat timer for a device.
        """
        heartbeat = self._client.get_heartbeat(self._device_name)
        self._client.send_heartbeat(heartbeat['id'])
        LOGGER.debug(
            "Sent a hausnet_heartbeat for: device=%s; heartbeat_id=%d",
            self._device_name,
            heartbeat['id']
        )


