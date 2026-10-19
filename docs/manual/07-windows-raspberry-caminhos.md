# Caminhos no Windows e Raspberry Pi

## Dados da aplicação

Os padrões são resolvidos pela localização da instalação do projeto, sem depender
da pasta atual do terminal, IDE, atalho ou serviço. Caminhos passados explicitamente
na linha de comando mantêm a semântica normal: se relativos, são relativos ao
terminal; se absolutos, são usados diretamente. Use aspas quando houver espaços.

| Item | Local dentro da instalação |
| --- | --- |
| Hardware | `data/public/devices.yml` |
| Modelo inicial, usado somente se faltar o arquivo de hardware | `data/public/devices.yml.example` |
| Receita-base | `data/public/receita_base.yaml` |
| Catálogos de receitas | `data/public/receita.json`, `data/private/receita.json` |
| Receita selecionada | `data/active_recipe.txt` |
| Estado da execução | `data/private/recipe_state.json` |
| Configurações locais de controle | `data/private/control_settings.json` |
| Padrões de fábrica | `data/control_defaults.json` |
| Fallback legado | `recipe.yml` na raiz do projeto |

O diretório do estado é criado se estiver ausente. Dados privados e arquivos locais
já existentes não são substituídos ao criar a configuração inicial.

## Windows: teste simulado

Ative a venv e mantenha `backend: simulated` no `devices.yml`. Exemplos PowerShell:

```powershell
python "C:\Projetos\Tesseract Device Bridge\run_bridge.py" --debug
python "C:\Projetos\Tesseract Device Bridge\run_panel.py" --debug
```

Esses comandos podem ser executados em outra pasta; encontram os dados junto aos
scripts. O boot log fica em `logs/boot.log` dentro da instalação. Não tenta criar
um diretório `C:\var\log`.

Em YAML escrito manualmente, prefira barras normais ou aspas simples:

```yaml
base_path: "C:/Projetos/Teste sensores"
# Alternativa:
# base_path: 'C:\Projetos\Teste sensores'
```

Evite caminhos Windows com barras invertidas dentro de aspas duplas: `\U` pode
ser interpretado como escape Unicode. O teste do DS18B20 usa `as_posix()`.
Um `base_path` de teste não deve ser levado ao Raspberry Pi: remova-o para usar
o barramento real. O backend real com GPIO físico é destinado ao Raspberry Pi;
os testes de backend no Windows usam mocks.

## Raspberry Pi: operação real

Use `backend: real`, os pinos corretos, polaridade `active_high` e endereços ROM reais.
O DS18B20 usa `/sys/bus/w1/devices/<address>/w1_slave`; esse caminho Linux é intencional.
O overlay 1-Wire fica em `/boot/firmware/config.txt` ou `/boot/config.txt`, conforme
a versão instalada do Raspberry Pi OS.

O boot log tenta `/var/log/tesseract-bridge/boot.log` e recua para `logs/boot.log`
na instalação se faltar permissão. O usuário do serviço deve poder gravar em
`data/private/`, nos catálogos que edita e no ponteiro de receita selecionada.
O instalador systemd já define `WorkingDirectory` e passa caminhos de execução
com aspas. A resolução dos padrões agora também funciona sem depender desse cwd.

Scripts `.sh` de instalação/logs são para Linux/Bash, não PowerShell. Por exemplo:

```bash
sudo bash "/home/pi/Tesseract Device Bridge/tools/install_service.sh"
bash "/home/pi/Tesseract Device Bridge/tools/logs.sh" --boot-log
```

O fallback de `logs.sh` também é relativo à instalação, e não ao terminal.

## Validação desta entrega

- Suíte completa executada no Linux: 481 testes passaram.
- Suíte executada de diretório externo: 481 testes passaram.
- Inicialização simulada do Bridge e painel em subprocessos, a partir de outro
  diretório, com instalação contendo espaços e acentos e sem `devices.yml`.
- Regressão para formato de caminho Windows no YAML e seleção de log Windows.
- Sintaxe dos scripts Bash validada com `bash -n`.

Não houve execução em Windows nativo nem em Raspberry Pi físico nesta validação.
No Windows, rode `python -m pytest -q`; no Pi, valide acesso ao GPIO e permissões
com o usuário real do serviço antes da operação.
