"""Reusable serial core: no OS ports or hardware opened in these tests."""
import pytest
from reusable.serial_monitor import SerialError, SerialMonitor
from reusable.serial_monitor.service import validate_settings


class Connection:
    def __init__(self, **settings):
        self.settings = settings
        self.opened = False
        self.closed = False
        self.port = None
    def open(self):
        assert self.dtr is False and self.rts is False
        self.opened = True
    def read(self, limit):
        return b'hello\xff'[:limit]
    def close(self):
        self.closed = True


@pytest.fixture
def monitor():
    core = SerialMonitor(opener=Connection, enumerator=lambda: [], idle_seconds=30)
    yield core
    core.close_all()


def test_manual_port_does_not_need_registration_or_enumeration(monitor):
    assert monitor.ports()['ports'] == []
    opened = monitor.open('browser-a', port='COM123', baudrate=230400, parity='E', bytesize=7)
    connection = monitor._session['connection']
    assert connection.settings['timeout'] == 0.2
    data = monitor.read(opened['session'], 'browser-a')
    assert data['hex'] == '68 65 6c 6c 6f ff'
    assert data['text'] == 'hello\ufffd'
    assert data['bytes_read'] == 6
    assert not connection.closed
    monitor.close(opened['session'], 'browser-a')
    assert connection.closed


def test_ownership_conflict_and_expiry_release_resources(monitor):
    opened = monitor.open('a', port='/dev/ttyUSB0')
    connection = monitor._session['connection']
    with pytest.raises(SerialError):
        monitor.open('b', port='/dev/ttyUSB1')
    with pytest.raises(SerialError):
        monitor.read(opened['session'], 'b')
    with pytest.raises(SerialError):
        monitor.close(opened['session'], 'b')
    monitor._session['last_read'] -= 31
    monitor._expire(opened['session'])
    assert connection.closed
    assert monitor._session is None
    with pytest.raises(SerialError):
        monitor.read(opened['session'], 'a')


@pytest.mark.parametrize('port', ['socket://host:1234', 'rfc2217://host', '/etc/passwd',
    '../ttyUSB0', 'COM0', '/dev/serial/by-id/../../etc/passwd', None, {}])
def test_non_native_paths_rejected_without_opening(monitor, port):
    with pytest.raises(SerialError) as error:
        monitor.open('a', port=port)
    assert error.value.code == 'invalid_port'
    assert monitor._session is None


@pytest.mark.parametrize('values', [dict(baudrate=True), dict(baudrate=299),
    dict(bytesize=True), dict(parity=[]), dict(stopbits=True)])
def test_invalid_settings(values):
    with pytest.raises(SerialError):
        validate_settings('COM3', **values)


def test_test_operation_opens_and_closes(monitor):
    result = monitor.test('a', port='/dev/ttyACM0')
    assert result['status'] == 'opened_and_closed'
    assert monitor._session is None


def test_usb_disconnection_closes_failed_read(monitor):
    opened = monitor.open('a', port='COM3')
    connection = monitor._session['connection']
    def fail(_limit):
        raise OSError('USB removed')
    connection.read = fail
    with pytest.raises(SerialError):
        monitor.read(opened['session'], 'a')
    assert connection.closed
    assert monitor._session is None


def test_failed_open_closes_handle():
    handles = []
    def opener(**kwargs):
        handle = Connection(**kwargs)
        handles.append(handle)
        def fail():
            raise PermissionError('busy')
        handle.open = fail
        return handle
    monitor = SerialMonitor(opener=opener)
    try:
        with pytest.raises(SerialError):
            monitor.open('a', port='COM3')
        assert handles[0].closed
        assert monitor._session is None
    finally:
        monitor.close_all()
