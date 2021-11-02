""" Mocks and fixtures for testing the configuration flow. Follows the
    standard naming convention.
"""

import pytest
from unittest.mock import patch

pytest_plugins = "pytest_homeassistant_custom_component"

TEST_MODULE = "custom_components.hausnet_heartbeat"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """ This fixture enables loading custom integrations in all tests.
        Remove to enable selective use of this fixture
    """
    yield


@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """ This fixture is used to prevent HomeAssistant from attempting to create
        and dismiss persistent notifications. These calls would fail without
        this fixture since the persistent_notification integration is never
        loaded during a test.
    """
    with (
        patch(
            "homeassistant.components.persistent_notification.async_create"
        ),
        patch(
            "homeassistant.components.persistent_notification.async_dismiss"
        )
    ):
        yield


@pytest.fixture(name="verified_connection")
def verified_connection_fixture():
    """ Blanket verification of the connection. """
    with (
        patch(TEST_MODULE + ".async_setup_entry", return_value=True),
        patch(
            TEST_MODULE + ".HeartbeatService.verify_connection",
            return_value=(True, None)
        )
    ):
        yield
