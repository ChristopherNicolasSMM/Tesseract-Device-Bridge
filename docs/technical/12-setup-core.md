# 12 — Núcleo e fronteira HTTP do setup

Referência atual: setup.12. A entrada `python -m setup [--port 8090]` utiliza
`setup.app.create_app(root, port=...)`. O assistente não importa módulos que
inicializam painel operacional, DeviceRuntime, GPIO ou MQTT ao abrir.
Os serviços ORM são carregados quando a ação de bootstrap/importação/publicação
os exige. A raiz padrão deriva do módulo, não do CWD.

## Núcleo genérico e adaptador

| Camada | Responsabilidade |
|---|---|
| reusable.guided_setup.persistence | FileLock do SO e gravação JSON atômica |
| reusable.guided_setup.configuration | Host/porta, teste de bind e atualização dotenv |
| reusable.guided_setup.web + templates/static | Navegação configurável, layout Jinja e CSS offline |
| setup.state.InstallationState | Schema versão 1, UUID de tentativa, staging, transições e cancelamento |
| setup.app | Sessão, origem/CSRF, limites HTTP, rotas e regras específicas do produto |
| setup.publication/finalize | Recibo, publicação, recuperação, revalidação e serviço |

O núcleo genérico não interpreta estados do Bridge nem publica arquivos de
produção. O adaptador mantém os estados new, in_progress, needs_review,
ready_simulated e ready_operational. A publicação registra também publishing
no recibo para bloquear boot incompleto. Veja [arquitetura consolidada](18-setup-arquitetura.md).

## Persistência e limpeza

O lock usa flock no POSIX e msvcrt no Windows, mantido durante o servidor.
O arquivo de lock pode permanecer após fechar: a exclusividade é do SO.
JSON usa temporário privado, flush/fsync, replace e fsync do diretório em POSIX.
O estado é gravado antes da criação de staging para permitir retomada.

Desde setup.19, novas tentativas usam `data/private/setup/<uuid-base32>` (26
caracteres minúsculos, preservando os 128 bits do UUID). Manifestos antigos sem
`staging_layout` continuam usando `attempt-<uuid>`; não há movimentação de
candidatos existentes. Cancelamento remove somente a
área identificada da tentativa, sem varrer o disco; symlinks de diretórios são
recusados. Se existe recibo de publicação, cancelar é bloqueado: use recuperação.
ACLs Windows e permissões do usuário continuam sendo responsabilidade do ambiente.

## HTTP

A CLI usa Werkzeug make_server sem debugger/reloader e um processo síncrono,
bind 127.0.0.1. A factory valida cliente loopback, Host local e porta; não instala
ProxyFix. Formulários exigem Origin da mesma origem ou Referer correspondente
quando Origin estiver ausente, além de CSRF. Cookies são HttpOnly/SameSite Strict,
com segredo aleatório por processo. Reiniciar exige recarregar a página.

Respostas usam no-store, nosniff, CSP e política de referência. Limites atuais:
257 MiB de corpo, 120 partes e 512 KiB de memória de campos; importadores impõem
limites menores por arquivo/formato. Não há CORS público, shell remoto ou endpoint
de leitura arbitrária. Guardas de publicação impedem ações antigas após publicar.

## Testes e distribuição

`tests/test_setup.py` cobre factory, estado, lock, origem/CSRF, imports proibidos
e CLI real. O clone mínimo do subprocesso precisa copiar **setup/, shared_ui/ e
reusable/**; runtime, storage e GPIO ficam ausentes para provar isolamento na abertura.
O teste verifica também o CSS por HTTP. O módulo reutilizável tem testes próprios
em `tests/test_guided_setup_module.py`.

Veja o [guia de integração em outro produto](../modules/guided-setup/README.md).
O sucesso da suíte não valida ACLs, GPIO ou cargas físicas; evidências e pendências
ficam na [matriz de homologação](../homologacao/setup-2.0.0.md).
