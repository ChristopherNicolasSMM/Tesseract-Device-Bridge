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
- Demais testes e o sistema de CI precisam de validação completa; este registro
  não afirma que a suíte integral passou.
