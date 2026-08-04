"""
Armazenamento de entidades cadastráveis pelo painel — sem banco de
dados, tudo em arquivo, seguindo a mesma filosofia de `devices.yml`/
`recipe.yml` (YAML/JSON legível, editável na mão se precisar).

Convenção "entidade": cada tipo de dado cadastrável (receita é a
primeira; outras podem vir depois) mora em **um arquivo JSON por
pasta**, contendo uma **lista** de registros — `data/public/receita.json`
tem todas as receitas públicas, `data/private/receita.json` tem todas
as privadas. Não é "um arquivo por receita".

Público vs. private — a única diferença é versionamento:
    data/public/   -> vai commitado no repositório (compartilhado)
    data/private/   -> gitignored (`.gitignore`: `data/private/*`),
                       fica só na máquina de quem cadastrou

`data/public/receita_base.yaml` é um caso especial: é a migração da
receita que já existia como `recipe.yml` na raiz do projeto antes desta
pasta existir. Fica em YAML (não em `receita.json`) e **não é editável
pelo sistema de cadastro** — mas é selecionável normalmente pra
brassar, como qualquer outra receita. Isso existe pra sempre ter algo
funcional mesmo se `receita.json` estiver vazio em public/private.

Troca de receita ativa exige reiniciar o processo (decisão registrada
— `Recipe`/`RecipeEngine` são carregados uma única vez no boot,
`run_bridge.py`). `set_active_recipe_id()` só grava a intenção pro
próximo boot, não troca nada em memória agora.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from config import BridgeConfig
from recipe_engine.models import Recipe, RecipeError

logger = logging.getLogger("tesseract_bridge.data")

DATA_DIR = Path(__file__).parent
PUBLIC_DIR = DATA_DIR / "public"
PRIVATE_DIR = DATA_DIR / "private"

BASE_RECIPE_PATH = PUBLIC_DIR / "receita_base.yaml"
ACTIVE_RECIPE_POINTER_PATH = DATA_DIR / "active_recipe.txt"

# Fallback de última instância — comportamento de antes desta pasta
# existir. Só é alcançado se nem o ponteiro de receita ativa nem
# receita_base.yaml resolverem em nada (ex.: instalação nova que ainda
# não migrou). Path relativo à raiz do projeto (cwd do processo).
LEGACY_RECIPE_PATH = Path("recipe.yml")

RECIPE_ENTITY = "receita"
BASE_RECIPE_ID = "public:base"

_VALID_SOURCES = ("public", "private")


class DataStoreError(RuntimeError):
    """Arquivo de entidade malformado (JSON inválido, raiz não é lista, etc.)."""


# ---- I/O genérico de entidade (source + tipo -> lista de registros) -------


def _source_dir(source: str) -> Path:
    if source not in _VALID_SOURCES:
        raise ValueError(f"source inválido: '{source}' (esperado {_VALID_SOURCES}).")
    return PUBLIC_DIR if source == "public" else PRIVATE_DIR


def _entity_path(source: str, entity: str) -> Path:
    return _source_dir(source) / f"{entity}.json"


def read_entities(source: str, entity: str) -> List[Dict[str, Any]]:
    """
    Lê todos os registros de um tipo de entidade numa fonte
    (public/private). Arquivo ausente não é erro — devolve lista
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
    entradas de data/public/receita.json + data/private/receita.json.

    Se `bridge_config` for passado, cada receita é validada de verdade
    (Recipe.from_dict + validate) e `valid`/`error` refletem o
    resultado — sem ele, só lê o campo `name` sem validar contra
    devices.yml (mais rápido, útil pra listagem simples).
    """
    results: List[Dict[str, Any]] = []

    if BASE_RECIPE_PATH.exists():
        entry: Dict[str, Any] = {
            "id": BASE_RECIPE_ID,
            "source": "public",
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
    Carrega e valida uma receita pelo id global ("public:base",
    "private:<id>", etc. — ver list_recipes). Levanta RecipeError com
    mensagem clara se o id não existir ou a receita for inválida.
    """
    if recipe_id == BASE_RECIPE_ID:
        return Recipe.load(BASE_RECIPE_PATH, bridge_config)

    if ":" not in recipe_id:
        raise RecipeError(
            f"id de receita inválido: '{recipe_id}' (esperado 'public:<id>' ou 'private:<id>')."
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


def get_effective_active_recipe_id() -> Optional[str]:
    """
    Como load_active_recipe(), mas devolve só o id resolvido — sem
    carregar nem validar a receita. Usado pela UI pra saber qual
    receita vai rodar no próximo boot mesmo quando o ponteiro não foi
    definido explicitamente (cai pra receita_base por convenção, mesma
    ordem de load_active_recipe — exceto o fallback legado, que não
    tem id nesse sistema novo).
    """
    active_id = get_active_recipe_id()
    if active_id is not None:
        return active_id
    if BASE_RECIPE_PATH.exists():
        return BASE_RECIPE_ID
    return None


def get_recipe_dict_by_id(recipe_id: str) -> Dict[str, Any]:
    """
    Devolve o dict CRU (sem validar) de uma receita — usado pelo
    formulário de edição/duplicação, que precisa dos valores originais
    mesmo que a receita esteja momentaneamente inválida (ex.: um
    device foi removido do devices.yml depois que a receita foi salva
    — o usuário ainda precisa conseguir ver/corrigir o conteúdo).
    """
    if recipe_id == BASE_RECIPE_ID:
        if not BASE_RECIPE_PATH.exists():
            raise RecipeError(f"Receita '{recipe_id}' não encontrada (receita_base.yaml ausente).")
        return yaml.safe_load(BASE_RECIPE_PATH.read_text(encoding="utf-8")) or {}

    if ":" not in recipe_id:
        raise RecipeError(f"id de receita inválido: '{recipe_id}'.")
    source, raw_id = recipe_id.split(":", 1)
    if source not in _VALID_SOURCES:
        raise RecipeError(f"id de receita inválido: '{recipe_id}' (source desconhecido).")

    entries = read_entities(source, RECIPE_ENTITY)
    entry = next((e for e in entries if e.get("id") == raw_id), None)
    if entry is None:
        raise RecipeError(f"Receita '{recipe_id}' não encontrada em data/{source}/receita.json.")
    return entry.get("recipe", {})


def _slugify(name: str) -> str:
    """
    Converte um nome livre em slug seguro pra id (minúsculo, hífens,
    sem acento/espaço/símbolo) — "IPA Tropical!" -> "ipa-tropical".
    Nunca pede pro usuário inventar um id manualmente.
    """
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    return slug or "receita"


def _generate_unique_id(source: str, name: str) -> str:
    """Slug do nome, com sufixo numérico se colidir com um id já existente na mesma fonte."""
    base_slug = _slugify(name)
    existing_ids = {e.get("id") for e in read_entities(source, RECIPE_ENTITY)}
    candidate = base_slug
    counter = 2
    while candidate in existing_ids:
        candidate = f"{base_slug}-{counter}"
        counter += 1
    return candidate


def create_recipe(source: str, recipe_dict: Dict[str, Any], bridge_config: BridgeConfig) -> str:
    """
    Valida (Recipe.from_dict + validate) e grava uma receita nova em
    data/{source}/receita.json. Id gerado automaticamente a partir do
    nome (slug único dentro da fonte). Devolve o id GLOBAL
    ("source:id") da receita recém-criada.
    """
    if source not in _VALID_SOURCES:
        raise RecipeError(f"source inválido: '{source}' (esperado {_VALID_SOURCES}).")

    recipe = Recipe.from_dict(recipe_dict)
    recipe.validate(bridge_config)

    raw_id = _generate_unique_id(source, recipe.name)
    entries = read_entities(source, RECIPE_ENTITY)
    entries.append({"id": raw_id, "recipe": recipe_dict})
    write_entities(source, RECIPE_ENTITY, entries)

    return f"{source}:{raw_id}"


def update_recipe(recipe_id: str, recipe_dict: Dict[str, Any], bridge_config: BridgeConfig) -> None:
    """
    Substitui o conteúdo de uma receita já cadastrada — valida antes
    de gravar. receita_base nunca é editável por aqui.
    """
    if recipe_id == BASE_RECIPE_ID:
        raise RecipeError(
            f"'{BASE_RECIPE_ID}' não é editável pelo sistema de cadastro — "
            f"edite data/public/receita_base.yaml diretamente, ou duplique-a "
            f"pra criar uma cópia editável."
        )
    if ":" not in recipe_id:
        raise RecipeError(f"id de receita inválido: '{recipe_id}'.")
    source, raw_id = recipe_id.split(":", 1)
    if source not in _VALID_SOURCES:
        raise RecipeError(f"id de receita inválido: '{recipe_id}' (source desconhecido).")

    recipe = Recipe.from_dict(recipe_dict)
    recipe.validate(bridge_config)

    entries = read_entities(source, RECIPE_ENTITY)
    for entry in entries:
        if entry.get("id") == raw_id:
            entry["recipe"] = recipe_dict
            write_entities(source, RECIPE_ENTITY, entries)
            return
    raise RecipeError(f"Receita '{recipe_id}' não encontrada em data/{source}/receita.json.")


def delete_recipe(recipe_id: str) -> None:
    """
    Remove uma receita cadastrada. receita_base nunca é removível por
    aqui (é o fallback de segurança do sistema). Se a receita apagada
    era a marcada como ativa, limpa o ponteiro em vez de deixar órfão
    (load_active_recipe() já trata ponteiro órfão com segurança, mas é
    mais limpo já resolver aqui, na hora da remoção).
    """
    if recipe_id == BASE_RECIPE_ID:
        raise RecipeError(f"'{BASE_RECIPE_ID}' não pode ser removida pelo sistema de cadastro.")
    if ":" not in recipe_id:
        raise RecipeError(f"id de receita inválido: '{recipe_id}'.")
    source, raw_id = recipe_id.split(":", 1)
    if source not in _VALID_SOURCES:
        raise RecipeError(f"id de receita inválido: '{recipe_id}' (source desconhecido).")

    entries = read_entities(source, RECIPE_ENTITY)
    new_entries = [e for e in entries if e.get("id") != raw_id]
    if len(new_entries) == len(entries):
        raise RecipeError(f"Receita '{recipe_id}' não encontrada em data/{source}/receita.json.")
    write_entities(source, RECIPE_ENTITY, new_entries)

    if get_active_recipe_id() == recipe_id and ACTIVE_RECIPE_POINTER_PATH.exists():
        ACTIVE_RECIPE_POINTER_PATH.unlink()


def load_active_recipe(bridge_config: BridgeConfig) -> Optional[Recipe]:
    """
    Resolve e carrega a receita ativa pro boot do bridge, nesta ordem:

      1. Ponteiro salvo (active_recipe.txt) — se apontar pra uma receita
         que existe e é válida, usa ela. Se apontar pra algo que sumiu
         ou ficou inválido, loga aviso e cai pro próximo nível (não
         derruba o motor de receita por causa de um ponteiro velho).
      2. data/public/receita_base.yaml, se existir.
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
