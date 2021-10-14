""" A thin client for the Heartbeat API. """

from typing import Dict, List, Union
import logging

from urllib.parse import urlparse
from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient

log = logging.getLogger(__name__)


class HeartbeatClient:
    """Encapsulates Heartbeat api_client functionality."""

    def __init__(self, service_url: str, token: str) -> None:
        """Create a Swagger API client, load the Swagger definition from the provided service url, and set the
        authentication token for the domain name in the url.

        :param service_url: The base URL for the service, e.g. 'https://mon.hausnet.io/api', without a trailing slash.
        :param token:       The access token provided by the HausNet service.
        :raises:            Any exceptions that were raised during the Swagger client initialization, including
                            connection to the service.
        """
        host = urlparse(service_url).hostname
        http_client = RequestsClient()
        http_client.set_api_key(host=host, api_key=f'Token {token}', param_in='header', param_name='Authorization')
        # noinspection PyBroadException
        try:
            self.client = SwaggerClient.from_url(f'{service_url}/swagger.json', http_client=http_client)
            log.info(f"Connected to Heartbeat client at: url={service_url}")
        except Exception as e:
            log.exception(f"Failed to connect to Heartbeat client: url={service_url}")
            self.client = None
            raise e

    @property
    def connected(self) -> bool:
        """ Tell if client has been initialized. """
        return self.client is not None

    def list_devices(self) -> List[Dict]:
        """Get a list of devices belonging to the user associated with the auth token."""
        # noinspection PyUnresolvedReferences
        devices = self.client.devices.devices_list().response().result
        return devices

    def get_device(self, name: str) -> Union[Dict, None]:
        """Get a device by name, by iterating through all the devices.

        TODO: Add an API endpoint that directly fetches the device by name, instead of having to iterate.
        """
        devices = self.list_devices()
        for device in devices:
            if 'name' in device and device['name'] == name:
                return device
        return None

    def get_heartbeat(self, device_name: str) -> Union[Dict, None]:
        """Get a device's hausnet_heartbeat.

        :return: The hausnet_heartbeat (dynamic) object if a hausnet_heartbeat exists for the device, otherwise "None"

        TODO: Add an API call to do this directly from the device name.
        """
        device = self.get_device(device_name)
        # noinspection PyUnresolvedReferences
        if not device or not device['heartbeat_id']:
            return None
        # noinspection PyUnresolvedReferences
        heartbeat = self.client.heartbeats.heartbeats_read(id=device['heartbeat_id']).response().result
        return heartbeat

    def send_heartbeat(self, heartbeat_id: int):
        """Send a hausnet_heartbeat for a specific hausnet_heartbeat definition (or device). """
        # noinspection PyUnresolvedReferences
        self.client.heartbeats.heartbeats_beat(id=heartbeat_id).response()
