'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const busy = document.getElementById('busy');
  const message = document.getElementById('browser-message');
  const dialog = document.getElementById('preview-dialog');
  const text = document.getElementById('preview-content');
  const status = document.getElementById('preview-status');
  const messages = JSON.parse(document.getElementById('setup-messages')?.textContent || '{}');
  const showError = (value) => { message.textContent = value; message.hidden = false; message.className = 'setup-alert warning'; };
  document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => dialog.close()));
  document.querySelectorAll('[data-select-all]').forEach(button => button.addEventListener('change', () => {
    document.querySelectorAll('input[name="selected"]:not(:disabled)').forEach(input => { input.checked = button.checked; });
  }));
  document.querySelectorAll('[data-preview]').forEach(button => button.addEventListener('click', async () => {
    text.textContent = '';
    status.textContent = messages.processing || '';
    dialog.showModal();
    try {
      const response = await fetch('/import/preview/' + encodeURIComponent(button.dataset.preview), { credentials: 'same-origin' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || messages.request_error);
      status.textContent = messages[data.code] || data.code;
      text.textContent = data.text || '';
    } catch (error) { status.textContent = messages.request_error || 'Error'; }
  }));
  document.querySelectorAll('form').forEach(form => form.addEventListener('submit', async event => {
    if (!window.fetch) return;
    event.preventDefault();
    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;
    if (form.hasAttribute('data-run') && !form.querySelector('input[name="selected"]:checked')) {
      showError(messages.select_required); return;
    }
    const data = new FormData(form);
    busy.hidden = false;
    message.hidden = true;
    try {
      const response = await fetch(form.action, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'X-Setup-CSRF': data.get('csrf') || '' }, body: data
      });
      if (response.redirected && response.ok) {
        window.location.assign(response.url); return;
      }
      if (!response.ok) {
        const error = await response.json();
        showError(error.message || messages.request_error);
      } else {
        const result = await response.json();
        if (result.redirect && result.redirect.startsWith('/')) window.location.assign(result.redirect);
        else window.location.reload();
      }
    } catch (error) { showError(messages.request_error); }
    busy.hidden = true;
  }));
});
