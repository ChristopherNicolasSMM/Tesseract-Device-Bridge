"""Bridge-specific publication policy over the reusable read-only viewer."""
from pathlib import Path
from reusable.documentation import DocumentLibrary


def register_help(app):
    from reusable.documentation.web import register_documentation
    root = Path(__file__).resolve().parents[1]
    library = DocumentLibrary(root, folders=('docs',), files=('README.md',), categories=(
        ('docs/manual/04-', 'FAQ'), ('docs/manual/', 'Manuais'),
        ('docs/technical/', 'Documentação técnica'), ('docs/modules/', 'Módulos reutilizáveis'),
        ('docs/homologacao/', 'Homologação'), ('docs/audits/', 'Auditorias'),
        ('docs/', 'Índices'), ('README.md', 'Apresentação')))
    # These are published repository documents, readable wherever the host panel
    # is accessible. No administrative token, local data or environment is read.
    return register_documentation(app, library, home_links=(
        ('docs/manual/04-perguntas-frequentes.md', 'Perguntas frequentes', 'Respostas e caminhos para os guias completos.'),
        ('docs/manual/20-instalacao-migracao-2.0.0.md', 'Instalação e migração', 'Clone novo, importação, publicação e recuperação.'),
        ('docs/manual/03-funcionalidades.md', 'Operação do Bridge', 'Painel, receitas, sensores e atuadores.'),
        ('docs/manual/16-bombas-mqtt.md', 'Bombas e MQTT', 'Comandos, tópicos e confirmação automática.'),
        ('docs/technical/18-setup-arquitetura.md', 'Arquitetura técnica', 'Fronteiras e contratos do assistente.'),
        ('docs/modules/arquitetura.md', 'Módulos reutilizáveis', 'Integração dos componentes em outros projetos.'),
    ))
