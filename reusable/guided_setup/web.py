"""Optional Flask presentation adapter; importing the core needs no Flask."""
from dataclasses import dataclass


@dataclass(frozen=True)
class WizardStep:
    key: str
    path: str
    label_key: str


def register_wizard_ui(app, steps):
    """Install the reusable layout/assets; routes, labels and branding come from host.

    Steps are navigation only, never authorization. Host enforces dependencies
    and validates actions server-side. Supply a trusted catalog `t`, language,
    theme, build and csrf through your views, as shown in the integration guide.
    """
    from reusable.ui_preferences import register_layout
    register_layout(app)
    from flask import Blueprint, request
    steps = tuple(steps)
    blueprint = Blueprint('guided_setup_ui', __name__, template_folder='templates',
                          static_folder='static', static_url_path='/wizard-assets')
    app.register_blueprint(blueprint)

    @app.context_processor
    def wizard_navigation():
        return dict(wizard_steps=[dict(number=f'{index:02d}', path=step.path,
                    label_key=step.label_key,
                    active=request.path == '/' if step.path == '/' else request.path.startswith(step.path))
                    for index, step in enumerate(steps, 1)])
