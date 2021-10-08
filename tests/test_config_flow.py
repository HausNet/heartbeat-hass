"""Tests for heartbeat config flow."""
from unittest.mock import patch

import pytest

from homeassistant.data_entry_flow import RESULT_TYPE_FORM, \
    RESULT_TYPE_CREATE_ENTRY
from voluptuous.error import MultipleInvalid

from homeassistant.const import CONF_API_KEY, CONF_DEVICE
from homeassistant import config_entries
from homeassistant.components.hausnet_heartbeat import DOMAIN


async def test_flow_empty_name(hass):
    """Test config flow errors on invalid station."""
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


async def test_flow_works(hass):
    """Test config flow works."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result['type'] == RESULT_TYPE_FORM
    assert result['errors'] is None

    with patch(
        "homeassistant.components.hausnet_heartbeat.async_setup",
        return_value=True
    ):
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
