import os

import pytest
from flask import Flask

from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from panel.app import create_panel_app
from storage import sqlite_store as store


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TESSERACT_BRIDGE_ADMIN_TOKEN", "a-long-test-admin-token")
    config = BridgeConfig.from_dict(store.load_config())
    runtime = DeviceRuntime(config, SimulatedGPIOBackend())
    app = create_panel_app(config,runtime)
    app.testing=True
    yield app.test_client(),runtime
    runtime.shutdown()


def headers():
    return {"X-Bridge-Admin-Token":"a-long-test-admin-token"}


def test_admin_requires_token(client):
    http,_=client
    assert http.get("/api/admin/config").status_code==401
    assert http.get("/api/admin/config",headers=headers()).status_code==200


def test_config_is_drafted_and_activated_only_after_approval(client):
    http,runtime=client
    current=http.get("/api/admin/config",headers=headers()).json
    config=current["config"]
    config["devices"][0]["name"]="Revisão SQLite"
    r=http.post("/api/admin/drafts",headers=headers(),json=config)
    assert r.status_code==201, r.json
    assert store.load_config()["devices"][0]["name"] != "Revisão SQLite"
    result=http.post("/api/admin/drafts/"+str(r.json["id"])+"/activate",headers=headers())
    assert result.status_code==200, result.json
    assert store.load_config()["devices"][0]["name"] == "Revisão SQLite"
    assert runtime.list_devices()[0].name != "Revisão SQLite"


def test_duplicate_pin_is_rejected_by_admin(client):
    http,_=client
    payload=http.get("/api/admin/config",headers=headers()).json["config"]
    copied=dict(payload["devices"][0])
    copied["id"]="duplicated"
    payload["devices"].append(copied)
    r=http.post("/api/admin/drafts",headers=headers(),json=payload)
    assert r.status_code==409
    assert store.config_revision()==1
