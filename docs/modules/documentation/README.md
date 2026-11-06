# Módulo reutilizável de documentação

Código: `reusable/documentation/`. Adaptador do Bridge: `shared_ui/documentation.py`.
O mesmo módulo atende painel, configuração inicial e setup, sem ORM, GPIO ou MQTT.

## Arquitetura

| Componente | Responsabilidade |
| --- | --- |
| catalog.py | Escopo publicado, catálogo limitado, categorias e busca sem acentos |
| render.py | Markdown, sanitização HTML e reescrita de links/imagens locais |
| web.py | Blueprint Flask de consulta; autorização fornecida pelo host |
| templates/documentation/page.html | Navegação, busca, leitor e sumário |
| static/documentation.css | Layout responsivo e temas claro/escuro |
| shared_ui/documentation.py | Pastas, categorias, atalhos e política pública do Bridge |

O catálogo usa apenas stdlib. Renderização carrega Python-Markdown e Bleach sob
demanda; o adaptador web carrega Flask. Não há consulta à rede para renderizar,
ler ou pesquisar. Links externos são ações explícitas do usuário.

## Integração em outro projeto

```python
from reusable.documentation import DocumentLibrary
from reusable.documentation.web import register_documentation

library = DocumentLibrary(
    '/caminho/do/projeto',
    folders=('docs',),
    files=('README.md',),
    categories=(('docs/manual/', 'Manuais'), ('docs/technical/', 'Técnica')),
)
register_documentation(app, library, url_prefix='/help', authorize=minha_regra_de_leitura)
```

`authorize()` retorna `True`/`None` para permitir, `False` para recusar com 403 ou
uma resposta Flask para redirecionar ao login do host. A regra vale para páginas,
catálogo, download e assets. O host controla autenticação, autorização e quais
pastas podem ser publicadas. O Bridge fornece documentos públicos do repositório;
se for reutilizar em um projeto com arquivos privados, configure a regra antes
de registrar o blueprint. Cada app registra este blueprint uma vez.

O extra opcional é `documentation` no pacote `reusable/`, versão 0.2.0:

```bash
python -m pip install './reusable[documentation]'
```

Ao usar código diretamente, instale Flask, Markdown e Bleach conforme os limites
de versão de `requirements.txt`. Inclua templates e CSS ao distribuir o módulo;
o `pyproject.toml` já declara esses recursos.

## Contratos HTTP

| Método e rota | Resultado |
| --- | --- |
| GET /help/ | Início, ou leitor com `doc`, busca com `q` e filtro `category` |
| GET /help/catalog | Caminho, título e categoria dos documentos publicados |
| GET /help/raw?doc=... | Download de Markdown permitido como texto |
| GET /help/image?path=... | Imagem raster permitida |
| GET /help/assets/documentation.css | CSS distribuído no pacote |

Nenhuma rota escreve dados. Parâmetros não escolhem a raiz publicada. Documentos
fora do escopo, dotfiles, `..`, links simbólicos/junctions e formatos incompatíveis
são recusados. O padrão limita o catálogo a 256 documentos, cada um a 512 KiB,
o total a 16 MiB e a busca a 40 resultados. A varredura tem limite de entradas;
arquivos indisponíveis não interrompem a listagem. Valores podem ser adaptados na
instanciação do catálogo; revise também o orçamento para imagens.

## Renderização e fronteiras

Python-Markdown fornece títulos, `toc`, `tables` e `fenced_code`. Bleach restringe
HTML a uma allow-list sem eventos, scripts, formulários ou estilos embutidos.
A etapa seguinte reescreve links relativos somente para documentos publicados e
imagens locais permitidas. Protocolos externos aceitos para links são HTTP, HTTPS
e mailto, com `noopener noreferrer`; não há imagens externas, SVG ou fetch de
URLs remotas no servidor. Conteúdo de código é texto. O viewer envia CSP sem
scripts, `nosniff`, `no-store` e política de referrer restritiva.

O módulo possui tratamento de erros próprio: falhas na consulta retornam 503
sem invocar o tratador global de falhas de hardware. O iframe do painel permite
navegação/formulários GET e popups, mas não scripts. A central também é utilizável
como página independente. Não há edição nem execução de código presente nos guias.

Testes: `tests/test_documentation.py`. Execução e validação visual ficam com o
mantenedor. Fontes dos componentes de renderização:
[Python-Markdown](https://python-markdown.github.io/extensions/) e
[Bleach](https://bleach.readthedocs.io/en/latest/clean.html).
