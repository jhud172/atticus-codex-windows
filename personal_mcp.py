"""Read-only connectors using the user's existing GitHub, Outlook and OneDrive sessions.

No credentials are copied or returned. Each invocation is still approved by the
Atticus MCP boundary. Account identifiers and file contents stay out of source.
"""
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.parse


def tool(name, description, properties=None, required=None):
    return {'name':name,'description':description,'inputSchema':{'type':'object','properties':properties or {},'required':required or [],'additionalProperties':False}}


STRING={'type':'string'}
TOOLS={
 'github':[
  tool('github_status','Verify existing GitHub CLI sign-in; return login only.'),
  tool('github_repositories','List up to 30 repositories accessible through the existing GitHub CLI account.'),
  tool('github_repository','Read repository metadata.',{'repository':STRING},['repository']),
  tool('github_issues','List up to 30 open issues.',{'repository':STRING},['repository']),
  tool('github_pull_requests','List up to 30 open pull requests.',{'repository':STRING},['repository']),
  tool('github_file','Read a UTF-8 source file from a repository; not binary files.',{'repository':STRING,'path':STRING,'ref':STRING},['repository','path'])],
 'outlook':[
  tool('outlook_status','Check the existing local Outlook profile, inbox and calendar. Does not read messages.'),
  tool('outlook_inbox','Read recent inbox message metadata; no message bodies.',{'limit':{'type':'integer','minimum':1,'maximum':50}}),
  tool('outlook_read','Read one explicitly chosen Outlook message using IDs returned by outlook_inbox.',{'entry_id':STRING,'store_id':STRING},['entry_id','store_id']),
  tool('outlook_calendar','Read appointments in the next 1-31 days.',{'days':{'type':'integer','minimum':1,'maximum':31}})],
 'onedrive':[
  tool('onedrive_status','Check the existing local OneDrive sync folder.'),
  tool('onedrive_files','List matching locally synced OneDrive file paths. Credential/dependency folders are excluded.',{'query':STRING}),
  tool('onedrive_read','Read a selected UTF-8 file inside the OneDrive sync folder. May hydrate an online-only file.',{'path':STRING},['path'])]
}


def execute(argv, input=None):
    result=subprocess.run(argv,input=input,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45,
                          creationflags=0x08000000 if os.name=='nt' else 0)
    if result.returncode: raise RuntimeError((result.stderr or 'The account/tool is unavailable. Sign in or open its application first.')[-1500:])
    return result.stdout


def repo_name(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',value): raise ValueError('Use owner/repository.')
    return value


def call(mode,name,args):
    if name not in {t['name'] for t in TOOLS.get(mode,[])}: raise ValueError('Unknown connector tool.')
    if mode=='github':
        gh=shutil.which('gh.exe') or shutil.which('gh')
        if not gh: raise ValueError('Install GitHub CLI and sign in with gh auth login first.')
        if name=='github_status': return json.loads(execute([gh,'api','user','--jq','{login: .login}']))
        if name=='github_repositories': return json.loads(execute([gh,'repo','list','--limit','30','--json','nameWithOwner,description,isPrivate,url']))
        repo=repo_name(args['repository'])
        if name=='github_repository': return json.loads(execute([gh,'repo','view',repo,'--json','nameWithOwner,description,isPrivate,url,defaultBranchRef']))
        if name in ('github_issues','github_pull_requests'):
            return json.loads(execute([gh,'issue' if name=='github_issues' else 'pr','list','--repo',repo,'--limit','30','--json','number,title,state,url']))
        relative=args['path']
        if not relative or relative.startswith('/') or '..' in relative.split('/'): raise ValueError('Choose a repository-relative file path.')
        import assistant_services as services
        parts=relative.replace('\\','/').split('/')
        if any(p.casefold() in services.DENIED_PARTS for p in parts) or re.search(r'(^|\.)env(\.|$)',parts[-1],re.I) or parts[-1].casefold() in services.DENIED_FILES or Path(parts[-1]).suffix.casefold() in ('.key','.pem','.pfx','.p12'): raise ValueError('Credential files and source-control internals are excluded.')
        endpoint='repos/'+repo+'/contents/'+urllib.parse.quote(relative,safe='/')
        if args.get('ref'): endpoint+='?ref='+urllib.parse.quote(args['ref'],safe='')
        content=json.loads(execute([gh,'api','--method','GET',endpoint]))
        if not isinstance(content,dict) or content.get('type')!='file' or content.get('encoding')!='base64' or content.get('size',0)>200000: raise ValueError('Choose a text file smaller than 200 KB.')
        raw=base64.b64decode(content['content'])
        if b'\0' in raw: raise ValueError('Binary files are not supported by this connector.')
        return {'path':relative,'text':raw.decode('utf-8-sig')}
    if mode=='outlook':
        # Data crosses stdin as JSON, never interpolated into PowerShell source.
        return json.loads(execute(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_name('outlook_mcp.ps1'))],json.dumps({'tool':name,'arguments':args})))
    import assistant_services as services
    folder=Path(os.environ.get('OneDrive') or Path.home()/'OneDrive')
    if not folder.is_dir(): raise ValueError('Set up the OneDrive desktop sync client first.')
    if name=='onedrive_status': return {'available':True,'mode':'Local synced files; cloud-only sites and SharePoint are not included.'}
    project={'path':str(folder)}
    if name=='onedrive_read':
        path=services.project_path(project,args['path']);text,_=services.text_file(path)
        return {'path':args['path'],'text':text[:40000],'truncated':len(text)>40000}
    files=[];query=str(args.get('query','')).casefold()
    for parent,dirs,names in os.walk(folder,followlinks=False):
        dirs[:]=[d for d in dirs if d.casefold() not in services.DENIED_PARTS and not (Path(parent)/d).is_symlink()]
        for filename in names:
            relative=str((Path(parent)/filename).relative_to(folder))
            if query not in relative.casefold(): continue
            try: services.project_path(project,relative)
            except (ValueError,OSError): continue
            files.append(relative)
            if len(files)>=100: return files
    return files


def serve(mode):
    if mode not in TOOLS: raise ValueError('Choose github, outlook or onedrive.')
    for line in sys.stdin:
        try:
            message=json.loads(line)
            if 'id' not in message: continue
            method=message.get('method');params=message.get('params',{})
            if method=='initialize': result={'protocolVersion':params.get('protocolVersion','2025-03-26'),'capabilities':{'tools':{}},'serverInfo':{'name':'atticus-'+mode,'version':'1.0'}}
            elif method=='tools/list': result={'tools':TOOLS[mode]}
            elif method=='tools/call':
                try: result={'content':[{'type':'text','text':json.dumps(call(mode,params['name'],params.get('arguments',{})),ensure_ascii=False)}]}
                except Exception as error: result={'isError':True,'content':[{'type':'text','text':str(error)}]}
            elif method=='ping': result={}
            else:
                print(json.dumps({'jsonrpc':'2.0','id':message['id'],'error':{'code':-32601,'message':'Method not supported.'}}),flush=True);continue
            print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':result},ensure_ascii=False),flush=True)
        except (ValueError,KeyError,TypeError): continue


if __name__=='__main__': serve(sys.argv[1] if len(sys.argv)>1 else '')
