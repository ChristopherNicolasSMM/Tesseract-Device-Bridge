# 04 — Perguntas Frequentes

## O painel não abre no celular. O que faço?

Verifique se o celular e o Raspberry Pi estão na mesma rede Wi-Fi. O endereço
do painel é `http://<ip-do-raspberry>:8088` — substitua `<ip-do-raspberry>`
pelo endereço IP real do Pi (você pode ver o IP rodando `hostname -I` no
terminal do Pi).

Se ainda não abrir, confirme que o processo `run_bridge.py` está rodando
no Pi (você deve ver a mensagem "Painel disponível em http://0.0.0.0:8088"
no terminal).

---

## O sensor está mostrando temperatura errada ou zero.

Possíveis causas:

1. **Endereço errado no `devices.yml`**: rode `python -m gpio.ds18b20_scan`
   e compare os endereços encontrados com os que estão no arquivo. Se
   forem diferentes, corrija o `devices.yml` e reinicie o processo.

2. **1-Wire não habilitado no Pi**: verifique se `dtoverlay=w1-gpio` está
   em `/boot/firmware/config.txt` (ou `/boot/config.txt`). Se não estiver,
   adicione, salve e reinicie o Pi.

3. **Conexão física**: verifique o cabo do sensor e o resistor pull-up de
   4.7kΩ no barramento (já incluso na placa MAZZA; se usar sensor avulso,
   é necessário colocar).

---

## O que significa "Subindo" vs "Em patamar"?

- **Subindo**: o sistema está aquecendo para atingir a temperatura alvo
  daquela etapa. O cronômetro mostra o tempo decorrido desde que a etapa
  começou.
- **Em patamar**: a temperatura alvo foi atingida e o sistema está
  mantendo-a pelo tempo configurado (`hold_minutes`). O cronômetro mostra
  o tempo **restante** — quando chegar a zero, o sistema avança para a
  próxima etapa automaticamente.

---

## O banner de queda de energia apareceu sem o Pi ter caído.

Se o Pi ficou sem acesso ao broker MQTT e o Tesseract Core aplicou failsafe
remotamente, ou se o processo foi encerrado de qualquer jeito que não fosse
`CTRL+C` limpo (ex.: `kill -9`, corte de energia), o sistema detecta isso
como um "crash" ao reiniciar.

Isso é comportamento esperado e é uma funcionalidade de segurança — o sistema
prefere ser conservador e parar tudo a retomar cegamente sem que você
confirme. Basta verificar fisicamente o equipamento e clicar em **Retomar**.

---

## Posso pausar a brassagem e retomar horas depois?

Sim. Ao pausar (botão `⏯` ou "Cancelar"), o sistema desliga os aquecedores
e bombas. O estado é salvo no Pi.

**Mas atenção**: a brassagem é um processo biológico/químico. Pausar a
mostura por muito tempo pode afetar o perfil de fermentação — isso é uma
questão de técnica cervejeira, não de sistema. O sistema preserva o tempo de
patamar já decorrido, mas não pode recuperar o efeito de um resfriamento
indesejado do mosto.

---

## Como adiciono uma nova receita?

Edite o arquivo `recipe.yml` no Raspberry Pi com a sua nova receita.
Você pode criar quantas receitas quiser, mas o sistema carrega **um arquivo
de cada vez** no boot — para trocar de receita, edite (ou substitua) o
`recipe.yml` e reinicie o processo (`CTRL+C` + `python run_bridge.py`
novamente).

Para validar se a receita está correta antes de reiniciar:

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

## O som do alarme não toca.

A maioria dos navegadores bloqueia áudio automático até que haja alguma
interação do usuário com a página. Se abrir o painel e o primeiro alarme
tocar sem você ter clicado em nada antes, o som pode ser bloqueado.

**Solução**: clique em qualquer lugar na página após abrir o painel —
isso "desbloqueia" o áudio para os alarmes seguintes. A partir daí, os
alarmes tocam normalmente.

Se preferir, use a opção **"Testar som"** no menu `⚙️ Alarmes` logo após
abrir o painel — isso serve como o primeiro clique que desbloqueia o áudio.

---

## Posso usar sem o Tesseract Core (sem MQTT)?

Sim. Coloque `mqtt: enabled: false` no `devices.yml`. O painel, o motor de
receita e todos os alarmes funcionam normalmente — você só perde a
integração com o servidor Tesseract (sincronização de receitas, histórico,
RBAC). Para uma brassagem caseira autônoma, não faz diferença.
