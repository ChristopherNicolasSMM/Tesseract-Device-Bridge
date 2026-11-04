/* SQLite device administration. The admin token lives only in JS memory. */
(() => {
  const $ = id => document.getElementById(id);
  let token = '', config = null, selected = -1, pending = null, revision = null;
  const msg = text => { $('sqlMessage').textContent = text; };
  async function api(path, method='GET', payload) {
    const result = await fetch('/api/admin/'+path, {
      method,
      headers: {'X-Bridge-Admin-Token': token, ...(payload ? {'Content-Type':'application/json'} : {})},
      body: payload ? JSON.stringify(payload) : undefined,
    });
    const data = await result.json();
    if (!result.ok) throw new Error(data.error || 'Falha na administração');
    return data;
  }
  const f = name => $('sqlDeviceForm').elements.namedItem(name);
  const value = name => String(f(name).value || '').trim();
  const checked = name => f(name).checked;
  function option(select, code, label) {
    const entry = document.createElement('option');
    entry.value = String(code);
    entry.textContent = label;
    select.appendChild(entry);
    return entry;
  }
  function choices(name, entries, current, placeholder) {
    const select = f(name); select.replaceChildren();
    option(select, '', placeholder);
    entries.forEach(entry => option(select, entry.id, entry.label));
    if (current && !entries.some(entry => entry.id === current)) {
      option(select, current, '⚠ Referência desconhecida: ' + current);
    }
    select.value = current || '';
  }
  function refreshReferences(device) {
    const others = config.devices;
    const sensors = others.filter(d => d.role === 'sensor' && d.subtype === 'temperature')
      .map(d => ({id:d.id,label:d.name+' ('+d.id+')'}));
    const controllers = others.filter(d => d.role === 'actuator' && d.id !== device.id
      && Number(d.hardware?.window_seconds) > 0
      && !d.hardware?.heating_source)
      .map(d => ({id:d.id,label:d.name+' ('+d.id+')'}));
    choices('temperature_sensor', sensors, device.hardware?.heating_source?.temperature_sensor || '',
      'Selecione um sensor térmico');
    choices('controller_device', controllers, device.hardware?.heating_source?.controller_device || '',
      'Selecione o controlador principal');
    const pins = f('pin'); pins.replaceChildren();
    for (let bcm=0; bcm<=27; bcm++) {
      const occupants=others.filter(d=> d.id!==device.id && Number(d.hardware?.pin)===bcm);
      option(pins, bcm, 'GPIO '+bcm+(occupants.length?' | em uso: '+occupants.map(d=>d.id).join(', '):' | livre'));
    }
    pins.value = String(device.hardware?.pin ?? 4);
    f('temperature_sensor').required = !!f('participation').value;
    f('controller_device').required = f('participation').value === 'auxiliary';
  }
  function showDevice() {
    const d = config.devices[selected], form = $('sqlDeviceForm');
    form.hidden = !d;
    if (!d) return;
    for (const field of ['id','name','role','subtype','state_topic','command_topic'])
      f(field).value = d[field] || '';
    f('pin').value = d.hardware?.pin ?? '';
    f('driver').value = d.hardware?.driver || '';
    f('address').value = d.hardware?.address || '';
    f('window_seconds').value = d.hardware?.window_seconds ?? '';
    f('is_risk').checked = !!d.is_risk;
    f('remote_control').checked = !!d.hardware?.remote_control;
    f('active_high').checked = d.hardware?.active_high !== false;
    f('participation').value = d.hardware?.heating_source?.participation || '';
    f('temperature_sensor').value = d.hardware?.heating_source?.temperature_sensor || '';
    f('controller_device').value = d.hardware?.heating_source?.controller_device || '';
    f('external_flame_cutoff').checked = !!d.hardware?.heating_source?.external_flame_cutoff;
    refreshReferences(d);
  }
  function drawList(index=selected) {
    const select = $('sqlDeviceSelect'); select.replaceChildren();
    config.devices.forEach((d,i) => {
      const option=document.createElement('option'); option.value=String(i);
      option.textContent=d.name+' ('+d.id+')'; select.appendChild(option);
    });
    selected=config.devices.length?Math.max(0,Math.min(index,config.devices.length-1)):-1;
    select.value=String(selected); showDevice();
    pending=null; $('sqlApplyDraft').disabled=true;
  }
  function drawConfig() {
    $('sqlBackend').value=config.backend;
    $('sqlMqttEnabled').checked=!!config.mqtt.enabled;
    $('sqlMqttHost').value=config.mqtt.host || 'localhost';
    $('sqlMqttPort').value=config.mqtt.port || 1883;
    $('sqlMqttPrefix').value=config.mqtt.topic_prefix || 'brewery';
    $('sqlMqttPassword').value='';
    $('sqlPanelPort').value=config.panel.port || 8088;
    $('sqlRevision').textContent='Revisão aprovada: '+revision+'. Alterações locais ainda não afetam GPIO.';
  }
  async function load() {
    const data=await api('config');
    config=data.config;revision=data.revision;
    $('sqlEditor').hidden=false;
    drawList(0);drawConfig();
    msg('Carregado. Ajuste os campos e crie um rascunho para validar.');
  }
  $('sqlUnlock').addEventListener('click', async ()=>{
    token=$('sqlToken').value;
    try { await load(); $('sqlToken').value=''; }
    catch(e){$('sqlEditor').hidden=true;msg(e.message);}
  });
  $('sqlReload').addEventListener('click',()=>load().catch(e=>msg(e.message)));
  f('participation').addEventListener('change', () => {
    const enabled = !!value('participation');
    f('temperature_sensor').required=enabled;
    f('controller_device').required=f('participation').value === 'auxiliary';
  });
  $('sqlDeviceSelect').addEventListener('change',()=>{
    selected=Number($('sqlDeviceSelect').value);showDevice();
  });
  $('sqlAddDevice').addEventListener('click',()=>{
    config.devices.push({
      id:'new_sensor',name:'Novo sensor',role:'sensor',subtype:'temperature',
      state_topic:'sensors/new_sensor/state',hardware:{pin:4},
      simulated:{initial_value:25,min:0,max:120},
    });
    drawList(config.devices.length-1);
    msg('Dispositivo adicionado apenas ao rascunho. Ajuste ID, pino e campos antes de salvar.');
  });
  $('sqlDeleteDevice').addEventListener('click',()=>{
    if(selected<0 || !confirm('Excluir dispositivo do rascunho? Receitas e calibrações serão validadas.'))return;
    config.devices.splice(selected,1);drawList(Math.max(0,selected-1));
  });
  $('sqlDeviceForm').addEventListener('submit',event=>{
    event.preventDefault();
    if(selected<0)return;
    const d=config.devices[selected];
    const role=value('role');
    const hw={...(d.hardware||{}), pin:Number(value('pin'))};
    if (value('participation') && (!value('temperature_sensor')
      || (value('participation')==='auxiliary' && !value('controller_device')))) {
      msg('Selecione um sensor térmico; fonte auxiliar exige controlador PID por janela.');
      return;
    }
    if(value('driver')) hw.driver=value('driver'); else delete hw.driver;
    if(value('address')) hw.address=value('address'); else delete hw.address;
    if(value('window_seconds'))hw.window_seconds=Number(value('window_seconds'));else delete hw.window_seconds;
    if(!checked('active_high'))hw.active_high=false;else delete hw.active_high;
    if(checked('remote_control'))hw.remote_control=true;else delete hw.remote_control;
    if(value('participation')){
      hw.heating_source={
        participation:value('participation'),
        temperature_sensor:value('temperature_sensor'),
        controller_device:value('controller_device'),
        external_flame_cutoff:checked('external_flame_cutoff')
      };
      delete hw.window_seconds;delete hw.remote_control;
    }else delete hw.heating_source;
    const next={...d,id:value('id'),name:value('name'),role,
      subtype:value('subtype'),hardware:hw};
    if(role==='sensor'){
      next.state_topic=value('state_topic')||('sensors/'+next.id+'/state');
      delete next.command_topic;delete next.is_risk;
      delete next.failsafe_value;delete next.failsafe_timeout_seconds;
    }else{
      next.command_topic=value('command_topic')||('actuators/'+next.id+'/set');
      if(value('state_topic'))next.state_topic=value('state_topic');
      else delete next.state_topic;
      next.is_risk=checked('is_risk');
      next.failsafe_value=next.subtype==='pwm'?0:false;
      if(!next.is_risk)delete next.failsafe_timeout_seconds;
    }
    config.devices[selected]=next;drawList(selected);
    msg('Alteração em memória. Salve rascunho para validação completa.');
  });
  function updateSettings() {
    config.backend=$('sqlBackend').value;
    config.mqtt.enabled=$('sqlMqttEnabled').checked;
    config.mqtt.host=$('sqlMqttHost').value.trim();
    config.mqtt.port=Number($('sqlMqttPort').value);
    config.mqtt.topic_prefix=$('sqlMqttPrefix').value.trim();
    if($('sqlMqttPassword').value)config.mqtt.password=$('sqlMqttPassword').value;
    config.panel.port=Number($('sqlPanelPort').value);
  }
  $('sqlCreateDraft').addEventListener('click',async()=>{
    try{
      updateSettings();
      const out=await api('drafts','POST',config);
      pending=out.id;$('sqlApplyDraft').disabled=false;
      msg('Rascunho #'+pending+' aprovado na validação. Confirme para gravar a revisão operacional.');
    }catch(e){msg('Revisão rejeitada: '+e.message);}
  });
  $('sqlApplyDraft').addEventListener('click',async()=>{
    if(!pending || !confirm('Aprovar configuração para o próximo reinício? O processo atual não será modificado.'))return;
    try{
      const out=await api('drafts/'+pending+'/activate','POST');
      $('sqlApplyDraft').disabled=true;
      msg('Revisão '+out.revision+' aprovada. Reinicie SOMENTE com equipamento parado e saídas isoladas.');
    }catch(e){msg(e.message);}
  });
  $('sqlBackup').addEventListener('click',async()=>{
    try{
      const out=await api('backup','POST');
      const resp=await fetch('/api/admin/backup/'+encodeURIComponent(out.file),
        {headers:{'X-Bridge-Admin-Token':token}});
      if(!resp.ok)throw new Error('Não foi possível baixar backup.');
      const url=URL.createObjectURL(await resp.blob()),a=document.createElement('a');
      a.href=url;a.download=out.file;a.click();URL.revokeObjectURL(url);
      msg('Backup SQLite gerado: '+out.file);
    }catch(e){msg(e.message);}
  });

  // All diagnostics endpoints inherit the administrative token. These
  // controls never call /api/devices/.../command or a physical GPIO backend.
  const diagText = (id, message) => { $(id).textContent = message; };
  const diagRow = (parent, text, buttonLabel, handler) => {
    const line = document.createElement('div'); line.className='sql-diag-row';
    const title = document.createElement('span'); title.textContent=text;
    line.appendChild(title);
    if (buttonLabel) {
      const btn=document.createElement('button');btn.type='button';
      btn.textContent=buttonLabel;btn.addEventListener('click',handler);
      line.appendChild(btn);
    }
    parent.appendChild(line);
  };
  $('sqlScanTemp').addEventListener('click', async () => {
    try {
      const result=await api('diagnostics/temperature');
      const area=$('sqlScanResults'), list=$('sqlRomOptions');
      area.replaceChildren();list.replaceChildren();
      if (!result.sensors.length) {
        diagText('sqlScanResults',
          'Nenhum DS18B20 detectado. No Raspberry Pi habilite o overlay 1-Wire e verifique fiação/GPIO4.');
      }
      result.sensors.forEach(sensor=>{
        option(list,sensor.address,sensor.address);
        const reading=sensor.temperature_c === null
          ? (sensor.error || 'sem leitura')
          : Number(sensor.temperature_c).toFixed(2)+' °C';
        diagRow(area,sensor.address+' | '+reading+
          (sensor.device_id?' | '+sensor.device_id:' | não cadastrado'),
          'Usar ROM',()=>{
            if (selected < 0){msg('Selecione primeiro um dispositivo.');return;}
            f('address').value=sensor.address;
            msg('ROM '+sensor.address+' preenchido no rascunho. Clique em Atualizar no rascunho para aplicar.');
          });
      });
    }catch(e){diagText('sqlScanResults', e.message);}
  });
  $('sqlReadGpio').addEventListener('click', async () => {
    try{
      const data=await api('diagnostics/gpio');
      const area=$('sqlGpioResults');area.replaceChildren();
      data.devices.forEach(device=>{
        const val=device.value===null?'sem leitura':String(device.value);
        diagRow(area,'BCM '+device.pin+' | '+device.name+
          ' | '+val+(device.unit||'')+(device.risk?' | risco':''));
      });
      diagRow(area,data.notice);
      diagRow(area,data.analog);
      const pins=$('sqlVirtualPin');pins.replaceChildren();
      data.virtual_gpio.filter(pin=>!pin.assigned_to.length).forEach(pin=>{
        option(pins,pin.pin,'BCM '+pin.pin+' | virtual '+(pin.level?'HIGH':'LOW'));
      });
      const allow=data.virtual_write_enabled && pins.options.length>0;
      $('sqlVirtualOn').disabled=!allow;
      $('sqlVirtualOff').disabled=!allow;
      diagText('sqlVirtualStatus',data.virtual_write_enabled
        ? 'Teste exclusivamente em memória, sem acionar os pinos físicos.'
        : 'Acionamento virtual desativado: requer SIMULATION_ONLY=1.');
    }catch(e){diagText('sqlGpioResults',e.message);}
  });
  async function setVirtual(level) {
    const pin=Number($('sqlVirtualPin').value);
    if(!$('sqlVirtualPin').options.length){return;}
    try{
      const result=await api('diagnostics/gpio/virtual','POST',{pin,level});
      diagText('sqlVirtualStatus','GPIO BCM '+result.pin+': '+
        (result.level?'HIGH':'LOW')+' (SOMENTE VIRTUAL)');
      await $('sqlReadGpio').click();
    }catch(e){diagText('sqlVirtualStatus',e.message);}
  }
  $('sqlVirtualOn').addEventListener('click',()=>setVirtual(true));
  $('sqlVirtualOff').addEventListener('click',()=>setVirtual(false));
  $('sqlVirtualOn').disabled=true;
  $('sqlVirtualOff').disabled=true;
  $('sqlSerialPorts').addEventListener('click',async()=>{
    try{
      const data=await api('diagnostics/serial/ports');
      const select=$('sqlSerialPort');select.replaceChildren();
      data.ports.forEach(port=>option(select,port.device,port.device+' | '+port.description));
      diagText('sqlSerialOutput',data.message+
        (data.ports.length?'':' Nenhuma porta serial disponível.'));
    }catch(e){diagText('sqlSerialOutput',e.message);}
  });
  $('sqlSerialRead').addEventListener('click',async()=>{
    if(!$('sqlSerialPort').value){
      diagText('sqlSerialOutput','Liste e selecione uma porta serial primeiro.');return;
    }
    try{
      const result=await api('diagnostics/serial/read','POST',{
        port:$('sqlSerialPort').value, baudrate:Number($('sqlSerialBaud').value)
      });
      diagText('sqlSerialOutput',result.bytes_read+
        ' bytes (somente leitura):\n'+(result.text||'(sem dados no período de leitura)'));
    }catch(e){diagText('sqlSerialOutput',e.message);}
  });
  $('sqlAudit').addEventListener('click',async()=>{
    try{
      const out=await api('audit');
      $('sqlAuditText').textContent=JSON.stringify(out.events,null,2);
    }catch(e){msg(e.message);}
  });
})();
