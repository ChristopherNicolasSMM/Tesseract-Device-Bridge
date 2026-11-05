# Setup guiado e configurações reutilizáveis

## O que foi extraído

Código: `reusable/guided_setup/`. O Bridge já utiliza essas funções, não se
trata apenas de um modelo para extração futura.

| Arquivo | Contrato genérico | Adaptador no Bridge |
|---|---|---|
| persistence.py | FileLock e atomic_json_write | setup/state.py |
| configuration.py | host_name, port_number, probe_bind, update_env | setup/infrastructure.py e security.py |
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
