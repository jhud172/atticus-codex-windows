"""Service integration checks using isolated runtime data and harmless commands."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import timedelta
from unittest.mock import Mock, patch

import assistant_services as services
import codex_provider as codex
import mcp_bridge


class ServicesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.env = patch.dict(os.environ, ATTICUS_DIR=str(self.base/'runtime'))
        self.env.start()
        self.project = self.base/'project'; self.project.mkdir()

    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

    def dispatch(self, action, **kwargs):
        return services.dispatch({'action':action, **kwargs}, trusted_ui=True)

    def grant(self):
        return self.dispatch('project_grant', path=str(self.project), name='Fixture')

    def test_permissions_cannot_be_self_granted(self):
        for action in services.TRUSTED_ACTIONS:
            with self.subTest(action=action), self.assertRaises(ValueError):
                services.dispatch({'action':action})

    def test_native_hub_json_bridge(self):
        process=subprocess.run([sys.executable,'-X','utf8',str(Path(services.__file__).with_name('atticus.py')),'--hub'],
            input=json.dumps({'action':'reminder_add','seconds':60,'text':'Native bridge fixture'}),capture_output=True,text=True,timeout=10)
        self.assertEqual(process.returncode,0,process.stderr)
        result=json.loads(process.stdout)
        self.assertTrue(result['ok'])
        self.assertEqual(self.dispatch('state')['reminders'][0]['text'],'Native bridge fixture')

    def test_project_paths_exclude_traversal_and_credentials(self):
        project=self.grant()
        for name in ('../outside.txt','.env.local','.git/config','auth.json','private.pem'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                services.project_path(project,name,True)
        (self.project/'note.txt').write_text('hello',encoding='utf-8')
        self.assertEqual(self.dispatch('project_files',project=project['id']),['note.txt'])
        self.assertEqual(self.dispatch('project_read',project=project['id'],path='note.txt')['text'],'hello')

    def test_preview_apply_backup_conflict_and_revoke(self):
        project=self.grant(); path=self.project/'note.txt'; path.write_bytes(b'original\r\n')
        change=self.dispatch('project_preview',project=project['id'],path='note.txt',content='new\n')
        self.assertEqual(path.read_bytes(),b'original\r\n')
        self.assertIn('-original',change['diff'])
        self.assertNotIn('content',self.dispatch('state')['changes'][0])
        path.write_bytes(b'changed elsewhere')
        with self.assertRaisesRegex(ValueError,'changed after preview'): self.dispatch('project_apply',id=change['id'])
        path.write_bytes(b'original\r\n')
        result=self.dispatch('project_apply',id=change['id'])
        self.assertEqual(result['status'],'verified')
        self.assertEqual(path.read_bytes(),b'new\n')
        self.assertEqual((services.root()/'backups'/change['id']).read_bytes(),b'original\r\n')
        with self.assertRaises(ValueError): self.dispatch('project_apply',id=change['id'])
        fresh=self.dispatch('project_preview',project=project['id'],path='new.txt',content='hello')
        self.dispatch('project_revoke',id=project['id'])
        with self.assertRaises(ValueError): self.dispatch('project_apply',id=fresh['id'])
        self.assertFalse((self.project/'new.txt').exists())

    def test_reminders_survive_reload_fire_once_and_snooze(self):
        reminder=self.dispatch('reminder_add',text='Fixture reminder',seconds=1)['reminder']
        with services.database() as data: data['reminders'][0]['due']=(services.now()-timedelta(seconds=1)).isoformat()
        self.assertEqual(self.dispatch('tick')[0]['id'],reminder['id'])
        self.assertEqual(self.dispatch('tick'),[])
        self.dispatch('reminder_snooze',id=reminder['id'])
        self.assertEqual(self.dispatch('state')['reminders'][0]['status'],'scheduled')
        self.dispatch('reminder_cancel',id=reminder['id'])
        self.assertEqual(self.dispatch('tick'),[])
        for seconds in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError): self.dispatch('reminder_add',text='invalid',seconds=seconds)

    def test_concurrent_processes_wait_for_the_windows_lock(self):
        with services.database():
            # Start a second process while the first owns the locked byte.
            process=subprocess.Popen([sys.executable,'-X','utf8','-c',
                'import assistant_services as s; print(s.dispatch({"action":"reminder_add","text":"concurrent","seconds":60})["status"])'],
                cwd=Path(services.__file__).parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            time.sleep(.3)
        stdout,stderr=process.communicate(timeout=10)
        self.assertEqual(process.returncode,0,stderr)
        self.assertIn('verified',stdout)
        self.assertEqual(len(self.dispatch('state')['reminders']),1)

    def test_workspace_positions_use_work_area_and_verify(self):
        brain=Mock(); brain.winctl.monitors.return_value=[{'name':'fixture','x':0,'y':0,'w':1920,'h':1080,'work':(0,0,1920,1040)}]
        brain.winctl.find.return_value=[{'hwnd':1}]
        brain.winctl.frame.return_value=(960,0,960,1040)
        saved=self.dispatch('workspace_save',name='Study',entries=[{'app':'Notepad','where':'right'}])
        with patch.object(services.time,'sleep'):
            result=services.dispatch({'action':'workspace_restore','id':saved['id']},brain)
        brain.winctl.set_frame.assert_called_once_with(1,960,0,960,1040)
        self.assertEqual(result['status'],'verified')
        brain.winctl.frame.return_value=(1,1,250,150)
        with patch.object(services.time,'sleep'):
            self.assertEqual(services.workspace_restore(saved,brain)['status'],'needs_attention')
        with self.assertRaises(ValueError): self.dispatch('workspace_save',name='bad',entries=[{'app':'x','rect':[0,0,float('nan'),1]}])

    def test_real_command_worker_completes_and_reports_exit(self):
        project=self.grant()
        command=self.dispatch('command_save',project=project['id'],name='Fixture',argv=[sys.executable,'-c','print("fixture output")'])
        result=self.dispatch('project_run',project=project['id'],command=command['id'])
        key=result['job']['id']
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            job=self.dispatch('job_status')[0]
            if job['status'] in ('completed','failed'): break
            time.sleep(.1)
        log=services.root()/'jobs'/key/'worker.log'
        self.assertEqual(job['status'],'completed',(job,log.read_text(encoding='utf-8') if log.exists() else 'No worker log'))
        self.assertEqual(job['result']['exitCode'],0)
        self.assertIn('fixture output',self.dispatch('state')['jobs'][0]['output'])

    def test_real_command_worker_can_be_cancelled(self):
        project=self.grant()
        command=self.dispatch('command_save',project=project['id'],name='Wait',argv=[sys.executable,'-c','import time; time.sleep(60)'])
        key=self.dispatch('project_run',project=project['id'],command=command['id'])['job']['id']
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            job=self.dispatch('job_status')[0]
            if job['status']=='running': break
            time.sleep(.1)
        self.assertEqual(job['status'],'running')
        self.dispatch('job_cancel',id=key)
        import psutil
        deadline=time.monotonic()+5
        while psutil.pid_exists(job['pid']) and time.monotonic()<deadline: time.sleep(.05)
        self.assertFalse(psutil.pid_exists(job['pid']))
        self.assertEqual(self.dispatch('job_status')[0]['status'],'cancelled')

    def test_recovery_marks_abandoned_jobs_without_replaying(self):
        with services.database() as data:
            job=services.create_job(data,'assistant',{'prompt':'fixture'})
            other=services.create_job(data,'assistant',{'prompt':'other'}); other.update(status='running',pid=99999999,processStarted=0)
        self.dispatch('recover')
        self.assertTrue(all(j['status']=='interrupted' for j in self.dispatch('job_status')))

    def test_declined_external_and_edit_actions_never_execute(self):
        session=codex.Session.__new__(codex.Session); session.brain=Mock(); session.commands=[]; session.receipts=[]
        session.brain.wait_commit.return_value=True; session.brain.ask_user.return_value='n'
        with patch.object(services,'dispatch') as dispatch, patch.object(services,'describe',return_value='fixture diff'), patch.object(mcp_bridge,'call') as call:
            result=session.action({'tool':'atticus_service','arguments':{'request':{'action':'project_apply','id':'x'}}})
            self.assertFalse(result['success']); dispatch.assert_not_called()
            result=session.action({'tool':'atticus_mcp','arguments':{'server':'fixture','tool':'echo','arguments':{}}})
            self.assertFalse(result['success']); call.assert_not_called()
            session.brain.ask_user.reset_mock()
            result=session.action({'tool':'atticus_service','arguments':{'request':{'action':'invented_action'}}})
            self.assertFalse(result['success']);session.brain.ask_user.assert_not_called()

    def test_mcp_stdio_initialise_discover_and_call(self):
        server=self.base/'server.py'
        server.write_text('''import sys,json
for line in sys.stdin:
 m=json.loads(line)
 if 'id' not in m: continue
 method=m['method']
 if method=='initialize': r={'protocolVersion':'2025-03-26','capabilities':{'tools':{}},'serverInfo':{'name':'fixture','version':'1'}}
 elif method=='tools/list': r={'tools':[{'name':'echo','inputSchema':{'type':'object'}}]}
 else: r={'content':[{'type':'text','text':m['params']['arguments']['text']}]}
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':r}),flush=True)
''',encoding='utf-8')
        self.dispatch('mcp_save',name='fixture',config={'command':sys.executable,'args':[str(server)]})
        self.assertEqual(mcp_bridge.tools('fixture')[0]['name'],'echo')
        self.assertEqual(mcp_bridge.call('fixture','echo',{'text':'hello'})['content'][0]['text'],'hello')
        with self.assertRaises(ValueError): self.dispatch('mcp_save',name='bad',config={'url':'https://example.com','bearer_token':'secret'})

    def test_mcp_http_session_and_event_stream(self):
        import http.server
        import threading
        seen=[]
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_POST(self):
                message=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append((message['method'],self.headers.get('Mcp-Session-Id')))
                if 'id' not in message:
                    self.send_response(202); self.end_headers(); return
                result={'protocolVersion':'2025-03-26','capabilities':{'tools':{}},'serverInfo':{'name':'fixture','version':'1'}} if message['method']=='initialize' else {'tools':[{'name':'echo','inputSchema':{'type':'object'}}]}
                body=json.dumps({'jsonrpc':'2.0','id':message['id'],'result':result})
                event=message['method']=='tools/list'
                encoded=('data: '+body+'\n\n' if event else body).encode()
                self.send_response(200); self.send_header('Content-Type','text/event-stream' if event else 'application/json'); self.send_header('Mcp-Session-Id','fixture-session'); self.send_header('Content-Length',str(len(encoded))); self.end_headers(); self.wfile.write(encoded)
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            with mcp_bridge.Client({'url':f'http://127.0.0.1:{server.server_port}/mcp'}) as client:
                self.assertEqual(client.request('tools/list',{})['tools'][0]['name'],'echo')
            self.assertIn(('tools/list','fixture-session'),seen)
        finally: server.shutdown();server.server_close();worker.join()

    def test_desktop_receipts_do_not_promise_unobserved_effects(self):
        self.assertEqual(services.desktop_receipt(['--type','hello'],'typed',0,Mock())['status'],'unverified')
        self.assertEqual(services.desktop_receipt(['--show','Missing'],'not found',0,Mock())['status'],'failed')
        self.assertEqual(services.desktop_receipt(['--windows'],'list',0,Mock())['status'],'read')


if __name__=='__main__': unittest.main()
