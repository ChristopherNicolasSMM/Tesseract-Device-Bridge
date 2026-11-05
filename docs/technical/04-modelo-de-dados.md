# 04 — Modelo de dados SQLite | 2.0.0

> Referência atual: instalações do setup usam ORM na revisão bridge_orm_0003.
> A branch continua em homologação. As tabelas legacy abaixo são mantidas como
> referência de compatibilidade/importação, não como schema do bootstrap ORM.

## Esquema ORM atual

Fonte: storage/models/ e storage/alembic/versions/bridge_orm_0001.py até 0003.py.
O setup vazio cria perfis/cabeçalhos mínimos, sem dispositivos ou receitas demo.

| Domínio | Tabelas representativas |
|---|---|
| Configuração e dispositivos | bridge_settings_v2, mqtt_settings_v2, panel_settings_v2, bridge_devices_v2 |
| Propriedades/fontes térmicas | bridge_device_properties_v2, bridge_device_heat_sources_v2 |
| Receitas | bridge_recipes_v2, bridge_recipe_vessels_v2, bridge_recipe_steps_v2, bridge_recipe_step_pumps_v2, bridge_recipe_hop_alarms_v2 |
| Controle | bridge_control_profiles_v2, bridge_control_curve_v2, bridge_control_vessel_profiles_v2 |
| Calibração e receita ativa | bridge_sensor_calibrations_v2, bridge_active_recipe_v2 |
| Sessão | bridge_session_state_v2 e tabelas auxiliares de campos/alarmes/chaves disparadas |
| Histórico e manutenção | bridge_configuration_revisions_v2, bridge_configuration_drafts_v2, bridge_recipe_revisions_v2, bridge_audit_events_v2, bridge_legacy_imports_v2 |

O router seleciona um backend; não sincroniza implicitamente legacy e ORM.
Formato externo de API/snapshot não deve ser confundido com coluna JSON legacy.
Detalhes: [normalização](08-normalizacao-sqlalchemy.md) e
[arquitetura do setup](18-setup-arquitetura.md).

Manifesto de tentativa e recibo ficam em JSON privado fora do banco. O recibo
liga configuração, identidade SQLite e estado de publicação; serial não cria
tabelas nem grava automaticamente o conteúdo monitorado. Não edite esses metadados
para aprovar operação física.

## Visão relacional legacy (compatibilidade)

```mermaid
erDiagram
  system_config ||--o{ configuration_revisions : "snapshot"
  system_config ||--o{ devices : "config aprovada"
  configuration_revisions ||--o{ configuration_drafts : "origem"
  recipes ||--o{ recipe_revisions : "historico"
  recipes ||--o| active_recipe : "selecionada"
  legacy_imports ||--o{ audit_events : "registra eventos"
  settings ||--o{ audit_events : "operacao"
  system_config {
    integer id PK
    text config_json
    integer revision
    text updated_at
  }
  devices {
    text id PK
    integer position
    text config_json
  }
  configuration_revisions {
    integer revision PK
    text snapshot_json
    text action
    text created_at
  }
  configuration_drafts {
    integer id PK
    text payload_json
    integer base_revision
    text status
  }
  recipes {
    text id PK
    text source
    integer editable
    text recipe_json
    integer revision
  }
  recipe_revisions {
    text recipe_id
    integer revision
    text recipe_json
  }
  active_recipe {
    integer id PK
    text recipe_id FK
  }
  settings {
    text key PK
    text value_json
    integer revision
  }
  sensor_calibrations {
    text sensor_id PK
    text address
    real offset_c
  }
  session_state {
    integer id PK
    text state_json
  }
  legacy_imports {
    text source_sha256 PK
    text manifest_json
  }
  audit_events {
    integer id PK
    text event_type
    text entity_id
    text details_json
  }
```

*As linhas acima resumem vínculos conceituais. Nem todos são chaves
estrangeiras físicas no SQLite; consulte os scripts SQL para constraints
exatas. Em particular, a seleção da receita usa FK e a tabela de revisões
de receita não possui FK declarada.*

## Entidades e responsabilidades

| Tabela | Conteúdo | Observações |
|---|---|---|
| `schema_migrations` | versão, nome, checksum SHA-256 e momento da execução | Detecta alteração de arquivo SQL já aplicado |
| `system_config` | MQTT, backend, painel e revisão aprovada em JSON | Linha única `id=1` |
| `devices` | IDs, ordem e configuração física completa | Dados operacionais |
| `configuration_revisions` | snapshots da configuração e ação de origem | Histórico de revisões |
| `configuration_drafts` | rascunho e revisão-base | Status `draft/applied/discarded` |
| `recipes` | ID `public:...`/`private:...`, dados de receita, versão, editabilidade | `public:base` é protegida |
| `recipe_revisions` | versões anteriores das receitas | Não é histórico completo de sessão |
| `active_recipe` | receita escolhida para próximo boot | ID de receita como FK |
| `settings` | parâmetros de controle e padrão de fábrica | Chaves `control` e `control_factory` |
| `sensor_calibrations` | ROM ID, sensor e offset (−5 a +5 °C) | Não aplicar automaticamente após troca física |
| `session_state` | snapshot persistido da sessão | Recuperação segura; jamais religar atuadores após falha |
| `audit_events` | eventos administrativos persistidos | Não registra toda leitura GPIO |
| `legacy_imports` | manifesto da importação e hashes da origem | Permite conferir a proveniência |

## Fluxos e integridade

- **Controle em tempo real:** SQLite não é chamado a cada ciclo de PID/GPIO.
- **Revisões:** o operador cria rascunho, valida configurações, aprova e
  reinicia quando seguro. A execução ativa permanece no snapshot anterior.
- **Receita:** `public:base` continua protegida; receitas normais mantêm
  `public:` ou `private:` como identificadores lógicos, **não** pastas
  distintas no Git.
- **Parâmetros:** o estado de uma execução de receita conserva o snapshot
  de configurações aplicadas. Alterar formulário térmico não altera a
  sessão já em andamento.
- **Calibração:** ROM ID e offset devem corresponder ao sensor físico;
  correção só entra no próximo boot.
- **Falha:** banco ausente/corrompido não deve liberar saídas físicas;
  retomar estados interrompidos requer decisão explícita e fail-safe.
- **Importação:** somente `tools/migrate_legacy_to_sqlite.py` acessa
  YAML/JSON antigos. A origem e o backup são preservados.

## Migração e durabilidade

Arquivos SQL versionados são aplicados antes da operação. Conexões SQLite
usam `foreign_keys=ON`, `busy_timeout`, journal DELETE e
`synchronous=FULL`. O backup utiliza a API nativa do SQLite.

O banco não deve ser versionado no Git. Mantenha cópias externas,
conferência de integridade e permissões restritas. Em serviços systemd,
verifique a identidade do usuário que escreve no diretório privado.

Mais detalhes: [administração](../manual/13-administracao-sqlite.md) e
[importação](../manual/12-sqlite-migracao.md).
