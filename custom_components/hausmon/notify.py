"""Notification via the HausNet/HausMon server"""

import asyncio
import logging
import os
from typing import Dict, Optional

from homeassistant.components.notify import BaseNotificationService
from homeassistant.const import CONF_API_KEY, CONF_DEVICE
from homeassistant.helpers.event import async_call_later

from hausmon_client.client import HausMonClient

from . import DOMAIN, HAUSMON_URL

LOGGER = logging.getLogger(__name__)

# Extended attributes for messaging
# The device name / identifier
ATTR_DEVICE = "device"
ATTR_HEARTBEAT = "heartbeat"

# The default heartbeat period, in seconds. Can be overridden for testing
# purposes. Note that the service my reject too high a rate of resets. 15
# minutes is considered adequate.
HEARTBEAT_PERIOD_SECONDS = int(os.getenv('HAUSMON_PERIOD', str(15*60)))


# noinspection PyUnusedLocal
# pylint: disable=unused-argument
def get_service(hass, config, discovery_info=None) \
        -> Optional['HausMonNotificationService']:
    """Get the HausMon notification service client. Note that this component
    expects a device with name "home_assistant" to be defined at the service.
    """
    # noinspection PyBroadException
    # pylint: disable=broad-except
    try:
        hausmon_service = HausMonNotificationService(hass)
        return hausmon_service
    except Exception:
        LOGGER.exception("Exception while creating HausMon client.")
        return None


class HausMonNotificationService(BaseNotificationService):
    """Notification service built on the HausMon service."""

    def __init__(self, hass) -> None:
        """Initialize the service to connect to the given API url, using
        the given API key. Kicks off the HASS heartbeat timer.
        """
        LOGGER.debug("Creating HausMon notification entity...")
        self._entities = []
        self._hass = hass
        domain_data: Dict = hass.data[DOMAIN]
        self._api_url: str = HAUSMON_URL
        self._device_name: str = domain_data.get(CONF_DEVICE)
        self._api_key: str = domain_data.get(CONF_API_KEY)
        self._client: Optional[HausMonClient] = None
        self._initialize_client()
        asyncio.run_coroutine_threadsafe(self.beat_heart(), hass.loop)
        LOGGER.debug(
            "Created the HausMon notification service: url=%s; device=%s",
            self._api_url, self._device_name
        )

    async def beat_heart(self, *args) -> None:
        """ Called by timer (or at object construction time, once) to beat the
            heart at the service. Sets up the call for the next beat at the end.
        """
        LOGGER.debug("Heartbeat timer triggered.")
        await self._hass.async_add_executor_job(self._send_heartbeat)
        self._set_heartbeat_timer()

    def _set_heartbeat_timer(self) -> None:
        """Set up the next call to the heartbeat function."""
        # noinspection PyTypeChecker
        async_call_later(self._hass, HEARTBEAT_PERIOD_SECONDS, self.beat_heart)
        LOGGER.debug(
            "Heartbeat scheduled in %d seconds",
            HEARTBEAT_PERIOD_SECONDS
        )

    def send_message(
            self,
            message: str = "",
            **kwargs
    ) -> None:
        """ Send a notification via Hausmon, for the device specified. If the
        heartbeat parameter is "True", also sends a request to reset the
        heartbeat for the device.

        Note that this is non-functional right now, and is intended for use
        in future.

        :param message:   Ignored (for now.)
        :param kwargs:    Placeholder for additional args, to match parent.
        """
        # Initialize the client in case it was not.
        if not self._client:
            self._initialize_client()
            if not self._client:
                return
        LOGGER.error("HausMon send_message ignored: %s", message)

    def _initialize_client(self):
        """Try to initialize the client, and set self._client to either the
        client instance, or 'None', depending on the result.
        """
        LOGGER.debug("Initializing HausMon client...")
        # noinspection PyBroadException
        # pylint: disable=broad-except
        try:
            self._client = self._client = \
                HausMonClient(self._api_url, self._api_key)
        except Exception:
            self._client = None
            LOGGER.error("Could not initialize HausMon client.")
            return

    def _send_heartbeat(self):
        """Send a heartbeat to reset the heartbeat timer for a device. It is
        assumed that the client has been initialized.
        """
        heartbeat = self._client.get_heartbeat(self._device_name)
        self._client.send_heartbeat(heartbeat['id'])
        LOGGER.debug(
            "Sent a heartbeat for: device=%s; heartbeat_id=%d",
            self._device_name,
            heartbeat['id']
        )
