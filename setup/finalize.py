"""Final review HTTP adapter. No runtime/hardware/service starts on publication."""
import json
import threading

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session

from .state import SetupError
from .i18n import catalog
from .publication import candidates, publish, recover, rollback, load_publication, revalidate

bp = Blueprint('setup_finish', __name__, url_prefix='/finish')


@bp.get('/')
def page():
    state = current_app.extensions['installation_state']
    session.setdefault('csrf', __import__('secrets').token_urlsafe(32))
    receipt = None
    if (state.root / 'data/private/installation.json').exists():
        receipt, _ = load_publication(state)
    language = state.value['language']
    return render_template('finish.html', t=catalog(language), language=language,
        theme=state.value.get('theme', 'light'), csrf=session['csrf'],
        choices=candidates(state), receipt=receipt, state=state.value,
        build=current_app.config['SETUP_BUILD'],
        service_available=__import__('setup.service', fromlist=['compatible']).compatible(),
        service_path=state.value.get('service_unit'))


@bp.post('/publish')
def publish_installation():
    state = current_app.extensions['installation_state']
    if request.form.get('confirm') != '1':
        raise SetupError('Explicit publication confirmation required.')
    # Preserve the actual selected setup port for effective-port revalidation.
    state.save(dict(state.value, setup_port=current_app.config['SETUP_PORT']))
    publish(state, request.form.get('candidate'), replace_env=request.form.get('replace_env') == '1',
            authorize_real=request.form.get('authorize_real') == '1')
    return redirect('/finish/', code=303)


@bp.post('/recover')
def recover_installation():
    if request.form.get('confirm') != '1':
        raise SetupError('Confirmation required.')
    recover(current_app.extensions['installation_state'])
    return redirect('/finish/', code=303)


@bp.post('/rollback')
def rollback_installation():
    if request.form.get('confirm') != '1':
        raise SetupError('Confirmation required.')
    rollback(current_app.extensions['installation_state'])
    return redirect('/finish/', code=303)


@bp.post('/service')
def generate_service():
    from .service import generate
    state = current_app.extensions['installation_state']
    path = generate(state, request.form.get('user') or None)
    state.save(dict(state.value, service_unit=str(path.relative_to(state.root))))
    return redirect('/finish/', code=303)


@bp.post('/close')
def close_setup():
    state = current_app.extensions['installation_state']
    if state.value['status'] not in ('ready_simulated', 'ready_operational', 'needs_review'):
        raise SetupError('Complete or recover publication first.')
    callback = current_app.extensions.get('setup_shutdown')
    if callback:
        threading.Timer(0.5, callback).start()
    return jsonify(message=catalog(state.value['language'])['finish_closed'])


@bp.post('/revalidate')
def revalidate_installation():
    if request.form.get('confirm') != '1':
        raise SetupError('Confirmation required.')
    revalidate(current_app.extensions['installation_state'],
               authorize_real=request.form.get('authorize_real') == '1')
    return redirect('/finish/', code=303)
