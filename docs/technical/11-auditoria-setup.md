# Etapa 1 — Auditoria do instalador independente

Data: 05/11/2026. Branch: `feature/sqlite-full-migration`.
Base inspecionada: `d38e196f794de28676cf553ae945036883a3291d`.
Escopo: leitura do código, diagnóstico e verificações locais; sem alteração do runtime, serviço ou banco operacional.

## Decisão atualizada

Por orientação expressa do usuário, o bloqueio experimental que exige ORM em simulação dura somente até a conclusão válida do setup. Não haverá homologação posterior obrigatória como barreira adicional do ORM. O setup continua sem inicializar GPIO/MQTT, e sua conclusão não inicia o Bridge automaticamente.

Conclusão válida significa banco publicado e íntegro, configuração aprovada e ausência de pendências críticas. Se o usuário escolheu simulação, a instalação continua simulada. Se escolheu operação real com configuração válida, o runtime poderá usar o backend real após o setup. `needs_review`, publicação incompleta e ausência de dispositivos não liberam operação física. Os intertravamentos térmicos, de gás, emergência e permissões permanecem. A exigência existente de Python 3.9 para GPIO real é independente do ORM e não será removida incidentalmente.

## Inventário e decisão de reaproveitamento

| Componente real | Diagnóstico | Decisão |
|---|---|---|
| `tools/install_service.sh` | Detecta Linux/systemctl, sudo, usuário e `.venv`/`venv`; exige Python 3.9; gera serviço, watchdog e kiosk | Adaptar como único caminho de instalação de serviço; não invocar diretamente pelo wizard atual |
| `tools/uninstall_service.sh` | Remove serviço principal e autostart de logs; percorre vários usuários; deixa watchdog, timer e kiosk | Adaptar para remover somente recursos registrados da instalação selecionada |
| `tools/logs.sh` | Diagnóstico journal/boot log; nome de serviço fixo | Manter, parametrizar identidade de instalação |
| `tools/migrate_legacy_to_sqlite.py` | CLI com dry-run, backup obrigatório e recusa de destino existente | Preservar CLI e reutilizar serviços; não chamar CLI via shell HTTP |
| `tools/gpio_test.py` | Ferramenta manual que inicializa backend real e pode ligar saídas | Manter fora do setup e de seus testes |
| `tools/ajuste_fontes_linux` | Comandos avulsos para fontes e instalação de Tailscale via script remoto | Não integrar ao instalador; finalidade separada |
| `storage/legacy_import.py` | Parser YAML seguro, validação de domínio, manifesto/hash, backup e importação transacional | Adaptar descoberta, seleção, validação parcial, limites e confinamento de caminhos |
| `storage/orm_normalize.py` | Backup SQLite consistente, staging, Alembic, backfill e equivalência; publicação exclusiva por hard link | Reutilizar normalização; adaptar conexão de origem, destino de staging e recuperação |
| `storage/orm_audit.py`, mappers de configuração/sessão/histórico | Equivalência e preservação das entidades existentes | Reutilizar; separar auditoria contra legado de validação estrutural de uma instalação nova |
| `storage/models/`, `storage/repositories/` | ORM independente de Flask; sessões curtas; repositório exige settings e revisão 0003 | Reutilizar; acrescentar bootstrap vazio e verificação de estado |
| Alembic `bridge_orm_0001..0003` | Cadeia existente; downgrade destrutivo bloqueado | Preservar revisões; evolução nova em revisão posterior quando necessária |
| `storage/sqlite_store.py` | Bootstrap legado cria sensor demo; caminhos relativos ancorados na raiz | Preservar compatibilidade; não usar seed demo na instalação ORM limpa |
| `storage/store_router.py` | Fachada única, sem escrita dupla; `_orm()` exige simulação | Substituir bloqueio transitório por conclusão válida do setup na etapa apropriada |
| `storage/launch_config.py` | Overrides de ambiente; simulação desliga MQTT e fixa loopback | Reutilizar; checar estado antes de permitir criação do runtime |
| `run_bridge.py`, `run_panel.py` | Criam backend/runtime; o primeiro escreve boot log no import | Não importar pelo setup; integrar guarda antes dos efeitos operacionais |
| `panel/app.py` | Factory exige runtime e registra rotas operacionais | Não reutilizar factory; criar Flask independente |
| `panel/templates/index.html` | Tokens e grande bloco CSS inline, idioma fixo pt-BR | Extrair gradualmente componentes estáticos sem importar o painel |
| `panel/admin_api.py` | Sem token retorna 503; token menor que 16 caracteres nunca autentica | Adaptar na Etapa 8 para token livre e política local sem token |
| `infrastructure/env.py`, `paths.py` | `.env` da instalação, UTF-8, override=False, portas validadas | Reutilizar leitura e resolução; criar escrita transacional própria |

## Lacunas e riscos confirmados

1. **Serviço:** arquivos em `/etc/systemd/system/tesseract-bridge*` são escritos sem backup ou conferência de proprietário/origem. Reexecutar pode substituir o serviço antigo. `enable` ocorre antes de `systemd-analyze verify`; início é oferecido com padrão afirmativo. Não há rollback global. A presença de `systemctl` não comprova systemd ativo. Não há detecção específica de Raspberry Pi OS. O serviço depende de `graphical.target`, inadequado como requisito obrigatório para Pi sem desktop. Não declara `EnvironmentFile`; hoje depende do loader Python. A montagem de `ExecStart` com shell e aspas requer testes com espaços/apóstrofos. Deve usar executável absoluto da venv e argumentos adequadamente escapados. Diretivas StartLimit estão no bloco Service e precisam de validação semântica na plataforma alvo. Separar geração, instalação, habilitação e início; kiosk/watchdog opcionais; nunca substituir unidade anterior silenciosamente.
2. **Bootstrap vazio:** `make_engine()` exige arquivo existente. Alembic pode criar tabelas em arquivo vazio previamente criado, mas não fornece seeds operacionais. `NormalizedRepository` exige `BridgeSettings` e revisão 0003. `BridgeConfig.validate()` exige pelo menos um dispositivo. Separar configuração de instalação e elegibilidade operacional sem relaxar globalmente validação de hardware. Não há modelo de organização no ORM Bridge inspecionado; não importar conceitos do Tesseract principal sem necessidade.
3. **Legado sem SQLite:** já existe suporte real a YAML/JSON, mas `collect()` exige devices válido e reconhece uma lista fixa. `devices.yml` na raiz precisa de seleção explícita via `devices_file`; descoberta automática ainda não existe. Dados inválidos abortam o conjunto. Arquivos desconhecidos não aparecem em inventário. Upload múltiplo e importação parcial ainda não existem. Pode-se reaproveitar uma base SQLite legada intermediária exclusivamente no staging e então normalizá-la, sem criar escrita dupla no runtime.
4. **Caminhos e consistência:** confinamento é verificado para devices, mas os demais caminhos conhecidos podem ser symlinks externos. Backup de arquivos relê a origem após calcular hashes, sem reconferência nessa função. Validar todos os caminhos e importar uma cópia capturada e verificada. Abrir SQLite original com política somente leitura; a conexão atual de normalização não usa URI mode=ro. Tratar WAL/SHM, hot journals e base em uso explicitamente; não usar immutable indiscriminadamente nem copiar somente o arquivo principal. Se a captura exigir escrita/recuperação na origem, exigir snapshot externo consistente ou origem parada, sem executar a recuperação nela.
5. **Publicação:** o hard link existente evita sobrescrita, mas precisa de diagnóstico/fallback seguro em sistemas sem suporte. Banco e `.env` exigem manifesto persistente de publicação, recuperação por fases e barreira de boot; dois renames não equivalem a uma transação conjunta. Impedir dois setups concorrentes e distinguir resíduos próprios de arquivos do usuário.
6. **Rede:** implementar CSRF, sessão efêmera, validação de Host/Origin e cliente loopback desde a primeira mutação. Proxy e headers encaminhados não podem conceder acesso local. Testar IPv4/IPv6, DNS rebinding e cookies. Servir no Raspberry por loopback e orientar túnel SSH. Não expor tokens ou dados importados em logs/prévias.
7. **Dependências/CI:** requirements contém Flask/SQLAlchemy/Alembic, sem Flask-Babel. O workflow existente cobre Ubuntu/Python 3.9 e subconjunto de testes; não comprova Windows nem Pi físico. `.gitignore` ignora YAML/YML globalmente, relevante a fixtures/workflows futuros, e não cobre por extensão todo staging/manifests: guardar temporários em diretório privado ignorado.

## Integração proposta

`setup/__main__.py` inicia CLI/servidor local independente. `setup/app.py` fornece factory sem runtime. Serviços de estado, descoberta, inspeção, importação, bootstrap, publicação e systemd recebem caminhos explicitamente. Templates usam recursos estáticos compartilhados sem importar `panel.app`.

Estado durável antes do banco: manifesto privado com versão de formato, ID da tentativa, raiz/destino, fase, arquivos criados e conclusão. Escrita atômica e lock impedem concorrência. A localização definitiva e eventual espelhamento no ORM serão definidos na implementação. O runtime deve conferir conclusão e banco/configuração correspondente, em vez de confiar num booleano fornecido por formulário. Instalações legadas funcionais mantêm seu contrato anterior; a guarda nova deve distinguir instalação gerenciada pelo setup de legado já configurado.

Transições: `new → in_progress → needs_review | ready_simulated | ready_operational`. `ready_operational` pode resultar da conclusão válida do setup com escolha real; não exige etapa posterior adicional. Cancelamento/interrupção não produz ready. Reiniciar setup não revoga silenciosamente uma instalação publicada nem substitui seus arquivos.

## Etapa 2 detalhada

- Criar módulo executável, opções de host/porta local e encerramento previsível; sem importar run_bridge, painel operacional, DeviceRuntime ou backends GPIO.
- Manifesto/lock/staging exclusivos, retomada e limpeza somente dos temporários registrados; tratamento de permissões e porta ocupada.
- Factory Flask mínima e primeira tela de idioma pt_BR/en; catálogos e códigos de mensagem desde o início. Consolidação CSS fica na Etapa 5.
- Proteção de sessão, CSRF, Host/Origin e rede desde a primeira rota de escrita. Credencial operacional fica na Etapa 8.
- Diagnóstico de plataforma/Python/venv sem comandos privilegiados ou instalação de serviço.
- Documentação incremental e testes: subprocesso sem `.env`/DB; sentinelas que falham se GPIO/MQTT forem inicializados; concorrência; retomada; abortar; permissões; porta em uso; idioma e requisições inválidas.
- Não antecipar importação, publicação ou liberação física antes de suas implementações completas. A alteração final da guarda ORM requer testes com backend real substituído por fake, cobrindo ready real, simulado, revisão, falha de publicação e pendências.

## Verificação desta auditoria

- Branch/HEAD conferidos por Git; clone inicialmente limpo. Nenhuma instrução AGENTS.md versionada foi encontrada.
- Conteúdo de todos os seis itens de tools lido; scripts não executados contra systemd/GPIO.
- `bash -n tools/install_service.sh tools/uninstall_service.sh tools/logs.sh`: código 0. Isso verifica sintaxe, não instalação ou unidades geradas.
- Ambiente de testes separado em `/tmp/tesseract-audit-venv`, dependências instaladas por requirements. `/tmp/tesseract-audit-venv/bin/python -m pytest -q`: **604 passed in 18.68s**, código 0, em Linux/Python 3.12.
- Sem homologação Windows, Raspberry, hardware, serviço ou CI remoto nesta etapa. A integração GitHub retornou erro interno; Git clone funcionou.
- Não houve alteração de main, push, banco real, arquivo .env de usuário ou serviço instalado.
