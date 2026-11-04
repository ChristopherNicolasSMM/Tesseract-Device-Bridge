# Caminhos no Windows e Raspberry Pi | versão 2.0.0

## Fonte única de dados

O Device Bridge usa o SQLite armazenado em
`data/private/bridge.sqlite3` (padrão) ou no caminho configurado por
`TESSERACT_BRIDGE_DB`. Os arquivos legados `devices.yml`,
`receita.json`, `control_settings.json`, `recipe_state.json` e
`sensor_calibration.json` só são lidos pelo **importador explícito**,
não pela inicialização do Bridge.

Caminhos relativos do `.env` são resolvidos a partir da **raiz do
clone**, mesmo que o terminal/IDE esteja em outra pasta.

## Windows: simulação segura

```powershell
Copy-Item .env.example .env
notepad .env
python -m storage.cli status
python -m pytest -q tests/test_infra_env.py
python run_bridge.py
```

Use `TESSERACT_BRIDGE_SIMULATION_ONLY=1` para desativar GPIO real
e MQTT, com painel restrito a `127.0.0.1:8089`. Ative a venv com
`.\venv\Scripts\Activate.ps1`.

Quando `imported.sqlite3` não existe, conclua a migração.
Para banco novo, aponte `bridge.sqlite3` no `.env` e execute
`python -m storage.cli init`.

## Raspberry Pi: instalação isolada e futura homologação física

- Python 3.9.x na venv para uso real.
- Banco SQLite local, permissões restritas para usuário do serviço.
- Confirme o ROM ID dos DS18B20, polaridade, pinagem e referências.
- Não permita instância antiga e nova simultâneas no mesmo hardware.
- O serviço systemd e o watchdog devem utilizar a URL/porta reais.
- O arquivo `.env` é privado: `chmod 600 .env` e leitura autorizada
  pelo usuário do processo.

A versão 2.0.0 ainda está em homologação. Evite ativar saída
física ou GLP até os testes e o procedimento de rollback estarem
formalmente validados.

## Status da homologação

O operador confirmou 12 testes de infraestrutura do `.env`
passando no Windows e um banco importado com 7 dispositivos e
2 receitas, em simulação. Isso **não substitui** a suíte integral
nem testes de carga física no Raspberry Pi.

Consulte o [manual de instalação](02-primeiros-passos.md) e
[manual de migração](12-sqlite-migracao.md).
