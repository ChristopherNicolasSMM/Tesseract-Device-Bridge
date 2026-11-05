# 15 — Assistente de instalação

Referência atual: **2.0.0-setup.12**, branch `feature/sqlite-full-migration`.
O [manual consolidado](20-instalacao-migracao-2.0.0.md) cobre o fluxo completo;
este guia descreve abertura, retomada e cancelamento.

## Iniciar sem configuração anterior

Após clonar a branch e instalar `requirements.txt` na venv, execute na raiz:

```powershell
python -m setup
```

Não copie `.env.example` nem crie SQLite antes de abrir o assistente.
Acesse `http://127.0.0.1:8090` ou `http://localhost:8090`, conforme a URL impressa.
Se a porta estiver ocupada, use `python -m setup --port 8091` e a porta correspondente
no navegador. Reinicie o processo depois de atualizar o código e recarregue a página.

O assistente tem cinco telas: idioma/aparência, dados, infraestrutura, credencial
e conclusão. Pode criar ORM vazio ou importar dados antigos em staging, revisar
pendências, preparar configuração e publicar a instalação com confirmação.
Abrir o setup não inicializa DeviceRuntime, GPIO, painel operacional ou MQTT.

## Acesso ao Raspberry

O servidor escuta somente em loopback, sem debugger/reloader. No computador cliente:

```bash
ssh -N -L 8090:127.0.0.1:8090 usuario@raspberry
```

Abra a URL local no computador; mantenha a mesma porta nas duas pontas do túnel.
Formulários exigem sessão/CSRF e origem local correspondente. Não exponha o
instalador por proxy público. Caminhos digitados pertencem ao servidor; arquivos
no computador cliente devem ser enviados por upload.

## Retomar e cancelar

Ctrl+C encerra o servidor e preserva a tentativa. Execute novamente para retomar.
A sessão HTTP é nova: recarregue a página antes de enviar formulários.
Somente um processo pode manter o lock da instalação.

Antes de publicar, Cancelar remove somente o staging identificado pela tentativa.
Arquivos da instalação antiga permanecem intactos. Manifesto e lock ficam em
`data/private/setup/`; não os edite manualmente. Estado desconhecido/corrompido
impede continuar e fica preservado para diagnóstico.

Depois de iniciada a publicação, use as ações de recuperação da tela Concluir.
Cancelar não remove uma instalação publicada. Consulte [recuperação e serviço](19-conclusao-servico.md).

## Modo de operação

Instalação vazia não recebe dispositivos ou receitas fictícias e é publicada em
simulação. O Bridge abre a configuração administrativa sem criar runtime físico;
o monitor serial fica disponível para diagnóstico explícito, mesmo sem cadastro.

A autorização ORM para modo configurado depende da conclusão válida e explícita
do setup. Pendências e publicação interrompida mantêm o bloqueio físico. Não há
uma etapa adicional obrigatória de homologação ORM após concluir; isso não remove
intertravamentos nem constitui homologação física do equipamento.

## Diagnóstico e validação

```powershell
python -m setup.doctor
python -m pytest tests/test_setup.py -q
```

O diagnóstico não abre o banco ou o `.env` para revelar conteúdo e não repara
arquivos. O núcleo genérico de configuração/persistência/layout fica em
`reusable/guided_setup/`; veja o [guia de reaproveitamento](../modules/guided-setup/README.md).

### Revisão da importação — setup.13

No modo SQLite, informe o arquivo ou selecione uma pasta. A descoberta procura
`.sqlite3`, `.sqlite` e `.db` na pasta e em `data/`, `data/public/` e `data/private/`,
sem busca recursiva irrestrita. Selecione apenas um banco por importação. Bancos
não importáveis aparecem desabilitados; pare a instalação antiga e forneça um
backup consistente, sem arquivos WAL/SHM/journal pendentes.

A importação parcial não ignora uma configuração de dispositivos inválida. O
relatório diferencia lista vazia, campos obrigatórios ausentes, YAML inválido e
controle remoto sem tópico de estado, sem mostrar valores ou credenciais. Para
configuração vazia, use o fluxo de instalação sem dados. Outras falhas de esquema
ainda exigem revisar uma cópia do arquivo; não habilite hardware para contorná-las.

Se o descarte falhar, o diagnóstico distingue publicação existente de arquivos
bloqueados. No primeiro caso use recuperação/rollback; no segundo feche o programa
que usa os temporários e repita. A tentativa permanece disponível para repetição.
