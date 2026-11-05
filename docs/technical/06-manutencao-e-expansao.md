# 06 — Manutenção e expansão | 2.0.0

## Manutenção de uma instalação

Use a Administração SQLite para rascunhar/validar/aprovar cadastros. A revisão
aprovada entra no snapshot após reinício seguro; não edite tabelas diretamente
para contornar validações. Receitas, seleção ativa, calibrações e sessão são
persistidas pelo router/repositórios. YAML/JSON antigos não são fontes operacionais.

O backup administrativo copia o banco consistentemente. Para recuperar toda a
instalação, pare processos e preserve .env, data/private, recibo/estado e versão
de código coerentes. Não substitua só o SQLite de uma instalação publicada por
outro banco com identidade diferente. Procedimento: [manutenção e recuperação](../manual/21-manutencao-recuperacao.md).

## Adicionar funcionalidades ao produto

1. Implemente validação de domínio em serviços compartilhados, usados por HTTP e
   persistência. A UI não é a única barreira de consistência.
2. Acesse dados pelo router/repositórios; não introduza escrita dupla ou fallback
   implícito para arquivos legados. Se precisar mudar schema, crie revisão Alembic
   posterior às existentes, com política de preservação/recuperação documentada.
3. Altere hardware somente por DeviceRuntime. Preserve failsafe, prioridade de
   override manual e confirmação de bomba; RecipeEngine/painel não escrevem GPIO
   diretamente para disputar o mesmo atuador.
4. Atualize manual, contrato técnico e regressões apropriadas. Homologação física
   é um registro separado dos resultados simulados.

## Sensores e drivers

Drivers reais ficam em gpio/ e são registrados explicitamente com
register_analog_driver antes de construir o backend. Recebem parâmetros hardware
do cadastro aprovado. O DS18B20 é um sensor digital 1-Wire que fornece temperatura;
o Raspberry não possui ADC nativo. Um novo ADC/sensor exige driver, schema e
validações compatíveis, além de testes de bancada e documentação de permissões.
Não use um subtipo de temperatura para dados de outra grandeza sem ajustar os
contratos de domínio/unidade. Não inicialize o driver ao importar o setup.

## Diagnóstico serial

O núcleo `reusable/serial_monitor` não conhece dispositivos de brassagem. O
adaptador HTTP fornece autenticação e guarda operacional; o monitor oferece
somente leitura/teste de abertura, com ownership e expiração. Não reutilize
esse canal como atalho para comandos físicos ou desligamento de intertravamentos.
[Contrato serial](../modules/serial-monitor/README.md).

## Reutilização do assistente

Lock, JSON atômico, host/porta, dotenv, layout e navegação ficam em
reusable/guided_setup. Outro projeto fornece estados, schema, credenciais,
autorização HTTP, migrações e publicação. Não copie recibos, .env, bancos ou
scripts systemd de uma instalação para generalizar o componente.
[Guia do assistente](../modules/guided-setup/README.md).

## Contribuições e validação

Trabalhe na branch feature/sqlite-full-migration. Preserve instalações antigas e
main. Documente novos contratos e mudanças incompatíveis dos módulos independentes.
O pacote reutilizável está em 0.1.0; o build do assistente do Bridge é setup.11,
identificadores com escopos diferentes.

Antes de homologar, valide clone limpo, importação YAML/JSON e SQLite, falhas de
permissão/interrupção, retomada, segurança, UI e serviços no SO alvo. O estado
atual das evidências permanece na [matriz de homologação](../homologacao/setup-2.0.0.md).
