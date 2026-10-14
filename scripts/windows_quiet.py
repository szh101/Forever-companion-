"""Windows test entrypoint: never display a window or access the game/capture/API.

Run with pythonw.exe. Evidence goes only to the specified isolated output path.
"""
import argparse
import contextlib
import io
import json
import platform
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    evidence = {"platform": platform.system(), "python": platform.python_version(),
                "gameTouched": False, "realCaptureTested": False, "liveApiTested": False,
                "hiddenGuiTested": False, "passed": False}
    log = io.StringIO()
    try:
        if sys.platform != "win32":
            raise RuntimeError("Windows-only quiet test")
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
            evidence["tests"] = result.testsRun
            evidence["skipped"] = len(result.skipped)
            evidence["testsPassed"] = result.testsRun - len(result.skipped) - len(result.failures) - len(result.errors)
            evidence["failures"] = len(result.failures)
            evidence["errors"] = len(result.errors)
            if not result.wasSuccessful():
                raise RuntimeError("Contract tests failed")
            import tkinter as tk
            from companion.app import App
            from companion.core import UserError
            root = tk.Tk()
            root.withdraw()  # BEFORE constructing widgets; never map this window.
            try:
                with patch("companion.app.list_windows", side_effect=AssertionError("No game access")), \
                     patch("companion.app.find_codex", side_effect=UserError("Offline test")):
                    app = App(root)
                if root.state() != "withdrawn" or app.capture.get():
                    raise RuntimeError("UI unexpectedly visible or capture enabled")
                app.input.insert("1.0", "离线测试")
                app.send()
                deadline = time.monotonic() + 5
                while app.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.03)
                if app.busy or "no AI request or network connection was made" not in app.chat.get("1.0", "end"):
                    raise RuntimeError("Demo request did not finish")
                if root.state() != "withdrawn":
                    raise RuntimeError("Window became visible")
                evidence["hiddenGuiTested"] = True
            finally:
                for callback in root.tk.call("after", "info"):
                    root.after_cancel(callback)
                root.destroy()
            from gui_smoke import main as full_gui_smoke
            full_gui_smoke()
            evidence["fullGuiSmokePassed"] = True
        evidence["passed"] = True
    except Exception as exc:
        evidence["failure"] = type(exc).__name__ + ": " + str(exc)
    evidence["log"] = log.getvalue()
    output = Path(args.report).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
