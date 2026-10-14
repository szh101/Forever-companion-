"""Single-window ScreenCaptureKit bridge. No desktop capture or input events."""
from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys

from .core import UserError

MAC_EXECUTABLES = frozenset({"world of warcraft", "world of warcraft classic",
    "world of warcraft beta", "wow", "wowb", "wowt", "wowclassic", "wowclassicb", "wowforever"})
ERRORS = {
    "permission": "Screen Recording is not allowed yet. Click Allow screen recording, enable Forever AI in System Settings, then reopen the app.",
    "windowChanged": "The selected WoW window has closed or its identity has changed. Refresh the list and select it again.",
    "unsupported": "Window capture requires macOS 14 or later. You can still import a screenshot file.",
    "captureFailed": "macOS could not capture the selected window. No desktop capture was taken. Restore the game window and retry, or import a screenshot.",
    "clipboardImageInvalid": "The screenshot is invalid. The clipboard was not updated.",
    "clipboardFailed": "Could not write the screenshot to the macOS clipboard.",
}


def helper_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "native" / "forever-capture"
    return Path(__file__).resolve().parents[1] / ".runtime" / "native" / "forever-capture"


def run_helper(*args: str, runner=None, input_bytes: bytes | None = None) -> bytes:
    helper = helper_path()
    if not helper.is_file() and runner is None:
        raise UserError("The capture helper has not been built. Use Forever AI.app or run scripts/build_native.py first.")
    try:
        result = (runner or subprocess.run)([str(helper), *args], input=input_bytes,
                                           capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        if args == ("copy-image",):
            raise UserError("The macOS clipboard helper did not respond. The screenshot is still available as an attachment.") from None
        raise UserError("The macOS capture helper did not respond. No desktop capture was taken. Retry or import a screenshot.") from None
    if result.returncode:
        try:
            code = json.loads(result.stderr).get("error")
        except (ValueError, TypeError, AttributeError):
            code = None
        fallback = ("The macOS clipboard helper did not complete the operation. The screenshot is still available as an attachment."
                    if args == ("copy-image",) else
                    "The macOS capture helper did not complete the operation. No desktop capture was taken.")
        raise UserError(ERRORS.get(code, fallback))
    if len(result.stdout) > 20_000_000:
        raise UserError("The capture helper returned too much data.")
    return result.stdout


def list_mac_windows():
    from .capture import GameWindow
    try:
        data = json.loads(run_helper("list"))
        if not isinstance(data, list) or len(data) > 200:
            raise ValueError
        windows = []
        for item in data:
            if (type(item.get("id")) is int and item["id"] > 0
                    and type(item.get("pid")) is int and item["pid"] > 0
                    and item.get("executable", "").lower() in MAC_EXECUTABLES):
                windows.append(GameWindow(item["id"], item["pid"], item["executable"],
                                          str(item.get("title") or "World of Warcraft")[:300], "darwin"))
        return windows
    except (ValueError, TypeError, AttributeError):
        raise UserError("macOS returned an invalid window list.") from None


def request_permission():
    # Called only by the explicit UI button, never during startup/enumeration.
    try:
        data = json.loads(run_helper("request-permission"))
        return data.get("granted") is True
    except (ValueError, AttributeError):
        raise UserError("Could not verify macOS capture permission. Check System Settings.") from None


def capture_mac_window(window):
    from PIL import Image, UnidentifiedImageError
    from .capture import encode_image
    if (window.backend != "darwin" or window.hwnd <= 0 or window.pid <= 0
            or window.executable.lower() not in MAC_EXECUTABLES):
        raise UserError("Select a local WoW window before capturing.")
    # The native helper rechecks executable/PID/window ID immediately before capture.
    raw = run_helper("capture", str(window.hwnd), str(window.pid), window.executable)
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise UserError("macOS did not return a valid window screenshot.")
    try:
        with Image.open(io.BytesIO(raw)) as frame:
            return encode_image(frame, "selected local macOS WoW window (ScreenCaptureKit)")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise UserError("macOS did not return a valid window screenshot.") from None
