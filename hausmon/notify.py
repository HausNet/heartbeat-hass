from typing import Optional

from homeassistant.components.notify import (
    BaseNotificationService,
)
from homeassistant.const import CONF_API_KEY

from .const import DOMAIN, LOGGER, HAUSMON_URL


# noinspection PyUnusedLocal
def get_service(hass, config, discovery_info=None) \
        -> Optional['HausMonNotificationService']:
    """Get the HausMon notification service client. Note that this component
    expects a device with name "home_assistant" to be defined at the service.
    """
    data = hass.data[DOMAIN]
    # noinspection PyBroadException
    try:
        hausmon_service = HausMonNotificationService(
            DOMAIN,
            HAUSMON_URL,
            data.get(CONF_API_KEY)
        )
        return hausmon_service
    except Exception:
        LOGGER.exception("Exception while creating HausMon client.")
        return None


class HausMonNotificationService(BaseNotificationService):
    """Notification service built on the HausMon service."""

    def __init__(self, domain: str, api_url: str, api_key: str) -> None:
        """Initialize the service to connect to the given API url, using
        the given API key.
        """
        from hausmon_client.client import HausMonClient
        self._domain: str = domain
        self._api_url: str = api_url
        self._api_key: str = api_key
        self._client: Optional[HausMonClient] = None
        self._initialize_client()

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
        # Send the heartbeat
        if not heartbeat:
            return
        self._send_heartbeat(device)

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

    def _send_heartbeat(self, device: str):
        """Send a heartbeat to reset the heartbeat timer for a device. It is
        assumed that the client has been initialized.

        :param device: Identifier for the device that owns the timer.
        """
        heartbeat = self._client.get_heartbeat(device)
        self._client.send_heartbeat(heartbeat['id'])
        LOGGER.debug(
            f"Sent a heartbeat for: device='{device}'; "
            f"heartbeat_id={heartbeat['id']}"
        )
