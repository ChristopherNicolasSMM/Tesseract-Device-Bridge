"""Opt-in remote controls using the same arbitration as the local panel."""
from collections import deque
from datetime import datetime, timezone
import math
from device_runtime import DeviceRuntimeError


def enabled(device):
    return (device.hardware.get('remote_control') is True and device.role == 'actuator'
            and 'heating_source' not in device.hardware)


class RemoteDeviceControl:
    def __init__(self, runtime, engine, boot_id, backend):
        self.runtime, self.engine, self.boot_id = runtime, engine, boot_id
        self.backend = backend
        self.seen = deque(maxlen=512)
        self.results = {}
        self.sequence = 0

    def command(self, device, data):
        request_id = data.get('request_id') if isinstance(data, dict) else None
        action = data.get('action') if isinstance(data, dict) else None
        try:
            if not enabled(device) or not isinstance(data, dict):
                raise ValueError('Controle remoto não habilitado para este dispositivo.')
            if type(data.get('version')) is not int or data['version'] != 1:
                raise ValueError('Versão não suportada.')
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 64:
                raise ValueError('Identificador inválido.')
            if request_id in self.seen:
                return  # MQTT QoS1 redelivery must never repeat an operation.
            self.seen.append(request_id)
            if data.get('boot_id') != self.boot_id:
                raise ValueError('Bridge reiniciado; aguarde nova telemetria.')
            issued = datetime.fromisoformat(data.get('issued_at', ''))
            if issued.tzinfo is None or not -2 <= (datetime.now(timezone.utc)-issued).total_seconds() <= 5:
                raise ValueError('Comando expirado ou horário inválido.')
            if device.has_duty_control:
                if action not in ('power_prepare', 'power_enable', 'power_release', 'power_off'):
                    raise ValueError('Operação de potência inválida.')
                if device.hardware.get('external_control_policy', 'manual_override') == 'local_only' and action != 'power_off':
                    raise ValueError('Política local_only: apenas desligamento remoto permitido.')
                if action == 'power_prepare':
                    value = data.get('value')
                    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
                        raise ValueError('Potência deve estar entre 0 e 100%.')
                    self.runtime.set_manual_duty_percent(device.id, value)
                    # Preparing while armed retains manual ownership, like the local slider.
                    if self.runtime.get_state(device.id).duty_enabled:
                        self.runtime.set_manual_enabled(device.id, True, origin='remote_manual')
                elif action == 'power_enable':
                    self.runtime.set_manual_enabled(device.id, True, origin='remote_manual')
                elif action == 'power_release':
                    self.runtime.set_manual_enabled(device.id, False, origin='remote_manual')
                else:
                    self.runtime.set_manual_duty(device.id, 0, origin='remote_manual')
            elif device.subtype == 'digital':
                if action == 'pump_set' and type(data.get('value')) is bool:
                    self.runtime.set_manual_override(device.id, data['value'])
                elif action == 'pump_release':
                    self.runtime.set_manual_override(device.id, None)
                elif action in ('pump_confirm', 'pump_decline') and self.engine and device.id in self.engine.pending_pump_confirmations:
                    method = self.engine.confirm_pump_auto if action == 'pump_confirm' else self.engine.decline_pump_auto
                    method(device.id)
                else:
                    raise ValueError('Operação de bomba inválida ou sem confirmação pendente.')
            else:
                raise ValueError('Tipo de dispositivo não suportado.')
            result = {'request_id': request_id, 'action': action, 'status': 'applied', 'message': 'Aceito pelo Bridge; consulte a saída lógica.'}
        except (ValueError, TypeError, DeviceRuntimeError) as exc:
            result = {'request_id': str(request_id or '')[:64], 'action': str(action or '')[:40], 'status': 'rejected', 'message': str(exc)[:250]}
        self.results[device.id] = result

    def telemetry(self, device):
        state = self.runtime.get_state(device.id)
        self.sequence += 1
        power = device.has_duty_control
        heating = self.runtime.get_heating_telemetry(device.id) if power else {}
        return {'version': 1, 'device_id': device.id, 'boot_id': self.boot_id,
                'sequence': self.sequence, 'observed_at': datetime.now(timezone.utc).isoformat(),
                'backend': self.backend, 'kind': 'power' if power else 'pump',
                'external_policy': device.hardware.get('external_control_policy', 'manual_override'),
                'output_on': bool(state.value), 'manual_enabled': bool(state.duty_enabled) if power else state.manual_override is not None,
                'manual_percent': state.manual_duty_percent if power else None,
                'owner': heating.get('owner', 'failsafe' if self.runtime.is_failsafe_suspended(device.id) else 'manual' if state.manual_override is not None else 'automatic'),
                'fault': heating.get('fault') or (str(self.runtime.emergency_reason)[:1000] if self.runtime.emergency_reason else None),
                'pending_confirmation': bool(self.engine and device.id in self.engine.pending_pump_confirmations),
                'last_command': self.results.get(device.id)}
