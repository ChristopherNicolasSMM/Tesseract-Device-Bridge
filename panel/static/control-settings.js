/* Settings UI: values are assigned as text, never inserted as markup. */
(() => {
  const $ = id => document.getElementById(id);
  let saved, vessels = [];
  async function request(url, options) {
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Não foi possível salvar.');
    return result;
  }
  function render(settings) {
    saved = settings;
    $('controlCurve').replaceChildren();
    settings.mash_curve.forEach(([delta, power]) => {
      const row = document.createElement('label');
      row.style.display = 'block';
      row.textContent = 'Diferença °C: ';
      [delta, power].forEach((value, index) => {
        const input = document.createElement('input');
        input.type = 'number'; input.step = '0.1'; input.required = true;
        input.value = value;
        input.setAttribute('aria-label', index ? 'Potência máxima em porcentagem' : 'Diferença para o alvo em graus');
        if (index) { input.min = 0; input.max = 100; }
        row.appendChild(input);
        row.appendChild(document.createTextNode(index ? ' %' : ' → potência máxima: '));
      });
      $('controlCurve').appendChild(row);
    });
    $('controlAlert').value = settings.alert_above;
    $('controlClear').value = settings.alert_clear;
    $('controlFreeze').checked = settings.freeze_hold_on_alert;
    $('controlBoilTemp').value = settings.boil_temperature;
    $('controlBoilPower').value = settings.boil_power;
    $('controlProfiles').replaceChildren();
    const names = new Map(Object.keys(settings.vessel_profiles).map(id => [id, id]));
    vessels.forEach(v => names.set(v.id, v.name));
    names.forEach((name, id) => {
      const label = document.createElement('label'); label.style.display = 'block'; label.textContent = name + ': ';
      const select = document.createElement('select'); select.dataset.vessel = id;
      [['mash', 'Mosturação'], ['boil', 'Fervura']].forEach(([value, text]) => {
        const option = document.createElement('option'); option.value = value; option.textContent = text; select.appendChild(option);
      });
      select.value = settings.vessel_profiles[id] || 'mash'; label.appendChild(select); $('controlProfiles').appendChild(label);
    });
  }
  async function load() {
    try { const result = await request('/api/control-settings'); vessels = result.vessels; render(result.settings); }
    catch (error) { $('controlSettingsMessage').textContent = error.message; }
  }
  $('controlSettingsForm').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const value = {...saved, mash_curve: [...$('controlCurve').children].map(row => [...row.querySelectorAll('input')].map(input => Number(input.value))),
        alert_above: Number($('controlAlert').value), alert_clear: Number($('controlClear').value),
        freeze_hold_on_alert: $('controlFreeze').checked,
        boil_temperature: Number($('controlBoilTemp').value), boil_power: Number($('controlBoilPower').value), vessel_profiles: {}};
      $('controlProfiles').querySelectorAll('select').forEach(select => { value.vessel_profiles[select.dataset.vessel] = select.value; });
      const result = await request('/api/control-settings', {method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(value)});
      render(result.settings); $('controlSettingsMessage').textContent = result.note;
    } catch (error) { $('controlSettingsMessage').textContent = error.message; }
  });
  $('controlRestore').addEventListener('click', async () => {
    try { const result = await request('/api/control-settings/restore', {method:'POST'}); render(result.settings); $('controlSettingsMessage').textContent = result.note; }
    catch (error) { $('controlSettingsMessage').textContent = error.message; }
  });
  load();
})();
