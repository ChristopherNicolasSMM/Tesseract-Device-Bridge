# Manutenção e recuperação de instalações publicadas

Este guia complementa o [manual consolidado](20-instalacao-migracao-2.0.0.md).
Não executa upgrades de hardware, troca de GPIO ou sincronização com a instalação antiga.

## Backup coerente

Encerre o runtime e o setup; se usa systemd, pare explicitamente a unidade gerada.
Não faça cópia de arquivos SQLite com o processo gravando.
O backup de banco pela CLI/API é consistente para o SQLite, mas não inclui .env,
receipt ou código. Para recuperar a instalação inteira, preserve o conjunto.

Windows, com processos parados, num destino novo fora do repositório:

```powershell
$backupDestino = Join-Path $env:USERPROFILE ("Bridge-Backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $backupDestino
Copy-Item .env (Join-Path $backupDestino ".env")
Copy-Item data/private (Join-Path $backupDestino "private") -Recurse
git rev-parse HEAD | Set-Content (Join-Path $backupDestino "commit.txt") -Encoding utf8
```

Linux, também com processos parados:

```bash
backup_destino="$HOME/Bridge-Backup-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$backup_destino"
cp -a .env "$backup_destino/.env"
cp -a data/private "$backup_destino/private"
git rev-parse HEAD > "$backup_destino/commit.txt"
chmod 600 "$backup_destino/.env"
```

Proteja o destino: ele contém token, senha MQTT, candidatos, dados e snapshots.
No Windows, use pasta pessoal com ACL restrita. Guarde cópia externa protegida.
O diretório private inclui installation.json e setup/state.json, além dos arquivos
que o registro de recuperação referencia. Não edite IDs ou application_id.

## Atualizar código

1. Pare o runtime/serviço e o setup.
2. Faça backup coerente.
3. Verifique git status e branch. Preserve alterações locais; não use reset --hard.
4. Faça pull --ff-only e instale requirements.txt na venv.
5. Execute a suíte local e o doctor.
6. Confira mudanças de schema/release antes de iniciar. Esta entrega mantém Alembic 0003.
7. Inicie manualmente ou autorize o serviço já instalado.

Se o pull divergir por patches aplicados manualmente, resolva o merge preservando
os dados privados. Marcadores <<<<<<< e >>>>>>> em Python/JSON não são código válido.
Não reaplique patch que já esteja representado no histórico remoto.

## Restaurar

Mantenha a instalação original e seu serviço parados. Prepare clone separado na
mesma versão do código registrada no backup. Crie nova venv e instale dependências.

Com o clone de restauração ainda sem banco/.env:
- copie o .env de backup para a raiz;
- copie o conteúdo de private para data/private;
- preserve exatamente receipt, ID, banco e estado correspondentes;
- execute python -m setup.doctor e confira o modo antes de iniciar.

Não rode o assistente de instalação limpa sobre esse conjunto restaurado.
Não inicie duas instâncias físicas da mesma planta.
O .env usa caminho relativo à raiz; ao mover entre plataformas, revise caminhos
legados externos que não tenham sido gerados pelo setup.

A unidade systemd contém caminhos absolutos e não deve ser reutilizada após mudar
pasta, usuário ou venv. Inicie manualmente no clone restaurado até revisar a unidade.
A geração se recusa a sobrescrever uma definição diferente com o mesmo ID:
arquive a definição antiga após revisão, sem alterar a unidade da instalação original
silenciosamente. Não apague seu registro de ownership para contornar a proteção.

## Recuperação do setup

Publicação incompleta: reabra setup e use Retomar ou rollback da própria tentativa.
Instalação concluída: use manutenção/revalidação, nunca Cancelar para remover dados.
Desfazer uma publicação concluída exige restauração explícita do conjunto de backup,
fora do fluxo de abortar. Não se usa downgrade destrutivo do Alembic.

Se outra aplicação alterou arquivos após a falha, a recuperação pode recusar hashes.
Pare os processos, preserve todos os arquivos e faça diagnóstico antes de qualquer
intervenção manual. Não remova banco, .env, receipt ou sidecars como tentativa genérica.

## Sandbox a partir de backup

Para experimentar, prefira um clone separado e uma cópia explícita.
Não aponte o ambiente de produção para o banco de sandbox.
Variáveis exportadas no shell têm prioridade sobre .env. Em especial, uma variável
TESSERACT_BRIDGE_INSTALL_ID de outra instalação pode impedir usar um sandbox.
Não copie credenciais para exemplos e não remova a identificação da produção.
Use modo simulado e ambiente isolado para o sandbox.
