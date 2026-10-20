"""Leased on/off heat demand. External flame cutoff is an independent hardware prerequisite.

No GPIO or network here. All deadlines use monotonic time; UTC only rejects delayed
commands. No arming or recovery is persisted across process restarts.
"""
import math
from datetime import datetime, timezone
from uuid import uuid4

DEFAULTS = {"demand_threshold": 80.0, "minimum_gap": 2.0,
            "minimum_seconds": 10.0, "cooldown_seconds": 30.0}
LEASE_SECONDS = 10.0


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Número fora do limite.")
    return float(value)


def settings(value):
    if not isinstance(value, dict):
        raise ValueError("Limites obrigatórios.")
    return {key: number(value.get(key, default), *limits) for (key, default), limits in zip(DEFAULTS.items(),
        ((10, 100), (1, 20), (1, 120), (10, 300)))}


class SourceControl:
    def __init__(self, participation):
        self.participation = participation
        self.boot_id = str(uuid4())
        self.arm_token = str(uuid4())
        self.lease_id = None
        self.sequence = 0
        self.deadline = 0.0
        self.target = None
        self.limits = dict(DEFAULTS)
        self.output_on = False
        self.reason = "Desabilitado; habilitação explícita necessária"
        self.since = None
        self.last_off = None

    def stop(self, reason):
        self.lease_id = None
        self.output_on = False
        self.since = None
        self.arm_token = str(uuid4())
        self.reason = reason

    def command(self, value, now, utc_now=None):
        if not isinstance(value, dict):
            raise ValueError("Comando estruturado obrigatório.")
        action = value.get("action")
        if action == "stop":
            self.stop("Parada solicitada pelo operador")
            return
        if value.get("version") != 1 or type(value.get("version")) is not int or value.get("boot_id") != self.boot_id:
            raise ValueError("Versão/boot incompatível.")
        issued = datetime.fromisoformat(value.get("issued_at", ""))
        utc_now = utc_now or datetime.now(timezone.utc)
        if issued.tzinfo is None or not -2 <= (utc_now-issued).total_seconds() <= 5:
            raise ValueError("Comando antigo ou sem fuso.")
        sequence = value.get("sequence")
        lease = value.get("lease_id")
        if type(sequence) is not int or sequence < 1 or not isinstance(lease, str) or not 1 <= len(lease) <= 64:
            raise ValueError("Autorização/sequência inválida.")
        if self.lease_id and now >= self.deadline:
            self.stop("Autorização expirada; habilite novamente")
        if action == "arm":
            if self.lease_id or value.get("arm_token") != self.arm_token:
                raise ValueError("Habilitação inválida ou já ativa.")
            target = number(value.get("target"), 1, 110)
            limits = settings(value.get("limits", {}))
            self.target, self.limits = target, limits
            self.lease_id = lease
            self.since = None
            # No heat until qualifying time AND the initial off dwell have elapsed.
            self.last_off = now
            self.arm_token = str(uuid4())
        elif action == "renew":
            if self.lease_id != lease or sequence <= self.sequence or value.get("target") != self.target:
                raise ValueError("Renovação sem habilitação, repetida ou alvo alterado.")
        else:
            raise ValueError("Ação inválida.")
        self.sequence = sequence
        self.deadline = now + LEASE_SECONDS
        self.reason = "Habilitado; aguardando condição local"

    def tick(self, now, temperature, demand=None, controller_target=None, controller_ok=True):
        was_on = self.output_on
        if not self.lease_id:
            self.output_on = False
            return False
        if now >= self.deadline:
            self.stop("Autorização expirada; habilite novamente")
            return False
        try:
            temperature = number(temperature, -55, 150)
            if temperature >= self.target + 3:
                self.stop("Sobretemperatura; habilite novamente")
                return False
            if self.participation == "auxiliary":
                demand = number(demand, 0, 100)
                if not controller_ok or controller_target is None or abs(number(controller_target, 1, 110)-self.target) > 0.1:
                    raise ValueError("Receita/controlador incompatível.")
        except ValueError:
            self.stop("Leitura/controlador inválido; habilite novamente")
            return False
        gap = self.target-temperature
        # OFF bypasses all dwell times. No minimum-ON delay can hold gas near target.
        hold = gap > 0.5 and (self.participation == "primary" or demand > self.limits["demand_threshold"]-10)
        enter = gap >= self.limits["minimum_gap"] and (self.participation == "primary" or demand >= self.limits["demand_threshold"])
        if was_on:
            self.output_on = hold
        elif enter:
            if self.since is None:
                self.since = now
            self.output_on = now-self.since >= self.limits["minimum_seconds"] and now-self.last_off >= self.limits["cooldown_seconds"]
        else:
            self.since = None
        if was_on and not self.output_on:
            self.last_off = now
            self.since = None
        self.reason = "Demanda de aquecimento ON" if self.output_on else "Aguardando distância do alvo, demanda ou temporização"
        return self.output_on

    def telemetry(self):
        return {"version": 1, "boot_id": self.boot_id, "arm_token": self.arm_token,
                "participation": self.participation, "armed": self.lease_id is not None,
                "lease_id": self.lease_id, "output_on": self.output_on, "target": self.target,
                "reason": str(self.reason)[:1000], "external_protection": "independent_hardware",
                "limits": dict(self.limits)}
