/* Serial monitor presentation adapter. Authentication is supplied by the host api callback. */
window.mountBridgeSerialMonitor = function(api) {
  const $ = id => document.getElementById(id);
  const diagText = (id, value) => { $(id).textContent = value; };
  function option(select, value, label) {
    const node = document.createElement('option');
    node.value = value; node.textContent = label; select.appendChild(node);
  }
  $('sqlSerialPorts').addEventListener('click',async()=>{
    try{
      const data=await api('diagnostics/serial/ports');
      const select=$('sqlSerialPort');select.replaceChildren();
      data.ports.forEach(port=>option(select,port.device,port.device+' | '+port.description));
      diagText('sqlSerialStatus',data.message+
        (data.ports.length?'':' Nenhuma porta serial disponível.'));
    }catch(e){diagText('sqlSerialStatus',e.message);}
  });
  let serialSession = '', serialTimer = null, serialPending = false;
  const serialSettings = () => ({
    port: $('sqlSerialManual').value.trim() || $('sqlSerialPort').value,
    baudrate: Number($('sqlSerialBaud').value), bytesize: Number($('sqlSerialBits').value),
    parity: $('sqlSerialParity').value, stopbits: Number($('sqlSerialStopBits').value)
  });
  function serialButtons(active) {
    ['sqlSerialStart','sqlSerialTest','sqlSerialRead'].forEach(id => $(id).disabled = active || serialPending);
    $('sqlSerialStop').disabled = !active || serialPending;
  }
  function serialAppend(result) {
    const output = $('sqlSerialOutput');
    if (result.bytes_read) {
      const chunk = $('sqlSerialFormat').value === 'hex' ? result.hex + '\n' : result.text;
      output.textContent = (output.textContent + chunk).slice(-65536);
      output.scrollTop = output.scrollHeight;
    }
    $('sqlSerialStatus').textContent = result.bytes_read + ' bytes nesta leitura; somente leitura.';
  }
  async function stopSerial() {
    clearTimeout(serialTimer); serialTimer = null;
    const id = serialSession; serialSession = '';
    if (id) {
      serialPending = true; serialButtons(false);
      try { await api('diagnostics/serial/close','POST',{session:id}); }
      catch(e) { diagText('sqlSerialStatus', e.message + ' A conexão expira sem leituras.'); }
      finally { serialPending = false; serialButtons(false); }
    } else serialButtons(false);
  }
  async function pollSerial() {
    const id = serialSession;
    if (!id) return;
    try {
      const result = await api('diagnostics/serial/poll','POST',{session:id, limit:1024});
      if (serialSession !== id) return;
      serialAppend(result);
      serialTimer = setTimeout(pollSerial, 500);
    } catch(e) {
      diagText('sqlSerialStatus', e.message);
      await stopSerial();
    }
  }
  async function serialAction(action) {
    if(serialPending || serialSession) return;
    const settings = serialSettings();
    if(!settings.port){diagText('sqlSerialStatus','Selecione ou informe uma porta do servidor.');return;}
    if(!confirm('Abrir a porta pode reiniciar o microcontrolador. O equipamento está isolado e seguro?')) return;
    serialPending = true; serialButtons(false);
    try {
      if(action === 'read') {
        // The persistent API supports all configured serial parameters, even for one-shot reads.
        const opened = await api('diagnostics/serial/open','POST',settings);
        serialSession = opened.session;
        serialAppend(await api('diagnostics/serial/poll','POST',{session:serialSession,limit:1024}));
        serialPending = false; await stopSerial();
      } else if(action === 'test') {
        const result = await api('diagnostics/serial/test','POST',settings);
        diagText('sqlSerialStatus',result.message);
      } else {
        const opened = await api('diagnostics/serial/open','POST',settings);
        serialSession = opened.session;
        if (document.hidden) { serialPending = false; await stopSerial(); return; }
        diagText('sqlSerialStatus','Monitor conectado em '+opened.port+'.');
        serialTimer = setTimeout(pollSerial, 0);
      }
    } catch(e) {
      diagText('sqlSerialStatus',e.message);
      serialPending = false; await stopSerial();
    } finally {serialPending = false; serialButtons(Boolean(serialSession));}
  }
  $('sqlSerialRead').addEventListener('click',()=>serialAction('read'));
  $('sqlSerialTest').addEventListener('click',()=>serialAction('test'));
  $('sqlSerialStart').addEventListener('click',()=>serialAction('open'));
  $('sqlSerialStop').addEventListener('click',()=>stopSerial());
  $('sqlSerialClear').addEventListener('click',()=>diagText('sqlSerialOutput',''));
  // Do not keep the port open from a hidden tab. Server-side idle expiry is the fallback.
  document.addEventListener('visibilitychange',()=>{if(document.hidden) stopSerial();});
  window.addEventListener('pagehide',()=>stopSerial());
};
