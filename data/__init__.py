"""SQLite recipe repository facade (public/private IDs remain compatible).

No YAML/JSON file access. Legacy conversion is exclusively in
storage.legacy_import, never in the runtime or frontend.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata

from config import BridgeConfig
from recipe_engine.models import Recipe, RecipeError
from storage import store_router as store
from storage.migrate import StorageError

logger = logging.getLogger("tesseract_bridge.data")
BASE_RECIPE_ID = "public:base"
RECIPE_ENTITY = "receita"
_VALID_SOURCES = ("public", "private")


class DataStoreError(RuntimeError):
    pass


def read_entities(source, entity):
    if source not in _VALID_SOURCES or entity != RECIPE_ENTITY:
        raise ValueError("Tipo ou fonte de entidade inválida.")
    return [{"id": row["id"].split(":", 1)[1], "recipe": json.loads(row["recipe_json"])}
            for row in store.list_recipe_rows()
            if row["source"] == source and row["id"] != BASE_RECIPE_ID]


def write_entities(source, entity, entries):
    """Compatibility API: a single SQLite transaction, never rewriting files."""
    if source not in _VALID_SOURCES or entity != RECIPE_ENTITY:
        raise ValueError("Tipo ou fonte de entidade inválida.")
    if not isinstance(entries, list):
        raise ValueError("Registros precisam ser uma lista.")
    ids = set()
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("recipe"), dict):
            raise ValueError("Registro de receita inválido.")
        if item["id"] in ids:
            raise ValueError("ID de receita duplicado.")
        ids.add(item["id"])
    store.replace_entities(source, entries)

def list_recipes(bridge_config=None):
    entries = []
    for row in store.list_recipe_rows():
        recipe = json.loads(row["recipe_json"])
        entry = {"id": row["id"], "source": row["source"],
                 "editable": bool(row["editable"]), "name": recipe.get("name"),
                 "valid": True, "error": None}
        if bridge_config is not None:
            try:
                loaded = Recipe.from_dict(recipe)
                loaded.validate(bridge_config)
                entry["name"] = loaded.name
            except (RecipeError, ValueError, TypeError) as exc:
                entry.update(valid=False, error=str(exc))
        entries.append(entry)
    return entries


def get_recipe_dict_by_id(recipe_id):
    row = store.recipe_row(recipe_id)
    if row is None:
        raise RecipeError(f"Receita '{recipe_id}' não encontrada no SQLite.")
    return json.loads(row["recipe_json"])


def load_recipe_by_id(recipe_id, bridge_config):
    recipe = Recipe.from_dict(get_recipe_dict_by_id(recipe_id))
    recipe.validate(bridge_config)
    return recipe


def get_active_recipe_id():
    return store.get_active_recipe()


def set_active_recipe_id(recipe_id):
    store.set_active_recipe(recipe_id)


def get_effective_active_recipe_id():
    current = get_active_recipe_id()
    if current:
        return current
    return BASE_RECIPE_ID if store.recipe_row(BASE_RECIPE_ID) else None


def _slugify(value):
    normal = unicodedata.normalize("NFKD", value)
    ascii_value = normal.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-") or "receita"


def create_recipe(source, recipe_dict, bridge_config):
    if source not in _VALID_SOURCES:
        raise RecipeError(f"Fonte inválida: {source}")
    recipe = Recipe.from_dict(recipe_dict)
    recipe.validate(bridge_config)
    existing = {r["id"] for r in store.list_recipe_rows()}
    base = _slugify(recipe.name)
    slug = base
    attempt = 2
    while source + ":" + slug in existing:
        slug = f"{base}-{attempt}"
        attempt += 1
    recipe_id = source + ":" + slug
    store.create_recipe(recipe_id, source, recipe_dict)
    return recipe_id


def update_recipe(recipe_id, recipe_dict, bridge_config):
    Recipe.from_dict(recipe_dict).validate(bridge_config)
    if recipe_id == BASE_RECIPE_ID:
        raise RecipeError("Receita-base protegida. Duplique para editar.")
    try:
        store.update_recipe(recipe_id, recipe_dict)
    except StorageError as exc:
        raise RecipeError(str(exc)) from exc


def delete_recipe(recipe_id):
    try:
        store.delete_recipe(recipe_id)
    except StorageError as exc:
        raise RecipeError(str(exc)) from exc


def load_active_recipe(bridge_config):
    active_id = get_active_recipe_id()
    if active_id:
        # A bad active recipe must NOT silently fall back to a different one.
        return load_recipe_by_id(active_id, bridge_config)
    if store.recipe_row(BASE_RECIPE_ID):
        return load_recipe_by_id(BASE_RECIPE_ID, bridge_config)
    return None
