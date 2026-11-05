# 01 — Introdução | Tesseract Device Bridge 2.0.0

O **Tesseract Device Bridge** é a aplicação local que lê sensores,
controla bombas e aquecimento e executa receitas de brassagem em etapas,
com metas de temperatura, patamares e alarmes. Pode operar sem conexão
com o Tesseract Core, ou integrar-se via MQTT quando habilitado.

## O que muda na versão 2.0.0

Na arquitetura 2.0.0, **o SQLite é a única fonte de dados operacionais**:
dispositivos, configurações, receitas, seleção de receita, parâmetros
térmicos, calibração e estado de sessão. Não é necessário localizar e
editar `devices.yml` ou `receita.json` para fazer manutenção cotidiana.

O painel oferece cinco áreas:

- **Painel:** sensores e atuadores em tempo real.
- **Gerenciamento:** inventário e **Administração SQLite** com token ou política local explícita,
  rascunhos, validação, aprovação, backups e auditoria.
- **Receitas:** execução, status, etapas, temporizadores e alarmes.
- **Configurações:** controles térmicos e calibração individual.
- **Cadastro:** catálogo, duplicação e seleção de receitas.

Para teste, o `.env` define o banco, a porta e o bloqueio
`SIMULATION_ONLY=1`. O backend simulado não opera GPIO real nem MQTT.

## Instalação e diagnóstico

O clone novo abre `python -m setup` sem banco ou .env prévios. A importação
usa cópias privadas, sem modificar a instalação antiga. O monitor serial
administrativo permite testar abertura e ler portas sem cadastro, inclusive
na configuração inicial vazia; atua nas portas do servidor.

Consulte o [manual consolidado](20-instalacao-migracao-2.0.0.md) e o
[guia de diagnóstico](14-diagnostico-hardware.md).

## Segurança física

O sistema possui bloqueios de emergência e mecanismos de fail-safe.
Configurações físicas aprovadas não são aplicadas no meio da operação:
exigem reinicialização supervisionada, com equipamento parado. A fonte
auxiliar GLP também requer proteção física independente do software.

## Estado desta versão

**2.0.0 está em homologação** na branch
`feature/sqlite-full-migration`. A versão estável anterior segue na
`main` e não deve ser substituída antes de testes completos no
Raspberry Pi.

Leia [Primeiros passos](02-primeiros-passos.md),
[Administração SQLite](13-administracao-sqlite.md) e
[Migração dos arquivos antigos](12-sqlite-migracao.md).
