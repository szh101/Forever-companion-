"""Windowed Windows entry point and explicitly requested, offline bundle check."""
import argparse
import json
from pathlib import Path
import sys
import time

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def bundle_check(report):
    import tkinter as tk
    import companion.app as ui
    from companion.core import UserError
    from companion.demo import snapshot
    evidence = {"passed": False, "hiddenGuiTested": False, "realCaptureTested": False,
                "liveApiTested": False, "gameTouched": False, "frozen": bool(getattr(sys, "frozen", False))}
    if evidence["frozen"]:
        from companion.windows_capture import helper_path
        evidence["windowCaptureHelperBundled"] = helper_path().is_file()
        if not evidence["windowCaptureHelperBundled"]:
            output = Path(report).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            evidence["failure"] = "Missing Windows Graphics Capture helper"
            output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            return 1
    root = tk.Tk()
    root.withdraw()
    original_finder = ui.find_codex
    def offline():
        raise UserError("Offline bundle check")
    try:
        ui.find_codex = offline
        app = ui.App(root)
        root.update_idletasks()
        assert not app.capture.get() and root.state() == "withdrawn"
        assert app.settings_window.state() == "withdrawn"
        assert app.fold_button.master.winfo_reqwidth() <= app.px(268)
        root.clipboard_get = lambda: json.dumps(snapshot())
        app.paste_button.invoke()
        assert "Snapshot received: 3 quests" in app.chat.get("1.0", "end")
        app.input.insert("1.0", "Windows offline bundle test")
        root.clipboard_get = lambda: '{"kind":"forever-ai-snapshot","schemaVersion":999}'
        app.paste_button.invoke()
        assert len(app.snapshot["quests"]) == 3
        assert app.input.get("1.0", "end").strip() == "Windows offline bundle test"
        assert "Import failed" in app.chat.get("1.0", "end")
        app.send()
        deadline = time.monotonic() + 10
        while app.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(0.02)
        assert not app.busy and len(app.picture_widgets) == 1
        assert "no AI request or network connection was made" in app.chat.get("1.0", "end")
        app.toggle_collapsed()
        assert root.minsize() == (app.px(280), app.px(40))
        app.toggle_collapsed()
        assert root.state() == "withdrawn"
        evidence.update(passed=True, hiddenGuiTested=True, dpiScale=app.ui_scale,
                        python=sys.version.split()[0], tk=root.tk.call("info", "patchlevel"))
    except Exception as exc:
        evidence["failure"] = type(exc).__name__ + ": " + str(exc)
    finally:
        ui.find_codex = original_finder
        for callback in root.tk.call("after", "info"):
            root.after_cancel(callback)
        root.destroy()
    output = Path(report).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if evidence["passed"] else 1


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--self-test-report", help="Run a hidden offline check; never reads the real clipboard")
    modes.add_argument("--check-codex-report", help="Check local CLI help/login only, with no window or model request")
    args = parser.parse_args()
    if args.self_test_report:
        return bundle_check(args.self_test_report)
    if args.check_codex_report:
        from companion.local_codex import CodexProbeError, probe_codex
        evidence = {}
        try:
            probe_codex(diagnostics=evidence)
        except CodexProbeError:
            pass
        evidence["frozen"] = bool(getattr(sys, "frozen", False))
        output = Path(args.check_codex_report).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if evidence["passed"] else 1
    from companion.app import main as run
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
