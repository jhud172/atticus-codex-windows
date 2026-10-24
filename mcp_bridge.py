"""Explicitly configured MCP clients. Every tool execution is approved by Atticus."""
import json
import os
import queue
import subprocess
import threading
import urllib.request


class Client:
    def __init__(self, config):
        self.config = config
        self.serial = 0
        self.session = None
        self.proc = None
        self.messages = queue.Queue()

    def __enter__(self):
        if self.config.get('command'):
            env = {k:v for k,v in os.environ.items() if k in ('PATH','SystemRoot','TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA') or k in self.config.get('env_vars',[])}
            self.proc = subprocess.Popen([self.config['command'], *self.config.get('args',[])], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, text=True, encoding='utf-8', env=env,
                                         creationflags=0x08000000 if os.name=='nt' else 0)
            threading.Thread(target=self.read,daemon=True).start()
        try:
            self.request('initialize', {'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'atticus','version':'2.0'}})
            self.send({'jsonrpc':'2.0','method':'notifications/initialized','params':{}})
        except Exception:
            self.__exit__()
            raise
        return self

    def __exit__(self,*_):
        if self.proc:
            import psutil
            try:
                proc=psutil.Process(self.proc.pid)
                for child in proc.children(recursive=True):
                    try: child.kill()
                    except psutil.Error: pass
                proc.kill()
            except psutil.Error: pass
            try: self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired: self.proc.kill(); self.proc.wait(timeout=5)
            self.proc.stdin.close(); self.proc.stdout.close()

    def read(self):
        try:
            for line in self.proc.stdout:
                try: self.messages.put(json.loads(line))
                except ValueError: pass
        finally: self.messages.put(None)

    def send(self,message):
        if self.proc:
            self.proc.stdin.write(json.dumps(message)+'\n'); self.proc.stdin.flush(); return
        headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-03-26'}
        if self.session: headers['Mcp-Session-Id']=self.session
        token_name=self.config.get('bearer_token_env_var')
        if token_name:
            token=os.environ.get(token_name)
            if not token: raise ValueError('The configured MCP token environment variable is missing.')
            headers['Authorization']='Bearer '+token
        req=urllib.request.Request(self.config['url'],json.dumps(message).encode(),headers)
        with urllib.request.urlopen(req,timeout=90) as response:
            self.session=response.headers.get('Mcp-Session-Id') or self.session
            if response.status==202: return
            if 'text/event-stream' in response.headers.get('Content-Type',''):
                size=0
                for line in response:
                    size+=len(line)
                    if size>8_000_000: raise ValueError('MCP response exceeded 8 MB.')
                    if line.startswith(b'data:'):
                        event=json.loads(line[5:].strip())
                        if event.get('id')==message.get('id'): self.messages.put(event); return
            else:
                value=response.read(8_000_001)
                if len(value)>8_000_000: raise ValueError('MCP response exceeded 8 MB.')
                if value: self.messages.put(json.loads(value))

    def request(self,method,params):
        self.serial+=1; key=self.serial
        self.send({'jsonrpc':'2.0','id':key,'method':method,'params':params})
        while True:
            try: event=self.messages.get(timeout=90)
            except queue.Empty: raise RuntimeError('MCP server timed out.') from None
            if event is None: raise RuntimeError('MCP server disconnected.')
            if event.get('id')==key and 'method' not in event:
                if event.get('error'): raise RuntimeError(str(event['error'].get('message','MCP request failed')))
                return event.get('result',{})
            if event.get('method') and 'id' in event:
                self.send({'jsonrpc':'2.0','id':event['id'],'error':{'code':-32601,'message':'Interactive server requests are not supported; ask in Atticus.'}})


def config_for(server):
    import assistant_services as services
    with services.database() as data:
        return dict(services.row(data['mcp'],server)['config'])


def tools(server):
    with Client(config_for(server)) as client:
        result=client.request('tools/list',{})
        return [{'name':t['name'],'description':t.get('description',''),'inputSchema':t.get('inputSchema',{})} for t in result.get('tools',[])][:100]


def call(server,tool,arguments):
    with Client(config_for(server)) as client:
        return client.request('tools/call',{'name':tool,'arguments':arguments})
