"""Explicit partial import on private copies, never on the source installation."""
import json
import shutil
from pathlib import Path

from .reports import event


def collect_partial(source, devices_file, *, disable_invalid_remote_control=False):
    from storage.legacy_import import collect
    # The input is already a bounded private snapshot.
    working = Path(source).parent / 'validated'
    working.mkdir(mode=0o700)
    devices = working / devices_file
    devices.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(source) / devices_file, devices)
    options = dict(devices_file=devices_file,
                   disable_invalid_remote_control=disable_invalid_remote_control)
    events = []
    try:
        snapshot = collect(working, **options)
    except Exception as exc:
        return None, [event('blocking_error', devices_error_code(exc), file=devices_file)]
    # Keep reference dependencies before active recipe/session pointers.
    order = ['data/control_defaults.json', 'data/private/control_settings.json',
             'data/public/receita_base.yaml', 'recipe.yml',
             'data/public/receita.json', 'data/private/receita.json',
             'data/private/sensor_calibration.json', 'data/active_recipe.txt',
             'data/private/recipe_state.json']
    for relative in order:
        original = Path(source) / relative
        if not original.is_file():
            continue
        dest = working / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if relative.endswith('/receita.json'):
            try:
                entries = json.loads(original.read_text(encoding='utf-8'))
                if not isinstance(entries, list):
                    raise ValueError('not a list')
            except (ValueError, UnicodeError):
                events.append(event('warning', 'file_rejected', file=relative))
                continue
            accepted = []
            for index, entry in enumerate(entries):
                dest.write_text(json.dumps(accepted + [entry], ensure_ascii=False), encoding='utf-8')
                try:
                    current = collect(working, **options)
                except Exception:
                    events.append(event('warning', 'entity_rejected', file=relative, index=index))
                else:
                    accepted.append(entry)
                    snapshot = current
            dest.write_text(json.dumps(accepted, ensure_ascii=False), encoding='utf-8')
        else:
            # Two aliases of the base recipe must not silently mask each other.
            if relative == 'recipe.yml' and (working / 'data/public/receita_base.yaml').exists():
                events.append(event('ignored', 'alias_ignored', file=relative))
                continue
            shutil.copyfile(original, dest)
            try:
                current = collect(working, **options)
            except Exception:
                dest.unlink()
                events.append(event('warning', 'file_rejected', file=relative))
            else:
                snapshot = current
    events.append(event('imported', 'legacy_validated'))
    return snapshot, events


def devices_error_code(exc):
    """Map known validation failures to static messages; never expose source values."""
    text = str(exc)
    if 'ao menos um device' in text:
        return 'devices_empty'
    if 'sem state_topic' in text:
        return 'devices_remote_invalid'
    if 'campo(s) obrigatório(s)' in text:
        return 'devices_required'
    if 'objeto YAML' in text:
        return 'devices_object_required'
    import yaml
    if isinstance(exc, yaml.YAMLError):
        return 'devices_yaml_invalid'
    return 'devices_invalid'
