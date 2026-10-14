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
    "windowChanged": "所选 WoW 窗口已关闭或发生变化，请刷新并重新选择。",
    "minimized": "游戏窗口已最小化，请恢复窗口后再预览。",
    "timeout": "等待游戏画面超时，请恢复游戏窗口后重试。",
    "resized": "游戏窗口尺寸正在变化，请稍后重新预览。",
    "unsupported": "当前系统无法使用独立窗口捕获，请选择游戏截图文件。",
}


def helper_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "native" / "forever-capture-windows.exe"
    return Path(__file__).resolve().parents[1] / ".runtime/native/forever-capture-windows.exe"


def decode_frame(raw: bytes):
    from PIL import Image
    if len(raw) < 20 or raw[:8] != MAGIC:
        raise UserError("Windows 截图组件没有返回有效画面。")
    width, height, size = struct.unpack_from("<III", raw, 8)
    if (width < 100 or height < 100 or width * height > MAX_PIXELS
            or size != width * height * 4 or len(raw) != 20 + size):
        raise UserError("Windows 截图组件返回的画面尺寸或数据无效。")
    rgba = Image.frombytes("RGBA", (width, height), raw[20:], "raw", "BGRA")
    # Never display undefined RGB values in transparent window corners.
    image = Image.new("RGB", (width, height), "black")
    image.paste(rgba, mask=rgba.getchannel("A"))
    return image


def grab_window(window, *, runner=None):
    from .capture import WOW_EXECUTABLES
    if (window.backend != "win32" or window.hwnd <= 0 or window.pid <= 0
            or window.executable not in WOW_EXECUTABLES):
        raise UserError("只能捕获已选择的本机 WoW 窗口。")
    helper = helper_path()
    if runner is None and not helper.is_file():
        raise UserError("Windows 单窗口截图组件缺失，请重新安装助手或导入游戏截图。")
    options = {"capture_output": True, "stdin": subprocess.DEVNULL, "timeout": 8,
               "check": False, "shell": False}
    if sys.platform == "win32":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = (runner or subprocess.run)([str(helper), "--hwnd", str(window.hwnd),
            "--pid", str(window.pid), "--exe", window.executable], **options)
    except subprocess.TimeoutExpired:
        raise UserError("Windows 单窗口截图超时，请恢复游戏窗口后重试。") from None
    except OSError:
        raise UserError("Windows 单窗口截图组件无法启动，请重新安装助手或导入截图。") from None
    if result.returncode:
        code = result.stderr[:100].decode("ascii", errors="replace").strip()
        raise UserError(ERRORS.get(code, "无法获取所选游戏窗口的独立画面，请重试或导入截图。"))
    return decode_frame(result.stdout)
