"""Support for monitoring the local system for anomalous events."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import datetime
import logging
from enum import Enum
from typing import Any, Dict, Optional, List

import voluptuous as vol

from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA,
    BinarySensorEntity
)
from homeassistant.const import (
    CONF_ICON,
    CONF_SENSORS,
    CONF_ID, CONF_NAME, EVENT_STATE_CHANGED,
)
from homeassistant.core import HomeAssistant, Event
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

CONF_RELATED_ENTITY_ID = "related_entity_id"
CONF_PULSE_MINUTES = "pulse_minutes"
DEFAULT_ICON = "mdi.alarm"
SCAN_INTERVAL_MINUTES = 1

SIGNAL_HAUSMON_UPDATE = "hausmon_update"

# TODO: Make id & name unique
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_SENSORS): vol.All(
            cv.ensure_list,
            [
                vol.Schema(
                    {
                        vol.Required(CONF_ID): cv.string,
                        vol.Required(CONF_NAME): cv.string,
                        vol.Required(CONF_RELATED_ENTITY_ID): cv.entity_id,
                        vol.Required(CONF_PULSE_MINUTES): cv.positive_int,
                        vol.Required(CONF_ICON, default=DEFAULT_ICON):
                            cv.icon
                    }
                )
            ]
        )
    }
)


class PulseUpdateType(Enum):
    """Indicators of why a pulse is being updated."""
    PULSE_RECEIVED = 1
    PULSE_EXPIRED = 2


@dataclass
class PulseMissingData:
    """Data for a missing pulse sensor."""
    # The current state - true => pulse missing, false => pulse present
    pulse_missing: bool
    # Time by which, if no pulse has been received, the pulse will be
    # considered missing.
    trigger_time: Optional[datetime.datetime]
    # Minutes between expected pulses.
    pulse_minutes: int
    # Related entity that is being monitored.
    related_entity_id: str
    # Time the state was changed last.
    update_time: Optional[datetime.datetime]
    # Last exception, if any.
    last_exception: Optional[BaseException]


# noinspection PyUnusedLocal
# (discovery_info parameter)
async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Optional[Any] = None
) -> None:
    """Set up the monitor condition sensors."""
    entities: List[BinarySensorEntity] = []
    sensor_registry: Dict[str, PulseMissingData] = {}

    for sensor_config in config[CONF_SENSORS]:
        pulse_minutes = sensor_config[CONF_PULSE_MINUTES]
        trigger_time = datetime.datetime.now() + \
            datetime.timedelta(minutes=pulse_minutes)
        sensor_id = sensor_config[CONF_ID]
        related_entity_id = sensor_config[CONF_RELATED_ENTITY_ID]
        sensor_registry[sensor_id] = PulseMissingData(
            False,
            trigger_time,
            pulse_minutes,
            related_entity_id,
            None,
            None
        )
        entities.append(PulseMissingSensor(
            sensor_config[CONF_ID],
            sensor_config[CONF_NAME],
            sensor_config[CONF_ICON],
            sensor_registry[sensor_id]
        ))
    await async_manage_sensor_registry_updates(
        hass,
        sensor_registry
    )
    async_add_entities(entities)


async def async_manage_sensor_registry_updates(
    hass: HomeAssistant,
    sensor_registry: Dict[str, PulseMissingData]
) -> None:
    """Update the registry and create polling."""
    _pulse_data_lock = asyncio.Lock()

    def _update_pulse(
            pulse_data: PulseMissingData,
            pulse_update: PulseUpdateType
    ) -> bool:
        """Based on whether a pulse was received, or timed out, updates the
        pulse data. Returns true if the state was changed.
        """
        old_pulse_missing = pulse_data.pulse_missing
        if pulse_update == PulseUpdateType.PULSE_EXPIRED:
            if old_pulse_missing:
                return False
            pulse_data.pulse_missing = True
        else:  # PulseUpdateType.PULSE_RECEIVED
            pulse_data.pulse_missing = False
        now = datetime.datetime.now()
        pulse_data.update_time = now
        pulse_data.last_exception = None
        pulse_data.trigger_time = now + \
            datetime.timedelta(minutes=pulse_data.pulse_minutes)
        return old_pulse_missing != pulse_data.pulse_missing

    # noinspection PyUnusedLocal
    # timestamp ignored
    async def _update_pulse_missing(timestamp: datetime.datetime) -> None:
        """Update missing pulse sensors, by comparing the trigger time for
        each with the current time. Also sets up a timer callback for the next
        trigger time in line.
        """
        state_changed = False
        async with _pulse_data_lock:
            next_trigger: Optional[datetime.datetime] = None
            now = datetime.datetime.now()
            for sensor_id, data in sensor_registry.items():
                if now > data.trigger_time:
                    state_changed |= _update_pulse(
                        data,
                        PulseUpdateType.PULSE_EXPIRED
                    )
                if next_trigger is None:
                    next_trigger = data.trigger_time
                elif data.trigger_time < next_trigger:
                    next_trigger = data.trigger_time
            next_trigger_seconds = int((next_trigger - now).total_seconds())
            async_call_later(hass, next_trigger_seconds, _update_pulse_missing)
        if state_changed:
            async_dispatcher_send(hass, SIGNAL_HAUSMON_UPDATE)

    async def _event_to_pulse(event: Event):
        """Event listener that extracts the pulse of registered entities."""
        for sensor_id, sensor_data in sensor_registry.items():
            if sensor_data.related_entity_id == event.data['entity_id']:
                state_changed: bool = _update_pulse(
                    sensor_data,
                    PulseUpdateType.PULSE_RECEIVED
                )
                if state_changed:
                    async_dispatcher_send(hass, SIGNAL_HAUSMON_UPDATE)
                _LOGGER.debug(
                    "Pulse received: related_entity_id=%s; state_changed=%s",
                    event.data['entity_id'],
                    state_changed
                )

    hass.bus.async_listen(EVENT_STATE_CHANGED, _event_to_pulse)
    await _update_pulse_missing(datetime.datetime.now())


class PulseMissingSensor(BinarySensorEntity):
    """A sensor that turns on when activity was not sensed within a given
    time frame.
    """
    def __init__(
        self,
        id_: str,
        name: str,
        icon: Optional[str],
        sensor_data: PulseMissingData
    ) -> None:
        """Initialize the sensor, with an id, name, and pulse period. Also,
        give it access to the sensor data that is collected out of band.
        """
        self._name: str = name
        self._unique_id: str = id_
        self._sensor_data: PulseMissingData = sensor_data
        self._icon: str = icon

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID."""
        return self._unique_id

    @property
    def device_class(self) -> Optional[str]:
        """Return the class of this sensor."""
        return None

    @property
    def icon(self) -> Optional[str]:
        """Icon to use in the frontend."""
        return self._icon

    @property
    def state(self) -> Optional[bool]:
        """Return the state of the device."""
        return self.data.pulse_missing

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return True

    @property
    def should_poll(self) -> bool:
        """Entity does not poll."""
        return False

    @property
    def data(self) -> PulseMissingData:
        """Return registry entry for the data."""
        return self._sensor_data

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_HAUSMON_UPDATE, self.async_write_ha_state
            )
        )
