"""Bridge side of the shared heating v1 contract; no physical hardware/broker."""
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from bridge import Bridge
from config import BridgeConfig, ConfigError
from device_runtime import DeviceRuntime, DeviceRuntimeError
from gpio.simulated_backend import SimulatedGPIOBackend
from recipe_engine.pid import PidController, PidGains

YAML = '''
mqtt: {enabled: false}
backend: simulated
panel: {enabled: false}
devices:
  - id: mash_heater
    name: Heater
    role: actuator
    subtype: digital
    command_topic: actuators/mash_heater/set
    state_topic: actuators/mash_heater/state
    hardware: {pin: 17, window_seconds: 10}
    is_risk: true
    failsafe_value: false
'''


def build(tmp_path, policy=None):
    text=YAML if policy is None else YAML.replace('window_seconds: 10', 'window_seconds: 10, external_control_policy: '+policy)
    path=tmp_path/'devices.yml';path.write_text(text,encoding='utf-8')
    config=BridgeConfig.load(path)
    runtime=DeviceRuntime(config,SimulatedGPIOBackend())
    bridge=Bridge(config,runtime)
    bridge._mqtt=MagicMock()
    return bridge,runtime


def automatic(runtime, duty=60):
    runtime.set_pid_duty('mash_heater',duty,telemetry={'demand_percent':95.0,'power_limit_percent':60.0,'temperature':60.0,'target':65.0})


def test_publisher_matches_shared_contract_and_preserves_window(tmp_path):
    bridge,runtime=build(tmp_path)
    try:
        automatic(runtime,100);runtime.tick_duty(0)
        automatic(runtime,60);runtime.tick_duty(1)
        bridge._telemetry_boot_id='contract-boot'
        bridge.publish_sensor_states()
        topic,payload=bridge._mqtt.publish.call_args.args
        assert topic.endswith('actuators/mash_heater/state')
        actual=json.loads(payload)
        fixture=json.loads((Path(__file__).parent/'fixtures/heating_telemetry_v1.json').read_text())
        actual['heating']['observed_at']=fixture['heating']['observed_at']
        assert actual==fixture
        assert bridge._mqtt.publish.call_args.kwargs=={'qos':0,'retain':False}
        bridge.publish_sensor_states()
        assert json.loads(bridge._mqtt.publish.call_args.args[1])['heating']['sequence']==2
        runtime.tick_duty(10)
        assert runtime.get_heating_telemetry('mash_heater')['applied_window_percent']==60
    finally:runtime.shutdown()


def test_local_only_blocks_remote_heat_and_release_but_accepts_off(tmp_path):
    bridge,runtime=build(tmp_path,'local_only')
    try:
        automatic(runtime);runtime.tick_duty(0)
        for command in ('80','{"value":80}','{"value":null}'):
            bridge._handle_command_message('mash_heater',command)
            assert runtime.get_heating_telemetry('mash_heater')['owner']=='local_recipe'
        bridge._handle_command_message('mash_heater','{"value":0}')
        runtime.tick_duty(1)
        state=runtime.get_heating_telemetry('mash_heater')
        assert state['owner']=='remote_manual' and state['selected_percent']==0 and state['output_on'] is False
        runtime.set_manual_duty('mash_heater',None)
        assert runtime.get_heating_telemetry('mash_heater')['owner']=='local_recipe'
    finally:runtime.shutdown()


def test_legacy_override_local_manual_and_failsafe_are_distinct(tmp_path):
    bridge,runtime=build(tmp_path)
    try:
        automatic(runtime);runtime.tick_duty(0)
        bridge._handle_command_message('mash_heater','40')
        runtime.tick_duty(1)
        assert runtime.get_heating_telemetry('mash_heater')['owner']=='remote_manual'
        runtime.set_manual_duty_percent('mash_heater',55)
        assert runtime.get_heating_telemetry('mash_heater')['owner']=='local_manual'
        runtime.set_manual_enabled('mash_heater',True)
        assert runtime.get_heating_telemetry('mash_heater')['owner']=='local_manual'
        runtime.apply_failsafe('mash_heater');runtime.tick_duty(2)
        state=runtime.get_heating_telemetry('mash_heater')
        assert state['owner']=='failsafe' and state['selected_percent']==0 and not state['output_on']
        runtime.emergency_stop('sensor failure')
        state=runtime.get_heating_telemetry('mash_heater')
        assert state['fault']=='sensor failure' and state['demand_percent'] is None
    finally:runtime.shutdown()


def test_pid_reports_pre_ceiling_demand_without_changing_output():
    pid=PidController(PidGains(20,0,0))
    assert pid.compute(65,60,1,output_limit=60)==60
    assert pid.last_demand_percent==100
    pid.reset();assert pid.last_demand_percent is None


@pytest.mark.parametrize('value',[float('nan'),float('inf'),True,'50'])
def test_nonfinite_or_nonnumeric_pid_duty_rejected(tmp_path,value):
    bridge,runtime=build(tmp_path)
    try:
        with pytest.raises(DeviceRuntimeError):runtime.set_pid_duty('mash_heater',value)
    finally:runtime.shutdown()


def test_invalid_policy_rejected(tmp_path):
    with pytest.raises(ConfigError):build(tmp_path,'automatic_anywhere')


def test_stop_reports_failsafe_before_mqtt_disconnect(tmp_path):
    bridge,runtime=build(tmp_path)
    automatic(runtime);runtime.tick_duty(0)
    bridge.stop()
    calls=bridge._mqtt.method_calls
    assert calls[0][0]=='publish' and calls[1][0]=='disconnect'
    payload=json.loads(calls[0].args[1])['heating']
    assert payload['owner']=='failsafe' and payload['selected_percent']==0
    assert payload['fault'] and not payload['output_on']
