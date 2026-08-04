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

### Suíte de testes

291 → 370 testes ao longo da sessão (79 novos/reescritos). Todos os
patches validados em clone limpo do HEAD real via `git am` antes da
entrega.

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
- Este arquivo (`BACKLOG.md`), criado agora.

---

## Pendente (próximos patches)

### 1. Nova aba — cadastro e seleção de receitas

Hoje o bridge carrega **um único `recipe.yml`** no boot; trocar de
receita exige editar o arquivo manualmente e reiniciar o processo (ver
FAQ "Como adiciono uma nova receita?" em `docs/manual/04-perguntas-frequentes.md`
— vai precisar de atualização quando isso for implementado).

Pedido: uma aba nova, depois de "Receitas", pra cadastrar múltiplas
receitas pelo próprio painel e escolher qual usar em cada brassagem,
sem editar arquivo nem reiniciar o serviço.

**Direção já discutida (não fechada, retomar quando chegar a vez)**:
manter YAML (sem banco) — uma pasta `dados/` com um arquivo por
receita, e um `receita_base.yaml` como fallback: se `dados/` estiver
vazia, o sistema usa ela pra já funcionar sem cadastro nenhum (mesmo
comportamento de hoje). Se o painel (JS) precisar listar as receitas
cadastradas, um índice leve em JSON (`dados/index.json`, só
nome+arquivo) evita precisar de um parser YAML no navegador — o
conteúdo de cada receita continua YAML, parseado só no lado Python.

**Perguntas em aberto pra próxima sessão de decisão**:
- Trocar de receita exige reiniciar o processo (limitação atual,
  `Recipe` é carregada uma vez no boot) ou precisa suportar troca a
  quente, sem restart?
- Interação com o Tesseract Core: essas receitas cadastradas aqui
  deveriam sincronizar com receitas do lado do Tesseract (fora de
  escopo da Fase F ainda pendente na skill 05), ou são independentes?
- Validação de receita cadastrada pelo painel: mesma validação de
  `Recipe.load()` (falha cedo, mensagem clara) precisa rodar no
  momento do cadastro, não só ao carregar — senão um erro de digitação
  só aparece na hora de tentar usar a receita numa brassagem real.
