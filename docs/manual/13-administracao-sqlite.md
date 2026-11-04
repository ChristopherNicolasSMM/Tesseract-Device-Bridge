# 13 — Administração SQLite | Manual da versão 2.0.0

## O que significa a área destacada no painel?

A versão 2.0.0 usa o banco SQLite como fonte operacional. O painel apresenta:

| Área | O que ela mostra | Pode alterar a configuração? |
|---|---|---|
| **Inventário de Dispositivos** | Foto do **DeviceRuntime atual**, incluindo nome, ID, tipo, GPIO, valor e indicação de risco | Não; é leitura do que está em execução |
| **Administração SQLite** | Cadastro persistido e revisões de dispositivos, conectividade e informações de manutenção | Sim, mediante token, validação e aprovação |
| **Configurações** | Controle de temperatura, potência, perfis de recipientes e offset dos sensores | Sim, com regras próprias de quando entram em vigor |
| **Cadastro** | Receitas públicas/privadas, duplicação e escolha da receita ativa | Sim, com validação do processo |

**Administração SQLite não é um editor SQL genérico:** não oferece execução arbitrária de comandos, acesso à estrutura de tabelas ou consultas livres. É uma interface de gestão de dispositivos e parâmetros do Bridge.

## 1. O token de administrador

No `.env` do clone, configure um valor exclusivo:

```dotenv
TESSERACT_BRIDGE_ADMIN_TOKEN=COLE_AQUI_UM_TOKEN_SEGURO
```

Gere com `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Reinicie o processo após alterar a variável.

1. Abra **Gerenciamento**.
2. Localize **Administração SQLite**.
3. Informe o token no campo **Token de administrador**.
4. Clique **Desbloquear**.

Se o token estiver incorreto, a API responderá 401; se não estiver configurado, a administração será desabilitada (503). O token do formulário é mantido na memória da página, não é salvo no `localStorage`. Ele **não é** senha do SQLite nem substitui autenticação completa do painel.

## 2. Editar um dispositivo

A interface oferece seleção, criação e remoção de dispositivos do rascunho, e campos como ID, nome, papel, subtipo, pino GPIO, driver, ROM ID de DS18B20, tópicos MQTT, polaridade, controle remoto e alguns vínculos de aquecimento.

1. Selecione um dispositivo no campo de seleção.
2. Modifique um campo de baixo risco, como **Nome**.
3. Clique **Atualizar no rascunho**. Nesse momento, a alteração ainda está apenas no navegador.
4. Clique **Salvar rascunho validado**. A API valida a configuração e grava uma revisão pendente.
5. Clique **Aprovar para próximo boot**. O SQLite passa a registrar a revisão aprovada.
6. Encerre qualquer operação, confira bombas e resistências em estado seguro e **reinicie** o Bridge.
7. Confira no inventário se o novo snapshot está ativo.

A aprovação altera **o banco**, mas não troca automaticamente o mapeamento de hardware no processo já em execução. Alterações em GPIO, fontes de aquecimento, sensores e gás exigem conferência física independente. O formulário atual não cobre todos os campos avançados do modelo: preserve propriedades existentes e valide em simulação antes de usar em produção.

**Segurança:** não tente remover um dispositivo usado por receita ou calibração sem revisar as referências. O backend valida a configuração completa, IDs, relacionamentos e ROM IDs, e pode recusar a aprovação.

## 3. Conectividade e infraestrutura

- **Backend real/simulado**, broker MQTT, porta do broker, prefixo e porta de painel podem ser revisados no cadastro persistido.
- **TESSERACT_BRIDGE_SIMULATION_ONLY=1**, no `.env`, tem prioridade operacional: força simulação, MQTT desligado, host `127.0.0.1` e porta de teste.
- `TESSERACT_BRIDGE_PANEL_HOST` e `TESSERACT_BRIDGE_PANEL_PORT` são overrides de infraestrutura apenas quando a simulação for `0`; não são gravados no SQLite.
- O arquivo indicado em `TESSERACT_BRIDGE_DB` deve existir. Não altere uma instalação em operação apenas mudando esse caminho.

## 4. As ações de manutenção

**Backup SQLite:** gera uma cópia consistente com a API de backup do SQLite, salva no diretório privado do banco e permite transferi-la. Não contém o código-fonte nem substitui cópias externas.

**Auditoria:** lista até os 100 eventos mais recentes de ações persistidas que geram registros; não equivale a um log completo de todas as leituras e comandos GPIO.

**Revisão ativa:** número de revisão da configuração armazenada. O inventário continua mostrando o snapshot em memória até reinicializar.

## 5. Onde cada dado fica

| Tipo | Fonte 2.0.0 |
|---|---|
| Hardware e MQTT | SQLite, tabelas de configuração e dispositivos |
| Receitas e seleção da próxima execução | SQLite |
| Parâmetros térmicos e padrões de fábrica | SQLite |
| Calibração e vínculos ROM ID | SQLite |
| Estado persistido da sessão | SQLite |
| Revisões e eventos de auditoria | SQLite |
| Caminho do banco, modo de teste, portas de override, token | `.env` ou variáveis de ambiente |
| YAML/JSON antigos | **Somente importação**, jamais leitura operacional em runtime |

## Backend ORM experimental

A partir do patch de cutover em simulação, as APIs administrativas passam
pela fachada `storage/store_router.py`. No modo ORM, rascunhos,
revisões e eventos são registros relacionais, gravados na cópia
normalizada, sem alterações no banco legado. O token e as regras de
não alterar hardware durante sessões ativas permanecem obrigatórios.
A implantação física continua pendente.

Leia [Cutover ORM em simulação](../technical/10-cutover-orm-simulacao.md).

## 6. Restrições e homologação

- A branch `feature/sqlite-full-migration` é a versão **2.0.0 em homologação**, não uma release física aprovada.
- O token protege a API `/api/admin/*`, mas outros endpoints operacionais podem ter regras de acesso próprias; o painel não deve ser exposto à Internet.
- A simulação isolada no Windows deve manter `TESSERACT_BRIDGE_SIMULATION_ONLY=1`.
- Para proteção de equipamentos, qualquer operação real requer testes de GPIO, failsafe, sensores, intertravamentos e GLP com supervisão humana.
- Se houver problema, pare o clone experimental. A pasta `main` original e seus arquivos antigos permanecem intactos após uma migração normal.
