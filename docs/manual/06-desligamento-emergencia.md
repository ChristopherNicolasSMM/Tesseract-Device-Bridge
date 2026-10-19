# Desligamento por falha

## Comportamento

Falhas de sensor, valores inválidos (incluindo NaN/infinito), erros de acesso GPIO,
exceções no PID/loop, falhas internas do painel/callback MQTT e exceções não
tratadas nas threads do serviço acionam o bloqueio de emergência.

1. Bloqueia novos acionamentos e zera as intenções manuais/PID.
2. Envia OFF diretamente a **todos os atuadores configurados**, inclusive bombas,
   saídas sem `is_risk` e saídas cujo `failsafe_value` não seja zero.
3. Continua tentando as demais saídas se uma falhar. Registra quais não puderam
   receber OFF; não informa que o desligamento físico foi confirmado.
4. Aborta a receita e tenta persistir o motivo em `safety_error`. Uma falha de
   gravação não impede as tentativas de desligamento.
5. Não permite reativação por comando manual, MQTT, PID, Iniciar ou Retomar
   enquanto esse processo estiver bloqueado. Corrija a causa antes de reiniciar.

O desligamento de emergência ignora a janela de potência; as variações normais
continuam obedecendo à janela existente. OFF é um comando lógico: `active_high`
continua sendo respeitado pelo backend, inclusive em relés ativos em nível baixo.

A thread do DS18B20 notifica a primeira falha detectada (incluindo CRC e erro de
arquivo) e deixa a leitura bloqueada até reinicialização. Não usa o último valor
bom para mascarar falhas, mesmo que leituras posteriores recuperem. O limite de
idade do cache continua detectando ausência de atualização. Leituras bloqueadas
no sistema operacional são detectadas pelo envelhecimento do cache quando o
runtime o consulta; o loop consulta todos os sensores mesmo com MQTT desabilitado
ou sem receita ativa.

Encerramento normal, Ctrl+C e SIGTERM executam OFF antes da desconexão MQTT e
liberação do GPIO. A inicialização prepara as saídas desligadas antes de abrir
os sensores e também tenta desligar/liberar tudo se a inicialização falhar.

Validações de entrada respondidas como erro de cliente (por exemplo, URL inexistente
ou formulário inválido) não são tratadas como falha do controlador.

## Diagnóstico

O painel exibe o bloqueio e o motivo quando o servidor continua disponível;
a receita abortada expõe o motivo também após reinício. `/api/status` inclui
`emergency`, `emergency_reason` e `shutdown_errors`. Depois da falha, requisições
de alteração recebem HTTP 503. A correção exige reiniciar o processo; se houver
reinício automático pelo supervisor, isso também cria um novo processo. Não há
retomada automática da receita abortada, mas novos comandos externos devem ser
controlados pelo operador após corrigir a causa.

## Limites físicos

OFF enviado por software não garante desligamento de um relé/SSR travado, de GPIO
inacessível, nem execução de limpeza após SIGKILL, falha de energia ou travamento
do sistema operacional. Esses casos dependem de proteção física independente.
As falhas de escrita são registradas explicitamente para não esconder essa situação.

## Aplicação e testes

Este patch é incremental ao patch `tesseract-device-bridge-controle-temperatura.patch`.
Não há migração de banco. Reinicie o Bridge após aplicar.

```powershell
git am --keep-cr .\tesseract-device-bridge-emergencia-e-teste-windows.patch
python -m pytest -q
```

Antes de operar com mostura, valide em bancada, sem carga térmica perigosa: acione
as saídas e provoque a desconexão de um sensor. Confira OFF físico, receita abortada
e bloqueio de novos acionamentos. A suíte usa GPIO simulado e gpiozero MockFactory,
incluindo relés ativos em nível baixo; não substitui a validação elétrica no Pi.

O teste de configuração do DS18B20 usa `tmp_path.as_posix()` para que caminhos do
Windows não sejam interpretados como escapes Unicode pelo YAML.
