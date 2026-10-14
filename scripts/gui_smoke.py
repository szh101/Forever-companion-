"""Hidden UI smoke test, no screen capture, no game enumeration, no API call."""
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def assert_english_controls(root):
    """Check control labels; transcript and question contents remain unrestricted."""
    pending = [root]
    while pending:
        widget = pending.pop()
        pending.extend(widget.winfo_children())
        options = widget.keys()
        labels = [str(widget.cget(key)) for key in ("text", "values") if key in options]
        if "textvariable" in options and widget.cget("textvariable"):
            labels.append(str(root.getvar(widget.cget("textvariable"))))
        labels.append(getattr(widget, "tooltip_text", ""))
        for label in labels:
            assert not any("\u3400" <= char <= "\u9fff" for char in label), (str(widget), label)


def main():
    import tkinter as tk
    from companion.app import App
    from companion.core import Answer, UserError
    from companion.local_codex import AUTO_MODEL, CODEX_PROVIDER
    from companion.app import FOLLOW_CHAT
    import json
    from companion.providers import DEMO_PROVIDER, MODEL_CHOICES
    root = tk.Tk()
    root.withdraw()
    # User-action helpers may request input focus; hidden checks never dispatch
    # those requests to Windows or affect the foreground game.
    focus_guard = patch("tkinter.Misc.focus_set")
    focus_mock = focus_guard.start()
    try:
        with patch("companion.app.list_windows", side_effect=AssertionError("No game enumeration at startup")), patch("companion.app.find_codex", side_effect=UserError("fixture")):
            app = App(root)
        assert root.state() == "withdrawn"
        assert not app.capture.get()
        assert app.settings_window.state() == "withdrawn"
        assert root.minsize() == (app.px(280), app.px(260))
        assert app.expanded_size == f"{app.px(320)}x{app.px(380)}"
        assert not hasattr(app, "mode_combo")
        assert_english_controls(root)
        assert not any("\u3400" <= char <= "\u9fff" for char in app.chat.get("1.0", "end"))
        if sys.platform == "darwin":
            assert app.paste_screenshot_button is not None
            assert app.game_overlay is None
            assert not root.overrideredirect(), "Mac keeps native window controls"
        root.update_idletasks()
        assert app.fold_button.master.winfo_reqwidth() <= app.px(268), "Header must fit the logical minimum window"
        for logical_width in (280, 320):
            width = app.px(logical_width)
            app.resize_status(SimpleNamespace(widget=root, width=width))
            for label in (app.status_widget, app.snapshot_widget):
                assert int(label.cget("wraplength")) == width - app.px(16)
        # Controls are recognizable, font-independent icons with a hover label.
        # Tooltips stay inside the existing window and never show while hidden.
        for tooltip in app.tooltips:
            button = tooltip.widget
            assert not button.cget("text") and button.cget("image")
            assert button.tooltip_text
            tooltip.show()
            assert tooltip.label is None
        assert app.input in app.interactive_widgets
        assert app.send_button in app.interactive_widgets
        assert app.chat.vbar in app.interactive_widgets
        assert app.preview_button not in app.interactive_widgets
        assert app.opacity.get() == 92 and app.opacity_label.get() == "92%"
        with patch.object(root, "attributes") as attributes:
            app.set_opacity(10)
            attributes.assert_called_with("-alpha", 0.45)
            assert app.opacity_label.get() == "45%"
            app.set_opacity(110)
            attributes.assert_called_with("-alpha", 1.0)
            assert app.opacity_label.get() == "100%"
            app.set_opacity(92)
        assert tuple(app.provider_combo["values"]) == (CODEX_PROVIDER, DEMO_PROVIDER, "OpenAI", "Gemini", "Claude")
        assert app.model_combo.instate(["disabled"])
        app.load_demo()
        assert app.snapshot["demo"] and len(app.snapshot["quests"]) == 3
        with patch.object(root, "clipboard_get", return_value=json.dumps(app.snapshot)):
            assert app.paste_input() == "break"
            assert app.snapshot["demo"]
        # Every paste attempt must visibly acknowledge success or failure, and
        # neither echo clipboard contents nor lose the user's existing draft.
        app.input.delete("1.0", "end")
        app.input.insert("1.0", "保留这段问题")
        valid_snapshot = app.snapshot
        previous_chat = app.chat.get("1.0", "end")
        with patch.object(root, "clipboard_get", return_value=json.dumps(valid_snapshot)):
            app.paste_button.invoke()
        assert app.chat.get("1.0", "end").count("Import successful") == previous_chat.count("Import successful") + 1
        assert "Snapshot received: 3 quests" in app.chat.get("1.0", "end")
        assert "forever-ai-snapshot" not in app.chat.get("1.0", "end")
        for value in ("private clipboard fixture", '{"kind":"forever-ai-snapshot"}'):
            with patch.object(root, "clipboard_get", return_value=value):
                app.paste_button.invoke()
            assert app.snapshot == valid_snapshot
            assert app.input.get("1.0", "end").strip() == "保留这段问题"
            assert "Import failed" in app.status.get()
            assert "Import failed" in app.chat.get("1.0", "end")
            assert value not in app.chat.get("1.0", "end")
        with patch.object(root, "clipboard_get", side_effect=tk.TclError("fixture")):
            app.paste_button.invoke()
        assert "No readable text on the clipboard" in app.chat.get("1.0", "end")
        with patch.object(root, "clipboard_get", return_value="普通聊天文字"):
            assert app.paste_input() is None
        with patch.object(root, "clipboard_get", return_value='{"kind":"forever-ai-snapshot"}'):
            assert app.paste_input() == "break"
            assert app.snapshot == valid_snapshot
        app.input.delete("1.0", "end")
        app.input.insert("1.0", json.dumps(app.snapshot))
        app.send()
        assert not app.busy
        assert app.input.get("1.0", "end").strip() == ""
        app.remove_snapshot()
        assert app.snapshot is None
        app.input.delete("1.0", "end")
        app.input.insert("1.0", "离线 UI 测试")
        app.send()
        deadline = time.monotonic() + 5
        while app.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(0.03)
        assert not app.busy
        assert "no AI request or network connection was made" in app.chat.get("1.0", "end")
        from companion.demo import example_picture
        assert len(app.picture_widgets) == 1
        assert "not a game map" in app.chat.get("1.0", "end")
        for provider, choices in MODEL_CHOICES.items():
            app.key.set("fixture-not-a-real-key")
            app.provider.set(provider)
            app.provider_combo.event_generate("<<ComboboxSelected>>")
            assert_english_controls(root)
            assert tuple(app.model_combo["values"]) == tuple(x[0] for x in choices)
            assert app.model.get() == choices[0][0]
            assert app.key.get() == ""
            assert not app.history
            assert app.model_combo.instate(["!disabled", "!readonly"])
            app.model_combo.current(1)
            assert app.model.get() == choices[1][0]
            assert choices[1][1] in app.model_description.get()
            app.model.set("custom-model-id")
            assert "Custom model" in app.model_description.get()
        app.provider.set("Gemini")
        app.change_provider()
        assert not app.search.get() and app.search_toggle.instate(["disabled"])
        app.fill_prompt("无需网络的模拟 Gemini 请求")
        app.send()
        assert not app.busy and "API key" in app.status.get()
        app.key.set("fixture-not-a-real-key")
        app.model.set("custom-gemini-id")
        with patch("companion.app.ask", return_value=Answer("模拟 Gemini 回答")) as mock_ask:
            app.send()
            deadline = time.monotonic() + 5
            while app.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(0.03)
            assert not app.busy
            assert mock_ask.call_args.args[:3] == ("Gemini", "fixture-not-a-real-key", "custom-gemini-id")
            assert mock_ask.call_args.kwargs["search"] is False
            assert app.history[-1]["content"] == "模拟 Gemini 回答"
        # Selecting the same provider must not erase an already entered key.
        app.change_provider()
        assert app.key.get() == "fixture-not-a-real-key"
        app.provider.set("OpenAI")
        app.change_provider()
        assert app.key.get() == "" and not app.history
        assert app.search.get() and app.search_toggle.instate(["!disabled"])
        app.search.set(False)
        app.provider.set("Claude")
        app.change_provider()
        app.provider.set("OpenAI")
        app.change_provider()
        assert not app.search.get()
        app.provider.set(CODEX_PROVIDER)
        app.change_provider()
        assert app.key_entry.instate(["disabled"])
        app.fill_prompt("本机连接模拟")
        with patch("companion.app.ask_codex", return_value=Answer("Codex 模拟回答")) as mock_codex:
            app.send()
            deadline = time.monotonic() + 5
            while app.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(0.03)
            assert mock_codex.call_args.args[:2] == (AUTO_MODEL, "本机连接模拟")
            assert "generate" not in mock_codex.call_args.kwargs
            assert app.history[-1]["content"] == "Codex 模拟回答"
        app.image_provider.set("Gemini")
        app.change_image_provider()
        assert app.image_key_entry.instate(["disabled"])
        assert app.image_provider_combo.instate(["disabled"])
        app.provider.set("Claude")
        app.change_provider()
        app.key.set("chat-fixture")
        assert app.image_provider_combo.instate(["!disabled"])
        assert app.image_key_entry.instate(["!disabled"])
        app.image_key.set("image-fixture")
        app.fill_prompt("虚构流程图")
        with patch("companion.app.ask", return_value=Answer("生成图", images=[example_picture()])) as mock_image:
            app.send()
            deadline = time.monotonic() + 5
            while app.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(0.03)
            connection = mock_image.call_args.kwargs["image_connection"]
            assert (connection.provider, connection.key, connection.model) == ("Gemini", "image-fixture", "gemini-nano-banana-2.1")
            assert mock_image.call_args.args[3] == "虚构流程图"
            assert app.history[-1]["content"] == "生成图"
        app.image_provider.set("OpenAI")
        app.change_image_provider()
        assert app.image_key.get() == ""
        app.image_provider.set(FOLLOW_CHAT)
        app.change_image_provider()
        app.clear_chat()
        assert not app.picture_widgets and not app.history
        app.toggle_collapsed()
        assert app.collapsed and root.minsize() == (app.px(280), app.px(40))
        assert app.fold_button.tooltip_text == "Expand"
        app.toggle_collapsed()
        assert not app.collapsed and root.minsize() == (app.px(280), app.px(260))
        assert app.fold_button.tooltip_text == "Collapse"
        app.provider.set(DEMO_PROVIDER)
        app.change_provider()
        assert app.model.get() == "" and app.model_combo.instate(["disabled"])
        if app.paste_screenshot_button is not None:
            from companion.capture import GameWindow
            from companion.core import Screenshot
            shot = Screenshot(example_picture().png, time.time(), "selected fixture window")
            executable = "World of Warcraft" if sys.platform == "darwin" else "wow.exe"
            backend = "darwin" if sys.platform == "darwin" else "win32"
            window = GameWindow(101, 202, executable, "synthetic", backend)
            def finish_job():
                deadline = time.monotonic() + 5
                while app.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.02)
                assert not app.busy
            assert app.paste_screenshot_button in app.interactive_widgets
            assert app.controls.pack_slaves()[:2] == [app.paste_button, app.paste_screenshot_button]
            app.input.insert("1.0", "保留截图问题")
            app.capture.set(True)
            with patch.object(app, "selected_window", return_value=window), \
                 patch("companion.app.capture_window", return_value=shot) as capture, \
                 patch("companion.app.copy_screenshot_to_clipboard") as copy, \
                 patch.object(app, "show_image", side_effect=AssertionError("No preview/focus")):
                app.paste_screenshot_button.invoke()
                finish_job()
                capture.assert_called_once_with(window)
                copy.assert_called_once_with(shot.png, root.winfo_id())
            assert app.file_shot is shot and not app.capture.get()
            assert "保留截图问题" in app.input.get("1.0", "end")
            assert "Captured & copied" in app.status.get()
            # Capture failure preserves the previous attachment. A busy system
            # clipboard still leaves a newly captured image ready to send.
            with patch.object(app, "selected_window", return_value=window), \
                 patch("companion.app.capture_window", side_effect=UserError("fixture capture failed")), \
                 patch("companion.app.copy_screenshot_to_clipboard") as copy:
                app.paste_screenshot_button.invoke()
                finish_job()
                copy.assert_not_called()
                assert app.file_shot is shot
            with patch.object(app, "selected_window", return_value=window), \
                 patch("companion.app.capture_window", return_value=shot), \
                 patch("companion.app.copy_screenshot_to_clipboard", side_effect=UserError("The clipboard is busy.")):
                app.paste_screenshot_button.invoke()
                finish_job()
                assert app.file_shot is shot and "Screenshot attached" in app.status.get()
            # An explicit screenshot click may discover a window, but startup
            # and subsequent clicks with an existing selection do not enumerate.
            app.windows = []
            app.window_combo.configure(values=[])
            app.window_combo.set("")
            with patch("companion.app.list_windows", return_value=[]) as discover, \
                 patch("companion.app.capture_window") as capture, \
                 patch("companion.app.copy_screenshot_to_clipboard") as copy:
                app.paste_screenshot_button.invoke()
                discover.assert_called_once_with()
                capture.assert_not_called()
                copy.assert_not_called()
                assert app.file_shot is shot and "Nothing captured" in app.status.get()
            with patch("companion.app.list_windows", side_effect=UserError("The capture helper has not been built.")), \
                 patch("companion.app.capture_window") as capture, \
                 patch("companion.app.copy_screenshot_to_clipboard") as copy:
                app.paste_screenshot_button.invoke()
                assert app.status.get() == "The capture helper has not been built."
                capture.assert_not_called()
                copy.assert_not_called()
            other_window = GameWindow(303, 404, executable, "second synthetic", backend)
            with patch("companion.app.list_windows", return_value=[window, other_window]) as discover, \
                 patch("companion.app.capture_window", return_value=shot) as capture, \
                 patch("companion.app.copy_screenshot_to_clipboard"):
                app.paste_screenshot_button.invoke()
                finish_job()
                discover.assert_called_once_with()
                capture.assert_called_once_with(window)
                assert app.selected_window() is window
                app.window_combo.current(1)
                app.paste_screenshot_button.invoke()
                finish_job()
                discover.assert_called_once_with()
                assert capture.call_args.args == (other_window,)
            # Removing an attachment while a capture is finishing must win over
            # that older completion; this fixture does not access the clipboard.
            import threading
            entered, resume = threading.Event(), threading.Event()
            def delayed_capture(_window):
                entered.set()
                assert resume.wait(5)
                return shot
            with patch("companion.app.capture_window", side_effect=delayed_capture), \
                 patch("companion.app.copy_screenshot_to_clipboard"):
                app.paste_screenshot_button.invoke()
                assert entered.wait(5)
                app.remove_image()
                resume.set()
                finish_job()
                assert app.file_shot is None and not app.capture.get()
                assert "Capturing" not in app.status.get()
            app.file_shot = shot
            app.provider.set("OpenAI")
            app.change_provider()
            app.key.set("fixture-only")
            with patch("companion.app.ask", return_value=Answer("fixture screenshot response")) as ask, \
                 patch("companion.app.capture_window", side_effect=AssertionError("No automatic capture")):
                app.send()
                finish_job()
                assert ask.call_args.kwargs["screenshot"] is shot
                assert app.file_shot is None and not app.capture.get()
                app.input.insert("1.0", "下一条不附图")
                app.send()
                finish_job()
                assert ask.call_args.kwargs["screenshot"] is None
        if app.game_overlay is not None:
            from companion.windows_overlay import OverlayEvent
            # Exercise the real disabled Tk transcript with synthetic deltas;
            # no OS event injection, hooks, mouse reads or visible window.
            app.chat.configure(state="normal")
            app.chat.delete("1.0", "end")
            app.chat.insert("1.0", "".join(f"History fixture {n}\n" for n in range(200)))
            app.chat.configure(state="disabled")
            root.update_idletasks()
            app.chat.yview_moveto(1)
            before = app.chat.yview()[0]
            focus_calls = focus_mock.call_count
            app.game_overlay.handle(OverlayEvent("", "wheel", 0, 0, 120))
            above = app.chat.yview()[0]
            assert above < before, "Positive wheel must move real chat history upward"
            app.game_overlay.handle(OverlayEvent("", "wheel", 0, 0, -120))
            assert app.chat.yview()[0] > above, "Negative wheel must move history downward"
            assert app.game_overlay.ordinary_wheel(SimpleNamespace(delta=120)) == "break"
            assert app.chat.yview()[0] < before
            assert focus_mock.call_count == focus_calls
            assert app.game_overlay.native is None
        assert root.state() == "withdrawn"
        print("PASS: English compact/icon controls, hidden hover labels, opacity bounds, one-shot screenshot/clipboard fixtures, actual hidden transcript wheel scrolling, hidden settings, collapse, direct snapshot paste, provider/key isolation, mock Gemini and Codex, image routing/rendering; no game, clipboard or network access")
    finally:
        focus_guard.stop()
        root.destroy()


if __name__ == "__main__":
    main()
