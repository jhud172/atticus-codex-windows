"""Codex tool boundary regressions; no network or desktop actions."""
import json
import unittest
from unittest.mock import Mock, patch

import atticus
import codex_provider as codex


class CodexTests(unittest.TestCase):
    def session(self):
        session = codex.Session.__new__(codex.Session)
        session.brain = Mock()
        session.brain.wait_commit.return_value = True
        session.brain.pref.return_value = True
        session.brain.label.return_value = 'Opening an app'
        session.commands = []
        session.ask = 'scratch'
        return session

    def test_rejects_arbitrary_execution_and_nested_requests(self):
        for args in ([], ['--wait'], ['--gate'], ['--shortcut', 'x', 'evil'],
                     ['--watch', 'cmd', 'evil'], ['--fast', 'anything'], ['--show', 3]):
            with self.assertRaises(ValueError):
                codex.validate(args)

    def test_only_read_helpers_skip_approval(self):
        self.assertTrue(codex.validate(['--windows']))
        self.assertTrue(codex.validate(['--ui', 'see', 'Notepad']))
        for args in (['--ui', 'click', 'B1'], ['--show', 'Notepad'],
                     ['--type', 'hello'], ['--int', 'service', 'read']):
            self.assertFalse(codex.validate(args))

    def test_decline_or_timeout_never_executes(self):
        for answer in ('n', None):
            session = self.session()
            session.brain.ask_user.return_value = answer
            with patch.object(codex.subprocess, 'run') as execute:
                result = session.action({'tool': 'atticus_action', 'arguments': {'args': ['--show', 'Notepad']}})
            self.assertFalse(result['success'])
            execute.assert_not_called()

    def test_unconfirmed_transcript_never_executes_or_asks(self):
        session = self.session()
        session.brain.wait_commit.return_value = False
        with patch.object(codex.subprocess, 'run') as execute:
            result = session.action({'tool': 'atticus_action', 'arguments': {'args': ['--show', 'Notepad']}})
        self.assertFalse(result['success'])
        execute.assert_not_called()
        session.brain.ask_user.assert_not_called()

    def test_approved_arguments_use_no_shell_and_preserve_unicode(self):
        session = self.session()
        session.brain.ask_user.return_value = 'y'
        session.brain.SELF = 'C:/A folder/atticus.py'
        args = ['--type', 'Sample £5; $(not a shell command)']
        with patch.object(codex.subprocess, 'run', return_value=Mock(stdout='typed', stderr='', returncode=0)) as execute:
            result = session.action({'tool': 'atticus_action', 'arguments': {'args': args}})
        self.assertTrue(result['success'])
        self.assertEqual(execute.call_args.args[0][-2:], args)
        self.assertNotIn('shell', execute.call_args.kwargs)

    def test_unknown_server_requests_fail_closed(self):
        session = self.session()
        session.send = Mock()
        session.reject({'id': 44, 'method': 'item/commandExecution/requestApproval'})
        self.assertEqual(session.send.call_args.args[0]['result'], {'decision': 'decline'})
        session.reject({'id': 45, 'method': 'unknown/privilege'})
        self.assertIn('error', session.send.call_args.args[0])

    def test_login_failure_is_not_ready(self):
        with patch.object(codex, 'executable', return_value='codex.exe'), \
             patch.object(codex.subprocess, 'run', return_value=Mock(returncode=1)):
            self.assertFalse(codex.plan()['ok'])

    def test_usage_label_does_not_claim_codex_is_free(self):
        with patch.object(codex, 'executable', return_value='codex.exe'), \
             patch.object(codex.subprocess, 'run', return_value=Mock(returncode=0)):
            self.assertIn('account limits', codex.plan()['text'])


if __name__ == '__main__':
    unittest.main()
