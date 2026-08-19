    // ===== HELPERS =====
    const $ = id => document.getElementById(id);
    const toast = (msg, type = 'info') => {
      const container = $('toast-container');
      const el = document.createElement('div');
      el.className = `toast ${type}`;
      el.textContent = msg;
      container.appendChild(el);
      setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(40px)'; setTimeout(() => el.remove(), 300); }, 3500);
    };

    // ===== RELÓGIO =====
    function updateClock() {
      const now = new Date();
      $('clockDisplay').textContent = now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
    setInterval(updateClock, 1000);
    updateClock();

    // ===== TABS =====
    document.querySelectorAll('.nav-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        $(tab.dataset.tab).classList.add('active');
        if (tab.dataset.tab === 'cadastro') loadCadastroTab();
      });
    });

    // ===== ABA CADASTRO DE RECEITAS =====
    let cadastroRecipes = [];
    let cadastroActiveId = null;
    let cadastroRunningName = null;
    let cadastroEditingId = null;   // null = criando nova (via duplicar); string = editando existente
    let cadastroDraft = null;       // { name, vessels: [...], steps: [...] }

    async function loadCadastroTab() {
      try {
        const res = await fetch('/api/recipes');
        if (!res.ok) throw new Error('Falha ao carregar receitas');
        const payload = await res.json();
        cadastroRecipes = payload.recipes || [];
        cadastroActiveId = payload.active_recipe_id;
        cadastroRunningName = payload.running_recipe_name;
        renderRecipeCatalog();
      } catch (e) {
        toast(`❌ Erro ao carregar receitas: ${e.message}`, 'error');
      }
    }

    function renderRecipeCatalog() {
      $('recipeCatalogCount').textContent = cadastroRecipes.length;
      const grid = $('recipeCatalogGrid');
      if (cadastroRecipes.length === 0) {
        grid.innerHTML = `<p class="cadastro-hint">Nenhuma receita disponível ainda.</p>`;
        return;
      }
      grid.innerHTML = cadastroRecipes.map(r => {
        const isRunning = cadastroRunningName !== null && r.name === cadastroRunningName;
        const isPendingActive = r.id === cadastroActiveId && !isRunning;
        const cardClass = !r.valid ? 'invalid' : (isRunning ? 'running' : (isPendingActive ? 'pending-restart' : ''));

        const badges = [];
        badges.push(`<span class="recipe-badge source-${r.source}">${r.source === 'public' ? '🌐 Pública' : '🔒 Privada'}</span>`);
        if (!r.editable) badges.push(`<span class="recipe-badge locked">🔐 Base (não editável)</span>`);
        if (isRunning) badges.push(`<span class="recipe-badge running">🟢 Rodando agora</span>`);
        else if (isPendingActive) badges.push(`<span class="recipe-badge pending">⏳ Vai rodar no próximo restart</span>`);
        if (!r.valid) badges.push(`<span class="recipe-badge invalid">⚠️ Inválida</span>`);

        const actions = [];
        if (r.valid && r.id !== cadastroActiveId) {
          actions.push(`<button type="button" class="btn-recipe ghost" onclick="useRecipeAsActive('${r.id}')">▶ Usar esta</button>`);
        }
        actions.push(`<button type="button" class="btn-recipe ghost" onclick="duplicateRecipe('${r.id}')">🧬 Duplicar</button>`);
        if (r.editable) {
          actions.push(`<button type="button" class="btn-recipe ghost" onclick="editRecipe('${r.id}')">✏️ Editar</button>`);
          actions.push(`<button type="button" class="btn-recipe ghost" onclick="deleteRecipeConfirm('${r.id}')">🗑 Excluir</button>`);
        }

        const errorHtml = (!r.valid && r.error) ? `<div class="recipe-catalog-error">${r.error}</div>` : '';

        return `
          <div class="recipe-catalog-card ${cardClass}">
            <div class="recipe-catalog-name">${r.name || '(sem nome)'}</div>
            <div class="recipe-catalog-badges">${badges.join('')}</div>
            ${errorHtml}
            <div class="recipe-catalog-actions">${actions.join('')}</div>
          </div>
        `;
      }).join('');
    }

    async function useRecipeAsActive(id) {
      try {
        const res = await fetch('/api/recipes/active', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id })
        });
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || 'Falha ao marcar receita ativa');
        toast(`✅ Marcada como ativa — ${payload.note}`, 'success');
        loadCadastroTab();
      } catch (e) {
        toast(`❌ Erro: ${e.message}`, 'error');
      }
    }

    async function deleteRecipeConfirm(id) {
      const recipe = cadastroRecipes.find(r => r.id === id);
      if (!confirm(`Excluir a receita "${recipe ? recipe.name : id}"? Essa ação não pode ser desfeita.`)) return;
      try {
        const res = await fetch(`/api/recipes/${id}`, { method: 'DELETE' });
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || 'Falha ao excluir');
        toast(`✅ Receita excluída`, 'success');
        loadCadastroTab();
      } catch (e) {
        toast(`❌ Erro: ${e.message}`, 'error');
      }
    }

    async function duplicateRecipe(id) {
      try {
        const res = await fetch(`/api/recipes/${id}`);
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || 'Falha ao carregar receita');
        const draft = JSON.parse(JSON.stringify(payload.recipe));
        draft.name = `${draft.name || 'Receita'} (cópia)`;
        openCadastroForm(draft, null, id);
      } catch (e) {
        toast(`❌ Erro: ${e.message}`, 'error');
      }
    }

    async function editRecipe(id) {
      try {
        const res = await fetch(`/api/recipes/${id}`);
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || 'Falha ao carregar receita');
        openCadastroForm(JSON.parse(JSON.stringify(payload.recipe)), id, null);
      } catch (e) {
        toast(`❌ Erro: ${e.message}`, 'error');
      }
    }

    function openCadastroForm(draft, editingId, basedOnId) {
      cadastroDraft = draft;
      cadastroEditingId = editingId;
      if (!cadastroDraft.steps) cadastroDraft.steps = [];
      if (!cadastroDraft.vessels) cadastroDraft.vessels = [];

      $('cadastroFormTitle').textContent = editingId ? 'Editar receita' : 'Nova receita';
      $('cadastroBasedOnHint').textContent = editingId
        ? 'Editando uma receita já cadastrada.'
        : (basedOnId ? `Baseada em: ${basedOnId} — ajuste o nome e as etapas abaixo.` : '');
      $('cadastroName').value = draft.name || '';

      document.querySelectorAll('input[name="cadastroSource"]').forEach(r => { r.checked = (r.value === 'private'); });

      renderCadastroVessels();
      renderCadastroSteps();
      $('cadastroError').style.display = 'none';

      $('cadastroListView').style.display = 'none';
      $('cadastroFormView').style.display = 'block';
    }

    function closeCadastroForm() {
      $('cadastroFormView').style.display = 'none';
      $('cadastroListView').style.display = 'block';
      cadastroDraft = null;
      cadastroEditingId = null;
    }

    function onCadastroFieldChange() {
      if (!cadastroDraft) return;
      cadastroDraft.name = $('cadastroName').value;
    }

    function renderCadastroVessels() {
      const vessels = cadastroDraft.vessels || [];
      $('cadastroVesselsSummary').textContent = vessels.map(v => v.name || v.id).join(', ') || 'nenhuma';
      $('cadastroVesselsEditor').innerHTML = vessels.map((v, i) => `
        <div class="cadastro-vessel-row">
          <span class="cadastro-vessel-name">${v.name || v.id}</span>
          <span class="cadastro-vessel-devices">${v.heater_device_id} + ${v.sensor_device_id}</span>
          <label style="font-size:11px; color:var(--text-secondary);">Kp <input type="number" step="0.1" class="cadastro-pid-input" value="${(v.pid && v.pid.kp) || 0}" onchange="updateVesselPid(${i}, 'kp', this.value)"></label>
          <label style="font-size:11px; color:var(--text-secondary);">Ki <input type="number" step="0.01" class="cadastro-pid-input" value="${(v.pid && v.pid.ki) || 0}" onchange="updateVesselPid(${i}, 'ki', this.value)"></label>
          <label style="font-size:11px; color:var(--text-secondary);">Kd <input type="number" step="0.01" class="cadastro-pid-input" value="${(v.pid && v.pid.kd) || 0}" onchange="updateVesselPid(${i}, 'kd', this.value)"></label>
        </div>
      `).join('');
    }

    function updateVesselPid(index, field, value) {
      cadastroDraft.vessels[index].pid[field] = parseFloat(value) || 0;
    }

    function availablePumpDevices() {
      const heaterIds = new Set((cadastroDraft.vessels || []).map(v => v.heater_device_id));
      return (window.lastDevices || []).filter(d => d.role === 'actuator' && !heaterIds.has(d.id));
    }

    function renderCadastroSteps() {
      const steps = cadastroDraft.steps || [];
      const vessels = cadastroDraft.vessels || [];
      const pumps = availablePumpDevices();

      $('cadastroStepsList').innerHTML = steps.map((step, i) => {
        const vesselOptions = vessels.map(v =>
          `<option value="${v.id}" ${step.vessel === v.id ? 'selected' : ''}>${v.name || v.id}</option>`
        ).join('');

        const selectedPumps = new Set(step.pumps || []);
        const pumpChecks = pumps.map(p => `
          <label class="cadastro-pump-check">
            <input type="checkbox" ${selectedPumps.has(p.id) ? 'checked' : ''} onchange="toggleStepPump(${i}, '${p.id}', this.checked)">
            ${p.name || p.id}
          </label>
        `).join('') || '<span style="font-size:11px; color:var(--text-secondary);">Nenhuma bomba disponível no devices.yml</span>';

        const hopAlarms = step.hop_alarms || [];
        const hopAlarmRows = hopAlarms.map((h, j) => `
          <div class="cadastro-hop-alarm-row">
            <input type="number" class="alarm-settings-input" value="${h.minutes_remaining}" placeholder="min restantes" onchange="updateHopAlarm(${i}, ${j}, 'minutes_remaining', this.value)">
            <input type="text" class="alarm-settings-input" value="${h.label || ''}" placeholder="Ex.: Lúpulo Amargor - 30g" onchange="updateHopAlarm(${i}, ${j}, 'label', this.value)">
            <button type="button" class="btn-recipe ghost" onclick="removeHopAlarm(${i}, ${j})" title="Remover">✕</button>
          </div>
        `).join('');

        return `
          <div class="cadastro-step-card">
            <div class="cadastro-step-header">
              <span class="cadastro-step-number">${i + 1}</span>
              <select class="alarm-settings-select" style="width:auto; flex:1;" onchange="updateStepField(${i}, 'vessel', this.value)">${vesselOptions}</select>
              <button type="button" class="btn-recipe ghost cadastro-step-remove" onclick="removeCadastroStep(${i})" title="Remover etapa">🗑</button>
            </div>
            <div class="cadastro-step-grid">
              <label>
                <span class="alarm-settings-label">Rótulo (opcional)</span>
                <input type="text" class="alarm-settings-input" value="${step.label || ''}" placeholder="Ex.: Sacarificação" onchange="updateStepField(${i}, 'label', this.value)">
              </label>
              <label>
                <span class="alarm-settings-label">Temperatura alvo (°C)</span>
                <input type="number" step="0.1" class="alarm-settings-input" value="${step.target_temp}" onchange="updateStepField(${i}, 'target_temp', this.value)">
              </label>
              <label>
                <span class="alarm-settings-label">Tempo de patamar (min)</span>
                <input type="number" class="alarm-settings-input" value="${step.hold_minutes}" onchange="updateStepField(${i}, 'hold_minutes', this.value)">
              </label>
            </div>
            <div class="cadastro-pumps-row">${pumpChecks}</div>
            <div class="cadastro-hop-alarms">
              <span class="alarm-settings-label">Alarmes de lúpulo (opcional)</span>
              ${hopAlarmRows}
              <button type="button" class="btn-recipe ghost" style="margin-top:6px;" onclick="addHopAlarm(${i})">+ Alarme</button>
            </div>
          </div>
        `;
      }).join('');
    }

    function updateStepField(index, field, value) {
      const step = cadastroDraft.steps[index];
      if (field === 'target_temp' || field === 'hold_minutes') {
        step[field] = parseFloat(value) || 0;
      } else {
        step[field] = value;
      }
    }

    function toggleStepPump(index, pumpId, checked) {
      const step = cadastroDraft.steps[index];
      const pumps = new Set(step.pumps || []);
      if (checked) pumps.add(pumpId); else pumps.delete(pumpId);
      step.pumps = Array.from(pumps);
    }

    function addCadastroStep() {
      const vessels = cadastroDraft.vessels || [];
      cadastroDraft.steps.push({
        vessel: vessels[0] ? vessels[0].id : '',
        label: '',
        target_temp: 65,
        hold_minutes: 30,
        pumps: [],
      });
      renderCadastroSteps();
    }

    function removeCadastroStep(index) {
      cadastroDraft.steps.splice(index, 1);
      renderCadastroSteps();
    }

    function addHopAlarm(stepIndex) {
      const step = cadastroDraft.steps[stepIndex];
      if (!step.hop_alarms) step.hop_alarms = [];
      step.hop_alarms.push({ minutes_remaining: 0, label: '' });
      renderCadastroSteps();
    }

    function removeHopAlarm(stepIndex, alarmIndex) {
      cadastroDraft.steps[stepIndex].hop_alarms.splice(alarmIndex, 1);
      renderCadastroSteps();
    }

    function updateHopAlarm(stepIndex, alarmIndex, field, value) {
      const alarm = cadastroDraft.steps[stepIndex].hop_alarms[alarmIndex];
      alarm[field] = field === 'minutes_remaining' ? (parseFloat(value) || 0) : value;
    }

    async function saveCadastroRecipe() {
      const errorEl = $('cadastroError');
      errorEl.style.display = 'none';

      if (!cadastroDraft.name || !cadastroDraft.name.trim()) {
        errorEl.textContent = 'Dê um nome pra receita antes de salvar.';
        errorEl.style.display = 'block';
        return;
      }
      if (!cadastroDraft.steps || cadastroDraft.steps.length === 0) {
        errorEl.textContent = 'Adicione ao menos uma etapa antes de salvar.';
        errorEl.style.display = 'block';
        return;
      }

      try {
        let res;
        if (cadastroEditingId) {
          res = await fetch(`/api/recipes/${cadastroEditingId}`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ recipe: cadastroDraft })
          });
        } else {
          const source = document.querySelector('input[name="cadastroSource"]:checked').value;
          res = await fetch('/api/recipes', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source, recipe: cadastroDraft })
          });
        }
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || 'Falha ao salvar receita');

        toast(`✅ Receita salva`, 'success');
        closeCadastroForm();
        loadCadastroTab();
      } catch (e) {
        errorEl.textContent = e.message;
        errorEl.style.display = 'block';
      }
    }

    // ===== STATUS MQTT =====
    async function fetchStatus() {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) throw new Error('Status API error');
        const data = await res.json();
        const dot = $('statusDot');
        const text = $('statusText');
        dot.className = 'led-dot ' + (data.mqtt || 'unknown');
        const labels = { connected: 'MQTT Conectado', disconnected: 'MQTT Desconectado', disabled: 'MQTT Desabilitado', unknown: 'Status Desconhecido' };
        text.textContent = labels[data.mqtt] || data.mqtt;
      } catch (e) {
        $('statusDot').className = 'led-dot unknown';
        $('statusText').textContent = 'Erro ao buscar status';
      }
    }

    // ===== RENDER =====
    function renderDevices(devices) {
      // Atualiza contadores
      const sensors = devices.filter(d => d.role === 'sensor');
      const actuators = devices.filter(d => d.role === 'actuator');
      $('sensorCount').textContent = sensors.length;
      $('actuatorCount').textContent = actuators.length;

      // Grid Sensores
      const sensorGrid = $('sensorGrid');
      if (sensors.length === 0) {
        sensorGrid.innerHTML = '<p style="color: var(--text-secondary); grid-column: 1/-1;">Nenhum sensor configurado.</p>';
      } else {
        sensorGrid.innerHTML = sensors.map(d => renderCard(d)).join('');
      }

      // Grid Atuadores
      const actuatorGrid = $('actuatorGrid');
      if (actuators.length === 0) {
        actuatorGrid.innerHTML = '<p style="color: var(--text-secondary); grid-column: 1/-1;">Nenhum atuador configurado.</p>';
      } else {
        actuatorGrid.innerHTML = actuators.map(d => renderCard(d)).join('');
      }

      // Tabela de gerenciamento
      const tbody = $('deviceTableBody');
      if (devices.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color: var(--text-secondary);">Nenhum dispositivo encontrado.</td></tr>';
      } else {
        tbody.innerHTML = devices.map(d => `
          <tr>
            <td><code style="background:var(--bg-primary);padding:2px 6px;border-radius:4px;">${d.id}</code></td>
            <td><strong>${d.name}</strong></td>
            <td><span style="text-transform:capitalize;">${d.role}</span></td>
            <td>${d.subtype || 'digital'}</td>
            <td>${d.gpio ?? '—'}</td>
            <td>
              <span class="status-indicator ${(d.value === true || d.value === 'true' || d.value > 0) ? 'on' : 'off'}"></span>
              ${typeof d.value === 'boolean' ? (d.value ? 'Ligado' : 'Desligado') : d.value}${d.unit || ''}
            </td>
            <td>${d.range ? `${d.range.min} – ${d.range.max}` : '—'}</td>
            <td>${d.is_risk ? '⚠️ Sim' : '❌ Não'}</td>
          </tr>
        `).join('');
      }
    }

    function renderCard(d) {
      const isRisk = d.is_risk ? 'risk' : '';
      const unit = d.unit || '';
      let valueDisplay = d.value;
      if (typeof d.value === 'boolean') valueDisplay = d.value ? 'Ligado' : 'Desligado';
      if (d.window_seconds != null) {
        // Controle de potência: o pino físico pisca liga/desliga várias
        // vezes por janela (time-proportioning) — mostrar o valor cru
        // (d.value) piscaria de forma confusa a cada poll. Mostra o
        // resultado estável (efetivo) em vez disso.
        valueDisplay = d.duty_source === 'idle' || d.duty_source == null ? 'Desligado' : `${d.duty_percent}%`;
      }

      let controlsHtml = '';
      if (d.role === 'sensor') {
        // Sensor: mostra slider de simulação
        const min = d.range?.min ?? 0;
        const max = d.range?.max ?? 100;
        const step = (d.subtype === 'digital') ? 1 : 0.1;
        controlsHtml = `
          <input type="range" min="${min}" max="${max}" step="${step}" value="${d.value}" 
                 oninput="simulate('${d.id}', parseFloat(this.value))">
          <div class="range-labels"><span>${min}</span><span>${max}</span></div>
          <small style="color:var(--text-secondary);font-size:11px;">🔄 Arraste para simular</small>
        `;
      } else {
        // Atuador
        if (d.window_seconds != null) {
          // Controle de potência (time-proportioning) — SSR liga/desliga
          // por ciclos inteiros, potência real vem da % de tempo ligado
          // dentro da janela (d.window_seconds), não de PWM de hardware.
          //
          // Interruptor mestre (d.duty_enabled) e valor de % (d.manual_duty_percent)
          // são independentes de propósito: arrastar o slider sozinho
          // NUNCA energiza o atuador — só quando o interruptor é ligado
          // explicitamente é que o valor configurado passa a valer.
          const manualDuty = d.manual_duty_percent ?? 0;
          const sourceLabels = {
            manual: '🖐️ Manual',
            pid: '🌡️ Receita (PID)',
            failsafe_suspended: '🛑 Failsafe',
            idle: '⏸️ Repouso',
          };
          const sourceLabel = sourceLabels[d.duty_source] || d.duty_source || '';
          const appliedNote = (d.duty_source && d.duty_source !== 'idle') ? ` (${d.duty_percent}%)` : '';
          controlsHtml = `
            <div class="toggle-wrapper">
              <div class="toggle ${d.duty_enabled ? 'active' : ''}" onclick="toggleDutyEnabled('${d.id}', ${!d.duty_enabled})">
                <div class="thumb"></div>
              </div>
              <span class="toggle-label">${d.duty_enabled ? 'Controle ligado' : 'Controle desligado'}</span>
            </div>
            <input type="range" min="0" max="100" step="1" value="${manualDuty}"
                   oninput="dutyPreview('${d.id}', this.value)"
                   onchange="setDuty('${d.id}', parseFloat(this.value))">
            <div class="range-labels"><span>0%</span><span id="dutyLabel-${d.id}">${manualDuty}%</span><span>100%</span></div>
            <small style="color:var(--text-secondary);font-size:11px;">Aplicado: ${sourceLabel}${appliedNote} · janela ${d.window_seconds}s</small>
          `;
        } else if (d.subtype === 'pwm') {
          controlsHtml = `
            <input type="range" min="0" max="100" step="1" value="${d.value}" 
                   oninput="command('${d.id}', parseFloat(this.value))">
            <div class="range-labels"><span>0%</span><span>100%</span></div>
          `;
        } else {
          // Digital: toggle switch
          const isOn = d.value === true || d.value === 'true' || d.value === 1;
          controlsHtml = `
            <div class="toggle-wrapper">
              <div class="toggle ${isOn ? 'active' : ''}" onclick="toggleActuator('${d.id}', ${!isOn})">
                <div class="thumb"></div>
              </div>
              <span class="toggle-label">${isOn ? 'Ligado' : 'Desligado'}</span>
            </div>
          `;
        }
      }

      const riskBadge = isRisk ? ' ⚠️' : '';
      const roleTag = d.role === 'sensor' ? '📊' : '🔧';

      return `
        <div class="card ${isRisk}">
          <div class="card-header">
            <h3>${d.name}${riskBadge}</h3>
            <span class="type-tag">${roleTag} ${d.subtype || d.role}</span>
          </div>
          <div class="card-value">${valueDisplay}<span class="unit">${unit}</span></div>
          <div class="card-meta">
            <span>ID: ${d.id}</span>
            ${d.gpio !== undefined ? `<span>GPIO: ${d.gpio}</span>` : ''}
          </div>
          <div class="card-actions">
            ${controlsHtml}
          </div>
        </div>
      `;
    }

    // ===== API FUNCTIONS =====
    async function command(id, value) {
      try {
        const res = await fetch(`/api/devices/${id}/command`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ value })
        });
        if (!res.ok) throw new Error('Falha ao executar comando');
        toast(`✅ Comando enviado para ${id}`, 'success');
        refresh();
      } catch (e) {
        toast(`❌ Erro: ${e.message}`, 'error');
      }
    }

    async function simulate(id, value) {
      try {
        const res = await fetch(`/api/devices/${id}/simulate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ value: parseFloat(value) })
        });
        if (!res.ok) throw new Error('Falha na simulação');
        // Não damos toast a cada arrasto para não poluir, apenas atualizamos silenciosamente
      } catch (e) {
        toast(`❌ Erro na simulação: ${e.message}`, 'error');
      }
    }

    // Função especial para toggle (evita dupla chamada)
    window.toggleActuator = function (id, newState) {
      command(id, newState);
    };

    // Atualiza só o label enquanto o usuário arrasta o slider de duty,
    // sem bater na API a cada pixel — a chamada de fato só acontece em
    // onchange (setDuty), quando o usuário solta o slider.
    window.dutyPreview = function (id, value) {
      const label = document.getElementById(`dutyLabel-${id}`);
      if (label) label.textContent = `${value}%`;
    };

    async function setDuty(id, dutyPercent) {
      try {
        const res = await fetch(`/api/devices/${id}/duty`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ duty_percent: dutyPercent })
        });
        if (!res.ok) throw new Error('Falha ao definir potência');
        toast(`✅ Potência de ${id} definida em ${dutyPercent}%`, 'success');
        refresh();
      } catch (e) {
        toast(`❌ Erro: ${e.message}`, 'error');
      }
    }

    async function toggleDutyEnabled(id, enabled) {
      try {
        const res = await fetch(`/api/devices/${id}/duty/enabled`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled })
        });
        if (!res.ok) throw new Error('Falha ao ligar/desligar controle');
        toast(`✅ Controle de ${id} ${enabled ? 'ligado' : 'desligado'}`, 'success');
        refresh();
      } catch (e) {
        toast(`❌ Erro: ${e.message}`, 'error');
      }
    }

    // Toggle do controle manual dentro do card da vasilha (receita) — usa
    // o mesmo endpoint /duty/enabled do heater_device_id da vasilha, só
    // lê o estado atual em window.lastDevices em vez de um valor fixo
    // gravado no HTML (o card da vasilha é renderizado uma vez só, ao
    // carregar a receita, então não dá pra "cravar" o !enabled no onclick
    // como é feito na grade de Atuadores, que é re-renderizada a cada poll).
    window.toggleVesselManual = function (vesselName, heaterDeviceId) {
      const device = deviceById(heaterDeviceId);
      const currentlyEnabled = !!(device && device.duty_enabled);
      toggleDutyEnabled(heaterDeviceId, !currentlyEnabled);
    };

    // Atualiza só o label do slider de duty dentro do card da vasilha
    // enquanto o usuário arrasta — mesma lógica de dutyPreview(), só que
    // aponta pro elemento do card da receita em vez do card de Atuadores.
    window.vesselDutyPreview = function (vesselName, value) {
      const label = document.getElementById(`vdutyLabel-${vesselName}`);
      if (label) label.textContent = `${value}%`;
    };

    // Bomba (ou qualquer atuador simples liga/desliga) dentro do card da
    // vasilha — toque alterna o valor físico atual E assume controle
    // manual (o RecipeEngine para de mexer nesse device até ser
    // liberado). Reaproveita o mesmo endpoint /command já usado pela
    // grade de Atuadores — o registro de override acontece no backend
    // (command_device -> set_manual_override), não aqui.

    window.togglePumpManual = function (pumpId) {
      const device = deviceById(pumpId);
      const currentlyOn = !!(device && device.value === true);
      command(pumpId, !currentlyOn);
    };
    


    window.releasePumpManual = async function (pumpId) {
      try {
        const res = await fetch(`/api/devices/${pumpId}/command`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ value: null })
        });
        if (!res.ok) throw new Error('Falha ao liberar controle');
        toast(`✅ ${pumpId} devolvida pro controle automático da receita`, 'success');
        refresh();
      } catch (e) {
        toast(`❌ Erro: ${e.message}`, 'error');
      }
    };

    async function refresh() {
      try {
        const res = await fetch('/api/devices');
        if (!res.ok) throw new Error('Falha ao buscar dispositivos');
        const devices = await res.json();
        window.lastDevices = devices;
        renderDevices(devices);

        // Atualização otimista: as ações do usuário (setDuty, toggle de
        // controle manual, comando de bomba) já chamam refresh() na
        // hora após o POST — sem isto, o card da vasilha (gauge,
        // subcard de bomba) só reflete a ação no próximo tick
        // independente de pollRecipeStatus (até 2,5s depois). Reusa o
        // último status de receita em cache — não busca de novo, já
        // que o que mudou com a ação foi window.lastDevices, não a
        // etapa/alvo da receita em si.
        if (recipeLoaded && window.lastRecipeStatus) {
          updateVesselGaugesFromStatus(window.lastRecipeStatus);
        }
      } catch (e) {
        toast(`❌ Erro ao atualizar: ${e.message}`, 'error');
      }
    }


    // ===== RECEITAS =====
    let recipeDefinition = null;
    let recipeLoaded = false;
    const chartHistory = {};
    const MAX_CHART_POINTS = 150;

    function deviceValue(id) {
      const list = window.lastDevices || [];
      const d = list.find(x => x.id === id);
      return d ? d.value : null;
    }

    function deviceById(id) {
      const list = window.lastDevices || [];
      return list.find(x => x.id === id) || null;
    }

    async function loadRecipeDefinition() {
      try {
        const res = await fetch('/api/recipe/definition');
        if (!res.ok) {
          recipeLoaded = false;
          $('recipeEmpty').style.display = 'block';
          $('recipeContent').style.display = 'none';
          return;
        }
        recipeDefinition = await res.json();
        recipeLoaded = true;
        $('recipeEmpty').style.display = 'none';
        $('recipeContent').style.display = 'block';
        $('recipeName').textContent = recipeDefinition.name;
        renderVesselSkeleton();
        renderTimeline(null);
      } catch (e) {
        recipeLoaded = false;
      }
    }

    function vesselPumpIds(vesselName) {
      const ids = new Set();
      recipeDefinition.steps.forEach(s => { if (s.vessel === vesselName) s.pumps.forEach(p => ids.add(p)); });
      return Array.from(ids);
    }
    function renderVesselSkeleton() {
      const row = $('vesselRow');
      row.innerHTML = (recipeDefinition.vessel_order || Object.keys(recipeDefinition.vessels)).map(name => {
        // Busca o label. Se não existir, usa o próprio name e coloca a 1ª letra em maiúscula
        const vesselData = recipeDefinition.vessels[name];
        const displayLabel = vesselData.label || (name.charAt(0).toUpperCase() + name.slice(1));
        const heaterId = vesselData.heater_device_id;

        return `
        <div class="vessel-card" id="vcard-${name}">
          <div class="vessel-top-row">
            <div class="gauge-wrap">
              <svg viewBox="0 0 104 104">
                <circle class="gauge-track" cx="52" cy="52" r="44"></circle>
                <circle class="gauge-fill" id="gfill-${name}" cx="52" cy="52" r="44"
                        stroke-dasharray="0 276.5"></circle>
              </svg>
              <div class="gauge-center">
                <div class="gauge-temp" id="gtemp-${name}">\u2014</div>
                <div class="gauge-duty" id="gduty-${name}">0% pot.</div>
              </div>
            </div>
            <div class="vessel-info">
              <div class="vessel-name">${displayLabel}</div>
              <div class="vessel-target" id="vtarget-${name}"><span class="arrow">\u2192</span> aguardando</div>
              <div class="vessel-pumps" id="vpumps-${name}"></div>
            </div>
          </div>
          <div class="vessel-manual-control" id="vmanual-${name}">
            <div class="toggle-wrapper">
              <div class="toggle" id="vtoggle-${name}" onclick="toggleVesselManual('${name}', '${heaterId}')">
                <div class="thumb"></div>
              </div>
              <span class="toggle-label" id="vtoggle-label-${name}">Controle desligado</span>
            </div>
            <input type="range" min="0" max="100" step="1" value="0" id="vduty-slider-${name}"
                   oninput="dutyPreview('${heaterId}', this.value); vesselDutyPreview('${name}', this.value)"
                   onchange="setDuty('${heaterId}', parseFloat(this.value))">
            <div class="range-labels"><span>0%</span><span id="vdutyLabel-${name}">0%</span><span>100%</span></div>
            <small style="color:var(--text-secondary);font-size:11px;" id="vsource-${name}"></small>
          </div>
        </div>
        `;
      }).join('');
    }

    /*
    function renderTimeline(status) {
      const track = $('timelineTrack');
      track.innerHTML = recipeDefinition.steps.map((s, i) => {
        let cls = 'timeline-step';
        let meta = `${s.target_temp}\u00b0C \u00b7 ${s.hold_minutes}min`;
        if (status) {
          if (i < status.step_index) cls += ' done';
          else if (i === status.step_index && (status.status === 'ramping' || status.status === 'holding')) {
            cls += ' current';
            if (status.status === 'holding') cls += ' holding';
            meta = status.status === 'ramping' ? 'subindo\u2026' : 'em patamar\u2026';
          } else if (i === status.step_index && status.status === 'finished') {
            cls += ' done';
          }
        }
        const label = s.label || `${s.vessel} \u2014 ${s.target_temp}\u00b0C`;
        return `
          <div class="${cls}">
            <div class="timeline-line"></div>
            <div class="timeline-node">${i + 1}</div>
            <div class="timeline-label">${label}</div>
            <div class="timeline-meta">${meta}</div>
          </div>`;
      }).join('');
    }
    */

    function renderTimeline(status) {
      const track = $('timelineTrack');
      track.innerHTML = recipeDefinition.steps.map((s, i) => {
        let cls = 'timeline-step';
        let meta = `${s.target_temp}\u00b0C \u00b7 ${s.hold_minutes}min`;
        if (status) {
          if (i < status.step_index) cls += ' done';
          else if (i === status.step_index && (status.status === 'ramping' || status.status === 'holding')) {
            cls += ' current';
            if (status.status === 'holding') cls += ' holding';
            meta = status.status === 'ramping' ? 'subindo\u2026' : 'em patamar\u2026';
          } else if (i === status.step_index && status.status === 'finished') {
            cls += ' done';
          }
        }

        // MUDANÇA AQUI: Busca o label do vessel para a timeline
        const vesselDisplayLabel = recipeDefinition.vessels[s.vessel]?.label || s.vessel;
        const label = s.label || `${vesselDisplayLabel} \u2014 ${s.target_temp}\u00b0C`;

        return `
          <div class="${cls}">
            <div class="timeline-line"></div>
            <div class="timeline-node">${i + 1}</div>
            <div class="timeline-label">${label}</div>
            <div class="timeline-meta">${meta}</div>
          </div>`;
      }).join('');
    }


    let currentStepIndexCache = 0;

    function updateGauge(vesselName, currentTemp, targetTemp, heaterDevice, active) {
      const card = $('vcard-' + vesselName);
      if (!card) return;
      card.classList.toggle('active', !!active);

      const dutyPercent = heaterDevice ? (heaterDevice.duty_percent || 0) : 0;
      const dutySource = heaterDevice ? heaterDevice.duty_source : null;
      const heating = dutySource && dutySource !== 'idle';

      const C = 2 * Math.PI * 44;
      const frac = Math.max(0, Math.min(1, dutyPercent / 100));
      $('gfill-' + vesselName).setAttribute('stroke-dasharray', `${(frac * C).toFixed(1)} ${C.toFixed(1)}`);
      $('gtemp-' + vesselName).textContent = (currentTemp !== null && currentTemp !== undefined) ? `${currentTemp.toFixed(1)}\u00b0` : '\u2014';
      $('gduty-' + vesselName).textContent = heating ? `${Math.round(dutyPercent)}% pot.` : 'inativo';

      const targetEl = $('vtarget-' + vesselName);
      targetEl.innerHTML = active
        ? `<span class="arrow">\u2192</span> alvo ${targetTemp}\u00b0C`
        : `<span class="arrow">\u2192</span> aguardando`;

      // Sincroniza o controle manual (toggle + slider) com o estado real
      // do heater_device_id dessa vasilha — funciona mesmo quando a
      // receita não está na etapa desta vasilha (um override manual não
      // depende de qual etapa está ativa).
      const toggleEl = $('vtoggle-' + vesselName);
      const toggleLabelEl = $('vtoggle-label-' + vesselName);
      const sliderEl = $('vduty-slider-' + vesselName);
      const sliderLabelEl = $('vdutyLabel-' + vesselName);
      const sourceEl = $('vsource-' + vesselName);
      const manualEnabled = !!(heaterDevice && heaterDevice.duty_enabled);
      const manualDuty = heaterDevice ? (heaterDevice.manual_duty_percent ?? 0) : 0;
      if (toggleEl) toggleEl.classList.toggle('active', manualEnabled);
      if (toggleLabelEl) toggleLabelEl.textContent = manualEnabled ? 'Controle ligado' : 'Controle desligado';
      // Não sobrescreve o slider enquanto o usuário está arrastando (foco ativo nele).
      if (sliderEl && document.activeElement !== sliderEl) sliderEl.value = manualDuty;
      if (sliderLabelEl) sliderLabelEl.textContent = `${manualDuty}%`;
      if (sourceEl) {
        const sourceLabels = {
          manual: '\ud83e\uddb1\ufe0f Manual', pid: '\ud83c\udf21\ufe0f Receita (PID)',
          failsafe_suspended: '\ud83d\uded1 Failsafe', idle: '\u23f8\ufe0f Repouso',
        };
        sourceEl.textContent = heaterDevice ? `Aplicado: ${sourceLabels[dutySource] || dutySource || ''}` : '';
      }

      updatePumpSubcards(vesselName);
    }

    // Marcação HTML de um subcard de bomba — usada só quando a LISTA de
    // bombas da vasilha muda de "formato" (entrou/saiu do estado
    // "aguardando confirmação", ou a lista de ids mudou). Estado que
    // muda com frequência (ligado/desligado, manual/receita) NÃO passa
    // por aqui depois da primeira renderização — ver syncPumpSubcard().
    function renderPumpSubcardHtml(pid, pendingPumps) {
      // Estado "aguardando confirmação" tem prioridade sobre tudo — a
      // receita quer ligar essa bomba pela primeira vez nesta execução
      // e precisa de aprovação explícita antes (evita energizar bomba
      // com conexão fechada/errada sem checar).
      if (pendingPumps.includes(pid)) {
        return `
          <div class="pump-subcard pending" data-pump-id="${pid}">
            <div class="pump-subcard-info">
              <span class="pump-subcard-name">${pid}</span>
              <span class="pump-subcard-pending-label">⚠️ Ligar automaticamente?</span>
            </div>
            <div class="pump-confirm-actions">
              <button type="button" class="pump-confirm-btn approve" onclick="confirmPumpAuto('${pid}')">Confirmar</button>
              <button type="button" class="pump-confirm-btn decline" onclick="declinePumpAuto('${pid}')">Manter manual</button>
            </div>
          </div>
        `;
      }

      return `
        <div class="pump-subcard" data-pump-id="${pid}">
          <button type="button" class="pump-power-btn" onclick="togglePumpManual('${pid}')"></button>
          <div class="pump-subcard-info">
            <span class="pump-subcard-name">${pid}</span>
            <span class="pump-mode-badge"></span>
          </div>
        </div>
      `;
    }

    // Sincroniza só os campos que mudam com frequência (ligado/
    // desligado, manual/receita) de um subcard "normal" já existente no
    // DOM, sem recriar nós — evita o "piscar" de regenerar o HTML
    // inteiro a cada poll (2,5s), quando na prática só o ícone/badge
    // mudam.
    function syncPumpSubcard(subcard, pid) {
      const pumpDevice = deviceById(pid);


      //const isOn = pumpDevice ? pumpDevice.value === true : false;
      const isOn = pumpDevice ? Boolean(Number(pumpDevice.value)) : false;


      const isManual = !!(pumpDevice && pumpDevice.manual_override !== null && pumpDevice.manual_override !== undefined);

      subcard.classList.toggle('on', isOn);
      subcard.classList.toggle('manual', isManual);

      // Ícone real (não label sem affordance): ▶ quando desligada
      // (ação = "ligar"), ⏹ quando ligada (ação = "parar").
      const btn = subcard.querySelector('.pump-power-btn');
      if (btn) {
        btn.textContent = isOn ? '\u23f9' : '\u25b6';
        btn.title = isOn ? 'Parar bomba (assume controle manual)' : 'Ligar bomba (assume controle manual)';
      }

      const badge = subcard.querySelector('.pump-mode-badge');
      if (badge) {
        badge.classList.toggle('manual', isManual);
        badge.textContent = isManual ? '\ud83e\uddb1\ufe0f Manual' : '\ud83e\udd16 Receita';
      }

      let releaseBtn = subcard.querySelector('.pump-release-btn');
      if (isManual && !releaseBtn) {
        releaseBtn = document.createElement('button');
        releaseBtn.type = 'button';
        releaseBtn.className = 'pump-release-btn';
        releaseBtn.title = 'Devolver pro controle automático da receita';
        releaseBtn.textContent = '\u21ba';
        releaseBtn.onclick = () => releasePumpManual(pid);
        subcard.appendChild(releaseBtn);
      } else if (!isManual && releaseBtn) {
        releaseBtn.remove();
      }
    }

    function updatePumpSubcards(vesselName) {
      const pumpsEl = $('vpumps-' + vesselName);
      const pumpIds = vesselPumpIds(vesselName);
      const pendingPumps = window.pendingPumpConfirmations || [];

      // Só recria o DOM quando a "forma" da lista muda (bomba entrou/
      // saiu do estado pendente, ou a lista de ids em si mudou) — não
      // a cada poll, que é o que causava o piscar mesmo sem mudança
      // real de estado.
      const signature = pumpIds.map(pid => `${pid}:${pendingPumps.includes(pid) ? 'pending' : 'normal'}`).join('|');
      if (pumpsEl.dataset.signature !== signature) {
        pumpsEl.innerHTML = pumpIds.map(pid => renderPumpSubcardHtml(pid, pendingPumps)).join('');
        pumpsEl.dataset.signature = signature;
      }

      pumpIds.forEach(pid => {
        if (pendingPumps.includes(pid)) return; // sem campos dinâmicos a sincronizar no estado pendente
        const subcard = pumpsEl.querySelector(`.pump-subcard[data-pump-id="${pid}"]`);
        if (subcard) syncPumpSubcard(subcard, pid);
      });
    }

    function pushChartPoint(vesselName, actual, setpoint) {
      if (!chartHistory[vesselName]) chartHistory[vesselName] = [];
      const arr = chartHistory[vesselName];
      arr.push({ t: Date.now(), actual, setpoint });
      if (arr.length > MAX_CHART_POINTS) arr.shift();
    }

    function drawChart(vesselName) {
      const svg = $('recipeChart');
      const arr = chartHistory[vesselName] || [];
      if (arr.length < 2) { svg.innerHTML = ''; return; }

      const W = 800, H = 180, PAD = 10;
      const temps = arr.flatMap(p => [p.actual, p.setpoint]).filter(v => v !== null && v !== undefined);
      const yMin = Math.min(...temps) - 2;
      const yMax = Math.max(...temps) + 2;
      const xStep = (W - PAD * 2) / (MAX_CHART_POINTS - 1);
      const xOffset = W - PAD - (arr.length - 1) * xStep;

      const toY = v => H - PAD - ((v - yMin) / (yMax - yMin || 1)) * (H - PAD * 2);
      const toX = i => xOffset + i * xStep;

      const actualPath = arr.map((p, i) => `${i === 0 ? 'M' : 'L'} ${toX(i).toFixed(1)} ${toY(p.actual).toFixed(1)}`).join(' ');
      const setpointPath = arr.map((p, i) => `${i === 0 ? 'M' : 'L'} ${toX(i).toFixed(1)} ${toY(p.setpoint).toFixed(1)}`).join(' ');

      svg.innerHTML = `
        <path d="${setpointPath}" fill="none" stroke="var(--ink-warm-400)" stroke-width="1.5" stroke-dasharray="5 5" />
        <path d="${actualPath}" fill="none" stroke="var(--copper-500)" stroke-width="2.5" />
      `;
    }

    // Atualiza só os cards de vasilha (gauge, potência, subcards de
    // bomba) a partir do último status de receita conhecido — extraído
    // de pollRecipeStatus() pra poder ser chamado também logo após
    // refresh() (ver mais abaixo), sem precisar buscar /api/recipe/status
    // de novo: um comando do usuário muda window.lastDevices na hora,
    // não muda o status da receita em si (etapa/alvo), então reusar o
    // status em cache é seguro e evita esperar o próximo tick de
    // pollRecipeStatus (até 2,5s) só pra refletir a própria ação.
    function updateVesselGaugesFromStatus(status) {
      const active = (status.status === 'ramping' || status.status === 'holding');
      const currentVessel = status.current_vessel;
      const currentStep = active ? recipeDefinition.steps[status.step_index] : null;

      (recipeDefinition.vessel_order || Object.keys(recipeDefinition.vessels)).forEach(name => {
        const isActive = active && name === currentVessel;
        const vesselInfo = recipeDefinition.vessels[name];
        const sensorId = vesselInfo.sensor_device_id;
        const temp = deviceValue(sensorId);
        const heaterDevice = deviceById(vesselInfo.heater_device_id);
        updateGauge(name, temp, currentStep ? currentStep.target_temp : null, heaterDevice, isActive);
      });

      if (active && currentVessel) {
        const sensorId = recipeDefinition.vessels[currentVessel].sensor_device_id;
        const temp = deviceValue(sensorId);
        if (temp !== null) {
          pushChartPoint(currentVessel, temp, currentStep.target_temp);
          drawChart(currentVessel);
        }
      }
    }

    async function pollRecipeStatus() {
      if (!recipeLoaded) return;
      try {
        const res = await fetch('/api/recipe/status');
        if (!res.ok) return;
        const status = await res.json();
        window.lastRecipeStatus = status;
        currentStepIndexCache = status.step_index;

        const pill = $('recipeStatusPill');
        pill.className = 'status-pill ' + status.status;
        const labels = {
          idle: 'Parada', ramping: 'Subindo', holding: 'Em patamar',
          finished: 'Concluida', aborted: 'Cancelada',
          paused_after_crash: 'Pausada (queda)', paused_manual: 'Pausada',
        };
        $('recipeStatusText').textContent = labels[status.status] || status.status;

        $('btnStart').disabled = (status.status === 'ramping' || status.status === 'holding');
        $('btnAbort').disabled = !(status.status === 'ramping' || status.status === 'holding');

        const banner = $('crashBanner');
        if (status.status === 'paused_after_crash') {
          banner.classList.add('show');
          $('crashFromStatus').textContent = status.paused_from_status === 'holding' ? 'o patamar' : 'a rampa';
        } else {
          banner.classList.remove('show');
        }

        updateTransportBar(status);
        updateCountdownAnchor(status);
        updateTotalTimeDisplay(status);
        updateAlarmUI(status);

        window.pendingPumpConfirmations = status.pending_pump_confirmations || [];
        updatePumpConfirmBanner(window.pendingPumpConfirmations);

        renderTimeline(status);

        updateVesselGaugesFromStatus(status);
      } catch (e) { /* silencioso */ }
    }

    // ===== BARRA DE TRANSPORTE (Sessao A: controles manuais) =====
    const ACTIVE_RECIPE_STATUSES = ['ramping', 'holding'];
    const PAUSED_RECIPE_STATUSES = ['paused_manual', 'paused_after_crash'];
    let countdownAnchor = null;  // recalculado a cada poll, usado pelo ticker local de 1s

    function updateTransportBar(status) {
      const active = ACTIVE_RECIPE_STATUSES.includes(status.status);
      const paused = PAUSED_RECIPE_STATUSES.includes(status.status);

      $('btnSkipPrevious').disabled = !active;
      $('btnResetStep').disabled = !active;
      $('btnSkipNext').disabled = !active;

      const playBtn = $('btnPlayPause');
      playBtn.disabled = false;
      if (active) {
        playBtn.textContent = '\u23f8';  // pause
        playBtn.title = 'Pausar';
      } else {
        playBtn.textContent = '\u25b6';  // play
        playBtn.title = paused ? 'Retomar' : 'Iniciar';
      }
    }

    function updateCountdownAnchor(status) {
      const active = ACTIVE_RECIPE_STATUSES.includes(status.status);
      if (!active) {
        countdownAnchor = { mode: status.status, frozen: true };
        return;
      }
      if (status.status === 'holding' && recipeDefinition) {
        const step = recipeDefinition.steps[status.step_index];
        countdownAnchor = {
          mode: 'holding',
          deadlineEpoch: status.hold_started_at + (step.hold_minutes * 60),
          serverNowEpoch: Date.now() / 1000,
          clientNowMs: Date.now(),
        };
      } else {
        // ramping: sem duracao fixa, mostra tempo decorrido subindo
        countdownAnchor = {
          mode: 'ramping',
          startedEpoch: status.step_started_at,
          serverNowEpoch: Date.now() / 1000,
          clientNowMs: Date.now(),
        };
      }
    }

    function formatMMSS(totalSeconds) {
      const sign = totalSeconds < 0 ? '-' : '';
      const s = Math.abs(Math.round(totalSeconds));
      const mm = Math.floor(s / 60).toString().padStart(2, '0');
      const ss = (s % 60).toString().padStart(2, '0');
      return `${sign}${mm}:${ss}`;
    }

    function tickCountdownDisplay() {
      const timeEl = $('countdownTime');
      const labelEl = $('countdownLabel');
      if (!countdownAnchor) {
        timeEl.textContent = '--:--';
        labelEl.textContent = 'Aguardando inicio';
        return;
      }
      if (countdownAnchor.frozen) {
        const labels = {
          idle: 'Aguardando inicio', finished: 'Receita concluida', aborted: 'Cancelada',
          paused_manual: 'Pausada manualmente', paused_after_crash: 'Pausada (queda de energia)',
        };
        timeEl.textContent = '--:--';
        labelEl.textContent = labels[countdownAnchor.mode] || countdownAnchor.mode;
        return;
      }
      const elapsedSinceAnchor = (Date.now() - countdownAnchor.clientNowMs) / 1000;
      if (countdownAnchor.mode === 'holding') {
        const nowEpoch = countdownAnchor.serverNowEpoch + elapsedSinceAnchor;
        const remaining = countdownAnchor.deadlineEpoch - nowEpoch;
        timeEl.textContent = formatMMSS(Math.max(0, remaining));
        labelEl.textContent = 'Tempo restante na etapa';
      } else if (countdownAnchor.mode === 'ramping') {
        const nowEpoch = countdownAnchor.serverNowEpoch + elapsedSinceAnchor;
        const elapsed = nowEpoch - countdownAnchor.startedEpoch;
        timeEl.textContent = formatMMSS(elapsed);
        labelEl.textContent = 'Subindo a temperatura (tempo decorrido)';
      }
    }

    function updateTotalTimeDisplay(status) {
      const estimatedSeconds = (status.total_estimated_minutes || 0) * 60;
      $('totalEstimatedDisplay').textContent = formatMMSS(estimatedSeconds);
      $('totalElapsedDisplay').textContent = formatMMSS(status.total_elapsed_seconds || 0);
    }

    async function togglePlayPauseRecipe() {
      try {
        const res = await fetch('/api/recipe/status');
        const status = res.ok ? await res.json() : null;
        if (!status || status.status === 'idle' || status.status === 'finished' || status.status === 'aborted') {
          await startRecipe();
        } else if (ACTIVE_RECIPE_STATUSES.includes(status.status)) {
          await fetch('/api/recipe/pause', { method: 'POST' });
          toast('Receita pausada', 'info');
          pollRecipeStatus();
        } else if (PAUSED_RECIPE_STATUSES.includes(status.status)) {
          await resumeRecipe();
        }
      } catch (e) { toast('Erro ao alternar play/pause', 'error'); }
    }

    async function skipPreviousRecipe() {
      try {
        const res = await fetch('/api/recipe/skip_previous', { method: 'POST' });
        if (!res.ok) throw new Error();
        toast('Voltou para a etapa anterior', 'info');
        pollRecipeStatus();
      } catch (e) { toast('Erro ao voltar etapa', 'error'); }
    }

    async function skipNextRecipe() {
      try {
        const res = await fetch('/api/recipe/skip_next', { method: 'POST' });
        if (!res.ok) throw new Error();
        toast('Avancou para a proxima etapa', 'info');
        pollRecipeStatus();
      } catch (e) { toast('Erro ao avancar etapa', 'error'); }
    }

    async function resetStepRecipe() {
      try {
        const res = await fetch('/api/recipe/reset_step', { method: 'POST' });
        if (!res.ok) throw new Error();
        toast('Etapa reiniciada', 'info');
        pollRecipeStatus();
      } catch (e) { toast('Erro ao reiniciar etapa', 'error'); }
    }

    // ===== ALARMES (Sessao B: som + popup) =====
    const ALARM_SETTINGS_KEY = 'tesseract_alarm_settings';
    let alarmBannerCurrentId = null;
    let alarmPlaybackToken = 0;

    function getAlarmSettings() {
      try {
        const raw = localStorage.getItem(ALARM_SETTINGS_KEY);
        if (raw) return JSON.parse(raw);
      } catch (e) { /* ignora settings corrompidas */ }
      return { soundType: 'beep', repeatCount: 3, customSoundBase64: null };
    }

    function saveAlarmSettings(settings) {
      localStorage.setItem(ALARM_SETTINGS_KEY, JSON.stringify(settings));
    }

    function loadAlarmSettingsIntoUI() {
      const settings = getAlarmSettings();
      $('alarmSoundType').value = settings.soundType;
      $('alarmRepeatCount').value = settings.repeatCount;
      $('alarmCustomSoundRow').style.display = settings.soundType === 'custom' ? 'block' : 'none';
      $('alarmCustomSoundStatus').textContent = settings.customSoundBase64
        ? 'Arquivo carregado e salvo neste navegador.'
        : 'Nenhum arquivo selecionado.';
    }

    function toggleAlarmSettings() {
      const popover = $('alarmSettingsPopover');
      const isOpen = popover.style.display !== 'none';
      if (isOpen) {
        popover.style.display = 'none';
      } else {
        loadAlarmSettingsIntoUI();
        popover.style.display = 'block';
      }
    }

    function onAlarmSoundTypeChange() {
      const settings = getAlarmSettings();
      settings.soundType = $('alarmSoundType').value;
      saveAlarmSettings(settings);
      $('alarmCustomSoundRow').style.display = settings.soundType === 'custom' ? 'block' : 'none';
    }

    function onAlarmRepeatChange() {
      const settings = getAlarmSettings();
      const value = parseInt($('alarmRepeatCount').value, 10);
      settings.repeatCount = (value >= 1 && value <= 20) ? value : 3;
      saveAlarmSettings(settings);
    }

    function onCustomSoundUpload(event) {
      const file = event.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        const settings = getAlarmSettings();
        settings.customSoundBase64 = reader.result;  // data:audio/...;base64,....
        saveAlarmSettings(settings);
        $('alarmCustomSoundStatus').textContent = `Carregado: ${file.name}`;
        toast('Som personalizado salvo neste navegador', 'success');
      };
      reader.onerror = () => toast('Erro ao ler o arquivo de audio', 'error');
      reader.readAsDataURL(file);
    }

    // ---- sintese de som via Web Audio (sem precisar de arquivo de audio) ----
    let _alarmAudioCtx = null;
    function getAudioCtx() {
      if (!_alarmAudioCtx) {
        _alarmAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
      }
      return _alarmAudioCtx;
    }

    function playTone(freq, durationMs, startDelayMs, type) {
      const ctx = getAudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type || 'sine';
      osc.frequency.value = freq;
      gain.gain.value = 0.25;
      osc.connect(gain);
      gain.connect(ctx.destination);
      const startTime = ctx.currentTime + (startDelayMs / 1000);
      osc.start(startTime);
      osc.stop(startTime + (durationMs / 1000));
    }

    function synthOneCycle(soundType) {
      if (soundType === 'beep') {
        playTone(880, 180, 0, 'sine');
      } else if (soundType === 'siren') {
        playTone(600, 220, 0, 'sawtooth');
        playTone(900, 220, 220, 'sawtooth');
      } else if (soundType === 'bell') {
        playTone(1046, 140, 0, 'triangle');
        playTone(1318, 220, 160, 'triangle');
      }
    }

    function playOneAlarmCycle(settings, onCycleDone) {
      if (settings.soundType === 'custom' && settings.customSoundBase64) {
        const audio = new Audio(settings.customSoundBase64);
        audio.onended = onCycleDone;
        audio.onerror = onCycleDone;
        audio.play().catch(() => onCycleDone());
      } else {
        synthOneCycle(settings.soundType);
        setTimeout(onCycleDone, 600);  // duracao aproximada de um ciclo sintetizado
      }
    }

    function startAlarmPlayback() {
      const settings = getAlarmSettings();
      const myToken = ++alarmPlaybackToken;
      let cyclesPlayed = 0;

      function playNext() {
        if (myToken !== alarmPlaybackToken) return;  // cancelado (ack ou novo alarme)
        if (cyclesPlayed >= settings.repeatCount) return;  // atingiu o limite -- para sozinho
        cyclesPlayed += 1;
        playOneAlarmCycle(settings, playNext);
      }
      playNext();
    }

    function stopAlarmPlayback() {
      alarmPlaybackToken += 1;  // invalida qualquer ciclo agendado
    }

    function testAlarmSound() {
      startAlarmPlayback();
    }

    function showAlarmBanner(alarm, totalPending) {
      $('alarmBannerLabel').textContent = alarm.label;
      $('alarmBannerExtra').textContent = totalPending > 1 ? `+ ${totalPending - 1} alarme(s) na fila` : '';
      $('alarmBanner').classList.add('show');
    }

    function hideAlarmBanner() {
      $('alarmBanner').classList.remove('show');
    }

    function updateAlarmUI(status) {
      const alarms = status.pending_alarms || [];
      if (alarms.length === 0) {
        if (alarmBannerCurrentId !== null) {
          stopAlarmPlayback();
          hideAlarmBanner();
          alarmBannerCurrentId = null;
        }
        return;
      }
      const first = alarms[0];
      if (first.id !== alarmBannerCurrentId) {
        alarmBannerCurrentId = first.id;
        showAlarmBanner(first, alarms.length);
        startAlarmPlayback();
      } else {
        $('alarmBannerExtra').textContent = alarms.length > 1 ? `+ ${alarms.length - 1} alarme(s) na fila` : '';
      }
    }

    async function acknowledgeCurrentAlarm() {
      if (alarmBannerCurrentId === null) return;
      stopAlarmPlayback();
      try {
        await fetch(`/api/recipe/alarms/${alarmBannerCurrentId}/ack`, { method: 'POST' });
      } catch (e) { /* segue mesmo se a chamada falhar -- proximo poll resincroniza */ }
      alarmBannerCurrentId = null;
      hideAlarmBanner();
      pollRecipeStatus();
    }

    // Banner de bombas aguardando confirmação — só informativo (sem
    // botão de ação, diferente do banner de alarme): a ação em si
    // acontece no subcard da bomba, que mostra os botões Confirmar/
    // Manter manual. O banner some sozinho assim que a lista de
    // pendências fica vazia, sem precisar de nenhum "OK" manual.
    function updatePumpConfirmBanner(pending) {
      const banner = $('pumpConfirmBanner');
      if (!pending || pending.length === 0) {
        banner.classList.remove('show');
        return;
      }
      const text = pending.length === 1
        ? `Bomba <strong>${pending[0]}</strong> aguardando confirmação para ligar automaticamente`
        : `<strong>${pending.length} bombas</strong> aguardando confirmação para ligar automaticamente: ${pending.join(', ')}`;
      $('pumpConfirmBannerText').innerHTML = text;
      banner.classList.add('show');
    }

    async function confirmPumpAuto(pumpId) {
      try {
        const res = await fetch(`/api/recipe/pumps/${pumpId}/confirm`, { method: 'POST' });
        if (!res.ok) throw new Error('Falha ao confirmar');
        toast(`✅ ${pumpId} confirmada — receita vai controlar automaticamente`, 'success');
        pollRecipeStatus();
        refresh();
      } catch (e) {
        toast(`❌ Erro: ${e.message}`, 'error');
      }
    }

    async function declinePumpAuto(pumpId) {
      try {
        const res = await fetch(`/api/recipe/pumps/${pumpId}/decline`, { method: 'POST' });
        if (!res.ok) throw new Error('Falha ao manter manual');
        toast(`✅ ${pumpId} mantida em controle manual`, 'success');
        pollRecipeStatus();
        refresh();
      } catch (e) {
        toast(`❌ Erro: ${e.message}`, 'error');
      }
    }

    async function startRecipe() {
      try {
        await fetch('/api/recipe/start', { method: 'POST' });
        toast('Receita iniciada', 'success');
        pollRecipeStatus();
      } catch (e) { toast('Erro ao iniciar receita', 'error'); }
    }

    async function abortRecipe() {
      try {
        await fetch('/api/recipe/abort', { method: 'POST' });
        toast('Receita cancelada, failsafe aplicado', 'info');
        pollRecipeStatus();
      } catch (e) { toast('Erro ao cancelar receita', 'error'); }
    }

    async function resumeRecipe() {
      try {
        const res = await fetch('/api/recipe/resume', { method: 'POST' });
        if (!res.ok) throw new Error();
        toast('Receita retomada de onde parou', 'success');
        pollRecipeStatus();
      } catch (e) { toast('Erro ao retomar receita', 'error'); }
    }

    // ===== INIT =====
    fetchStatus();
    refresh();
    loadRecipeDefinition().then(() => { pollRecipeStatus(); });
    setInterval(fetchStatus, 8000);//Conexão MQTT
    setInterval(refresh, 3000);
    setInterval(pollRecipeStatus, 2500);
    setInterval(tickCountdownDisplay, 1000);
