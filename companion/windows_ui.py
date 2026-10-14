"""Windows logical-pixel sizing; macOS keeps its existing geometry."""
import sys


def layout_scale(root):
    return max(1.0, root.winfo_fpixels("1i") / 96.0) if sys.platform == "win32" else 1.0
