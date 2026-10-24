"""Local workspaces, reminders, reviewed project tools and supervised jobs.

All runtime state lives outside the repository. Folder and command grants can
only be created by the native control centre, never by an AI tool call.
"""
import contextlib
import difflib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import urllib.parse
from datetime import datetime, timedelta, timezone


def root():
    return Path(os.environ.get('ATTICUS_DIR') or Path(os.environ.get('APPDATA', Path.home())) / 'Atticus')


def identifier():
    return uuid.uuid4().hex[:16]


def now():
    return datetime.now(timezone.utc)


def stamp():
    return now().isoformat()


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.atticus-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextlib.contextmanager
def database():
    folder = root()
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'assistant.lock').open('a+b') as lock:
        # Reading a byte already locked by another Windows process raises EACCES
        # before our bounded lock retry can run. Inspect file metadata instead.
        if os.fstat(lock.fileno()).st_size == 0:
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            # Bounded retry, including when the native UI polls during a write.
            for attempt in range(100):
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if attempt == 99: raise
                    time.sleep(.03)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            path = folder / 'assistant.json'
            data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            original = json.dumps(data, sort_keys=True)
            for name in ('reminders', 'workspaces', 'projects', 'changes', 'jobs', 'mcp'):
                data.setdefault(name, [])
            yield data
            if json.dumps(data, sort_keys=True) != original: atomic(path, data)
        finally:
            lock.seek(0)
            if os.name == 'nt': msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(lock, fcntl.LOCK_UN)


def row(rows, key):
    found = next((r for r in rows if r['id'] == key or r.get('name', '').casefold() == str(key).casefold()), None)
    if found is None: raise ValueError('That item no longer exists. Refresh the control centre.')
    return found


def receipt(status, details, **data):
    return {'status': status, 'details': details, **data}


def history(query='', limit=150):
    records = []
    path = root() / 'log.jsonl'
    if path.exists():
        with path.open(encoding='utf-8') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    if query.casefold() in (str(item.get('task', '')) + ' ' + str(item.get('reply', ''))).casefold():
                        records.append({k: item.get(k) for k in ('at', 'task', 'reply', 'secs', 'provider', 'ran', 'receipts')})
                except ValueError: pass
    return records[-limit:][::-1]


DENIED_PARTS = {'.git', '.ssh', '.aws', '.azure', '.codex', '.codex-runtime', '.mcp-auth', '.claude', 'node_modules', '.venv'}
DENIED_FILES = {'auth.json', 'credentials', 'credentials.json', 'secrets.json', 'id_rsa', 'id_ed25519'}


def project_path(project, relative, allow_new=False):
    base = Path(project['path']).resolve(strict=True)
    requested = Path(relative)
    if requested.is_absolute() or '..' in requested.parts:
        raise ValueError('Use a relative path inside the approved project folder.')
    if any(p.casefold() in DENIED_PARTS for p in requested.parts):
        raise ValueError('Dependency, credential and source-control internals are excluded.')
    if re.search(r'(^|\.)env(\.|$)',requested.name,re.I) or requested.name.casefold() in DENIED_FILES or requested.suffix.lower() in ('.key', '.pem', '.pfx', '.p12'):
        raise ValueError('Credential files are excluded from project tools.')
    target = (base / requested).resolve(strict=not allow_new)
    if not target.is_relative_to(base) or target == base:
        raise ValueError('The path leaves the approved project folder.')
    # Also check the resolved path: an innocently named symlink cannot expose credentials.
    parts = target.relative_to(base).parts
    if any(p.casefold() in DENIED_PARTS for p in parts) or re.search(r'(^|\.)env(\.|$)',target.name,re.I) or target.name.casefold() in DENIED_FILES or target.suffix.lower() in ('.key','.pem','.pfx','.p12'):
        raise ValueError('The resolved file is excluded from project tools.')
    return target


def text_file(path):
    if path.stat().st_size > 2_000_000: raise ValueError('Read a smaller text file (maximum 2 MB).')
    data = path.read_bytes()
    if b'\0' in data: raise ValueError('This is not a supported text file.')
    return data.decode('utf-8-sig'), hashlib.sha256(data).hexdigest()


def grant_project(data, name, path):
    target = Path(path).resolve(strict=True)
    if not target.is_dir() or target.parent == target or target == Path.home():
        raise ValueError('Choose one project folder, rather than a drive or the entire user profile.')
    existing = next((p for p in data['projects'] if p['path'] == str(target)), None)
    if existing: return existing
    item = {'id': identifier(), 'name': str(name or target.name)[:80], 'path': str(target), 'commands': []}
    data['projects'].append(item)
    return item


def parse_due(request):
    if 'seconds' in request:
        seconds = float(request['seconds'])
        if not math.isfinite(seconds) or seconds < 1 or seconds > 31536000: raise ValueError('Choose a delay between one second and one year.')
        return now() + timedelta(seconds=seconds)
    value = datetime.fromisoformat(str(request['due']).replace('Z', '+00:00'))
    if value.tzinfo is None: value = value.astimezone()
    if value <= now(): raise ValueError('Choose a future reminder time.')
    return value.astimezone(timezone.utc)


def create_job(data, kind, request):
    item = {'id': identifier(), 'kind': kind, 'name': str(request.get('name') or request.get('prompt') or kind)[:120],
            'status': 'queued', 'created': stamp(), 'request': request}
    data['jobs'].append(item)
    return item


def launch_job(job):
    folder = root() / 'jobs' / job['id']
    folder.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith('ATTICUS_')}
    env.update(ATTICUS_DIR=str(root()), PYTHONUTF8='1')
    with (folder / 'worker.log').open('ab') as log:
        proc = subprocess.Popen([sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), '--job-worker', job['id']],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env,
                                creationflags=0x08000000 if os.name == 'nt' else 0)
    return proc.pid


def update_job(key, **values):
    with database() as data:
        item = row(data['jobs'], key)
        if item['status'] == 'cancelled' and values.get('status') not in (None, 'cancelled'): return
        item.update(values)


def cancel_process(pid, started=None):
    import psutil
    try:
        proc = psutil.Process(int(pid))
        if started is not None and abs(proc.create_time() - float(started)) > 1: return
        for child in proc.children(recursive=True):
            try: child.kill()
            except psutil.Error: pass
        proc.kill()
    except psutil.Error: pass


def job_worker(key):
    import psutil
    with database() as data:
        item = dict(row(data['jobs'], key))
        if item['status'] != 'queued': return
        project = dict(row(data['projects'], item['request']['project'])) if item['kind'] == 'command' else None
        row(data['jobs'], key).update(status='running', pid=os.getpid(), processStarted=psutil.Process().create_time(), started=stamp())
    try:
        if item['kind'] == 'command':
            command = row(project['commands'], item['request']['command'])
            folder = root() / 'jobs' / key
            with (folder / 'output.log').open('wb') as output:
                process = subprocess.Popen(command['argv'], cwd=project['path'], stdout=output, stderr=subprocess.STDOUT,
                                           stdin=subprocess.DEVNULL, creationflags=0x08000000 if os.name == 'nt' else 0)
                try: code = process.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    cancel_process(process.pid)
                    raise RuntimeError('Command exceeded 30 minutes and was stopped.')
            result = receipt('verified' if code == 0 else 'failed', f'Command exited with code {code}.', exitCode=code)
        else:
            import atticus
            # No screen capture or unrelated context is attached to a background research request.
            answer, _, _ = atticus.run(item['request']['prompt'])
            result = receipt('completed' if atticus.run.ok else 'failed', answer)
        update_job(key, status='completed' if result['status'] in ('verified', 'completed') else 'failed', result=result, ended=stamp())
    except Exception as error:
        update_job(key, status='failed', result=receipt('failed', str(error)), ended=stamp())


def workspace_capture(name, brain):
    entries = []
    monitors = brain.winctl.monitors()
    for window in brain.winctl.windows():
        if 'atticus' in str(window.get('proc', '')).casefold(): continue
        x, y, w, h = brain.winctl.frame(window['hwnd'])
        if w < 250 or h < 150: continue
        monitor = next((m for m in monitors if m['x'] <= x + w / 2 < m['x'] + m['w'] and m['y'] <= y + h / 2 < m['y'] + m['h']), monitors[0])
        mx,my,mw,mh = monitor['work']
        entries.append({'app': window['app'], 'title': window['title'], 'screen': monitor['name'],
                        'rect': [(x-mx)/mw, (y-my)/mh, w/mw, h/mh]})
        if len(entries) >= 16: break
    if not entries: raise ValueError('No usable application windows were found.')
    return {'id': identifier(), 'name': str(name)[:80], 'entries': entries}


def workspace_restore(item, brain):
    monitors = brain.winctl.monitors()
    results = []
    for entry in item['entries']:
        windows = brain.winctl.find(entry['app'], entry.get('title', '')) or brain.winctl.find(entry['app'])
        if not windows:
            brain.winctl.launch(entry['app'])
            for _ in range(20):
                time.sleep(.2)
                windows = brain.winctl.find(entry['app'])
                if windows: break
        if not windows:
            results.append(receipt('failed', 'Could not find ' + entry['app'])); continue
        monitor = next((m for m in monitors if m['name'] == entry.get('screen')), monitors[0])
        rx, ry, rw, rh = entry.get('rect', [0, 0, .5, 1])
        mx,my,mw,mh = monitor['work']
        w, h = min(mw, max(250, int(rw*mw))), min(mh, max(150, int(rh*mh)))
        x = mx + max(0, min(mw-w, int(rx*mw)))
        y = my + max(0, min(mh-h, int(ry*mh)))
        hwnd = windows[0]['hwnd']
        brain.winctl.set_frame(hwnd, x, y, w, h)
        time.sleep(.15)
        actual = brain.winctl.frame(hwnd)
        ok = all(abs(a-b) <= 16 for a,b in zip(actual, (x,y,w,h)))
        results.append(receipt('verified' if ok else 'unverified', entry['app']))
    return receipt('verified' if all(r['status']=='verified' for r in results) else 'needs_attention', 'Workspace restore checked against actual window positions.', windows=results)


def public_state(data, query=''):
    jobs = []
    for item in data['jobs'][-100:][::-1]:
        shown = {k: v for k,v in item.items() if k not in ('request', 'pid', 'processStarted')}
        logfile = root() / 'jobs' / item['id'] / 'output.log'
        if logfile.exists():
            with logfile.open('rb') as f:
                f.seek(max(0, logfile.stat().st_size-12000)); shown['output'] = f.read().decode('utf-8', 'replace')
        jobs.append(shown)
    meetings = []
    folder = root() / 'meetings'
    if folder.exists():
        for p in sorted(folder.glob('*.json'), reverse=True)[:50]:
            try: meetings.append(json.loads(p.read_text(encoding='utf-8')))
            except ValueError: pass
    return {'reminders': data['reminders'], 'workspaces': data['workspaces'], 'projects': data['projects'],
            'changes': [{k:v for k,v in c.items() if k!='content'} for c in data['changes'][-50:][::-1]], 'jobs': jobs, 'mcp': data['mcp'],
            'history': history(query), 'meetings': meetings, 'setup': setup_preview() if (root()/'pending-setup.json').exists() else None}


READ_ACTIONS = {'state', 'history', 'project_list', 'project_read', 'project_files', 'job_status', 'mcp_tools'}
TRUSTED_ACTIONS = {'project_grant', 'project_revoke', 'command_save', 'mcp_save', 'mcp_remove', 'recover', 'tick', 'setup_preview', 'setup_apply'}
SUPPORTED_ACTIONS = READ_ACTIONS | TRUSTED_ACTIONS | {'project_preview','project_apply','project_reject','reminder_add','reminder_cancel','reminder_snooze','workspace_capture','workspace_save','workspace_restore','workspace_remove','project_run','background_start','job_cancel'}


def validate_mcp_config(name, config):
    name=str(name)
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,39}',name): raise ValueError('Use a short server name with letters, digits, underscores or hyphens.')
    if not isinstance(config,dict) or not (config.get('command') or config.get('url')): raise ValueError('Provide an MCP command or HTTP URL.')
    if set(config)-{'command','args','url','env_vars','bearer_token_env_var','server_options'}: raise ValueError('Unsupported MCP setting. Use environment variable names for credentials.')
    options=config.get('server_options',{})
    if not isinstance(options,dict) or set(options)-{'IJ_MCP_SERVER_PORT','BLENDER_HOST','BLENDER_PORT','DISABLE_TELEMETRY'}: raise ValueError('Only local development ports/host and telemetry settings may be embedded in server_options.')
    for key,value in options.items():
        if not isinstance(value,str) or (key.endswith('_PORT') and (not value.isdigit() or not 1<=int(value)<=65535)) or (key=='BLENDER_HOST' and value not in ('127.0.0.1','localhost','::1')) or (key=='DISABLE_TELEMETRY' and value not in ('true','false')): raise ValueError('Invalid local server option: '+key)
    if config.get('command') and config.get('url'): raise ValueError('Choose one MCP transport, command or URL.')
    if config.get('command') and (not isinstance(config['command'],str) or '\0' in config['command']): raise ValueError('Use an executable path for the MCP command.')
    for key in ('args','env_vars'):
        if key in config and (not isinstance(config[key],list) or not all(isinstance(v,str) and '\0' not in v for v in config[key])): raise ValueError(key+' must be an array of strings.')
    if config.get('url') and not str(config['url']).startswith(('https://','http://localhost:','http://127.0.0.1:')): raise ValueError('Use HTTPS or a loopback MCP server.')
    if config.get('url'):
        address=urllib.parse.urlsplit(config['url'])
        if address.username or address.password or any(k.casefold() in ('token','key','api_key','access_token') for k,v in urllib.parse.parse_qsl(address.query)): raise ValueError('Keep credentials in a token environment variable rather than the MCP URL.')
    if any(k in config for k in ('bearer_token','http_headers','env')): raise ValueError('Use environment variable names, rather than embedded credentials.')


def setup_preview():
    path=root()/'pending-setup.json'
    if path.stat().st_size>150000: raise ValueError('The setup proposal is too large.')
    raw=path.read_bytes(); proposal=json.loads(raw)
    if not isinstance(proposal,dict) or not isinstance(proposal.get('projects'),list) or not isinstance(proposal.get('mcp'),list): raise ValueError('Invalid setup proposal.')
    return {**proposal,'sha256':hashlib.sha256(raw).hexdigest()}


def apply_setup(digest):
    proposal=setup_preview()
    if digest!=proposal['sha256']: raise ValueError('The setup proposal changed. Review it again before approving.')
    # Validate every grant and definition before changing any existing state.
    for project in proposal['projects']:
        grant_project({'projects':[]},project['name'],project['path'])
        for command in project.get('commands',[]):
            argv=command['argv']
            if not command.get('name') or not isinstance(argv,list) or not argv or len(argv)>100 or not all(isinstance(v,str) and '\0' not in v for v in argv): raise ValueError('Invalid saved command.')
            if not (Path(argv[0]).is_file() or shutil.which(argv[0])): raise ValueError('The saved command executable is missing: '+command['name'])
    for server in proposal['mcp']: validate_mcp_config(server['name'],server['config'])
    with database() as data:
        atomic(root()/('before-reviewed-setup-'+identifier()+'.backup.json'),data)
        for project in proposal['projects']:
            item=grant_project(data,project['name'],project['path'])
            for command in project.get('commands',[]):
                if not any(c['name']==command['name'] and c['argv']==command['argv'] for c in item['commands']): item['commands'].append({'id':identifier(),**command})
        for server in proposal['mcp']:
            data['mcp']=[m for m in data['mcp'] if m['name']!=server['name']]
            data['mcp'].append({'id':identifier(),**{k:v for k,v in server.items() if k in ('name','config','connectionStatus','connectionMessage','checked')}})
    os.replace(root()/'pending-setup.json',root()/'applied-setup.json')
    return receipt('verified','Reviewed project folders and connector definitions saved. Connections marked sign-in required still need browser authorisation.')


def dispatch(request, brain=None, trusted_ui=False):
    action = request.get('action')
    if action=='mcp_tools':
        import mcp_bridge
        try:
            tools=mcp_bridge.tools(request['server'])
        except (ValueError,OSError,RuntimeError) as error:
            with database() as data:
                item=row(data['mcp'],request['server']);item.update(connectionStatus='needs_attention',checked=stamp(),connectionMessage=str(error)[:500])
            raise
        with database() as data:
            item=row(data['mcp'],request['server']);item.update(connectionStatus='catalogue_ready',checked=stamp(),connectionMessage=str(len(tools))+' tools available. Tool execution still requires approval.')
        return tools
    if action in TRUSTED_ACTIONS and not trusted_ui: raise ValueError('This permission must be configured by you in the control centre.')
    if action=='setup_preview': return setup_preview()
    if action=='setup_apply': return apply_setup(request['sha256'])
    launch = None
    with database() as data:
        if action == 'state': return public_state(data, str(request.get('query', '')))
        if action == 'history': return history(str(request.get('query', '')))
        if action == 'project_list': return data['projects']
        if action == 'project_grant': return grant_project(data, request.get('name'), request['path'])
        if action == 'project_revoke':
            item = row(data['projects'], request['id']); data['projects'].remove(item); return receipt('verified', 'Project access revoked.')
        if action == 'command_save':
            project = row(data['projects'], request['project'])
            argv = request['argv']
            if not isinstance(argv,list) or not argv or len(argv)>100 or not all(isinstance(a,str) and '\0' not in a for a in argv): raise ValueError('Enter a JSON array of executable and arguments.')
            command = {'id': identifier(), 'name': str(request['name'])[:80], 'argv': argv}
            project['commands'].append(command); return command
        if action == 'project_files':
            project = row(data['projects'], request['project']); files=[]
            base=Path(project['path'])
            for folder, dirs, names in os.walk(base, followlinks=False):
                dirs[:]=[d for d in dirs if d.casefold() not in DENIED_PARTS and not (Path(folder)/d).is_symlink()]
                for name in names:
                    relative=str((Path(folder)/name).relative_to(base))
                    try: project_path(project,relative)
                    except (ValueError,OSError): continue
                    if str(request.get('query','')).casefold() in relative.casefold(): files.append(relative)
                    if len(files)>=500: return files
            return files
        if action == 'project_read':
            project=row(data['projects'],request['project']); path=project_path(project,request['path']); text,digest=text_file(path)
            return {'path':request['path'],'sha256':digest,'text':text[:40000],'truncated':len(text)>40000}
        if action == 'project_preview':
            project=row(data['projects'],request['project']); path=project_path(project,request['path'],True)
            old,digest=text_file(path) if path.exists() else ('',None)
            content=request['content']
            if not isinstance(content,str) or len(content.encode('utf-8'))>500000: raise ValueError('Propose a text change smaller than 500 KB.')
            change={'id':identifier(),'project':project['id'],'path':request['path'],'sha256':digest,'content':content,'status':'proposed','created':stamp(),
                    'diff':''.join(difflib.unified_diff(old.splitlines(True),content.splitlines(True),fromfile='before/'+request['path'],tofile='after/'+request['path']))[:60000]}
            data['changes'].append(change)
            return {k:v for k,v in change.items() if k!='content'}
        if action == 'project_apply':
            change=row(data['changes'],request['id'])
            if change['status']!='proposed': raise ValueError('This change has already been applied or rejected.')
            project=row(data['projects'],change['project']); path=project_path(project,change['path'],True)
            digest=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
            if digest!=change['sha256']: raise ValueError('The file changed after preview. Create a fresh preview to avoid overwriting it.')
            if path.exists():
                backup=root()/'backups'/change['id']; backup.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,backup)
            path.parent.mkdir(parents=True,exist_ok=True)
            fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.atticus-edit-')
            try:
                with os.fdopen(fd,'w',encoding='utf-8',newline='') as f: f.write(change['content'])
                os.replace(tmp,path)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
            change['status']='applied'; change.pop('content',None)
            return receipt('verified','File updated and original backed up.',path=change['path'])
        if action == 'project_reject':
            change=row(data['changes'],request['id']); change['status']='rejected'; change.pop('content',None)
            return receipt('verified','Proposed change discarded.')
        if action == 'reminder_add':
            item={'id':identifier(),'text':str(request['text']).strip()[:1000],'due':parse_due(request).isoformat(),'status':'scheduled','created':stamp()}
            if not item['text']: raise ValueError('Enter reminder text.')
            data['reminders'].append(item); return receipt('verified','Reminder saved.',reminder=item)
        if action in ('reminder_cancel','reminder_snooze'):
            item=row(data['reminders'],request['id'])
            if action=='reminder_cancel': item['status']='cancelled'
            else: item.update(status='scheduled',due=(now()+timedelta(minutes=5)).isoformat())
            return receipt('verified','Reminder updated.')
        if action == 'tick':
            alerts=[]
            for item in data['reminders']:
                if item['status']=='scheduled' and datetime.fromisoformat(item['due'])<=now():
                    item.update(status='due',fired=stamp()); alerts.append({'title':'Reminder','text':item['text'],'id':item['id']})
            for item in data['jobs']:
                if item['status'] in ('completed','failed','interrupted') and not item.get('notified'):
                    item['notified']=True; alerts.append({'title':'Task '+item['status'],'text':item['name'],'id':item['id']})
            return alerts
        if action == 'recover':
            import psutil
            for item in data['jobs']:
                if item['status']=='queued':
                    item.update(status='interrupted',result=receipt('interrupted','The app stopped before this task began. Review before retrying.'))
                elif item['status']=='running':
                    try: alive=abs(psutil.Process(item['pid']).create_time()-item['processStarted'])<1
                    except (psutil.Error,KeyError): alive=False
                    if not alive: item.update(status='interrupted',result=receipt('interrupted','The app or worker stopped. Review before retrying.'))
            return receipt('verified','Task recovery checked.')
        if action == 'workspace_capture':
            if brain is None: raise ValueError('Desktop access unavailable.')
            item=workspace_capture(request['name'],brain); data['workspaces']=[w for w in data['workspaces'] if w['name'].casefold()!=item['name'].casefold()]; data['workspaces'].append(item)
            return receipt('verified','Workspace saved.',workspace=item)
        if action == 'workspace_save':
            entries=request['entries']
            if not isinstance(entries,list) or not 1<=len(entries)<=16: raise ValueError('Choose between one and sixteen workspace entries.')
            for entry in entries:
                if not isinstance(entry,dict) or not isinstance(entry.get('app'),str) or not entry['app'].strip() or len(entry['app'])>300: raise ValueError('Enter an application name.')
                if entry.get('where','left') not in ('left','right','full','center'): raise ValueError('Choose left, right, full or centre.')
                entry.setdefault('rect', {'left':[0,0,.5,1],'right':[.5,0,.5,1],'full':[0,0,1,1],'center':[.15,.15,.7,.7]}[entry.get('where','left')])
                rect=entry['rect']
                if not isinstance(rect,list) or len(rect)!=4 or not all(isinstance(n,(int,float)) and math.isfinite(n) for n in rect) or not all(0<n<=2 for n in rect[2:]): raise ValueError('Use four finite relative rectangle values with positive dimensions up to two screens.')
            item={'id':identifier(),'name':str(request['name'])[:80],'entries':entries}
            data['workspaces']=[w for w in data['workspaces'] if w['name'].casefold()!=item['name'].casefold()]; data['workspaces'].append(item); return item
        if action == 'workspace_remove':
            data['workspaces'].remove(row(data['workspaces'],request['id'])); return receipt('verified','Workspace removed.')
        if action == 'workspace_restore':
            item=dict(row(data['workspaces'],request['id']))
            # Release the state lock before waiting for desktop applications.
        elif action in ('project_run','background_start'):
            if action=='project_run':
                project=row(data['projects'],request['project']); row(project['commands'],request['command'])
                launch=create_job(data,'command',request)
            else:
                if not str(request.get('prompt','')).strip(): raise ValueError('Enter a task for the background assistant.')
                launch=create_job(data,'assistant',request)
        elif action == 'job_cancel':
            job=row(data['jobs'],request['id'])
            if job['status'] not in ('queued','running'): return receipt('completed','This task has already stopped: '+job['status']+'.')
            job['status']='cancelled'; pid=job.get('pid'); started=job.get('processStarted')
        elif action == 'job_status': return data['jobs']
        elif action == 'mcp_save':
            config=request['config']; name=str(request['name'])
            validate_mcp_config(name,config)
            data['mcp']=[m for m in data['mcp'] if m['name']!=name]; data['mcp'].append({'id':identifier(),'name':name,'config':config}); return receipt('verified','MCP configuration saved for new requests.')
        elif action == 'mcp_remove':
            data['mcp'].remove(row(data['mcp'],request['id'])); return receipt('verified','MCP server removed.')
        else: raise ValueError('Unknown assistant service action.')
    if action=='workspace_restore': return workspace_restore(item,brain)
    if action=='job_cancel':
        if pid: cancel_process(pid,started)
        return receipt('verified','Cancellation requested; the worker process tree was stopped.')
    if launch:
        try: launch_job(launch)
        except OSError as error: update_job(launch['id'],status='failed',result=receipt('failed',str(error)))
        return receipt('queued','Task queued. Track it in the control centre.',job=launch)


def quick(task, brain):
    match=re.fullmatch(r'(?i)(?:remind me in|(?:set |start )?(?:a )?timer (?:for )?)(\d+(?:\.\d+)?)\s*(seconds?|minutes?|hours?|days?)(?:\s+(?:to\s+)?(.+))?[.!]?',task.strip())
    if match:
        units={'s':1,'m':60,'h':3600,'d':86400}
        result=dispatch({'action':'reminder_add','seconds':float(match[1])*units[match[2][0].lower()],'text':match[3] or 'Your timer has finished.'})
        return 'Reminder saved for '+datetime.fromisoformat(result['reminder']['due']).astimezone().strftime('%H:%M:%S on %d %b')+'.'
    match=re.fullmatch(r'(?i)(?:restore|open|start) (?:my )?workspace (.+?)[.!]?',task.strip())
    if match:
        result=dispatch({'action':'workspace_restore','id':match[1]},brain)
        return 'Workspace restored and verified.' if result['status']=='verified' else 'Workspace restored partially. Open the control centre to check the result.'
    return None


def run_cli(request, brain):
    try: return {'ok':True,'data':dispatch(request,brain,trusted_ui=True)}
    except (ValueError,OSError,KeyError,TypeError) as error: return {'ok':False,'error':str(error)}


def describe(request):
    """Show the actual change/command at the approval boundary, rather than just a tool name."""
    with database() as data:
        if request.get('action')=='project_run':
            project=row(data['projects'],request['project']); command=row(project['commands'],request['command'])
            return 'Run '+subprocess.list2cmdline(command['argv'])+'\nIn '+project['path']
        if request.get('action')=='project_apply':
            change=row(data['changes'],request['id'])
            return 'Apply '+change['path']+'\n'+change['diff'][:12000]
    return json.dumps(request,ensure_ascii=False)[:2000]


def desktop_receipt(args, output, code, brain):
    if code:
        return receipt('failed',output or 'Desktop helper failed.')
    if args[0] in ('--search','--read','--find','--windows','--clip','--history','--help') or args[:2]==['--ui','see']:
        return receipt('read',output)
    if re.search(r'(?i)\b(could not|failed|not found|no window found|no app or file|error:)\b',output):
        return receipt('failed',output or 'Desktop helper failed.')
    if args[0]=='--show' and len(args)>1 and not re.match(r'^[a-z]+:',args[1],re.I) and brain.winctl.find(args[1]):
        return receipt('verified',output,observation='A matching application window exists.')
    if args[0]=='--place' and len(args)>=4:
        windows=brain.winctl.find(args[1],args[4] if len(args)>4 else '')
        if windows:
            actual=brain.winctl.frame(windows[0]['hwnd']); monitors=brain.winctl.monitors()
            monitor=next((m for m in monitors if m['x']<=actual[0]+actual[2]/2<m['x']+m['w'] and m['y']<=actual[1]+actual[3]/2<m['y']+m['h']),None)
            destination=args[3].casefold()
            correct_screen=monitor and (destination=='current' or destination==monitor['name'].casefold() or destination=='laptop' and monitor['built_in'] or destination=='monitor' and not monitor['built_in'])
            if correct_screen and args[2] in ('left','right','full','center'):
                expected=brain.winctl.rect_for(args[2],monitor['work'],actual[2:])
                if all(abs(a-b)<=16 for a,b in zip(actual,expected)):
                    return receipt('verified',output,observation='The actual window frame matches the requested layout.')
    return receipt('unverified',output,observation='The helper ran, but its effect was not independently confirmed. Check the target before claiming completion.')


if __name__ == '__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--job-worker': job_worker(sys.argv[2])
