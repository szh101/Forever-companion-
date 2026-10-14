"""Synthetic buffers and mocked OS bridges; never touch the real clipboard."""
import ctypes
import io
import struct
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw, PngImagePlugin

from companion.clipboard_image import (
    CF_DIB, GMEM_MOVEABLE, _prepare_image, _write_clipboard,
    copy_screenshot_to_clipboard,
)
from companion.core import UserError


def fixture_image(size=(240, 160)):
    image = Image.new("RGB", size, "#234567")
    ImageDraw.Draw(image).rectangle((0, 0, size[0] // 2, size[1] // 2), fill="white")
    return image


def png_bytes(size=(240, 160), *, metadata=False):
    buffer = io.BytesIO()
    info = PngImagePlugin.PngInfo()
    if metadata:
        info.add_text("private", "test metadata must not be copied")
    fixture_image(size).save(buffer, "PNG", pnginfo=info)
    return buffer.getvalue()


class FakeClipboard:
    PNG = 0xC001

    def __init__(self, *, busy=False, alloc_fail_at=0, lock_fail=False,
                 empty_fail=False, set_fail_at=0):
        self.busy, self.alloc_fail_at, self.lock_fail = busy, alloc_fail_at, lock_fail
        self.empty_fail, self.set_fail_at = empty_fail, set_fail_at
        self.calls, self.buffers, self.transferred = [], {}, {}
        self.alloc_count, self.set_count = 0, 0

    def RegisterClipboardFormatW(self, name):
        self.calls.append(("register", name))
        return self.PNG

    def OpenClipboard(self, hwnd):
        self.calls.append(("open", hwnd))
        return not self.busy

    def EmptyClipboard(self):
        self.calls.append(("empty",))
        return not self.empty_fail

    def CloseClipboard(self):
        self.calls.append(("close",))
        return True

    def SetClipboardData(self, kind, handle):
        self.calls.append(("set", kind, handle))
        self.set_count += 1
        if self.set_count == self.set_fail_at:
            return 0
        self.transferred[kind] = handle
        return handle

    def GlobalAlloc(self, flags, size):
        self.calls.append(("allocate", flags, size))
        self.alloc_count += 1
        if self.alloc_count == self.alloc_fail_at:
            return 0
        handle = self.alloc_count
        self.buffers[handle] = ctypes.create_string_buffer(size)
        return handle

    def GlobalLock(self, handle):
        self.calls.append(("lock", handle))
        return 0 if self.lock_fail else ctypes.addressof(self.buffers[handle])

    def GlobalUnlock(self, handle):
        self.calls.append(("unlock", handle))
        return True

    def GlobalFree(self, handle):
        if handle in self.transferred.values():
            raise AssertionError("must not free Windows-owned buffer")
        self.calls.append(("free", handle))
        del self.buffers[handle]
        return 0


class ClipboardImageTests(unittest.TestCase):
    def test_copy_sets_png_and_24bit_dib_with_real_owner_and_transfers_ownership(self):
        fake = FakeClipboard()
        with patch("companion.clipboard_image.sys.platform", "win32"), \
             patch("companion.clipboard_image._win32_api", return_value=(fake, fake)):
            copy_screenshot_to_clipboard(png_bytes(metadata=True), 123)
        self.assertIn(("open", 123), fake.calls)
        self.assertEqual(fake.calls[-1], ("close",))
        self.assertFalse(any(c[0] == "free" for c in fake.calls))
        self.assertEqual(set(fake.transferred), {fake.PNG, CF_DIB})
        for kind, handle in fake.transferred.items():
            raw = fake.buffers[handle].raw
            with Image.open(io.BytesIO(raw)) as image:
                self.assertEqual(image.size, (240, 160))
                self.assertEqual(image.getpixel((239, 159)), (35, 69, 103))
                self.assertNotIn("private", image.info)
            if kind == CF_DIB:
                self.assertEqual(struct.unpack_from("<H", raw, 14)[0], 24)
        alloc_indices = [i for i, c in enumerate(fake.calls) if c[0] == "allocate"]
        self.assertEqual(len(alloc_indices), 2)
        self.assertLess(max(alloc_indices), fake.calls.index(("empty",)))
        self.assertTrue(all(c[1] == GMEM_MOVEABLE for c in fake.calls if c[0] == "allocate"))

    def test_busy_clipboard_frees_buffers_without_empty_or_close(self):
        fake = FakeClipboard(busy=True)
        with self.assertRaisesRegex(UserError, "clipboard is busy"):
            _write_clipboard(b"png fixture", b"dib fixture", 123, api=(fake, fake))
        self.assertEqual(fake.buffers, {})
        self.assertFalse(any(c[0] in {"empty", "close", "set"} for c in fake.calls))
        self.assertEqual([c for c in fake.calls if c[0] == "free"], [("free", 1), ("free", 2)])

    def test_allocation_and_lock_failures_leave_existing_clipboard_untouched(self):
        for args in ({"alloc_fail_at": 1}, {"alloc_fail_at": 2}, {"lock_fail": True}):
            with self.subTest(args=args):
                fake = FakeClipboard(**args)
                with self.assertRaises(UserError):
                    _write_clipboard(b"png", b"dib", 123, api=(fake, fake))
                self.assertEqual(fake.buffers, {})
                self.assertFalse(any(c[0] in {"open", "empty", "set"} for c in fake.calls))

    def test_copy_failure_unlocks_and_frees_without_opening_clipboard(self):
        fake = FakeClipboard()
        with patch("companion.clipboard_image.ctypes.memmove", side_effect=OSError("fixture")):
            with self.assertRaises(OSError):
                _write_clipboard(b"png", b"dib", 123, api=(fake, fake))
        self.assertEqual(fake.calls[-2:], [("unlock", 1), ("free", 1)])
        self.assertEqual(fake.buffers, {})
        self.assertFalse(any(c[0] == "open" for c in fake.calls))

    def test_empty_failure_closes_clipboard_and_frees_both_buffers(self):
        fake = FakeClipboard(empty_fail=True)
        with self.assertRaises(UserError):
            _write_clipboard(b"png", b"dib", 123, api=(fake, fake))
        self.assertEqual(fake.calls[-3:], [("close",), ("free", 1), ("free", 2)])
        self.assertFalse(any(c[0] == "set" for c in fake.calls))

    def test_set_failure_frees_only_untransferred_buffers(self):
        for failed in (1, 2):
            with self.subTest(failed=failed):
                fake = FakeClipboard(set_fail_at=failed)
                with self.assertRaisesRegex(UserError, "Could not write the screenshot"):
                    _write_clipboard(b"png", b"dib", 123, api=(fake, fake))
                self.assertIn(("close",), fake.calls)
                frees = [c[1] for c in fake.calls if c[0] == "free"]
                self.assertEqual(frees, [1, 2] if failed == 1 else [2])
                self.assertEqual(set(fake.buffers), set(fake.transferred.values()))

    def test_invalid_tiny_blank_or_oversized_source_never_touches_clipboard(self):
        blank = io.BytesIO()
        Image.new("RGB", (200, 200)).save(blank, "PNG")
        with patch("companion.clipboard_image.sys.platform", "win32"), \
             patch("companion.clipboard_image._win32_api") as native:
            for data in (b"not an image", b"", "not bytes", png_bytes((50, 50)), blank.getvalue()):
                with self.subTest(data_type=type(data)):
                    with self.assertRaises(UserError):
                        copy_screenshot_to_clipboard(data, 123)
            with patch("companion.clipboard_image.MAX_BYTES", 10):
                with self.assertRaisesRegex(UserError, "20 MB"):
                    copy_screenshot_to_clipboard(b"x" * 11, 123)
            native.assert_not_called()

    def test_pixel_limit_is_checked_before_loading_pixels(self):
        raw = png_bytes()
        with patch("companion.clipboard_image.MAX_PIXELS", 10), \
             patch("PIL.PngImagePlugin.PngImageFile.load", side_effect=AssertionError("no decode")):
            with self.assertRaisesRegex(UserError, "resolution is too high"):
                _prepare_image(raw)

    def test_resize_and_alpha_flattens_to_matching_png_and_dib(self):
        png, dib = _prepare_image(png_bytes((2400, 1600)))
        for data in (png, dib):
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual(image.size, (2048, 1365))
        source = fixture_image().convert("RGBA")
        ImageDraw.Draw(source).rectangle((130, 100, 239, 159), fill=(250, 10, 10, 0))
        raw = io.BytesIO()
        source.save(raw, "PNG")
        for data in _prepare_image(raw.getvalue()):
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual(image.getpixel((239, 159)), (0, 0, 0))

    def test_unsupported_platform_invalid_owner_and_native_error_are_safe(self):
        with patch("companion.clipboard_image.sys.platform", "linux"), \
             patch("companion.clipboard_image._win32_api") as native:
            with self.assertRaisesRegex(UserError, "not supported on this platform"):
                copy_screenshot_to_clipboard(png_bytes(), 123)
            native.assert_not_called()
        with patch("companion.clipboard_image.sys.platform", "win32"), \
             patch("companion.clipboard_image._win32_api") as native:
            for hwnd in (None, 0, -1, True, "123"):
                with self.assertRaises(UserError):
                    copy_screenshot_to_clipboard(png_bytes(), hwnd)
            native.assert_not_called()
        with patch("companion.clipboard_image.sys.platform", "win32"), \
             patch("companion.clipboard_image._win32_api", side_effect=OSError("private")):
            with self.assertRaises(UserError) as raised:
                copy_screenshot_to_clipboard(png_bytes(), 123)
            self.assertNotIn("private", str(raised.exception))

    def test_mac_copies_normalized_png_over_stdin_without_windows_or_files(self):
        from companion import mac_capture
        with patch("companion.clipboard_image.sys.platform", "darwin"), \
             patch("companion.clipboard_image._win32_api", side_effect=AssertionError("No Windows API")), \
             patch.object(mac_capture, "run_helper", return_value=b'{"copied":true}') as helper:
            copy_screenshot_to_clipboard(png_bytes(metadata=True), 0)
        self.assertEqual(helper.call_args.args, ("copy-image",))
        with Image.open(io.BytesIO(helper.call_args.kwargs["input_bytes"])) as image:
            self.assertEqual(image.size, (240, 160))
            self.assertNotIn("private", image.info)

    def test_mac_rejects_invalid_images_before_native_clipboard(self):
        with patch("companion.clipboard_image.sys.platform", "darwin"), \
             patch("companion.mac_capture.run_helper") as helper:
            for data in (b"not PNG", b"", png_bytes((50, 50))):
                with self.assertRaises(UserError):
                    copy_screenshot_to_clipboard(data, 0)
            helper.assert_not_called()

    def test_mac_clipboard_failure_remains_a_user_error(self):
        with patch("companion.clipboard_image.sys.platform", "darwin"), \
             patch("companion.mac_capture.run_helper", side_effect=UserError("The clipboard helper did not respond.")):
            with self.assertRaisesRegex(UserError, "clipboard helper did not respond"):
                copy_screenshot_to_clipboard(png_bytes(), 0)


if __name__ == "__main__":
    unittest.main()
