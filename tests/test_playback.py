import asyncio
import json
import time
import pytest
from ios_location_controller.playback import PlaybackController

@pytest.fixture(autouse=True)
def isolate_device_discovery(monkeypatch):
    # These tests use fake adapters. Keep real usbmux discovery and its
    # external service cancellation races out of lifecycle assertions.
    async def parked_discovery(self):
        await asyncio.Future()
    monkeypatch.setattr(PlaybackController, '_discover', parked_discovery)

class FakeDevice:
    sent=[]
    def __init__(self, **kwargs): pass
    async def connect(self): pass
    async def close(self): pass
    async def clear(self): pass
    async def set_point(self,point): self.sent.append(point)

def test_lifecycle_and_persistence(tmp_path):
    c=PlaybackController(tmp_path/'session.json',FakeDevice)
    route={"name":"test","points":[{"lat":31.23,"lng":121.47},{"lat":31.24,"lng":121.48}]}
    try:
        with pytest.raises(ValueError): c.call('start')
        c.call('route',route)
        assert c.status()['current'] is None
        c.call('settings',{'interval':.1})
        c.call('connect')
        assert c.status()['current']==route['points'][0]
        c.call('position', {'lat': 35.0, 'lng': 139.0})
        assert c.status()['current']=={'lat': 35.0, 'lng': 139.0}
        c.call('start'); time.sleep(.35)
        c.call('pause')
        paused=c.status()
        time.sleep(.4)
        assert c.status()['current']==paused['current']
        assert c.status()['elapsed_s']==paused['elapsed_s']
        with pytest.raises(ValueError): c.call('route',route)
        c.call('start'); time.sleep(.2); c.call('pause')
        assert 0 < c.status()['elapsed_s']-paused['elapsed_s'] < .4
        c.call('stop'); assert c.status()['current'] is None
        c.call('disconnect'); assert not c.status()['connected']
    finally: c.close()
    restored=PlaybackController(tmp_path/'session.json',FakeDevice)
    try:
        assert restored.status()['route']==route
        assert restored.status()['settings']['interval']==.1
        assert restored.status()['state']=='idle'
        assert restored.status()['current'] is None
    finally: restored.close()


def test_point_variation_is_saved_and_sent_at_start(tmp_path):
    from ios_location_controller.gpx import Point, distance_meters
    path = tmp_path / 'session.json'
    controller = PlaybackController(path, FakeDevice)
    route = {'name':'jitter', 'points':[{'lat':31.23,'lng':121.47},
                                      {'lat':31.24,'lng':121.48}]}
    try:
        controller.call('settings', {'point_variation_m':3, 'interval':10})
        controller.call('route', route)
        controller.call('connect')
        current = controller.status()['current']
        deviation = distance_meters(Point(current['lat'], current['lng']), Point(31.23,121.47))
        assert 0 < deviation <= 3.001
        assert controller.call('start')['current'] == current
        controller.call('pause')
        assert controller.call('start')['current'] == current
        assert controller.status()['route'] == route
    finally:
        controller.close()
    saved = json.loads(path.read_text())
    assert saved['settings']['point_variation_m'] == 3
    assert saved['points'] == route['points']


def test_platform_options_and_failed_cleanup(tmp_path):
    options = []

    class Device(FakeDevice):
        fail_close = False

        def __init__(self, **kwargs):
            options.append(kwargs)
            self.udid = 'wifi-phone'

        async def close(self):
            if self.fail_close:
                raise RuntimeError('offline during cleanup')

    controller = PlaybackController(tmp_path/'wireless.json', Device)
    try:
        result = controller.call('connect', {'platform':'android', 'address':'192.168.1.2:5555'})
        assert result['platform'] == 'android'
        assert result['udid'] == 'wifi-phone'
        assert options[0]['address'] == '192.168.1.2:5555'
        controller.device.fail_close = True
        with pytest.raises(RuntimeError, match='cleanup'):
            controller.call('disconnect')
        assert controller.status()['connected']
        controller.device.fail_close = False
        controller.call('disconnect')
        controller.call('connect', {'platform':'ios', 'rsd_host':'fd00::1', 'rsd_port':1234})
        assert options[-1]['rsd_host'] == 'fd00::1'
        assert options[-1]['rsd_port'] == 1234
        assert controller.status()['connected']
    finally:
        controller.close()


def test_clear_loaded_route_stops_and_persists(tmp_path):
    class Device(FakeDevice):
        clears = 0

        async def clear(self):
            self.clears += 1

    path = tmp_path / 'session.json'
    controller = PlaybackController(path, Device)
    points = [{'lat':31.23,'lng':121.47}, {'lat':31.24,'lng':121.48}]
    try:
        controller.call('route', {'name':'saved', 'points':points})
        controller.call('connect')
        controller.call('start')
        result = controller.call('clear-route')
        assert result['route'] == {'name':'', 'points':[]}
        assert result['state'] == 'ready'
        assert result['current'] is None
        assert result['total_m'] == 0
        assert controller.device.clears == 1
        with pytest.raises(ValueError):
            controller.call('start')
    finally:
        controller.close()
    restored = PlaybackController(path, Device)
    try:
        assert restored.status()['route'] == {'name':'', 'points':[]}
    finally:
        restored.close()


def test_clear_loaded_route_keeps_route_on_device_failure(tmp_path):
    class Device(FakeDevice):
        async def clear(self):
            raise RuntimeError('device offline')

    controller = PlaybackController(tmp_path/'session.json', Device)
    points = [{'lat':31.23,'lng':121.47}, {'lat':31.24,'lng':121.48}]
    try:
        controller.call('route', {'name':'saved', 'points':points})
        controller.call('connect')
        with pytest.raises(RuntimeError, match='device offline'):
            controller.call('clear-route')
        assert controller.status()['route']['points'] == points
    finally:
        controller.close()


def test_network_telemetry_reports_only_successful_updates(tmp_path):
    from unittest.mock import AsyncMock
    from ios_location_controller.android import AndroidDevice

    options = []

    def factory(**kwargs):
        options.append(kwargs['android_options'])
        device = AndroidDevice('test', options=kwargs['android_options'])
        device.original_mode = 'default'
        device.connect = AsyncMock()
        device.shell = AsyncMock(return_value='')
        return device

    controller = PlaybackController(tmp_path/'network.json', factory)
    config = {'provider':'network', 'network_interval':60, 'network_accuracy':90}
    try:
        controller.call('route', {'points':[{'lat':31,'lng':121}, {'lat':32,'lng':122}]})
        controller.call('settings', {'interval':.1})
        result = controller.call('connect', {'platform':'android', 'android_options':config})
        assert options == [config]
        assert result['diagnostics']['mock'] is True
        assert result['diagnostics']['injections']['network']['accuracy_m'] == 90
        controller.call('start')
        time.sleep(.25)
        result = controller.call('pause')
        assert result['distance_m'] > 0
        assert result['current'] == {'lat':31,'lng':121}
        result = controller.call('position', {'lat':33, 'lng':123})
        assert result['current'] == {'lat':33,'lng':123}
        assert result['diagnostics']['injections']['network']['lat'] == 33
        result = controller.call('stop')
        assert result['diagnostics']['injections'] == {}
        result = controller.call('disconnect')
        assert result['diagnostics'] is None
    finally:
        controller.close()
