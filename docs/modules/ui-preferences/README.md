# Preferências visuais reutilizáveis

Código: `reusable/ui_preferences/`. O módulo só publica CSS, JavaScript e o template
`_layout_control.html`. Não carrega banco, GPIO, MQTT ou rotas de escrita.

## Integração

```python
from reusable.ui_preferences import register_layout
register_layout(app)
```

Inclua `layout_ui.static` para `layout.css` e `layout.js` no cabeçalho e o template
`_layout_control.html` no ponto desejado. Marque o contêiner com
`data-layout-surface="panel|wizard|configuration|help"`. Os adaptadores existentes
já fazem isso em cada aplicativo do Bridge. O registro é idempotente por app.
O pacote `reusable/` inclui templates, CSS e JavaScript, versão 0.2.1.

O modo padrão não sobrepõe os limites do host. Os demais modos aplicam
`--layout-max` sob `data-layout-mode`; o adapter wizard desconta os 260 px do menu
lateral e muda para largura responsiva abaixo de 1.100 px. Adapte esses seletores
se outro projeto tiver menus ou contêineres diferentes. A renderização do controle
reconhece `language='en'`, com português como padrão.

## Persistência e validação

A chave `tesseract_layout_v1` contém somente `version`, `mode` e `width`. O script
aceita modos enumerados e largura numérica finita, arredondada e limitada a
960–2.560 px. CSS livre ou valores de formulário sem validação não são aceitos.
Cookie por host, `Path=/`, `SameSite=Strict`, um ano de validade e `Secure` em
HTTPS, permite sincronizar portas do mesmo host. O fallback localStorage mantém
preferência por origem; eventos storage sincronizam abas da mesma origem e foco
reconsulta a preferência compartilhada. Reset grava explicitamente o modo padrão,
para evitar ressuscitar valores antigos de localStorage em outra porta.

`normalize`, `read`, `save`, `width` e `defaults` ficam disponíveis via CommonJS
para testes Node. Falhas de cookies/armazenamento são tratadas sem impedir o
controle atual. Nenhuma requisição administrativa é disparada pelo JavaScript.
A chave é do host Bridge; ao incorporar o módulo em outro produto, revise esse
namespace para não compartilhar preferências indevidamente.

## Documentação e segurança de scripts

O host habilita `layout_control=True` em `register_documentation` e registra os
assets do módulo. Na central independente, apenas o script de layout recebe nonce
aleatório por resposta; o CSP permite esse nonce, mantendo o Markdown sanitizado.
No iframe `embedded=1`, não há script nem controle de layout. O pai aplica apenas
os atributos e variáveis de largura ao documento de mesma origem, inclusive após
cada navegação. Não usa postMessage, eval ou scripts inseridos pelo conteúdo.

Marque o iframe com `data-layout-frame` e mantenha `embedded=1` nas URLs/formulários
internos. Quadros externos são ignorados. O sandbox continua sem `allow-scripts`.
Esse mecanismo não modifica a sanitização, nem autoriza execução de HTML dos
manuais. Falhas do módulo não alteram autorizações de hardware.

## Validação local

```powershell
node tests/js/test_layout_preferences.cjs
python -m pytest tests/test_layout_preferences.py tests/test_documentation.py tests/test_guided_setup_module.py tests/test_setup.py -q
```

Cobrir visualmente os cinco modos/ações (incluindo restaurar), viewport pequeno,
menu lateral, documentação dentro/fora da aba, recarga, troca de porta e navegador
com armazenamento bloqueado. Os testes não foram executados nesta entrega.
