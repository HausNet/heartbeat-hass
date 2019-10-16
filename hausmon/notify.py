import asyncio
from typing import Optional, Dict

from homeassistant.components.notify import (BaseNotificationService)
from homeassistant.const import (CONF_API_KEY, CONF_DEVICE, CONF_URL)
from homeassistant.helpers.event import async_call_later

from . import DOMAIN, LOGGER, HAUSMON_URL

# Extended attributes for messaging
# The device name / identifier
ATTR_DEVICE = "device"
ATTR_HEARTBEAT = "heartbeat"

# The default heartbeat period, in seconds.
HEARTBEAT_PERIOD_SECONDS = 5*60


# noinspection PyUnusedLocal
def get_service(hass, config, discovery_info=None) \
        -> Optional['HausMonNotificationService']:
    """Get the HausMon notification service client. Note that this component
    expects a device with name "home_assistant" to be defined at the service.
    """
    # noinspection PyBroadException
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
        from hausmon_client.client import HausMonClient
        self._hass = hass
        domain_data: Dict = hass.data[DOMAIN]
        self._api_url: str = domain_data.get(CONF_URL, HAUSMON_URL)
        self._device_name: str = domain_data.get(CONF_DEVICE)
        self._api_key: str = domain_data.get(CONF_API_KEY)
        self._client: Optional[HausMonClient] = None
        self._initialize_client()
        asyncio.run_coroutine_threadsafe(self.beat_heart(), hass.loop)

    async def beat_heart(self):
        """Called by timer (or at object construction time, once) to beat heart
        at the service. Sets up the call for the next beat at the end.
        """
        LOGGER.debug("Heartbeat timer triggered.")
        asyncio.run_coroutine_threadsafe(
            self._send_heartbeat(),
            self._hass.loop
        )
        await self._set_heartbeat_timer()

    async def _set_heartbeat_timer(self):
        """Set up the next call to the heartbeat function."""
        async_call_later(self._hass, HEARTBEAT_PERIOD_SECONDS, self.beat_heart)

    def send_message(
            self,
            message: str = "",
            device: str = "",
            heartbeat: bool = False,
            **kwargs
    ) -> None:
        """Send a notification via Hausmon, for the device specified. If the
        heartbeat parameter is "True", also sends a request to reset the
        heartbeat for the device.


        :param message:   Ignored (for now.)
        :param device:    The source device for the message.
        :param heartbeat: Whether the device heartbeat should be reset
        :param kwargs:    Placeholder for additional args, to match parent.
        """
        # Initialize the client in case it was not.
        if not self._client:
            self._initialize_client()
            if not self._client:
                return
        # TODO: Send the message
        LOGGER.debug(f"Message sent: {message}")

    def _initialize_client(self):
        """Try to initialize the client, and set self._client to either the
        client instance, or 'None', depending on the result.
        """
        from hausmon_client.client import HausMonClient
        # noinspection PyBroadException
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
        try:
            heartbeat = self._client.get_heartbeat(self._device_name)
        except Exception as e:
            pass
        self._client.send_heartbeat(heartbeat['id'])
        LOGGER.debug(
            f"Sent a heartbeat for: device='{self._device_name}'; "
            f"heartbeat_id={heartbeat['id']}"
        )
