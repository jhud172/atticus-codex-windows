import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, MagicMock, patch

import assistant_services as services
import mcp_bridge
import personal_mcp
import codex_provider


class ConnectorTests(unittest.TestCase):
    def test_stateful_connectors_survive_multiple_tool_calls_then_close(self):
        session=codex_provider.Session.__new__(codex_provider.Session)
        client=MagicMock();client.config={'command':'example'}
        with patch.object(mcp_bridge,'config_for',return_value=client.config),patch.object(mcp_bridge,'Client') as factory:
            factory.return_value.__enter__.return_value=client
            session.external_request('browser','tools/call',{'name':'navigate'})
            session.external_request('browser','tools/call',{'name':'snapshot'})
            factory.assert_called_once();self.assertEqual(client.request.call_count,2)
            client.__exit__.assert_not_called()
            session.close_external();client.__exit__.assert_called_once()

    def test_tools_are_read_only_and_unknown_calls_fail(self):
        names=[t['name'] for tools in personal_mcp.TOOLS.values() for t in tools]
        self.assertFalse(any(word in name for name in names for word in ('send','delete','create','publish')))
        with self.assertRaises(ValueError):personal_mcp.call('github','send_message',{})

    def test_github_arguments_are_validated_and_passed_without_a_shell(self):
        for repo in ('--help','a/b/c','https://example.com/a/b'):
            with self.assertRaises(ValueError):personal_mcp.repo_name(repo)
        with patch.object(personal_mcp.shutil,'which',return_value='gh.exe'),patch.object(personal_mcp,'execute',return_value='[]') as execute:
            personal_mcp.call('github','github_issues',{'repository':'owner/repo'})
        self.assertEqual(execute.call_args.args[0],['gh.exe','issue','list','--repo','owner/repo','--limit','30','--json','number,title,state,url'])
        with patch.object(personal_mcp.shutil,'which',return_value='gh.exe'),patch.object(personal_mcp,'execute') as execute:
            with self.assertRaises(ValueError):personal_mcp.call('github','github_file',{'repository':'owner/repo','path':'prism.env'})
            execute.assert_not_called()

    def test_outlook_inputs_cross_stdin_without_source_interpolation(self):
        args={'entry_id':'quote"; do-not-execute','store_id':'sample'}
        with patch.object(personal_mcp,'execute',return_value='{}') as execute:personal_mcp.call('outlook','outlook_read',args)
        self.assertNotIn(args['entry_id'],' '.join(execute.call_args.args[0]))
        self.assertEqual(json.loads(execute.call_args.args[1])['arguments'],args)

    def test_native_windows_environment_and_no_unrequested_tokens(self):
        with patch.dict(os.environ,{'SYSTEMROOT':'C:/Windows','GH_TOKEN':'not-to-be-inherited','CODEX_PRIVATE':'private'}),patch.object(mcp_bridge.subprocess,'Popen') as popen:
            client=mcp_bridge.Client({'command':'node','args':[]})
            client.request=Mock(return_value={});client.send=Mock();client.read=Mock()
            client.__enter__()
            env=popen.call_args.kwargs['env']
        self.assertIn('SYSTEMROOT',env)
        self.assertNotIn('GH_TOKEN',env);self.assertNotIn('CODEX_PRIVATE',env)

    def test_existing_local_server_options_are_nonsecret_only(self):
        services.validate_mcp_config('editor',{'command':'java','server_options':{'IJ_MCP_SERVER_PORT':'64342'}})
        for options in ({'TOKEN':'bad'},{'BLENDER_HOST':'external.example'},{'BLENDER_PORT':'0'}):
            with self.assertRaises(ValueError):services.validate_mcp_config('editor',{'command':'java','server_options':options})

    def test_real_personal_connector_stdio_catalogue(self):
        config={'command':sys.executable,'args':['-X','utf8',str(Path(personal_mcp.__file__)),'github']}
        with mcp_bridge.Client(config,timeout=10) as client:
            tools=client.request('tools/list',{})['tools']
        self.assertIn('github_status',[t['name'] for t in tools])

    def test_reviewed_setup_requires_fresh_digest_and_rolls_back_invalid_grants(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,ATTICUS_DIR=str(Path(temp)/'runtime')):
            project=Path(temp)/'project';project.mkdir()
            proposal={'projects':[{'name':'Fixture','path':str(project),'commands':[]}],'mcp':[{'name':'fixture','config':{'command':sys.executable,'args':[]}}]}
            services.atomic(services.root()/'pending-setup.json',proposal)
            preview=services.dispatch({'action':'setup_preview'},trusted_ui=True)
            with self.assertRaises(ValueError):services.dispatch({'action':'setup_apply','sha256':preview['sha256']})
            with self.assertRaises(ValueError):services.dispatch({'action':'setup_apply','sha256':'stale'},trusted_ui=True)
            self.assertEqual(services.dispatch({'action':'project_list'}),[])
            services.dispatch({'action':'setup_apply','sha256':preview['sha256']},trusted_ui=True)
            self.assertEqual(len(services.dispatch({'action':'project_list'})),1)
            self.assertTrue((services.root()/'applied-setup.json').exists())
            self.assertTrue(list(services.root().glob('before-reviewed-setup-*.backup.json')))
            proposal['mcp'][0]['config']={'command':sys.executable,'env':{'SECRET':'not allowed'}}
            services.atomic(services.root()/'pending-setup.json',proposal)
            preview=services.setup_preview()
            with self.assertRaises(ValueError):services.apply_setup(preview['sha256'])
            self.assertEqual(len(services.dispatch({'action':'project_list'})),1)


if __name__=='__main__':unittest.main()
