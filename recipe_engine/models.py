"""
Modelo de receita — vasilhas (cada uma com seu PID e seus devices) e
etapas (rampa até uma temperatura alvo + patamar por um tempo).

Carregado de um arquivo YAML separado do devices.yml (uma receita não é
configuração de hardware, é configuração de processo — pode trocar de
receita sem reiniciar o bridge nem tocar no devices.yml).

Validação cruzada com BridgeConfig: toda referência a device_id (heater,
sensor, pump) precisa existir no devices.yml carregado — falha cedo,
com mensagem clara, em vez de estourar erro só quando a receita começar
a rodar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml

from config import BridgeConfig
from recipe_engine.pid import PidGains


class RecipeError(ValueError):
    """Erro de validação de receita — mensagem explica o que está errado e onde."""


@dataclass
class VesselConfig:
    name: str
    heater_device_id: str
    sensor_device_id: str
    pid: PidGains
    window_seconds: float = 10.0

    @classmethod
    def from_dict(cls, name: str, raw: Dict[str, Any]) -> "VesselConfig":
        missing = [k for k in ("heater_device_id", "sensor_device_id", "pid") if k not in raw]
        if missing:
            raise RecipeError(f"vessel '{name}': campo(s) obrigatório(s) ausente(s) {missing}.")

        pid_raw = raw["pid"]
        pid_missing = [k for k in ("kp", "ki", "kd") if k not in pid_raw]
        if pid_missing:
            raise RecipeError(f"vessel '{name}': pid sem campo(s) {pid_missing}.")

        return cls(
            name=name,
            heater_device_id=raw["heater_device_id"],
            sensor_device_id=raw["sensor_device_id"],
            pid=PidGains(kp=float(pid_raw["kp"]), ki=float(pid_raw["ki"]), kd=float(pid_raw["kd"])),
            window_seconds=float(raw.get("window_seconds", 10.0)),
        )

    def validate_against(self, bridge_config: BridgeConfig) -> None:
        for device_id, role_label in (
            (self.heater_device_id, "heater_device_id"),
            (self.sensor_device_id, "sensor_device_id"),
        ):
            try:
                bridge_config.get_device(device_id)
            except KeyError:
                raise RecipeError(
                    f"vessel '{self.name}': {role_label} '{device_id}' não existe no devices.yml."
                )
        if self.window_seconds <= 0:
            raise RecipeError(f"vessel '{self.name}': window_seconds deve ser > 0.")


@dataclass
class RecipeStep:
    vessel: str
    target_temp: float
    hold_minutes: float
    pumps: List[str] = field(default_factory=list)
    label: str | None = None

    @classmethod
    def from_dict(cls, index: int, raw: Dict[str, Any]) -> "RecipeStep":
        missing = [k for k in ("vessel", "target_temp", "hold_minutes") if k not in raw]
        if missing:
            raise RecipeError(f"step #{index}: campo(s) obrigatório(s) ausente(s) {missing}.")
        return cls(
            vessel=raw["vessel"],
            target_temp=float(raw["target_temp"]),
            hold_minutes=float(raw["hold_minutes"]),
            pumps=list(raw.get("pumps", [])),
            label=raw.get("label"),
        )

    def validate_against(self, vessels: Dict[str, VesselConfig], bridge_config: BridgeConfig, index: int) -> None:
        if self.vessel not in vessels:
            raise RecipeError(f"step #{index}: vessel '{self.vessel}' não declarada em 'vessels'.")
        if self.hold_minutes < 0:
            raise RecipeError(f"step #{index}: hold_minutes não pode ser negativo.")
        for pump_id in self.pumps:
            try:
                bridge_config.get_device(pump_id)
            except KeyError:
                raise RecipeError(f"step #{index}: pump '{pump_id}' não existe no devices.yml.")


@dataclass
class Recipe:
    name: str
    vessels: Dict[str, VesselConfig]
    steps: List[RecipeStep]

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Recipe":
        if "name" not in raw:
            raise RecipeError("receita sem campo 'name'.")
        vessels_raw = raw.get("vessels", {})
        if not vessels_raw:
            raise RecipeError("receita precisa declarar ao menos uma vessel em 'vessels'.")
        steps_raw = raw.get("steps", [])
        if not steps_raw:
            raise RecipeError("receita precisa declarar ao menos um step em 'steps'.")

        vessels = {name: VesselConfig.from_dict(name, v) for name, v in vessels_raw.items()}
        steps = [RecipeStep.from_dict(i, s) for i, s in enumerate(steps_raw)]

        return cls(name=raw["name"], vessels=vessels, steps=steps)

    @classmethod
    def load(cls, path: str | Path, bridge_config: BridgeConfig) -> "Recipe":
        file_path = Path(path)
        if not file_path.exists():
            raise RecipeError(f"Arquivo de receita não encontrado: {file_path}")
        with file_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        recipe = cls.from_dict(raw)
        recipe.validate(bridge_config)
        return recipe

    def validate(self, bridge_config: BridgeConfig) -> None:
        for vessel in self.vessels.values():
            vessel.validate_against(bridge_config)
        for index, step in enumerate(self.steps):
            step.validate_against(self.vessels, bridge_config, index)

    def step_count(self) -> int:
        return len(self.steps)
