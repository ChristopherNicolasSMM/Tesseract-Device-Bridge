# Largura do conteúdo — controle Layout

Use **↔ Layout** no cabeçalho. No painel, fica entre o indicador MQTT e o relógio;
no setup, junto da versão; na configuração inicial, no cabeçalho; na documentação
aberta separadamente, ao lado do tema.

| Modo | Resultado |
| --- | --- |
| Padrão | Preserva os limites originais de cada tela |
| Ampla | Conteúdo com máximo de 1.800 px |
| Total | Usa a largura disponível, mantendo o espaçamento da tela |
| Personalizada | Ajuste de 960 a 2.560 px, em passos de 40 px |

A alteração é imediata, sem salvar configurações administrativas. **Restaurar
padrão** retorna aos limites originais, inclusive os limites internos da tela de
configurações e do leitor. O ajuste personalizado é uma largura máxima, não um
mínimo: janelas menores continuam responsivas e o setup respeita o menu lateral.
Não muda o zoom, tamanho da fonte, altura dos painéis ou largura dos diálogos.

Na aba de ajuda, o iframe herda a largura do painel; não mostra outro controle
Layout. Navegar entre documentos, pesquisar ou trocar o tema mantém a herança.
Ao abrir a central em outra aba, o controle volta a aparecer.

## Preferência no navegador

A preferência usa um cookie de layout por host, com validade de um ano, e
`localStorage` como alternativa. Assim, `127.0.0.1:8090` e `127.0.0.1:8088`
compartilham a preferência ao abrir/recarregar ou recuperar foco. `localhost` e
`127.0.0.1` são hosts diferentes; outros navegadores/dispositivos também mantêm
preferências próprias. Abas na mesma origem recebem atualizações via evento de
armazenamento. Se cookies forem bloqueados, o fallback é limitado à mesma origem
(host, protocolo e porta). Se ambos forem bloqueados, o ajuste funciona na página
atual e o controle informa que não conseguiu salvar.

Não há gravação no SQLite, `.env`, perfil de dispositivo, PID ou credencial. O
cookie não contém segredo e não é usado para autenticação. Reiniciar o Bridge não
apaga a preferência; limpar os dados do navegador pode apagá-la.

A entrega corresponde a setup.22 e pacote reutilizável 0.2.1. Testes e conferência
visual desta interface permanecem pendentes de execução pelo mantenedor; o aceite
anterior de simulação não equivale à validação desta nova alteração.
