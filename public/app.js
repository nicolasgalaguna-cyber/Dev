'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
let state=null, busy=false, noticeTimer, mic=null, selected=new Set(), dossierTrack='';
const escapeText=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time=s=>`${Math.floor((s||0)/60).toString().padStart(2,'0')}:${Math.floor((s||0)%60).toString().padStart(2,'0')}`;
function notice(message){$('#notice').textContent=message;$('#notice').classList.add('visible');clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('#notice').classList.remove('visible'),6000);}
function login(){if(!$('#login').open)$('#login').showModal();}
async function api(path,data,options={}){
  const r=await fetch('/api/'+path,{...options,method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Radio-Request':'1',...options.headers},body:data===undefined?undefined:JSON.stringify(data)});
  const body=await r.json();if(!r.ok){if(r.status===401)login();throw Error(body.error||'Solicitud fallida');}return body;
}
async function action(path,data){try{const r=await api(path,data);await refresh();return r;}catch(e){notice(e.message);return null;}}
function options(select,tracks,placeholder){const value=select.value;select.replaceChildren();if(placeholder){const o=new Option(placeholder,'');select.add(o);}for(const t of tracks)select.add(new Option(t.name||`${t.title} — ${t.artist}`,t.id));if([...select.options].some(o=>o.value===value))select.value=value;}
let fingerprint='';
function renderLibrary(){
 const st=state.station, print=JSON.stringify([st.tracks,st.playlists,st.schedules,st.active_playlist,st.history]);
 if(print===fingerprint)return;fingerprint=print;
 $('#track-count').textContent=`${st.tracks.length} PISTAS`;
 $('#tracks').innerHTML=st.tracks.map(t=>`<tr><td><input type="checkbox" data-select="${t.id}" ${selected.has(t.id)?'checked':''} aria-label="Elegir ${escapeText(t.title)}"></td><td>${escapeText(t.title)} <small>${escapeText(t.artist)} · ${t.kind==='jingle'?'JINGLE':'MÚSICA'}</small></td><td>${time(t.duration)}</td><td><button data-load="${t.id}" data-target="0">A</button> <button data-load="${t.id}" data-target="1">B</button></td></tr>`).join('')||'<tr><td colspan="4">Tu biblioteca está vacía. Importa audio o ejecuta la carga de demostración.</td></tr>';
 options($('#active-playlist'),st.playlists,'Biblioteca musical completa');$('#active-playlist').value=st.active_playlist||'';
 options($('#schedule-playlist'),st.playlists,'Elige una lista');options($('#research-track'),st.tracks,'Elige una canción');
 $('#jingles').innerHTML=st.tracks.filter(t=>t.kind==='jingle').map(t=>`<button data-jingle="${t.id}">↗ ${escapeText(t.title)}</button>`).join('')||'<p class="subtle">Importa jingles en la biblioteca.</p>';
 const p=st.playlists.find(x=>x.id===st.active_playlist), ids=p?p.tracks:st.tracks.filter(t=>t.kind==='music').map(t=>t.id);
 $('#queue-list').innerHTML=ids.slice(0,6).map(id=>`<li>${escapeText(st.tracks.find(t=>t.id===id)?.title||'Pista')}</li>`).join('')||'<p class="subtle">No hay pistas en rotación.</p>';
 $('#schedule-list').innerHTML=st.schedules.map(s=>`<div class="schedule-item"><div><strong>${escapeText(s.name)}</strong><small>${s.days.map(d=>['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'][d]).join(' · ')} / ${time(s.start*60)}–${time(s.end*60)}<br>${escapeText(st.playlists.find(p=>p.id===s.playlist)?.name)} · prioridad ${s.priority}</small></div><button data-delete-schedule="${s.id}" aria-label="Eliminar bloque ${escapeText(s.name)}">×</button></div>`).join('')||'<p class="subtle">Sin bloques: se usa la lista base.</p>';
 $('#history').innerHTML=st.history.slice(-6).reverse().map(h=>`<div class="history-row">${escapeText(h.title)} <small>${new Date(h.ended*1000).toLocaleString('es-CO')}</small></div>`).join('')||'<p class="subtle">Las pistas completadas aparecerán aquí.</p>';
}
function safeLink(url){try{const u=new URL(url);return u.protocol==='https:'?u.href:'#';}catch{return '#';}}
function sources(el,items){el.replaceChildren();for(const c of items){const a=document.createElement('a');a.href=safeLink(c.url);a.textContent=c.title||c.url;a.target='_blank';a.rel='noopener noreferrer';a.className='source';el.append(a);}}
function renderDossier(force=false){
 const id=$('#research-track').value;if(!force&&id===dossierTrack)return;dossierTrack=id;
 const d=state.station.dossiers[id]||{}, research=d.research;
 $('#research-result').textContent=research?`BORRADOR / REQUIERE CONTRASTE\n\n${research.text}`:'Aún no hay investigación para esta canción. Puedes añadir afirmaciones revisadas sin usar IA.';
 sources($('#sources'),research?.citations||[]);
 $('#claims').innerHTML=(d.claims||[]).map(c=>`<div class="claim"><strong>${c.kind==='interpretation'?'INTERPRETACIÓN':'REVISIÓN EDITORIAL'}</strong>${escapeText(c.text)}<small>Revisó: ${escapeText(c.reviewer)}</small><a class="source" target="_blank" rel="noopener noreferrer" href="${escapeText(safeLink(c.url))}">Consultar fuente ↗</a></div>`).join('');
}
async function refresh(){
 if(busy)return;busy=true;
 try{
 state=await api('state');$('#login').close();const a=state.audio;
 $('#connection').textContent='● Servidor conectado';$('#air').classList.toggle('on',a.running);$('#air').textContent=a.running?'● EMISIÓN ACTIVA':'● FUERA DEL AIRE';
 if(document.activeElement!==$('#autodj'))$('#autodj').checked=a.autodj;
 if(document.activeElement!==$('#fade'))$('#fade').value=a.crossfade;
 $('#level').value=a.peak;$('#live-state').textContent=a.live?'● MIC AL AIRE':'MIC CERRADO';
 a.decks.forEach((d,i)=>{const el=$('#deck'+i);el.querySelector('.track-title').textContent=d?.track.title||'Esperando una pista';el.querySelector('.track-artist').textContent=d?.track.artist||'La siguiente historia está por llegar';el.querySelector('.deck-state').textContent=d?(a.running&&d.playing?'REPRODUCIENDO':'PREPARADO'):'EN ESPERA';el.querySelector('.position').textContent=time(d?.position);el.querySelector('.duration').textContent=time(d?.duration);el.querySelector('progress').value=d?d.position/d.duration:0;});
 $('#events').replaceChildren(...a.events.map(e=>{const p=document.createElement('div');p.textContent=`${new Date(e.time*1000).toLocaleTimeString('es-CO')} / ${e.message}`;return p;}));
 $('#ai-status').textContent=state.capabilities.ai?'Investigación web disponible. Se cobra en tu cuenta de API.':'IA sin configurar. La revisión editorial y los guiones locales están disponibles.';
 renderLibrary();renderDossier();
 }catch(e){$('#connection').textContent='Sin conexión';if(!$('#login').open)notice(e.message);}finally{busy=false;}
}
$('#login-form').onsubmit=async e=>{e.preventDefault();try{await api('login',{token:new FormData(e.target).get('token')});e.target.reset();$('#login-error').textContent='';await refresh();}catch(err){$('#login-error').textContent=err.message;}};
$('#login').addEventListener('cancel',e=>e.preventDefault());
$('#logout').onclick=async()=>{await stopMic();await action('logout',{});login();};
$('#start').onclick=()=>action('transport',{action:'start'});$('#stop').onclick=()=>action('transport',{action:'stop'});$('#skip').onclick=()=>action('transport',{action:'skip'});
$('#autodj').onchange=e=>action('transport',{action:'settings',autodj:e.target.checked});$('#fade').onchange=e=>action('transport',{action:'settings',crossfade:Number(e.target.value)});
$('#master').onchange=e=>action('transport',{action:'settings',master:Number(e.target.value)});$('#crossfader').onchange=e=>action('transport',{action:'settings',manual_mix:Number(e.target.value)});
$('#active-playlist').onchange=e=>{action('playlist/activate',{id:e.target.value||null});};
$('#listen').onclick=async()=>{const a=$('#air-audio');if(a.paused){a.src='/stream.wav';a.hidden=false;try{await a.play();}catch(e){notice(e.message);}}else{a.pause();a.hidden=true;a.removeAttribute('src');a.load();}};
$('#air-audio').onerror=()=>{if($('#air-audio').getAttribute('src'))notice('No se pudo reproducir el monitor. Puedes usar VLC con /stream.wav.');};
$('#upload-form').onsubmit=async e=>{e.preventDefault();const form=e.target, data=new FormData(form), file=data.get('file'), btn=form.querySelector('button');btn.disabled=true;btn.textContent='Importando…';try{const r=await fetch('/api/upload',{method:'POST',headers:{'X-Radio-Request':'1','X-Title':encodeURIComponent(data.get('title')),'X-Artist':encodeURIComponent(data.get('artist')),'X-Kind':data.get('kind'),'Content-Type':'application/octet-stream'},body:file});const v=await r.json();if(!r.ok)throw Error(v.error);form.reset();await refresh();notice('Audio importado');}catch(err){notice(err.message);}finally{btn.disabled=false;btn.textContent='↑ Añadir a la biblioteca';}};
$('#playlist-form').onsubmit=async e=>{e.preventDefault();const tracks=state.station.tracks.filter(t=>selected.has(t.id)).map(t=>t.id);if(await action('playlists',{name:new FormData(e.target).get('name'),tracks})){selected.clear();fingerprint='';e.target.reset();await refresh();}};
$('#schedule-form').onsubmit=async e=>{e.preventDefault();const d=new FormData(e.target), mins=v=>{const [h,m]=v.split(':').map(Number);return h*60+m;};await action('schedules',{name:d.get('name'),playlist:d.get('playlist'),days:d.getAll('days').map(Number),start:mins(d.get('start')),end:mins(d.get('end')),priority:Number(d.get('priority'))});};
$('#research-track').onchange=()=>{renderDossier(true);$('#script-output').value='';sources($('#script-sources'),[]);};
$('#research').onclick=async e=>{if(!$('#research-track').value)return notice('Elige una canción');const btn=e.target;btn.disabled=true;btn.textContent='Investigando fuentes…';const result=await action('research',{track:$('#research-track').value});if(result)renderDossier(true);btn.disabled=false;btn.textContent='✳ Investigar con fuentes';};
$('#claim-form').onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));if(await action('claim',{track:$('#research-track').value,claim:d})){e.target.reset();renderDossier(true);notice('Revisión editorial registrada');}};
$('#generate').onclick=async()=>{const result=await action('script',{track:$('#research-track').value,seconds:Number($('#script-seconds').value)});if(result){$('#script-output').value=result.text;sources($('#script-sources'),result.sources.map(url=>({url})));}};
$('#copy-script').onclick=async()=>{try{await navigator.clipboard.writeText($('#script-output').value);notice('Guion copiado');}catch{notice('Selecciona y copia el guion manualmente');}};
document.addEventListener('change',e=>{if(e.target.dataset.select){if(e.target.checked)selected.add(e.target.dataset.select);else selected.delete(e.target.dataset.select);}if(e.target.dataset.gain)action('deck',{deck:Number(e.target.dataset.gain),action:'gain',value:Number(e.target.value)});});
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;const d=b.dataset;if(d.deck)await action('deck',{deck:Number(d.deck),action:d.action});if(d.load)await action('deck',{deck:Number(d.target),track:d.load,action:'load'});if(d.jingle)await action('jingle',{track:d.jingle});if(d.deleteSchedule)await action('schedule/delete',{id:d.deleteSchedule});if(d.monitor){const track=state?.audio.decks[Number(d.monitor)]?.track;if(!track)return notice('Deck vacío');const a=$('#cue-audio');a.src='/media/'+track.id;a.hidden=false;a.play().catch(err=>notice(err.message));}});
async function stopMic(){const m=mic;mic=null;if(m){m.node.port.onmessage=null;m.source.disconnect();m.node.disconnect();m.stream.getTracks().forEach(t=>t.stop());await m.context.close();try{await api('live/release',{});}catch{}}$('#mic').textContent='♩ Abrir micrófono';$('#mic').classList.remove('open');}
$('#mic').onclick=async()=>{if(mic)return stopMic();let stream, context;try{if(!window.isSecureContext||!navigator.mediaDevices)throw Error('El micrófono requiere HTTPS o localhost');stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,channelCount:1}});context=new AudioContext();await context.audioWorklet.addModule('/mic-worklet.js');await api('live/acquire',{});const source=context.createMediaStreamSource(stream), node=new AudioWorkletNode(context,'radio-mic');const mute=context.createGain();mute.gain.value=0;source.connect(node);node.connect(mute).connect(context.destination);mic={stream,context,node,source};let pending=false;node.port.onmessage=async e=>{if(!mic)return;if(pending){notice('Conexión lenta: cerrando micrófono');return stopMic();}pending=true;try{const r=await fetch('/api/live/chunk',{method:'POST',headers:{'X-Radio-Request':'1','Content-Type':'application/octet-stream'},body:e.data});if(!r.ok)throw Error('Se perdió la concesión de micrófono');}catch(err){notice(err.message);await stopMic();}finally{pending=false;}};await context.resume();$('#mic').textContent='■ Cerrar micrófono';$('#mic').classList.add('open');}catch(err){stream?.getTracks().forEach(t=>t.stop());if(context&&context.state!=='closed')await context.close();notice(err.message);}};
window.addEventListener('pagehide',()=>{mic?.stream.getTracks().forEach(t=>t.stop());});
for(const [index,wave] of $$('.wave').entries()){for(let i=0;i<68;i++){const bar=document.createElement('i');bar.style.height=`${10+Math.abs(Math.sin(i*1.4+index)*Math.cos(i*.31))*80}%`;wave.append(bar);}wave.title='Gráfico decorativo; el medidor master muestra el nivel real';}
setInterval(()=>{$('#clock').textContent=new Date().toLocaleTimeString('es-CO',{timeZone:'America/Bogota',hour12:false});},1000);
$$('nav a').forEach(a=>a.onclick=()=>{$$('nav a').forEach(x=>x.classList.remove('active'));a.classList.add('active');});
refresh();setInterval(refresh,1500);
