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
  const folderDialog = document.getElementById('folder-dialog');
  if (folderDialog) {
    const byId = id => document.getElementById(id);
    let currentFolder = '', parentFolder = null, navigation = 0;
    const cleanPath = value => value.trim().replace(/^"(.*)"$/, '$1');
    const csrf = document.querySelector('form[action="/import/discover"] input[name="csrf"]').value;
    async function navigateFolder(path) {
      const sequence = ++navigation;
      currentFolder = ''; parentFolder = null;
      byId('folder-select').disabled = true;
      byId('folder-parent').disabled = true;
      byId('folder-list').replaceChildren();
      byId('folder-status').textContent = messages.processing;
      try {
        const response = await fetch('/import/folders', {
          method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json', 'X-Setup-CSRF': csrf},
          body: JSON.stringify({path: cleanPath(path)})
        });
        const data = await response.json();
        if (sequence !== navigation) return;
        if (!response.ok) throw new Error(data.message || messages.folder_unavailable);
        currentFolder = data.path; parentFolder = data.parent;
        byId('folder-path').value = data.path;
        byId('folder-select').disabled = false;
        byId('folder-parent').disabled = !data.parent;
        const roots = byId('folder-root'); roots.replaceChildren();
        data.roots.forEach(root => {
          const option = document.createElement('option');
          option.value = root; option.textContent = root; roots.appendChild(option);
          if (data.path.toLowerCase().startsWith(root.toLowerCase())) roots.value = root;
        });
        data.folders.forEach(folder => {
          const li = document.createElement('li');
          const button = document.createElement('button');
          button.type = 'button'; button.className = 'bridge-button secondary';
          button.textContent = folder.name;
          button.addEventListener('click', () => navigateFolder(folder.path));
          li.appendChild(button); byId('folder-list').appendChild(li);
        });
        byId('folder-status').textContent = data.truncated ? messages.folder_truncated :
          data.folders.length ? messages.folder_navigation : messages.folder_no_children;
      } catch (error) {
        if (sequence === navigation) byId('folder-status').textContent = error.message || messages.folder_unavailable;
      }
    }
    const kind = byId('source-kind');
    const syncFolderKind = () => { byId('browse-source').disabled = false; };
    kind.addEventListener('change', syncFolderKind); syncFolderKind();
    byId('browse-source').addEventListener('click', () => {
      if (!folderDialog.open) folderDialog.showModal();
      const input = cleanPath(byId('source-path').value);
      navigateFolder(kind.value === 'sqlite' && /\.(sqlite3?|db)$/i.test(input) ? '' : input);
    });
    byId('folder-path').addEventListener('input', () => {
      currentFolder = ''; byId('folder-select').disabled = true;
    });
    byId('folder-open').addEventListener('click', () => navigateFolder(byId('folder-path').value));
    byId('folder-path').addEventListener('keydown', event => {
      if (event.key === 'Enter') { event.preventDefault(); navigateFolder(event.target.value); }
    });
    byId('folder-parent').addEventListener('click', () => { if (parentFolder) navigateFolder(parentFolder); });
    byId('folder-root').addEventListener('change', event => navigateFolder(event.target.value));
    byId('folder-select').addEventListener('click', () => {
      if (currentFolder) { byId('source-path').value = currentFolder; folderDialog.close(); }
    });
    document.querySelectorAll('[data-folder-close]').forEach(button => button.addEventListener('click', () => folderDialog.close()));
    folderDialog.addEventListener('close', () => { if (!folderDialog.open) navigation++; });
  }
  const remoteDialog = document.getElementById('remote-dialog');
  if (remoteDialog) {
    const radios = document.querySelectorAll('input[name="remote_policy"]');
    const topics = remoteDialog.querySelectorAll('input[name^="state_topic:"]');
    radios.forEach(radio => radio.addEventListener('change', () => {
      const keep = document.querySelector('input[name="remote_policy"]:checked')?.value === 'keep';
      topics.forEach(input => { input.disabled = !keep; input.required = keep; });
    }));
    document.getElementById('remote-open').addEventListener('click', () => remoteDialog.showModal());
    const resetRemoteChoice = () => {
      radios.forEach(radio => { radio.checked = false; });
      topics.forEach(input => { input.disabled = true; input.required = false; });
    };
    document.getElementById('remote-close').addEventListener('click', () => {
      resetRemoteChoice(); remoteDialog.close();
    });
    remoteDialog.addEventListener('cancel', resetRemoteChoice);
    document.getElementById('remote-apply').addEventListener('click', () => {
      if (!document.querySelector('input[name="remote_policy"]:checked')) {
        document.getElementById('remote-error').hidden = false; return;
      }
      if ([...topics].some(input => !input.disabled && !input.reportValidity())) return;
      remoteDialog.close(); document.getElementById('import-run').requestSubmit();
    });
    remoteDialog.showModal();
  }
  document.querySelectorAll('form').forEach(form => form.addEventListener('submit', async event => {
    if (!window.fetch) return;
    event.preventDefault();
    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;
    if (form.hasAttribute('data-run') && !form.querySelector('input[name="selected"]:checked')) {
      showError(messages.select_required); return;
    }
    if (form.hasAttribute('data-run') && remoteDialog &&
        !document.querySelector('input[name="remote_policy"]:checked')) {
      if (!remoteDialog.open) remoteDialog.showModal(); return;
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
        else if (result.message) {
          message.textContent = result.message; message.hidden = false;
          message.className = 'setup-alert success';
        } else window.location.reload();
      }
    } catch (error) { showError(messages.request_error); }
    busy.hidden = true;
  }));
});
