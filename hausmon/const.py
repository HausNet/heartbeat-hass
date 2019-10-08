import logging

# The HASS domain for the component.
DOMAIN = "hausmon"

# The logger for the component.
LOGGER = logging.getLogger(__package__)

# The URL for the API.
HAUSMON_URL = "http://mon.hausnet.io/api"

# Extended attributes for messaging
# The device name / identifier
ATTR_DEVICE = "device"
ATTR_HEARTBEAT = "heartbeat"
