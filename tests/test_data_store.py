import json
import textwrap

import pytest
import yaml

import data
from config import BridgeConfig
from recipe_engine.models import RecipeError


DEVICES_YAML = """
mqtt:
  enabled: false
backend: simulated
panel:
  enabled: false

devices:
  - id: mash_tun_temp
    name: "Temp Mostura"
    role: sensor
    subtype: temperature
    state_topic: "sensors/mash_tun_temp/state"
    hardware: { pin: 4, driver: ds18b20, address: "28-aaa" }
    simulated: { initial_value: 25.0 }

  - id: boil_temp
    name: "Temp Fervura"
    role: sensor
    subtype: temperature
    state_topic: "sensors/boil_temp/state"
    hardware: { pin: 4, driver: ds18b20, address: "28-bbb" }
    simulated: { initial_value: 20.0 }

  - id: mash_heater
    name: "Aquecedor Mostura"
    role: actuator
    subtype: digital
    command_topic: "actuators/mash_heater/set"
    hardware: { pin: 17, window_seconds: 10 }
    failsafe_value: false
    is_risk: true

  - id: boil_heater
    name: "Aquecedor Fervura"
    role: actuator
    subtype: digital
    command_topic: "actuators/boil_heater/set"
    hardware: { pin: 27, window_seconds: 10 }
    failsafe_value: false
    is_risk: true

  - id: pump_b1
    name: "Bomba B1"
    role: actuator
    subtype: digital
    command_topic: "actuators/pump_b1/set"
    hardware: { pin: 22 }
    failsafe_value: false
    is_risk: true
"""


def _recipe_dict(name="Receita Teste"):
    return {
        "name": name,
        "vessels": [
            {
                "id": "mash", "name": "Mash",
                "heater_device_id": "mash_heater", "sensor_device_id": "mash_tun_temp",
                "pid": {"kp": 5.0, "ki": 0.1, "kd": 0.0},
            },
        ],
        "steps": [
            {"vessel": "mash", "target_temp": 67, "hold_minutes": 10},
        ],
    }


@pytest.fixture
def bridge_config(tmp_path):
    path = tmp_path / "devices.yml"
    path.write_text(textwrap.dedent(DEVICES_YAML), encoding="utf-8")
    return BridgeConfig.load(path)


@pytest.fixture
def data_dirs(tmp_path, monkeypatch):
    """
    Aponta os caminhos do módulo data/ pra dentro de tmp_path -- os
    caminhos reais são intencionalmente fixos (pasta ao lado do
    código, não um serviço parametrizável), então o jeito certo de
    testar isolado é monkeypatch nas constantes do módulo.
    """
    public_dir = tmp_path / "data" / "public"
    private_dir = tmp_path / "data" / "private"
    public_dir.mkdir(parents=True)
    private_dir.mkdir(parents=True)

    monkeypatch.setattr(data, "PUBLIC_DIR", public_dir)
    monkeypatch.setattr(data, "PRIVATE_DIR", private_dir)
    monkeypatch.setattr(data, "BASE_RECIPE_PATH", public_dir / "receita_base.yaml")
    monkeypatch.setattr(data, "ACTIVE_RECIPE_POINTER_PATH", tmp_path / "data" / "active_recipe.txt")
    monkeypatch.setattr(data, "LEGACY_RECIPE_PATH", tmp_path / "recipe.yml")

    return {"public": public_dir, "private": private_dir, "root": tmp_path}


# ---- I/O genérico de entidade ----------------------------------------------


def test_read_entities_missing_file_returns_empty_list(data_dirs):
    assert data.read_entities("public", "receita") == []


def test_write_then_read_entities_roundtrip(data_dirs):
    entries = [{"id": "abc", "recipe": _recipe_dict()}]
    data.write_entities("public", "receita", entries)
    assert data.read_entities("public", "receita") == entries


def test_read_entities_invalid_json_raises(data_dirs):
    path = data_dirs["public"] / "receita.json"
    path.write_text("isto não é json {{{", encoding="utf-8")
    with pytest.raises(data.DataStoreError, match="não é um JSON válido"):
        data.read_entities("public", "receita")


def test_read_entities_non_list_root_raises(data_dirs):
    path = data_dirs["public"] / "receita.json"
    path.write_text('{"não": "é uma lista"}', encoding="utf-8")
    with pytest.raises(data.DataStoreError, match="lista de registros"):
        data.read_entities("public", "receita")


def test_source_dir_rejects_invalid_source(data_dirs):
    with pytest.raises(ValueError):
        data.read_entities("outro", "receita")


# ---- list_recipes -----------------------------------------------------------


def test_list_recipes_empty_when_nothing_exists(data_dirs):
    assert data.list_recipes() == []


def test_list_recipes_includes_base_when_present(data_dirs):
    yaml_content = yaml.safe_dump(_recipe_dict("Receita Base"), allow_unicode=True)
    data.BASE_RECIPE_PATH.write_text(yaml_content, encoding="utf-8")

    recipes = data.list_recipes()
    assert len(recipes) == 1
    assert recipes[0]["id"] == "public:base"
    assert recipes[0]["editable"] is False
    assert recipes[0]["name"] == "Receita Base"


def test_list_recipes_includes_json_entries_from_both_sources(data_dirs):
    data.write_entities("public", "receita", [{"id": "p1", "recipe": _recipe_dict("Pública 1")}])
    data.write_entities("private", "receita", [{"id": "v1", "recipe": _recipe_dict("Privada 1")}])

    recipes = {r["id"]: r for r in data.list_recipes()}
    assert recipes["public:p1"]["name"] == "Pública 1"
    assert recipes["public:p1"]["editable"] is True
    assert recipes["private:v1"]["name"] == "Privada 1"
    assert recipes["private:v1"]["source"] == "private"


def test_list_recipes_without_bridge_config_does_not_validate(data_dirs):
    # Receita com heater_device_id que não existe em lugar nenhum --
    # sem bridge_config, list_recipes não tenta validar, só lê o nome.
    bad_recipe = _recipe_dict()
    bad_recipe["vessels"][0]["heater_device_id"] = "nao_existe"
    data.write_entities("public", "receita", [{"id": "p1", "recipe": bad_recipe}])

    recipes = data.list_recipes()
    assert recipes[0]["valid"] is True  # não validado, então não marca inválido


def test_list_recipes_with_bridge_config_validates_and_flags_invalid(data_dirs, bridge_config):
    bad_recipe = _recipe_dict()
    bad_recipe["vessels"][0]["heater_device_id"] = "nao_existe"
    data.write_entities("public", "receita", [{"id": "p1", "recipe": bad_recipe}])

    recipes = data.list_recipes(bridge_config=bridge_config)
    assert recipes[0]["valid"] is False
    assert recipes[0]["error"]


def test_list_recipes_skips_entry_without_id(data_dirs):
    data.write_entities("public", "receita", [{"recipe": _recipe_dict()}])  # sem "id"
    assert data.list_recipes() == []


# ---- load_recipe_by_id -------------------------------------------------------


def test_load_recipe_by_id_base(data_dirs, bridge_config):
    yaml_content = yaml.safe_dump(_recipe_dict("Receita Base"), allow_unicode=True)
    data.BASE_RECIPE_PATH.write_text(yaml_content, encoding="utf-8")

    recipe = data.load_recipe_by_id("public:base", bridge_config)
    assert recipe.name == "Receita Base"


def test_load_recipe_by_id_from_json(data_dirs, bridge_config):
    data.write_entities("private", "receita", [{"id": "v1", "recipe": _recipe_dict("Da Privada")}])

    recipe = data.load_recipe_by_id("private:v1", bridge_config)
    assert recipe.name == "Da Privada"


def test_load_recipe_by_id_unknown_raises(data_dirs, bridge_config):
    with pytest.raises(RecipeError, match="não encontrada"):
        data.load_recipe_by_id("public:nao-existe", bridge_config)


def test_load_recipe_by_id_malformed_id_raises(data_dirs, bridge_config):
    with pytest.raises(RecipeError, match="inválido"):
        data.load_recipe_by_id("sem-dois-pontos", bridge_config)


def test_load_recipe_by_id_invalid_recipe_raises(data_dirs, bridge_config):
    bad_recipe = _recipe_dict()
    bad_recipe["vessels"][0]["heater_device_id"] = "nao_existe"
    data.write_entities("public", "receita", [{"id": "p1", "recipe": bad_recipe}])

    with pytest.raises(RecipeError):
        data.load_recipe_by_id("public:p1", bridge_config)


# ---- ponteiro de receita ativa ------------------------------------------------


def test_get_active_recipe_id_none_by_default(data_dirs):
    assert data.get_active_recipe_id() is None


def test_set_then_get_active_recipe_id_roundtrip(data_dirs):
    data.set_active_recipe_id("private:v1")
    assert data.get_active_recipe_id() == "private:v1"


# ---- load_active_recipe (resolução de fallback) -------------------------------


def test_load_active_recipe_returns_none_when_nothing_configured(data_dirs, bridge_config):
    assert data.load_active_recipe(bridge_config) is None


def test_load_active_recipe_falls_back_to_legacy_recipe_yml(data_dirs, bridge_config):
    yaml_content = yaml.safe_dump(_recipe_dict("Legado"), allow_unicode=True)
    data.LEGACY_RECIPE_PATH.write_text(yaml_content, encoding="utf-8")

    recipe = data.load_active_recipe(bridge_config)
    assert recipe.name == "Legado"


def test_load_active_recipe_prefers_base_over_legacy(data_dirs, bridge_config):
    data.BASE_RECIPE_PATH.write_text(yaml.safe_dump(_recipe_dict("Base"), allow_unicode=True), encoding="utf-8")
    data.LEGACY_RECIPE_PATH.write_text(yaml.safe_dump(_recipe_dict("Legado"), allow_unicode=True), encoding="utf-8")

    recipe = data.load_active_recipe(bridge_config)
    assert recipe.name == "Base"


def test_load_active_recipe_prefers_pointer_over_base(data_dirs, bridge_config):
    data.BASE_RECIPE_PATH.write_text(yaml.safe_dump(_recipe_dict("Base"), allow_unicode=True), encoding="utf-8")
    data.write_entities("private", "receita", [{"id": "v1", "recipe": _recipe_dict("Escolhida")}])
    data.set_active_recipe_id("private:v1")

    recipe = data.load_active_recipe(bridge_config)
    assert recipe.name == "Escolhida"


def test_load_active_recipe_falls_through_when_pointer_is_stale(data_dirs, bridge_config):
    """
    Ponteiro aponta pra uma receita que não existe mais (ex.: foi
    apagada) -- não derruba o motor de receita, cai pro próximo nível
    do fallback (aqui, receita_base).
    """
    data.BASE_RECIPE_PATH.write_text(yaml.safe_dump(_recipe_dict("Base"), allow_unicode=True), encoding="utf-8")
    data.set_active_recipe_id("private:nao-existe-mais")

    recipe = data.load_active_recipe(bridge_config)
    assert recipe.name == "Base"


# ---- get_effective_active_recipe_id ------------------------------------------


def test_effective_active_id_none_when_nothing_configured(data_dirs):
    assert data.get_effective_active_recipe_id() is None


def test_effective_active_id_falls_back_to_base(data_dirs):
    data.BASE_RECIPE_PATH.write_text(yaml.safe_dump(_recipe_dict("Base"), allow_unicode=True), encoding="utf-8")
    assert data.get_effective_active_recipe_id() == data.BASE_RECIPE_ID


def test_effective_active_id_prefers_explicit_pointer(data_dirs):
    data.BASE_RECIPE_PATH.write_text(yaml.safe_dump(_recipe_dict("Base"), allow_unicode=True), encoding="utf-8")
    data.set_active_recipe_id("private:v1")
    assert data.get_effective_active_recipe_id() == "private:v1"


# ---- get_recipe_dict_by_id ----------------------------------------------------


def test_get_recipe_dict_by_id_base(data_dirs):
    raw = _recipe_dict("Base")
    data.BASE_RECIPE_PATH.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    assert data.get_recipe_dict_by_id(data.BASE_RECIPE_ID)["name"] == "Base"


def test_get_recipe_dict_by_id_json_entry(data_dirs):
    data.write_entities("private", "receita", [{"id": "v1", "recipe": _recipe_dict("Da Privada")}])
    assert data.get_recipe_dict_by_id("private:v1")["name"] == "Da Privada"


def test_get_recipe_dict_by_id_unknown_raises(data_dirs):
    with pytest.raises(RecipeError, match="não encontrada"):
        data.get_recipe_dict_by_id("public:nao-existe")


# ---- create_recipe -------------------------------------------------------------


def test_create_recipe_generates_slug_id(data_dirs, bridge_config):
    global_id = data.create_recipe("public", _recipe_dict("IPA Tropical!"), bridge_config)
    assert global_id == "public:ipa-tropical"

    entries = data.read_entities("public", "receita")
    assert len(entries) == 1
    assert entries[0]["id"] == "ipa-tropical"


def test_create_recipe_handles_slug_collision(data_dirs, bridge_config):
    id1 = data.create_recipe("public", _recipe_dict("Pilsen"), bridge_config)
    id2 = data.create_recipe("public", _recipe_dict("Pilsen"), bridge_config)
    assert id1 == "public:pilsen"
    assert id2 == "public:pilsen-2"


def test_create_recipe_invalid_raises_and_does_not_write(data_dirs, bridge_config):
    bad_recipe = _recipe_dict()
    bad_recipe["vessels"][0]["heater_device_id"] = "nao_existe"
    with pytest.raises(RecipeError):
        data.create_recipe("public", bad_recipe, bridge_config)
    assert data.read_entities("public", "receita") == []


def test_create_recipe_rejects_invalid_source(data_dirs, bridge_config):
    with pytest.raises(RecipeError, match="source inválido"):
        data.create_recipe("outro", _recipe_dict(), bridge_config)


# ---- update_recipe --------------------------------------------------------------


def test_update_recipe_replaces_content(data_dirs, bridge_config):
    global_id = data.create_recipe("private", _recipe_dict("Original"), bridge_config)
    data.update_recipe(global_id, _recipe_dict("Atualizada"), bridge_config)

    recipe = data.load_recipe_by_id(global_id, bridge_config)
    assert recipe.name == "Atualizada"


def test_update_recipe_base_raises(data_dirs, bridge_config):
    data.BASE_RECIPE_PATH.write_text(yaml.safe_dump(_recipe_dict("Base"), allow_unicode=True), encoding="utf-8")
    with pytest.raises(RecipeError, match="não é editável"):
        data.update_recipe(data.BASE_RECIPE_ID, _recipe_dict("Tentativa"), bridge_config)


def test_update_recipe_unknown_raises(data_dirs, bridge_config):
    with pytest.raises(RecipeError, match="não encontrada"):
        data.update_recipe("public:nao-existe", _recipe_dict(), bridge_config)


def test_update_recipe_invalid_raises_and_does_not_overwrite(data_dirs, bridge_config):
    global_id = data.create_recipe("public", _recipe_dict("Original"), bridge_config)
    bad_recipe = _recipe_dict("Ruim")
    bad_recipe["vessels"][0]["heater_device_id"] = "nao_existe"

    with pytest.raises(RecipeError):
        data.update_recipe(global_id, bad_recipe, bridge_config)

    recipe = data.load_recipe_by_id(global_id, bridge_config)
    assert recipe.name == "Original"  # não sobrescreveu


# ---- delete_recipe --------------------------------------------------------------


def test_delete_recipe_removes_entry(data_dirs, bridge_config):
    global_id = data.create_recipe("public", _recipe_dict("Descartável"), bridge_config)
    data.delete_recipe(global_id)
    assert data.read_entities("public", "receita") == []


def test_delete_recipe_base_raises(data_dirs):
    data.BASE_RECIPE_PATH.write_text(yaml.safe_dump(_recipe_dict("Base"), allow_unicode=True), encoding="utf-8")
    with pytest.raises(RecipeError, match="não pode ser removida"):
        data.delete_recipe(data.BASE_RECIPE_ID)


def test_delete_recipe_unknown_raises(data_dirs):
    with pytest.raises(RecipeError, match="não encontrada"):
        data.delete_recipe("public:nao-existe")


def test_delete_active_recipe_clears_pointer(data_dirs, bridge_config):
    global_id = data.create_recipe("private", _recipe_dict("Vai Sumir"), bridge_config)
    data.set_active_recipe_id(global_id)
    assert data.get_active_recipe_id() == global_id

    data.delete_recipe(global_id)

    assert data.get_active_recipe_id() is None


def test_delete_recipe_does_not_clear_pointer_of_other_recipe(data_dirs, bridge_config):
    id1 = data.create_recipe("private", _recipe_dict("Fica"), bridge_config)
    id2 = data.create_recipe("private", _recipe_dict("Vai Sumir"), bridge_config)
    data.set_active_recipe_id(id1)

    data.delete_recipe(id2)

    assert data.get_active_recipe_id() == id1
