"""Dark select dropdown: native Windows Chrome/Edge menu stays readable.

A source-level regression test documents the CSS rules, while visual
homologation of native <select> popups must still be done on Windows.
"""
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "panel" / "templates" / "index.html"
CSS = Path(__file__).resolve().parents[1] / "reusable" / "guided_setup" / "static" / "theme.css"


def test_native_select_popups_use_dark_color_scheme():
    html = HTML.read_text(encoding="utf-8") + CSS.read_text(encoding="utf-8")
    assert "color-scheme: dark;" in html
    assert "select option," in html
    assert "select optgroup {" in html
    assert "background-color: var(--bg-card);" in html
    assert "select option:disabled {" in html


def test_control_settings_select_has_explicit_dark_background():
    html = HTML.read_text(encoding="utf-8") + CSS.read_text(encoding="utf-8")
    rules = html.split('#control-settings input[type="number"], #control-settings select {', 1)[1].split("}", 1)[0]
    assert "color: var(--text-primary)" in rules
    assert "background: var(--bg-card)" in rules
    assert "background: transparent" not in rules


def test_dropdown_has_visible_keyboard_focus_state():
    html = HTML.read_text(encoding="utf-8") + CSS.read_text(encoding="utf-8")
    assert "#control-settings select:focus-visible {" in html
    assert "outline: 2px solid var(--accent-blue)" in html
