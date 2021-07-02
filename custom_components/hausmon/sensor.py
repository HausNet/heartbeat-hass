"""Support for monitoring the local system for anomalous events."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
import datetime
import logging
from typing import Any, Dict, Optional, List
import pprint

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA,
    BinarySensorEntity
)
from homeassistant.const import (
    CONF_ICON,
    CONF_SENSORS,
    CONF_ID, CONF_NAME, EVENT_STATE_CHANGED, EVENT_HOMEASSISTANT_STARTED,
)
from homeassistant.core import HomeAssistant, Event
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
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


@dataclass
class PulseState:
    """Data for a missing pulse sensor."""
    # The current state - true => pulse missing, false => pulse present
    pulse_missing: bool
    # Time by which, if no pulse has been received, the pulse will be
    # considered missing.
    receipt_deadline: Optional[datetime.datetime]
    # Minutes between expected pulses.
    pulse_minutes: int
    # Related entity that is being monitored.
    related_entity_id: str
    # Time the state was changed last.
    update_time: Optional[datetime.datetime]
    # Last exception, if any.
    last_exception: Optional[BaseException]

    def set_next_deadline(self):
        """Set the next deadline by adding the number of minutes a pulse is
        expected in, to the current date/time.
        """
        self.receipt_deadline = datetime.datetime.now() + \
            datetime.timedelta(minutes=self.pulse_minutes)


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
    sensor_registry: Dict[str, PulseState] = {}

    for sensor_config in config[CONF_SENSORS]:
        pulse_minutes = sensor_config[CONF_PULSE_MINUTES]
        sensor_id = sensor_config[CONF_ID]
        related_entity_id = sensor_config[CONF_RELATED_ENTITY_ID]
        sensor_registry[sensor_id] = PulseState(
            pulse_missing=False,
            receipt_deadline=None,
            pulse_minutes=pulse_minutes,
            related_entity_id=related_entity_id,
            update_time=None,
            last_exception=None
        )
        _LOGGER.debug("Added sensor to registry: %s", sensor_id)
        entities.append(PulseMissingSensor(
            sensor_config[CONF_ID],
            sensor_config[CONF_NAME],
            sensor_config[CONF_ICON],
            sensor_registry[sensor_id]
        ))
        _LOGGER.debug("Created entity for sensor: %s", sensor_id)
    async_add_entities(entities)
    await async_manage_sensor_registry_updates(
        hass,
        sensor_registry
    )


async def async_manage_sensor_registry_updates(
    hass: HomeAssistant,
    sensor_registry: Dict[str, PulseState]
) -> None:
    """Update the registry and create polling."""
    _pulse_data_lock = asyncio.Lock()
    _timeout_scheduled = False

    def _handle_missing_pulse(sensor_id: str, pulse_state: PulseState) -> bool:
        """ Called when pulse goes missing. Returns true if the pulse went
        missing since the last time it was received -- i.e. it happened since
        the last time it was updated.
        """
        _LOGGER.debug(
            "Handling missing pulse: "
            "sensor=%s, related_entity_id=%s, current_state=%s",
            sensor_id,
            pulse_state.related_entity_id,
            pulse_state.pulse_missing
        )
        if pulse_state.pulse_missing:
            return False
        pulse_state.pulse_missing = True
        entity_id = pulse_state.related_entity_id
        minutes = pulse_state.pulse_minutes
        persistent_notification.async_create(
            hass,
            f"No updates received from '{entity_id}' in {minutes} minutes. ",
            title=f"Pulse missing: {sensor_id}",
            notification_id=sensor_id + '.' + str(int(time.time()))
        )
        return True

    def _handle_pulse_event(sensor_id: str, pulse_state: PulseState) -> bool:
        """ Update a pulse's state when a pulse event is received. Returns
        True if the state goes from missing to present.
        """
        _LOGGER.debug(
            "Handling pulse event received: entity=%s; current_state=%s",
            pulse_state.related_entity_id,
            pulse_state.pulse_missing
        )
        state_changed = pulse_state.pulse_missing
        pulse_state.pulse_missing = False
        now = datetime.datetime.now()
        pulse_state.update_time = now
        pulse_state.last_exception = None
        pulse_state.set_next_deadline()
        entity_id = pulse_state.related_entity_id
        if state_changed:
            persistent_notification.async_create(
                hass,
                f"Missing pulse from '{entity_id}' resumed. ",
                title=f"Pulse resumed: {sensor_id}",
                notification_id=sensor_id + str(int(time.time()))
            )
        return state_changed

    async def _set_next_deadline():
        """If a timeout has not been scheduled, schedule one for the closest
        receipt_deadline in the future. Does not schedule a timeout if all the
        pulses have gone missing.

        Note that the callback timer's resolution is seconds, so 1 is added to
        the timeout to avoid timeout times of zero.
        """
        async with _pulse_data_lock:
            nonlocal _timeout_scheduled
            if _timeout_scheduled:
                return
            next_timeout: Optional[datetime.datetime] = None
            now = datetime.datetime.now()
            for sensor_id, pulse_state in sensor_registry.items():
                if pulse_state.receipt_deadline < now:
                    continue
                if next_timeout is None:
                    next_timeout = pulse_state.receipt_deadline
                    continue
                if pulse_state.receipt_deadline < next_timeout:
                    next_timeout = pulse_state.receipt_deadline
            if next_timeout is None:
                _LOGGER.debug("No next timeout found")
                return
            _LOGGER.debug(
                "Setting next pulse timeout: scheduled=%s",
                next_timeout
            )
            _timeout_scheduled = True
        next_timeout_seconds = int((next_timeout - now).total_seconds()) + 1
        async_call_later(hass, next_timeout_seconds, _pulse_timeout)

    # noinspection PyUnusedLocal
    # timestamp ignored
    async def _pulse_timeout(timestamp: datetime.datetime) -> None:
        """Given the current time, examines each of the sensors, and, if its
        receipt_deadline is in the past, handles it as a missing pulse. Then,
        sets the next timout.
        """
        _LOGGER.debug("Pulse timeout!")
        state_changed = False
        async with _pulse_data_lock:
            nonlocal _timeout_scheduled
            _timeout_scheduled = False
            now = datetime.datetime.now()
            for sensor_id, pulse_state in sensor_registry.items():
                _LOGGER.debug(
                    "State: sensor=%s; entity=%s, now=%s; deadline=%s",
                    sensor_id,
                    pulse_state.related_entity_id,
                    now,
                    pulse_state.receipt_deadline
                )
                if pulse_state.receipt_deadline < now:
                    state_changed |= _handle_missing_pulse(
                        sensor_id,
                        pulse_state
                    )
        if state_changed:
            async_dispatcher_send(hass, SIGNAL_HAUSMON_UPDATE)
        await _set_next_deadline()

    async def _event_to_pulse(event: Event):
        """Event listener, that, when the event's entity corresponds to one
        of the sensors' related entities, resets that sensor's timeout. Also
        calls _set_next_deadline() to handle the case where all the pulses
        have gone missing, and the pulse timout has to be restarted.
        """

        _LOGGER.debug("Event listener triggered!")
        pp = pprint.PrettyPrinter()
        pp.pprint(event)

        state_changed: bool = False
        async with _pulse_data_lock:
            for sensor_id, sensor_data in sensor_registry.items():
                _LOGGER.debug(
                    "Matching event: related_entity_id=%s; event_entity_id=%s",
                    sensor_data.related_entity_id,
                    event.data['entity_id']
                )
                if sensor_data.related_entity_id == event.data['entity_id']:
                    state_changed |= _handle_pulse_event(sensor_id, sensor_data)
                    _LOGGER.debug(
                        "Pulse received: entity_id=%s; state_changed=%s",
                        event.data['entity_id'],
                        state_changed
                    )
        if state_changed:
            async_dispatcher_send(hass, SIGNAL_HAUSMON_UPDATE)
        await _set_next_deadline()

    # For event_time, passed in by HASS, but not used.
    # noinspection PyUnusedLocal
    async def _start_pulse_monitor(event_time: datetime.datetime):
        """Start monitoring pulses, and set up the first pulse deadline."""
        for sensor_id, pulse_state in sensor_registry.items():
            pulse_state.set_next_deadline()
        remove_listener = hass.bus.async_listen(
            EVENT_STATE_CHANGED,
            _event_to_pulse
        )

        _LOGGER.debug("Event listener installed!")
        pp = pprint.PrettyPrinter()
        pp.pprint(remove_listener)

        await _set_next_deadline()

    # Start working once HASS is up.
    hass.bus.async_listen(EVENT_HOMEASSISTANT_STARTED, _start_pulse_monitor)


class PulseMissingSensor(BinarySensorEntity):
    """A sensor that turns on when activity was not sensed within a given
    time frame.
    """
    def __init__(
        self,
        id_: str,
        name: str,
        icon: Optional[str],
        pulse_state: PulseState
    ) -> None:
        """Initialize the sensor, with an id, name, and pulse period. Also,
        give it access to the sensor data that is collected out of band.
        """
        self._name: str = name
        self._unique_id: str = id_
        self._pulse_state: PulseState = pulse_state
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
    def available(self) -> bool:
        """Return True if entity is available."""
        return True

    @property
    def should_poll(self) -> bool:
        """Entity does not poll."""
        return False

    @property
    def data(self) -> PulseState:
        """Return registry entry for the data."""
        return self._pulse_state
