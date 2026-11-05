# 12 — Migração SQLite | Device Bridge 2.0.0

O caminho atual é o [setup independente](20-instalacao-migracao-2.0.0.md),
num clone novo. A instalação antiga é origem somente leitura, inclusive
quando possui apenas YAML/JSON e nunca teve SQLite.

## Pelo navegador

1. Execute python -m setup no clone novo.
2. Inicie uma tentativa e abra Importar dados.
3. Selecione pasta antiga ou banco SQLite consistente, ou envie arquivos.
4. Revise grid, seleções e prévias formatadas com segredos mascarados.
5. Importe para staging e revise eventos.
6. Configure infraestrutura/credencial e publique após confirmar o candidato.

A origem não recebe migrações Alembic, alteração .env ou escrita dupla.
SQLite legado é normalizado em cópia; ORM antigo é atualizado somente em cópia.
Bancos desconhecidos, revisões futuras, corrupção ou sidecars são recusados.
Pare a origem e obtenha backup consistente; não remova WAL/SHM/journal manualmente.

## CLI do setup

Encerre o servidor setup para liberar o lock:

```powershell
python -m setup.import_legacy --source "C:\Projetos\Bridge-Antigo"
python -m setup.import_legacy --source "C:\Projetos\Bridge-Antigo" --import-data --allow-partial
python -m setup.import_legacy --source "C:\Backup\bridge.sqlite3" --sqlite --import-data
```

Use --select repetidamente para caminhos legados suportados. Havendo dois
devices.yml, escolha exatamente um. Não se mesclam fontes conflitantes.

A reparação --disable-invalid-remote-control é opcional e explícita.
Ela trata somente atuadores legados elegíveis sem state_topic, registra
remote_control=false e não altera a origem. Não inventa tópicos nem relaxa
failsafe, GPIO, ROM ID ou gás. Corrija referências antes de reativar a permissão.

## Migração parcial

A opção --allow-partial é somente para YAML/JSON.
Entidades/arquivos opcionais rejeitados geram advertência e needs_review.
Dispositivos críticos inválidos não produzem banco candidato.
SQLite incompatível/corrompido não é recuperado linha por linha pelo importador.

## Ferramentas de compatibilidade

tools/migrate_legacy_to_sqlite.py, storage.cli normalize e orm-audit continuam
disponíveis para fluxos avançados legacy e auditoria em cópias separadas.
Não são comandos a executar sobre o banco ORM já publicado pelo setup.
O CLI antigo pode gerar ZIP de origem com credenciais; preserve-o privadamente.
Ao comparar origem/candidato, use um par ainda não alterado pelo runtime.

## Retorno e recuperação

Abortar antes da publicação remove somente staging da tentativa.
Publicação incompleta usa Retomar/rollback do assistente; publicação concluída
usa restauração de conjunto coerente conforme [Manutenção](21-manutencao-recuperacao.md).
Nunca sobrescreva um DB existente nem faça downgrade destrutivo de Alembic.
