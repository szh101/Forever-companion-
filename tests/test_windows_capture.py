"""Synthetic frames and mocked native helper calls; never capture a window."""
from dataclasses import replace
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from companion.capture import GameWindow
from companion.core import UserError
from companion.windows_capture import decode_frame, grab_window


def packet(width=100, height=100, pixels=None, *, count=None, magic=b"FAIWGC1\0"):
    if pixels is None:
        pixels = bytes((10, 20, 30, 255)) * (width * height)
    return magic + struct.pack("<III", width, height,
                               len(pixels) if count is None else count) + pixels


class WindowFrameTests(unittest.TestCase):
    def test_bgra_channels_and_transparent_pixels_do_not_expose_hidden_color(self):
        # Contrasting corners also catch row shifts or an incorrect byte stride.
        pixels = bytearray(bytes((10, 20, 30, 255)) * 10_000)
        pixels[:4] = bytes((90, 80, 70, 0))
        pixels[-4:] = bytes((40, 50, 60, 255))
        image = decode_frame(packet(pixels=bytes(pixels)))
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.size, (100, 100))
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 0))
        self.assertEqual(image.getpixel((1, 0)), (30, 20, 10))
        self.assertEqual(image.getpixel((99, 99)), (60, 50, 40))

    def test_corrupt_or_incomplete_protocol_is_rejected(self):
        valid = packet()
        cases = {
            "no header": b"",
            "short header": valid[:19],
            "wrong magic": packet(magic=b"NOTWGC1\0"),
            "short pixels": valid[:-1],
            "trailing bytes": valid + b"private trailing data",
            "byte count too small": packet(count=39_999),
            "byte count too large": packet(count=40_001),
        }
        for label, raw in cases.items():
            with self.subTest(case=label), self.assertRaises(UserError):
                decode_frame(raw)

    def test_untrusted_dimensions_are_bounded_before_image_decoding(self):
        # Header-only frames avoid allocating the advertised large image.
        dimensions = ((0, 100), (99, 100), (100, 99),
                      (8_000, 5_001), (0xFFFFFFFF, 100))
        for width, height in dimensions:
            with self.subTest(size=(width, height)), \
                 patch("PIL.Image.frombytes", side_effect=AssertionError("Invalid size decoded")), \
                 self.assertRaises(UserError):
                decode_frame(packet(width, height, b"", count=0))


class WindowHelperTests(unittest.TestCase):
    window = GameWindow(12345, 67890, "wowb.exe", "Synthetic WoW")

    def test_selected_identity_is_passed_without_a_shell_or_console(self):
        helper = Path("synthetic-native-helper.exe")
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, packet(), b""))
        with patch("companion.windows_capture.helper_path", return_value=helper):
            image = grab_window(self.window, runner=runner)
        self.assertEqual(image.size, (100, 100))
        args, options = runner.call_args
        self.assertEqual(args[0], [str(helper), "--hwnd", "12345", "--pid", "67890",
                                   "--exe", "wowb.exe"])
        self.assertTrue(options["capture_output"])
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertEqual(options["timeout"], 8)
        self.assertIs(options["check"], False)
        self.assertIs(options["shell"], False)
        if sys.platform == "win32":
            self.assertEqual(options["creationflags"], subprocess.CREATE_NO_WINDOW)
        runner.assert_called_once()

    def test_invalid_identity_never_launches_helper(self):
        identities = (
            replace(self.window, backend="darwin"),
            replace(self.window, hwnd=0),
            replace(self.window, hwnd=-1),
            replace(self.window, pid=0),
            replace(self.window, pid=-1),
            replace(self.window, executable="other.exe"),
            replace(self.window, executable="folder/wowb.exe"),
            replace(self.window, executable="wowb.exe --all-windows"),
        )
        for window in identities:
            runner = Mock(side_effect=AssertionError("Invalid identity launched"))
            with self.subTest(window=window), self.assertRaises(UserError):
                grab_window(window, runner=runner)
            runner.assert_not_called()

    def test_missing_helper_fails_before_any_process_or_desktop_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "absent.exe"
            with patch("companion.windows_capture.helper_path", return_value=missing), \
                 patch("subprocess.run") as runner, \
                 patch("PIL.ImageGrab.grab", side_effect=AssertionError("Desktop fallback")):
                with self.assertRaises(UserError):
                    grab_window(self.window)
                runner.assert_not_called()

    def test_helper_failure_does_not_expose_private_output_or_accept_its_frame(self):
        secret = "PRIVATE fixture window title and path"
        runner = Mock(return_value=subprocess.CompletedProcess(
            [], 1, packet(), secret.encode("utf-8")))
        with patch("companion.windows_capture.helper_path", return_value=Path("fixture.exe")), \
             patch("PIL.ImageGrab.grab", side_effect=AssertionError("Desktop fallback")):
            with self.assertRaises(UserError) as error:
                grab_window(self.window, runner=runner)
        self.assertNotIn(secret, str(error.exception))
        runner.assert_called_once()

    def test_failed_launch_or_timeout_stops_without_retry_or_fallback(self):
        secret = "PRIVATE fixture launch details"
        failures = (OSError(secret), subprocess.TimeoutExpired(secret, 8, stderr=secret.encode()))
        for failure in failures:
            runner = Mock(side_effect=failure)
            with self.subTest(failure=type(failure).__name__), \
                 patch("companion.windows_capture.helper_path", return_value=Path("fixture.exe")), \
                 patch("PIL.ImageGrab.grab", side_effect=AssertionError("Desktop fallback")):
                with self.assertRaises(UserError) as error:
                    grab_window(self.window, runner=runner)
            self.assertNotIn(secret, str(error.exception))
            runner.assert_called_once()

    def test_success_exit_with_a_partial_frame_is_still_a_capture_failure(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, packet()[:-4], b""))
        with patch("companion.windows_capture.helper_path", return_value=Path("fixture.exe")), \
             patch("PIL.ImageGrab.grab", side_effect=AssertionError("Desktop fallback")):
            with self.assertRaises(UserError):
                grab_window(self.window, runner=runner)
        runner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
