"""Windows-specific local fixtures; no game, credentials or model requests."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from companion.core import Screenshot, UserError
from companion.local_codex import (AUTO_MODEL, ask_codex, find_codex, generated_artifacts,
                                   process_options, windows_codex_candidates)
from companion.windows_files import artifact_stream, linked_path
from companion.windows_ui import layout_scale
from test_reply_images import png


class DisplayScaleTests(unittest.TestCase):
    def test_windows_uses_display_dpi_but_mac_keeps_existing_size(self):
        class Root:
            def winfo_fpixels(self, distance):
                return 192
        with patch("companion.windows_ui.sys.platform", "win32"):
            self.assertEqual(layout_scale(Root()), 2)
        with patch("companion.windows_ui.sys.platform", "darwin"):
            self.assertEqual(layout_scale(Root()), 1)

    def test_packaged_preflight_mode_never_starts_ui(self):
        import json
        from scripts.windows_entry import main
        from companion.local_codex import CodexProbeError
        for passed in (True, False):
            with tempfile.TemporaryDirectory() as folder:
                report = Path(folder) / 'check.json'
                def probe(*, diagnostics):
                    diagnostics.update(passed=passed, modelRequestSent=False)
                    if not passed:
                        raise CodexProbeError('fixture', diagnostics)
                with patch('sys.argv', ['entry', '--check-codex-report', str(report)]), \
                     patch('companion.local_codex.probe_codex', side_effect=probe), \
                     patch('companion.app.main', side_effect=AssertionError('No UI')):
                    self.assertEqual(main(), 0 if passed else 1)
                self.assertEqual(json.loads(report.read_text(encoding='utf-8'))['passed'], passed)


class WindowsCodexDiscoveryTests(unittest.TestCase):
    def test_desktop_without_codex_path_finds_newest_real_installed_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            local = home / 'AppData/Local'
            old = local / 'OpenAI/Codex/bin/zz-old/codex.exe'
            new = local / 'OpenAI/Codex/bin/aa-new/codex.exe'
            other = local / 'OpenAI/Codex/bin/newest-rg-only/rg.exe'
            directory = local / 'OpenAI/Codex/bin/not-a-file/codex.exe'
            for file in (old, new, other):
                file.parent.mkdir(parents=True)
                file.write_bytes(b'fixture; never executed')
            directory.mkdir(parents=True)
            os.utime(old, (10, 10))
            os.utime(new, (20, 20))
            with patch('companion.local_codex.sys.platform', 'win32'), \
                 patch('companion.local_codex.Path.home', return_value=home), \
                 patch('companion.local_codex.shutil.which', return_value=None), \
                 patch.dict(os.environ, {'PATH': '', 'LOCALAPPDATA': str(home / 'redirected')}):
                self.assertEqual(windows_codex_candidates(), [new, old])
                self.assertEqual(find_codex(), [str(new)])

    def test_local_appdata_is_supported_and_path_still_has_priority(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            local = root / 'custom-local'
            installed = local / 'OpenAI/Codex/bin/hash/codex.exe'
            installed.parent.mkdir(parents=True)
            installed.write_bytes(b'fixture')
            explicit = root / 'explicit-cli.exe'
            explicit.write_bytes(b'fixture')
            with patch('companion.local_codex.sys.platform', 'win32'), \
                 patch('companion.local_codex.Path.home', return_value=root / 'home'), \
                 patch.dict(os.environ, {'LOCALAPPDATA': str(local)}):
                with patch('companion.local_codex.shutil.which', return_value=None):
                    self.assertEqual(find_codex(), [str(installed)])
                with patch('companion.local_codex.shutil.which', return_value=str(explicit)):
                    self.assertEqual(find_codex(), [str(explicit)])

    def test_mac_discovery_does_not_scan_windows_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            cli = Path(folder) / 'codex'
            cli.write_bytes(b'fixture')
            with patch('companion.local_codex.sys.platform', 'darwin'), \
                 patch('companion.local_codex.shutil.which', return_value=str(cli)), \
                 patch('companion.local_codex.windows_codex_candidates', side_effect=AssertionError('Windows only')):
                self.assertEqual(find_codex(), [str(cli)])


@unittest.skipUnless(sys.platform == "win32", "Windows native adapter checks")
class WindowsRuntimeTests(unittest.TestCase):
    def test_codex_subprocess_has_no_console_and_no_shell(self):
        options = process_options(["codex.exe"])
        self.assertEqual(options["creationflags"], subprocess.CREATE_NO_WINDOW)
        self.assertFalse(options["shell"])

    def test_npm_shim_resolves_without_cmd_shell(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shim = root / "codex.cmd"
            shim.write_text("fixture", encoding="utf-8")
            script = root / "node_modules/@openai/codex/bin/codex.js"
            script.parent.mkdir(parents=True)
            script.write_text("fixture", encoding="utf-8")
            with patch("companion.local_codex.shutil.which", side_effect=lambda name: str(shim) if name == "codex" else "node.exe"):
                self.assertEqual(find_codex(), ["node.exe", str(script)])

    def test_plain_artifact_is_read_but_hardlink_is_rejected(self):
        thread = "00000000-0000-0000-0000-000000000001"
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            folder = root / "generated_images" / thread
            folder.mkdir(parents=True)
            (folder / "plain.png").write_bytes(png())
            self.assertEqual(len(generated_artifacts(root, thread, 0)), 1)
            with artifact_stream(folder / "plain.png") as stream:
                self.assertEqual(stream.read(), png())
            os.link(folder / "plain.png", folder / "hard.png")
            self.assertEqual(generated_artifacts(root, thread, 0), [])

    def test_short_path_artifact_root_preserves_file_and_link_checks(self):
        import ctypes
        from ctypes import wintypes as w
        import _winapi
        thread = "00000000-0000-0000-0000-000000000001"
        with tempfile.TemporaryDirectory(prefix="forever-long-artifact-fixture-") as base:
            root = Path(base)
            folder = root / "generated_images" / thread
            folder.mkdir(parents=True)
            picture = folder / "plain.png"
            picture.write_bytes(png())
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetShortPathNameW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
            kernel.GetShortPathNameW.restype = w.DWORD
            short = ctypes.create_unicode_buffer(32768)
            count = kernel.GetShortPathNameW(str(root), short, len(short))
            self.assertGreater(count, 0)
            self.assertLess(count, len(short))
            if os.path.normcase(short.value) == os.path.normcase(str(root)):
                self.skipTest("This fixture volume does not create 8.3 path aliases")
            alias = Path(short.value)
            self.assertEqual(len(generated_artifacts(alias, thread, 0)), 1)
            with artifact_stream(alias / "generated_images" / thread / "plain.png") as stream:
                self.assertEqual(stream.read(), png())
            os.link(picture, folder / "hard.png")
            self.assertEqual(generated_artifacts(alias, thread, 0), [])
            linked = root / "linked-pictures"
            _winapi.CreateJunction(str(folder), str(linked))
            with self.assertRaises(OSError):
                with artifact_stream(alias / "linked-pictures" / "plain.png"):
                    self.fail("A junction below a short path was accepted")

    def test_junction_directory_is_rejected_before_read(self):
        import _winapi
        thread = "00000000-0000-0000-0000-000000000001"
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            actual = root / "synthetic-pictures"
            actual.mkdir()
            (actual / "picture.png").write_bytes(png())
            parent = root / "generated_images"
            parent.mkdir()
            _winapi.CreateJunction(str(actual), str(parent / thread))
            self.assertTrue(linked_path(parent / thread))
            self.assertEqual(generated_artifacts(root, thread, 0), [])
            with self.assertRaises(OSError):
                with artifact_stream(parent / thread / "picture.png"):
                    self.fail("A redirected artifact was accepted")

    def test_attachment_cleanup_after_native_spawn_failure_and_timeout(self):
        for failure in (OSError("fixture"), subprocess.TimeoutExpired("fixture", 1)):
            paths = []
            def runner(args, **kwargs):
                if "--help" in args:
                    return subprocess.CompletedProcess(args, 0, b"--ignore-user-config --ephemeral --json", b"")
                if "status" in args:
                    return subprocess.CompletedProcess(args, 0, b"Logged in using ChatGPT", b"")
                paths.append(Path(args[args.index("--image") + 1]))
                self.assertTrue(paths[-1].exists())
                raise failure
            with self.assertRaises(UserError):
                ask_codex(AUTO_MODEL, "fixture", screenshot=Screenshot(png(), time.time(), "fixture"),
                           command=["codex.exe"], runner=runner, search=False)
            self.assertFalse(paths[0].parent.exists())
