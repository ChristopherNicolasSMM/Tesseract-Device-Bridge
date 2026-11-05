# Monitor serial reutilizável

## Interface no Bridge

Abra **Gerenciamento → Administração SQLite → Diagnósticos → Monitor serial**.
Desbloqueie com a credencial administrativa ou use a política local explicitamente
configurada no setup. Na instalação sem dispositivos, os mesmos controles estão na página de
configuração inicial, após informar/carregar a autorização administrativa.
O monitor atua nas portas da máquina que executa o Bridge;
o navegador não acessa a USB do computador remoto.

1. Clique **Listar portas seriais** e selecione uma porta, ou preencha **porta
   manual**. Nenhuma delas precisa estar cadastrada no banco.
2. Defina baud rate, bits de dados, paridade e bits de parada. Padrão: 9600/8N1.
3. **Testar abertura da porta** abre e fecha sem ler/enviar comandos. Sucesso
   significa que o SO permitiu abrir, não que o protocolo/dispositivo foi validado.
4. **Ler até 1024 bytes** abre, lê uma amostra e fecha.
5. **Iniciar monitor** mantém a conexão aberta; a tela solicita leituras a cada
   500 ms após a resposta anterior. Não reabre a porta a cada leitura.
6. Escolha texto UTF-8 ou hexadecimal para as próximas amostras. **Limpar saída**
   limpa somente o buffer visual; **Encerrar monitor** fecha a conexão.

A saída visual guarda os últimos 65.536 caracteres. Não há gravação automática
em arquivo, SQLite, auditoria de conteúdo ou `localStorage`. Texto usa
`textContent`; bytes inválidos em UTF-8 são substituídos visualmente e podem ser
inspecionados em hexadecimal. Trocar o formato não reinterpreta o histórico.

## Código e contrato Python

Código independente: `reusable/serial_monitor/service.py`.

```python
from reusable.serial_monitor import SerialMonitor

monitor = SerialMonitor(idle_seconds=30)
owner = object()  # identidade confiável, atribuída pelo hospedeiro
try:
    print(monitor.ports())
    print(monitor.test(owner, port='COM3', baudrate=115200))
    opened = monitor.open(owner, port='COM3', baudrate=115200,
                          bytesize=8, parity='N', stopbits=1)
    print(monitor.read(opened['session'], owner, limit=1024))
    monitor.close(opened['session'], owner)
finally:
    monitor.close_all()
```

No Linux, substitua `COM3` por `/dev/ttyUSB0` ou `/dev/ttyACM0`, por exemplo.
O hospedeiro deve chamar `close_all()` no encerramento. Há também fechamento em
`atexit` e temporizador daemon para abandono. Não dependa de `atexit` em desligamento
abrupto; o SO libera descritores quando o processo termina.

| Operação | Resultado/efeito |
|---|---|
| `ports()` | `available`, `ports` (device/description/hwid), `message`; não abre portas |
| `open(owner, port, ...)` | Sessão opaca e parâmetros efetivos; mantém conexão |
| `read(session, owner, limit)` | `text`, `hex`, `bytes_read`, porta/baud e modo read_only |
| `test(owner, port, ...)` | Abre e fecha; status opened_and_closed |
| `close(session, owner)` | Fecha somente a sessão correspondente |
| `close_owner(owner)` | Libera a conexão desse proprietário, se existir |
| `close_all()` | Libera recursos do monitor no shutdown do hospedeiro |

O construtor aceita `opener` e `enumerator` para adaptação/testes sem hardware.
A implementação padrão usa pyserial sob demanda. Erros operacionais levantam
`SerialError`, com atributo estável `code` para tradução pelo hospedeiro
(ex.: invalid_port, open_failed, monitor_busy, session_expired); a falha de enumeração retorna `available=False` e lista vazia.
A validação do núcleo não consulta o ORM nem exige enumeração prévia.

## API administrativa do Bridge

Todas as rotas estão em `/api/admin/diagnostics/serial/` e herdam a autorização
administrativa. O identificador de proprietário vem da sessão assinada do
navegador, não de um campo fornecido pelo cliente. Um segundo navegador, mesmo
com token válido, não consegue ler/fechar a sessão do primeiro.

| Método/caminho | Corpo JSON | Uso |
|---|---|---|
| GET `ports` | — | Enumeração sem abrir |
| POST `test` | port, baudrate, bytesize, parity, stopbits | Teste de abertura |
| POST `open` | mesmos parâmetros | Sessão persistente |
| POST `poll` | session, limit opcional | Amostra limitada |
| POST `close` | session | Fechamento explícito |
| POST `read` | port, baudrate | Compatibilidade com a antiga leitura pontual |

O frontend atual usa open/poll/close também para amostras pontuais, preservando
os parâmetros avançados. Erros de parâmetros, acesso, desconexão, porta ocupada
ou sessão inválida retornam 400. A guarda de sessão operacional retorna 409.
A emergência do painel operacional pode retornar 503 antes da rota; a
expiração ainda libera a conexão se o pedido de fechamento for bloqueado.
Autenticação/origem/CSRF seguem a política administrativa existente. Uma ação
serial não cria/edita dispositivos no banco.

## Limites e segurança operacional

- Apenas portas nativas: `COM1`…`COM9999`, `/dev/ttyUSBn`, `ttyACMn`, `ttyAMAn`,
  `ttySn`, `ttyTHSn`, `/dev/tty.*`, `/dev/cu.*` e `/dev/serial/by-id/...`.
  Não há URLs RFC2217/socket, shell, caminhos de arquivos arbitrários ou Web Serial.
- Baud rate inteiro 300–2.000.000; bits 5–8; paridade N/E/O/M/S; parada 1/1,5/2.
  Nem todo adaptador suporta todas as combinações: o driver decide na abertura.
- Uma conexão ativa por processo. Tentativas concorrentes são recusadas; o
  monitor não toma a conexão de outro usuário. Outros programas podem ocupá-la.
- Timeout de leitura 200 ms; limite Python/HTTP 1–4096 bytes, frontend 1024.
- Após 30 segundos sem leituras, o temporizador fecha a conexão. Ao ocultar/sair
  da página, o frontend tenta fechá-la; a expiração cobre falhas desse pedido.
- Abrir/ler/testar é bloqueado em sessão de brassagem ativa/pausada ou emergência.
  O polling revalida a guarda e fecha a sessão do proprietário quando recusado.
  O monitor não reserva o runtime nem substitui isolamento físico do equipamento.
- DTR/RTS e flow control são solicitados desligados. **Abrir ainda pode reiniciar
  microcontroladores ou provocar transientes no adaptador USB**. Isole as cargas.
- Não existe transmissão de comandos neste módulo. Para protocolos com escrita,
  implemente contrato separado, com permissões e intertravamentos próprios.

Sem pyserial, instale as dependências no ambiente correto. No Windows, confira
Gerenciador de Dispositivos/driver e feche outro terminal serial. No Raspberry,
verifique a porta e permissões do usuário do serviço (normalmente grupo `dialout`),
reinicie a sessão após alterar grupos e confirme que a UART não é console do SO.
Não rode o servidor como root para contornar uma permissão da porta.

## Validação

`tests/test_serial_monitor_module.py` cobre abertura manual sem cadastro/lista,
ownership, concorrência, formato hexadecimal, limites, expiração e falhas de USB.
`tests/test_admin_diagnostics.py` cobre autenticação e intertravamento HTTP.
A confirmação real COM/USB/UART, permissões e dispositivos continua sendo manual.
