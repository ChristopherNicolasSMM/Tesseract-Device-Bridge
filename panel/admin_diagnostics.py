"""Authenticated maintenance endpoints, separated from recipe/GPIO control.

Routes are registered on the existing admin blueprint and inherit its
admin-token before_request interlock.
"""
from __future__ import annotations

from flask import current_app, jsonify, request, session
from storage.migrate import StorageError

from tesseract_bridge.diagnostics import service
from tesseract_bridge.infrastructure.env import flag


def register_diagnostics(blueprint, require_idle):
    def runtime_context():
        return (
            current_app.config["BRIDGE_CONFIG"],
            current_app.config["DEVICE_RUNTIME"],
        )

    @blueprint.get("/diagnostics/temperature")
    def diagnostic_temperature():
        config, _runtime = runtime_context()
        return jsonify(sensors=service.sensors(config))

    @blueprint.get("/diagnostics/gpio")
    def diagnostic_gpio():
        config, runtime = runtime_context()
        bank = current_app.config.setdefault("ADMIN_VIRTUAL_GPIO", {})
        result = service.gpio_inventory(config, runtime, bank)
        result["virtual_write_enabled"] = (
            flag("TESSERACT_BRIDGE_SIMULATION_ONLY", False)
            and config.backend == "simulated"
        )
        return jsonify(result)

    @blueprint.post("/diagnostics/gpio/virtual")
    def diagnostic_virtual_gpio():
        config, runtime = runtime_context()
        if not flag("TESSERACT_BRIDGE_SIMULATION_ONLY", False) or config.backend != "simulated":
            return jsonify(error="Acionamento de testes permitido apenas em SIMULATION_ONLY=1."), 403
        try:
            require_idle()
        except StorageError as exc:
            return jsonify(error=str(exc)), 409
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="JSON inválido."), 400
        try:
            result = service.virtual_gpio_write(
                config, current_app.config.setdefault("ADMIN_VIRTUAL_GPIO", {}),
                pin=payload.get("pin"), level=payload.get("level"),
            )
        except service.DiagnosticError as exc:
            return jsonify(error=str(exc), code=exc.code), 400
        return jsonify(result)

    @blueprint.get("/diagnostics/serial/ports")
    def diagnostic_serial_ports():
        return jsonify(service.serial_ports())

    @blueprint.post("/diagnostics/serial/read")
    def diagnostic_serial_read():
        # Opening a serial port may reset its attached microcontroller.
        # Never permit this operation while a brewing session is active.
        try:
            require_idle()
        except StorageError as exc:
            return jsonify(error=str(exc)), 409
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="JSON inválido."), 400
        try:
            return jsonify(service.serial_read(
                payload.get("port"), payload.get("baudrate")
            ))
        except service.DiagnosticError as exc:
            return jsonify(error=str(exc), code=exc.code), 400

    def serial_owner():
        import secrets
        return session.setdefault('serial_owner', secrets.token_urlsafe(24))

    @blueprint.post('/diagnostics/serial/<action>')
    def diagnostic_serial_session(action):
        if action not in ('open', 'poll', 'close', 'test'):
            return jsonify(error='Operação serial desconhecida.'), 404
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error='JSON inválido.'), 400
        monitor = service.serial_monitor()
        owner = serial_owner()
        try:
            # Closing remains permitted when the operational session becomes active.
            if action != 'close':
                try:
                    require_idle()
                except StorageError:
                    monitor.close_owner(owner)
                    raise
            if action in ('open', 'test'):
                settings = {key: payload.get(key, default) for key, default in
                    (('port', ''), ('baudrate', 9600), ('bytesize', 8), ('parity', 'N'), ('stopbits', 1))}
                result = getattr(monitor, action)(owner, **settings)
            elif action == 'poll':
                result = monitor.read(payload.get('session'), owner, payload.get('limit', 1024))
            else:
                monitor.close(payload.get('session'), owner)
                result = dict(status='closed')
            response = jsonify(result)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except StorageError as exc:
            return jsonify(error=str(exc)), 409
        except service.DiagnosticError as exc:
            return jsonify(error=str(exc), code=exc.code), 400
