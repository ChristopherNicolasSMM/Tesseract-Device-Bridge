# 09 — Estado atual do cutover e do setup | 2.0.0

Atualização: 05/11/2026. Esta página substitui o diagnóstico anterior em que o ORM
era permitido somente em simulação. A main continua preservada.

| Área | Implementação atual | Homologação |
|---|---|---|
| Persistência ORM e fachada única | SQLAlchemy/Alembic 0003; sem escrita dupla | Suíte e hardware devem ser verificados por versão |
| Bootstrap vazio | Cabeçalhos/perfis essenciais, zero fake devices | Testes escritos e fluxo de configuração sem runtime |
| Origem YAML/JSON/SQLite | Captura/normalização em staging, origem somente leitura | Conferir dados reais e formatos das instalações antigas |
| Assistente Flask | Local, i18n, temas, grid/prévia/upload | Validação visual Windows/Pi pendente |
| Administração | Token gerado/customizado ou política local sem token | Regressão de origem/CSRF/rede documentada |
| Publicação | Receipt, identidade DB/.env, retomada e rollback incompleto | Testes e interrupção real em plataforma de teste |
| Gate ORM | Conclusão válida; modo configurado requer autorização | Não existe outra fase obrigatória no código após concluir |
| Instalação vazia | App administrativo sem DeviceRuntime/GPIO/MQTT | Revisar primeiro cadastro e reinício |
| Serviço | Unidade com ID único, ações separadas via tools/ | Systemd físico e permissões ainda pendentes |
| Documentação e CI | Manuais consolidados, Ubuntu/Windows e Python 3.9/3.13 | Configurado não significa execução aprovada |

O backend legacy continua compatível e selecionável para instalações existentes.
Novas instalações usam ORM. As tabelas legadas que eventualmente permaneçam numa
cópia normalizada não recebem sincronização nem escrita paralela pelo backend ORM.
Não há remoção destrutiva de schema por esta entrega.

O processo recusa publicação incompleta, banco/receipt incompatíveis e tentativa
de sair da simulação sem estado autorizado. Intertravamentos de hardware e a
exigência Python 3.9 para GPIO real permanecem independentes do ORM.

As revisões 0001/0002/0003 preservam hardware, receitas, controle, calibração,
sessão, revisões históricas, rascunhos, auditoria e manifestos. A CLI orm-audit
compara origem e candidato apropriados antes de serem usados/alterados.
Não compare uma base de trabalho já editada com o snapshot anterior como se
a divergência fosse necessariamente corrupção.

Referências atuais:
- [Instalação e migração](../manual/20-instalacao-migracao-2.0.0.md)
- [Arquitetura consolidada](18-setup-arquitetura.md)
- [Evidências e aceite pendente](../homologacao/setup-2.0.0.md)
- [Sandbox ORM de compatibilidade](10-cutover-orm-simulacao.md)
