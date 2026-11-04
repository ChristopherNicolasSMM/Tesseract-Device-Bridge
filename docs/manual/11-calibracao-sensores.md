# Calibração individual de temperatura (Device Bridge)

## Ambiente de execução do Raspberry Pi

No Raspberry Pi com GPIO real, o Bridge aceita **Python 3.9.x dentro da venv**,
sem substituir o Python do sistema. O instalador do serviço systemd verifica
a versão e recusa versões diferentes de 3.9; `run_bridge.py` e
`run_panel.py` também verificam antes de abrir o backend real.
O backend `simulated` pode continuar em outras versões para desenvolvimento.

Verifique no dispositivo:

```bash
cd ~/Tesseract-Device-Bridge
source venv/bin/activate
python --version
python -m pytest tests/test_temperature_calibration.py tests/test_python_runtime.py -q
```

## Parâmetro de correção

Para cada sensor de temperatura: **temperatura corrigida = temperatura bruta + offset (°C)**.

- Calibre os sensores **individualmente**, usando termômetro de referência confiável,
  imersão adequada e agitação, com temperatura estabilizada perto da faixa de mostura.
- Exemplo: referência 67,0 °C e sensor 64,9 °C ⇒ offset **+2,1 °C**.
- Uma única leitura não demonstra linearidade: repita a verificação em mais de um ponto.
- Valores aceitos: **-5,0 a +5,0 °C**. Correção grande requer investigar montagem,
  alimentação, imersão e posicionamento antes de liberar a produção.
- Não confunda diferença de leitura com problema de controle, mistura desigual ou
  atraso térmico do sensor.

Acesse **Configurações → Calibração dos sensores**. Cada cartão mostra leitura
bruta, corrigida, offset ativo, offset a aplicar e identificação física ROM.
Altere apenas os sensores calibrados e clique em **Salvar offsets**.

O arquivo `data/private/sensor_calibration.json` é persistido atomicamente,
ignorado pelo Git e vinculado ao ID do dispositivo **e** endereço físico DS18B20.
Se o ROM mudar, o Bridge recusa iniciar até a calibração ser revista, evitando
reutilizar o ajuste do sensor antigo.

O ajuste é carregado **uma única vez no boot**. Após salvar, encerre qualquer
sessão, mantenha atuadores desligados e reinicie o Bridge conscientemente.
O ajuste nunca é aplicado no meio de uma receita em andamento.
Se houver erro de leitura, o bloqueio de emergência continua ativo.

O `DeviceRuntime` fornece temperatura corrigida como `value` para PID, rampas,
alarmes, interface, MQTT e fonte auxiliar. `raw_value` preserva a leitura anterior
à correção para diagnóstico. Para o corte de sobretemperatura da fonte GLP,
prevalece o maior valor entre bruto e corrigido. O circuito de proteção física
da combustão permanece independente do software.

A calibração não reescreve históricos nem garante por si só a FG planejada.
Antes da próxima brassagem, valide ambos os sensores com a nova leitura
e execute teste térmico com água, sem gás.
