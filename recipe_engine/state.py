"""
Estado de execução de uma receita — persistido em JSON a cada mudança,
pra sobreviver a um restart do processo (decisão registrada: ao cair,
aplica failsafe em tudo e fica parado esperando confirmação manual,
nunca retoma sozinho).

Esta classe é só dados + serialização — toda a lógica de transição vive
em recipe_engine/engine.py.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

# Status possíveis:
# - idle: nenhuma receita rodando.
# - ramping: subindo até target_temp da etapa atual.
# - holding: patamar — tempo só conta depois que target_temp foi atingido.
# - paused_after_crash: processo caiu/reiniciou no meio de ramping/holding;
#   failsafe já foi aplicado; aguardando confirmação manual pra retomar.
# - finished: todas as etapas concluídas.
# - aborted: usuário cancelou manualmente.
_VALID_STATUSES = {"idle", "ramping", "holding", "paused_after_crash", "finished", "aborted"}


@dataclass
class RecipeState:
    recipe_name: Optional[str] = None
    status: str = "idle"
    step_index: int = 0
    step_started_at: Optional[float] = None
    hold_started_at: Optional[float] = None
    hold_elapsed_seconds_at_pause: float = 0.0
    paused_from_status: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"status inválido '{self.status}', esperado um de {sorted(_VALID_STATUSES)}.")

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
