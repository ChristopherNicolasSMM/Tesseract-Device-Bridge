import math
import pytest
from control_settings import factory_settings, load_settings, save_settings, power_limit, validate_settings
from recipe_engine.engine import RecipeEngine
from recipe_engine.pid import PidController, PidGains
from panel.app import create_panel_app
from tests.test_recipe_engine import setup


@pytest.mark.parametrize('delta,expected', [(-10,100),(-3,100),(-2,75),(-1.5,67.5),(-1,60),(0,50),(.25,40),(.5,30),(.75,15),(1,0),(5,0)])
def test_factory_curve(delta, expected):
    assert power_limit(factory_settings()['mash_curve'], delta) == pytest.approx(expected)


@pytest.mark.parametrize('field,value', [('boil_temperature', math.nan), ('boil_power',101),('alert_clear',3),('freeze_hold_on_alert',1),('mash_curve',[[0,10],[0,0]]),('mash_curve',[[0,10],[1,20]]),('vessel_profiles',{'x':'invalid'})])
def test_validation(field,value):
    settings=factory_settings();settings[field]=value
    with pytest.raises(ValueError):validate_settings(settings)


def make_engine(setup, **changes):
    runtime,recipe,path=setup
    settings=factory_settings();settings.update(changes)
    settings_path=path.parent/'settings.json';save_settings(settings,settings_path)
    engine=RecipeEngine(runtime,recipe,path,now=0,settings_path=settings_path)
    engine.start(0);engine.tick(0)
    return runtime,engine,settings_path


def test_long_ramp_cut_and_no_rebound(setup):
    runtime,engine,_=make_engine(setup)
    for now in range(1,100):engine.tick(now)
    target=engine.recipe.steps[0].target_temp
    for now,delta in enumerate([-2,-1,0,.5,1,2],100):
        runtime.inject_sensor('mash_tun_temp',target+delta);engine.tick(now)
        assert engine.thermal['automatic_power'] <= engine.thermal['power_limit']
    assert engine.thermal['automatic_power']==0
    runtime.inject_sensor('mash_tun_temp',target);engine.tick(106)
    assert engine.thermal['automatic_power'] < 5


def test_alarm_hysteresis_ack_and_timer_freeze(setup):
    runtime,engine,_=make_engine(setup,freeze_hold_on_alert=True)
    target=engine.recipe.steps[0].target_temp
    runtime.inject_sensor('mash_tun_temp',target);engine.tick(1)
    runtime.inject_sensor('mash_tun_temp',target+3);engine.tick(2)
    assert not engine.thermal['over_temperature']
    runtime.inject_sensor('mash_tun_temp',target+3.1);engine.tick(3)
    start=engine.state.hold_started_at
    alarm=[a for a in engine.pending_alarms if a.type=='over_temperature'][0]
    engine.acknowledge_alarm(alarm.id)
    engine.tick(20)
    assert engine.thermal['timer_frozen']
    assert engine.state.hold_started_at==start+17
    assert not [a for a in engine.pending_alarms if a.type=='over_temperature']
    runtime.inject_sensor('mash_tun_temp',target+2.6);engine.tick(21)
    assert engine.thermal['over_temperature']
    runtime.inject_sensor('mash_tun_temp',target+2.5);engine.tick(22)
    assert not engine.thermal['over_temperature']


def test_boiling_temperature_power_and_snapshot(setup):
    runtime,engine,path=make_engine(setup,boil_temperature=96.5,boil_power=65)
    engine.skip_next(1);engine.tick(1)
    runtime.inject_sensor('boil_temp',96);engine.tick(2)
    assert engine.state.status=='ramping'
    assert engine.thermal['automatic_power']==100
    runtime.inject_sensor('boil_temp',96.5);engine.tick(3)
    assert engine.state.status=='holding'
    assert engine.thermal['automatic_power']==65
    settings=load_settings(path);settings['boil_temperature']=98;save_settings(settings,path)
    engine.pause(4);engine.resume(5)
    assert engine.target_temperature(engine.recipe.steps[1])==96.5
    recovered=RecipeEngine(runtime,engine.recipe,engine._state_path,now=6,settings_path=path)
    assert recovered.state.status=='paused_after_crash'
    assert recovered.control_settings['boil_temperature']==96.5
    recovered.start(7)
    assert recovered.control_settings['boil_temperature']==98


def test_api_save_restore_validation_and_ui(setup):
    runtime,recipe,path=setup
    engine=RecipeEngine(runtime,recipe,path,now=0,settings_path=path.parent/'settings.json')
    app=create_panel_app(runtime._config,runtime,recipe_engine=engine)
    client=app.test_client()
    assert 'Configurações' in client.get('/').get_data(as_text=True)
    assert client.get('/static/control-settings.js').status_code==200
    settings=client.get('/api/control-settings').json['settings']
    settings['boil_temperature']=97
    assert client.put('/api/control-settings',json=settings).status_code==200
    assert engine.control_settings['boil_temperature']==100
    engine.start(1)
    assert engine.control_settings['boil_temperature']==97
    assert client.put('/api/control-settings',json=[]).status_code==400
    assert client.post('/api/control-settings/restore').json['settings']==factory_settings()
    assert engine.control_settings['boil_temperature']==97
    assert load_settings(engine._settings_path)==factory_settings()


def test_pid_external_ceiling_unwinds_integral():
    pid=PidController(PidGains(5,.1,0))
    for _ in range(50):pid.compute(65,60,2)
    assert pid.compute(65,65.5,2,output_limit=30)<=30
    assert pid.compute(65,66,2,output_limit=0)==0
    assert pid.compute(65,65,2,output_limit=50)==0
