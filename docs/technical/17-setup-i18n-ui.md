# 17 — i18n, layout e recursos compartilhados

Referência atual: setup.12. Catálogos `setup/translations/pt_BR.json` e `en.json`
alimentam Jinja, mensagens HTTP/JS e exibição de eventos. Idioma e tema ficam no
manifesto; códigos de evento e dados persistidos não são traduzidos. O painel
operacional não foi integralmente traduzido por esta entrega.

## Composição visual

| Fonte | Uso |
|---|---|
| reusable/guided_setup/templates/guided_setup/base.html | Estrutura genérica, blocos e navegação |
| reusable/guided_setup/static/theme.css | Tokens e controles compartilhados |
| reusable/guided_setup/static/wizard.css | Layout responsivo claro/escuro |
| setup/templates/base.html | Marca, breadcrumb, scripts e modal do Bridge |
| setup/static/setup.css | Overrides específicos do produto |
| setup/static/setup.js | Envio de formulários, feedback de processamento e prévia |
| shared_ui | Adaptador que preserva /shared-ui/theme.css para os consumidores |

O registro `register_wizard_ui` recebe WizardStep e disponibiliza os recursos em
`/wizard-assets/`. Não inicializa runtime ou banco. O tema tem uma única fonte;
não copie estilos para cada aplicação. Recursos são locais, sem CDN obrigatória.
Blocos de marca, conteúdo, scripts e estilos permitem customizar outro produto.

## Fluxo e segurança

A navegação marca a etapa atual, mas não concede autorização. Rotas validam
estado e pré-requisitos no servidor. POST de aparência mantém CSRF/origem.
JS trata o redirecionamento JSON do setup e usa textContent para prévias e erros;
a CSP não depende de scripts executáveis inline. O indicador de processamento
não apresenta percentual fictício de progresso.

O grid suporta seleção, upload e modal JSON/YAML, com mascaramento e limites.
Uploads sucessivos acrescentam arquivos; destino duplicado é recusado. Não há
tradução de conteúdo importado. Detalhes: [importação visual](../manual/16-importacao-navegador.md).

## Reaproveitamento e verificação

Catálogo, etapas e marca são fornecidos pelo hospedeiro. A biblioteca visual não
configura autenticação, CSRF, publicação ou migrações. Veja o
[contrato do componente](../modules/guided-setup/README.md).

```powershell
python -m pytest tests/test_setup_i18n.py tests/test_guided_setup_module.py tests/test_dark_select_css.py tests/test_setup.py -q
```

Conferir visualmente temas, selects nativos Windows, foco, modal e telas pequenas.
O teste CLI mínimo inclui os três pacotes setup/shared_ui/reusable. Não registrar
aprovação visual sem execução no navegador de destino.
