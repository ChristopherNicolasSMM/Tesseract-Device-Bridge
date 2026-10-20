"""No broker/hardware: exercise the actual leased arbiter and runtime write gate."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest
from source_control import SourceControl
from config import BridgeConfig, ConfigError
from device_runtime import DeviceRuntime, DeviceRuntimeError
from gpio.simulated_backend import SimulatedGPIOBackend
from bridge import Bridge


def command(control, action='arm', **extra):
    return dict(version=1, action=action, boot_id=control.boot_id, arm_token=control.arm_token,
        lease_id='lease', sequence=1, issued_at=datetime.now(timezone.utc).isoformat(), target=65,
        limits=dict(minimum_seconds=1,cooldown_seconds=10), **extra)


def test_primary_qualification_off_dwell_hysteresis_and_unconditional_off():
    c=SourceControl('primary'); c.command(command(c),0)
    for t in (0,5):
        c.command({**command(c,'renew'),'sequence':t+2},t)
        assert not c.tick(t,60)
    c.command({**command(c,'renew'),'sequence':20},10)
    assert c.tick(10,60)
    assert c.tick(11,64.4)
    assert not c.tick(12,64.5)
    assert c.lease_id is not None
    assert not c.tick(13,60) # Minimum OFF dwell is enforced again.


def test_auxiliary_requires_local_recipe_target_and_demand():
    c=SourceControl('auxiliary'); c.command(command(c),0)
    assert not c.tick(0,60,95,65)
    c.command({**command(c,'renew'),'sequence':2},9)
    assert c.tick(10,60,95,65)
    assert c.tick(11,60,75,65)
    assert not c.tick(12,60,70,65)
    assert not c.tick(13,60,95,66)
    assert c.lease_id is None


@pytest.mark.parametrize('changes', [dict(boot_id='old'),dict(sequence=True),dict(version=True),
    dict(target=float('nan')),dict(target=0),dict(arm_token='replay'),dict(limits={'minimum_gap':0}),
    dict(issued_at=(datetime.now(timezone.utc)-timedelta(seconds=6)).isoformat())])
def test_invalid_arm_never_energizes(changes):
    c=SourceControl('primary')
    with pytest.raises((ValueError,TypeError)):c.command({**command(c),**changes},0)
    assert c.lease_id is None and c.output_on is False


def test_expiry_stop_and_restart_require_new_explicit_arm():
    c=SourceControl('primary'); old=command(c); c.command(old,0)
    c.tick(0,60)
    c.command({**command(c,'renew'),'sequence':2},9)
    assert c.tick(10,60)
    assert not c.tick(19,60)
    with pytest.raises(ValueError):c.command({**command(c,'renew'),'sequence':3},20)
    with pytest.raises(ValueError):c.command(old,20)
    c.command(command(c),20)
    c.stop('OFF')
    assert c.lease_id is None and not c.tick(21,60)
    with pytest.raises(ValueError):SourceControl('primary').command(old,0)


@pytest.mark.parametrize('temp', [float('nan'), None, True, 68])
def test_bad_readings_and_overtemperature_disarm(temp):
    c=SourceControl('primary');c.command(command(c),0)
    assert not c.tick(0,temp) and c.lease_id is None


def build(tmp_path, **settings):
    raw=dict(mqtt={'enabled':False},backend='simulated',panel={'enabled':False},devices=[
        dict(id='temp',name='Temp',role='sensor',subtype='temperature',state_topic='temp/state',hardware={'pin':4},simulated={'initial_value':60}),
        dict(id='gas',name='Gas',role='actuator',subtype='digital',state_topic='gas/state',command_topic='gas/set',is_risk=True,
             failsafe_value=False,hardware={'pin':17,'heating_source':{'participation':'primary','temperature_sensor':'temp','external_flame_cutoff':True,**settings}})])
    cfg=BridgeConfig.from_dict(raw);cfg.validate()
    runtime=DeviceRuntime(cfg,SimulatedGPIOBackend());bridge=Bridge(cfg,runtime);bridge._mqtt=MagicMock()
    return runtime,bridge


def test_runtime_rejects_all_generic_on_paths_and_publishes_source(tmp_path):
    r,b=build(tmp_path)
    try:
        for fn in (lambda:r.set_actuator('gas',True),lambda:r.set_manual_override('gas',True)):
            with pytest.raises(DeviceRuntimeError):fn()
        b._handle_command_message('gas','{"value":true}')
        assert not r.get_state('gas').value
        control=r._sources['gas']
        b._handle_command_message('gas',json.dumps({'heating_control':command(control)}))
        assert control.lease_id=='lease'
        b.publish_sensor_states()
        frame=json.loads(b._mqtt.publish.call_args.args[1])
        assert frame['heat_source']['armed'] and frame['heat_source']['backend']=='simulated'
        r.apply_failsafe('gas')
        assert control.lease_id is None and r.get_state('gas').value is False
        r.source_command('gas',command(control))
        r.trip('sensor failed')
        assert control.lease_id is None and r.get_state('gas').value is False
        with pytest.raises(DeviceRuntimeError):r.source_command('gas',command(control))
    finally:r.shutdown()


def test_auxiliary_cannot_configure_without_local_controller(tmp_path):
    with pytest.raises(ConfigError):build(tmp_path,participation='auxiliary')


def test_actual_gpio_follows_lease_and_cuts_without_waiting(tmp_path,monkeypatch):
    import device_runtime as module
    now=[0.0];monkeypatch.setattr(module.time,'monotonic',lambda:now[0])
    r,b=build(tmp_path)
    try:
        c=r._sources['gas'];r.source_command('gas',command(c));r.tick_sources()
        assert r.get_state('gas').value is False
        now[0]=9;r.source_command('gas',{**command(c,'renew'),'sequence':2})
        now[0]=10;r.tick_sources()
        assert r.get_state('gas').value is True
        r.inject_sensor('temp',64.5);r.tick_sources()
        assert r.get_state('gas').value is False
        now[0]=19;r.tick_sources()
        assert c.lease_id is None
    finally:r.shutdown()


def test_retained_source_command_does_not_reach_controller(tmp_path):
    from mqtt_client import MqttClientWrapper
    from types import SimpleNamespace
    from unittest.mock import patch
    r,b=build(tmp_path)
    try:
        with patch('mqtt_client.mqtt.Client'):
            wrapper=MqttClientWrapper(b._config.mqtt,{'gas/set':'gas'},lambda payload:None,
                b._handle_command_message,reject_retained_device_ids={'gas'})
        c=r._sources['gas']
        message=SimpleNamespace(topic='gas/set',payload=json.dumps({'heating_control':command(c)}).encode(),retain=True)
        wrapper._handle_message(None,None,message)
        assert c.lease_id is None
        message.retain=False;wrapper._handle_message(None,None,message)
        assert c.lease_id=='lease'
    finally:r.shutdown()


def test_publisher_matches_shared_source_fixture(tmp_path):
    from pathlib import Path
    r,b=build(tmp_path)
    try:
        c=r._sources['gas'];c.boot_id='source-contract-boot';c.arm_token='source-contract-token'
        b.publish_sensor_states()
        actual=json.loads(b._mqtt.publish.call_args.args[1])
        expected=json.loads((Path(__file__).parent/'fixtures/heat_source_v1.json').read_text())
        actual['heat_source']['observed_at']=expected['heat_source']['observed_at']
        assert actual==expected
        assert b._mqtt.publish.call_args.kwargs=={'qos':0,'retain':False}
    finally:r.shutdown()
