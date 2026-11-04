"""SQLite paths do not depend on the terminal's current working directory."""
import os
import json
from pathlib import Path
import pytest

import project_paths
from storage import sqlite_store as store
from tests.test_boot_log import load_boot_log_fn


def test_project_paths_absolute(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert project_paths.PROJECT_ROOT.is_absolute()
    assert store.DEFAULT_DB.is_absolute()


def test_config_and_settings_sqlite_are_cwd_independent(tmp_path,monkeypatch):
    before=store.load_config()
    monkeypatch.chdir(tmp_path)
    assert store.load_config()==before
    assert store.load_control()["mash_curve"]


def test_env_db_path_override_is_explicit(tmp_path,monkeypatch):
    other=tmp_path/"other.sqlite3"
    monkeypatch.setenv("TESSERACT_BRIDGE_DB",str(other))
    store.initialize()
    assert store.db_path()==other.resolve()


def test_boot_log_windows_uses_own_path(tmp_path):
    fn=load_boot_log_fn()
    fn("Boot test", platform_name="win32")


def test_recipe_state_test_adapter_uses_explicit_path(tmp_path):
    from recipe_engine.state import RecipeState
    state=RecipeState.fresh("Test")
    path=tmp_path/"state.json"
    state.save(path)
    assert RecipeState.load(path).recipe_name=="Test"
