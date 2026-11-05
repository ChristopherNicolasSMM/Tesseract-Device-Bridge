# Manual de Instalação e Migração — Tesseract Device Bridge 2.0.0

Atualizado em 05/11/2026. Branch de trabalho: feature/sqlite-full-migration.
Build do instalador: 2.0.0-setup.11. Implementação disponível para homologação;
a matriz de plataformas ainda precisa dos aceites registrados em
[Homologação](../homologacao/setup-2.0.0.md). A main permanece preservada.

## 1. Modelo de instalação

O setup é executado num clone novo. A instalação antiga serve apenas como origem
de leitura; seus bancos, YAML/JSON, .env e serviço não são migrados no local.
O assistente inicia sem banco, sem .env e sem dispositivos. Nunca inicializa
GPIO, DeviceRuntime ou conexão MQTT.

O processo termina com banco ORM, .env e receipt privados coerentes.
Uma instalação vazia fica sem dispositivos fictícios e sem receitas.
O antigo storage.cli init continua disponível para compatibilidade legacy e
possui seed de demonstração; ele não é o bootstrap do novo instalador.

## 2. Dependências e clone

Git, Python e dependências de requirements.txt. Use ambiente virtual.
Windows/Python 3.13 pode executar setup e simulação. GPIO real no Raspberry
continua exigindo a venv Python 3.9 já prevista pelo projeto; não substitua o Python
do sistema operacional. Em Linux com Python gerenciado, instale dependências na venv.

Windows / PowerShell:

```powershell
git clone --branch feature/sqlite-full-migration --single-branch https://github.com/ChristopherNicolasSMM/Tesseract-Device-Bridge.git Tesseract-Device-Bridge-SQLite
cd Tesseract-Device-Bridge-SQLite
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m setup
```

Linux / Raspberry, para setup e simulação:

```bash
git clone --branch feature/sqlite-full-migration --single-branch https://github.com/ChristopherNicolasSMM/Tesseract-Device-Bridge.git Tesseract-Device-Bridge-SQLite
cd Tesseract-Device-Bridge-SQLite
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m setup
```

Se pretende concluir com backend físico, use o Python 3.9 apropriado ao equipamento
para criar a venv antes de instalar as dependências. O setup validará essa condição.
Não copie .env.example nem crie banco manualmente antes do assistente.

Abra http://127.0.0.1:8090. Para outra porta: python -m setup --port 8091.
A versão impressa no terminal também aparece no cabeçalho e em /setup-version.
Não execute o assistente como root.

No Raspberry sem navegador, mantenha o servidor em loopback e crie um túnel
no computador do navegador:

```bash
ssh -N -L 8090:127.0.0.1:8090 usuario@raspberry
```

Use a mesma porta nos dois lados. localhost também é aceito, mas mantenha o mesmo
endereço durante a sessão. Reiniciar o servidor invalida cookies/CSRF anteriores;
reabra a página inicial. Proxy de rede não substitui o túnel.

## 3. Idioma, aparência e origem

Selecione pt_BR ou en e inicie/retome a tentativa. Temas claro e escuro persistem.
O shell segue a identidade do Tesseract principal com recursos locais, sem CDN.
Na preparação de dados, escolha:

| Origem | Procedimento |
|---|---|
| Instalação limpa | Preparar banco vazio na página inicial |
| YAML/JSON de versão sem SQLite | Descobrir a pasta antiga ou enviar arquivos pelo navegador |
| SQLite legado/ORM | Selecionar um backup consistente por caminho ou upload |

O caminho digitado existe no computador que executa o setup. Para arquivos no
computador do navegador e servidor no Raspberry, use upload.

### YAML/JSON

A descoberta visita somente raiz, data, data/public e data/private.
O adaptador reconhece devices.yml na raiz ou data/public, recipe.yml,
receita_base.yaml, catálogos receita.json e arquivos de controle/calibração/sessão
nos caminhos já suportados. Arquivos desconhecidos são listados como ignorados.
Não são executados nem oferecidos para prévia.

No grid, confira nome/origem, formato, tamanho, registros detectáveis e
compatibilidade. Selecione exatamente um devices.yml quando houver dois aliases.
Exibir abre JSON/YAML formatado, com credenciais mascaradas e limite de conteúdo.
Arquivos malformados não são exibidos como texto bruto.

Para receita.json isolado, indique explicitamente destino público ou privado.
Uploads YAML/JSON podem ser acrescentados ao inventário da tentativa; destinos
duplicados são recusados, sem sobrescrita silenciosa. Para mudar de origem,
faça nova descoberta ou escolha um SQLite, ou cancele e reinicie a tentativa.

Sem importação parcial, dados inválidos abortam o job. Com a opção explícita,
arquivos opcionais e entradas de catálogos inválidos são registrados para revisão,
mantendo os dados válidos. Dispositivos críticos inválidos não produzem banco
candidato; só um relatório needs_review. Não há redução silenciosa de proteção.

A CLI de compatibilidade continua disponível:

```powershell
python -m setup.import_legacy --source "C:\Projetos\Bridge-Antigo"
python -m setup.import_legacy --source "C:\Projetos\Bridge-Antigo" --import-data --allow-partial --language pt_BR
```

Encerre o servidor setup antes da CLI porque ambos precisam do mesmo lock.
A opção --disable-invalid-remote-control é uma reparação explícita da CLI;
o assistente web não a ativa silenciosamente.

### SQLite

A origem é capturada antes da inspeção. Não se abre o SQLite antigo para recuperar
journal ou escrever nele. São aceitos esquema legado conhecido e ORM Alembic
0001/0002/0003; upgrade ocorre exclusivamente em cópia. Bancos desconhecidos,
corrompidos ou revisões futuras são recusados.

WAL, SHM ou journal existentes causam recusa. Pare o Bridge antigo e forneça
um backup SQLite consistente/checkpointado. Não apague os sidecars manualmente:
eles podem conter dados confirmados ainda ausentes do arquivo principal.

```powershell
python -m setup.import_legacy --source "C:\Backup\bridge.sqlite3" --sqlite --import-data
```

### Relatórios e limites

Eventos: imported, warning, blocking_error, ignored, com mensagens traduzidas.
Hashes, contagens, reparos e caminhos relativos do candidato ficam privados.
Exceções não são copiadas para o relatório com conteúdo arbitrário de arquivos.

- YAML/JSON: 8 MiB por arquivo, 32 MiB por conjunto.
- Descoberta: até 1000 entradas nos diretórios autorizados.
- SQLite: 256 MiB; HTTP: 257 MiB, até 120 partes.
- Prévia: entrada de até 256 KiB, saída de até 64 KiB.
- Sem execução de YAML arbitrário, extração ZIP ou SQL enviado pelo navegador.
- Seleção do grid usa IDs do inventário; não aceita um caminho livre para prévia.

A importação é síncrona: o indicador mostra atividade, sem porcentagem fictícia.
O relatório aparece ao terminar. Não feche o processo durante a gravação; para
cancelar, aguarde a resposta e descarte a tentativa. Uma interrupção conserva
temporários privados para diagnóstico, nunca publica automaticamente o resultado.

## 4. Infraestrutura e credencial

O formulário apresenta dicas para cada campo. Caminho definitivo automático:
./data/private/bridge.sqlite3; persistência orm.

| Campo | Efeito |
|---|---|
| SIMULATION_ONLY=1 | Simulação; MQTT desligado; painel em 127.0.0.1 |
| TEST_PANEL_PORT | Porta efetiva em simulação; padrão 8089 |
| PANEL_HOST / PANEL_PORT | Overrides fora da simulação; ignorados em simulação |
| DB | Relativo à raiz da instalação, independente do diretório de execução |

O teste de porta usa bind/close, sem servidor extra nem hardware. IPs não locais
e nomes DNS são marcados como disponibilidade não verificada. A porta deverá
ser reconferida no início do serviço; a verificação pontual não a reserva.

O .env ativo não é alterado nessa tela. São preparados candidatos imutáveis
privados, preservando comentários e variáveis não editadas do .env local, quando válido.

Na credencial, escolha geração segura, token personalizado ou ausência de token.
Token curto é aceito com aviso; não há regra de complexidade. Há limite de 4096 bytes
e recusa de CR/LF/NUL. O token gerado aparece uma vez; copie-o antes de sair.
Não é persistido no cookie, localStorage ou logs. Gerar outro invalida o candidato
anterior para a publicação futura.

O candidato usa ADMIN_TOKEN_B64 para serialização e compatibilidade Unicode/dotenv.
Base64 não é criptografia: .env, backups e candidatos continuam sendo segredos.
ADMIN_TOKEN textual antigo continua suportado; B64 não vazio tem prioridade.

Sem token exige confirmação de política local: LOCAL_ADMIN=1 força o painel para
127.0.0.1; administração remota, proxy, Host externo e requisição sem CSRF/origem válida
são recusados. No painel, deixe o token vazio e clique Desbloquear para criar sessão.
Instalações antigas sem token e sem política explícita mantêm administração desativada.
O token protege /api/admin, não substitui a política de todas as rotas /api ou do MQTT.
Intertravamentos de gás, temperatura, emergência e sessão continuam ativos.

Alterar infraestrutura exige preparar novamente a credencial.

## 5. Publicação e início

Em Concluir instalação, selecione um candidato. Um banco definitivo existente
nunca é sobrescrito. Confirme a troca do .env local, se necessário; o conteúdo deve
permanecer igual ao que foi lido durante a preparação e terá backup privado.

A autorização de modo configurado é explícita. A conclusão válida remove o bloqueio
transitório do ORM, sem exigir uma nova fase posterior como barreira de software.
Isso não constitui homologação física do equipamento. O setup não inicia GPIO,
MQTT ou serviço automaticamente.

| Estado | Comportamento |
|---|---|
| new / in_progress | Preparação e staging; não concluído |
| publishing | Publicação incompleta; início do runtime bloqueado |
| needs_review | Pendências; configuração forçada para simulação |
| ready_simulated | Concluído em simulação |
| ready_operational | Concluído e autorizado em modo configurado |

Sem dispositivos, a publicação termina em ready_simulated. A execução abre
somente configuração administrativa, sem criar DeviceRuntime/GPIO/MQTT.
Cadastre dispositivos válidos, aprove a configuração e reinicie para o painel simulado.

Após Encerrar assistente:

```powershell
python run_bridge.py
```

O botão de revisão da instalação publicada permite revalidar após corrigir pendências,
desde que não haja sessão pendente. Modo configurado exige .env coerente, dispositivos
válidos, ambiente físico compatível e confirmação explícita. Não exclua receipt para
contornar a barreira. Para diagnóstico somente de leitura:

```powershell
python -m setup.doctor
```

Esse comando não valida fiação ou toda a integridade do banco, não abre GPIO e não
mostra valores de credenciais. Código de saída 1 indica inconsistência detectada.

## 6. Publicação interrompida e cancelamento

O receipt data/private/installation.json é gravado como publishing antes de publicar
os arquivos definitivos. O bootstrap fica bloqueado até a conclusão ou recuperação.
Banco/configuração são vinculados por ID, caminho e application_id do SQLite.

Se o processo cair: reabra python -m setup, acesse Concluir instalação e escolha
Retomar ou Desfazer publicação incompleta. O rollback só remove os arquivos que
correspondem aos hashes registrados e restaura o .env anterior, quando aplicável.
Alterações externas ou sidecars provocam recusa e exigem revisão manual.
Uma instalação concluída não é removida por Cancelar.

Publicação nova exige filesystem local com hard links exclusivos (ex.: NTFS/ext4).
FAT/exFAT ou compartilhamento sem suporte falha preservando os dados.
Antes da publicação, Cancelar remove somente temporários da tentativa.
Não utilize git clean -xfd para limpar o projeto: ele pode apagar dados privados.

## 7. Serviço opcional

Windows e Linux sem systemd: execução manual. Em Linux com systemd ativo,
gere a unidade após concluir sem pendências. O setup deve executar como o mesmo
usuário não-root do serviço; o Python absoluto da venv é registrado na unidade.

Gerar não instala; instalar não habilita; habilitar não inicia.
A interface fornece caminhos reais para comandos separados:

```bash
sudo bash tools/install_service.sh --setup-managed install "CAMINHO_GERADO.service"
sudo bash tools/install_service.sh --setup-managed enable "CAMINHO_GERADO.service"
sudo bash tools/install_service.sh --setup-managed start "CAMINHO_GERADO.service"
```

A unidade tem ID único, não substitui tesseract-bridge.service antigo, e não exige
desktop/kiosk. O loader Python lê .env; não se interpreta esse arquivo como shell
nem se depende de EnvironmentFile systemd com semântica diferente.
Verificação, ownership, hash e rollback da instalação do serviço estão em
[Conclusão e serviço](19-conclusao-servico.md). Remoção é direcionada à unidade:

```bash
sudo bash tools/uninstall_service.sh --setup-managed "CAMINHO_GERADO.service"
```

Não use o instalador legado sem argumentos para uma instalação criada pelo setup.

## 8. Backup, atualização e retorno

Guia completo: [Manutenção e recuperação](21-manutencao-recuperacao.md).
Pare o runtime/serviço antes de backup de instalação, atualização ou restauração.
O backup deve preservar banco, .env, receipt e estado do setup como conjunto.
Não transporte a venv entre máquinas; recrie-a.

Atualização de código não exige repetir a migração YAML/JSON nem apagar dados:

```powershell
git status
git pull --ff-only origin feature/sqlite-full-migration
python -m pip install -r requirements.txt
python -m pytest -q
python -m setup.doctor
```

Reabra o setup para manutenção, não para sobrescrever um banco publicado.
Não faça merge com main sem solicitação explícita.

## 9. Resolução de problemas

| Sintoma | Verificação / ação |
|---|---|
| Tela sem CSS / teste não encontrado | Confira branch, resultado do pull e build. Reinicie setup; não aplique patches antigos sobre commits publicados |
| POST 403 | Reabra a página no mesmo host/porta. Reinício invalida sessão. Não desabilite CSRF |
| WinError 32 ao descartar SQLite | Feche conexões/aplicativos que usam o arquivo. Use a versão com fechamento explícito; não force a exclusão |
| Destino existente | Preserve o banco; use manutenção ou outro clone, sem sobrescrita |
| .env mudou desde a preparação | Refaça infraestrutura e credencial antes de publicar |
| WAL/SHM/journal na origem | Pare a origem e produza backup consistente. Não apague sidecars |
| Identidade de banco divergente | Restaure conjunto coerente do backup, não apenas um SQLite qualquer |
| Serviço indisponível no Windows | Comportamento previsto; use execução manual |
| needs_review | Corrija pendências no painel simulado e faça revisão explícita |
| Python incompatível com GPIO | Use venv Python 3.9 no equipamento validado; setup/simulação continuam disponíveis |

Não compartilhe .env, tokens, backups, bases reais ou snapshots privados ao relatar erro.
Compartilhe commit, sistema, Python, resumo de testes e saída sanitizada do doctor.

## 10. Documentos relacionados

- [Índice](../README.md)
- [Contrato técnico](../technical/18-setup-arquitetura.md)
- [Matriz de homologação](../homologacao/setup-2.0.0.md)
- [Manual resumido em inglês](setup-installation-en.md)
