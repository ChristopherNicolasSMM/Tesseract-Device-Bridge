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
    result['events'] = [dict(item, message=translate(language, item['code']))
                        for item in report.get('events', [])]
    return result
