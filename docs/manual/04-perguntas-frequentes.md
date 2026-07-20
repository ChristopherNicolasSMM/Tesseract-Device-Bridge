# 04 — Perguntas Frequentes

> **Navegação:** [Manual](01-introducao.md) | [Primeiros Passos](02-primeiros-passos.md) | [Funcionalidades](03-funcionalidades.md)

---

## O painel não abre no celular

Verifique se o celular e o Pi estão na mesma rede Wi-Fi. O endereço é `http://<ip-do-pi>:8088`. Para saber o IP do Pi:

```bash
hostname -I
```

Se ainda não abrir, confirme se o bridge está rodando. Deve aparecer "Painel disponível em http://0.0.0.0:8088" no terminal ou via:

```bash
sudo systemctl status tesseract-bridge
```

---

## O atuador não liga, mas `raspi-gpio` funciona

Esse é o sintoma de backend GPIO errado. O `raspi-gpio` acessa `/dev/gpiomem` diretamente — sem biblioteca Python — enquanto o bridge usa o `gpiozero`, que precisa escolher um "pin factory" (backend). Se o backend errado for escolhido, o setup funciona mas os pinos não respondem.

**Como diagnosticar:**

```bash
python tools/gpio_test.py
# Escolha [4] — mostra qual backend está ativo
```

**O que instalar conforme o resultado:**

| Backend mostrado | Problema | Solução |
|---|---|---|
| `lgpio` | No Raspbian/Bullseye, lgpio pode não ter permissão certa | `pip install RPi.GPIO` |
| `RPi.GPIO` | Deveria funcionar — checar permissão | `sudo usermod -a -G gpio $USER` (logout e login) |
| `default automático` | Nenhum backend instalado | `pip install RPi.GPIO` |

**Testar pino específico:**

```bash
python tools/gpio_test.py
# [1] Testar saída → pino 17 → active_high: true → modo manual
```

Se o relé não responder nem com o gpio_test, o problema pode ser permissão de acesso ao GPIO (`sudo` resolve temporariamente para confirmar):

```bash
sudo python tools/gpio_test.py
```

---

## O sensor está mostrando temperatura errada ou zero

**1. Endereço errado no `devices.yml`:**

```bash
python -m gpio.ds18b20_scan
```

Compare os endereços com o que está em `devices.yml`. Se diferente, corrija e reinicie o bridge.

**2. 1-Wire não habilitado:**

Verifique se existe a linha abaixo em `/boot/firmware/config.txt` (ou `/boot/config.txt` em versões antigas):

```
dtoverlay=w1-gpio
```

Se não existir, adicione, salve e reinicie o Pi.

**3. Conexão física:** verifique o cabo do sensor e o resistor pull-up de 4.7kΩ (já incluso na placa MAZZA; em sensor avulso, é necessário colocar).

---

## O que significa "Subindo" vs "Em patamar"?

- **Subindo**: o sistema está aquecendo para atingir a temperatura alvo. O cronômetro mostra o tempo decorrido.
- **Em patamar**: a temperatura alvo foi atingida e o sistema está mantendo-a. O cronômetro mostra o tempo **restante** — quando chegar a zero, avança para a próxima etapa automaticamente.

---

## O banner vermelho de queda de energia apareceu sem o Pi ter caído

Acontece quando:
- O processo foi encerrado de qualquer forma que não seja `CTRL+C` limpo (incluindo `kill -9`, corte de energia ou `sudo systemctl stop`)
- O Tesseract Core aplicou failsafe via MQTT remotamente

Isso é comportamento esperado e seguro — o sistema prefere parar tudo a retomar cegamente. Verifique fisicamente o equipamento e clique em **Retomar**.

---

## Posso pausar a brassagem e retomar horas depois?

Sim. O sistema preserva o tempo de patamar já decorrido. Mas atenção: pausar a mostura por muito tempo pode afetar o perfil enzimático — isso é uma questão de técnica cervejeira, não do sistema.

---

## O serviço não inicia no boot

Verifique se está habilitado:

```bash
sudo systemctl is-enabled tesseract-bridge
# Deve mostrar: enabled
```

Se mostrar `disabled`:
```bash
sudo systemctl enable tesseract-bridge
```

Veja os logs para entender o erro:
```bash
bash tools/logs.sh --boot
```

Erros comuns:
- `devices.yml` não encontrado → o `WorkingDirectory` do serviço precisa ser o diretório do projeto. Reinstale com `sudo bash tools/install_service.sh`.
- `ModuleNotFoundError` → o Python do serviço não tem os pacotes instalados. Se usar virtualenv, o script detecta `.venv/` automaticamente. Senão, garanta que o `pip install -r requirements.txt` foi feito com o mesmo Python que o serviço usa.

---

## O terminal de logs não abre automaticamente no boot do desktop

O arquivo de autostart do LXDE pode ter sido criado para outro usuário ou não foi criado. Verifique:

```bash
ls ~/.config/autostart/tesseract-bridge-logs.desktop
```

Se não existir, crie manualmente ou reinstale o serviço:

```bash
sudo bash tools/install_service.sh
# Responda S quando perguntar sobre autostart LXDE
```

---

## O som do alarme não toca

Navegadores bloqueiam áudio automático até o usuário interagir com a página. **Solução**: clique em qualquer lugar na página após abrir o painel — isso desbloqueia o áudio. Ou use **⚙️ Alarmes → Testar som** logo após abrir, que serve como primeiro clique.

---

## Como adiciono uma nova receita?

Edite o `recipe.yml` e reinicie o processo. O bridge carrega um arquivo de cada vez — para trocar de receita, substitua o conteúdo do `recipe.yml` e reinicie:

```bash
sudo systemctl restart tesseract-bridge
```

Valide a receita antes de reiniciar:

```bash
python3 -c "
from config import BridgeConfig
from recipe_engine.models import Recipe
config = BridgeConfig.load('devices.yml')
recipe = Recipe.load('recipe.yml', config)
print('OK:', recipe.name, recipe.step_count(), 'etapas')
"
```

---

## Posso usar sem o Tesseract Core / sem MQTT?

Sim. No `devices.yml`:

```yaml
mqtt:
  enabled: false
```

O painel, o motor de receita e todos os alarmes funcionam normalmente. Você só perde a integração com o servidor Tesseract (histórico, RBAC, sync de receitas). Para brassagem caseira autônoma, não faz diferença nenhuma.
