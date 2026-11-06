# Matriz de homologação — setup 2.0.0

Atualização: 06/11/2026. Branch: feature/sqlite-full-migration.
Estado: cenário de simulação validado pelo mantenedor; homologação em cenário real pendente de sua execução.
Referência documental: 2.0.0-setup.20.
Não há merge em main, tag de release ou certificado de operação física.

## Aceite informado em 06/11/2026

O mantenedor confirmou: "no cenário de simulação esta ok". A validação em cenário
real ficou explicitamente pendente de sua parte. Esse aceite manual global da
simulação não informa commit executado, SO/Python, totais da suíte atual nem o
resultado individual de cada item da matriz; esses campos não serão presumidos.

| Escopo | Situação atual | Responsável / limite |
|---|---|---|
| Cenário de simulação | Validado pelo mantenedor em 06/11/2026 | Aceite manual global informado nesta conversa |
| Suíte automatizada atual | Resultado consolidado não informado | Números abaixo são históricos; não equivalem ao build atual |
| Hardware real e intertravamentos | Pendente | Mantenedor: sensores, GPIO, bombas, aquecimento, emergência, failsafe e GLP |
| Integração MQTT em cenário real | Pendente | Mantenedor: comandos, telemetria e comportamento após falhas/reconexão |
| Raspberry Pi e serviço systemd | Pendente em cenário real | Mantenedor: instalação, boot, reinício e permissões |

O aceite da simulação não encerra a homologação física nem altera as autorizações
e proteções do runtime. Os roteiros abaixo permanecem como referência; sua
presença não declara que todos os seus passos foram executados.

## Evidência recebida

| Evidência | Fonte e limite |
|---|---|
| 604 testes aprovados no início | Execução Linux/Python 3.12 na auditoria inicial, antes das etapas posteriores |
| 617 testes aprovados após núcleo | Execução do assistente para a Etapa 2, não resultado da versão atual |
| 639 aprovados / 1 falha / 1 skip | Retorno Windows/Python 3.13 do usuário após Etapa 6; falha de isolamento corrigida depois |
| 672 aprovados / 1 falha / 2 skips | Retorno após Etapa 9; falha de isolamento do teste de serviço |
| 699 aprovados / 1 falha / 2 skips | Retorno histórico Windows/Python 3.13 após setup.11; clone mínimo omitia reusable/ |
| Correção 2133f7e publicada | Inclui reusable/ e verifica recursos CSS via HTTP; resultado posterior ainda não informado |
| Correção 7e3e2a9 publicada | Isola pasta do teste e preserva sentinela; resultado após correção ainda não informado |
| Verificações de sintaxe | Python/JSON/JS/shell conferidos na Etapa 9; não equivalem à suíte funcional |
| CI anterior | Sem confirmação de sucesso da matriz ampliada; verificar execução real após publicação |
| Simulação — aceite manual global | Confirmação do mantenedor em 06/11/2026; sem novos totais de testes ou commit executado informado |
| Raspberry físico/systemd/GLP | Sem homologação final registrada nesta conversa |

Não transformar falhas corrigidas em aprovação presumida nem extrapolar um teste
simulado para fiação, chama, relés ou atuação real.

## Execução automatizada

Workflow .github/workflows/sqlite-branch.yml:
Ubuntu e Windows; Python 3.9 e 3.13; suíte completa com JUnit.
Sintaxe Python, Jinja, JavaScript e shell (Linux). Nenhum script de instalação de
serviço, GPIO real ou comando de início físico é executado pelo CI.
Consulte [Actions](https://github.com/ChristopherNicolasSMM/Tesseract-Device-Bridge/actions).

Validação local:

```powershell
git pull --ff-only origin feature/sqlite-full-migration
python -m pip install -r requirements.txt
python -m pytest -q
python -m setup.doctor
python -m setup
```

Registre commit real, SO, versão Python, totais passed/failed/skipped, duração e
motivo de cada skip. Não use número fixo esperado como condição de aceite:
novos testes e skips específicos de plataforma alteram os totais.

## Aceite por cenário

| Cenário | Cobertura automatizada principal | Aceite manual / situação |
|---|---|---|
| Clone sem .env/DB | test_setup, subprocesso HTTP mínimo e sentinela de imports | Confirmar clone limpo Windows e Pi |
| ORM vazio sem fake device | test_setup_bootstrap, test_setup_publication | Abrir configuração administrativa sem runtime |
| YAML/JSON sem SQLite | test_setup_legacy | Dados reais anonimizados e hashes originais preservados |
| SQLite legado/ORM | test_setup_sqlite_import | Revisões antigas, valores reais e tamanhos usuais |
| Importação parcial | test_setup_partial | Conferir entidades rejeitadas e relatório |
| Grid, upload e modal | test_setup_browser_import | Seleção, mapeamento público/privado, XSS/redação visual |
| i18n e temas | test_setup_i18n, test_dark_select_css | pt_BR/en, dark/light, Windows selects e celular |
| Infraestrutura | test_setup_infrastructure | Portas ocupadas, IPv4/IPv6, host local/nominal e permissão |
| Credencial | test_setup_security, test_admin_security_policy | Exibição única, curto, Unicode, sem token e túnel SSH |
| Origem/CSRF remoto | test_setup, test_admin_security_policy | Rejeição cross-origin/proxy e sessões após reinício |
| Cancelamento/lock | test_setup, test_setup_partial | Duas instâncias e encerramento abrupto |
| Publicação e rollback | test_setup_publication | Interrupção real em equipamento de teste e perda de energia |
| Arquivo final existente | test_setup_publication | Nenhuma sobrescrita de DB/.env sem regras previstas |
| Serviço opcional | test_setup_service (geração) | systemd-analyze, instalar/habilitar/iniciar/remover em Pi |
| Modo configurado | test_setup_publication, test_orm_cutover | Autorizar no setup; conferir intertravamentos e Python 3.9 |
| Backup/restauração | Procedimento documentado | Restaurar conjunto em clone separado; não usar duas plantas reais |
| Diagnóstico sem segredo | test_setup_doctor | Conferir saída compartilhável sem dados privados |

## Roteiro Windows

1. Confirmar pull, commit e build 2.0.0-setup.20 (ou sucessor explicitamente registrado).
2. Executar suíte completa sem erros de coleta.
3. Clone descartável novo: instalar vazio; confirmar zero devices e tela administrativa.
4. Importar pasta YAML/JSON por caminho e upload; acrescentar receita.json com destino explícito.
5. Importar SQLite de backup consistente e tentar um arquivo desconhecido/corrompido.
6. Conferir relatórios, credenciais mascaradas e ausência de alteração da origem.
7. Repetir com os dois idiomas e temas; validar selects, modais e foco.
8. Testar porta ocupada, CSRF após reinício e cancelamento.
9. Interromper publicação somente em instalação descartável; retomar e testar rollback.
10. Guardar resultados sanitizados e commit. Não anexar .env ou bases reais.

## Roteiro Raspberry/systemd

1. Clone e venv novos; preservar instalação antiga, backup e serviço anterior.
2. Setup local ou túnel SSH; iniciar em simulação.
3. Validar caminhos, banco e credencial; publicar sem iniciar hardware.
4. Gerar unidade com usuário correto. Conferir Python absoluto, diretório e ownership.
5. Instalar, habilitar e iniciar em ações separadas, inicialmente em simulação.
6. Conferir logs, reinício controlado, boot sem desktop e portas.
7. Remover somente a unidade gerada e conferir que a instalação antiga ficou intacta.
8. Para operação física autorizada: usar ambiente Python 3.9 e verificar sensores,
   emergência, failsafe, limites térmicos e corte de chama em condições apropriadas.
   Testes de software não comprovam esses itens.
9. Registrar modelo do Pi, OS, Python, bibliotecas, commit e resultado real.

## Critério de encerramento

A documentação/CI podem ser entregues sem declarar homologação concluída.
Encerrar a homologação exige suíte atual aprovada, fluxo visual reproduzível em
clone limpo, migração/rollback preservando origem e aceite de plataforma/serviço.
O gate do código continua sendo conclusão válida do setup, como definido pelo usuário;
o registro de homologação não cria uma nova barreira de software posterior ao setup.

Registro final a preencher:
- Commit:
- Windows/Python e suíte:
- Linux/Python e suíte:
- Raspberry/OS/venv:
- Serviço:
- Fluxo visual/importação/restauração:
- Hardware e intertravamentos:
- Pendências e aceite do operador:


## Extensão: módulos reutilizáveis e monitor serial

Entrega: setup.11, implementação sem execução local da suíte nesta sessão.
Validar `tests/test_serial_monitor_module.py`, `tests/test_guided_setup_module.py`,
`tests/test_admin_diagnostics.py` e a regressão completa de setup.

No Windows/Raspberry: verificar porta enumerada e manual sem cadastro, erro de
porta inexistente/ocupada, leitura pontual, monitor contínuo, modo hexadecimal,
fechamento ao ocultar/encerrar e expiração após abandono. Repetir na página de
configuração sem dispositivos. Validar origem/CSRF na política local e recusa
durante sessão ativa. Para hardware real, usar equipamento com cargas isoladas.

Para o setup, conferir tema claro/escuro, navegação e retomada após a extração
para `reusable/guided_setup`, sem mudar o formato do manifesto nem o fluxo de
publicação. Empacotamento opcional e instalação em outro projeto exigem sua
própria validação; não há publicação no PyPI.


### Retorno Windows da extensão setup.11

O mantenedor reportou 699 testes aprovados, 1 falha e 2 ignorados. A falha
`test_actual_cli_in_clean_clone` omitia o pacote `reusable/` ao montar o clone
mínimo temporário e resultava em ModuleNotFoundError antes de abrir o servidor.
A preparação foi corrigida e passou a verificar também os recursos CSS via HTTP.
Esta correção não foi executada localmente nesta sessão; confirmação pendente.


## Extensão setup.12 — pasta e inventário

Incluídos seletor de pastas do servidor e filtro por nomes/caminhos reconhecidos
pelos importadores. Nenhum arquivo desconhecido vira importável por ter extensão
JSON/YAML. Na entrega setup.12, apenas a grade era filtrada. Desde setup.17, o relatório
visível também omite arquivos fora do escopo, inclusive em relatórios antigos.
O inventário técnico mantém o registro de descoberta.

Testes adicionados em test_setup_browser_import e test_guided_setup_module para
origem com .md/JSON alheio, retomada de inventário antigo, navegação com espaços,
CSRF, erros, ausência de efeitos e limites. Não executados nesta entrega.
Validar no Windows seleção de unidade, pasta acima, colar caminho e permissões;
no Raspberry, confirmar que o seletor mostra pastas do servidor e que arquivos
no cliente continuam sendo enviados por upload.

## Entrega posterior ao aceite: central de ajuda (setup.21)

A aba Ajuda e documentação, os links no setup/configuração inicial e o módulo
`reusable/documentation` foram incluídos após o aceite de simulação do mantenedor.
Esse aceite anterior não comprova a validação desta nova interface.

Pendentes de execução local: `tests/test_documentation.py`, regressão do painel e
do setup, navegação Markdown/imagens, busca com acentos, temas e largura móvel.
Conferir acesso somente ao catálogo publicado, links externos em outra aba,
tratamento de documento indisponível sem `runtime.trip`, consulta durante
emergência e tela de configuração vazia sem instanciar hardware. As dependências
de renderização devem ser instaladas pelo requirements atualizado.
A validação física permanece pendente do mantenedor, como registrado acima.

## Entrega posterior ao aceite: largura de conteúdo (setup.22)

O controle global Layout foi entregue após o aceite anterior da simulação.
Pendente: testes Python/Node listados no módulo ui-preferences e validação visual
em painel, setup, configuração inicial e documentação independente/incorporada.
Conferir mudança imediata, restauração, responsividade, armazenamento bloqueado,
herança em navegação no iframe e compartilhamento entre portas do mesmo host.
O aceite da nova interface não foi informado; a operação física segue pendente.
