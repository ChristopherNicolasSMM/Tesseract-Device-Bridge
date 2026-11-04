# 14 — Diagnóstico de hardware | Device Bridge 2.0.0

> **Disponibilidade:** branch `feature/sqlite-full-migration`,
> interface Gerenciamento → Administração SQLite, após autenticação.
> O hardware real **não** é acionado pela área de diagnóstico.

## 1. Scanner de sensores DS18B20

O botão **Buscar sensores e ler temperatura** chama a leitura 1-Wire
existente (`gpio.ds18b20_scan.scan_with_readings`), sem alterar
a configuração ou executar comandos em GPIO. No Raspberry Pi:

1. Conecte o sensor DS18B20 ao barramento 1-Wire.
2. Habilite o overlay `dtoverlay=w1-gpio` no Raspberry Pi OS e reinicie.
3. Abra Gerenciamento, desbloqueie com token e clique no scanner.
4. Confira temperatura, erro CRC, ROM ID (`28-xxxxxxxxxxxx`)
   e vínculo com dispositivo existente.
5. Escolha **Usar ROM** na linha desejada: o endereço é preenchido
   no dispositivo atualmente selecionado.
6. Clique **Atualizar no rascunho**; depois salve e valide
   a revisão para o próximo reinício seguro.

O scanner também funciona em um Raspberry Pi com backend simulado:
as leituras 1-Wire são **observacionais**. Em Windows comum, sem
filesystem 1-Wire, a lista estará vazia.

## 2. Cadastro com referências válidas

Os campos **Sensor térmico** e **Controlador PID** agora utilizam
selectboxes derivados dos dispositivos cadastrados na revisão aberta.
O controlador é apresentado a partir dos atuadores não auxiliares;
o sensor térmico, dos sensores de temperatura. Uma referência antiga
não encontrada aparece marcada como **referência desconhecida**, em
vez de desaparecer silenciosamente.

**GPIO BCM** também é um seletor, mostrando ocupação pelos
dispositivos existentes. Isso é uma informação para facilitar
cadastro, **não** aprovação automática de pinagem: o backend
continua validando colisões, usos 1-Wire e demais restrições.
**Endereço ROM** é um campo com sugestões do scanner, permitindo
digitação quando o sensor não estiver conectado.

## 3. GPIO digital, PWM e analógico

**Ler estado lógico** exibe o último valor conhecido do runtime,
não uma medição elétrica independente do nível físico.
Dispositivos já registrados como sensores analógicos aparecem
com seu valor lógico, se houver driver e ADC instalados.

O Raspberry Pi **não possui ADC integrado**. Para medições analógicas
adicionais, é necessário hardware adequado (por exemplo MCP3008
ou ADS1115), driver e cadastro do sensor. GPIO digital BCM
não deve ser tratado como entrada analógica sem conversor.

### Teste virtual HIGH/LOW

A interface oferece uma lista de GPIO BCM **livres**, que não estejam
atribuídos a dispositivos atuais. Os comandos HIGH/LOW:

- Exigem token administrativo e
  `TESSERACT_BRIDGE_SIMULATION_ONLY=1`.
- Alteram **apenas valores em memória**, sem chamar
  `DeviceRuntime.set_actuator` ou qualquer backend GPIO real.
- Recusam pinos ocupados; não ligam resistência, bomba nem GLP.
- Bloqueiam comandos durante sessão ativa/emergência.

Essa função serve para testar formulários e a interface. **Não valida
tensão elétrica, relés, cabeamento ou funcionamento dos pinos físicos.**

### Testes físicos de GPIO

Não estão disponíveis nesta tela nesta etapa da 2.0.0. Devem ser
implementados em procedimento separado, com cargas fisicamente
isoladas, autorização adicional, limitação temporal, watchdog,
pino permitido explicitamente e retorno garantido a OFF.
A válvula de gás deve preservar o corte externo independente
de chama; nunca deve poder ser acionada pelo diagnóstico genérico.

## 4. Monitor serial de leitura

Clique **Listar portas seriais**, escolha uma porta detectada e o
baud rate, depois **Ler até 1024 bytes (somente leitura)**.
As rotas exigem token administrativo e não oferecem transmissão
de dados, comandos arbitrários ou monitoramento contínuo.

- O monitor utiliza `pyserial`, incluído em `requirements.txt`.
- As portas precisam constar da enumeração do sistema operacional.
- Cada leitura tem timeout de 200 ms e máximo de 1024 bytes.
- Abrir uma porta USB/serial **pode reiniciar alguns
  microcontroladores**, mesmo sem enviar comandos. Use somente quando
  o dispositivo conectado puder ser interrompido com segurança.

## 5. Segurança e limitações

Todo diagnóstico fica sob `/api/admin/diagnostics/*`, herdando o
token e o bloqueio de emergência administrativo. Não exponha o painel
à Internet. O token não substitui autenticação de usuários, proteção
CSRF e rede protegida numa futura implantação em produção.

Para verificar uma mudança real de hardware, use plano de homologação
separado, com as saídas físicas isoladas e os mecanismos de segurança
do Device Bridge acionados.
