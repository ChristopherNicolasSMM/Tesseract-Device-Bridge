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
  $('sqlAudit').addEventListener('click',async()=>{
    try{
      const out=await api('audit');
      $('sqlAuditText').textContent=JSON.stringify(out.events,null,2);
    }catch(e){msg(e.message);}
  });
})();
