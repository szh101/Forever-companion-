"""OS-level capture of explicitly selected WoW windows. No game input/hooks."""
from __future__ import annotations

import ctypes
import io
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .core import Screenshot, UserError

WOW_EXECUTABLES = {"wow.exe", "wowb.exe", "wowt.exe", "wowclassic.exe", "wowclassicb.exe",
                   "wowforever.exe", "wowforeverb.exe", "wowf.exe"}


@dataclass(frozen=True)
class GameWindow:
    hwnd: int
    pid: int
    executable: str
    title: str
    backend: str = "win32"

    @property
    def label(self):
        return f"{self.title} · {self.executable} · PID {self.pid}"


def list_windows() -> list[GameWindow]:
    if sys.platform == "darwin":
        from .mac_capture import list_mac_windows
        return list_mac_windows()
    if sys.platform != "win32":
        return []
    from ctypes import wintypes as w
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback_type, w.LPARAM]
    user.EnumWindows.restype = w.BOOL
    user.IsWindowVisible.argtypes = [w.HWND]
    user.IsWindowVisible.restype = w.BOOL
    user.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user.GetWindowTextW.restype = ctypes.c_int
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.GetWindowThreadProcessId.restype = w.DWORD
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    windows = []

    @callback_type
    def visit(hwnd, _):
        if not user.IsWindowVisible(hwnd):
            return True
        pid = w.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION only
        if not handle:
            return True
        try:
            path, size = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
            if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                return True
            name = os.path.basename(path.value).lower()
            if name not in WOW_EXECUTABLES:
                return True
            title = ctypes.create_unicode_buffer(1024)
            user.GetWindowTextW(hwnd, title, 1024)
            windows.append(GameWindow(int(hwnd), pid.value, name, title.value or "World of Warcraft"))
        finally:
            kernel.CloseHandle(handle)
        return True

    if not user.EnumWindows(visit, 0):
        raise UserError("Windows could not list game windows.")
    return windows


def encode_image(image, label: str, captured_at=None) -> Screenshot:
    from PIL import ImageStat
    if image.width < 100 or image.height < 100 or image.width * image.height > 40_000_000:
        raise UserError("The captured window size is invalid. Restore the game window and try again.")
    image = image.convert("RGB")
    # Reject obvious blank frames; this does not prove that every frame is fresh.
    stat = ImageStat.Stat(image.resize((64, 64)))
    if max(stat.stddev) < 1:
        raise UserError("The screenshot is nearly black or a solid color. Try borderless windowed mode and preview again, or import a game screenshot.")
    image.thumbnail((2048, 2048))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")  # re-encode; discard file metadata
    return Screenshot(buffer.getvalue(), time.time() if captured_at is None else captured_at, label)


def capture_window(window: GameWindow, *, enumerator=None, grabber=None) -> Screenshot:
    if window.backend == "darwin":
        from .mac_capture import capture_mac_window
        return capture_mac_window(window)
    if window.executable not in WOW_EXECUTABLES or window.hwnd <= 0:
        raise UserError("Select a WoW window before capturing.")
    if sys.platform != "win32" and grabber is None:
        raise UserError("This window is not supported on this computer. Refresh the list or import a screenshot.")
    # Revalidate process identity every capture; HWNDs can be reused after exit.
    current = next((x for x in (enumerator or list_windows)() if x.hwnd == window.hwnd), None)
    if current is None or current.pid != window.pid or current.executable != window.executable:
        raise UserError("The selected WoW window has closed or changed. Refresh the window list and select it again.")
    try:
        if grabber is None:
            from .windows_capture import grab_window
            frame = grab_window(window)
        else:
            frame = grabber(window=window.hwnd)
    except UserError:
        raise
    except Exception:
        raise UserError("Could not capture the selected window. No desktop capture was taken. Try borderless windowed mode or import a screenshot.") from None
    # A window may close/reuse its handle while the helper is waiting for a frame.
    current = next((x for x in (enumerator or list_windows)() if x.hwnd == window.hwnd), None)
    if current is None or current.pid != window.pid or current.executable != window.executable:
        raise UserError("The game window changed during capture. Refresh the list and select it again.")
    return encode_image(frame, "selected WoW window (Windows Graphics Capture)")


def load_image(path: str) -> Screenshot:
    from PIL import Image, UnidentifiedImageError
    p = Path(path)
    if p.stat().st_size > 20_000_000:
        raise UserError("The image file exceeds 20 MB.")
    try:
        with Image.open(p) as img:
            if img.width * img.height > 40_000_000:
                raise UserError("The image resolution is too high.")
            img.load()
            return encode_image(img, "user-selected file (original capture time unknown)")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise UserError("Could not read the image. Select a valid PNG or JPEG game screenshot.") from None
