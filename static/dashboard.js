const $ = s => document.querySelector(s);
const escapeHTML = v => String(v ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time = v => v ? new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Manila',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(new Date(v)) : '—';
const color = s => ({NORMAL:'green','LOW PRIORITY':'yellow',WARNING:'orange',CRITICAL:'red',REACHABLE:'green',RETRYING:'orange',UNAVAILABLE:'red','LOGGER STALE':'orange'}[s] || 'muted');
const badge = s => `<span class="badge ${color(s)}">${escapeHTML(s)}</span>`;
let data, selectedTab='readings', generation=0, timer, controller;
function plot(history) {
  const colors=['#117e70','#8547bd','#c36629'];
  const width=300,height=70;
  let svg='<svg class="plot" viewBox="0 0 300 70" preserveAspectRatio="none" role="img" aria-label="Recent CPU RAM and disk percentages from 0 to 100"><path d="M0 10H300 M0 35H300 M0 60H300" stroke="#c8c9c3" stroke-width=".5" fill="none"/>';
  ['cpu','ram','disk'].forEach((r,j)=>{
    let d='', prev=null;
    history.forEach((p,i)=>{
      const value=p[r];const valid=Number.isFinite(value);const now=new Date(p.checked_at).getTime();
      if(!valid){prev=null;return;}
      const x=history.length>1?i/(history.length-1)*width:width/2,y=height-5-value/100*(height-10);
      d+=`${prev!==null && now-prev<15000?'L':'M'}${x.toFixed(1)},${y.toFixed(1)} `;
      prev=now;
      if(history.length===1)svg+=`<circle cx="${x}" cy="${y}" r="2" fill="${colors[j]}"/>`;
    });
    svg+=`<path d="${d}" stroke="${colors[j]}" stroke-width="1.7" fill="none" vector-effect="non-scaling-stroke"/>`;
  });return svg+'</svg>';
}
function nodeMarkup(card,i) {
  let note=card.status==='LOGGER STALE'?'Logger has no recent saved check. Current node state is unknown.':card.status==='REACHABLE'?'Endpoint responded with valid metrics.':'No valid endpoint response. Confirm VM power state in Proxmox.';
  if(card.status==='NO DATA')note='Waiting for the first saved check.';
  return `<article class="node"><div class="node-main"><div class="node-title"><h3>${escapeHTML(card.node)}</h3><span class="node-number">0${i+1}</span></div><p class="ip">${escapeHTML(card.ip)} · :5123</p>${badge(card.status)}<div class="metrics">${['cpu','ram','disk'].map(r=>{
    const m=card.metrics[r];const level=m.severity||'NO READING';
    return `<div class="metric"><span class="metric-name">${r.toUpperCase()}</span><strong class="metric-value">${m.value===null?'—':m.value.toFixed(1)+'%'}</strong><span class="metric-level ${color(level)}">${escapeHTML(level)}</span><div class="meter"><i style="width:${m.value??0}%"></i></div></div>`;
  }).join('')}</div>${plot(card.history)}<div class="plot-caption"><span>Latest ${card.history.length} checks · 0–100%</span><div class="plot-legend"><span>CPU</span><span>RAM</span><span>DISK</span></div></div><p class="node-note">${note}</p></div><div class="node-foot">${[['Latest check',card.checked_at],['Last response',card.last_seen],['First failure',card.first_failure_at],['Last outage',card.last_outage_at],['Last recovery',card.recovery_at]].map(([label,v])=>`<div class="timing"><span>${label}</span><b>${time(v)}</b></div>`).join('')}<div class="timing"><span>Consecutive failures</span><b>${card.failures}</b></div></div></article>`;
}
const journalHeads=new Map();
function journal() {
  if(!data)return;
  const specs={
    alerts:{headers:['Event ID','Event timestamp','Node / metric','From','Severity','Status','Value','Boundary','Source'],rows:data.alerts.map(r=>[r.id,time(r.checked_at),`${escapeHTML(r.node)} / ${escapeHTML(r.resource.toUpperCase())}`,escapeHTML(r.previous_severity||'UNKNOWN'),badge(r.severity||'UNKNOWN'),escapeHTML(r.state),r.value.toFixed(1)+'%',r.threshold.toFixed(1)+'%',escapeHTML(data.source)])},
    events:{headers:['Event ID','Event timestamp','Node','Previous','Status','Severity','Last response','First failure','Recovery timestamp','Source'],rows:data.events.map(r=>[r.id,time(r.checked_at),escapeHTML(r.node),escapeHTML(r.previous_status),badge(r.new_status),badge(r.severity),time(r.last_seen),time(r.first_failure_at),time(r.recovery_at),escapeHTML(data.source)])},
    readings:{headers:['Reading ID','Event timestamp','Node','Status','CPU / severity','RAM / severity','Disk / severity','Failures','Source'],rows:data.readings.map(r=>[r.id,time(r.checked_at),escapeHTML(r.node),badge(r.status),...['cpu','ram','disk'].map(m=>r[m]===null?'—':r[m].toFixed(1)+'% · '+escapeHTML(r[m+'_severity'])),r.consecutive_failures,escapeHTML(data.source)])},
    metrics:{headers:['Event ID','Node name','Metric name','Metric value','Severity','Status','Event timestamp','Source'],rows:data.readings.flatMap(r=>['cpu','ram','disk'].map(m=>[r.id,escapeHTML(r.node),m.toUpperCase(),r[m]===null?'—':r[m].toFixed(1)+'%',badge(r[m+'_severity']||'NO READING'),badge(r.status),time(r.checked_at),escapeHTML(data.source)]))}
  };
  const spec=specs[selectedTab];
  const head=spec.rows.length?Number(spec.rows[0][0]):0;
  const previousHead=journalHeads.get(selectedTab);
  const newRows=previousHead===undefined?[]:spec.rows.filter(row=>Number(row[0])>previousHead);
  journalHeads.set(selectedTab,Math.max(previousHead||0,head));
  $('#history').innerHTML=spec.rows.length?`<table><thead><tr>${spec.headers.map(h=>`<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${spec.rows.map(r=>`<tr class="${newRows.includes(r)?'fresh-reading':''}">${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`:'<div class="empty">No saved records for this source yet.</div>';
  if(previousHead===undefined||newRows.length)$('#history').scrollTop=0;
  const label=selectedTab==='readings'?'checks':selectedTab==='metrics'?'metric rows':'events';
  $('#journal-live').textContent=`LIVE · ${newRows.length?newRows.length+' new '+label+' · ':''}Newest first · Updated ${time(data.server_time)}`;
  $('#history').setAttribute('aria-labelledby','tab-'+selectedTab);
  const names={alerts:'Severity transition',events:'Availability',readings:'Resource reading',metrics:'Metric + severity'};
  $('#record-title').textContent=names[selectedTab]+' records';
  $('#record-export').textContent='Download '+names[selectedTab].toLowerCase()+' CSV ↓';
  $('#record-export').href='/export/'+selectedTab+'?source='+encodeURIComponent($('#source').value);
}
function render() {
  $('#online').innerHTML=data.cards.filter(c=>c.status==='REACHABLE').length+' <span>/ 3</span>';
  $('#count').textContent=data.count.toLocaleString();
  $('#critical').textContent=data.cards.filter(c=>c.status==='REACHABLE').reduce((n,c)=>n+Object.values(c.metrics).filter(m=>m.severity==='CRITICAL').length,0);
  $('#nodes').innerHTML=data.cards.map(nodeMarkup).join('');journal();window.monitorNotifications.update(data);window.monitorAlarms.update(data);
  $('#notice').hidden=true;
  $('#sync').textContent='Updated '+time(data.server_time);
}
function exportLinks(){$('#record-export').href='/export/'+selectedTab+'?source='+encodeURIComponent($('#source').value);}
async function poll(gen) {
  controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),12000);
  try {
    const response=await fetch('/api/dashboard?source='+encodeURIComponent($('#source').value),{cache:'no-store',signal:controller.signal});
    const next=await response.json();if(!response.ok)throw new Error(next.error||'Cannot read history.');
    if(gen!==generation)return;data=next;render();
  }catch(e){if(gen!==generation)return;$('#sync').textContent='Connection unavailable';$('#notice').hidden=false;$('#notice').textContent=(e.name==='AbortError'?'Dashboard request timed out.':e.message)+' Displayed values may be stale; current state is unknown.';window.monitorAlarms.clear('Dashboard connection unavailable; no sound from stale values.');$('#online').textContent='Unknown';$('#critical').textContent='Unknown';}
  finally{clearTimeout(timeout);if(gen===generation)timer=setTimeout(()=>poll(gen),5000);}
}
$('#source').addEventListener('change',()=>{window.monitorAlarms.clear('Data source changed; waiting for fresh checks.');generation++;clearTimeout(timer);controller?.abort();data=null;journalHeads.clear();$('#nodes').innerHTML='<div class="loading">Loading selected source…</div>';$('#history').innerHTML='';$('#online').textContent='—';$('#count').textContent='—';$('#critical').textContent='—';exportLinks();poll(generation);});
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{selectedTab=b.dataset.tab;document.querySelectorAll('[data-tab]').forEach(x=>{const active=x===b;x.classList.toggle('selected',active);x.setAttribute('aria-selected',String(active));});journal();}));
exportLinks();poll(generation);

// Sidebar follows the section in view without reloading the dashboard.
const sectionObserver=new IntersectionObserver(entries=>{const current=entries.filter(e=>e.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];if(current)document.querySelectorAll('.rail .nav').forEach(a=>a.classList.toggle('active',a.hash==='#'+current.target.id));},{rootMargin:'-10% 0px -50% 0px',threshold:[0,.2,.5]});document.querySelectorAll('main > section[id]').forEach(s=>sectionObserver.observe(s));
