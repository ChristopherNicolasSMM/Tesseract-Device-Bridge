# Componentes reutilizáveis

O código fica em `reusable/`, separado do domínio de brassagem. Cada componente
possui seu próprio contrato e guia; não importa `config`, `storage`, `panel`,
`setup`, GPIO ou MQTT. Os adaptadores do Bridge dependem dos componentes.

| Componente | Código | Documentação |
|---|---|---|
| Monitor serial | `reusable/serial_monitor/` | [Uso, API e limites](serial-monitor/README.md) |
| Setup guiado/configurações | `reusable/guided_setup/` | [Integração e responsabilidades](guided-setup/README.md) |
| Integração entre camadas | Adaptadores do projeto | [Guia de arquitetura](arquitetura.md) |

Versão dos componentes: 0.1.1.

Instalação opcional em outro projeto, a partir deste checkout:

```bash
python -m pip install './reusable[serial,wizard]'
```

No Bridge, o pacote é importado diretamente do clone; `requirements.txt` mantém
as dependências já usadas. Não é necessário instalar o pacote separadamente.
A distribuição declara Python >=3.9 e inclui templates/CSS. Não há publicação
no PyPI nesta entrega. O empacotamento não transforma o Bridge inteiro em wheel.
Antes de distribuir externamente, confirme os termos de licença/autorização do
repositório; esta extração não cria uma licença nova.

Testes dos módulos: `tests/test_serial_monitor_module.py` e
`tests/test_guided_setup_module.py`. A integração preserva os testes de setup e
`tests/test_admin_diagnostics.py`. A execução local/CI deve validar a entrega;
nenhuma homologação física é inferida a partir de mocks.

## Central de documentação

[Visualizador Markdown reutilizável](documentation/README.md): catálogo, busca,
renderização sanitizada e integração Flask, sem dependência de hardware ou ORM.

## Preferências visuais

[Controle de largura reutilizável](ui-preferences/README.md): ativos, template,
persistência no navegador e herança de largura na documentação incorporada.
