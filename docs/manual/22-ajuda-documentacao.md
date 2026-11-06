# Ajuda e documentação no navegador

A nova aba **Ajuda e documentação** reúne a documentação distribuída com esta
instalação. Está disponível no painel operacional. No setup e na configuração
inicial sem dispositivos há um link para a mesma central, sem iniciar runtime.
A página também pode ser aberta diretamente em `/help/`, na porta do aplicativo
em uso; não há um servidor ou uma porta adicional.

## Navegação

- **Início e atalhos:** FAQ, instalação, operação, bombas/MQTT e arquitetura.
- **Categorias:** manuais, documentação técnica, módulos, homologação e auditorias.
- **Busca:** título e conteúdo; múltiplas palavras e termos sem acentos são aceitos.
  Há até 40 resultados por consulta. Categoria e consulta podem ser combinadas.
- **Leitor:** títulos, sumário, tabelas, listas, imagens locais e blocos de código.
  Links entre Markdown abrem no leitor; links externos abrem em outra aba.
- **Baixar .md:** salva o documento consultado como texto, sem alterar a origem.
- **Tema:** alternância claro/escuro; navegação e busca preservam o tema escolhido.

O conteúdo vem de `docs/` e do `README.md` da raiz; não há cópia no banco. Atualize
os arquivos pelo fluxo normal de versionamento para atualizar o conteúdo. O
catálogo é consultado novamente a cada acesso; não requer indexação em SQLite.

## Limites desta entrega

A central é somente leitura, sem edição, upload ou histórico pelo navegador.
Os documentos publicados são legíveis a quem já tem acesso ao painel; não há
exigência de token administrativo para esses arquivos distribuídos no repositório.
As regras de acesso local do setup continuam aplicadas à central do setup.

HTML ativo e scripts são removidos do documento. Somente imagens raster locais
nos formatos PNG, JPEG, GIF e WebP entram no leitor; imagens externas e SVG não
são servidas. Diagramas Mermaid permanecem em bloco de código nesta versão.
Links para arquivos fora do catálogo, código-fonte ou destinos locais ausentes
ficam sem navegação. Um erro da central não executa comandos nem aciona a rotina
de emergência do runtime.

Na instalação/atualização, inclua as dependências de `requirements.txt`:

```powershell
python -m pip install -r requirements.txt
```

Reinicie o aplicativo e recarregue a página. Validação visual e regressão da nova
aba permanecem pendentes de execução local; o aceite anterior da simulação é
anterior a esta entrega. O cenário real continua pendente do mantenedor.

## Largura do leitor

O botão **↔ Layout** fica ao lado do tema na central independente. Dentro da aba
de ajuda, o leitor herda a largura do painel. Veja [modos e persistência](23-layout-interface.md).
