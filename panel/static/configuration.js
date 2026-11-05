'use strict';
let csrf = '', token = '';
const text = document.getElementById('document'), message = document.getElementById('message');
async function api(path, method='GET', body) {
  const response = await fetch('/api/admin/' + path, {method, credentials:'same-origin',
    headers: {'X-Bridge-Admin-Token':btoa(String.fromCharCode(...new TextEncoder().encode(token))),
      'X-Bridge-Admin-Token-Encoding':'base64utf8','X-Bridge-Admin-CSRF':csrf,'Content-Type':'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Falha administrativa');
  return data;
}
document.getElementById('load').addEventListener('click', async () => {
  try {
    token = document.getElementById('token').value;
    csrf = '';
    if (!token) csrf = (await api('security/session')).csrf || '';
    text.value = JSON.stringify((await api('config')).config, null, 2);
    document.getElementById('token').value = '';
    document.getElementById('save').disabled = false;
    message.textContent = 'Configuração carregada; revise antes de aprovar.';
  } catch (error) { message.textContent = error.message; }
});
document.getElementById('save').addEventListener('click', async () => {
  try {
    const draft = await api('drafts', 'POST', JSON.parse(text.value));
    await api('drafts/' + draft.id + '/activate', 'POST');
    message.textContent = 'Configuração aprovada. Reinicie o Bridge; nenhuma saída foi acionada.';
  } catch (error) { message.textContent = error.message; }
});

window.mountBridgeSerialMonitor(api);
