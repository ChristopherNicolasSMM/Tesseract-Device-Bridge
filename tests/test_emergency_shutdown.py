import signal
import threading
from pathlib import PureWindowsPath
from unittest.mock import Mock

import pytest
import yaml

from bridge import Bridge
from config import BridgeConfig
from device_runtime import DeviceRuntime, DeviceRuntimeError
from gpio.simulated_backend import SimulatedGPIOBackend
from gpio.ds18b20_driver import Ds18b20ReadError
from panel.app import create_panel_app
from recipe_engine.engine import RecipeEngine
from recipe_engine.models import Recipe
from recipe_engine.state import RecipeState
from safety_lifecycle import safety_lifecycle
from tests.test_recipe_engine import DEVICES_YAML, RECIPE_YAML


@pytest.fixture
def plant(tmp_path):
    config=BridgeConfig.from_dict(yaml.safe_load(DEVICES_YAML))
    # Emergency must ignore both is_risk=false and a nonzero configured failsafe.
    config.devices[-1].is_risk=False
    config.devices[-1].failsafe_value=True
    backend=SimulatedGPIOBackend()
    runtime=DeviceRuntime(config,backend)
    recipe=Recipe.from_dict(yaml.safe_load(RECIPE_YAML))
    engine=RecipeEngine(runtime,recipe,tmp_path/'state.json',now=0,settings_path=tmp_path/'settings.json')
    engine.start(0)
    runtime.set_manual_duty('mash_heater',100)
    runtime.set_manual_duty('boil_heater',100)
    runtime.set_actuator('pump_b1',True)
    runtime.tick_duty(0)
    return config,backend,runtime,engine


def assert_off(backend):
    assert all(not state['value'] for state in backend._pins.values() if state['mode'] in ('output','pwm'))


def test_sensor_exception_aborts_all_and_rejects_reactivation(plant,monkeypatch):
    _,backend,runtime,engine=plant
    read=backend.read
    def failed(pin,address=None):
        if address=='28-aaa':raise Ds18b20ReadError('sensor desconectado')
        return read(pin,address)
    monkeypatch.setattr(backend,'read',failed)
    with pytest.raises(Ds18b20ReadError):runtime.get_state('mash_tun_temp')
    assert_off(backend)
    assert engine.state.status=='aborted'
    assert RecipeState.load(engine._state_path).status=='aborted'
    for command in [lambda:runtime.set_actuator('pump_b1',True),lambda:runtime.set_manual_duty('mash_heater',100),lambda:runtime.resume_all_suspended_overrides(),lambda:engine.start(1),lambda:engine.resume(1)]:
        with pytest.raises((DeviceRuntimeError,RuntimeError)):command()
        assert_off(backend)
    runtime.tick_duty(10)
    assert_off(backend)


@pytest.mark.parametrize('invalid',[float('nan'),float('inf'),None,'65'])
def test_invalid_sensor_values_trip(plant,invalid):
    _,backend,runtime,engine=plant
    backend.inject(4,invalid,address='28-aaa')
    with pytest.raises(DeviceRuntimeError):runtime.get_state('mash_tun_temp')
    assert_off(backend);assert engine.state.status=='aborted'


def test_pid_exception_and_disk_failure_still_switch_off(plant,monkeypatch):
    _,backend,runtime,engine=plant
    engine.tick(0)
    monkeypatch.setattr(engine._pid['mash'],'compute',Mock(side_effect=ArithmeticError('PID falhou')))
    monkeypatch.setattr(engine,'_save',Mock(side_effect=OSError('disco cheio')))
    with pytest.raises(ArithmeticError):engine.tick(1)
    assert_off(backend);assert engine.state.status=='aborted'


def test_failed_off_write_does_not_skip_other_outputs(plant,monkeypatch):
    _,backend,runtime,engine=plant
    write=backend.write
    def failed(pin,value,address=None):
        if pin==17 and not value:raise OSError('GPIO indisponível')
        return write(pin,value,address)
    monkeypatch.setattr(backend,'write',failed)
    runtime.trip('falha')
    assert runtime.shutdown_errors=={'mash_heater':'GPIO indisponível'}
    assert not backend.read(27)
    assert not backend.read(22)
    assert engine.state.status=='aborted'


def test_command_write_failure_trips_other_outputs(plant,monkeypatch):
    _,backend,runtime,engine=plant
    write=backend.write
    def failed(pin,value,address=None):
        if pin==22 and value:raise OSError('falha de escrita')
        return write(pin,value,address)
    monkeypatch.setattr(backend,'write',failed)
    with pytest.raises(OSError):runtime.set_actuator('pump_b1',True)
    assert_off(backend)


@pytest.mark.parametrize('failure',['connect','loop','sleep','interrupt'])
def test_loop_lifecycle_never_leaves_outputs_on(plant,monkeypatch,failure):
    config,backend,runtime,engine=plant
    bridge=Bridge(config,runtime,engine)
    # Keep pin states for inspection after shutdown.
    monkeypatch.setattr(backend,'teardown',Mock())
    if failure=='connect':monkeypatch.setattr(bridge,'start',Mock(side_effect=OSError('broker indisponível')))
    if failure=='loop':monkeypatch.setattr(bridge,'tick_recipe',Mock(side_effect=RuntimeError('erro no loop')))
    if failure in ('sleep','interrupt'):
        monkeypatch.setattr('bridge.time.sleep',Mock(side_effect=KeyboardInterrupt() if failure=='interrupt' else RuntimeError('erro inesperado')))
    if failure=='interrupt':bridge.run_forever()
    else:
        with pytest.raises((OSError,RuntimeError)):bridge.run_forever()
    assert_off(backend);assert engine.state.status=='aborted'


def test_read_failure_in_panel_trips_without_mqtt(plant,monkeypatch):
    config,backend,runtime,engine=plant
    monkeypatch.setattr(backend,'read',Mock(side_effect=OSError('sensor falhou')))
    client=create_panel_app(config,runtime,recipe_engine=engine).test_client()
    assert client.get('/api/devices').status_code==500
    assert_off(backend)
    assert client.post('/api/devices/pump_b1/command',json={'value':True}).status_code==503
    status=client.get('/api/status').json
    assert status['emergency'] and status['emergency_reason']
    assert client.get('/api/recipe/status').json['status']=='aborted'


def test_unexpected_http_and_mqtt_exceptions_trip(plant):
    config,backend,runtime,engine=plant
    bridge=Bridge(config,runtime,engine)
    bridge._safe_callback(Mock(side_effect=ValueError('payload inesperado')))()
    assert_off(backend);assert engine.state.status=='aborted'


def test_signal_handler_turns_every_output_off(plant,monkeypatch):
    _,backend,runtime,engine=plant
    monkeypatch.setattr(backend,'teardown',Mock())
    original=signal.getsignal(signal.SIGTERM)
    with pytest.raises(SystemExit):
        with safety_lifecycle(runtime):
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
    assert_off(backend)
    assert signal.getsignal(signal.SIGTERM)==original


def test_uncaught_thread_error_trips(plant,monkeypatch):
    _,backend,runtime,engine=plant
    monkeypatch.setattr(backend,'teardown',Mock())
    monkeypatch.setattr(threading,'excepthook',Mock())
    with safety_lifecycle(runtime):
        threading.excepthook(Mock(thread=Mock(name='worker'),exc_value=RuntimeError('worker failed')))
        assert_off(backend);assert engine.state.status=='aborted'


def test_concurrent_command_cannot_reenergize_after_trip(plant):
    _,backend,runtime,engine=plant
    completed=threading.Event()
    def command():
        try:runtime.set_actuator('pump_b1',True)
        except DeviceRuntimeError:pass
        completed.set()
    with runtime._io_lock:
        thread=threading.Thread(target=command);thread.start()
        runtime.trip('falha concorrente')
    assert completed.wait(2)
    thread.join();assert_off(backend)


def test_windows_yaml_path_is_not_a_unicode_escape():
    path=PureWindowsPath(r'C:\Users\christopher.mauricio\AppData\Local\Temp')
    raw=yaml.safe_load(f'base_path: "{path.as_posix()}"')
    assert raw['base_path']=='C:/Users/christopher.mauricio/AppData/Local/Temp'


def test_real_gpio_active_low_sensor_background_failure_needs_no_http_poll(plant,tmp_path,monkeypatch):
    from gpio.real_backend import RealGPIOBackend
    from gpiozero.pins.mock import MockFactory, MockPWMPin
    config,_,_,old_engine=plant
    for device in config.devices:
        if device.role=='actuator':device.hardware['active_high']=False
        else:
            folder=tmp_path/device.hardware['address'];folder.mkdir()
            (folder/'w1_slave').write_text('crc YES\nt=25000\n',encoding='ascii')
            device.hardware.update(base_path=str(tmp_path),poll_interval_seconds=.01)
    backend=RealGPIOBackend(pin_factory=MockFactory(pin_class=MockPWMPin))
    runtime=DeviceRuntime(config,backend)
    engine=RecipeEngine(runtime,old_engine.recipe,tmp_path/'real-state.json',now=0,settings_path=tmp_path/'settings.json')
    engine.start(0)
    runtime.set_manual_duty('mash_heater',100)
    runtime.set_actuator('pump_b1',True)
    runtime.tick_duty(0)
    detected=threading.Event()
    trip=runtime.trip
    def tracked(reason):
        trip(reason);detected.set()
    monkeypatch.setattr(runtime,'trip',tracked)
    try:
        (tmp_path/'28-aaa'/'w1_slave').unlink()
        assert detected.wait(2), 'background sensor failure was not delivered'
        assert engine.state.status=='aborted'
        for pin in (17,27,22):
            assert not backend.read(pin)
            # active-low OFF is electrically HIGH, not forced LOW.
            assert backend._devices[pin].pin.state == 1
    finally:runtime.shutdown()


def test_initial_sensor_setup_failure_switches_off_outputs_already_initialized(plant,monkeypatch):
    config,backend,_,_=plant
    setup=backend.setup
    def failed(pin,mode,**kwargs):
        if mode=='input_analog':raise OSError('sensor ausente no boot')
        setup(pin,mode,**kwargs)
    monkeypatch.setattr(backend,'setup',failed)
    monkeypatch.setattr(backend,'teardown',Mock())
    with pytest.raises(OSError):DeviceRuntime(config,backend)
    assert_off(backend)


def test_unexpected_http_exception_aborts_recipe(plant):
    config,backend,runtime,engine=plant
    app=create_panel_app(config,runtime,recipe_engine=engine)
    @app.get('/test-unexpected')
    def broken():raise ArithmeticError('falha interna')
    assert app.test_client().get('/test-unexpected').status_code==500
    assert_off(backend);assert engine.state.status=='aborted'
