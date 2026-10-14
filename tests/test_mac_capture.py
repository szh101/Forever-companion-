import io
import json
import subprocess
import unittest
from unittest.mock import patch

from companion.capture import GameWindow, capture_window
from companion.core import UserError
from companion import mac_capture
from test_capture import fixture_image


class MacCaptureTests(unittest.TestCase):
    def test_only_native_game_metadata_enters_picker(self):
        rows = [{"id": 25, "pid": 500, "executable": "World of Warcraft", "title": "WoW"},
                {"id": 26, "pid": 501, "executable": "Safari", "title": "World of Warcraft"},
                {"id": 0, "pid": 500, "executable": "Wow", "title": "invalid"}]
        with patch.object(mac_capture, "run_helper", return_value=json.dumps(rows).encode()) as run:
            windows = mac_capture.list_mac_windows()
        self.assertEqual(len(windows), 1)
        self.assertEqual((windows[0].hwnd, windows[0].pid, windows[0].backend), (25, 500, "darwin"))
        run.assert_called_once_with("list")  # no capture or permission request on startup

    def test_selected_window_identity_and_png(self):
        out = io.BytesIO()
        fixture_image().save(out, "PNG")
        window = GameWindow(25, 500, "World of Warcraft", "WoW", "darwin")
        with patch.object(mac_capture, "run_helper", return_value=out.getvalue()) as run:
            shot = capture_window(window)
        run.assert_called_once_with("capture", "25", "500", "World of Warcraft")
        self.assertIn("ScreenCaptureKit", shot.label)
        self.assertTrue(shot.png.startswith(b"\x89PNG"))

    def test_arbitrary_window_rejected_before_native_call(self):
        with patch.object(mac_capture, "run_helper") as run, self.assertRaises(UserError):
            capture_window(GameWindow(25, 500, "Safari", "World of Warcraft", "darwin"))
        run.assert_not_called()

    def test_permission_failure_and_timeout_never_retry_or_fallback(self):
        for error in (b'{"error":"permission"}', b'{"error":"windowChanged"}', b'private stderr'):
            calls = []

            def failed(args, **kwargs):
                calls.append(args)
                return subprocess.CompletedProcess(args, 1, b"", error)

            with self.assertRaises(UserError) as caught:
                mac_capture.run_helper("capture", "25", "500", "World of Warcraft", runner=failed)
            self.assertNotIn("private stderr", str(caught.exception))
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1:], ["capture", "25", "500", "World of Warcraft"])
        with self.assertRaises(UserError):
            mac_capture.run_helper("list", runner=lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired("helper", 20)))

    def test_permission_request_is_explicit_and_fail_closed(self):
        with patch.object(mac_capture, "run_helper", return_value=b'{"granted":false}') as run:
            self.assertFalse(mac_capture.request_permission())
        run.assert_called_once_with("request-permission")
        with patch.object(mac_capture, "run_helper", return_value=b"invalid"), self.assertRaises(UserError):
            mac_capture.request_permission()

    def test_clipboard_bytes_use_stdin_and_never_capture_or_request_permission(self):
        calls = []
        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, b'{"copied":true}', b"")
        self.assertEqual(mac_capture.run_helper("copy-image", input_bytes=b"fixture PNG", runner=runner),
                         b'{"copied":true}')
        self.assertEqual(calls[0][0][1:], ["copy-image"])
        self.assertEqual(calls[0][1]["input"], b"fixture PNG")
        self.assertEqual(len(calls), 1)

    def test_clipboard_failure_messages_do_not_leak_native_output(self):
        for code in (b'{"error":"clipboardFailed"}', b'{"error":"clipboardImageInvalid"}', b'private stderr'):
            def runner(args, **kwargs):
                return subprocess.CompletedProcess(args, 1, b"", code)
            with self.assertRaisesRegex(UserError, "clipboard") as caught:
                mac_capture.run_helper("copy-image", input_bytes=b"fixture", runner=runner)
            self.assertNotIn("private stderr", str(caught.exception))
        with self.assertRaisesRegex(UserError, "screenshot.*attachment"):
            mac_capture.run_helper("copy-image", runner=lambda *a, **kw: (_ for _ in ()).throw(
                subprocess.TimeoutExpired("helper", 20)))


if __name__ == "__main__":
    unittest.main()
