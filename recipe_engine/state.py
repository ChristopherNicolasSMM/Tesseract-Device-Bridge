"""
Estado de execucao de uma receita - persistido em JSON a cada mudanca,
pra sobreviver a um restart do processo (decisao registrada: ao cair,
aplica failsafe em tudo e fica parado esperando confirmacao manual,
nunca retoma sozinho).

Esta classe e so dados + serializacao - toda a logica de transicao vive
em recipe_engine/engine.py.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

# Status possiveis:
# - idle: nenhuma receita rodando.
# - ramping: subindo ate target_temp da etapa atual.
# - holding: patamar - tempo so conta depois que target_temp foi atingido.
# - paused_after_crash: processo caiu/reiniciou no meio de ramping/holding;
#   failsafe ja foi aplicado; aguardando confirmacao manual pra retomar.
# - paused_manual: usuario pausou deliberadamente pelo painel (mesmo
#   efeito de paused_after_crash - failsafe aplicado, espera resume() -
#   mas nao foi um crash, e uma acao explicita).
# - finished: todas as etapas concluidas.
# - aborted: usuario cancelou manualmente.
_VALID_STATUSES = {
    "idle", "ramping", "holding",
    "paused_after_crash", "paused_manual",
    "finished", "aborted",
}

# Status em que resume() é válido (saem de uma pausa, voltam a rodar).
PAUSED_STATUSES = {"paused_after_crash", "paused_manual"}

# Status em que o motor está ativamente avançando (tick() faz algo).
ACTIVE_STATUSES = {"ramping", "holding"}

# Tipos de alarme possíveis.
ALARM_TYPE_VESSEL_START = "vessel_start"
ALARM_TYPE_VESSEL_END = "vessel_end"
ALARM_TYPE_HOP_ADDITION = "hop_addition"


@dataclass
class AlarmEvent:
    id: int
    type: str
    label: str
    fired_at: float


@dataclass
class RecipeState:
    recipe_name: Optional[str] = None
    status: str = "idle"
    step_index: int = 0
    step_started_at: Optional[float] = None
    hold_started_at: Optional[float] = None
    hold_elapsed_seconds_at_pause: float = 0.0
    paused_from_status: Optional[str] = None
    # Marca o inicio da execucao da receita inteira (setado uma vez em
    # fresh(), preservado por pause/resume/skip) - usado para calcular
    # tempo total decorrido. None enquanto idle.
    recipe_started_at: Optional[float] = None
    # Snapshot do tempo total decorrido, congelado no instante em que a
    # receita termina ou e cancelada (depois disso recipe_started_at
    # nao serve mais pra calcular "decorrido ate agora", porque "agora"
    # ja nao tem relacao com a execucao que parou).
    total_elapsed_seconds_frozen: Optional[float] = None
    # Alarmes disparados e ainda nao confirmados pelo usuario (som +
    # popup no painel). Uma vez confirmado (ack), sai desta lista -
    # nao mantemos historico aqui, so o que esta pendente agora.
    pending_alarms: List[AlarmEvent] = field(default_factory=list)
    # Contador monotonico pra gerar id unico de alarme (nunca reusado,
    # mesmo apos ack - evita qualquer ambiguidade de id no painel).
    next_alarm_id: int = 1
    # Chaves "step_index:alarm_index" dos hop_alarms ja disparados na
    # execucao atual da etapa - zerado sempre que a etapa reinicia
    # (avanca, volta, ou e resetada), pra permitir disparar de novo se
    # a mesma etapa for reexecutada.
    fired_hop_alarm_keys: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"status invalido '{self.status}', esperado um de {sorted(_VALID_STATUSES)}.")
        # pending_alarms pode chegar como lista de dicts (vindo de JSON
        # carregado via load()) - normaliza pra AlarmEvent.
        normalized = []
        for a in self.pending_alarms:
            normalized.append(a if isinstance(a, AlarmEvent) else AlarmEvent(**a))
        self.pending_alarms = normalized

    def save(self, path: str | Path) -> None:
        file_path = Path(path)
        file_path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "RecipeState":
        file_path = Path(path)
        if not file_path.exists():
            return cls()
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        return cls(**raw)

    @classmethod
    def fresh(cls, recipe_name: str) -> "RecipeState":
        return cls(recipe_name=recipe_name, status="ramping", step_index=0)
