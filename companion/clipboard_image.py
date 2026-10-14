"""Write a requested screenshot to the OS clipboard; no reading or capture."""
from __future__ import annotations

import ctypes
import io
import sys
import warnings

from .capture import encode_image
from .core import UserError

MAX_BYTES = 20_000_000
MAX_PIXELS = 40_000_000
CF_DIB = 8
GMEM_MOVEABLE = 0x0002


def _win32_api():
    # No clipboard/window access occurs when importing this module.
    from ctypes import wintypes as w

    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user.RegisterClipboardFormatW.argtypes = [w.LPCWSTR]
    user.RegisterClipboardFormatW.restype = w.UINT
    user.OpenClipboard.argtypes = [w.HWND]
    user.OpenClipboard.restype = w.BOOL
    user.EmptyClipboard.argtypes = []
    user.EmptyClipboard.restype = w.BOOL
    user.CloseClipboard.argtypes = []
    user.CloseClipboard.restype = w.BOOL
    user.SetClipboardData.argtypes = [w.UINT, w.HANDLE]
    user.SetClipboardData.restype = w.HANDLE
    kernel.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
    kernel.GlobalAlloc.restype = w.HANDLE
    kernel.GlobalLock.argtypes = [w.HANDLE]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [w.HANDLE]
    kernel.GlobalUnlock.restype = w.BOOL
    kernel.GlobalFree.argtypes = [w.HANDLE]
    kernel.GlobalFree.restype = w.HANDLE
    return user, kernel


def _prepare_image(png: bytes) -> tuple[bytes, bytes]:
    """Validate/re-encode before opening or emptying the clipboard."""
    from PIL import Image, UnidentifiedImageError

    if not isinstance(png, bytes) or not png:
        raise UserError("The screenshot is invalid and cannot be copied to the clipboard.")
    if len(png) > MAX_BYTES:
        raise UserError("The screenshot exceeds 20 MB and cannot be copied to the clipboard.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(png), formats=["PNG"]) as image:
                if image.width < 100 or image.height < 100:
                    raise UserError("The screenshot is too small to copy to the clipboard.")
                if image.width * image.height > MAX_PIXELS:
                    raise UserError("The screenshot resolution is too high to copy to the clipboard.")
                image.load()
                rgba = image.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, "black")
                rgb.paste(rgba, mask=rgba.getchannel("A"))
                # Shared normalization removes metadata and rejects blank frames.
                normalized = encode_image(rgb, "user-requested screenshot").png
                rgb.thumbnail((2048, 2048))
                bitmap = io.BytesIO()
                rgb.save(bitmap, "BMP")
                dib = bitmap.getvalue()[14:]  # CF_DIB excludes BITMAPFILEHEADER.
                if len(normalized) > MAX_BYTES or len(dib) > MAX_BYTES:
                    raise UserError("The screenshot exceeds 20 MB and cannot be copied to the clipboard.")
                return normalized, dib
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise UserError("The screenshot resolution is too high to copy to the clipboard.") from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, OverflowError):
        raise UserError("The screenshot is invalid and cannot be copied to the clipboard.") from None


def _allocate(kernel, data: bytes):
    handle = kernel.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise UserError("Could not allocate memory for the clipboard image.")
    try:
        pointer = kernel.GlobalLock(handle)
        if not pointer:
            raise UserError("Could not write the clipboard image to memory.")
        try:
            ctypes.memmove(pointer, data, len(data))
        finally:
            kernel.GlobalUnlock(handle)
        return handle
    except BaseException:
        kernel.GlobalFree(handle)
        raise


def _write_clipboard(png: bytes, dib: bytes, owner_hwnd: int, *, api=None) -> None:
    user, kernel = _win32_api() if api is None else api
    png_format = user.RegisterClipboardFormatW("PNG")
    if not png_format:
        raise UserError("Could not register the clipboard image format.")
    pending = []
    opened = False
    try:
        # Prepare both moveable buffers first. Invalid images, allocation failures,
        # or a busy clipboard must not erase the existing clipboard contents.
        for kind, data in ((png_format, png), (CF_DIB, dib)):
            pending.append((kind, _allocate(kernel, data)))
        if not user.OpenClipboard(owner_hwnd):
            raise UserError("The clipboard is busy. The screenshot was not copied.")
        opened = True
        if not user.EmptyClipboard():
            raise UserError("Could not update the clipboard. The screenshot was not copied.")
        while pending:
            kind, handle = pending[0]
            if not user.SetClipboardData(kind, handle):
                raise UserError("Could not write the screenshot to the clipboard.")
            # Success transfers ownership to Windows: never free this handle.
            pending.pop(0)
    finally:
        if opened:
            user.CloseClipboard()
        for _, handle in pending:
            kernel.GlobalFree(handle)


def copy_screenshot_to_clipboard(png: bytes, owner_hwnd: int) -> None:
    """Copy after a button click; Windows requires the app's HWND as owner."""
    if sys.platform == "darwin":
        from .mac_capture import run_helper
        normalized, _ = _prepare_image(png)
        # PNG travels over stdin, never a screenshot file or a shell argument.
        run_helper("copy-image", input_bytes=normalized)
        return
    if sys.platform != "win32":
        raise UserError("Copying screenshots to the clipboard is not supported on this platform yet.")
    # OpenClipboard(NULL) followed by EmptyClipboard leaves no clipboard owner
    # and makes SetClipboardData fail. Require the caller's own valid app window.
    if not isinstance(owner_hwnd, int) or isinstance(owner_hwnd, bool) or owner_hwnd <= 0:
        raise UserError("The Companion window is not ready. The screenshot was not copied.")
    try:
        normalized, dib = _prepare_image(png)
        _write_clipboard(normalized, dib, owner_hwnd)
    except UserError:
        raise
    except (OSError, ctypes.ArgumentError):
        raise UserError("Could not copy the screenshot to the clipboard.") from None
