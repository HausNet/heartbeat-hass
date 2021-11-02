"""Tests for hausnet_heartbeat config flow."""

import pytest
from unittest.mock import patch

from conftest import TEST_MODULE

from homeassistant.data_entry_flow import RESULT_TYPE_FORM, \
    RESULT_TYPE_CREATE_ENTRY
from voluptuous.error import MultipleInvalid

from homeassistant.const import CONF_API_KEY, CONF_DEVICE
from homeassistant import config_entries
from custom_components.hausnet_heartbeat import DOMAIN


async def test_flow_empty_name(hass):
    """ Test case where config parameters left empty. """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert not result["errors"]

    with pytest.raises(MultipleInvalid):
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_DEVICE: None,
                CONF_API_KEY: None
            }
        )


async def test_flow_works(hass, verified_connection):
    """ Test config flow works with provided credentials. """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result['type'] == RESULT_TYPE_FORM
    assert not result['errors']

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_DEVICE: "my_device", CONF_API_KEY: "ABC123", }
    )

    assert result["type"] == RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "Heartbeat Configuration"
    assert result["data"] == {
        CONF_DEVICE: "my_device",
        CONF_API_KEY: "ABC123"
    }
