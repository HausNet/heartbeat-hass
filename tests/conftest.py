""" Mocks and fixtures for testing the configuration flow. Follows the
    standard naming convention.
"""
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """ This fixture enables loading custom integrations in all tests.
        Remove to enable selective use of this fixture
    """
    yield
