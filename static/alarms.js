(() => {
  const q = s => document.querySelector(s);
  let buffers={}, loading, clip, audio, enabled=false, active=null, acknowledged=null, lastPlayed=0, expiry;
  let saved={volume:35,repeat:15,pack:"funny"};
  try {const p=JSON.parse(localStorage.getItem('monitor-sound')||'{}');if(Number.isFinite(p.volume))saved.volume=Math.max(0,Math.min(100,p.volume));if([10,15,30,60].includes(p.repeat))saved.repeat=p.repeat;} catch {}
  function preferences(){try{localStorage.setItem('monitor-sound',JSON.stringify(saved));}catch{}}
  function describe(){
    const text=q('#alarm-status');text.className='';
    if(!enabled){text.textContent='Sound off. Click Enable alarm sound after opening this page.';return;}
    if(!active){text.textContent='Sound enabled · no fresh warning or critical metrics.';return;}
    text.className='active-'+active.level.toLowerCase();
    text.textContent=`${active.level}: ${active.names.join(', ')}${acknowledged===active.key?' · silenced until severity changes':' · repeating alarm'}`;
  }
  const dialog=q('#alarm-popup');
  let previousLevels=new Map(), activeItems=[];
  function closePopup(){if(dialog.open)dialog.close();}
  function popup(items, open){
    if(!items.length){closePopup();return;}
    const critical=items.some(i=>i.level==='CRITICAL');
    dialog.className=critical?'alarm-critical':'alarm-warning';
    q('#alarm-popup-level').textContent=critical?'CRITICAL ALERT':'WARNING ALERT';
    const list=q('#alarm-popup-items');list.replaceChildren();
    for(const item of items){
      const row=document.createElement('div');row.className='alarm-popup-item';
      const title=document.createElement('strong');title.textContent=item.name;
      const details=document.createElement('p');details.textContent=`${item.value.toFixed(1)}% · ${item.level}`;
      row.append(title,details);list.append(row);
    }
    q('#alarm-popup-audio').textContent=enabled?(acknowledged===active?.key?'Current alarm silenced.':'Alarm sound enabled.'):'Sound is off. Click Enable alarm sound to allow browser audio.';
    q('#popup-enable-sound').hidden=enabled;
    if(open&&!dialog.open)dialog.showModal();
  }
  for(const selector of ['#close-alarm-popup','#dismiss-alarm-popup'])q(selector).addEventListener('click',closePopup);
  q('#popup-enable-sound').addEventListener('click',()=>q('#enable-sound').click());
  q('#popup-silence').addEventListener('click',()=>{q('#ack-alarm').click();closePopup();});
  async function unlock(){
    const Audio=window.AudioContext||window.webkitAudioContext;
    if(!Audio)throw new Error('This browser does not support alarm audio.');
    audio ||= new Audio();await audio.resume();
    if(audio.state!=='running')throw new Error('Audio is blocked. Click again or check browser permissions.');
    if(saved.pack==='funny'&&(!buffers.WARNING||!buffers.CRITICAL)){
      loading ||= Promise.all(['WARNING','CRITICAL'].map(async level=>{
        const response=await fetch('/static/audio/'+level.toLowerCase()+'-funny.wav?v=sis35');
        if(!response.ok)throw new Error('Cannot load funny alarm files. Reinstall the update to restore the local audio files.');
        buffers[level]=await audio.decodeAudioData(await response.arrayBuffer());
      })).catch(error=>{loading=null;buffers={};throw error;});
      await loading;
    }
  }
  function tone(level){
    if(!audio||audio.state!=='running')return false;
    if(saved.pack==='funny'&&buffers[level]){
      stopClip();const source=audio.createBufferSource(),gain=audio.createGain();
      source.buffer=buffers[level];gain.gain.value=saved.volume/100;
      source.connect(gain);gain.connect(audio.destination);source.start();clip=source;
      source.onended=()=>{if(clip===source)clip=null;source.disconnect();gain.disconnect();};
      return true;
    }
    return false;
  }

  function stopClip(){if(clip){try{clip.stop();}catch{}clip=null;}}
  function maybePlay(force=false){
    if(!active||acknowledged===active.key)return;
    if(force||Date.now()-lastPlayed>=saved.repeat*1000){
      lastPlayed=Date.now();
      popup(activeItems,true);
      if(enabled&&!tone(active.level))q('#alarm-status').textContent='Audio paused by browser. Toggle Enable alarm sound to resume.';
    }
  }
  window.monitorAlarms={
    update(data){

      const warnings=[], critical=[];
      for(const card of data.cards){
        if(!Number.isFinite(card.age)||card.age>15||card.age < -5)continue;
        if(card.status==='UNAVAILABLE')continue;
        if(card.status!=='REACHABLE')continue;
        for(const [metric,value] of Object.entries(card.metrics)){
          if(!Number.isFinite(value.value))continue;
          const item={name:card.node+' / '+metric.toUpperCase(),level:value.severity,value:value.value,age:card.age};
          if(item.level==='CRITICAL')critical.push(item);else if(item.level==='WARNING')warnings.push(item);
        }
      }
      const items=[...critical,...warnings].sort((a,b)=>a.name.localeCompare(b.name));
      const next=items.length?{source:data.source,level:critical.length?'CRITICAL':'WARNING',names:items.map(i=>i.name),key:data.source+'|'+items.map(i=>i.name+':'+i.level).join('|')}:null;
      const currentLevels=new Map(items.map(item=>[item.name,item.level]));
      const newlyRaised=items.some(item=>previousLevels.get(item.name)!==item.level);
      previousLevels=currentLevels;activeItems=items;
      clearTimeout(expiry);
      if(items.length)expiry=setTimeout(()=>window.monitorAlarms.clear('Readings expired; waiting for fresh VM measurements.'),Math.max(0,15-Math.max(...items.map(i=>i.age)))*1000+20);
      const changed=next?.key!==active?.key;
      if(changed){stopClip();acknowledged=null;lastPlayed=0;}active=next;describe();maybePlay(changed);popup(items,false);
    },
    clear(message){clearTimeout(expiry);previousLevels=new Map();activeItems=[];closePopup();stopClip();active=null;acknowledged=null;lastPlayed=0;describe();if(enabled&&message)q('#alarm-status').textContent=message;}
  };
  q('#alarm-volume').value=saved.volume;
  q('#alarm-volume').addEventListener('input',e=>{saved.volume=Number(e.target.value);preferences();});
  q('#enable-sound').addEventListener('click',async()=>{
    try{if(enabled){stopClip();enabled=false;q('#enable-sound').textContent='Enable alarm sound';}else{await unlock();enabled=true;q('#enable-sound').textContent='Disable alarm sound';maybePlay(true);}describe();popup(activeItems,false);}
    catch(e){q('#alarm-status').textContent=e.message;}
  });
  q('#ack-alarm').addEventListener('click',()=>{stopClip();if(active)acknowledged=active.key;closePopup();describe();});
})();
