# Documentação — Tesseract Device Bridge 2.0.0

## Começar e manter

| Tema | Guia atual |
|---|---|
| Instalação e migração consolidadas | [Manual 2.0.0](manual/20-instalacao-migracao-2.0.0.md) |
| Primeiros passos | [Resumo Windows/Raspberry](manual/02-primeiros-passos.md) |
| Backup, atualização e recuperação | [Manutenção](manual/21-manutencao-recuperacao.md) |
| English setup guide | [Installation and migration](manual/setup-installation-en.md) |
| Assistente visual | [Importação pelo navegador](manual/16-importacao-navegador.md) |
| Infraestrutura e credencial | [Infraestrutura](manual/17-infraestrutura.md) · [Segurança](manual/18-credencial-administrativa.md) |
| Publicação e systemd | [Conclusão e serviço](manual/19-conclusao-servico.md) |
| Operação e administração | [Funcionalidades](manual/03-funcionalidades.md) · [Administração SQLite](manual/13-administracao-sqlite.md) |
| Controle térmico e sensores | [Temperatura](manual/05-configuracoes-temperatura.md) · [Calibração](manual/11-calibracao-sensores.md) |
| Emergência | [Desligamento](manual/06-desligamento-emergencia.md) |

## Engenharia e aceite

- [Arquitetura do setup](technical/18-setup-arquitetura.md)
- [Matriz de homologação e evidências](homologacao/setup-2.0.0.md)
- [Normalização SQLAlchemy](technical/08-normalizacao-sqlalchemy.md)
- [Auditoria inicial e reaproveitamento](technical/11-auditoria-setup.md)
- [Contrato de importação](technical/16-setup-import-contract.md)
- [Identidade e i18n](technical/17-setup-i18n-ui.md)

Os documentos 15–19 do manual registram entregas incrementais. O manual 20 consolida
o comportamento atual e prevalece sobre avisos históricos de etapas ainda não
implementadas. Os guias antigos de cutover são referências de sandbox/compatibilidade,
não uma proibição absoluta do ORM físico após conclusão válida do setup.

## Componentes para outros projetos

- [Índice dos módulos reutilizáveis](modules/README.md)
- [Monitor serial: UI, API e limites](modules/serial-monitor/README.md)
- [Setup guiado: configuração, persistência e layout](modules/guided-setup/README.md)
- [Arquitetura e guia de integração](modules/arquitetura.md)
