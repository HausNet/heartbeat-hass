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

from .client import HeartbeatClient, HeartbeatClientConnectError, \
    HeartbeatClientAuthError

# The HASS domain for the component.
DOMAIN = "hausnet_heartbeat"
# The logger for the component.
LOGGER = logging.getLogger(DOMAIN)
# The URL for the API.
HEARTBEAT_URL = os.getenv(
    'HAUSNET_HEARTBEAT_URL',
    'https://app.hausnet.io/heartbeat/api'
)
HEARTBEAT_SERVICE = 'hausnet_heartbeat'
# Number of times to retry sending the heartbeat
HEARTBEAT_RETRY_TIMES = 3

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
    token = config.data[CONF_API_KEY]
    device = config.data[CONF_DEVICE]
    failures = {
        HeartbeatService.CONNECT_FAILED:
            f"Network connection to {HEARTBEAT_URL} failed.",
        HeartbeatService.DEVICE_NOT_FOUND:
            f"Device {device} not found at service",
        HeartbeatService.AUTH_FAILED:
            f"Authentication token invalid",
        HeartbeatService.UNKNOWN_FAILURE:
            "Unknown connection or authentication failure ",
    }
    try:
        success, error = await HeartbeatService.verify_connection(
            hass, HEARTBEAT_URL, token, device
        )
        if not success :
            raise ConfigEntryAuthFailed(failures[error])
    except Exception as e:
        raise ConfigEntryAuthFailed(e) from e
    service = HeartbeatService(
        hass, config.data[CONF_API_KEY], config.data[CONF_DEVICE]
    )
    await service.init_api_client()
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
    UNKNOWN_FAILURE = 3

    def __init__(self, hass: HomeAssistant, api_key: str, device: str):
        """Set up the service"""
        self._hass: HomeAssistant = hass
        self._api_url: str = HEARTBEAT_URL
        self._api_token: str = api_key
        self._device_name: str = device
        self._api_client: Optional[HeartbeatClient] = None
        asyncio.run_coroutine_threadsafe(self.beat_heart(), hass.loop)

    # noinspection PyUnusedLocal
    # (for arg - unused)
    async def beat_heart(self, arg: Optional[datetime.datetime] = None) -> None:
        """ Called by timer (or at object construction time, once) to beat the
        heart at the service. Sets up the call for the next beat at the end.
        """
        LOGGER.debug("Heartbeat timer triggered.")
        await self._send_heartbeat_with_retry()
        self._set_heartbeat_timer()

    def _set_heartbeat_timer(self) -> None:
        """Set up the next call to the hausnet_heartbeat function."""
        # noinspection PyTypeChecker
        async_call_later(self._hass, HEARTBEAT_PERIOD_SECONDS, self.beat_heart)
        LOGGER.debug(
            "Heartbeat scheduled in %d seconds",
            HEARTBEAT_PERIOD_SECONDS
        )

    async def init_api_client(self):
        """ Initialize client using the provided URL and token. """
        self._api_client = await self._hass.async_add_executor_job(
            lambda url=self._api_url, token=self._api_token:
                HeartbeatClient(url, token)
        )

    @staticmethod
    async def verify_connection(
            hass: HomeAssistant, url: str, token: str, device_name: str
    ) -> Tuple[bool, Optional[int]]:
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
            api_client = await hass.async_add_executor_job(
                lambda c_url=url, c_token=token:
                    HeartbeatClient(c_url, c_token)
            )
            device = await hass.async_add_executor_job(
                api_client.get_device, device_name
            )
            if not device:
                return False, HeartbeatService.DEVICE_NOT_FOUND
        except HeartbeatClientAuthError:
            return False, HeartbeatService.AUTH_FAILED
        except HeartbeatClientConnectError:
            return False, HeartbeatService.CONNECT_FAILED
        except Exception:
            return False, HeartbeatService.CONNECT_FAILED
        return True, None

    # noinspection PyBroadException
    async def _send_heartbeat_with_retry(self):
        """ Try sending the hausnet_heartbeat, and if that fails, re-initialize
            the client and retry (HEARBEAT_RETRY_TIMES times).
        """
        for retry_count in range(0, HEARTBEAT_RETRY_TIMES):
            try:
                if not self._api_client:
                    await self.init_api_client()
                    if not self._api_client:
                        LOGGER.warning(
                            "Heartbeat client initialization failed. "
                            "Retrying..."
                        )
                    continue
                if await self._send_heartbeat():
                    return
            except Exception:
                LOGGER.exception(
                    f"Heartbeat send failed, try {retry_count + 1} of "
                    f"{HEARTBEAT_RETRY_TIMES}."
                )
                continue
        LOGGER.error("Heartbeat send failed. Skipping beat.")

    async def _send_heartbeat(self) -> bool:
        """ Send a hausnet_heartbeat to reset the hausnet_heartbeat timer for
            a device. Returns False if a heartbeat object could not be found
            at the service, True if the heartbeat was found and sent.
        """
        heartbeat = await self._hass.async_add_executor_job(
            self._api_client.get_heartbeat, self._device_name
        )
        if not heartbeat:
            LOGGER.error(f"No heartbeat found for device: {self._device_name}")
            return False
        await self._hass.async_add_executor_job(
            self._api_client.send_heartbeat, heartbeat['id']
        )
        LOGGER.info(
            "Sent a hausnet_heartbeat for: device=%s; heartbeat_id=%d",
            self._device_name,
            heartbeat['id']
        )
        return True


