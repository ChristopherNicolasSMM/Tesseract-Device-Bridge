"""
Backend real de GPIO para Raspberry Pi — usa gpiozero como camada de
abstração, mas força explicitamente qual "pin factory" (backend) usar,
em vez de deixar o gpiozero escolher automaticamente.

Por que isso importa
--------------------
O gpiozero suporta vários backends e, a partir do Raspberry Pi OS
Bookworm (2023), o padrão mudou de RPi.GPIO para lgpio. Se o backend
errado for escolhido automaticamente, o setup aparentemente funciona
(sem exceção) mas os pinos não respondem fisicamente — exatamente o
sintoma relatado: o CraftBeerPi4 funcionava, o bridge não.

O `raspi-gpio` (que funcionou para desligar os pinos via terminal)
acessa /dev/gpiomem diretamente, sem biblioteca Python no meio. O
backend RPi.GPIO faz o mesmo — por isso, em Raspbian/Bullseye/Buster,
RPi.GPIO é a escolha certa e deve ter prioridade.

Ordem de tentativa
------------------
1. lgpio      — padrão no Pi OS Bookworm e Pi 5 (libgpiod via chardev)
2. RPi.GPIO   — padrão no Raspbian / Pi OS Bullseye e anteriores
3. pigpio     — fallback; requer daemon `pigpiod` rodando previamente

O backend escolhido é registrado no log (nível INFO) assim que o
RealGPIOBackend é instanciado, para que seja visível no terminal ao
subir o bridge:

    INFO  tesseract_bridge.gpio.real: backend selecionado: RPi.GPIO (rpigpio)

Se nenhum backend estiver disponível, levanta RuntimeError com
instruções claras de instalação em vez de mensagem de erro opaca.

active_high
-----------
A grande maioria das placas de interface para Raspberry Pi (incluindo
a MAZZA CraftBeerPi) usa transistores NPN como driver de saída:
HIGH no pino → NPN conduz → carga liga. Isso é lógica direta,
active_high=True (default do gpiozero).

Alguns módulos de relé prontos (os "azuis do AliExpress") usam
optoacoplador com lógica invertida: LOW no pino → relé fecha. Para
esses, use active_high: false no devices.yml — o campo é propagado
aqui via kwargs e passado ao DigitalOutputDevice.

Testabilidade fora do Pi
------------------------
Os testes unitários usam gpiozero.pins.mock (MockFactory + MockPWMPin)
via device_factory injetável — validam que o modo certo foi
configurado para o tipo certo de device ("wiring test"), mas NÃO
provam que o hardware físico responde. O primeiro teste real sempre
é no Pi de verdade, usando tools/gpio_test.py.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Union

from gpiozero import DigitalInputDevice, DigitalOutputDevice, PWMOutputDevice

from gpio.base import GPIOBackend
from gpio.ds18b20_driver import Ds18b20Reader

logger = logging.getLogger("tesseract_bridge.gpio.real")

_Key = Union[int, "tuple[int, str]"]


def _make_key(pin: int, address: Optional[str]) -> _Key:
    """
    Gera a chave de lookup do device no dicionário interno.
    Sensores DS18B20 no mesmo barramento 1-Wire compartilham o pino
    mas se distinguem pelo address (ROM ID gravado de fábrica), então
    a chave vira uma tupla (pin, address) nesses casos.
    """
    return pin if address is None else (pin, address)


def _pick_pin_factory():
    """
    Tenta instanciar os backends do gpiozero na ordem de preferência:
      1. lgpio    — padrão no Pi OS Bookworm / Pi 5
      2. RPi.GPIO — padrão no Raspbian / Bullseye / Buster
      3. pigpio   — fallback (requer daemon pigpiod)

    Retorna o primeiro que instanciar sem erro, ou None se nenhum
    estiver disponível (o gpiozero vai usar o seu próprio default
    nesse caso — melhor que levantar erro no import).

    Chamado uma única vez no __init__ do RealGPIOBackend e o resultado
    é guardado em self._pin_factory para ser passado a cada device
    criado depois.
    """
    candidates = [
        # (nome legível para o log, módulo, classe)
        ("lgpio",    "gpiozero.pins.lgpio",   "LGPIOFactory"),
        ("RPi.GPIO", "gpiozero.pins.rpigpio", "RPiGPIOFactory"),
        ("pigpio",   "gpiozero.pins.pigpio",  "PiGPIOFactory"),
    ]

    for name, module_path, class_name in candidates:
        try:
            import importlib
            module = importlib.import_module(module_path)
            factory_class = getattr(module, class_name)
            factory = factory_class()
            logger.info("backend selecionado: %s (%s)", name, module_path.split(".")[-1])
            return factory
        except Exception as exc:
            # Não é erro — é apenas "este backend não está disponível".
            logger.debug("backend %s indisponivel: %s", name, exc)

    # Nenhum backend explícito funcionou — avisa e retorna None.
    # O gpiozero vai tentar o seu default automático; se também falhar,
    # o erro vai aparecer na primeira chamada a setup().
    logger.warning(
        "Nenhum backend GPIO explícito disponível (lgpio, RPi.GPIO, pigpio). "
        "O gpiozero vai tentar o default automático, o que pode não funcionar. "
        "Para instalar: 'pip install lgpio' ou 'pip install RPi.GPIO'."
    )
    return None


# Registro de drivers para sensores que não são GPIO digital/PWM simples.
# Cada driver é uma callable que recebe (pin, **kwargs) e retorna um
# objeto com .value (float). Adicionar novos drivers sem editar este
# arquivo: chamar register_analog_driver() antes de instanciar o backend.
_ANALOG_DRIVERS: Dict[str, Callable[..., Any]] = {
    "ds18b20": Ds18b20Reader,
}


def register_analog_driver(name: str, factory: Callable[..., Any]) -> None:
    """
    Registra (ou sobrescreve) um driver de sensor analógico/1-Wire.
    Útil para novos tipos de sensor (umidade do solo, pH, etc.) sem
    precisar editar gpio/real_backend.py.

    O factory recebe (pin, **kwargs) onde kwargs são os campos extras
    do bloco `hardware:` do devices.yml (ex.: address, driver).
    """
    _ANALOG_DRIVERS[name] = factory


class RealGPIOBackend(GPIOBackend):
    """
    Implementação de GPIOBackend sobre hardware real do Raspberry Pi,
    usando gpiozero com backend explícito (ver _pick_pin_factory).

    Pode ser instanciado com um pin_factory já pronto (útil nos testes,
    onde se passa gpiozero.pins.mock.MockFactory para validar wiring
    sem hardware físico):

        backend = RealGPIOBackend(pin_factory=MockFactory())

    Sem argumentos, seleciona o melhor backend disponível
    automaticamente.
    """

    def __init__(self, pin_factory=None) -> None:
        # Se nenhum pin_factory foi passado pelo chamador, detectar
        # automaticamente. Guardamos o resultado para reusar em cada
        # device criado via setup() — garantia de que todos os devices
        # usam o mesmo backend dentro de uma instância do bridge.
        self._pin_factory = pin_factory if pin_factory is not None else _pick_pin_factory()
        self._devices: Dict[_Key, Any] = {}
        self._modes: Dict[_Key, str] = {}

    # ---- helpers internos ------------------------------------------------

    def _device_kwargs(self, extra: dict) -> dict:
        """
        Retorna os kwargs comuns a todo device gpiozero: apenas
        pin_factory, se tivermos um selecionado. Separado para não
        repetir o if em cada branch de setup().
        """
        kwargs = {}
        if self._pin_factory is not None:
            kwargs["pin_factory"] = self._pin_factory
        return kwargs

    def _require_device(self, key: _Key, pin: int, address: Optional[str]) -> Any:
        """Levanta KeyError descritivo se setup() não foi chamado antes."""
        if key not in self._devices:
            suffix = f" (address={address})" if address is not None else ""
            raise KeyError(
                f"Pino {pin}{suffix} não foi configurado via setup() antes do uso. "
                f"Verifique se o DeviceRuntime inicializou todos os devices corretamente."
            )
        return self._devices[key]

    # ---- interface pública (GPIOBackend) ----------------------------------

    def setup(self, pin: int, mode: str, **kwargs: Any) -> None:
        """
        Configura um pino GPIO para o modo indicado e armazena o device
        gpiozero correspondente.

        Parâmetros de kwargs usados aqui:
          address      (str)  — ROM ID do sensor DS18B20; torna a chave
                                uma tupla (pin, address) em vez de só pin.
          driver       (str)  — nome do driver analógico a usar
                                (ex.: "ds18b20"). Obrigatório para
                                mode="input_analog".
          active_high  (bool) — True (default): HIGH = ativo (ligado).
                                False: LOW = ativo — para relés com
                                lógica invertida (optoacoplador invertido).
                                Campo opcional em devices.yml:
                                  hardware:
                                    active_high: false
          pwm_frequency (int) — frequência PWM em Hz (default: 100).
                                Só usado em mode="pwm".
        """
        address = kwargs.get("address")
        key = _make_key(pin, address)

        # active_high: default True (lógica direta — MAZZA NPN e a
        # maioria dos módulos de relé industriais). Configurar como
        # False no devices.yml apenas para relés active-low (ex.:
        # módulos azuis do AliExpress com optoacoplador invertido).
        active_high = kwargs.get("active_high", True)

        gz_kwargs = self._device_kwargs(kwargs)

        if mode == "output":
            # Saída digital (liga/desliga).
            # initial_value=False garante que o pino começa desligado,
            # independente do estado que ficou do boot anterior.
            device = DigitalOutputDevice(
                pin,
                active_high=active_high,
                initial_value=False,
                **gz_kwargs,
            )

        elif mode == "pwm":
            # Saída PWM (potência variável, ex.: resistência com SSR analógico).
            # A maioria da placa MAZZA usa digital + time-proportioning
            # (RecipeEngine), não PWM de hardware. Mas o suporte existe
            # para hardware que realmente suporte PWM.
            frequency = kwargs.get("pwm_frequency", 100)
            device = PWMOutputDevice(
                pin,
                active_high=active_high,
                initial_value=0,
                frequency=frequency,
                **gz_kwargs,
            )

        elif mode == "input":
            # Entrada digital (botão, sensor de nível on/off, etc.).
            device = DigitalInputDevice(pin, **gz_kwargs)

        elif mode == "input_analog":
            # Sensor analógico ou protocolo especial (ex.: DS18B20 1-Wire).
            # O driver é responsável por toda a lógica de leitura —
            # o gpiozero não é usado diretamente aqui.
            driver_name = kwargs.get("driver")
            driver_factory = _ANALOG_DRIVERS.get(driver_name)
            if driver_factory is None:
                raise NotImplementedError(
                    f"Nenhum driver analógico registrado para '{driver_name}' "
                    f"(pino {pin}). "
                    f"Drivers disponíveis: {sorted(_ANALOG_DRIVERS)}. "
                    f"Para adicionar: register_analog_driver('{driver_name}', sua_classe)."
                )
            # O driver recebe todos os kwargs do bloco hardware: do
            # devices.yml (pin, address, driver, etc.) — é de
            # responsabilidade do driver ignorar o que não usa.
            device = driver_factory(pin, **kwargs)

        else:
            raise ValueError(
                f"Modo inválido '{mode}' para pino {pin}. "
                f"Modos aceitos: 'output', 'pwm', 'input', 'input_analog'."
            )

        self._devices[key] = device
        self._modes[key] = mode
        logger.info(
            "setup: pino=%s address=%s mode=%s active_high=%s",
            pin, address, mode, active_high,
        )

    def read(self, pin: int, address: Optional[str] = None) -> Any:
        """
        Lê o valor atual do device no pino indicado.

        Para PWM, converte de 0.0-1.0 (escala interna do gpiozero) para
        0-100 (escala usada pelo resto do bridge).
        """
        key = _make_key(pin, address)
        device = self._require_device(key, pin, address)
        mode = self._modes[key]
        value = device.value

        if mode == "pwm":
            # gpiozero internamente usa 0.0–1.0; o bridge usa 0–100.
            return float(value) * 100.0

        logger.debug("read: pino=%s address=%s mode=%s value=%s", pin, address, mode, value)
        return value

    def write(self, pin: int, value: Any, address: Optional[str] = None) -> None:
        """
        Escreve um valor no atuador do pino indicado.

        Só válido para modes 'output' e 'pwm'. Tentar escrever em um
        sensor levanta ValueError explícito (em vez de falhar silenciosamente
        ou gravar em hardware errado).
        """
        key = _make_key(pin, address)
        device = self._require_device(key, pin, address)
        mode = self._modes[key]

        if mode not in ("output", "pwm"):
            raise ValueError(
                f"write() chamado em pino {pin} com mode='{mode}'. "
                f"write() só é permitido em modos 'output' e 'pwm'. "
                f"Para alterar o valor de um sensor em teste, use "
                f"SimulatedGPIOBackend e inject()."
            )

        if mode == "pwm":
            # Converte 0-100 (bridge) para 0.0-1.0 (gpiozero).
            device.value = max(0.0, min(1.0, float(value) / 100.0))
        else:
            # Digital: qualquer truthy = liga, falsy = desliga.
            device.value = bool(value)

        logger.info(
            "write: pino=%s address=%s mode=%s value=%s",
            pin, address, mode, value,
        )

    def teardown(self, pin: int, address: Optional[str] = None) -> None:
        """
        Libera o device do pino indicado e fecha a conexão com o
        hardware (gpiozero.Device.close()). Chamado pelo DeviceRuntime
        quando o bridge está encerrando.
        """
        key = _make_key(pin, address)
        device = self._devices.pop(key, None)
        self._modes.pop(key, None)

        if device is not None and hasattr(device, "close"):
            device.close()
            logger.info("teardown: pino=%s address=%s", pin, address)
