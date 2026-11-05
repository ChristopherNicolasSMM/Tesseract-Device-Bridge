# 07 — Organização dos módulos Python | 2.0.0

Referência: branch feature/sqlite-full-migration, setup.11. O clone mantém layout
flat para executar entrypoints diretamente, sem exigir instalação do Bridge como
wheel. O pyproject.toml da raiz configura ferramentas; o de reusable/ define
somente a distribuição opcional dos componentes independentes.

## Pacotes e fronteiras

| Local | Responsabilidade | Dependências permitidas |
|---|---|---|
| reusable/serial_monitor | Conexão serial, sessão, limites e expiração | stdlib; pyserial carregado sob demanda |
| reusable/guided_setup | Configuração, persistência, layout e navegação | stdlib; extras opcionais dotenv/Flask |
| setup/ | Assistente específico do Bridge, migração e publicação | Componentes genéricos e domínio sob demanda |
| shared_ui/ | URL de compatibilidade para os recursos visuais | Estáticos do componente guiado; sem runtime |
| tesseract_bridge/infrastructure | Ambiente, caminhos e guarda de publicação | Não inicializa hardware ao importar |
| tesseract_bridge/control e safety | Controle, prioridades e failsafe | Contratos do runtime |
| tesseract_bridge/diagnostics | Adaptação de diagnóstico para o domínio | Núcleo serial, configuração e leitura 1-Wire |
| tesseract_bridge/integrations | MQTT e status externos | Inicialização explícita pelo processo operacional |
| storage/ | Router, ORM, migrações, importadores e compatibilidade | Não depende de tela Flask para persistir |
| panel/ | HTTP operacional/administrativo e apresentações | Serviços de domínio; autorização no adaptador |
| gpio/ e recipe_engine/ | Backends e execução de receitas | Fluxo operacional, fora do instalador |

Entrypoints preservados: run_bridge.py, run_panel.py e python -m setup.
BridgeConfig permanece em config.py e DeviceRuntime em device_runtime.py.
A fachada data/ resolve receitas no banco; arquivos legados servem ao importador.

## Direção de dependências

O hospedeiro importa os módulos reutilizáveis; eles não importam config, storage,
panel, setup, device_runtime, GPIO ou MQTT. Integrações específicas não devem ser
adicionadas ao núcleo genérico. Scripts do produto permanecem nos adaptadores.
[Guia de arquitetura e integração](../modules/arquitetura.md).

O monitor HTTP usa panel/admin_diagnostics.py e compartilha apresentação entre
index.html e configuration.html por _serial_monitor.html e serial-monitor.js.
O callback HTTP da tela fornece autenticação ao componente visual. O backend
não precisa de cadastro ORM para enumerar/abrir uma porta.

No setup, state.py preserva schema/staging e delega lock/gravação JSON. A base
Jinja do produto estende guided_setup/base.html. CSS do tema fica no componente;
/shared-ui/theme.css continua disponível sem duplicar a fonte dos estilos.

## Distribuição e cópia mínima

Outro projeto pode instalar `./reusable[serial,wizard]`, com os extras necessários.
Isso não instala o runtime do Bridge nem transporta migrações e arquivos privados.
Para iniciar o setup isolado deste produto, são necessários setup/, shared_ui/ e
reusable/. O teste de CLI copia esses três pacotes e omite storage/runtime/GPIO.
Copiar somente setup/ deixa de ser uma instalação válida desse assistente.

## Verificação

```powershell
python -m pytest tests/test_package_layout.py tests/test_guided_setup_module.py tests/test_serial_monitor_module.py tests/test_setup.py -q
python -m pytest -q
```

A matriz CI cobre Windows/Linux e Python 3.9/3.13. Isso não certifica hardware,
permissões de porta ou systemd real; ver [homologação](../homologacao/setup-2.0.0.md).
