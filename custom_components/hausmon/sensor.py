"""Support for monitoring the local system for anomalous events."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import datetime
from functools import lru_cache
import logging
import os
from typing import Any, cast

import psutil
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import (
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_TYPE,
    EVENT_HOMEASSISTANT_STOP,
    STATE_OFF,
    STATE_ON,
    CONF_CONDITIONS,
    CONF_ENTITY_ID,
    CONF_ICON,
)
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity_component import DEFAULT_SCAN_INTERVAL
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

CONF_COMPARISON = "comparison"
CONF_VALUE = "value"
DEFAULT_ICON = "mdi.alarm"

SIGNAL_HAUSMON_UPDATE = "hausmon_update"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_CONDITIONS, default={CONF_CONDITIONS: "alive"}): 
            vol.All(
                cv.ensure_list,
                [
                    vol.Schema(
                        {
                            vol.Required(CONF_NAME):
                                vol.All(str, vol.Length(min=1)),
                            vol.Required(CONF_ENTITY_ID):
                                vol.All(str, vol.Length(min=1)),
                            vol.Required(CONF_COMPARISON):
                                vol.All(str, vol.Length(min=1)),
                            vol.Required(CONF_VALUE):
                                vol.Number(),
                            vol.Optional(CONF_ICON, default=DEFAULT_ICON):
                                vol.All(str, vol.Length(min=1))
                        }
                    )
                ],
                None,
            )
    }
)


@dataclass
class SensorData:
    """Data for a sensor."""

    argument: Any
    state: str | None
    value: Any | None
    update_time: datetime.datetime | None
    last_exception: BaseException | None


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: Any | None = None,
) -> None:
    """Set up the monitor condition sensors."""
    entities = []
    sensor_registry: dict[tuple[str, str], SensorData] = {}

    for condition in config[CONF_CONDITIONS]:
        type_ = condition[CONF_TYPE]
        # Initialize the sensor argument if none was provided.
        # For disk monitoring default to "/" (root) to prevent runtime errors, if argument was not specified.
        if CONF_ARG not in condition:
            argument = ""
            if condition[CONF_TYPE].startswith("disk_"):
                argument = "/"
        else:
            argument = condition[CONF_ARG]

        # Verify if we can retrieve CPU / processor temperatures.
        # If not, do not create the entity and add a warning to the log
        if (
            type_ == "processor_temperature"
            and await hass.async_add_executor_job(_read_cpu_temperature) is None
        ):
            _LOGGER.warning("Cannot read CPU / processor temperature information")
            continue

        sensor_registry[(type_, argument)] = SensorData(
            argument, None, None, None, None
        )
        entities.append(SystemMonitorSensor(sensor_registry, type_, argument))

    scan_interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    await async_setup_sensor_registry_updates(hass, sensor_registry, scan_interval)

    async_add_entities(entities)


async def async_setup_sensor_registry_updates(
    hass: HomeAssistant,
    sensor_registry: dict[tuple[str, str], SensorData],
    scan_interval: datetime.timedelta,
) -> None:
    """Update the registry and create polling."""

    _update_lock = asyncio.Lock()

    def _update_sensors() -> None:
        """Update sensors and store the result in the registry."""
        for (type_, argument), data in sensor_registry.items():
            try:
                state, value, update_time = _update(type_, data)
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception("Error updating sensor: %s (%s)", type_, argument)
                data.last_exception = ex
            else:
                data.state = state
                data.value = value
                data.update_time = update_time
                data.last_exception = None

        # Only fetch these once per iteration as we use the same
        # data source multiple times in _update
        _disk_usage.cache_clear()
        _swap_memory.cache_clear()
        _virtual_memory.cache_clear()
        _net_io_counters.cache_clear()
        _net_if_addrs.cache_clear()
        _getloadavg.cache_clear()

    async def _async_update_data(*_: Any) -> None:
        """Update all sensors in one executor jump."""
        if _update_lock.locked():
            _LOGGER.warning(
                "Updating systemmonitor took longer than the scheduled update interval %s",
                scan_interval,
            )
            return

        async with _update_lock:
            await hass.async_add_executor_job(_update_sensors)
            async_dispatcher_send(hass, SIGNAL_HAUSMON_UPDATE)

    polling_remover = async_track_time_interval(hass, _async_update_data, scan_interval)

    @callback
    def _async_stop_polling(*_: Any) -> None:
        polling_remover()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_polling)

    await _async_update_data()


class SystemMonitorSensor(SensorEntity):
    """Implementation of a system monitor sensor."""

    def __init__(
        self,
        sensor_registry: dict[tuple[str, str], SensorData],
        sensor_type: str,
        argument: str = "",
    ) -> None:
        """Initialize the sensor."""
        self._type: str = sensor_type
        self._name: str = f"{self.sensor_type[SENSOR_TYPE_NAME]} {argument}".rstrip()
        self._unique_id: str = slugify(f"{sensor_type}_{argument}")
        self._sensor_registry = sensor_registry
        self._argument: str = argument

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
    def data(self) -> SensorData:
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
    type_: str, data: SensorData
) -> tuple[str | None, str | None, datetime.datetime | None]:
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
