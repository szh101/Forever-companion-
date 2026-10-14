import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from companion.core import Screenshot, UserError
from companion.local_codex import (CodexProbeError, ask_codex, codex_command, generated_artifacts,
                                   parse_codex_output, probe_codex, process_options, write_probe_diagnostic)
from test_reply_images import png


def events(items):
    return '\n'.join(json.dumps(item) for item in items).encode()


class CodexBridgeTests(unittest.TestCase):
    def test_isolated_read_only_invocation_and_no_inherited_api_key(self):
        args = codex_command(['/bin/codex'], 'gpt-6.1-sol', search=False)
        for required in ['--ignore-user-config', '--ephemeral', 'read-only', 'approval_policy="never"',
                         'mcp_servers={}', 'project_doc_max_bytes=0', 'web_search="disabled"']:
            self.assertIn(required, args)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', args)
        self.assertIn(['--enable', 'image_generation'], [args[i:i+2] for i in range(len(args)-1)])
        self.assertIn(['--enable', 'code_mode_host'], [args[i:i+2] for i in range(len(args)-1)])
        self.assertIn(['--disable', 'shell_tool'], [args[i:i+2] for i in range(len(args)-1)])
        self.assertIn('web_search="live"', codex_command(['/bin/codex'], 'model', search=True))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'private', 'OPENAI_BASE_URL': 'https://evil.invalid', 'CODEX_THREAD_ID': 'unrelated'}):
            options = process_options(['/bin/codex'])
            for key in ['OPENAI_API_KEY', 'OPENAI_BASE_URL', 'CODEX_THREAD_ID']:
                self.assertNotIn(key, options['env'])
            self.assertFalse(options['shell'])
        with self.assertRaises(UserError): codex_command(['/bin/codex'], 'model; command', search=True)

    def test_missing_login_and_older_cli_fail_before_model_request(self):
        def old(args, **kwargs): return subprocess.CompletedProcess(args, 0, b'old CLI', b'')
        with self.assertRaisesRegex(UserError, '版本'):
            probe_codex(runner=old, command=['codex'])
        def logged_out(args, **kwargs):
            text = b'--ignore-user-config --ephemeral --json' if '--help' in args else b'Not logged in'
            return subprocess.CompletedProcess(args, 0, text, b'')
        with self.assertRaisesRegex(UserError, '尚未'):
            ask_codex('model', 'question', runner=logged_out, command=['codex'])

    def test_missing_cli_in_chat_produces_discovery_diagnostic_without_request(self):
        with patch('companion.local_codex.find_codex', side_effect=UserError('not installed')), \
             patch('companion.local_codex.subprocess.run', side_effect=AssertionError('No process')), \
             patch('companion.local_codex.build_request', side_effect=AssertionError('No prompt payload')):
            with self.assertRaises(CodexProbeError) as caught:
                ask_codex('model', 'PRIVATE QUESTION')
        report = caught.exception.diagnostics
        self.assertEqual(report['phase'], 'discovery')
        self.assertEqual(report['failureCode'], 'not_found')
        self.assertFalse(report['modelRequestSent'])
        self.assertNotIn('PRIVATE', json.dumps(report))

    def test_chat_uses_same_discovered_cli_as_its_preflight(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            if '--help' in args:
                text = b'--ignore-user-config --ephemeral --json'
            elif 'status' in args:
                text = b'Logged in using ChatGPT'
            else:
                text = events([{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'fixture'}},
                               {'type': 'turn.completed'}])
            return subprocess.CompletedProcess(args, 0, text, b'')
        with patch('companion.local_codex.find_codex', return_value=['resolved-codex']) as finder:
            answer = ask_codex('model', 'fixture', runner=runner)
        finder.assert_called_once_with()
        self.assertEqual(answer.text, 'fixture')
        self.assertEqual([args[0] for args in calls], ['resolved-codex'] * 3)

    def test_prompt_uses_stdin_private_attachment_is_removed(self):
        requests, paths = [], []
        def runner(args, **kwargs):
            if '--help' in args:
                return subprocess.CompletedProcess(args, 0, b'--ignore-user-config --ephemeral --json', b'')
            if 'status' in args:
                return subprocess.CompletedProcess(args, 0, b'', b'Logged in using ChatGPT')
            requests.append((args, kwargs))
            image_path = Path(args[args.index('--image') + 1])
            paths.append(image_path)
            self.assertTrue(image_path.is_file())
            if os.name != 'nt': self.assertEqual(image_path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn('PRIVATE QUESTION', ' '.join(args))
            self.assertIn(b'PRIVATE QUESTION', kwargs['input'])
            self.assertNotIn(base64.b64encode(png()), kwargs['input'])
            self.assertNotIn(b'Generate one explanatory image', kwargs['input'])
            self.assertIn(b'according to the user', kwargs['input'])
            return subprocess.CompletedProcess(args, 0, events([
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '测试回答'}},
                {'type': 'turn.completed'}]), b'')
        result = ask_codex('model', 'PRIVATE QUESTION', screenshot=Screenshot(png(), time.time(), 'fixture'),
                           search=False, command=['codex'], runner=runner)
        self.assertEqual(result.text, '测试回答')
        self.assertFalse(paths[0].exists())
        self.assertEqual(len(requests), 1)

    def test_help_process_failure_is_not_an_unsupported_version(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 3221225794, b'', b'PRIVATE CLI STDERR')
        with self.assertRaises(CodexProbeError) as caught:
            ask_codex('model', 'PRIVATE QUESTION', runner=runner, command=['fixture-codex'])
        error = caught.exception
        self.assertEqual(len(calls), 1, 'Stop before login or any model request')
        self.assertIn('3221225794', str(error))
        self.assertIn('fixture-codex', str(error))
        self.assertNotIn('请更新', str(error))
        self.assertEqual(error.diagnostics['failureCode'], 'help_process_failed')
        self.assertFalse(error.diagnostics['modelRequestSent'])
        with tempfile.TemporaryDirectory() as folder:
            write_probe_diagnostic(error, directory=folder)
            report = (Path(folder) / 'codex-probe.json').read_text(encoding='utf-8')
            self.assertNotIn('PRIVATE', report + str(error))
            self.assertEqual(json.loads(report)['returncode'], 3221225794)
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_stderr_help_is_accepted_and_login_output_is_not_retained(self):
        def runner(args, **kwargs):
            text = (b'--ignore-user-config --ephemeral --json' if '--help' in args
                    else b'Logged in using ChatGPT\nPRIVATE LOGIN DETAILS')
            return subprocess.CompletedProcess(args, 0, b'', text)
        report = {}
        probe_codex(runner=runner, command=['fixture-codex'], diagnostics=report)
        self.assertTrue(report['passed'])
        self.assertEqual(report['phase'], 'complete')
        self.assertEqual(report['missingFlags'], [])
        self.assertNotIn('PRIVATE', json.dumps(report))

    def test_missing_flags_identify_the_cli_and_stop_before_login(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, b'Usage: codex exec --json', b'')
        with self.assertRaises(CodexProbeError) as caught:
            probe_codex(runner=runner, command=['old-codex'])
        self.assertEqual(caught.exception.diagnostics['missingFlags'], ['--ignore-user-config', '--ephemeral'])
        self.assertIn('old-codex', str(caught.exception))
        self.assertEqual(len(calls), 1)

    def test_empty_help_spawn_failure_and_timeout_are_distinct(self):
        for failure, expected in [(None, 'empty_help'), (OSError(2, 'PRIVATE OS ERROR'), 'os_error'),
                                  (subprocess.TimeoutExpired('fixture', 10, output=b'PRIVATE'), 'timeout')]:
            def runner(args, **kwargs):
                if failure:
                    raise failure
                return subprocess.CompletedProcess(args, 0, b'', b'')
            with self.assertRaises(CodexProbeError) as caught:
                probe_codex(runner=runner, command=['fixture-codex'])
            self.assertEqual(caught.exception.diagnostics['failureCode'], expected)
            self.assertNotIn('PRIVATE', str(caught.exception) + json.dumps(caught.exception.diagnostics))

    def test_login_process_failure_is_not_claimed_to_be_logged_out(self):
        def runner(args, **kwargs):
            if '--help' in args:
                return subprocess.CompletedProcess(args, 0, b'--ignore-user-config --ephemeral --json', b'')
            return subprocess.CompletedProcess(args, 5, b'', b'PRIVATE LOGIN ERROR')
        with self.assertRaises(CodexProbeError) as caught:
            probe_codex(runner=runner, command=['fixture-codex'])
        self.assertEqual(caught.exception.diagnostics['failureCode'], 'login_check_failed')
        self.assertEqual(caught.exception.diagnostics['phase'], 'login_status')
        self.assertNotIn('尚未通过', str(caught.exception))

    def test_diagnostic_write_failure_keeps_original_error(self):
        error = CodexProbeError('original', {'failureCode': 'fixture'})
        with patch('companion.local_codex.Path.mkdir', side_effect=PermissionError):
            write_probe_diagnostic(error, directory='unavailable')
        self.assertEqual(str(error), 'original')

    def test_completed_answer_and_images_only_partial_turn_rejected(self):
        image = base64.b64encode(png()).decode()
        result = parse_codex_output(events([
            {'type': 'item.completed', 'item': {'type': 'reasoning', 'text': 'hidden'}},
            {'type': 'item.completed', 'item': {'type': 'image_generation', 'result': image}},
            {'type': 'turn.completed'}]))
        self.assertEqual(result.text, '')
        self.assertTrue(result.images[0].generated)
        for value in [events([{'type': 'turn.failed', 'error': {'message': 'private token'}}]),
                      events([{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'partial'}}])]:
            with self.assertRaises(UserError) as caught: parse_codex_output(value)
            self.assertNotIn('private token', str(caught.exception))

    def test_model_cannot_make_bridge_read_outside_request_directory(self):
        with tempfile.TemporaryDirectory() as parent:
            private = Path(parent) / 'private.png'
            private.write_bytes(png())
            request = Path(parent) / 'request'
            request.mkdir()
            result = parse_codex_output(events([
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': f'![leak]({private})'}},
                {'type': 'turn.completed'}]), directory=request)
            self.assertEqual(result.images, [])

    def test_unavailable_image_tool_is_explained_by_codex_without_api_fallback(self):
        def runner(args, **kwargs):
            if '--help' in args: value = b'--ignore-user-config --ephemeral --json'
            elif 'status' in args: value = b'Logged in using ChatGPT'
            else: value = events([{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '没有生图工具'}}, {'type': 'turn.completed'}])
            return subprocess.CompletedProcess(args, 0, value, b'')
        result = ask_codex('model', 'picture', runner=runner, command=['codex'])
        self.assertEqual(result.text, '没有生图工具')
        self.assertEqual(result.images, [])

    def test_only_current_cli_thread_new_artifacts_are_displayed(self):
        thread = "00000000-0000-0000-0000-000000000001"
        with tempfile.TemporaryDirectory() as base:
            start = time.time() - 1
            folder = Path(base) / "generated_images" / thread
            folder.mkdir(parents=True)
            (folder / "new.png").write_bytes(png())
            (folder / "old.png").write_bytes(png())
            os.utime(folder / "old.png", (start - 100, start - 100))
            (folder / "auth.json").write_text("must never be read")
            sibling = folder.parent / "00000000-0000-0000-0000-000000000002"
            sibling.mkdir()
            (sibling / "other.png").write_bytes(png())
            raw = events([{'type': 'thread.started', 'thread_id': thread},
                          {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '已生成示意图'}},
                          {'type': 'turn.completed'}])
            result = parse_codex_output(raw, artifact_root=base, request_started=start)
            self.assertEqual(len(result.images), 1)
            self.assertTrue(result.images[0].generated)
            self.assertTrue((folder / "new.png").exists(), "Preserve CLI-owned originals")
            self.assertEqual(generated_artifacts(base, "../other", start), [])
            self.assertEqual(generated_artifacts(base, thread, time.time() + 60), [])
            with self.assertRaises(UserError):
                parse_codex_output(events([{'type': 'thread.started', 'thread_id': thread}]),
                                   artifact_root=base, request_started=start)

    @unittest.skipIf(os.name == 'nt', 'Windows symlinks require separate system privileges')
    def test_generated_artifact_links_are_not_followed(self):
        thread = "00000000-0000-0000-0000-000000000001"
        with tempfile.TemporaryDirectory() as base:
            private = Path(base) / "private.png"
            private.write_bytes(png())
            folder = Path(base) / "generated_images" / thread
            folder.mkdir(parents=True)
            (folder / "link.png").symlink_to(private)
            os.link(private, folder / "hard.png")
            self.assertEqual(generated_artifacts(base, thread, 0), [])
