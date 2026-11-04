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

  // Calibração em armazenamento privado; alterações nunca atuam no GPIO em tempo real.
  let calibrationSensors = [];
  const calibrationPane = $('sensorCalibrationSection');
  const thermalPane = $('thermalSettingsSection');
  function showSettingsPane(which) {
    const calibration = which === 'calibration';
    calibrationPane.style.display = calibration ? '' : 'none';
    thermalPane.style.display = calibration ? 'none' : '';
    $('settingsThermalTab').setAttribute('aria-pressed', String(!calibration));
    $('settingsCalibrationTab').setAttribute('aria-pressed', String(calibration));
    if (calibration) loadCalibrations();
  }
  $('settingsThermalTab').addEventListener('click', () => showSettingsPane('thermal'));
  $('settingsCalibrationTab').addEventListener('click', () => showSettingsPane('calibration'));
  function formatC(value) {
    return Number.isFinite(value) ? value.toFixed(2) + ' °C' : 'indisponível';
  }
  function renderCalibrations(sensors, maxOffset) {
    calibrationSensors = sensors;
    const list = $('sensorCalibrationList');
    list.replaceChildren();
    sensors.forEach(sensor => {
      const row = document.createElement('div');
      row.className = 'calibration-card';
      const details = document.createElement('div');
      const title = document.createElement('strong');
      title.textContent = sensor.name + ' (' + sensor.id + ')';
      const address = document.createElement('small');
      address.textContent = 'Sensor físico: ' + (sensor.address || 'não informado');
      const readings = document.createElement('small');
      readings.textContent = 'Bruta: ' + formatC(sensor.raw_value) +
        ' | Corrigida em uso: ' + formatC(sensor.value) +
        ' | Offset ativo: ' + Number(sensor.active_offset_c).toFixed(2) + ' °C';
      details.append(title, address, readings);
      if (sensor.pending_restart) {
        const pending = document.createElement('small');
        pending.textContent = '⚠ Alteração pendente: reinicie o Bridge para aplicar.';
        details.appendChild(pending);
      }
      const label = document.createElement('label');
      label.textContent = 'Offset (°C): ';
      const input = document.createElement('input');
      input.type = 'number';
      input.step = '0.1';
      input.min = -maxOffset;
      input.max = maxOffset;
      input.required = true;
      input.value = sensor.configured_offset_c;
      input.dataset.sensorId = sensor.id;
      input.setAttribute('aria-label', 'Offset do sensor ' + sensor.name);
      label.appendChild(input);
      row.append(details, label);
      list.appendChild(row);
    });
    if (!sensors.length) {
      list.textContent = 'Nenhum sensor de temperatura foi configurado.';
    }
    $('saveSensorCalibration').disabled = sensors.length === 0;
    $('zeroSensorCalibration').disabled = sensors.length === 0;
  }
  async function loadCalibrations() {
    try {
      const result = await request('/api/sensor-calibration');
      renderCalibrations(result.sensors, result.max_absolute_offset_c);
      $('sensorCalibrationMessage').textContent = '';
    } catch (error) {
      $('sensorCalibrationMessage').textContent = error.message;
    }
  }
  $('saveSensorCalibration').addEventListener('click', async () => {
    try {
      const sensors = {};
      $('sensorCalibrationList').querySelectorAll('input[data-sensor-id]').forEach(input => {
        if (!input.value.trim() || !input.checkValidity()) throw new Error('Informe um offset válido para cada sensor.');
        const sensor = calibrationSensors.find(s => s.id === input.dataset.sensorId);
        sensors[sensor.id] = {address: sensor.address, offset_c: Number(input.value)};
      });
      const result = await request('/api/sensor-calibration', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({schema: 1, sensors})
      });
      $('sensorCalibrationMessage').textContent = result.note;
      await loadCalibrations();
      $('sensorCalibrationMessage').textContent = result.note;
    } catch (error) {
      $('sensorCalibrationMessage').textContent = error.message;
    }
  });
  $('zeroSensorCalibration').addEventListener('click', () => {
    $('sensorCalibrationList').querySelectorAll('input[data-sensor-id]').forEach(input => { input.value = '0'; });
    $('sensorCalibrationMessage').textContent = 'Campos zerados. Clique Salvar offsets para confirmar; reinicie para aplicar.';
  });

  load();
})();
