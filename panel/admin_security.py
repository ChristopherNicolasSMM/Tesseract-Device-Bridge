"""Local-only unauthenticated administration with exact host and CSRF checks."""
import base64
import binascii
import ipaddress
import secrets
from urllib.parse import urlsplit

from flask import current_app, jsonify, request, session
from tesseract_bridge.infrastructure.admin_policy import admin_token, local_admin_enabled


def require_admin():
    try:
        expected = admin_token()
    except ValueError:
        return jsonify(error='Credencial administrativa inválida na configuração.'), 503
    if expected:
        received = request.headers.get('X-Bridge-Admin-Token', '')
        if request.headers.get('X-Bridge-Admin-Token-Encoding') == 'base64utf8':
            try:
                received = base64.b64decode(received, validate=True).decode('utf-8')
            except (ValueError, UnicodeError, binascii.Error):
                return jsonify(error='Token de administração inválido.'), 401
        if not received or not secrets.compare_digest(expected.encode('utf-8'), received.encode('utf-8')):
            return jsonify(error='Token de administração inválido.'), 401
        return None
    if not local_admin_enabled():
        # Preserve the legacy behavior unless the local policy is explicitly selected.
        return jsonify(error='Administração desativada: configure credencial ou política local explícita.'), 503
    if any(name in request.headers for name in ('Forwarded', 'X-Forwarded-For', 'X-Forwarded-Host')):
        return jsonify(error='Proxy não permitido na administração sem token.'), 403
    try:
        address = ipaddress.ip_address(request.remote_addr or '')
        address = getattr(address, 'ipv4_mapped', None) or address
        local = address.is_loopback
    except ValueError:
        local = False
    port = current_app.config['BRIDGE_CONFIG'].panel.port
    hosts = {'127.0.0.1:' + str(port), 'localhost:' + str(port), '[::1]:' + str(port)}
    if port == 80:
        hosts |= {'127.0.0.1', 'localhost', '[::1]'}
    if not local or request.host.lower() not in hosts:
        return jsonify(error='Administração sem token disponível somente em loopback local.'), 403
    expected_origin = request.scheme + '://' + request.host.lower()
    origin = request.headers.get('Origin')
    if request.headers.get('Sec-Fetch-Site') == 'cross-site':
        return jsonify(error='Origem administrativa recusada.'), 403
    if origin is not None and origin != expected_origin:
        return jsonify(error='Origem administrativa recusada.'), 403
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if origin is None:
            ref = urlsplit(request.headers.get('Referer', ''))
            origin = ref.scheme + '://' + ref.netloc.lower() if ref.netloc else None
        csrf = session.get('admin_csrf', '')
        received = request.headers.get('X-Bridge-Admin-CSRF', '')
        if origin != expected_origin or not csrf or not secrets.compare_digest(csrf, received):
            return jsonify(error='Sessão/CSRF inválido; reabra a administração local.'), 403
    return None


def session_info():
    if admin_token():
        return jsonify(mode='token')
    session.setdefault('admin_csrf', secrets.token_urlsafe(32))
    response = jsonify(mode='local', csrf=session['admin_csrf'])
    response.headers['Cache-Control'] = 'no-store'
    return response
