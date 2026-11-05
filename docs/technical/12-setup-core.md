# Núcleo independente do setup

## Contrato desta entrega

`python -m setup [--port 8090]` inicia exclusivamente o servidor local do
assistente. `setup.app.create_app(root, port=...)` é a factory testável. Não há
import de storage, painel, DeviceRuntime, backend GPIO ou cliente MQTT. A raiz
padrão vem do arquivo do módulo, não do CWD. Esta etapa usa apenas `new` e
`in_progress`; nenhum endpoint declara a instalação pronta.

## Persistência

`InstallationState` adquire lock do SO (flock POSIX, msvcrt no Windows), mantido
até o servidor encerrar. O arquivo do lock permanece, mas um processo encerrado
libera o bloqueio do SO. O estado tem versão 1, idioma e ID UUID da tentativa.
A escrita usa arquivo privado temporário, flush/fsync e replace; POSIX também
sincroniza o diretório. A gravação antecede a criação do staging para permitir
retomar uma interrupção entre as operações. Resíduos de escrita interrompida
não são considerados instalações publicadas.

O staging está restrito a `data/private/setup/attempt-<uuid>`. Cancelamento é
idempotente e não procura bancos ou arquivos pelo disco. Diretórios base e staging
com symlinks são recusados. Corrupção/versão desconhecida falha de forma fechada,
preservando o arquivo. Windows precisa de validação local de ACLs; o modo 0700/0600
POSIX não substitui ACL Windows. Não há alterações em banco operacional ou `.env`.

## HTTP

Werkzeug make_server sem debugger/reloader, um único processo/thread atendendo
requisições, bind 127.0.0.1. Acesso requer cliente loopback e Host local explícito (`127.0.0.1`, `localhost` ou `[::1]`) incluindo
porta. Endereços IPv4 mapeados em IPv6 são normalizados antes da checagem.
O servidor CLI continua escutando em IPv4; o Host IPv6 é aceito pela factory
para transportes locais que o utilizem. Não há ProxyFix nem confiança em X-Forwarded-For. POST exige Origin igual ao Host local validado,
token CSRF de sessão assinado e cookie HttpOnly/SameSite Strict. Segredo de sessão
é aleatório por execução e não é persistido. Respostas usam no-store, CSP sem
scripts/frames externos e nosniff. Limite de corpo: 16 KiB. Não há CORS, SQL ou
shell remoto. Erros de estado/permissão não expõem caminhos em JSON.

Catálogos JSON pt_BR/en incluem as mensagens da página e erros do núcleo. Textos
traduzidos não são identificadores de estado. A consolidação visual e expansão
dos catálogos continuam previstas na Etapa 5.

## Testes

`python -m pytest tests/test_setup.py -q` cobre: factory sem dados, idiomas,
retomada, cancelamento preservando arquivos alheios, lock concorrente, acesso
remoto/proxy/Host, CSRF/Origin, estado corrompido, staging symlink, falha de
replace por permissão, CLI/porta ocupada, sentinela de imports operacionais e
processo HTTP real a partir de cópia contendo somente setup/.

O teste POSIX de symlink é explicitamente omitido em Windows quando os privilégios
adicionais necessários não estão disponíveis. O teste de permissão injeta falha
de replace para ser reproduzível inclusive em ambientes de teste privilegiados.
Não representa homologação de ACLs ou Raspberry físico.
