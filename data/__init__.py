"""
Armazenamento de entidades cadastráveis pelo painel — sem banco de
dados, tudo em arquivo, seguindo a mesma filosofia de `devices.yml`/
`recipe.yml` (YAML/JSON legível, editável na mão se precisar).

Convenção "entidade": cada tipo de dado cadastrável (receita é a
primeira; outras podem vir depois) mora em **um arquivo JSON por
pasta**, contendo uma **lista** de registros — `data/publico/receita.json`
tem todas as receitas públicas, `data/privado/receita.json` tem todas
as privadas. Não é "um arquivo por receita".

Público vs. privado — a única diferença é versionamento:
    data/publico/   -> vai commitado no repositório (compartilhado)
    data/privado/   -> gitignored (`.gitignore`: `data/privado/*`),
                       fica só na máquina de quem cadastrou

`data/publico/receita_base.yaml` é um caso especial: é a migração da
receita que já existia como `recipe.yml` na raiz do projeto antes desta
pasta existir. Fica em YAML (não em `receita.json`) e **não é editável
pelo sistema de cadastro** — mas é selecionável normalmente pra
brassar, como qualquer outra receita. Isso existe pra sempre ter algo
funcional mesmo se `receita.json` estiver vazio em publico/privado.

Troca de receita ativa exige reiniciar o processo (decisão registrada
— `Recipe`/`RecipeEngine` são carregados uma única vez no boot,
`run_bridge.py`). `set_active_recipe_id()` só grava a intenção pro
próximo boot, não troca nada em memória agora.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from config import BridgeConfig
from recipe_engine.models import Recipe, RecipeError

logger = logging.getLogger("tesseract_bridge.data")

DATA_DIR = Path(__file__).parent
PUBLIC_DIR = DATA_DIR / "publico"
PRIVATE_DIR = DATA_DIR / "privado"

BASE_RECIPE_PATH = PUBLIC_DIR / "receita_base.yaml"
ACTIVE_RECIPE_POINTER_PATH = DATA_DIR / "active_recipe.txt"

# Fallback de última instância — comportamento de antes desta pasta
# existir. Só é alcançado se nem o ponteiro de receita ativa nem
# receita_base.yaml resolverem em nada (ex.: instalação nova que ainda
# não migrou). Path relativo à raiz do projeto (cwd do processo).
LEGACY_RECIPE_PATH = Path("recipe.yml")

RECIPE_ENTITY = "receita"
BASE_RECIPE_ID = "publico:base"

_VALID_SOURCES = ("publico", "privado")


class DataStoreError(RuntimeError):
    """Arquivo de entidade malformado (JSON inválido, raiz não é lista, etc.)."""


# ---- I/O genérico de entidade (source + tipo -> lista de registros) -------


def _source_dir(source: str) -> Path:
    if source not in _VALID_SOURCES:
        raise ValueError(f"source inválido: '{source}' (esperado {_VALID_SOURCES}).")
    return PUBLIC_DIR if source == "publico" else PRIVATE_DIR


def _entity_path(source: str, entity: str) -> Path:
    return _source_dir(source) / f"{entity}.json"


def read_entities(source: str, entity: str) -> List[Dict[str, Any]]:
    """
    Lê todos os registros de um tipo de entidade numa fonte
    (publico/privado). Arquivo ausente não é erro — devolve lista
    vazia (é o estado normal antes de qualquer cadastro).
    """
    path = _entity_path(source, entity)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DataStoreError(f"'{path}' não é um JSON válido: {exc}") from exc
    if not isinstance(raw, list):
        raise DataStoreError(f"'{path}' precisa conter uma lista de registros no nível raiz.")
    return raw


def write_entities(source: str, entity: str, entries: List[Dict[str, Any]]) -> None:
    """Grava a lista completa de registros de um tipo de entidade (sobrescreve o arquivo)."""
    path = _entity_path(source, entity)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---- Receitas (primeira entidade concreta) --------------------------------


def list_recipes(bridge_config: Optional[BridgeConfig] = None) -> List[Dict[str, Any]]:
    """
    Lista todas as receitas disponíveis: receita_base (se existir) +
    entradas de data/publico/receita.json + data/privado/receita.json.

    Se `bridge_config` for passado, cada receita é validada de verdade
    (Recipe.from_dict + validate) e `valid`/`error` refletem o
    resultado — sem ele, só lê o campo `name` sem validar contra
    devices.yml (mais rápido, útil pra listagem simples).
    """
    results: List[Dict[str, Any]] = []

    if BASE_RECIPE_PATH.exists():
        entry: Dict[str, Any] = {
            "id": BASE_RECIPE_ID,
            "source": "publico",
            "editable": False,
            "name": None,
            "valid": True,
            "error": None,
        }
        try:
            if bridge_config is not None:
                recipe = Recipe.load(BASE_RECIPE_PATH, bridge_config)
                entry["name"] = recipe.name
            else:
                raw = yaml.safe_load(BASE_RECIPE_PATH.read_text(encoding="utf-8")) or {}
                entry["name"] = raw.get("name")
        except (RecipeError, yaml.YAMLError) as exc:
            entry["valid"] = False
            entry["error"] = str(exc)
        results.append(entry)

    for source in _VALID_SOURCES:
        try:
            raw_entries = read_entities(source, RECIPE_ENTITY)
        except DataStoreError as exc:
            logger.error("Falha ao ler receitas de '%s': %s", source, exc)
            continue

        for raw_entry in raw_entries:
            raw_id = raw_entry.get("id")
            if not raw_id:
                logger.warning("Registro sem 'id' em data/%s/receita.json — ignorado.", source)
                continue

            recipe_dict = raw_entry.get("recipe", {})
            entry = {
                "id": f"{source}:{raw_id}",
                "source": source,
                "editable": True,
                "name": recipe_dict.get("name"),
                "valid": True,
                "error": None,
            }
            if bridge_config is not None:
                try:
                    recipe = Recipe.from_dict(recipe_dict)
                    recipe.validate(bridge_config)
                    entry["name"] = recipe.name
                except RecipeError as exc:
                    entry["valid"] = False
                    entry["error"] = str(exc)
            results.append(entry)

    return results


def load_recipe_by_id(recipe_id: str, bridge_config: BridgeConfig) -> Recipe:
    """
    Carrega e valida uma receita pelo id global ("publico:base",
    "privado:<id>", etc. — ver list_recipes). Levanta RecipeError com
    mensagem clara se o id não existir ou a receita for inválida.
    """
    if recipe_id == BASE_RECIPE_ID:
        return Recipe.load(BASE_RECIPE_PATH, bridge_config)

    if ":" not in recipe_id:
        raise RecipeError(
            f"id de receita inválido: '{recipe_id}' (esperado 'publico:<id>' ou 'privado:<id>')."
        )
    source, raw_id = recipe_id.split(":", 1)
    if source not in _VALID_SOURCES:
        raise RecipeError(f"id de receita inválido: '{recipe_id}' (source desconhecido).")

    entries = read_entities(source, RECIPE_ENTITY)
    entry = next((e for e in entries if e.get("id") == raw_id), None)
    if entry is None:
        raise RecipeError(f"Receita '{recipe_id}' não encontrada em data/{source}/receita.json.")

    recipe = Recipe.from_dict(entry.get("recipe", {}))
    recipe.validate(bridge_config)
    return recipe


def get_active_recipe_id() -> Optional[str]:
    if not ACTIVE_RECIPE_POINTER_PATH.exists():
        return None
    value = ACTIVE_RECIPE_POINTER_PATH.read_text(encoding="utf-8").strip()
    return value or None


def set_active_recipe_id(recipe_id: str) -> None:
    """
    Marca qual receita fica ativa no PRÓXIMO boot do processo — não
    troca a receita rodando agora (decisão registrada: troca de receita
    exige restart, não é "a quente"). Não valida o id aqui de propósito
    (quem chama — a rota da API — já valida contra list_recipes()
    antes); mantém esta função simples e sem depender de BridgeConfig.
    """
    ACTIVE_RECIPE_POINTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_RECIPE_POINTER_PATH.write_text(recipe_id.strip() + "\n", encoding="utf-8")


def load_active_recipe(bridge_config: BridgeConfig) -> Optional[Recipe]:
    """
    Resolve e carrega a receita ativa pro boot do bridge, nesta ordem:

      1. Ponteiro salvo (active_recipe.txt) — se apontar pra uma receita
         que existe e é válida, usa ela. Se apontar pra algo que sumiu
         ou ficou inválido, loga aviso e cai pro próximo nível (não
         derruba o motor de receita por causa de um ponteiro velho).
      2. data/publico/receita_base.yaml, se existir.
      3. recipe.yml na raiz do projeto — comportamento de antes desta
         pasta existir, garante zero quebra pra quem não migrou ainda.
      4. None — motor de receita fica desabilitado (mesmo comportamento
         de sempre quando não há nenhuma receita configurada).

    Erros de validação em receita_base.yaml ou no recipe.yml legado
    (níveis 2 e 3) SE PROPAGAM (RecipeError) — igual ao comportamento
    anterior, quem chama decide o que fazer (run_bridge.py loga e
    desabilita o motor).
    """
    active_id = get_active_recipe_id()
    if active_id is not None:
        try:
            return load_recipe_by_id(active_id, bridge_config)
        except RecipeError as exc:
            logger.warning(
                "Receita ativa '%s' não pôde ser carregada (%s) — usando fallback.",
                active_id, exc,
            )

    if BASE_RECIPE_PATH.exists():
        return Recipe.load(BASE_RECIPE_PATH, bridge_config)

    if LEGACY_RECIPE_PATH.exists():
        return Recipe.load(LEGACY_RECIPE_PATH, bridge_config)

    return None
