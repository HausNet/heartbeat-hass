""" Test the client against service mocks. """

import unittest.mock as mock

import custom_components.hausnet_heartbeat.client as hbc
from bravado.testing.response_mocks import BravadoResponseMock


def test_devices_can_be_listed():
    """Test that devices can be listed"""
    devices = [
        {'id': 1, 'name': 'device_A', 'heartbeat_id': 1},
        {'id': 2, 'name': 'device_B', 'heartbeat_id': None},
        {'id': 3, 'name': 'device_C', 'heartbeat_id': 2},
    ]
    mock_client = mock.MagicMock(name='Mock Swagger Client')
    with mock.patch.object(hbc.SwaggerClient, 'from_url', return_value=mock_client):
        heartbeat_client = hbc.HeartbeatClient(service_url='http://fakeurl', token='some-token')
        mock_client.devices.devices_list().response.return_value = BravadoResponseMock(result=devices)
        devices = heartbeat_client.list_devices()
    assert len(devices) == 3

    for device in devices:
        assert device['name'] in ['device_A', 'device_B', 'device_C']
        if device['name'] == 'device_B':
            assert device['heartbeat_id'] is None
        else:
            assert device['heartbeat_id'] is not None


def test_get_device():
    """Test that a specific device can be retrieved."""
    devices = [
        {'id': 1, 'name': 'device_A', 'heartbeat_id': 1},
        {'id': 2, 'name': 'device_B', 'heartbeat_id': None},
        {'id': 3, 'name': 'device_C', 'heartbeat_id': 2},
    ]
    mock_client = mock.MagicMock(name='Mock Swagger Client')
    with mock.patch.object(hbc.SwaggerClient, 'from_url', return_value=mock_client):
        heartbeat_client = hbc.HeartbeatClient(service_url='http://fakeurl', token='some-token')
        mock_client.devices.devices_list().response.return_value = BravadoResponseMock(result=devices)
        device = heartbeat_client.get_device('device_C')
    assert device['name'] == 'device_C'


def test_heartbeat_spec_is_returned() -> None:
    """Test that a full hausnet_heartbeat spec is returned, given the device name."""
    devices = [
        {'id': 1, 'name': 'device_A', 'heartbeat_id': 1},
        {'id': 2, 'name': 'device_B', 'heartbeat_id': None},
        {'id': 3, 'name': 'device_C', 'heartbeat_id': 2},
    ]
    heartbeat_specs = [
        {'id': 1, 'period_seconds': 15},
        {'id': 2, 'period_seconds': 15},
    ]
    mock_client = mock.MagicMock(name='Mock Swagger Client')
    with mock.patch.object(hbc.SwaggerClient, 'from_url', return_value=mock_client):
        heartbeat_client = hbc.HeartbeatClient(service_url='http://fakeurl', token='some-token')
        mock_client.devices.devices_list().response.return_value = BravadoResponseMock(result=devices)
        mock_client.heartbeats.heartbeats_read().response.side_effect=[
            BravadoResponseMock(result=heartbeat_specs[0]), BravadoResponseMock(result=heartbeat_specs[1]),
        ]
        heartbeat_A = heartbeat_client.get_heartbeat('device_A')
        heartbeat_B = heartbeat_client.get_heartbeat('device_B')
    assert heartbeat_A is not None
    assert heartbeat_A['period_seconds'] == 15
    assert heartbeat_B is None
