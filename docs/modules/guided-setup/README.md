# Setup guiado e configurações reutilizáveis

## O que foi extraído

Código: `reusable/guided_setup/`. O Bridge já utiliza essas funções, não se
trata apenas de um modelo para extração futura.

| Arquivo | Contrato genérico | Adaptador no Bridge |
|---|---|---|
| persistence.py | FileLock e atomic_json_write | setup/state.py |
| configuration.py | host_name, port_number, probe_bind, update_env | setup/infrastructure.py e security.py |
| folders.py | Listagem limitada de pastas/unidades, sem ler arquivos | setup/browser_import.py |
| web.py | WizardStep e register_wizard_ui | setup/app.py |
| templates/guided_setup/base.html | Layout Jinja com blocos e navegação | setup/templates/base.html |
| static/theme.css e wizard.css | Tema compartilhado e layout offline | shared_ui e setup |

O pacote base usa stdlib. `update_env` carrega python-dotenv quando chamado;
o adaptador visual carrega Flask ao registrar a UI. Sem o extra `wizard`, as
funções de persistência continuam utilizáveis. Não há importação de SQLAlchemy,
GPIO, MQTT ou inicialização do runtime.

## Configuração independente de produto

```python
from reusable.guided_setup.configuration import (
    host_name, port_number, probe_bind, update_env,
)

host = host_name('127.0.0.1')
port = port_number('8050')
print(probe_bind(host, port, reserved_ports=(8090,)))
candidate = update_env('# Preserve comentários\nCUSTOM=keep\n', {
    'MYAPP_HOST': host,
    'MYAPP_PORT': port,
})
```

Não há prefixo `TESSERACT_BRIDGE_`, caminho de banco ou campos obrigatórios no
núcleo. `ConfigurationError` informa valores inválidos. `probe_bind` só testa
bind em IP literal e não consulta DNS; hostname/IP não local gera
`port_unchecked`, porta ocupada/reservada gera erro. O teste libera imediatamente
o socket e **não reserva** a porta para uma publicação futura.

`update_env` preserva linhas não alteradas e comentários, substitui apenas
chaves informadas e elimina duplicatas dessas chaves. Chaves devem ser nomes
ASCII de variáveis. Valores aceitos são literais simples sem espaços, `$`, aspas,
quebras de linha ou NUL. Para valores complexos, o adaptador deve implementar
serialização adequada, como Base64 para tokens; Base64 não é criptografia.
O núcleo não escreve `.env`, não interpola valores e não gera credenciais.

## Persistência e retomada

```python
import json
from pathlib import Path
from reusable.guided_setup.persistence import FileLock, atomic_json_write

private = Path('var/private/install')
private.mkdir(parents=True, mode=0o700, exist_ok=True)
lock = FileLock(private / 'lock')
try:
    path = private / 'state.json'
    previous = json.loads(path.read_text()) if path.exists() else {'version': 1, 'stage': 'new'}
    # O produto valida schema/versão e decide a transição antes de gravar.
    updated = dict(previous, stage='configure')
    atomic_json_write(path, updated)
finally:
    lock.close()
```

O hospedeiro deve validar diretórios privados, rejeitar links de diretório,
validar JSON lido e guardar o lock durante toda a tentativa. A função de gravação
rejeita destino symlink, usa temporário privado, fsync e replace, e limpa o
temporário em erro. Em POSIX também sincroniza o diretório. Ela não escolhe os
estados, não limpa staging e não publica banco/configuração como transação.
No Bridge, essas responsabilidades continuam em `InstallationState` e
`setup/publication.py`; o formato anterior do manifesto é preservado.

## Assistente Flask em outro projeto

```python
from flask import Flask, render_template
from reusable.guided_setup.web import WizardStep, register_wizard_ui

app = Flask(__name__)
register_wizard_ui(app, [
    WizardStep('language', '/', 'language_step'),
    WizardStep('network', '/network/', 'network_step'),
])

labels = dict(title='Instalação do meu produto', security_note='Acesso local',
    badge='Instalação', progress='Etapas', language_step='Idioma',
    network_step='Rede', staging_only='Alterações temporárias', prepare='Configurar',
    stop='Encerre o servidor após concluir', processing='Processando')

@app.get('/network/')
def network():
    return render_template('network.html', t=labels, language='pt_BR',
                           theme='light', build='1.0')
```

Crie `templates/network.html`:

```jinja2
{% extends 'guided_setup/base.html' %}
{% block brand %}Meu produto{% endblock %}
{% block heading %}Configurar rede{% endblock %}
{% block content %}
<section class="bridge-card">Formulários e mensagens do seu projeto.</section>
{% endblock %}
```

Implemente também a rota `/` ou ajuste os caminhos de navegação. `WizardStep`
recebe chave estável, URL local e chave de tradução. As etapas são fornecidas
pelo hospedeiro; não há sequência de importação de brassagem embutida. A
navegação marca a etapa atual, **não autoriza ações nem garante pré-requisitos**.

Blocos disponíveis: `brand`, `breadcrumb`, `heading`, `content`, `dialogs`,
`theme_styles`, `extra_styles` e `scripts`. O tema padrão e layout usam recursos
locais em `/wizard-assets/`; não exigem CDN. O Bridge sobrescreve a marca e usa
`/shared-ui/theme.css`, apontando para a mesma fonte CSS do pacote. Scripts de
upload/importação do Bridge permanecem em `setup/static/setup.js`.

O template recebe `t`, `language`, `theme`, `build`. Traduções são catálogos
fornecidos pela aplicação, não hardcoded no núcleo. Formulários devem receber
CSRF e implementá-lo no servidor. Registro da UI não configura chave de sessão,
autenticação, política de origem, bind local ou limites de upload. O exemplo
mostra somente apresentação; não publique um instalador externo com formulários
mutáveis sem implementar essas políticas.

## Responsabilidades que continuam no produto

- Schema/estados, dependências das etapas, retomada e cancelamento seguros.
- Credenciais, autenticação, proteção CSRF e validação de origem/Host.
- Migrações, cópias, staging, relatórios e integridade dos dados.
- Publicação controlada de banco + configuração e rollback.
- Integração com serviços do SO e autorização para iniciar operação física.

Para reutilizar um instalador completo, implemente esses adaptadores para seu
produto. Copiar `setup/` integralmente levaria nomes, formatos e regras do Bridge;
a biblioteca permite reaproveitar os mecanismos sem essa dependência.

## Compatibilidade e validação

A CLI do Bridge continua `python -m setup`; as rotas de setup e
`/static/setup.css` continuam disponíveis. O CSS estrutural agora vem do módulo;
`setup/static/setup.css` fica reservado a overrides do produto.

`tests/test_guided_setup_module.py` cobre configuração sem prefixos do Bridge,
lock, gravação atômica e renderização em um Flask de outro projeto.
A suíte `tests/test_setup*.py` verifica os adaptadores e contratos anteriores.
A extração não altera a autorização operacional criada na etapa 9.


## Navegação de pastas (0.1.1)

`reusable.guided_setup.folders.list_folders(path)` retorna caminho resolvido,
pasta pai, raízes/unidades, nomes/caminhos de subpastas e indicador de truncamento.
Limites padrão: 200 subpastas e 2000 entradas examinadas por requisição, sem
recursão. Links simbólicos e pastas internas comuns são omitidos da listagem.
Caminho vazio começa na pasta pessoal do usuário do processo. Não abre arquivos,
não executa shell e não depende de uma interface gráfica no servidor.

A autorização é do hospedeiro. No Bridge a rota POST /import/folders exige tentativa
em andamento, cliente/Host local, origem e CSRF do setup. O resultado não cria
browser_source nem dispara descoberta/importação. Não exponha essa função como
explorador de arquivos público em outra aplicação.

## Diagnósticos reutilizáveis

`diagnostics.py` fornece `DiagnosticLog(directory, project_root=..., build=...)`,
independente de Flask, storage, MQTT e GPIO. O host garante diretório privado e
lock de processo. Use `write(stage, status, exc=..., file_hint=..., attempt=...)`
para receber um ID; `read_all()` reúne os arquivos retidos. O padrão é 1 MiB por
arquivo, com dois backups. Os arquivos são fechados ao terminar cada escrita.

A serialização de exceções omite mensagens, linhas-fonte e variáveis locais.
O host deve fornecer `stage`, `status`, `attempt` e `file_hint` como metadados
controlados, nunca conteúdo ou valores secretos. O Bridge usa apenas etapas
internas, ID da tentativa e nomes relativos reconhecidos pela migração. A API
raiseia erros de filesystem: o adaptador do host decide como preservar a falha
original sem depender da disponibilidade do log.

## Orçamento de caminhos Windows

`paths.py` fornece `compact_attempt_name(uuid_hex)` e
`require_staging_budget(directory)`. O primeiro usa Base32 minúsculo dos 128 bits
integrais; o segundo reserva 54 unidades de nome mais separador para as árvores
compactas do Bridge, medindo o caminho absoluto em UTF-16 no Windows. Um host com
outra árvore de arquivos deve adequar esse orçamento. A exceção `PathLengthError`
permite apresentar uma orientação de caminho curto sem tentar gravar o arquivo.
O adaptador mantém o layout declarado no manifesto para preservar tentativas
anteriores. Não há prefixos especiais de caminho, alterações de registro ou
realocação fora do clone.
