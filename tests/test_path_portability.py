"""Run these tests on Windows as well as Linux; no real GPIO is accessed."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import control_settings
import data
import project_paths
from config import BridgeConfig
from recipe_engine.state import RecipeState
from run_panel import ensure_config_file
from tests.test_boot_log import load_boot_log_fn


@pytest.mark.parametrize('name',['DEFAULT_CONFIG_PATH','EXAMPLE_CONFIG_PATH','DEFAULT_RECIPE_STATE_PATH','LEGACY_RECIPE_PATH'])
def test_default_paths_are_absolute_and_ignore_cwd(tmp_path,monkeypatch,name):
    monkeypatch.chdir(tmp_path)
    path=getattr(project_paths,name)
    assert path.is_absolute()
    assert path.is_relative_to(project_paths.PROJECT_ROOT)
    assert path != tmp_path/path.name


def test_data_and_settings_paths_ignore_cwd(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert data.DATA_DIR==project_paths.DATA_DIR
    assert data.LEGACY_RECIPE_PATH==project_paths.LEGACY_RECIPE_PATH
    assert control_settings.DEFAULTS_PATH==project_paths.DATA_DIR/'control_defaults.json'
    assert control_settings.SETTINGS_PATH==project_paths.DATA_DIR/'private'/'control_settings.json'
    assert len(control_settings.load_settings()['mash_curve'])==6


def test_example_recreates_missing_config_in_path_with_spaces_and_accents(tmp_path):
    destination=tmp_path/'Instalação com espaços'/'data'/'public'/'devices.yml'
    ensure_config_file(destination)
    assert BridgeConfig.load(destination).backend=='simulated'
    assert destination.read_bytes()==project_paths.EXAMPLE_CONFIG_PATH.read_bytes()
    destination.write_text('keep my config',encoding='utf-8')
    ensure_config_file(destination)
    assert destination.read_text(encoding='utf-8')=='keep my config'


def test_state_creates_missing_parent_directory(tmp_path):
    path=tmp_path/'Dados privados com espaços'/'private'/'recipe_state.json'
    RecipeState.fresh('Mosturação').save(path)
    assert RecipeState.load(path).recipe_name=='Mosturação'


def test_boot_log_windows_uses_only_local_path(tmp_path):
    load_boot_log_fn(tmp_path,platform_name='nt')('Inicialização Windows')
    assert (tmp_path/'logs'/'boot.log').exists()
    assert not (tmp_path/'var_log').exists()


@pytest.mark.parametrize('entrypoint',['run_bridge','run_panel'])
def test_entrypoints_from_other_cwd_in_installation_with_spaces(tmp_path,entrypoint):
    installation=tmp_path/'Instalação Tesseract com espaços'
    shutil.copytree(project_paths.PROJECT_ROOT,installation,
                    ignore=shutil.ignore_patterns('.git','__pycache__','.pytest_cache','*.patch','logs','private'))
    # Exercise clean-install bootstrap as well as the explicit --debug flag.
    (installation/'data'/'public'/'devices.yml').unlink()
    outside=tmp_path/'diretório externo';outside.mkdir()
    code='''
import sys, time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
entrypoint=sys.argv[2]
from flask import Flask
# Avoid opening sockets or waiting forever in a portability regression.
Flask.run=lambda *args,**kwargs: None
if entrypoint=='run_bridge':
    import run_bridge as module
    def one_cycle(bridge):
        bridge._runtime.validate_sensors()
        if bridge.recipe_engine:
            bridge.recipe_engine.start(time.time())
            bridge.recipe_engine.tick(time.time())
    module.Bridge.run_forever=one_cycle
else:
    import run_panel as module
sys.argv=[entrypoint+'.py','--debug']
module.main()
'''
    result=subprocess.run([sys.executable,'-c',code,str(installation),entrypoint],cwd=outside,
                          capture_output=True,text=True,encoding='utf-8',
                          env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=20)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    assert (installation/'data'/'public'/'devices.yml').exists()
    assert not (outside/'data').exists()
    assert not (outside/'--debug').exists()
    if entrypoint=='run_bridge':
        state=RecipeState.load(installation/'data'/'private'/'recipe_state.json')
        assert state.status=='aborted'  # lifecycle safely closed the simulated run
