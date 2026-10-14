"""Overlay adapter contracts with fake widgets only; no Tk or native windows."""
import unittest
from types import SimpleNamespace
from unittest import mock

from companion.overlay_ui import GameOverlay
from companion.windows_overlay import OverlayEvent


class FakeWidget:
    def __init__(self, name, rect=(20, 30, 80, 50), visible=True):
        self.name, self.rect, self.visible = name, rect, visible
        self.bindings, self.events, self.states = {}, [], []
        self.focus_calls = self.invoke_calls = 0
        self.disabled = False
        self.children, self.scrolls = [], []

    def __str__(self):
        return self.name

    def bind(self, event, callback, add=None):
        self.bindings[event] = callback

    def winfo_rootx(self):
        return self.rect[0]

    def winfo_rooty(self):
        return self.rect[1]

    def winfo_x(self):
        return self.rect[0]

    def winfo_y(self):
        return self.rect[1]

    def winfo_width(self):
        return self.rect[2] - self.rect[0]

    def winfo_height(self):
        return self.rect[3] - self.rect[1]

    def winfo_viewable(self):
        return self.visible

    def winfo_children(self):
        return self.children

    def instate(self, state):
        return state == ["disabled"] and self.disabled

    def state(self, state):
        self.states.append(state)

    def focus_set(self):
        self.focus_calls += 1

    def event_generate(self, sequence, **kwargs):
        self.events.append((sequence, kwargs))

    def invoke(self):
        self.invoke_calls += 1

    def yview_scroll(self, amount, units):
        self.scrolls.append((amount, units))

    def index(self, _index):
        return "1.0"

    def tag_names(self):
        return ()


class FakeRoot(FakeWidget):
    def __init__(self, visible=True):
        super().__init__("root", (10, 20, 330, 400), visible)
        self.scheduled, self.cancelled, self.decorations = [], [], []
        self.geometries = []

    def after(self, milliseconds, callback):
        self.scheduled.append((milliseconds, callback))
        return str(len(self.scheduled))

    def after_cancel(self, timer):
        self.cancelled.append(timer)

    def overrideredirect(self, value):
        self.decorations.append(value)

    def update_idletasks(self):
        pass

    def minsize(self):
        return (280, 280)

    def geometry(self, value):
        self.geometries.append(value)

    def after_idle(self, callback):
        return self.after(0, callback)


class FakeNative:
    def __init__(self):
        self.activation_calls = self.release_calls = self.close_calls = 0
        self.targets, self.scroll_rects = (), ()
        self.allow_activation = True
        self.bounds = (10, 20, 320, 380)
        self.moves = []

    def activate_input(self):
        self.activation_calls += 1
        return self.allow_activation

    def release_input(self):
        self.release_calls += 1

    def update_targets(self, targets, scroll_rects=()):
        self.targets, self.scroll_rects = tuple(targets), tuple(scroll_rects)

    def close(self):
        self.close_calls += 1

    def get_bounds(self):
        return self.bounds

    def move_resize(self, x, y, width, height):
        self.moves.append((x, y, width, height))
        self.bounds = self.moves[-1]


class OverlayUIContractTests(unittest.TestCase):
    def make_overlay(self, visible=True):
        app = SimpleNamespace(root=FakeRoot(visible),
                              input=FakeWidget("input", (20, 320, 290, 375)),
                              chat=FakeWidget("chat", (20, 65, 305, 310)),
                              drag_handle=FakeWidget("drag"), resize_handle=FakeWidget("resize"),
                              status=mock.Mock(), opacity=SimpleNamespace(get=lambda: 92),
                              collapsed=False, open_source=mock.Mock())
        app.chat.vbar = FakeWidget("scrollbar", (305, 65, 315, 310))
        app.button = FakeWidget("button", (250, 30, 280, 55))
        app.interactive_widgets = [app.input, app.button, app.chat.vbar]
        overlay = GameOverlay(app)
        overlay.native = FakeNative()
        overlay.update_layout()
        return overlay, app, overlay.native

    def test_withdrawn_refresh_never_constructs_or_starts_native_backend(self):
        overlay, app, native = self.make_overlay(False)
        overlay.native = None
        with mock.patch("companion.overlay_ui.sys.platform", "win32"), \
                mock.patch("companion.windows_overlay.WindowsOverlay") as constructor:
            overlay.refresh()
            constructor.assert_not_called()
        self.assertEqual(app.root.decorations, [])
        overlay.native = native
        overlay.refresh()
        self.assertEqual(native.targets, ())
        self.assertEqual(native.scroll_rects, ())
        self.assertEqual(native.activation_calls, 0)

    def test_only_explicit_input_press_activates_keyboard_and_focuses_input(self):
        overlay, app, native = self.make_overlay()
        overlay.handle(OverlayEvent("input", "motion", 30, 330))
        overlay.handle(OverlayEvent("input", "release", 30, 330))
        self.assertEqual(native.activation_calls, 0)
        self.assertEqual(app.input.focus_calls, 0)
        overlay.handle(OverlayEvent("input", "press", 30, 330))
        self.assertEqual(native.activation_calls, 1)
        self.assertEqual(app.input.focus_calls, 1)
        self.assertEqual(app.input.events[-1],
                         ("<ButtonPress-1>", {"x": 10, "y": 10, "when": "now"}))
        overlay.handle(OverlayEvent("input", "release", 30, 330))
        self.assertEqual(native.activation_calls, 1)
        self.assertIsNone(overlay.pressed)
        self.assertEqual(app.input.events[-1][1]["state"], 0x100)

    def test_input_cancel_releases_tk_button_state_without_clearing_draft_or_reactivating(self):
        overlay, app, native = self.make_overlay()
        overlay.handle(OverlayEvent("input", "press", 30, 330))
        overlay.handle(OverlayEvent("input", "motion", 40, 330))
        self.assertEqual(app.input.events[-1][1]["state"], 0x100)
        overlay.handle(OverlayEvent("input", "cancel", 700, 700))
        self.assertEqual(app.input.events[-1][0], "<ButtonRelease-1>")
        self.assertEqual(app.input.events[-1][1]["state"], 0x100)
        self.assertIsNone(overlay.pressed)
        self.assertEqual(native.activation_calls, 1)

    def test_rejected_input_activation_does_not_focus_or_deliver_typing_events(self):
        overlay, app, native = self.make_overlay()
        native.allow_activation = False
        overlay.handle(OverlayEvent("input", "press", 30, 330))
        self.assertEqual(native.activation_calls, 1)
        self.assertEqual(app.input.focus_calls, 0)
        self.assertEqual(app.input.events, [])
        self.assertIsNone(overlay.pressed)
        app.status.set.assert_called_once()

    def test_button_click_invokes_without_focus_and_release_outside_cancels(self):
        overlay, app, native = self.make_overlay()
        for action in ("press", "release"):
            overlay.handle(OverlayEvent("button", action, 260, 40))
        self.assertEqual(app.button.invoke_calls, 1)
        self.assertEqual(app.button.states[-2:], [["pressed"], ["!pressed"]])
        overlay.handle(OverlayEvent("button", "press", 260, 40))
        overlay.handle(OverlayEvent("button", "release", 300, 40))
        self.assertEqual(app.button.invoke_calls, 1)
        self.assertEqual(native.activation_calls, 0)
        self.assertEqual(app.button.focus_calls, 0)
        self.assertEqual(app.button.events, [])

    def test_hover_wheel_accumulates_partial_deltas_without_taking_keyboard(self):
        overlay, app, native = self.make_overlay()
        for delta in (30, 60):
            overlay.handle(OverlayEvent("", "wheel", 30, 90, delta))
        self.assertEqual(app.chat.scrolls, [])
        self.assertEqual(overlay.wheel_remainder, 90)
        overlay.handle(OverlayEvent("", "wheel", 30, 90, 30))
        for delta in (-40, -40, -40):
            overlay.handle(OverlayEvent("", "wheel", 30, 90, delta))
        self.assertEqual(app.chat.scrolls, [(-3, "units"), (3, "units")])
        self.assertEqual(overlay.wheel_remainder, 0)
        self.assertEqual(native.activation_calls, 0)
        self.assertEqual(app.chat.focus_calls, 0)
        self.assertEqual(app.input.focus_calls, 0)

    def test_drag_tracks_motion_and_final_release_using_native_screen_bounds(self):
        overlay, app, native = self.make_overlay()
        app.interactive_widgets.append(app.drag_handle)
        overlay.update_layout()
        native.bounds = (-640, -200, 640, 760)  # Deliberately different from stale Tk geometry.
        overlay.handle(OverlayEvent("drag", "press", 30, 40))
        overlay.handle(OverlayEvent("drag", "motion", 70, 60))
        overlay.handle(OverlayEvent("drag", "release", 100, 80))
        self.assertEqual(native.moves, [(-600, -180, 640, 760), (-570, -160, 640, 760)])
        self.assertIsNone(overlay.drag)
        self.assertIsNone(overlay.pressed)
        self.assertEqual(native.activation_calls, 0)

    def test_ordinary_chat_and_scrollbar_wheel_work_without_focus_or_double_scroll(self):
        overlay, app, native = self.make_overlay()
        event = SimpleNamespace(delta=120)
        self.assertIsNone(app.chat.bindings["<MouseWheel>"](event))
        self.assertEqual(app.chat.scrolls, [])  # Native overlay owns this path.
        overlay.native = None
        self.assertEqual(app.chat.bindings["<MouseWheel>"](event), "break")
        self.assertEqual(app.chat.vbar.bindings["<MouseWheel>"](SimpleNamespace(delta=-120)), "break")
        self.assertEqual(app.chat.scrolls, [(-3, "units"), (3, "units")])
        self.assertEqual(app.chat.focus_calls, 0)
        self.assertEqual(app.input.focus_calls, 0)
        self.assertEqual(native.activation_calls, 0)
        overlay.closed = True
        self.assertIsNone(overlay.ordinary_wheel(event))
        self.assertEqual(len(app.chat.scrolls), 2)

    def test_fast_drag_applies_release_position_even_without_any_motion_event(self):
        overlay, app, native = self.make_overlay()
        app.interactive_widgets.append(app.drag_handle)
        overlay.update_layout()
        overlay.handle(OverlayEvent("drag", "press", 30, 40))
        overlay.handle(OverlayEvent("drag", "release", 80, 100))
        self.assertEqual(native.moves, [(60, 80, 320, 380)])
        self.assertEqual(native.activation_calls, 0)

    def test_resize_clamps_minimum_and_cancel_ends_drag_without_moving_or_focusing(self):
        overlay, app, native = self.make_overlay()
        app.interactive_widgets.extend((app.drag_handle, app.resize_handle))
        overlay.update_layout()
        overlay.handle(OverlayEvent("resize", "press", 30, 40))
        overlay.handle(OverlayEvent("resize", "motion", -1000, -1000))
        self.assertEqual(native.moves, [(10, 20, 280, 280)])
        overlay.handle(OverlayEvent("resize", "cancel", -1000, -1000))
        overlay.handle(OverlayEvent("resize", "release", 1000, 1000))
        self.assertEqual(len(native.moves), 1)
        self.assertIsNone(overlay.drag)
        self.assertIsNone(overlay.pressed)
        self.assertEqual(native.activation_calls, 0)

    def test_drag_icon_still_works_in_ordinary_window_fallback(self):
        overlay, app, native = self.make_overlay()
        overlay.native = None
        overlay.failed = True
        handle = app.drag_handle
        handle.bindings["<ButtonPress-1>"](SimpleNamespace(x_root=30, y_root=40))
        handle.bindings["<B1-Motion>"](SimpleNamespace(x_root=-10, y_root=-20))
        handle.bindings["<ButtonRelease-1>"](SimpleNamespace(x_root=-30, y_root=-30))
        self.assertEqual(app.root.geometries, ["320x380+-30+-40", "320x380+-50+-50"])
        self.assertIsNone(overlay.fallback_drag)
        self.assertEqual(native.activation_calls, 0)

    def test_native_drag_does_not_also_run_tk_fallback_and_targets_survive_layout_refresh(self):
        overlay, app, native = self.make_overlay()
        app.interactive_widgets.append(app.drag_handle)
        overlay.update_layout()
        app.drag_handle.bindings["<ButtonPress-1>"](SimpleNamespace(x_root=30, y_root=40))
        self.assertIsNone(overlay.fallback_drag)
        overlay.handle(OverlayEvent("drag", "press", 30, 40))
        overlay.handle(OverlayEvent("drag", "motion", 50, 60))
        app.root.rect = (30, 40, 350, 420)
        app.drag_handle.rect = (40, 50, 100, 70)
        overlay.configured(SimpleNamespace(widget=app.root))
        overlay.update_layout()
        self.assertEqual(next(t.rect for t in native.targets if t.key == "drag"), (40, 50, 100, 70))
        self.assertEqual(overlay.pressed, "drag")
        overlay.handle(OverlayEvent("drag", "release", 70, 80))
        self.assertEqual(native.moves[-1], (50, 60, 320, 380))
        self.assertEqual(app.root.geometries, [])

    def test_source_link_opens_without_chat_focus_or_text_pointer_events(self):
        overlay, app, native = self.make_overlay()
        key = "link-2:1.0:0"
        overlay.widgets[key] = (app.chat, "link")
        overlay.hit_rects[key] = (20, 80, 130, 100)
        for action in ("press", "release"):
            overlay.handle(OverlayEvent(key, action, 30, 90))
        app.open_source.assert_called_once_with("link-2")
        overlay.handle(OverlayEvent(key, "press", 30, 90))
        overlay.handle(OverlayEvent(key, "release", 150, 90))
        app.open_source.assert_called_once_with("link-2")
        self.assertEqual(app.chat.events, [])
        self.assertEqual(app.chat.focus_calls, 0)
        self.assertEqual(native.activation_calls, 0)

    def test_escape_explicitly_releases_keyboard_via_input_binding(self):
        overlay, app, native = self.make_overlay()
        result = app.input.bindings["<Escape>"]()
        self.assertEqual(result, "break")
        self.assertEqual(native.release_calls, 1)
        self.assertEqual(native.activation_calls, 0)
        overlay.native = None
        self.assertEqual(overlay.release_input(), "break")

    def test_failed_backend_restores_normal_window_and_stops_refresh(self):
        overlay, app, _ = self.make_overlay()
        overlay.native = None
        backend = mock.Mock()
        backend.start.return_value = False
        scheduled = len(app.root.scheduled)
        with mock.patch("companion.overlay_ui.sys.platform", "win32"), \
                mock.patch("companion.windows_overlay.WindowsOverlay", return_value=backend):
            overlay.refresh()
        self.assertTrue(overlay.failed)
        self.assertIsNone(overlay.native)
        self.assertEqual(app.root.decorations, [True, False])
        backend.close.assert_called_once_with()
        backend.activate_input.assert_not_called()
        app.status.set.assert_called_once_with("Click-through mode could not start. Restored normal window behavior.")
        self.assertEqual(len(app.root.scheduled), scheduled)

    def test_layout_excludes_plain_chat_and_hidden_or_outside_widgets(self):
        overlay, app, native = self.make_overlay()
        app.interactive_widgets += [FakeWidget("hidden", visible=False),
                                    FakeWidget("outside", (500, 600, 520, 620)),
                                    FakeWidget("partial", (300, 380, 400, 500))]
        overlay.update_layout()
        targets = {target.key: target for target in native.targets}
        self.assertEqual(set(targets), {"input", "button", "scrollbar", "partial"})
        self.assertEqual(targets["partial"].rect, (300, 380, 330, 400))
        self.assertEqual(targets["input"].kind, "input")
        self.assertEqual(targets["scrollbar"].kind, "scrollbar")
        self.assertEqual(native.scroll_rects, ((20, 65, 305, 310), (305, 65, 315, 310)))
        self.assertNotIn("chat", targets)

    def test_hidden_scrollbar_and_collapsed_chat_are_not_wheel_targets(self):
        overlay, app, native = self.make_overlay()
        app.chat.vbar.visible = False
        overlay.update_layout()
        self.assertEqual(native.scroll_rects, ((20, 65, 305, 310),))
        app.collapsed = True
        overlay.update_layout()
        self.assertEqual(native.scroll_rects, ())


if __name__ == "__main__":
    unittest.main()
