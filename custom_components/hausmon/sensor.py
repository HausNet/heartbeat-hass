"""Support for monitoring the local system for anomalous events."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import datetime
from functools import lru_cache
import logging
import os
from typing import Any, cast, Dict, Optional, Tuple

import voluptuous as vol

from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA,
    BinarySensorEntity
)
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    STATE_OFF,
    STATE_ON,
    CONF_ICON,
    CONF_SENSORS,
    CONF_ID, CONF_NAME,
)
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

CONF_RELATED_ENTITY_ID = "related_entity_id"
CONF_PULSE_MINUTES = "pulse_minutes"
DEFAULT_ICON = "mdi.alarm"
SCAN_INTERVAL_MINUTES = 1

SIGNAL_HAUSMON_UPDATE = "hausmon_update"

# TODO: Make id & name unique
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_SENSORS, default={CONF_SENSORS: "pulse_missing"}):
            vol.All(
                cv.ensure_list,
                [
                    vol.Schema(
                        {
                            vol.Required(CONF_ID): cv.string,
                            vol.Required(CONF_NAME): cv.string,
                            vol.Required(CONF_RELATED_ENTITY_ID): cv.entity_id,
                            vol.Required(CONF_PULSE_MINUTES): cv.positive_int,
                            vol.Optional(CONF_ICON, default=DEFAULT_ICON):
                                cv.icon
                        }
                    )
                ],
                None,
            )
    }
)


@dataclass
class PulseMissingData:
    """Data for a missing pulse sensor."""
    # The current state - true => pulse missing, false => pulse present
    pulse_missing: bool
    # Time by which, if no pulse has been received, the pulse will be
    # considered missing.
    trigger_time: Optional[datetime.datetime]
    # Time the state was changed last.
    update_time: Optional[datetime.datetime]
    # Last exception, if any.
    last_exception: Optional[BaseException]


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Any | None = None,
) -> None:
    """Set up the monitor condition sensors."""
    entities = []
    sensor_registry: Dict[str, PulseMissingData] = {}

    for sensor_config in config[CONF_SENSORS]:
        sensor_registry[sensor_config[CONF_ID]] = PulseMissingData(
            None, None, None, None
        )
        entities.append(PulseMissingSensor(
            sensor_config[CONF_ID],
            sensor_config[CONF_NAME],
            sensor_config[CONF_PULSE_MINUTES],
            sensor_registry[CONF_ID]
        ))

    await async_manage_sensor_registry_updates(
        hass,
        sensor_registry,
        SCAN_INTERVAL_MINUTES
    )

    async_add_entities(entities)


async def async_manage_sensor_registry_updates(
    hass: HomeAssistant,
    sensor_registry: Dict[str, PulseMissingData],
    scan_interval_minutes: int,
) -> None:
    """Update the registry and create polling."""
    _update_lock = asyncio.Lock()

    def _update_sensors() -> None:
        """Update sensors and store the result in the registry."""
        for sensor_id, data in sensor_registry.items():
            try:
                state, value, update_time = _update(sensor_id, data)
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception(
                    "Error updating sensor: %s (%s)",
                    sensor_id
                )
                data.last_exception = ex
            else:
                data.state = state
                data.value = value
                data.update_time = update_time
                data.last_exception = None
                data.trigger_time = datetime.datetime.now()

    async def _async_update_data(*_: Any) -> None:
        """Update all sensors in one executor jump."""
        if _update_lock.locked():
            _LOGGER.warning(
                "Updating hausmon monitor sensors took longer than the "
                "scheduled update interval %s, skipping.",
                scan_interval_minutes,
            )
            return
        async with _update_lock:
            await hass.async_add_executor_job(_update_sensors)
            async_dispatcher_send(hass, SIGNAL_HAUSMON_UPDATE)

    polling_remover = async_track_time_interval(
        hass,
        _async_update_data,
        datetime.timedelta(minutes=scan_interval_minutes)
    )

    @callback
    def _async_stop_polling(*_: Any) -> None:
        polling_remover()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_polling)

    await _async_update_data()


class PulseMissingSensor(BinarySensorEntity):
    """A sensor that turns on when activity was not sensed within a given
    time frame.
    """
    def __init__(
        self,
        id_: str,
        name: str,
        pulse_minutes: int,
        sensor_data: PulseMissingData
    ) -> None:
        """Initialize the sensor, with an id, name, and pulse period. Also,
        give it access to the sensor data that is collected out of band.
        """
        self._name: str = name
        self._unique_id: str = id_
        self._pulse_minutes: int = pulse_minutes
        self._sensor_data = sensor_data

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID."""
        return self._unique_id

    @property
    def device_class(self) -> str | None:
        """Return the class of this sensor."""
        return self.sensor_type[SENSOR_TYPE_DEVICE_CLASS]  # type: ignore[no-any-return]

    @property
    def icon(self) -> str | None:
        """Icon to use in the frontend, if any."""
        return self.sensor_type[SENSOR_TYPE_ICON]  # type: ignore[no-any-return]

    @property
    def state(self) -> str | None:
        """Return the state of the device."""
        return self.data.state

    @property
    def unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of this entity, if any."""
        return self.sensor_type[SENSOR_TYPE_UOM]  # type: ignore[no-any-return]

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.data.last_exception is None

    @property
    def should_poll(self) -> bool:
        """Entity does not poll."""
        return False

    @property
    def sensor_type(self) -> list:
        """Return sensor type data for the sensor."""
        return CONDITION_TYPES[self._type]  # type: ignore

    @property
    def data(self) -> PulseMissingData:
        """Return registry entry for the data."""
        return self._sensor_registry[(self._type, self._argument)]

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_HAUSMON_UPDATE, self.async_write_ha_state
            )
        )


def _update(  # noqa: C901
    entity_id: str, data: PulseMissingData
) -> Tuple[Optional[str], Optional[str], Optional[datetime.datetime]]:
    """Get the latest system information."""
    state = None
    value = None
    update_time = None

    if type_ == "disk_use_percent":
        state = _disk_usage(data.argument).percent
    elif type_ == "disk_use":
        state = round(_disk_usage(data.argument).used / 1024 ** 3, 1)
    elif type_ == "disk_free":
        state = round(_disk_usage(data.argument).free / 1024 ** 3, 1)
    elif type_ == "memory_use_percent":
        state = _virtual_memory().percent
    elif type_ == "memory_use":
        virtual_memory = _virtual_memory()
        state = round((virtual_memory.total - virtual_memory.available) / 1024 ** 2, 1)
    elif type_ == "memory_free":
        state = round(_virtual_memory().available / 1024 ** 2, 1)
    elif type_ == "swap_use_percent":
        state = _swap_memory().percent
    elif type_ == "swap_use":
        state = round(_swap_memory().used / 1024 ** 2, 1)
    elif type_ == "swap_free":
        state = round(_swap_memory().free / 1024 ** 2, 1)
    elif type_ == "processor_use":
        state = round(psutil.cpu_percent(interval=None))
    elif type_ == "processor_temperature":
        state = _read_cpu_temperature()
    elif type_ == "process":
        state = STATE_OFF
        for proc in psutil.process_iter():
            try:
                if data.argument == proc.name():
                    state = STATE_ON
                    break
            except psutil.NoSuchProcess as err:
                _LOGGER.warning(
                    "Failed to load process with ID: %s, old name: %s",
                    err.pid,
                    err.name,
                )
    elif type_ in ["network_out", "network_in"]:
        counters = _net_io_counters()
        if data.argument in counters:
            counter = counters[data.argument][IO_COUNTER[type_]]
            state = round(counter / 1024 ** 2, 1)
        else:
            state = None
    elif type_ in ["packets_out", "packets_in"]:
        counters = _net_io_counters()
        if data.argument in counters:
            state = counters[data.argument][IO_COUNTER[type_]]
        else:
            state = None
    elif type_ in ["throughput_network_out", "throughput_network_in"]:
        counters = _net_io_counters()
        if data.argument in counters:
            counter = counters[data.argument][IO_COUNTER[type_]]
            now = dt_util.utcnow()
            if data.value and data.value < counter:
                state = round(
                    (counter - data.value)
                    / 1000 ** 2
                    / (now - (data.update_time or now)).total_seconds(),
                    3,
                )
            else:
                state = None
            update_time = now
            value = counter
        else:
            state = None
    elif type_ in ["ipv4_address", "ipv6_address"]:
        addresses = _net_if_addrs()
        if data.argument in addresses:
            for addr in addresses[data.argument]:
                if addr.family == IF_ADDRS_FAMILY[type_]:
                    state = addr.address
        else:
            state = None
    elif type_ == "last_boot":
        # Only update on initial setup
        if data.state is None:
            state = dt_util.utc_from_timestamp(psutil.boot_time()).isoformat()
        else:
            state = data.state
    elif type_ == "load_1m":
        state = round(_getloadavg()[0], 2)
    elif type_ == "load_5m":
        state = round(_getloadavg()[1], 2)
    elif type_ == "load_15m":
        state = round(_getloadavg()[2], 2)

    return state, value, update_time


# When we drop python 3.8 support these can be switched to
# @cache https://docs.python.org/3.9/library/functools.html#functools.cache
@lru_cache(maxsize=None)
def _disk_usage(path: str) -> Any:
    return psutil.disk_usage(path)


@lru_cache(maxsize=None)
def _swap_memory() -> Any:
    return psutil.swap_memory()


@lru_cache(maxsize=None)
def _virtual_memory() -> Any:
    return psutil.virtual_memory()


@lru_cache(maxsize=None)
def _net_io_counters() -> Any:
    return psutil.net_io_counters(pernic=True)


@lru_cache(maxsize=None)
def _net_if_addrs() -> Any:
    return psutil.net_if_addrs()


@lru_cache(maxsize=None)
def _getloadavg() -> tuple[float, float, float]:
    return os.getloadavg()


def _read_cpu_temperature() -> float | None:
    """Attempt to read CPU / processor temperature."""
    temps = psutil.sensors_temperatures()

    for name, entries in temps.items():
        for i, entry in enumerate(entries, start=1):
            # In case the label is empty (e.g. on Raspberry PI 4),
            # construct it ourself here based on the sensor key name.
            _label = f"{name} {i}" if not entry.label else entry.label
            # check both name and label because some systems embed cpu# in the
            # name, which makes label not match because label adds cpu# at end.
            if _label in CPU_SENSOR_PREFIXES or name in CPU_SENSOR_PREFIXES:
                return cast(float, round(entry.current, 1))

    return None
