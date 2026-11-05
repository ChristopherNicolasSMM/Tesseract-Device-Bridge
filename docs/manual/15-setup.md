# Instalador independente — Etapa 2

O núcleo do assistente já está disponível. Esta entrega prepara uma tentativa,
seleciona idioma e permite retomada/cancelamento. Ainda não importa dados,
publica banco, escreve `.env`, instala serviço ou libera operação física.

## Executar

Na raiz do clone da branch `feature/sqlite-full-migration`, após instalar
`requirements.txt` no ambiente virtual:

Windows / PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
python -m setup
```

Linux / Raspberry Pi:

```bash
source venv/bin/activate
python -m setup
```

Abra `http://127.0.0.1:8090`. Também é permitido `http://localhost:8090`. O assistente aceita somente
hosts locais explícitos e valida a porta e a origem dos formulários. Se a porta estiver ocupada, use `python -m setup --port 8091` e abra a URL
impressa. O servidor fica limitado a loopback, sem debugger ou reloader, e não
carrega o painel operacional, GPIO, MQTT ou variáveis do `.env`.

Para acessar um Raspberry a partir de outro computador, mantenha o assistente
no Pi e abra um túnel no computador:

```bash
ssh -N -L 8090:127.0.0.1:8090 usuario@raspberry
```

Abra `http://127.0.0.1:8090` no computador. Use a mesma porta nos dois lados
para manter a validação de origem. Não publique o setup por proxy ou na rede.

## Estado e cancelamento

Continuar salva idioma e inicia/retoma a mesma tentativa. Ctrl+C encerra o
servidor e preserva o estado. Reinicie o comando para retomar; a sessão HTTP
é nova a cada execução. Somente um processo do instalador pode operar por vez.

Cancelar remove somente o diretório temporário identificado pela tentativa e
volta ao estado inicial. Outros arquivos, bancos e instalações ficam preservados.
O manifesto e o lock ficam em `data/private/setup/`, fora do Git. Não edite esses
arquivos manualmente. Estado corrompido ou de versão desconhecida impede o
início e é preservado para diagnóstico. Falta de permissão exige corrigir o
acesso do usuário ao clone; o servidor não precisa executar como root.

## Continuidade

O bloqueio experimental ORM será substituído, nas próximas entregas, pela
verificação de conclusão válida do setup. Não haverá uma etapa extra obrigatória
de homologação depois do setup para liberar o ORM real. Escolha simulada,
pendências críticas e configuração incompleta continuam bloqueando operação
física. Os intertravamentos operacionais serão preservados.

## Preparação vazia — Etapa 3

Após iniciar a tentativa, o botão de preparar banco vazio cria o ORM no diretório
privado temporário da tentativa. Aplica Alembic até 0003 e configura cabeçalhos
simulados, MQTT desativado e perfis de controle padrão. Nenhum dispositivo ou
receita fictícia é criado. Repetir a ação verifica o banco sem sobrescrevê-lo.
Cancelar descarta o staging. O banco definitivo e o .env ainda não são publicados.
A ausência de dispositivos continua impedindo iniciar o runtime operacional.
