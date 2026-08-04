# Backlog — Tesseract Device Bridge

Histórico de decisões e trabalho por sessão, mais pendências conhecidas.
Mesmo espírito do `BACKLOG.md`/skills do Tesseract principal: documentação
viva, atualizada junto com o código, não depois.

---

## 2026-08-04 — Controle de potência, override manual, performance, UX

### Concluído

**1. Controle de potência por atuador (heater) — interruptor separado do valor de %**
Antes, ajustar o slider de 0-100% já energizava a resistência sozinho.
Agora: `DeviceRuntime.set_manual_duty_percent()` só grava o valor
configurado; `set_manual_enabled()` é o interruptor mestre, separado —
só quando ligado o valor configurado é de fato aplicado. Endpoints:
`POST /api/devices/<id>/duty` (valor) e `POST /api/devices/<id>/duty/enabled`
(interruptor). Ver [Fluxo 8](docs/technical/03-fluxos.md#fluxo-8--prioridade-de-controle-de-um-atuador-failsafe--manual--receita--repouso).

**2. Controle manual também no card da vasilha da receita**
O primeiro ajuste só cobriu a grade "Atuadores" (devices crus) — o
card de vasilha (medidor circular Mash/Boil) ganhou o mesmo
toggle+slider, sem precisar sair da tela da receita. De quebra,
corrigido: o medidor de potência agora reflete o estado real do
`heater_device_id`, não mais só `status.current_duty_percent` (que só
existe pra vasilha da etapa ativa — um override manual numa vasilha
"fora de etapa" aparecia como "inativo" mesmo aplicando potência).

**3. Override manual de bombas (`has_manual_override` / `set_manual_override`)**
Achado real: `RecipeEngine._apply_pumps()` decide liga/desliga
comparando com bookkeeping interno (`self._active_pumps`), nunca com o
estado físico — um comando manual numa bomba podia ser desfeito
silenciosamente na próxima troca de etapa (bombas são `is_risk: true`
no `devices.yml.example`, então isso também tocava segurança). Mesmo
mecanismo de prioridade do item 1, generalizado pra atuadores sem
controle de potência. `POST /api/devices/<id>/command` passou a
registrar o override em vez de escrever cru.

**4. Subcard visual da bomba (UX)**
O indicador de bomba no card da vasilha era só uma "pílula" de texto
sem nenhuma affordance de que era clicável ou tinha 2 ações (manual/
automático + liga/desliga). Substituído por um subcard: botão de
ícone real (▶ liga / ⏹ para — o próprio ícone comunica a ação
disponível), badge de modo (🤖 Receita / 🖐️ Manual) e botão pequeno de
liberar controle (↺), só visível quando em manual.

**5. `run_bridge.py` — removido bloqueio indevido de execução no Windows**
Uma checagem de plataforma barrava `python run_bridge.py` mesmo
rodando manualmente (não só instalação como serviço systemd, que já é
responsabilidade só de `tools/install_service.sh`, script bash). Sem
mudança de comportamento em Linux/macOS/WSL.

**6. DS18B20 — leitura em thread de fundo (elimina travamento no painel)**
Diagnóstico corrigido no meio do caminho: o Flask dev server já roda
com `threaded=True` por padrão (não era o gargalo). A causa real: ler
`w1_slave` no Linux dispara uma conversão nova no sensor a cada
chamada, bloqueando ~750-950ms — sem cache, `/api/devices` com 3
sensores DS18B20 travava ~2,25-2,85s por poll. `Ds18b20Reader` agora
lê a primeira vez de forma síncrona (só no boot) e depois mantém uma
thread de fundo atualizando o cache continuamente — `.value` nunca
mais bloqueia. Resiliente a glitch de CRC (comum em 1-Wire); só
levanta erro de verdade depois de `stale_after_seconds` (default 10s)
sem nenhuma leitura boa.

**7. Confirmação de acionamento automático de bomba (item 1 do backlog, versão simplificada)**
Discutido e decidido em sessão de arquitetura própria: em vez da
configuração fina originalmente cogitada (timing de start/stop,
direto/pulsado), a versão simples resolve o mesmo medo raiz — a
receita nunca liga uma bomba pela **primeira vez numa execução** sem
aprovação explícita do operador. `RecipeEngine` ganhou
`_confirmed_pumps`/`_pending_confirmation` (em memória, não
persistido — crash real exige reconfirmar; pause/resume manual
preserva) e `confirm_pump_auto()`/`decline_pump_auto()` (o segundo
reaproveita 100% o `set_manual_override` que já existia). Painel:
banner de aviso no topo (sem botão, some sozinho) + subcard da bomba
com borda âmbar pulsante e os botões Confirmar/Manter manual. Ver
[Fluxo 9](docs/technical/03-fluxos.md#fluxo-9--confirmação-de-acionamento-automático-de-bomba-só-bombas-não-heaters).

### Documentação atualizada nesta sessão

- `README.md` — endpoints novos, seção de override de bombas, DS18B20,
  confirmação de acionamento automático.
- `docs/technical/03-fluxos.md` — Fluxo 8 (prioridade de controle) e
  Fluxo 9 (confirmação de bomba).
- `docs/technical/06-manutencao-e-expansao.md` — mecanismo de override,
  padrão de thread de fundo pra sensor lento, tabela de extensão.
- `docs/manual/03-funcionalidades.md` — removido aviso obsoleto de
  conflito manual/receita (resolvido nesta sessão); documentado o
  toggle+slider, o subcard de bomba e a confirmação automática.
- `docs/manual/02-primeiros-passos.md` / `04-perguntas-frequentes.md`
  — seção 4 e "Como adiciono uma nova receita?" reescritas pro sistema
  `data/` (base + json + ponteiro ativo).
- `recipe.yml.example` — cabeçalho avisando que virou referência de
  schema, não é mais copiado/carregado automaticamente.
- Este arquivo (`BACKLOG.md`), criado agora.

**8. Fundação de armazenamento de receitas (`data/`) — primeira metade do item 2 original**
Decisão de sessão própria: `recipe.yml` fixo na raiz virou
`data/publico/receita_base.yaml` (migração real, `git mv`) — YAML,
não editável pelo sistema de cadastro, mas sempre selecionável.
Receitas cadastradas (ainda sem UI) ficam em
`data/{publico,privado}/receita.json` — **um arquivo por pasta,
contendo uma lista** (convenção de "entidade"), não um arquivo por
receita. `publico`/`privado` só diferem em versionamento
(`.gitignore`: `data/privado/*`). Módulo `data/__init__.py` (lógica
direto no `__init__.py`, decisão explícita, foge do padrão do resto
do projeto de propósito) expõe `list_recipes()`, `load_recipe_by_id()`,
`get_active_recipe_id()`/`set_active_recipe_id()`,
`load_active_recipe()` — cadeia de fallback ponteiro → receita_base →
`recipe.yml` legado → `None`, reaproveitando `Recipe.from_dict()` +
`recipe.validate()` (já existiam separados de `Recipe.load()`) pra
validar receitas em JSON sem duplicar nada. Novos endpoints
`GET /api/recipes` e `POST /api/recipes/active`. Troca de receita
ativa **exige reiniciar o processo** (decisão tomada — endpoint só
grava o ponteiro pro próximo boot). 23 testes novos
(`tests/test_data_store.py`).

### Suíte de testes

291 → 393 testes ao longo de toda a sessão (102 novos/reescritos no
total). Todos os patches validados em clone limpo do HEAD real via
`git am` antes da entrega.

---

## Pendente (próximos patches)

### 1. Tela de cadastro de receitas pelo painel (UI em cima da fundação já pronta)

A fundação (item 8 acima) já resolve armazenamento, descoberta,
validação e resolução de qual receita usar no boot. Falta só a
**interface** — uma aba nova, depois de "Receitas", pra:
- Cadastrar uma receita nova (formulário, não editar JSON na mão) —
  grava em `data/publico/receita.json` ou `data/privado/receita.json`
  via `write_entities()` (já existe, só falta a rota da API que
  monta o registro e chama).
- Listar as disponíveis (já tem `GET /api/recipes`) e escolher qual
  fica ativa (já tem `POST /api/recipes/active`) — só falta o HTML/JS.
- Validar no momento do cadastro (reaproveitar `Recipe.from_dict()` +
  `recipe.validate()`, mesma validação que `list_recipes()` já faz),
  com mensagem de erro clara antes de salvar — não só ao carregar.

**Perguntas em aberto pra próxima sessão de decisão**:
- Troca de receita ativa **exige restart** (já decidido, ver item 8)
  — a UI precisa deixar isso claro pro operador (ex.: aviso "só
  efetivo no próximo restart", já retornado pela API hoje).
- Interação com o Tesseract Core: essas receitas cadastradas aqui
  deveriam sincronizar com receitas do lado do Tesseract (fora de
  escopo da Fase F ainda pendente na skill 05), ou são independentes?
- Formulário de cadastro replica a estrutura toda de `vessels`/`steps`/
  `hop_alarms` (mais flexível, mais trabalho de UI) ou começa mais
  simples (ex.: só duplicar uma receita existente e editar campos
  específicos)?
