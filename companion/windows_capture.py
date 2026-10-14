"""One-shot Windows Graphics Capture of the selected HWND, via a private pipe."""
from __future__ import annotations

from pathlib import Path
import struct
import subprocess
import sys

from .core import UserError

MAGIC = b"FAIWGC1\0"
MAX_PIXELS = 40_000_000
ERRORS = {
    "windowChanged": "The selected WoW window has closed or changed. Refresh the list and select it again.",
    "minimized": "The game window is minimized. Restore it before previewing.",
    "timeout": "Timed out waiting for the game image. Restore the game window and retry.",
    "resized": "The game window is being resized. Preview it again in a moment.",
    "unsupported": "Window capture is unavailable on this system. Select a game screenshot file.",
}


def helper_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "native" / "forever-capture-windows.exe"
    return Path(__file__).resolve().parents[1] / ".runtime/native/forever-capture-windows.exe"


def decode_frame(raw: bytes):
    from PIL import Image
    if len(raw) < 20 or raw[:8] != MAGIC:
        raise UserError("The Windows capture helper did not return a valid image.")
    width, height, size = struct.unpack_from("<III", raw, 8)
    if (width < 100 or height < 100 or width * height > MAX_PIXELS
            or size != width * height * 4 or len(raw) != 20 + size):
        raise UserError("The Windows capture helper returned invalid image dimensions or data.")
    rgba = Image.frombytes("RGBA", (width, height), raw[20:], "raw", "BGRA")
    # Never display undefined RGB values in transparent window corners.
    image = Image.new("RGB", (width, height), "black")
    image.paste(rgba, mask=rgba.getchannel("A"))
    return image


def grab_window(window, *, runner=None):
    from .capture import WOW_EXECUTABLES
    if (window.backend != "win32" or window.hwnd <= 0 or window.pid <= 0
            or window.executable not in WOW_EXECUTABLES):
        raise UserError("Select a local WoW window before capturing.")
    helper = helper_path()
    if runner is None and not helper.is_file():
        raise UserError("The Windows capture helper is missing. Reinstall the Companion or import a game screenshot.")
    options = {"capture_output": True, "stdin": subprocess.DEVNULL, "timeout": 8,
               "check": False, "shell": False}
    if sys.platform == "win32":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = (runner or subprocess.run)([str(helper), "--hwnd", str(window.hwnd),
            "--pid", str(window.pid), "--exe", window.executable], **options)
    except subprocess.TimeoutExpired:
        raise UserError("Windows window capture timed out. Restore the game window and retry.") from None
    except OSError:
        raise UserError("The Windows capture helper could not start. Reinstall the Companion or import a screenshot.") from None
    if result.returncode:
        code = result.stderr[:100].decode("ascii", errors="replace").strip()
        raise UserError(ERRORS.get(code, "Could not capture the selected game window. Retry or import a screenshot."))
    return decode_frame(result.stdout)
