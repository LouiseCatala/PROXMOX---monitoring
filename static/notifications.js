(() => {
  const q=s=>document.querySelector(s), storage='monitor-notifications-v1';
  let items=[],seen=new Set();
  try {
    const saved=JSON.parse(localStorage.getItem(storage)||'{}');
    if(Array.isArray(saved.items))items=saved.items.filter(i=>i&&typeof i.id==='string'&&typeof i.title==='string'&&typeof i.message==='string'&&['WARNING','CRITICAL','RECOVERED','TEST WARNING','TEST CRITICAL'].includes(i.level)&&Number.isFinite(Date.parse(i.at))).slice(0,100);
    if(Array.isArray(saved.seen))seen=new Set(saved.seen.filter(v=>typeof v==='string').slice(-1000));
  } catch {}
  function persist(){try{localStorage.setItem(storage,JSON.stringify({items,seen:[...seen].slice(-1000)}));}catch{}}
  function localTime(value){return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Manila',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(new Date(value));}
  function render(){
    const unread=items.filter(i=>!i.read).length;
    q('#notification-count').textContent=unread>99?'99+':unread;q('#notification-count').hidden=!unread;
    q('#notification-bell').setAttribute('aria-label',`Notifications, ${unread} unread`);
    const list=q('#notification-list');list.replaceChildren();
    if(!items.length){const empty=document.createElement('p');empty.className='notification-empty';empty.textContent='No alarm notifications yet. Warning, critical, offline and recovery events will appear here.';list.append(empty);return;}
    for(const item of items){
      const article=document.createElement('article');article.className='notification-item '+(item.read?'':'unread ')+(item.level.includes('CRITICAL')?'level-critical':item.level.includes('WARNING')?'level-warning':'level-recovered');
      const level=document.createElement('span');level.className='notification-level';level.textContent=item.level;
      const title=document.createElement('h3');title.textContent=item.title;
      const message=document.createElement('p');message.textContent=item.message;
      const meta=document.createElement('div');meta.className='notification-meta';
      const source=document.createElement('span');source.textContent=item.source;
      const timestamp=document.createElement('time');timestamp.dateTime=item.at;timestamp.textContent=localTime(item.at);meta.append(source,timestamp);
      article.append(level,title,message,meta);
      if(!item.read){const button=document.createElement('button');button.className='notification-read';button.textContent='Mark read';button.addEventListener('click',()=>{item.read=true;persist();render();});article.append(button);}
      list.append(article);
    }
  }
  function add(entries){
    const added=[];
    for(const entry of entries){if(seen.has(entry.id)||!Number.isFinite(Date.parse(entry.at)))continue;seen.add(entry.id);items.push({...entry,read:false});added.push(entry);}
    if(!added.length)return;
    items.sort((a,b)=>Date.parse(b.at)-Date.parse(a.at));items=items.slice(0,100);
    seen=new Set([...seen].slice(-1000));persist();render();
    q('#notification-announcement').textContent=`${added.length} new alarm notifications. ${added[added.length-1].title}`;
  }
  window.monitorNotifications={
    update(data){
      const entries=[];
      for(const event of data.alerts||[]){
        const recovered=event.state==='RECOVERED';
        if(!recovered&&!['WARNING','CRITICAL'].includes(event.severity))continue;
        entries.push({id:`${data.source}:alert:${event.id}`,source:data.source,at:event.checked_at,level:recovered?'RECOVERED':event.severity,title:event.node+' · '+String(event.resource).toUpperCase(),message:`${Number(event.value).toFixed(1)}% · ${event.previous_severity||'UNKNOWN'} → ${event.severity}. Recorded boundary: ${Number(event.threshold).toFixed(1)}%.`});
      }
      for(const event of data.events||[]){
        if(event.new_status==='UNAVAILABLE')entries.push({id:`${data.source}:availability:${event.id}`,source:data.source,at:event.checked_at,level:'CRITICAL',title:event.node+' · OFFLINE',message:'Three consecutive endpoint checks failed. Verify the agent, network and VM state in Proxmox.'});
        else if(event.new_status==='REACHABLE'&&['UNAVAILABLE','RETRYING'].includes(event.previous_status))entries.push({id:`${data.source}:availability:${event.id}`,source:data.source,at:event.checked_at,level:'RECOVERED',title:event.node+' · ENDPOINT RECOVERED',message:'The endpoint is responding with valid metrics again.'});
      }
      add(entries);
    },
    preview(level){add([{id:'preview:'+Date.now()+':'+Math.random(),source:'SOUND PREVIEW',at:new Date().toISOString(),level:'TEST '+level,title:level+' alarm sound test',message:'Sound preview only. No actual resource alarm or PostgreSQL event was created.'}]);}
  };
  function open(value){q('#notification-panel').hidden=!value;q('#notification-bell').setAttribute('aria-expanded',String(value));if(value)q('#close-notifications').focus();}
  q('#notification-bell').addEventListener('click',()=>open(q('#notification-panel').hidden));
  q('#close-notifications').addEventListener('click',()=>{open(false);q('#notification-bell').focus();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!q('#notification-panel').hidden){open(false);q('#notification-bell').focus();}});
  document.addEventListener('click',e=>{if(!q('#notification-panel').hidden&&!q('#notification-panel').contains(e.target)&&!q('#notification-bell').contains(e.target))open(false);});
  q('#mark-all-read').addEventListener('click',()=>{items.forEach(i=>i.read=true);persist();render();});
  q('#clear-notifications').addEventListener('click',()=>{items=[];persist();render();});
  render();
})();
