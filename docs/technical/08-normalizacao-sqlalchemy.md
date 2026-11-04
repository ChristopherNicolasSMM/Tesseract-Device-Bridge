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

Os **arquivos antigos, auditoria/revisões históricas e estado de sessão**
ainda existem no esquema legado para rollback. Não foram apagados ou
convertidos nesta primeira entrega: falta projetar o histórico imutável,
as filas de alarmes, as revisões e os snapshots de recuperação em models
próprios. A intenção é eliminar os campos JSON operacionais depois da
validação completa, sem remover evidências antes da migração.

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
python -m storage.cli normalize --output ./data/private/normalized-candidate.sqlite3
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
python -m pytest -q tests/test_package_layout.py tests/test_orm_normalize.py
python -m storage.cli status
```

Testes elétricos e de recuperação no Raspberry Pi continuam pendentes.
Não executar a v2.0.0 física em paralelo com a instalação estável.
