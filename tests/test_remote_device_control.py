import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import MagicMock
import pytest
from tests.test_heating_telemetry import YAML
from config import BridgeConfig, ConfigError
from bridge import Bridge
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend


@pytest.fixture
def setup(tmp_path):
    path = tmp_path/'devices.yml'
    path.write_text(YAML.replace('window_seconds: 10', 'window_seconds: 10, remote_control: true') + '''
  - id: pump
    name: Pump
    role: actuator
    subtype: digital
    state_topic: pump/state
    command_topic: pump/set
    hardware: {pin: 18, remote_control: true}
''')
    config = BridgeConfig.load(path)
    runtime = DeviceRuntime(config, SimulatedGPIOBackend())
    engine = MagicMock(); engine.pending_pump_confirmations = ['pump']
    bridge = Bridge(config, runtime, engine)
    bridge._mqtt = MagicMock()
    yield bridge, runtime, engine
    runtime.shutdown()


def send(bridge, action, value=None, device='mash_heater', **changes):
    command = {'version':1,'boot_id':bridge._remote_control.boot_id,'request_id':str(uuid4()),
        'issued_at':datetime.now(timezone.utc).isoformat(),'action':action,'value':value,**changes}
    bridge._handle_command_message(device, json.dumps({'device_control':command}))
    return command


def test_power_prepare_enable_release_and_off_preserve_pid(setup):
    bridge, runtime, _ = setup
    runtime.set_pid_duty('mash_heater', 65)
    send(bridge,'power_prepare',40)
    state=runtime.get_state('mash_heater')
    assert not state.duty_enabled and state.duty_percent == 65
    send(bridge,'power_enable');runtime.tick_duty(0)
    assert runtime.get_heating_telemetry('mash_heater')['owner'] == 'remote_manual'
    assert runtime.get_state('mash_heater').duty_percent == 40
    send(bridge,'power_release');runtime.tick_duty(1)
    assert runtime.get_state('mash_heater').duty_percent == 65
    send(bridge,'power_off');runtime.tick_duty(2)
    assert runtime.get_state('mash_heater').duty_enabled
    assert runtime.get_state('mash_heater').duty_percent == 0
    assert runtime.get_state('mash_heater').value is False


def test_pump_manual_release_and_confirmation(setup):
    bridge,runtime,engine=setup
    send(bridge,'pump_set',True,'pump')
    assert runtime.has_manual_override('pump') and runtime.get_state('pump').value is True
    send(bridge,'pump_release',device='pump')
    assert not runtime.has_manual_override('pump')
    send(bridge,'pump_confirm',device='pump');engine.confirm_pump_auto.assert_called_once_with('pump')
    send(bridge,'pump_decline',device='pump');engine.decline_pump_auto.assert_called_once_with('pump')
    engine.pending_pump_confirmations=[]
    send(bridge,'pump_confirm',device='pump')
    assert bridge._remote_control.results['pump']['status']=='rejected'


@pytest.mark.parametrize('changes',[{'boot_id':'old'},{'issued_at':(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat()}, {'version':True}, {'action':'unknown'}, {'value':True}, {'value':101}, {'value':float('nan')}])
def test_rejected_commands_never_arm(setup,changes):
    bridge,runtime,_=setup
    send(bridge, changes.get('action','power_prepare'), changes.get('value',30), **{k:v for k,v in changes.items() if k not in ('action','value')})
    assert not runtime.get_state('mash_heater').duty_enabled
    assert bridge._remote_control.results['mash_heater']['status']=='rejected'


def test_duplicate_enable_does_not_rearm_after_local_release(setup):
    bridge,runtime,_=setup
    data=send(bridge,'power_enable')
    runtime.set_manual_enabled('mash_heater',False)
    bridge._handle_command_message('mash_heater',json.dumps({'device_control':data}))
    assert not runtime.get_state('mash_heater').duty_enabled


def test_managed_generic_on_blocked_and_publisher_reports_result(setup):
    bridge,runtime,_=setup
    bridge._handle_command_message('mash_heater','{"value":true}')
    assert not runtime.get_state('mash_heater').duty_enabled
    send(bridge,'power_prepare',35)
    bridge.publish_sensor_states()
    frames=[json.loads(c.args[1]) for c in bridge._mqtt.publish.call_args_list]
    frame=next(f for f in frames if f['control']['kind']=='power')
    assert frame['control']['manual_percent']==35 and not frame['control']['manual_enabled']
    assert frame['control']['last_command']['status']=='applied'


def test_local_only_accepts_only_off(setup):
    bridge,runtime,_=setup
    runtime.get_device_config('mash_heater').hardware['external_control_policy']='local_only'
    send(bridge,'power_enable')
    assert bridge._remote_control.results['mash_heater']['status']=='rejected'
    send(bridge,'power_off')
    assert runtime.get_state('mash_heater').duty_percent==0


@pytest.mark.parametrize('hardware', ['remote_control: yes', 'remote_control: "true"', 'remote_control: true, heating_source: {}'])
def test_optin_config_validation(tmp_path,hardware):
    path=tmp_path/'config.yml'
    # 'yes' is a valid YAML boolean; string "true" is not.
    path.write_text(YAML.replace('window_seconds: 10', 'window_seconds: 10, '+hardware))
    if hardware=='remote_control: yes':
        assert BridgeConfig.load(path).devices[0].hardware['remote_control'] is True
    else:
        with pytest.raises(ConfigError):BridgeConfig.load(path)


def test_failsafe_always_wins_remote_command(setup):
    bridge,runtime,_=setup
    runtime.emergency_stop('Sensor perdido')
    send(bridge,'power_enable')
    send(bridge,'pump_set',True,'pump')
    runtime.tick_duty(0)
    assert runtime.get_state('mash_heater').value is False
    assert runtime.get_state('pump').value is False
    assert bridge._remote_control.results['pump']['status']=='rejected'


def test_legacy_boolean_power_is_full_percent_not_one(tmp_path):
    from tests.test_heating_telemetry import build
    bridge,runtime=build(tmp_path)
    try:
        bridge._handle_command_message('mash_heater','{"value":true}')
        assert runtime.get_state('mash_heater').duty_percent==100
    finally:runtime.shutdown()


def test_shared_control_contract(setup):
    from pathlib import Path
    bridge,runtime,_=setup
    runtime.set_manual_duty_percent('mash_heater',40)
    bridge._remote_control.boot_id='control-contract-boot'
    bridge.publish_sensor_states()
    actual=next(json.loads(c.args[1]) for c in bridge._mqtt.publish.call_args_list if 'heating' in json.loads(c.args[1]))
    fixture=json.loads((Path(__file__).parent/'fixtures/device_control_v1.json').read_text())
    actual['control']['observed_at']=fixture['control']['observed_at']
    assert {'value':actual['value'],'control':actual['control']}==fixture


def test_pump_telemetry_distinguishes_failsafe_from_stored_manual_intent(setup):
    bridge,runtime,_=setup
    send(bridge,'pump_set',True,'pump')
    runtime.apply_failsafe_external('pump',False)
    state=bridge._remote_control.telemetry(runtime.get_device_config('pump'))
    assert state['manual_enabled'] and not state['output_on'] and state['owner']=='failsafe'


def test_bridge_wires_retained_rejection_for_opted_in_devices(setup):
    from types import SimpleNamespace
    from unittest.mock import patch
    bridge,runtime,_=setup
    bridge._config.mqtt.enabled=True
    with patch('mqtt_client.mqtt.Client'):
        connected=Bridge(bridge._config,runtime)
    assert connected._mqtt._reject_retained_device_ids=={'mash_heater','pump'}
    command={'version':1,'request_id':'retained-enable','boot_id':connected._remote_control.boot_id,
        'issued_at':datetime.now(timezone.utc).isoformat(),'action':'power_enable'}
    topic=next(topic for topic,device in connected._command_topic_lookup.items() if device=='mash_heater')
    message=SimpleNamespace(topic=topic,payload=json.dumps({'device_control':command}).encode(),retain=True)
    connected._mqtt._handle_message(None,None,message)
    assert not runtime.get_state('mash_heater').duty_enabled
    message.retain=False
    connected._mqtt._handle_message(None,None,message)
    assert runtime.get_state('mash_heater').duty_enabled
