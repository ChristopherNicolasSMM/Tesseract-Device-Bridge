# Histórico de versões

## 2.0.0 — 2026-11-04 — branch experimental

**Status:** versão de desenvolvimento em homologação no branch
`feature/sqlite-full-migration`. **Ainda não foi feita publicação/merge
na main nem validação física final no Raspberry Pi.**

### Alterações estruturais

- SQLite como armazenamento operacional de dispositivos, receitas,
  configurações de controle, calibrações, estado de sessão e revisões.
- Migrações SQL versionadas, repositórios de persistência e backup consistente.
- Importador explícito de YAML/JSON legados com conferência, cópia de segurança
  e registro das adaptações necessárias (inclusive proteção de controle remoto).
- Administração pelo frontend com token, rascunhos de configuração, validação,
  aprovação e aplicação após reinício seguro.
- `.env.example`, leitura automática do `.env`, overrides de ambiente
  e modo `SIMULATION_ONLY` para homologação sem GPIO/MQTT reais.
- Correção do tema escuro dos menus `select`.
- Documentação e manual separados para o fluxo SQLite 2.0.0.
- Fundação relacional SQLAlchemy/Alembic com normalização somente em cópia, ainda sem cutover do runtime.
- Repositório ORM para leitura tipada e auditoria independente `orm-audit`, com comparação dos dados de legado antes da transição.
- Revisão `bridge_orm_0002`: calibrações, receita ativa, estado de sessão, alarmes e snapshot térmico normalizados em tabelas relacionais na cópia; runtime ainda em esquema legado.
- Revisão `bridge_orm_0003`: revisões históricas, rascunhos, auditoria, manifestos e migrações legadas com metadados tipados e documentos históricos em nós relacionais, ainda sem cutover do runtime.
- Corrigida a ordem de flush ORM antes da receita ativa (FK), além do fechamento explícito de conexões SQLite e publicação exclusiva da migração somente após validação, evitando mascarar erros de banco com WinError 32.
- Reorganização incremental em `tesseract_bridge/{infrastructure,control,safety,integrations}`, sem alterar o motor de receitas nem a lógica física.

### Compatibilidade e cuidados

- A `main` mantém o sistema estável anterior baseado em YAML/JSON.
- A 2.0.0 não lê arquivos legados em runtime; apenas a ferramenta de
  importação aceita os formatos antigos.
- O teste físico, os limites de segurança e o acesso administrativo ainda
  requerem homologação; não instalar como produção sem aceite explícito.

### Validação conhecida

- Informado pelo operador: 12 testes de infraestrutura do `.env` passaram,
  banco importado localizado corretamente, com 7 dispositivos e 2 receitas
  visualizados no painel simulado.
- Informado pelo operador: 23 testes passaram em Windows, `normalize --dry-run`
  e `orm-audit` da cópia Alembic 0001 concluíram com status OK e conferência
  de 7 dispositivos, 2 receitas e 2 perfis térmicos.
- Informado pelo operador: 19 testes da revisão 0002 passaram, e a
  auditoria `orm-audit` de `normalized-v2.sqlite3` retornou OK com
  calibrações, receita ativa, sessão e históricos preservados.
- Demais testes e o sistema de CI precisam de validação completa; este registro
  não afirma que a suíte integral passou.
