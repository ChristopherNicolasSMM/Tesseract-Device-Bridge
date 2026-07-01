# 02 — Primeiros Passos

## O que você vai precisar

- Raspberry Pi com a placa de controle já conectada e cabeada ao equipamento.
- Computador ou celular na mesma rede Wi-Fi que o Raspberry Pi.
- Python 3.10 ou superior instalado no Pi.

---

## 1. Instalar o sistema no Raspberry Pi

```bash
git clone https://github.com/ChristopherNicolasSMM/Tesseract-Device-Bridge.git
cd tesseract-device-bridge
pip install -r requirements.txt
```

---

## 2. Configurar o hardware (`devices.yml`)

Copie o arquivo de exemplo e edite com as informações do seu equipamento:

```bash
cp devices.yml.example devices.yml
```

Para descobrir os endereços dos seus sensores de temperatura (você vai
precisar desses endereços para preencher o `devices.yml`):

```bash
python -m gpio.ds18b20_scan
```

Isso vai listar algo como:

```
28-0000071234ab  ->  GPIO 4
28-0000059876cd  ->  GPIO 4
```

Abra o `devices.yml` num editor de texto e substitua os endereços
(`address: "28-xxx"`) pelos valores que o scan mostrou. Ajuste também
os pinos (`pin`) se a sua fiação for diferente do exemplo.

**Dica**: deixe `backend: simulated` durante os testes iniciais — assim você
pode usar o painel sem precisar da placa física ligada, pra conferir se a
receita está configurada do jeito certo.

---

## 3. Configurar a receita (`recipe.yml`)

Copie o arquivo de exemplo e adapte para a sua receita:

```bash
cp recipe.yml.example recipe.yml
```

Abra o `recipe.yml` num editor de texto. Os campos principais que você vai
querer editar:

```yaml
name: "Nome da sua receita"

vessels:
  - id: mash
    name: "Mostura"           # nome que vai aparecer na tela
    heater_device_id: mash_heater   # mesmo id que está no devices.yml
    sensor_device_id: mash_tun_temp
    pid:
      kp: 5.0
      ki: 0.1
      kd: 0.0

steps:
  - vessel: mash
    label: "Sacarificação"    # nome que vai aparecer na timeline
    target_temp: 67           # temperatura alvo em graus Celsius
    hold_minutes: 60          # quanto tempo manter nessa temperatura
    pumps: [pump_b1]          # bomba(s) que ficam ligadas durante essa etapa
    hop_alarms:
      - minutes_remaining: 60   # alerta quando faltam 60min para o fim da fervura
        label: "Lúpulo Amargor - 30g Magnum"
```

---

## 4. Primeira tela que você vai ver

Inicie o sistema:

```bash
python run_bridge.py
```

Abra o navegador no endereço `http://<ip-do-raspberry>:8088` (ou
`http://localhost:8088` se estiver usando o teclado e monitor diretamente
no Pi).

Você vai ver o painel com três abas:

- **Painel** — lista de todos os sensores e atuadores, com os valores ao vivo.
  Útil pra confirmar que o sensor está lendo certo e o relé responde.
- **Gerenciamento** — inventário dos devices configurados.
- **Receitas** — aqui é onde você vai usar o sistema durante a brassagem.

**Primeiro teste recomendado antes de usar na brassagem de verdade**: na aba
Painel, clique no botão de ligar/desligar de cada atuador e confirme que o
relé na placa responde. Verifique também que os sensores estão mostrando
temperaturas plausíveis.

---

## 5. Configurar o som dos alarmes

Na aba Receitas, clique no botão **⚙️ Alarmes** (canto superior direito).

- **Som**: escolha entre Beep, Sirene ou Campainha, ou faça upload de um
  arquivo de áudio próprio.
- **Repetições**: quantas vezes o som toca antes de parar sozinho. O som
  também para se você clicar em "OK" antes de terminar as repetições.

Clique em "Testar som" para ouvir como vai ficar.

Essas configurações ficam salvas no seu navegador — não precisa refazer toda
vez que abrir o painel.
