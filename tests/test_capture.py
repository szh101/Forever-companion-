import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw

from companion.capture import GameWindow, capture_window, encode_image
from companion.core import UserError


def fixture_image():
    im = Image.new("RGB", (800, 600), "#123456")
    ImageDraw.Draw(im).rectangle((200, 200, 600, 450), fill="white")
    return im


class CaptureTests(unittest.TestCase):
    def test_capture_only_selected_handle(self):
        window = GameWindow(123, 456, "wow.exe", "test")
        calls = []

        def grabber(**kwargs):
            calls.append(kwargs)
            return fixture_image()

        shot = capture_window(window, enumerator=lambda: [window], grabber=grabber)
        self.assertEqual(calls, [{"window": 123}])
        self.assertTrue(shot.png.startswith(b"\x89PNG"))

    def test_reused_window_handle_rejected(self):
        selected = GameWindow(123, 456, "wow.exe", "test")
        replacement = GameWindow(123, 999, "wow.exe", "test")
        with self.assertRaises(UserError):
            capture_window(selected, enumerator=lambda: [replacement], grabber=lambda **kw: self.fail("capture must not run"))

    def test_capture_failure_never_falls_back(self):
        window = GameWindow(123, 456, "wow.exe", "test")
        calls = []

        def fail(**kwargs):
            calls.append(kwargs)
            raise OSError("failure")

        with self.assertRaises(UserError):
            capture_window(window, enumerator=lambda: [window], grabber=fail)
        self.assertEqual(calls, [{"window": 123}])

    def test_handle_replaced_during_capture_discards_frame(self):
        selected = GameWindow(123, 456, "wow.exe", "test")
        replacement = GameWindow(123, 999, "wow.exe", "test")
        with patch('companion.capture.list_windows', side_effect=[[selected], [replacement]]):
            with self.assertRaises(UserError):
                capture_window(selected, grabber=lambda **kw: fixture_image())

    def test_windows_uses_independent_capture_never_pillow_gdi(self):
        selected = GameWindow(123, 456, "wow.exe", "test")
        with patch('companion.capture.sys.platform', 'win32'), \
             patch('companion.windows_capture.grab_window', return_value=fixture_image()) as native, \
             patch('PIL.ImageGrab.grab', side_effect=AssertionError('GDI must not run')):
            shot = capture_window(selected, enumerator=lambda: [selected])
        native.assert_called_once_with(selected)
        self.assertTrue(shot.png.startswith(b'\x89PNG'))

    def test_blank_or_tiny_frame_is_not_sent(self):
        for im in [Image.new("RGB", (800, 600)), Image.new("RGB", (10, 10))]:
            with self.assertRaises(UserError):
                encode_image(im, "test")


if __name__ == "__main__":
    unittest.main()
