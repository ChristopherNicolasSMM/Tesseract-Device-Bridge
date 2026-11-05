# 07 — Caminhos no Windows e Raspberry Pi

## Clone novo e instalação anterior

Use um clone separado da branch `feature/sqlite-full-migration`. A pasta antiga
é origem somente leitura; não execute a migração nela e não a atualize como
pré-requisito para importar. Siga [Primeiros passos](02-primeiros-passos.md)
e o [manual consolidado](20-instalacao-migracao-2.0.0.md).

Com a venv ativa e dependências instaladas:

```powershell
python -m setup
```

O setup começa sem `.env` ou banco e publica, após confirmação,
`data/private/bridge.sqlite3` e `.env`. Não use `storage.cli init` para substituir
o bootstrap ORM do assistente. Esse comando permanece para compatibilidade legacy.

## Resolução dos caminhos

| Caminho | Onde existe |
|---|---|
| Pasta/SQLite selecionado por caminho | Máquina que executa o setup |
| Arquivo selecionado no upload | Máquina do navegador; cópia privada no servidor |
| `./data/private/bridge.sqlite3` | Relativo à raiz do clone novo |
| `data/private/setup/` | Estado, staging e recursos privados do instalador |
| `data/private/installation.json` | Recibo da publicação, ligado ao banco e configuração |
| Backup externo | Fora do clone, em local privado escolhido pelo operador |

Caminhos relativos de infraestrutura são ancorados na raiz do projeto, não na
pasta de abertura do terminal/IDE. Execute comandos de manutenção na raiz para
evitar ambiguidade em argumentos explícitos. No PowerShell, coloque caminhos
com espaços entre aspas; exemplos de pastas Windows não existem no Raspberry.

## Windows

Ative `.\venv\Scripts\Activate.ps1`. Para testes, mantenha simulação e painel
em `127.0.0.1:8089`. Não há instalação automática de serviço Windows nesta versão.
Portas seriais usam nomes como `COM3`; pertencem ao servidor, não ao navegador.
Modo privado POSIX não substitui ACLs do Windows: revise permissões de `.env`,
bancos e backups no sistema de arquivos.

## Raspberry Pi

Use ambiente Python 3.9 para backend físico, banco local e usuário com acesso aos
dados privados. O serviço gerenciado usa caminhos absolutos do clone/venv e não
precisa de desktop. Gerar, instalar, habilitar e iniciar são ações distintas.
Consulte [conclusão e serviço](19-conclusao-servico.md).

Para acessar setup/administração local sem token, use túnel SSH. Portas seriais
podem exigir permissão do usuário (normalmente grupo `dialout`). Nunca execute
duas instâncias físicas disputando GPIO/atuadores nem rode o servidor como root
para contornar permissões.

## Mudança de pasta ou máquina

Pare os processos e restaure um conjunto coerente de banco, `.env`, recibo e
estado; recrie a venv no destino. Não copie a venv entre Windows e Raspberry.
Caminhos absolutos da unidade systemd precisam de revisão se o clone mudar.
Veja [backup, atualização e recuperação](21-manutencao-recuperacao.md).
