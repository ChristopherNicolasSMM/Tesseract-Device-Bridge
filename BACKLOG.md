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
`data/public/receita_base.yaml` (migração real, `git mv`) — YAML,
não editável pelo sistema de cadastro, mas sempre selecionável.
Receitas cadastradas (ainda sem UI) ficam em
`data/{public,private}/receita.json` — **um arquivo por pasta,
contendo uma lista** (convenção de "entidade"), não um arquivo por
receita. `public`/`private` só diferem em versionamento
(`.gitignore`: `data/private/*`). Módulo `data/__init__.py` (lógica
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

**9. `publico`/`privado` → `public`/`private`, e `devices.yml`/`recipe_state.json` movidos pra dentro de `data/`**
Ajuste feito por você direto no repositório (rename de pasta + updates
em `data/__init__.py`) — só precisei corrigir os testes
(`tests/test_data_store.py`) que ainda usavam os nomes antigos.
Completado nesta sessão: `devices.yml` → `data/public/devices.yml`
(`git mv`, continua versionado — "public" = compartilhado);
`devices.yml.example` → `data/public/devices.yml.example`;
`recipe.yml.example` **removido** (receita_base.yaml já cobre esse
papel, decisão confirmada); `recipe_state.json` → `data/private/recipe_state.json`
(`git rm --cached` + mv — nunca mais versionado, é estado de execução,
não config). `run_panel.py`/`run_bridge.py` atualizados
(`DEFAULT_CONFIG_PATH`, `EXAMPLE_CONFIG_PATH`, `DEFAULT_RECIPE_STATE_PATH`);
`tools/install_service.sh`/`uninstall_service.sh` corrigidos (checagem
de `devices.yml`, comentários do unit file systemd). Documentação
(`README.md`, docs técnicos/manual, este arquivo) atualizada nos
pontos operacionais/acionáveis — alguns diagramas ER/C4 conceituais
citam `devices.yml`/`recipe_state.json` sem o caminho completo
(schema não mudou, só a localização — baixo risco de confundir).

**10. Aba de cadastro de receitas (📖 Cadastro) — item pendente fechado**
Fluxo "duplicar e ajustar" (decidido em sessão própria): toda receita
nova parte de uma existente — nunca em branco. Vasilhas (hardware:
heater/sensor/PID) vêm herdadas, ficam num bloco avançado recolhido
(só PID é editável ali); o formulário foca só no que muda de receita
pra receita — etapas (alvo, patamar, bombas, alarmes de lúpulo). Id
gerado automaticamente por slug do nome (`ipa-tropical`, sufixo `-2`
etc. em colisão) — nunca pedido ao usuário. Backend:
`create_recipe()`/`update_recipe()`/`delete_recipe()` +
`get_recipe_dict_by_id()`/`get_effective_active_recipe_id()` em
`data/__init__.py`; endpoints `GET/POST /api/recipes`,
`GET/PUT/DELETE /api/recipes/<id>`; `GET /api/recipes` agora também
devolve `active_recipe_id` (vai rodar no próximo boot) e
`running_recipe_name` (rodando agora) — cards do painel mostram os
dois estados separados (podem divergir até reiniciar). `receita_base`
protegida: nunca editável/removível pelo cadastro, sempre
selecionável. 76 testes novos (42 em `data`, 34 na API — achado no
caminho: a fixture de teste do painel precisava isolar os caminhos do
módulo `data` com `monkeypatch`, senão os testes leriam/escreveriam no
`data/` real do repositório).

### Suíte de testes

291 → 424 testes ao longo de toda a sessão (178 novos/reescritos no
total). Todos os patches validados em clone limpo do HEAD real via
`git am` antes da entrega.

---

## Pendente (próximos patches)

### 1. Configuração fina de bomba: manual vs. automático, tempo de start/stop

Simplificado pra "confirmação de acionamento automático" (item 7 acima,
já concluído) — a configuração de timing fina (start/stop, direto/
pulsado) continua não implementada, mas o medo raiz (energizar bomba
sem checar antes) já está resolvido pela confirmação. Retomar só se
surgir uma necessidade real de timing além da confirmação simples.

### 2. Sincronização com o Tesseract Core (pergunta em aberto, não bloqueante)

As receitas cadastradas aqui (`data/`) deveriam sincronizar com
receitas do lado do Tesseract Core, ou continuam sendo independentes
(cada bridge com seu próprio catálogo)? Fora de escopo da Fase F ainda
pendente na skill 05 do Tesseract principal — só retomar quando essa
fase for aberta lá.
