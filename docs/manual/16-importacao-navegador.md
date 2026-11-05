# Assistente visual de importação — Etapa 6

## Atualizar e identificar a versão

Encerre o setup com Ctrl+C antes do pull. A tela sem CSS e a ausência do teste
test_setup_partial.py indicam cópia anterior às Etapas 4/5.
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
iniciar o setup. O terminal e o cabeçalho devem mostrar 2.0.0-setup.6.
GET /setup-version informa o mesmo identificador.
Abra http://127.0.0.1:8090 e recarregue a página após cada reinício do servidor.
O cookie é específico da porta; CSRF continua obrigatório. Origin deve coincidir;
quando ausente, exige Referer da mesma origem. Não usar proxy externo.

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

Confirmar revisão não conclui instalação nem libera operação física. Infraestrutura,
.env, token, publicação e serviço continuam nas Etapas 7–9.
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
- Entradas duplicadas ou não reconhecidas são recusadas, não mescladas.
- Prévia: entrada até 256 KiB; saída até 64 KiB, sem conteúdo bruto de arquivo
  malformado. Senhas/tokens/segredos são mascarados recursivamente antes da resposta.
  Arquivos desconhecidos não têm prévia. O modal usa textContent, nunca innerHTML.
- O formulário é protegido por sessão, CSRF e origem; seleção de inventário usa
  IDs validados contra descritor persistido no manifesto privado.
- Uploads e SQLite capturado ficam privados; origem nunca é migrada no local.
- Abort elimina somente os temporários da tentativa. Não há escrita em .env.

## Validação local (não executada pelo assistente)

```powershell
python -m pytest tests/test_setup_browser_import.py tests/test_setup_partial.py tests/test_setup_i18n.py tests/test_setup.py tests/test_setup_sqlite_import.py -q
python -m pytest -q
```

Conferir temas, idioma, selects, modal, upload, erro CSRF, cancelamento, relatório,
caminhos Windows com espaços e funcionamento com arquivos no computador e setup
no Raspberry via túnel SSH. A homologação visual real permanece local.
