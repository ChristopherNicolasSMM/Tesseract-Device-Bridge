"""Small explicit catalogs shared by Jinja, JSON messages and CLI reports."""
import json
from pathlib import Path

LANGUAGES = ('pt_BR', 'en')


def catalog(language):
    if language not in LANGUAGES:
        language = 'pt_BR'
    return json.loads((Path(__file__).parent / 'translations' / (language + '.json')).read_text(encoding='utf-8'))


def translate(language, code):
    return catalog(language).get(code, catalog('en').get(code, code))


def translate_report(report, language):
    # Keep stable identifiers and return a translated display copy.
    result = dict(report)
    events = report.get('events', [])
    if any(item.get('code') == 'file_ignored' for item in events):
        from storage.legacy_import import LEGACY_FILES
        known = set(LEGACY_FILES) | {'devices.yml'}
        # Also filter reports persisted by older builds, without rewriting them.
        events = [item for item in events if item.get('code') != 'file_ignored'
                  or item.get('file') in known]
    result['events'] = [dict(item, message=translate(language, item['code']))
                        for item in events]
    return result
