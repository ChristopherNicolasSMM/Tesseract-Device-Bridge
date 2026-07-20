#!/usr/bin/env python3
"""
GPIO Test Tool — Tesseract Device Bridge
=========================================
Script interativo para diagnosticar GPIO diretamente no Raspberry Pi,
sem precisar do devices.yml nem subir o bridge completo.

Roda assim:
    python tools/gpio_test.py

Usa o mesmo caminho de código que o bridge usa em produção:
  - gpio/real_backend.py  (com seleção automática de backend)
  - gpio/ds18b20_driver.py (para sensores DS18B20)

Por que isso é útil antes de subir o bridge
-------------------------------------------
Se um pino não responde no bridge, é difícil saber se o problema é:
  a) backend GPIO errado (lgpio vs RPi.GPIO vs pigpio)
  b) pino errado (BCM vs BOARD numbering)
  c) lógica invertida (active_high errado)
  d) problema físico (fiação, fusível, alimentação)

Este script isola cada variável uma por vez, testando um pino de cada
vez em vez de configurar todos de uma vez como o bridge faz.

Pré-requisitos
--------------
  pip install gpiozero
  pip install RPi.GPIO    # Raspbian / Bullseye / Buster
  # OU
  pip install lgpio       # Bookworm / Pi 5

  # Para sensores DS18B20, adicionar ao /boot/config.txt e reiniciar:
  # dtoverlay=w1-gpio
"""

import sys
import os
import time
import logging

# Garante que o diretório raiz do projeto está no path, independente
# de onde o script é chamado (ex.: de dentro de tools/ ou da raiz).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Loga apenas WARNING por padrão; o usuário pode subir para DEBUG
# passando --debug como argumento.
_debug = "--debug" in sys.argv
logging.basicConfig(
    level=logging.DEBUG if _debug else logging.WARNING,
    format="%(levelname)s  %(name)s: %(message)s",
)

# ---- importações do projeto -----------------------------------------------
try:
    from gpio.real_backend import RealGPIOBackend
except ImportError as e:
    print(f"\nErro ao importar o backend GPIO: {e}")
    print("Certifique-se de rodar este script da raiz do projeto:")
    print("    python tools/gpio_test.py")
    sys.exit(1)

# ---- helpers de UI ---------------------------------------------------------

def sep(char="─", width=52):
    print(char * width)

def titulo(texto):
    sep()
    print(f"  {texto}")
    sep()

def pergunta(prompt, default=None):
    """Lê input do usuário, retornando default se Enter vazio."""
    sufixo = f" [{default}]" if default is not None else ""
    try:
        resp = input(f"  {prompt}{sufixo}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\nInterrompido.")
        sys.exit(0)
    return resp if resp else (str(default) if default is not None else "")

def confirmar(prompt):
    """Pergunta S/N, retorna bool."""
    resp = pergunta(f"{prompt} [S/n]", default="s").lower()
    return resp in ("s", "sim", "y", "yes", "")

def aguardar_enter(msg="Pressione Enter para continuar..."):
    try:
        input(f"\n  {msg}")
    except (KeyboardInterrupt, EOFError):
        pass

# ---- backend global --------------------------------------------------------

_backend = None

def get_backend():
    """
    Instancia o backend uma única vez e reutiliza nas próximas chamadas.
    A mensagem de log do _pick_pin_factory() aparece aqui como INFO
    (ou suprimida se --debug não foi passado, mas o print abaixo
    sempre mostra o resultado).
    """
    global _backend
    if _backend is None:
        # Habilita INFO temporariamente só para capturar a mensagem do backend
        root_logger = logging.getLogger("tesseract_bridge.gpio.real")
        root_logger.setLevel(logging.INFO)
        _backend = RealGPIOBackend()
        # A mensagem de backend selecionado vai para o logger — capturamos
        # diretamente tentando detectar o factory escolhido.
        root_logger.setLevel(logging.WARNING if not _debug else logging.DEBUG)
    return _backend

def detectar_backend_nome():
    """Retorna o nome legível do backend ativo."""
    backend = get_backend()
    factory = backend._pin_factory
    if factory is None:
        return "default automático do gpiozero (não explícito)"
    class_name = type(factory).__name__
    mapa = {
        "LGPIOFactory": "lgpio (Pi OS Bookworm / Pi 5)",
        "RPiGPIOFactory": "RPi.GPIO (Raspbian / Bullseye / Buster)",
        "PiGPIOFactory": "pigpio (requer daemon pigpiod)",
        "MockFactory": "Mock (modo de teste — não é hardware real)",
    }
    return mapa.get(class_name, class_name)

# ---- opções do menu --------------------------------------------------------

def menu_testar_saida():
    """
    Testa um pino de saída (atuador — relé, bomba, resistência).
    Liga por N segundos e desliga, ou mantém o estado até Enter.
    """
    titulo("Testar pino de SAÍDA (atuador)")
    print("  Use números BCM (os mesmos que estão no devices.yml).")
    print("  Ex.: GPIO17 = pino 17 na numeração BCM.\n")

    pin_str = pergunta("Número do pino BCM")
    if not pin_str.isdigit():
        print("  ❌  Número inválido.")
        return
    pin = int(pin_str)

    print("\n  active_high define o que 'ligar' significa para este pino:")
    print("    true  → HIGH (3.3V) = ligado  — MAZZA NPN e maioria dos relés")
    print("    false → LOW  (0V)   = ligado  — relés active-low (módulos azuis AliExpress)\n")
    ah_str = pergunta("active_high?", default="true").lower()
    active_high = ah_str in ("true", "t", "s", "sim", "yes", "y", "1")

    print("\n  Modo de teste:")
    print("    [1] Liga por N segundos e desliga automaticamente")
    print("    [2] Liga e aguarda Enter para desligar (manual)\n")
    modo = pergunta("Escolha", default="1")

    # Configura o pino
    print(f"\n  Configurando GPIO {pin} como saída (active_high={active_high})...")
    backend = get_backend()
    try:
        backend.setup(pin, "output", active_high=active_high)
    except Exception as e:
        print(f"  ❌  Erro ao configurar o pino: {e}")
        return

    try:
        if modo == "2":
            # Modo manual
            print(f"  ▶  Ligando GPIO {pin}...")
            backend.write(pin, True)
            print(f"  ✅  GPIO {pin} = {'HIGH (3.3V)' if active_high else 'LOW (0V)'} — atuador deve estar LIGADO")
            aguardar_enter("Pressione Enter para DESLIGAR...")
            backend.write(pin, False)
            print(f"  ⏹  GPIO {pin} desligado.")

        else:
            # Modo temporizado
            segundos_str = pergunta("Quantos segundos ligar?", default="3")
            try:
                segundos = float(segundos_str)
            except ValueError:
                segundos = 3.0

            print(f"  ▶  Ligando GPIO {pin} por {segundos}s...")
            backend.write(pin, True)
            print(f"  ✅  GPIO {pin} = {'HIGH (3.3V)' if active_high else 'LOW (0V)'} — o atuador deve estar LIGADO agora")

            for i in range(int(segundos * 10)):
                time.sleep(0.1)
                restante = segundos - (i + 1) * 0.1
                print(f"\r  ⏱  Desligando em {restante:.1f}s... ", end="", flush=True)

            backend.write(pin, False)
            print(f"\r  ⏹  GPIO {pin} desligado após {segundos}s.       ")

    except Exception as e:
        print(f"  ❌  Erro durante o teste: {e}")
    finally:
        # Sempre libera o pino, mesmo em caso de erro ou CTRL+C
        try:
            backend.teardown(pin)
        except Exception:
            pass

    aguardar_enter()


def menu_diagnostico_rapido():
    """
    Testa vários pinos em sequência: liga 2s, desliga, passa para o próximo.
    Útil para verificar se todos os relés da placa respondem antes da brassagem.
    """
    titulo("Diagnóstico rápido — testa múltiplos pinos em sequência")
    print("  Informe os pinos BCM separados por vírgula.")
    print("  Ex.: 17,27,22,26  (atuadores padrão da MAZZA)\n")

    pinos_str = pergunta("Pinos BCM", default="17,27,22,26")
    try:
        pinos = [int(p.strip()) for p in pinos_str.split(",") if p.strip()]
    except ValueError:
        print("  ❌  Formato inválido. Use números separados por vírgula.")
        return

    ah_str = pergunta("\nactive_high para todos?", default="true").lower()
    active_high = ah_str in ("true", "t", "s", "sim", "yes", "y", "1")

    duracao_str = pergunta("Segundos ligado por pino?", default="2")
    try:
        duracao = float(duracao_str)
    except ValueError:
        duracao = 2.0

    print(f"\n  Testando {len(pinos)} pinos, {duracao}s cada, active_high={active_high}...")
    print("  Observe os relés da placa durante o teste.\n")

    backend = get_backend()
    resultados = []

    for pin in pinos:
        try:
            backend.setup(pin, "output", active_high=active_high)
            print(f"  GPIO {pin:>2}: ligando... ", end="", flush=True)
            backend.write(pin, True)
            time.sleep(duracao)
            backend.write(pin, False)
            backend.teardown(pin)
            print("OK ✅")
            resultados.append((pin, True, None))
        except Exception as e:
            print(f"ERRO ❌  ({e})")
            resultados.append((pin, False, str(e)))
            try:
                backend.teardown(pin)
            except Exception:
                pass
        time.sleep(0.3)  # Pequena pausa entre pinos

    # Resumo
    print("\n  ── Resumo ──────────────────────────────")
    for pin, ok, erro in resultados:
        status = "✅ OK" if ok else f"❌ ERRO: {erro}"
        print(f"  GPIO {pin:>2}: {status}")
    print()

    aguardar_enter()


def menu_ler_sensor():
    """
    Lê um sensor DS18B20 em loop contínuo (CTRL+C para parar).
    Útil para confirmar que o sensor está respondendo e lendo certo
    antes de usar na receita.
    """
    titulo("Ler sensor DS18B20 (temperatura 1-Wire)")
    print("  O sensor DS18B20 é identificado pelo endereço ROM (ex.: 28-0000071234ab).")
    print("  Use 'python -m gpio.ds18b20_scan' para listar os endereços conectados.\n")

    pin_str = pergunta("Pino BCM do barramento 1-Wire", default="4")
    if not pin_str.isdigit():
        print("  ❌  Número inválido.")
        return
    pin = int(pin_str)

    address = pergunta("Endereço ROM do sensor (ex.: 28-0000071234ab)")
    if not address:
        print("  ❌  Endereço obrigatório.")
        return

    intervalo_str = pergunta("Intervalo de leitura (segundos)?", default="2")
    try:
        intervalo = float(intervalo_str)
    except ValueError:
        intervalo = 2.0

    backend = get_backend()
    try:
        backend.setup(pin, "input_analog", driver="ds18b20", address=address)
    except Exception as e:
        print(f"  ❌  Erro ao configurar sensor: {e}")
        return

    print(f"\n  Lendo GPIO {pin} / endereço {address} a cada {intervalo}s")
    print("  Pressione CTRL+C para parar.\n")

    try:
        while True:
            try:
                valor = backend.read(pin, address=address)
                timestamp = time.strftime("%H:%M:%S")
                print(f"  [{timestamp}]  {valor:.2f} °C")
            except Exception as e:
                print(f"  ❌  Erro de leitura: {e}")
            time.sleep(intervalo)
    except KeyboardInterrupt:
        print("\n\n  Leitura interrompida.")
    finally:
        try:
            backend.teardown(pin, address=address)
        except Exception:
            pass

    aguardar_enter()


def menu_info_backend():
    """
    Mostra qual backend GPIO está sendo usado e como trocar se necessário.
    """
    titulo("Informações do backend GPIO")
    nome = detectar_backend_nome()
    print(f"  Backend ativo: {nome}\n")
    print("  O backend é selecionado automaticamente na ordem:")
    print("    1. lgpio    — Pi OS Bookworm / Pi 5")
    print("    2. RPi.GPIO — Raspbian / Pi OS Bullseye / Buster")
    print("    3. pigpio   — fallback (requer daemon: sudo pigpiod)\n")
    print("  Se o backend errado está sendo selecionado:")
    print("    Para forçar RPi.GPIO:  pip install RPi.GPIO")
    print("    Para forçar lgpio:     pip install lgpio")
    print("    Para pigpio:           pip install pigpio && sudo pigpiod\n")
    print("  Se os pinos não respondem mas o hardware está correto:")
    print("    1. Verifique permissões: sudo usermod -a -G gpio $USER")
    print("       (depois fazer logout e login novamente)")
    print("    2. Teste via raspi-gpio diretamente:")
    print("       raspi-gpio set <pino> op dh   # liga (drive high)")
    print("       raspi-gpio set <pino> op dl   # desliga (drive low)")
    print("    3. Se raspi-gpio funciona mas o bridge não, o problema")
    print("       é de backend. Use esta ferramenta para diagnosticar.")
    aguardar_enter()


# ---- loop principal --------------------------------------------------------

def main():
    print()
    titulo("Tesseract GPIO Test Tool")
    print("  Ferramenta de diagnóstico de GPIO para Raspberry Pi.")
    print("  Testa pinos individualmente, sem precisar do devices.yml.\n")
    print("  Dica: passe --debug para ver os logs internos do gpiozero.")
    print()

    # Inicializa o backend já na abertura para mostrar qual foi selecionado
    get_backend()
    nome = detectar_backend_nome()
    print(f"  Backend GPIO: {nome}")
    print()

    opcoes = {
        "1": ("Testar pino de saída (atuador — relé, bomba, resistência)", menu_testar_saida),
        "2": ("Diagnóstico rápido: testa múltiplos pinos em sequência",    menu_diagnostico_rapido),
        "3": ("Ler sensor DS18B20 em tempo real",                          menu_ler_sensor),
        "4": ("Informações do backend GPIO e como trocar",                 menu_info_backend),
        "5": ("Sair",                                                      None),
    }

    while True:
        sep()
        print("  Menu principal\n")
        for num, (descricao, _) in opcoes.items():
            print(f"    [{num}] {descricao}")
        print()

        escolha = pergunta("Escolha uma opção", default="1")

        if escolha not in opcoes:
            print("  ❌  Opção inválida. Tente novamente.\n")
            continue

        descricao, funcao = opcoes[escolha]
        if funcao is None:
            print("\n  Até logo!\n")
            break

        print()
        funcao()
        print()


if __name__ == "__main__":
    main()
