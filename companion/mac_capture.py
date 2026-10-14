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
    "permission": "macOS 尚未允许录屏。点击「授予截图权限」，在系统设置中允许 Forever AI，然后重新打开应用。",
    "windowChanged": "所选 WoW 窗口已关闭或身份发生变化，请刷新并重新选择。",
    "unsupported": "单窗口截图需要 macOS 14 或更新版本；仍可导入截图文件。",
    "captureFailed": "macOS 未能捕获选定窗口；没有回退到桌面。请恢复游戏窗口后重试，或导入截图。",
}


def helper_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "native" / "forever-capture"
    return Path(__file__).resolve().parents[1] / ".runtime" / "native" / "forever-capture"


def run_helper(*args: str, runner=None) -> bytes:
    helper = helper_path()
    if not helper.is_file() and runner is None:
        raise UserError("截图组件尚未构建。请使用 Forever AI.app，或先运行 scripts/build_native.py。")
    try:
        result = (runner or subprocess.run)([str(helper), *args], capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise UserError("macOS 截图组件未响应；未截取桌面，请重试或导入截图。") from None
    if result.returncode:
        try:
            code = json.loads(result.stderr).get("error")
        except (ValueError, TypeError, AttributeError):
            code = None
        raise UserError(ERRORS.get(code, "macOS 截图组件未完成操作；没有截取桌面。"))
    if len(result.stdout) > 20_000_000:
        raise UserError("截图组件返回的数据过大。")
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
        raise UserError("macOS 返回的窗口列表无效。") from None


def request_permission():
    # Called only by the explicit UI button, never during startup/enumeration.
    try:
        data = json.loads(run_helper("request-permission"))
        return data.get("granted") is True
    except (ValueError, AttributeError):
        raise UserError("无法确认 macOS 截图权限，请检查系统设置。") from None


def capture_mac_window(window):
    from PIL import Image, UnidentifiedImageError
    from .capture import encode_image
    if (window.backend != "darwin" or window.hwnd <= 0 or window.pid <= 0
            or window.executable.lower() not in MAC_EXECUTABLES):
        raise UserError("只能捕获已选择的本机 WoW 窗口。")
    # The native helper rechecks executable/PID/window ID immediately before capture.
    raw = run_helper("capture", str(window.hwnd), str(window.pid), window.executable)
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise UserError("macOS 没有返回有效窗口截图。")
    try:
        with Image.open(io.BytesIO(raw)) as frame:
            return encode_image(frame, "selected local macOS WoW window (ScreenCaptureKit)")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise UserError("macOS 没有返回有效窗口截图。") from None
