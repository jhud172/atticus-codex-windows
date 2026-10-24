(() => {
  const $=id=>document.getElementById(id), post=data=>window.webkit.messageHandlers.hub.postMessage(data);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let prefs={recordingLimit:300}, state={}, tab='history', query='', meeting={recording:false,message:''};
  const drafts=new Map();
  const time=value=>value?new Date(value).toLocaleString('en-GB'):'';
  const button=(text,action,id='',extra='')=>`<button data-action="${action}" data-id="${esc(id)}" ${extra}>${text}</button>`;
  const empty=text=>`<p class="empty">${text}</p>`;
  const field=(label,id,placeholder='',type='text')=>`<label for="${id}">${label}</label><input id="${id}" type="${type}" placeholder="${esc(placeholder)}">`;
  function render(){
    const previous=$('content').dataset.section, active=document.activeElement;
    if(previous){
      drafts.set(previous,{fields:Object.fromEntries([...$('content').querySelectorAll('input[id],textarea[id]')].map(f=>[f.id,f.value])),open:[...$('content').querySelectorAll('details')].map(d=>d.open)});
    }
    const focused=active?.matches('#content button[data-action]')?{action:active.dataset.action,id:active.dataset.id}:null;
    document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-current',b.dataset.tab===tab?'page':'false'));
    let html='';
    if(tab==='history') html=`<div class="search"><input id="search" aria-label="Search history" placeholder="Search questions and answers" value="${esc(query)}"><button data-action="search">Search</button></div>`+
      ((state.history||[]).map(h=>`<article class="card"><small>${esc(h.at)} · ${h.secs??'?'} s</small><h2>${esc(h.task)}</h2><pre>${esc(h.reply)}</pre>${(h.receipts||[]).map(r=>`<p><span class="badge">${esc(r.status)}</span> ${esc(r.action)} · ${esc(r.observation||r.details)}</p>`).join('')}${button('Ask again','ask','',`data-text="${esc(h.task)}"`)}</article>`).join('')||empty('Your completed conversations will appear here.'));
    if(tab==='workspaces') html=`<section><h2>Save a workspace</h2><p>Capture your current app windows, or define a layout. Restoring opens missing apps and checks their positions.</p>${field('Name','workspace-name','Study setup')}<div class="actions">${button('Capture current windows','workspace_capture')}</div><details><summary>Define or edit app entries</summary><p>Enter a JSON array. Screen names can be copied from a captured layout.</p><textarea id="workspace-entries" aria-label="Workspace entries">[{"app":"Notepad","where":"left"}]</textarea>${button('Save entries','workspace_save')}</details></section>`+
      ((state.workspaces||[]).map(w=>`<article class="card"><h2>${esc(w.name)}</h2><pre>${esc(JSON.stringify(w.entries,null,2))}</pre><div class="actions">${button('Restore and verify','workspace_restore',w.id)}${button('Remove','workspace_remove',w.id)}</div></article>`).join('')||empty('No saved workspaces yet.'));
    if(tab==='reminders') html=`<section><h2>Reminder or timer</h2>${field('What should I remind you about?','reminder-text','Take a break')}<div class="split"><div>${field('In minutes (timer)','reminder-minutes','10','number')}</div><div>${field('Or at a local date and time','reminder-time','','datetime-local')}</div></div><div class="actions">${button('Save reminder','reminder_add')}</div><p>Due reminders appear as notifications and remain in this list. If Atticus is closed, overdue reminders are delivered when it restarts.</p></section>`+
      ((state.reminders||[]).slice().reverse().map(r=>`<article class="card"><span class="badge">${esc(r.status)}</span><h2>${esc(r.text)}</h2><p>${esc(time(r.due))}</p><div class="actions">${button('Snooze 5 minutes','reminder_snooze',r.id)}${button('Cancel','reminder_cancel',r.id)}</div></article>`).join('')||empty('No reminders yet. Try “Remind me in 10 minutes to take a break”.'));
    if(tab==='projects') html=`<section><h2>Project access</h2><p>Choose specific folders. File edits require a preview and approval. Saved build commands run with your account access and require approval; they are not sandboxed to the folder.</p>${button('Add a project folder','project_grant')}</section>`+
      (state.projects||[]).map(p=>`<article class="card"><h2>${esc(p.name)}</h2><p>${esc(p.path)}</p><div class="actions">${button('List files','project_files',p.id)}${button('Revoke access','project_revoke',p.id)}</div>${(p.commands||[]).map(c=>`<div class="card"><b>${esc(c.name)}</b><pre>${esc(JSON.stringify(c.argv))}</pre>${button('Run in background','project_run',c.id,`data-project="${p.id}"`)}</div>`).join('')}<details><summary>Add a build or test command</summary>${field('Command name',`command-name-${p.id}`,'Build')}<label for="command-args-${p.id}">Executable and arguments as a JSON array</label><textarea id="command-args-${p.id}">["npm.cmd","run","build"]</textarea>${button('Save command','command_save',p.id)}</details></article>`).join('')+
      '<h2>File change previews</h2>'+((state.changes||[]).map(c=>`<article class="card"><span class="badge">${esc(c.status)}</span><h2>${esc(c.path)}</h2><pre>${esc(c.diff)}</pre>${c.status==='proposed'?`<div class="actions">${button('Apply reviewed change','project_apply',c.id)}${button('Reject','project_reject',c.id)}</div>`:''}</article>`).join('')||empty('Ask Atticus to read a project file and propose a change.'));
    if(tab==='jobs') html=`<section><h2>Background research</h2><p>Research runs without attaching your screens. If it needs a desktop action, an approval dialog may appear. Commands use the project grants above.</p><label for="job-prompt">Task</label><textarea id="job-prompt" placeholder="Research the official documentation and write a short comparison"></textarea><div class="actions">${button('Start task','background_start')}</div></section>`+
      ((state.jobs||[]).map(j=>`<article class="card"><span class="badge">${esc(j.status)}</span><h2>${esc(j.name)}</h2><small>${esc(time(j.created))}</small>${j.result?`<pre>${esc(j.result.details)}</pre>`:''}${j.output?`<details><summary>Command output</summary><pre>${esc(j.output)}</pre></details>`:''}${['queued','running'].includes(j.status)?button('Cancel task','job_cancel',j.id):''}</article>`).join('')||empty('No background tasks yet.'));
    if(tab==='meetings') html=`<section><h2>Meeting notes and audio transcription</h2><p>Recording is opt-in. Inform participants and follow the rules that apply to your meeting. System audio and your microphone are captured locally; no audio is sent to Codex. You may send the resulting transcript for a summary.</p><p class="${meeting.recording?'recording':''}" role="status">${esc(meeting.message||'Not recording')}</p><div class="actions">${button('Start recording','meeting_start')}${button('Stop and transcribe','meeting_stop')}${button('Cancel transcription','meeting_cancel')}${button('Transcribe an audio file','transcribe_file')}</div><label for="voice-limit">Voice request recording limit</label><select id="voice-limit"><option value="60">1 minute</option><option value="300" selected>5 minutes</option><option value="600">10 minutes</option><option value="1800">30 minutes</option></select>${button('Save voice limit','voice_limit')}</section>`+
      ((state.meetings||[]).map(m=>`<article class="card"><h2>${esc(m.title)}</h2><small>${esc(m.created)}</small><pre>${esc(m.transcript)}</pre>${button('Summarise in background with Codex','background_start','',`data-text="${esc('Summarise this meeting transcript with decisions and action items. Do not invent speakers or missing words.\n'+m.transcript)}"`)}</article>`).join('')||empty('No saved transcripts yet.'));
    if(tab==='extensions') html=`<section><h2>Custom MCP server</h2><p>Only add servers you trust. Each tool call asks for approval. Use token environment variable names, never paste a token here. Local commands run as your Windows user.</p>${field('Server name','mcp-name','my_server')}<label for="mcp-config">Server configuration</label><textarea id="mcp-config">{"url":"http://127.0.0.1:8080/mcp"}</textarea>${button('Add server','mcp_save')}</section>`+
      ((state.mcp||[]).map(m=>`<article class="card"><h2>${esc(m.name)}</h2><pre>${esc(JSON.stringify(m.config,null,2))}</pre>${button('Test tool discovery','mcp_tools',m.name)}${button('Remove server','mcp_remove',m.id)}</article>`).join('')||empty('No custom MCP servers connected.'));
    $('content').innerHTML=html;
    $('content').dataset.section=tab;
    const draft=drafts.get(tab);
    if(draft){for(const [id,value] of Object.entries(draft.fields)){if($(id))$(id).value=value;}[...$('content').querySelectorAll('details')].forEach((d,i)=>d.open=!!draft.open[i]);}
    if($('voice-limit'))$('voice-limit').value=String(prefs.recordingLimit||300);
    if(focused&&previous===tab)[...$('content').querySelectorAll('button[data-action]')].find(b=>b.dataset.action===focused.action&&b.dataset.id===focused.id)?.focus({preventScroll:true});
  }
  $('content').addEventListener('click',e=>{
    const b=e.target.closest('[data-action]');if(!b)return;const action=b.dataset.action,id=b.dataset.id;let r={action,id};
    try{
      if(action==='search'){query=$('search').value;r.query=query;}
      if(action==='ask')r.text=b.dataset.text;
      if(action.startsWith('workspace_')&&['workspace_capture','workspace_save'].includes(action)){r.name=$('workspace-name').value;if(!r.name)throw Error('Enter a workspace name.');if(action==='workspace_save')r.entries=JSON.parse($('workspace-entries').value);}
      if(action==='reminder_add'){r.text=$('reminder-text').value;const date=$('reminder-time').value;if(date)r.due=new Date(date).toISOString();else r.seconds=Number($('reminder-minutes').value)*60;}
      if(action==='project_files')r.project=id;
      if(action==='project_run'){r.project=b.dataset.project;r.command=id;}
      if(action==='command_save'){r.project=id;r.name=$(`command-name-${id}`).value;r.argv=JSON.parse($(`command-args-${id}`).value);}
      if(action==='background_start')r.prompt=b.dataset.text||$('job-prompt').value;
      if(action==='voice_limit')r.seconds=Number($('voice-limit').value);
      if(action==='mcp_tools')r.server=id;
      if(action==='mcp_save'){r.name=$('mcp-name').value;r.config=JSON.parse($('mcp-config').value);}
      post(r);
    }catch(error){window.hub.result(error.message,false);}
  });
  document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;post({action:'tab',tab});render();});
  $('refresh').onclick=()=>post({action:'ready'});
  window.hub={load(data,section,settings){state=data;prefs=settings||prefs;tab=section||tab;if(!document.querySelector('#content input:focus,#content textarea:focus,#content select:focus'))render();},list(value){$('listing').hidden=false;$('listing').open=true;$('listing-text').textContent=JSON.stringify(value,null,2);},result(message,ok){$('notice').textContent=message;$('notice').className=ok?'':'error';},meeting(value){meeting=value;if(tab==='meetings'&&!document.querySelector('#content input:focus,#content textarea:focus,#content select:focus'))render();}};
  post({action:'ready'});
})();
