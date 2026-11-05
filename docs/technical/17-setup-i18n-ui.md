# Etapa 5 — i18n e identidade compartilhada

Catálogos pt_BR/en com paridade de chaves; mensagens Jinja, JSON HTTP e eventos
de importação possuem códigos estáveis e tradução para exibição. O CLI aceita
--language. Idioma continua no manifesto da tentativa; dados persistidos e
identificadores de eventos não são traduzidos. Não há JavaScript no núcleo
atual: as telas usam formulários POST com CSRF e requisição completa.

shared_ui é um pacote estático sem dependência de painel/runtime. Extrai os tokens
CSS e as regras de select existentes do HTML do painel para theme.css, servido
por blueprint independente. Painel e setup carregam a mesma fonte de tokens.
O CSS específico do painel permanece no HTML, preservando o layout operacional.
Componentes bridge-card/button/field servem como base do assistente.
Tema claro é opt-in no setup; painel mantém seu tema escuro atual.
Não foi feita tradução completa do painel operacional, fora do escopo desta etapa.

Aparência usa POST protegido e persiste no manifesto; não inicia hardware nem
altera configuração operacional. CSP continua sem scripts inline. O assistente
tem layout responsivo, labels, foco visível e mensagens de sucesso/erro traduzidas.
Grid, prévia/modal e upload por navegador pertencem à Etapa 6.

Testes escritos e não executados pelo assistente, conforme autorização.
Validar temas e selects também visualmente no Windows/Chromium.

python -m pytest tests/test_setup_i18n.py tests/test_setup.py tests/test_dark_select_css.py tests/test_panel.py -q
python -m pytest -q
python -m setup

Revisar idioma, aparência clara/escura, persistência após reinício, CSRF,
legibilidade do painel e abertura sem .env/banco. O teste de clone mínimo agora
copia setup/ e shared_ui/, sem storage ou runtime.
