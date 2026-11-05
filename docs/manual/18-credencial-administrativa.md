# Etapa 8 — Credencial administrativa e acesso local

Atualize a branch feature. O setup mostra 2.0.0-setup.8. Prepare Infraestrutura
e abra Credencial administrativa no menu. Testes escritos e não executados
pelo assistente, conforme autorização do usuário. A sintaxe dos arquivos Python e\nos catálogos JSON foi verificada antes da publicação.

## Opções

1. Gerar token: usa secrets.token_urlsafe(32). O valor é exibido uma única vez
   na sessão local. Copie-o; não é salvo no cookie. Ao reiniciar o setup perde-se
   a exibição temporária; gere outro se necessário.
2. Token personalizado: qualquer valor não vazio é aceito, inclusive curto,
   sem regra de complexidade. Valores menores que 16 caracteres recebem aviso.
   Limite de 4096 bytes UTF-8; CR, LF e NUL são recusados para evitar configurações
   incompatíveis. Tokens fracos facilitam acesso indevido a quem alcançar o painel.
3. Sem token: exige confirmar explicitamente administração apenas local.

A credencial é preparada em arquivo .env privado imutável no staging. Não muda o
.env ativo. O manifesto contém somente modo, aviso de fraqueza e caminho do candidato.
O candidato só será publicado na Etapa 9. Alterar infraestrutura invalida a escolha
de credencial anterior para evitar publicar uma configuração desatualizada.

## Representação e compatibilidade

O setup grava ADMIN_TOKEN vazio e ADMIN_TOKEN_B64 com o valor serializado em base64,
evitando interpolação de caracteres como ${VAR} no dotenv e suportando Unicode.
Base64 NÃO é criptografia: esse arquivo é um segredo e deve permanecer privado.
O runtime continua aceitando o ADMIN_TOKEN textual antigo. ADMIN_TOKEN_B64, se
preenchido, tem prioridade; codificação inválida bloqueia administração.
Nenhum token real aparece em exemplos, relatórios ou logs.

## Administração sem token

Somente quando LOCAL_ADMIN=1 foi escolhido explicitamente e não há credencial:
- bootstrap do painel força bind 127.0.0.1;
- todas as rotas /api/admin exigem cliente loopback e Host local com a porta real;
- alterações exigem sessão assinada, cabeçalho CSRF e Origin/Referer da mesma origem;
- tentativa remota, DNS rebinding, fetch cross-site e headers de proxy são recusados;
- não há confiança em X-Forwarded-For/Host ou Forwarded.

Na administração do painel, deixe o token vazio e clique Desbloquear: o frontend
obtém a sessão local e envia CSRF nas alterações. Token permanece somente na memória
JavaScript, sem localStorage. Para token personalizado Unicode, o cabeçalho é
serializado em base64 UTF-8; clientes antigos com cabeçalho textual continuam aceitos.

Instalações antigas sem token e sem LOCAL_ADMIN mantêm administração desativada.
O modo com token continua aceitando clientes remotos autenticados, inclusive
integrações que usam X-Bridge-Admin-Token. Essa credencial protege a área administrativa;
a política das rotas operacionais /api e MQTT é independente e não foi alterada.
Não exponha o painel por proxy em modo local. Para Raspberry remoto, use túnel SSH
com a mesma porta nos dois lados e abra 127.0.0.1 no navegador.

Exemplo (ajuste usuário e porta conforme seu painel):
ssh -N -L 8088:127.0.0.1:8088 usuario@raspberry

CSRF/cookies são renovados após reiniciar o processo; reabra e desbloqueie a página.
Não iniciar setup ou runtime como root para contornar permissões.

## Proteções operacionais

Ausência de token não elimina intertravamentos térmicos, GLP, emergência,
sessão ativa ou aprovação de alterações de hardware. Esta etapa não remove
o bloqueio transitório ORM: ele será trocado pela conclusão válida do setup
na Etapa 9, conforme decisão do usuário.

## Validação local

```powershell
git pull --ff-only origin feature/sqlite-full-migration
python -m pytest tests/test_setup_security.py tests/test_admin_security_policy.py tests/test_sqlite_admin.py tests/test_admin_diagnostics.py tests/test_setup_infrastructure.py -q
python -m pytest -q
python -m setup
```

Validar exibição única, token curto aceito com aviso, escolha sem token confirmada,
origem/CSRF inválidos recusados, preservação do .env ativo e telas nos dois idiomas.
