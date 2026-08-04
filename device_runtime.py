"""
DeviceRuntime — conecta a configuração validada (BridgeConfig) a um
GPIOBackend concreto (simulado ou real).

Esta camada existe para não duplicar a lógica de "qual modo de pino usar
para qual combinação de role/subtype" tanto no painel web (Fase 3)
quanto no bridge MQTT (Fase 4) — os dois consomem DeviceRuntime, nunca
o GPIOBackend diretamente.

Não conhece MQTT. Não conhece HTTP. Só sabe traduzir DeviceConfig <->
GPIOBackend.

Controle de potência (duty-cycle / time-proportioning): DeviceRuntime é
o **dono único** do `TimeProportioningController` de cada atuador que
declarar `hardware.window_seconds` — nem o painel nem o RecipeEngine
escrevem direto no pino desses atuadores; ambos só *pedem* um duty
(`set_manual_duty` / `set_pid_duty`), e `tick_duty()` decide o valor
efetivo e escreve no GPIO. Um único caminho de escrita evita a disputa
entre "receita ativa" e "comando individual" que existia antes (ver
README, seção de limitações conhecidas).

Prioridade resolvida a cada tick, do mais forte pro mais fraco:
  1. Failsafe suspenso (apply_failsafe/apply_failsafe_external) — força
     0%, sempre, independente de qualquer override ou receita.
  2. Override manual **armado** (set_manual_enabled(id, True)) — vence a
     receita enquanto ativo. Definir o valor de % (set_manual_duty_percent)
     sozinho NÃO arma nada — só guarda o valor a ser aplicado quando/se
     o controle for ligado. Isso evita energizar o atuador sem intenção
     explícita só por ajustar o slider no painel.
  3. Duty da receita (set_pid_duty, do RecipeEngine) — só se não houver
     override armado nem failsafe suspenso.
  4. Repouso (0%) — nenhuma das anteriores presente.

Suspensão por failsafe só é revertida por `resume_all_suspended_overrides()`,
chamado exclusivamente por `RecipeEngine.resume()` (ação explícita do
usuário) — nunca por reconexão de rede (watchdog/status_handler), pra
não religar um atuador de risco sozinho.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from config import BridgeConfig, DeviceConfig
from gpio.base import GPIOBackend
from time_proportioning import TimeProportioningController

# Mapeia (role, subtype) -> mode aceito por GPIOBackend.setup().
# subtype=None cai no default de cada role (digital).
_MODE_MAP = {
    ("sensor", "temperature"): "input_analog",
    ("sensor", "analog"): "input_analog",
    ("sensor", "digital"): "input",
    ("sensor", None): "input",
    ("actuator", "pwm"): "pwm",
    ("actuator", "digital"): "output",
    ("actuator", None): "output",
}


class DeviceRuntimeError(RuntimeError):
    """Erro de uso do DeviceRuntime — ex.: operação incompatível com o role do device."""


@dataclass
class DeviceState:
    id: str
    name: str
    role: str
    subtype: str | None
    unit: str | None
    value: Any
    is_risk: bool
    failsafe_value: Any
    range: Dict[str, Any]
    gpio: int | None
    # Campos de controle de potência (time-proportioning) — None quando
    # o device não declara hardware.window_seconds (has_duty_control=False).
    window_seconds: float | None = None
    duty_percent: float | None = None  # duty EFETIVO (o que está realmente sendo aplicado)
    duty_source: str | None = None  # "manual" | "pid" | "failsafe_suspended" | "idle"
    duty_enabled: bool | None = None  # override manual armado? (interruptor mestre do painel)
    manual_duty_percent: float | None = None  # valor configurado pro override manual, mesmo desarmado
    # Override manual genérico (atuadores SEM controle de potência, ex.:
    # bombas) — None quando nunca foi definido explicitamente; caso
    # contrário, o último valor definido via set_manual_override().
    manual_override: Any | None = None


@dataclass
class DutyState:
    duty_percent: float
    source: str  # "manual" | "pid" | "failsafe_suspended" | "idle"
    window_seconds: float


def resolve_mode(role: str, subtype: str | None) -> str:
    mode = _MODE_MAP.get((role, subtype))
    if mode is None:
        # subtype desconhecido para o role: cai no default daquele role
        # em vez de falhar, já que novos subtypes (ex.: "humidity") podem
        # ser adicionados ao devices.yml sem exigir mudança de código aqui.
        mode = _MODE_MAP[(role, None)]
    return mode


class DeviceRuntime:
    """
    Liga cada DeviceConfig a um pino do GPIOBackend, e expõe operações
    de alto nível (list, read, set_actuator, inject_sensor) que tanto o
    painel quanto o bridge MQTT usam.
    """

    def __init__(self, config: BridgeConfig, backend: GPIOBackend) -> None:
        self._config = config
        self._backend = backend

        # Estado de controle de potência — um TPC por atuador com
        # hardware.window_seconds; populado em _setup_all().
        self._tpc: Dict[str, TimeProportioningController] = {}
        self._manual_duty: Dict[str, float] = {}
        # Interruptor mestre do override manual — SEPARADO do valor de %
        # (self._manual_duty). Ajustar o % sozinho nunca arma o atuador;
        # só quando o device_id está aqui, o valor de _manual_duty é
        # aplicado de fato (ver _resolve_effective_duty).
        self._manual_enabled: Set[str] = set()
        self._pid_duty: Dict[str, float] = {}
        self._failsafe_suspended: Set[str] = set()
        # Override manual genérico pra atuadores SEM controle de potência
        # (ex.: bombas) — separado de _manual_duty/_manual_enabled, que só
        # existem pra atuadores com hardware.window_seconds. Guarda o
        # último valor que um humano/API definiu explicitamente; o
        # RecipeEngine consulta has_manual_override() em _apply_pumps()
        # pra nunca sobrescrever um atuador sob controle manual — sem
        # isso, o diff interno do RecipeEngine (self._active_pumps) pode
        # dessincronizar da realidade e "desfazer" o comando manual
        # silenciosamente na próxima troca de etapa.
        self._manual_override: Dict[str, Any] = {}

        self._setup_all()

    def _setup_all(self) -> None:
        for device in self._config.devices:
            mode = resolve_mode(device.role, device.subtype)
            kwargs: Dict[str, Any] = {}
            kwargs.update(device.simulated)
            kwargs.update(device.limits)
            if "pwm_frequency" in device.hardware:
                kwargs["pwm_frequency"] = device.hardware["pwm_frequency"]
            if "driver" in device.hardware:
                kwargs["driver"] = device.hardware["driver"]
            if "address" in device.hardware:
                kwargs["address"] = device.hardware["address"]
            # active_high: controla se HIGH = ligado (True, default) ou
            # LOW = ligado (False, para relés active-low).
            # Só propagado se declarado explicitamente no devices.yml;
            # o backend usa True como default quando ausente.
            if "active_high" in device.hardware:
                kwargs["active_high"] = device.hardware["active_high"]
            self._backend.setup(pin=device.hardware["pin"], mode=mode, **kwargs)

            if device.has_duty_control:
                self._tpc[device.id] = TimeProportioningController(device.hardware["window_seconds"])

    def list_devices(self) -> List[DeviceState]:
        return [self._state_of(device) for device in self._config.devices]

    def get_state(self, device_id: str) -> DeviceState:
        device = self._config.get_device(device_id)
        return self._state_of(device)

    def set_actuator(self, device_id: str, value: Any) -> DeviceState:
        """
        Aciona um atuador diretamente (sem passar por MQTT) — usado pelo
        painel manual e, na Fase 4, também pelo bridge ao receber comando
        via command_topic.
        """
        device = self._config.get_device(device_id)
        if device.role != "actuator":
            raise DeviceRuntimeError(
                f"set_actuator chamado em '{device_id}', que não é actuator (role='{device.role}')."
            )
        self._backend.write(device.hardware["pin"], value, address=device.hardware.get("address"))
        return self._state_of(device)

    def inject_sensor(self, device_id: str, value: Any) -> DeviceState:
        """
        Injeta um valor fake em um sensor simulado (painel ajustando um
        slider). Só faz sentido com SimulatedGPIOBackend — se o backend
        real não tiver inject(), o erro sobe naturalmente como
        AttributeError, e quem chama (panel/api.py) decide como tratar
        isso para o usuário.
        """
        device = self._config.get_device(device_id)
        if device.role != "sensor":
            raise DeviceRuntimeError(
                f"inject_sensor chamado em '{device_id}', que não é sensor (role='{device.role}')."
            )
        self._backend.inject(device.hardware["pin"], value, address=device.hardware.get("address"))
        return self._state_of(device)

    def apply_failsafe(self, device_id: str) -> DeviceState:
        """
        Aplica failsafe_value (do próprio devices.yml) localmente a um
        atuador de risco — usado pela lógica de failsafe_timeout_seconds
        e pelas ações de abort/pause/crash do RecipeEngine.

        Se o device tiver controle de potência (has_duty_control), além
        da escrita imediata isso SUSPENDE qualquer duty manual ou vindo
        de receita — sem isso, o próximo tick_duty() religaria o
        atuador usando o duty antigo, tornando o failsafe efêmero. Mesma
        suspensão vale pra override manual booleano (ex.: bomba). A
        suspensão só é revertida por resume_all_suspended_overrides().
        """
        device = self._config.get_device(device_id)
        if not device.is_risk:
            raise DeviceRuntimeError(
                f"apply_failsafe chamado em '{device_id}', que não é is_risk=true."
            )
        if device.id in self._tpc or device.id in self._manual_override:
            self._failsafe_suspended.add(device.id)
        return self.set_actuator(device_id, device.failsafe_value)

    def apply_failsafe_external(self, device_id: str, value: Any) -> DeviceState:
        """
        Igual a apply_failsafe(), mas com o valor vindo de fora (payload
        de status agregado do Tesseract, ver status_handler.py) em vez
        do failsafe_value local — mesmo mecanismo de suspensão de duty,
        pra manter um único caminho de "failsafe sempre vence".
        """
        device = self._config.get_device(device_id)
        if device.id in self._tpc or device.id in self._manual_override:
            self._failsafe_suspended.add(device.id)
        return self.set_actuator(device_id, value)

    def resume_all_suspended_overrides(self) -> None:
        """
        Limpa toda suspensão de failsafe. Atuadores com controle de
        potência se resolvem sozinhos no próximo tick_duty() (loop
        contínuo). Overrides booleanos (bombas) NÃO têm esse loop —
        precisam ser reescritos explicitamente aqui, senão ficam parados
        no failsafe_value até algum evento futuro reescrever por acaso.
        Chamado SÓ por RecipeEngine.resume() (ação explícita do usuário)
        — nunca pelo watchdog/status_handler, que nunca devem religar um
        atuador de risco sozinhos por causa de reconexão de rede.
        """
        suspended_bool_overrides = [
            device_id for device_id in self._failsafe_suspended
            if device_id in self._manual_override
        ]
        self._failsafe_suspended.clear()
        for device_id in suspended_bool_overrides:
            self.set_actuator(device_id, self._manual_override[device_id])

    def has_duty_control(self, device_id: str) -> bool:
        return device_id in self._tpc

    def has_manual_override(self, device_id: str) -> bool:
        """
        True quando um humano/API definiu um valor manual explícito pra
        este atuador (fora do sistema de duty-cycle) — usado pelo
        RecipeEngine._apply_pumps() pra nunca sobrescrever silenciosamente
        um atuador sob controle manual.
        """
        return device_id in self._manual_override

    def set_manual_override(self, device_id: str, value: Optional[Any]) -> DeviceState:
        """
        Define (value não-None) ou limpa (None) um override manual pra um
        atuador SEM controle de potência (ex.: bomba, ou qualquer digital
        simples) — enquanto definido, o RecipeEngine._apply_pumps() nunca
        escreve nesse device, mesmo que ele apareça na lista de pumps de
        uma etapa ativa. Escreve no GPIO imediatamente, exceto se o
        device estiver com failsafe suspenso (segurança sempre vence).
        """
        device = self._config.get_device(device_id)
        if device.role != "actuator":
            raise DeviceRuntimeError(
                f"set_manual_override chamado em '{device_id}', que não é actuator (role='{device.role}')."
            )
        if value is None:
            self._manual_override.pop(device.id, None)
            return self._state_of(device)
        self._manual_override[device.id] = value
        if device.id in self._failsafe_suspended:
            # Guarda a intenção, mas não escreve fisicamente enquanto o
            # failsafe estiver suspenso — mesma regra de segurança do
            # controle de potência (failsafe sempre vence).
            return self._state_of(device)
        return self.set_actuator(device_id, value)

    def set_manual_duty_percent(self, device_id: str, duty_percent: float) -> DeviceState:
        """
        Define só o VALOR de % do override manual — NÃO arma o
        interruptor mestre (ver set_manual_enabled). Ajustar o slider no
        painel chama só isto: o atuador não energiza sozinho só porque
        o valor mudou, precisa do controle estar explicitamente ligado.
        """
        device = self._config.get_device(device_id)
        if device.id not in self._tpc:
            raise DeviceRuntimeError(
                f"set_manual_duty_percent chamado em '{device_id}', que não declara "
                f"hardware.window_seconds (sem controle de potência)."
            )
        if not isinstance(duty_percent, (int, float)) or isinstance(duty_percent, bool):
            raise DeviceRuntimeError(f"duty_percent deve ser numérico (recebido {duty_percent!r}).")
        if not (0.0 <= duty_percent <= 100.0):
            raise DeviceRuntimeError(f"duty_percent deve estar entre 0 e 100 (recebido {duty_percent}).")
        self._manual_duty[device.id] = float(duty_percent)
        return self._state_of(device)

    def set_manual_enabled(self, device_id: str, enabled: bool) -> DeviceState:
        """
        Liga/desliga o interruptor mestre do override manual — separado
        do valor de % (set_manual_duty_percent). Só quando enabled=True
        o valor configurado é de fato aplicado (ver _resolve_effective_duty).
        Desligar preserva o valor de % configurado (não zera), pra poder
        religar depois no mesmo nível sem precisar reconfigurar.
        """
        device = self._config.get_device(device_id)
        if device.id not in self._tpc:
            raise DeviceRuntimeError(
                f"set_manual_enabled chamado em '{device_id}', que não declara "
                f"hardware.window_seconds (sem controle de potência)."
            )
        if enabled:
            self._manual_enabled.add(device.id)
            # Garante que exista um valor (default seguro 0%) — ligar o
            # interruptor sem nunca ter configurado % não deve dar erro,
            # só não aplica potência nenhuma até o usuário ajustar o slider.
            self._manual_duty.setdefault(device.id, 0.0)
        else:
            self._manual_enabled.discard(device.id)
        return self._state_of(device)

    def set_manual_duty(self, device_id: str, duty_percent: Optional[float]) -> DeviceState:
        """
        Atômico: define o valor de % E arma o interruptor mestre de uma
        vez (duty_percent numérico), ou desarma por completo (None) —
        usado por comando MQTT/externo (bridge.py), onde o comando em si
        já é a intenção explícita de ligar, diferente de um humano
        arrastando o slider no painel (que usa os dois métodos acima,
        separados, via a API do painel).
        """
        if duty_percent is None:
            return self.set_manual_enabled(device_id, False)
        self.set_manual_duty_percent(device_id, duty_percent)
        return self.set_manual_enabled(device_id, True)

    def set_pid_duty(self, device_id: str, duty_percent: float) -> None:
        """
        Chamado pelo RecipeEngine a cada tick com o duty calculado pelo
        PID daquele instante — só tem efeito real se não houver override
        manual armado nem failsafe suspenso para este device (ver
        _resolve_effective_duty).
        """
        device = self._config.get_device(device_id)
        if device.id not in self._tpc:
            raise DeviceRuntimeError(
                f"set_pid_duty chamado em '{device_id}', que não declara "
                f"hardware.window_seconds (sem controle de potência)."
            )
        self._pid_duty[device.id] = max(0.0, min(100.0, float(duty_percent)))

    def get_duty_state(self, device_id: str) -> "DutyState":
        device = self._config.get_device(device_id)
        if device.id not in self._tpc:
            raise DeviceRuntimeError(
                f"get_duty_state chamado em '{device_id}', que não declara "
                f"hardware.window_seconds (sem controle de potência)."
            )
        duty_percent, source = self._resolve_effective_duty(device.id)
        return DutyState(
            duty_percent=duty_percent,
            source=source,
            window_seconds=device.hardware["window_seconds"],
        )

    def _resolve_effective_duty(self, device_id: str) -> Tuple[float, str]:
        if device_id in self._failsafe_suspended:
            return 0.0, "failsafe_suspended"
        if device_id in self._manual_enabled:
            return self._manual_duty.get(device_id, 0.0), "manual"
        if device_id in self._pid_duty:
            return self._pid_duty[device_id], "pid"
        return 0.0, "idle"

    def tick_duty(self, now: float) -> None:
        """
        Avança um passo o controle de potência de todo atuador com
        hardware.window_seconds: resolve o duty efetivo pela prioridade
        (failsafe > manual > receita > repouso), atualiza o TPC e
        escreve liga/desliga no GPIO. Chamado a cada iteração do loop
        principal do bridge — nunca pelo painel isolado (run_panel.py).
        """
        for device_id, tpc in self._tpc.items():
            duty_percent, _source = self._resolve_effective_duty(device_id)
            tpc.set_duty_cycle(duty_percent)
            on = tpc.should_be_on(now)
            device = self._config.get_device(device_id)
            self._backend.write(device.hardware["pin"], on, address=device.hardware.get("address"))

    def get_device_config(self, device_id: str) -> DeviceConfig:
        """
        Expõe o DeviceConfig (incl. subtype, command_topic resolvido pelo
        chamador) — usado por mqtt_client.py para decidir como coercer o
        failsafe_value vindo do Tesseract (string -> float/bool).
        """
        return self._config.get_device(device_id)

    def list_device_configs(self) -> List[DeviceConfig]:
        return list(self._config.devices)

    def _state_of(self, device: DeviceConfig) -> DeviceState:
        value = self._backend.read(device.hardware["pin"], address=device.hardware.get("address"))
        source = device.simulated if device.role == "sensor" else device.limits
        device_range = {
            "min": source.get("min", 0),
            "max": source.get("max", 100),
        }
        window_seconds = None
        duty_percent = None
        duty_source = None
        duty_enabled = None
        manual_duty_percent = None
        if device.id in self._tpc:
            window_seconds = device.hardware["window_seconds"]
            duty_percent, duty_source = self._resolve_effective_duty(device.id)
            duty_enabled = device.id in self._manual_enabled
            manual_duty_percent = self._manual_duty.get(device.id)

        manual_override = self._manual_override.get(device.id) if device.role == "actuator" else None

        return DeviceState(
            id=device.id,
            name=device.name,
            role=device.role,
            subtype=device.subtype,
            unit=device.unit,
            value=value,
            is_risk=device.is_risk,
            failsafe_value=device.failsafe_value,
            range=device_range,
            gpio=device.hardware["pin"],
            window_seconds=window_seconds,
            duty_percent=duty_percent,
            duty_source=duty_source,
            duty_enabled=duty_enabled,
            manual_duty_percent=manual_duty_percent,
            manual_override=manual_override,
        )
