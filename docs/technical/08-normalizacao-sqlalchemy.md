# 08 — Normalização relacional e SQLAlchemy | Device Bridge 2.0.0

> **Status:** fundação ORM e conversor **experimental**, sem cutover automático
> do runtime. A aplicação existente segue usando a camada SQLite anterior
> até concluir a homologação de migração, interfaces e recuperação física.

## Referência ao Tesseract principal

No repositório Tesseract, `core/db.py` é a factory compartilhada
`Flask-SQLAlchemy + Flask-Migrate`, os models ficam junto à feature,
e migrations são versionadas pelo Alembic.

O Device Bridge compartilha **os princípios**, mas não a dependência
do contexto Flask: o mesmo banco é acessado pelo processo de controle,
pelo painel e pelos utilitários de linha de comando. Por isso, o Bridge
utiliza diretamente `SQLAlchemy 2.x`, um `sessionmaker` central
(`storage/models/base.py`) e **Alembic próprio** em
`storage/alembic/`. Esse desenho facilita integração futura com o
ecossistema mãe sem acoplar as duas bases de dados.

A combinação `SQLAlchemy>=2.0,<2.1` e `alembic>=1.16,<1.17`
preserva a compatibilidade com Python 3.9, ainda utilizado pelo
Raspberry Pi. Versões recentes de Alembic exigem Python >=3.10.

## Modelos tipados e responsabilidades

| Local | Models | Estrutura |
|---|---|---|
| `storage/models/configuration.py` | `BridgeSettings`, `MqttSettings`, `PanelSettings` | Backend, broker, painel, revisão |
| Mesmo arquivo | `Device`, `DeviceProperty`, `DeviceHeatingSource` | Dispositivos, GPIO, recursos físicos e fonte protegida |
| `storage/models/recipe.py` | `Recipe`, `RecipeVessel`, `RecipeStep`, `RecipeStepPump`, `RecipeHopAlarm` | Receitas, PID por vasilha, etapas, bombas e alarmes |
| `storage/models/control.py` | `ControlProfile`, `ControlCurvePoint`, `ControlVesselProfile` | Parâmetros térmicos, curvas e perfis por recipiente |

As tabelas da fundação usam sufixo `_v2` **interno ao SQL**,
para coexistir temporariamente com as tabelas JSON legadas da 2.0.0
sem sobrescrever dados existentes. Esse sufixo **não** altera a
versão do aplicativo. Na etapa de cutover, não haverá duas fontes
ativas de configuração.

A modelagem registra campos consultáveis e tipados. Atributos extras
simples do hardware podem usar `DeviceProperty` com tipo declarado;
objetos desconhecidos/aninhados **não são convertidos em JSON opaco**.
O conversor recusa campos não mapeados, informando exatamente qual
model precisa ser ampliado, em vez de perder informação silenciosamente.

A revisão **bridge_orm_0002** acrescenta a normalização de
**calibrações (ROM ID e offset), receita ativa, estado de execução, alarmes
pendentes, alarmes de lúpulo já disparados e snapshot dos parâmetros térmicos**.
São tabelas relacionadas, com campos tipados, e o snapshot térmico da sessão
é independente do perfil editável para a próxima brassagem.

A revisão **bridge_orm_0003** acrescenta tabelas próprias para
**revisões de configuração, revisões de receitas, rascunhos administrativos,
eventos de auditoria, manifestos de importação e histórico das migrações SQL
legadas**. Os metadados são colunas tipadas; os documentos históricos
heterogêneos são representados por uma árvore relacional de nós
(`bridge_history_documents_v2` e `bridge_history_nodes_v2`),
com tipo, chave, pai e ordem explícitos. **Não são gravadas colunas JSON
nas novas tabelas**. Os nós preservam objetos, listas, `null`,
booleanos, números e textos, inclusive campos de versões anteriores.

Essa árvore documental é exclusiva para snapshots de auditoria/revisão.
Cadastros e dados operacionais continuam em modelos específicos.
Os registros legados permanecem no SQLite de destino para rollback,
mas agora têm representação equivalente no ORM.
A intenção é remover a dependência das colunas JSON antigas somente
após o cutover integral, testes e aceite.

## Processo seguro de migração (Windows)

Atualize a branch e instale dependências:

```powershell
git pull --ff-only origin feature/sqlite-full-migration
python -m pip install -r requirements.txt
```

**Pré-validação**, sem alterar o SQLite:

```powershell
python -m storage.cli normalize --dry-run
```

**Converter para uma CÓPIA independente**:

```powershell
python -m storage.cli normalize --output ./data/private/normalized-v3.sqlite3
```

A ferramenta lê o banco selecionado no `.env` (como
`imported.sqlite3`), cria uma cópia SQLite consistente, aplica uma
migração Alembic **somente na cópia**, preenche modelos ORM e compara
os objetos reconstruídos aos dados anteriores.

- Não remove nem altera a base de origem.
- O destino não pode existir anteriormente.
- Se detectar campo não representado no ORM ou divergência, a conversão
  falha e a cópia incompleta é removida.
- A normalização não ativa GPIO, não altera PID, não retoma sessão e
  **não muda automaticamente o banco do seu `.env`**.
- A execução do Bridge ainda usa as tabelas anteriores; não indique o
  `normalized-candidate.sqlite3` como fonte operacional nova
  esperando que os models ORM já estejam ativos no runtime.


## Auditoria adicional antes de trocar a persistência

Após o `normalize --output` ter criado a cópia (sem alterar o banco
`imported.sqlite3`), execute:

```powershell
python -m storage.cli orm-audit --candidate ./data/private/normalized-v3.sqlite3
```

A auditoria é **somente leitura**. Compara as entidades do ORM com as
configurações, receitas e perfis térmicos originais, a receita ativa,
calibrações, estado de sessão, rascunhos, revisões, auditoria e
manifestos importados. Na revisão 0003, todos esses históricos também
são comparados contra seus novos modelos relacionais.

O resultado deve conter `"result": "OK"`, a revisão
`"alembic": "bridge_orm_0003"`, os quantitativos de
dispositivos/receitas e `"runtime_cutover_enabled": false`.
Ela interrompe com erro caso identifique divergência ou banco ausente.
Não imprime segredos MQTT.

O novo `storage/repositories/orm.py` oferece leitura tipada da
configuração, catálogo de receitas, calibrações, receita ativa,
estado de sessão e perfis térmicos, além de um
protótipo transacional para atualizar perfis na **cópia** com verificação
de revisão. **Não está ligado ao frontend/runtime ainda**: isso
evita que escritas no modelo novo e no antigo causem divergência.

**Não** altere `TESSERACT_BRIDGE_DB` nem ative hardware real na cópia
normalizada; o cutover ainda exige escrita transacional de todas as
entidades pelo ORM, serviços de negócio, testes de concorrência e
o caminho administrativo seguro.

## Depois da homologação do conversor

As próximas entregas trocarão os repositórios de devices, receitas,
parâmetros térmicos, sessões e históricos para a camada ORM.
Cada troca exige testes comparativos e migração de dados de produção
com backup e rollback. Somente então se removem os campos
`config_json`, `recipe_json`, `value_json`, `state_json`
e snapshots JSON equivalentes.

## Checks

```powershell
python -m compileall -q .
python -m pytest -q tests/test_package_layout.py tests/test_orm_normalize.py tests/test_orm_repository.py tests/test_orm_operational.py tests/test_orm_history.py
python -m storage.cli status
```

Testes elétricos e de recuperação no Raspberry Pi continuam pendentes.
Não executar a v2.0.0 física em paralelo com a instalação estável.

**Compatibilidade:** `normalized-candidate.sqlite3` usa Alembic 0001
e `normalized-v2.sqlite3` usa 0002. Ambas continuam preservadas,
mas a auditoria atual exige **0003** em `normalized-v3.sqlite3`.
O destino deve ser novo, nunca sobrescrito. O `.env` continua
apontando para `imported.sqlite3`.
