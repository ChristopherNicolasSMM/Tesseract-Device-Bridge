# 16 — Assistente visual de importação

## Atualizar e identificar a versão

Encerre o setup com Ctrl+C antes do pull. Se os recursos estiverem ausentes, confira a versão e as dependências do clone.
Não aplique patches antigos sobre esta atualização.

```powershell
git status
git branch --show-current
git pull --ff-only origin feature/sqlite-full-migration
git log -3 --oneline
Test-Path tests/test_setup_partial.py
python -m setup
```

Se o pull falhar, preserve alterações locais e resolva a divergência antes de
iniciar o setup. O terminal e o cabeçalho devem mostrar 2.0.0-setup.21.
GET /setup-version informa o mesmo identificador.
Abra http://127.0.0.1:8090 e recarregue a página após cada reinício do servidor.
O cookie é específico da porta; CSRF continua obrigatório. Origin deve coincidir;
quando ausente, exige Referer da mesma origem. Não usar proxy externo.

## Selecionar ou colar uma pasta

Em Descobrir arquivos, mantenha Pasta da instalação anterior. Cole o caminho no
campo ou clique **Selecionar pasta no servidor**. O modal permite abrir um caminho,
navegar nas subpastas, subir um nível e escolher unidade/raiz. **Usar esta pasta**
preenche o campo; depois clique Descobrir arquivos para inventariar.

Selecione a raiz da instalação antiga, que contém devices.yml ou a pasta data;
não selecione data isoladamente. O seletor mostra o sistema de arquivos do servidor
do setup. Se o servidor é o Raspberry e os arquivos estão no Windows do navegador,
use upload, não o seletor do servidor. O navegador não fornece caminhos absolutos
de pastas locais ao servidor por uma caixa de seleção nativa.

O seletor lista somente pastas, oculta diretórios internos e não lê conteúdo de
arquivos. Listagens limitadas avisam para colar caminho mais específico. Falhas de
permissão/caminho não criam uma origem nem iniciam importação.

## Inventário filtrado

A grade contém somente nomes/caminhos reconhecidos pelos adaptadores de migração:
dispositivos, receitas, controles, calibrações, sessão e seleção ativa nos locais
legados suportados. Não basta ter extensão JSON/YAML; arquivos sem papel conhecido
na migração não são candidatos. .md, código, .gitignore e .env não entram na grade.
Arquivos reconhecidos acima do limite ou com conteúdo inválido continuam sujeitos
às validações; aparecer na lista não significa ter sido importado/aprovado.

Arquivos desconhecidos continuam registrados como ignorados pelo motor/relatório,
sem conteúdo executado. Inventários de tentativas antigas também são filtrados na
exibição. Se não houver arquivo reconhecido, a tela orienta corrigir a origem ou
usar upload, e não oferece importar uma seleção vazia.

## Visual

O shell usa cabeçalho, sidebar, títulos, cartões, campos e tabelas alinhados ao
Tesseract principal, com referência a templates/core/base.html, style.css e
style_dark.css do projeto mãe. Recursos são locais/offline, sem importar o
runtime Flask do Tesseract ou depender de CDN. Cores claro: #f6f9ff, #012970,
#4154f1; dark: #0b1220, #111a2e, #334155. A apresentação usa fontes locais com
fallback, sem exigir baixar fontes. O painel Bridge existente não é alterado.
CSS/JS usam versão na URL e no-store para evitar recursos antigos em cache.

## Fluxo

1. Selecione idioma e inicie/retome a tentativa.
2. Abra Importar dados.
3. Descubra pasta antiga ou SQLite por caminho que existe no servidor, ou envie
   arquivos pelo navegador. O caminho digitado é seleção explícita de origem.
4. Revise nome/origem relativa, formato, tamanho, registros detectáveis e status.
5. Selecione arquivos e use Exibir para abrir JSON/YAML formatado em modal.
6. Importe selecionados, com opção de importação parcial explícita para YAML/JSON.
7. Revise categorias importado/advertência/erro bloqueante/ignorado.
8. Confirme revisão para voltar à página inicial ou cancele a tentativa.

Confirmar revisão não conclui instalação nem libera operação física. Continue
pelas telas Infraestrutura, Credencial e Concluir instalação.
O indicador informa requisição em processamento, sem porcentagem fictícia; logs
são apresentados ao final. Enquanto o servidor síncrono processa uma importação,
cancelamento não interrompe uma escrita em andamento: aguarde a resposta e depois
cancele para descartar staging. Interrupção do processo mantém temporários privados
para revisão/repetição, sem publicar banco definitivo.

## Arquivos e limites

- YAML/JSON: 8 MiB por arquivo, 32 MiB no conjunto.
- SQLite: 256 MiB, apenas backup consistente sem WAL/SHM/journal.
- HTTP: 257 MiB, até 120 partes; nomes/caminhos e limites internos revalidados.
- receita.json tem destino ambíguo: envie isoladamente e selecione público/privado.
- Uploads sucessivos acrescentam arquivos ao inventário privado. Destinos
  duplicados ou não reconhecidos são recusados. Selecionar uma nova origem
  explicitamente reinicia o conjunto; importações anteriores não são mescladas.
- Prévia: entrada até 256 KiB; saída até 64 KiB, sem conteúdo bruto de arquivo
  malformado. Senhas/tokens/segredos são mascarados recursivamente antes da resposta.
  Arquivos desconhecidos não têm prévia. O modal usa textContent, nunca innerHTML.
- O formulário é protegido por sessão, CSRF e origem; seleção de inventário usa
  IDs validados contra descritor persistido no manifesto privado.
- Uploads e SQLite capturado ficam privados; origem nunca é migrada no local.
- Antes da publicação, Cancelar elimina somente os temporários da tentativa.
  A importação não escreve o .env ativo; a publicação tem seu próprio protocolo.

## Validação local (não executada pelo assistente)

```powershell
python -m pytest tests/test_setup_browser_import.py tests/test_setup_partial.py tests/test_setup_i18n.py tests/test_setup.py tests/test_setup_sqlite_import.py -q
python -m pytest -q
```

Conferir temas, idioma, selects, modal, upload, erro CSRF, cancelamento, relatório,
caminhos Windows com espaços e funcionamento com arquivos no computador e setup
no Raspberry via túnel SSH. A homologação visual real permanece local.
