/* Canonical values only; no arbitrary CSS, requests or administrative settings. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (!root.document) return;
  const doc = root.document;
  const env = {
    getCookie: () => doc.cookie,
    setCookie: value => { doc.cookie = value; },
    getItem: key => root.localStorage.getItem(key),
    setItem: (key, value) => root.localStorage.setItem(key, value)
  };
  let preference = api.read(env);
  const applyRoot = (element, value) => {
    element.dataset.layoutMode = value.mode;
    const width = api.width(value);
    if (width) element.style.setProperty('--layout-max', width);
    else element.style.removeProperty('--layout-max');
  };
  applyRoot(doc.documentElement, preference);
  function inherit(frame) {
    try {
      const child = frame.contentDocument;
      if (child && child.documentElement) {
        applyRoot(child.documentElement, preference);
        child.documentElement.dataset.layoutEmbedded = 'true';
      }
    } catch (_) { /* Cross-origin frames are never modified. */ }
  }
  function sync() {
    applyRoot(doc.documentElement, preference);
    doc.querySelectorAll('[data-layout-control]').forEach(control => {
      control.querySelector('[data-layout-mode-input]').value = preference.mode;
      control.querySelector('[data-layout-range]').value = preference.width;
      control.querySelector('[data-layout-value]').textContent = preference.width + ' px';
      control.querySelector('[data-layout-custom]').hidden = preference.mode !== 'custom';
    });
    doc.querySelectorAll('iframe[data-layout-frame]').forEach(inherit);
  }
  function change(value, control) {
    preference = api.normalize(value) || api.defaults();
    const saved = api.save(env, preference, root.location.protocol === 'https:');
    sync();
    control.querySelector('[data-layout-status]').textContent = saved ? control.dataset.saved : control.dataset.unsaved;
  }
  function initialize() {
    doc.querySelectorAll('[data-layout-control]').forEach(control => {
      const mode = control.querySelector('[data-layout-mode-input]');
      const range = control.querySelector('[data-layout-range]');
      mode.addEventListener('change', () => change({version:1, mode:mode.value, width:Number(range.value)}, control));
      range.addEventListener('input', () => change({version:1, mode:'custom', width:Number(range.value)}, control));
      control.querySelector('[data-layout-reset]').addEventListener('click', () => change(api.defaults(), control));
      control.addEventListener('keydown', event => {
        if (event.key === 'Escape') { control.open = false; control.querySelector('summary').focus(); }
      });
    });
    doc.addEventListener('click', event => doc.querySelectorAll('[data-layout-control][open]').forEach(control => {
      if (!control.contains(event.target)) control.open = false;
    }));
    doc.querySelectorAll('iframe[data-layout-frame]').forEach(frame => frame.addEventListener('load', () => inherit(frame)));
    root.addEventListener('storage', event => { if (event.key === api.KEY) { preference = api.read(env); sync(); } });
    root.addEventListener('focus', () => { preference = api.read(env); sync(); });
    sync();
  }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', initialize, {once:true});
  else initialize();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const KEY = 'tesseract_layout_v1';
  const defaults = () => ({version:1, mode:'default', width:1400});
  function normalize(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value) || value.version !== 1 ||
        !['default','wide','full','custom'].includes(value.mode) || typeof value.width !== 'number' || !Number.isFinite(value.width)) return null;
    return {version:1, mode:value.mode, width:Math.max(960, Math.min(2560, Math.round((value.width - 960)/40)*40 + 960))};
  }
  function decode(text) { try { return normalize(JSON.parse(text)); } catch (_) { return null; } }
  function read(env) {
    try {
      const part = env.getCookie().split(';').map(s => s.trim()).find(s => s.startsWith(KEY + '='));
      if (part) { const value = decode(decodeURIComponent(part.slice(KEY.length + 1))); if (value) return value; }
    } catch (_) { /* Browser policy may deny cookies. */ }
    try { const value = decode(env.getItem(KEY)); if (value) return value; } catch (_) { /* Storage can be disabled. */ }
    return defaults();
  }
  function save(env, value, secure) {
    const normalized = normalize(value);
    if (!normalized) return false;
    const text = JSON.stringify(normalized);
    let saved = false;
    try { const pair = KEY + '=' + encodeURIComponent(text); env.setCookie(pair + '; Path=/; Max-Age=31536000; SameSite=Strict' + (secure ? '; Secure' : '')); saved = env.getCookie().split(';').some(part => part.trim() === pair); } catch (_) {}
    try { env.setItem(KEY, text); saved = env.getItem(KEY) === text || saved; } catch (_) {}
    return saved;
  }
  function width(value) {
    if (value.mode === 'wide') return '1800px';
    if (value.mode === 'full') return '100%';
    if (value.mode === 'custom') return value.width + 'px';
    return null;
  }
  return {KEY, defaults, normalize, read, save, width};
});
