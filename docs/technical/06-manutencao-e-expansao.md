# 06 — Manutenção e Expansão

## Adicionar um novo tipo de sensor analógico

O único driver analógico implementado hoje é o DS18B20 (temperatura 1-Wire).
Para suportar outro tipo de sensor (umidade do solo, pH, CO2, etc.):

1. Criar `gpio/<nome_do_driver>_driver.py` com uma função que recebe
   `pin` e `address` (opcional) e retorna um float:

```python
def read_meu_sensor(pin: int, address: str | None = None) -> float:
    # lógica de leitura (i2c, SPI, filesystem, etc.)
    return valor_float
```

2. Registrar no `DeviceRuntime.__init__` via `register_analog_driver()`:

```python
from gpio.meu_sensor_driver import read_meu_sensor
runtime.register_analog_driver("meu_driver", read_meu_sensor)
```

3. Usar em `devices.yml`:

```yaml
- id: sensor_umidade_solo
  role: sensor
  subtype: temperature   # ou outro subtype válido
  hardware:
    pin: 5
    driver: meu_driver
    address: "opcional"
```

4. Adicionar testes cobrindo o novo driver com um filesystem fake ou mock
   (ver `tests/test_ds18b20_driver.py` como referência de padrão).

---

## Adaptar para um novo domínio de automação

O bridge é agnóstico de domínio. Para controlar, por exemplo, irrigação por
zona (sensor de umidade → válvula solenóide) em vez de brassagem:

**O que muda:**

| Arquivo | O que fazer |
|---|---|
| `devices.yml` | Descrever os sensores de umidade e as válvulas com os pinos corretos |
| `recipe.yml` | Declarar as "vasilhas" (zonas de irrigação), o alvo (`target_temp` passa a ser `target_humidity` semanticamente, mas o campo se chama `target_temp` no YAML — considere renomear numa versão futura), as etapas e os alarmes |
| `gpio/<driver>.py` | Novo driver se o sensor não for DS18B20 |

**O que não muda:**

Nada em `recipe_engine/`, `bridge.py`, `panel/`, `mqtt_client.py`,
`failsafe_watchdog.py`, `status_handler.py` — o núcleo opera sobre
abstrações de "sensor com valor float" e "atuador liga/desliga".

**Limitação atual a considerar**: o campo de alvo na receita se chama
`target_temp` (legado da origem cervejeira). Para novos domínios, o nome é
semanticamente estranho. Para renomear sem quebrar receitas existentes:
1. Adicionar campo `target_value` em `RecipeStep` como alias.
2. Manter `target_temp` por retrocompatibilidade com um `DeprecationWarning`.
3. Atualizar `recipe.yml.example` para o novo nome.
4. Gerar migration de `recipe.yml` (renomear campo via script).

---

## Adicionar uma nova etapa ou vasilha a uma receita existente

1. Editar `recipe.yml` (ou criar um novo, já que `recipe.yml` é editável
   sem reiniciar o bridge — `run_bridge.py` carrega no boot; mudar
   `recipe.yml` exige reiniciar o processo para ter efeito).
2. Validar localmente antes de aplicar em produção:

```bash
python3 -c "
from config import BridgeConfig
from recipe_engine.models import Recipe
config = BridgeConfig.load('devices.yml')
recipe = Recipe.load('recipe.yml', config)
print('OK:', recipe.name, recipe.step_count(), 'etapas')
"
```

3. Se adicionar uma nova `vessel`, verificar que `heater_device_id` e
   `sensor_device_id` existem em `devices.yml` — a validação no `load()`
   levanta `RecipeError` com mensagem clara se não existirem.

---

## Adicionar um novo campo ao schema de `devices.yml` ou `recipe.yml`

1. Adicionar o campo no dataclass correspondente em `config.py` (devices)
   ou `recipe_engine/models.py` (recipe), com um valor default (campo
   opcional) ou sem (campo obrigatório com validação explícita).
2. Adicionar validação em `validate_against()` / `validate()` se necessário.
3. Adicionar testes em `tests/test_config.py` ou `tests/test_recipe_models.py`.
4. Atualizar `devices.yml.example` ou `recipe.yml.example`.
5. Atualizar este arquivo (`06-manutencao-e-expansao.md`) e
   `04-modelo-de-dados.md` com o novo campo.

**Atenção**: `recipe_state.json` é carregado por `RecipeState.load()` que
usa `dataclass(**raw)` — adicionar um campo novo ao dataclass sem um default
vai quebrar o load de arquivos de estado antigos. Sempre use `field(default=...)`.

---

## Pontos de extensão conhecidos

| Ponto | Como usar |
|---|---|
| `register_analog_driver(name, fn)` | Registra novos drivers de sensor analógico no `DeviceRuntime` |
| `GPIOBackend` (interface abstrata) | Subclassear para novos backends (ex.: MCP23017 I²C, saída serial, etc.) |
| `BridgeConfig.mqtt.enabled: false` | Roda o bridge 100% offline, sem dependência de broker |
| `recipe_engine` recebe `DeviceRuntime` no construtor | Pode ser testado isoladamente com um `DeviceRuntime` com backend simulado |
| `AlarmEvent.type` é string livre | O painel usa os tipos conhecidos (`vessel_start`, `vessel_end`, `hop_addition`) mas aceita qualquer string — extensível sem mudar a UI |
| Polling do painel é 2.5s configurável | `setInterval(pollRecipeStatus, 2500)` em `index.html` — ajustável conforme latência aceitável |

---

## Checklist de validação antes de um deploy em Pi real

- [ ] `python -m pytest tests/ -v` — todos passando
- [ ] `python3 -c "from config import BridgeConfig; BridgeConfig.load('devices.yml')"` — sem erros
- [ ] `python3 -c "from recipe_engine.models import Recipe; from config import BridgeConfig; Recipe.load('recipe.yml', BridgeConfig.load('devices.yml'))"` — sem erros (se recipe.yml existir)
- [ ] `python -m gpio.ds18b20_scan` — sensores encontrados com os endereços certos
- [ ] `devices.yml` com `backend: real` (não `simulated`)
- [ ] `mqtt.host` apontando pro broker real (ou `mqtt.enabled: false` se não houver broker)
- [ ] Testar manualmente no painel: ligar/desligar cada atuador e confirmar resposta física
- [ ] Testar failsafe: matar o processo com `kill -9` durante execução, confirmar que atuadores de risco desligam ao reiniciar
