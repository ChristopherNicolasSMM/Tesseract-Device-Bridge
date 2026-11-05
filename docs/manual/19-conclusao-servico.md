# Etapa 9 — Publicação, recuperação e serviço

Entrega na branch feature/sqlite-full-migration. Testes escritos e não executados
pelo assistente, por autorização do usuário. Sintaxe Python/JSON, JavaScript e shell verificada antes
da publicação; Windows/Pi/systemd exigem homologação local. Templates Jinja ainda
precisam da validação funcional local (a dependência não estava disponível aqui). Build: 2.0.0-setup.9.

## Concluir

Prepare banco/importação, infraestrutura e credencial. Abra Concluir instalação,
selecione explicitamente um candidato e revise o resumo. Nenhum banco definitivo
existente será substituído. Se existir .env na instalação nova, confirme sua troca;
o original precisa estar inalterado desde a preparação e terá backup privado.

Modo configurado (SIMULATION_ONLY=0) exige autorização explícita no formulário.
Backend físico também mantém a exigência existente de Python 3.9 no Raspberry.
Não existe etapa adicional obrigatória de homologação ORM depois da conclusão:
a publicação válida remove seu bloqueio transitório. Nenhum GPIO/MQTT/runtime é
iniciado pelo setup, mesmo ao publicar no modo configurado.

Sem dispositivos: publicação ready_simulated e .env forçado para simulação.
python run_bridge.py ou python run_panel.py abre somente a configuração administrativa
local, sem criar DeviceRuntime, GPIO ou conexão MQTT. Cadastre dispositivos válidos
e reinicie para abrir o painel operacional simulado. Para alterar para modo configurado,
revise .env e use a revalidação explícita na conclusão do setup.

Com pendências de importação/sessão: status needs_review e simulação forçada.
Depois de corrigir dados no painel simulado, a seção de manutenção permite
revalidar integridade, dispositivos, receitas e controles, mediante confirmação
de que as pendências foram resolvidas. Não é possível promover para modo configurado
sem autorização e configuração válida. Essa manutenção não substitui a instalação.

## Protocolo de publicação

- Banco e .env candidatos são preparados integralmente no staging.
- Receipt privado data/private/installation.json registra status publishing antes
  de qualquer arquivo definitivo. O bootstrap bloqueia inicialização incompleta.
- Arquivos novos usam cópia privada sincronizada e hard link exclusivo, sem sobrescrita.
  Se o filesystem não suportar hard links, falha com preservação, sem cópia parcial.
  Usar filesystem local com suporte (NTFS/ext4); não publicar em FAT/exFAT.
- .env anterior é copiado para backup privado e conferido por SHA-256 antes da troca.
- Receipt só muda para estado final após ambos os arquivos estarem publicados.
- Identificador da instalação no .env e PRAGMA application_id na cópia vinculam
  configuração/banco ao receipt. O hash inicial não é exigido após o runtime gravar
  dados, porque sessões e cadastros precisam continuar editáveis.
- Não há alteração de schema ORM: application_id é metadado de identificação SQLite,
  não uma nova tabela. Alembic 0003 permanece íntegro.
- Dados antigos, serviços antigos e main não são modificados.

Se cair antes da confirmação, não há publicação. Se cair durante a publicação,
reabra python -m setup e Concluir instalação: escolha Retomar ou Desfazer publicação
incompleta. O rollback só remove arquivos correspondentes aos hashes registrados
e restaura o backup quando aplicável. Arquivos alterados externamente provocam
recusa para revisão manual. Nunca apagar WAL/journal ou bancos à força.
Cancelamento comum é bloqueado enquanto há publicação; não elimina backups.
Uma instalação concluída não é removida pelo botão Cancelar.

Após concluir, use Encerrar assistente e inicie o Bridge manualmente.
O botão encerra o servidor local; pode fechar a janela. O serviço é opcional.

## systemd

O fluxo usa tools/install_service.sh --setup-managed com adaptador Python único.
O script antigo continua disponível para compatibilidade explícita; o setup não
chama o instalador legado que sobrescreve tesseract-bridge.service.
A unidade nova usa nome com ID único da instalação; não substitui unidade anterior.

Gerar na tela de conclusão não exige root. Requer Linux com systemd ativo e usuário
não-root existente, com o mesmo UID do usuário que executa o setup. Execute o setup
como o usuário desejado para preservar o acesso aos dados privados. Usa o Python absoluto do ambiente em que o setup foi executado,
WorkingDirectory do clone novo, Restart=on-failure, UMask=0077 e multi-user.target.
Não depende de desktop/kiosk ou watchdog externo. O .env é carregado pelo loader
Python existente; não se injeta EnvironmentFile systemd porque dotenv pode conter
sintaxe que systemd não interpreta da mesma forma. Credenciais não ficam na unidade.

Comandos separados, mostrados na interface (ajuste o caminho gerado):

sudo bash tools/install_service.sh --setup-managed install "data/private/setup/services/tesseract-bridge-ID.service"
sudo bash tools/install_service.sh --setup-managed enable "data/private/setup/services/tesseract-bridge-ID.service"
sudo bash tools/install_service.sh --setup-managed start "data/private/setup/services/tesseract-bridge-ID.service"

Install verifica systemd-analyze antes de criar a unidade, recusa destino existente
e registra ownership. Enable não inicia; Start exige receipt pronto e banco validado.
Para remover somente essa unidade:

sudo bash tools/uninstall_service.sh --setup-managed "data/private/setup/services/tesseract-bridge-ID.service"

Headers/ID/hash são verificados antes de habilitar, iniciar ou remover. Não se varrem
outros usuários nem se removem recursos da instalação antiga. Qualquer unidade alterada
externamente exige revisão. Em Windows/Linux sem systemd, a interface fornece execução
manual. O setup Flask nunca executa sudo nem inicia hardware automaticamente.

## Validação local

```powershell
git pull --ff-only origin feature/sqlite-full-migration
python -m pytest tests/test_setup_publication.py tests/test_setup_service.py tests/test_orm_cutover.py tests/test_setup_security.py -q
python -m pytest -q
python -m setup
```

Validar instalação vazia, origem legada, publicação interrompida/retomada, rollback,
.env existente/alterado, destino existente, bloqueio de arquivo no Windows, identidade
do banco e painel só de configuração. Serviço e GPIO real dependem da plataforma local.
O encerramento da Etapa 10 exige documentação consolidada e homologação das plataformas.
