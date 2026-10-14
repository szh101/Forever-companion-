"""Synthetic input routing only: no Windows hooks, windows, or real input."""
import ctypes
from ctypes import wintypes
import queue
import threading
import time
import unittest
from unittest import mock

from companion.windows_overlay import OverlayEvent, OverlayTarget, WindowsOverlay, _Win32


class FakeRoot:
    def __init__(self, mapped=True):
        self.mapped, self.scheduled, self.cancelled = mapped, [], []

    def winfo_ismapped(self):
        return self.mapped

    def winfo_id(self):
        return 11

    def after(self, milliseconds, callback):
        self.scheduled.append((milliseconds, callback))
        return str(len(self.scheduled))

    def after_cancel(self, identifier):
        self.cancelled.append(identifier)


class FakeAPI:
    hwnd = 10

    def __init__(self):
        self.calls = []
        self.visible = True

    def start(self, *args, **kwargs):
        self.calls.append(("start", args))
        self.outside_press = kwargs.get("outside_press")

    def close(self):
        self.calls.append(("close",))

    def update_targets(self, *args):
        self.calls.append(("targets", args))

    def unobscured(self, x, y):
        self.calls.append(("unobscured", x, y))
        return self.visible

    def foreground_identity(self):
        return (900, 1234)

    def activate_input(self):
        self.calls.append(("activate",))
        return True

    def restore_focus(self, previous):
        self.calls.append(("restore", previous))
        return True

    def clicked_previous_window(self, previous, x, y):
        self.calls.append(("clicked", previous, x, y))
        return x >= 200

    def end_input_on_click(self, previous, x, y):
        self.calls.append(("end_input", previous, x, y))
        return True

    def set_opacity(self, value):
        self.calls.append(("opacity", value))

    def move_resize(self, *args):
        self.calls.append(("move", args))

    def poll_pointer(self):
        pass


class OverlayTests(unittest.TestCase):
    def make_overlay(self, mapped=True):
        root, api, events, errors = FakeRoot(mapped), FakeAPI(), [], []
        overlay = WindowsOverlay(root, events.append, errors.append, api=api)
        overlay.update_targets([OverlayTarget("input", (0, 50, 100, 100), "input"),
                                OverlayTarget("button", (100, 50, 130, 80))],
                               scroll_rects=[(0, 0, 130, 50)])
        return overlay, api, events, errors

    def test_hidden_window_never_initializes_native_backend(self):
        overlay, api, _, _ = self.make_overlay(False)
        self.assertFalse(overlay.start())
        self.assertEqual(api.calls, [])
        self.assertEqual(overlay.root.scheduled, [])
        with mock.patch("companion.windows_overlay._Win32") as constructor:
            self.assertFalse(WindowsOverlay(FakeRoot(False), lambda _: None).start())
            constructor.assert_not_called()

    def test_passive_wheel_is_scoped_and_queued_without_focus_calls(self):
        overlay, api, events, _ = self.make_overlay()
        self.assertTrue(overlay.start())
        self.assertFalse(overlay._wheel(200, 200, 120))
        self.assertTrue(overlay._wheel(20, 20, -120))
        self.assertEqual(events, [])
        overlay._pump()
        self.assertEqual(events, [OverlayEvent("", "wheel", 20, 20, -120)])
        self.assertFalse(any(c[0] in ("activate", "restore") for c in api.calls))
        api.visible = False
        self.assertFalse(overlay._wheel(20, 20, 120))

    def test_queue_pressure_or_visibility_error_does_not_swallow_wheel(self):
        overlay, api, _, _ = self.make_overlay()
        overlay.start()
        for _ in range(128):
            overlay.events.put_nowait((time.monotonic(), OverlayEvent("", "wheel", 20, 20, 120)))
        self.assertFalse(overlay._wheel(20, 20, 120))
        api.unobscured = mock.Mock(side_effect=OSError("unavailable"))
        self.assertFalse(overlay._wheel(20, 20, 120))

    def test_button_events_never_activate_or_record_a_focus_target(self):
        overlay, api, events, _ = self.make_overlay()
        overlay.start()
        overlay._enqueue(OverlayEvent("button", "press", 110, 60))
        overlay._enqueue(OverlayEvent("button", "release", 110, 60))
        overlay._pump()
        self.assertEqual([e.action for e in events], ["press", "release"])
        self.assertIsNone(overlay.previous_focus)
        self.assertFalse(any(c[0] == "activate" for c in api.calls))

    def test_input_activation_and_restore_are_explicit_ui_actions(self):
        overlay, api, _, _ = self.make_overlay()
        overlay.start()
        overlay._enqueue(OverlayEvent("input", "press", 20, 60))
        self.assertEqual(overlay.previous_focus, (900, 1234))
        self.assertNotIn(("activate",), api.calls)
        self.assertTrue(overlay.activate_input())
        self.assertTrue(overlay.release_input())
        self.assertIn(("restore", (900, 1234)), api.calls)
        self.assertIsNone(overlay.previous_focus)

    def test_first_outside_down_releases_input_on_ui_thread_and_keeps_hover_neutral(self):
        overlay, api, events, _ = self.make_overlay()
        overlay.start()
        overlay._enqueue(OverlayEvent("input", "press", 20, 60))
        overlay._pump()
        self.assertTrue(overlay.activate_input())
        overlay._enqueue(OverlayEvent("input", "leave", 0, 0))
        overlay._pump()
        self.assertIsNotNone(overlay.input_session)  # Moving away still permits typing.
        api.outside_press(200, 200)
        self.assertIsNone(overlay.input_session)
        self.assertFalse(any(c[0] == "end_input" for c in api.calls))
        overlay._pump()
        self.assertEqual([c for c in api.calls if c[0] == "end_input"],
                         [("end_input", (900, 1234), 200, 200)])
        self.assertIsNone(overlay.previous_focus)
        self.assertEqual(events[-1].action, "cancel")
        api.outside_press(210, 210)
        overlay._pump()
        self.assertEqual(len([c for c in api.calls if c[0] == "end_input"]), 1)

    def test_outside_down_cancels_pending_input_activation_without_second_click(self):
        overlay, api, events, _ = self.make_overlay()
        overlay.start()
        overlay._enqueue(OverlayEvent("input", "press", 20, 60))
        api.outside_press(200, 200)  # Happens before Tk handles that first press.
        self.assertFalse(overlay._enqueue(OverlayEvent("input", "press", 200, 200)))
        overlay._pump()
        self.assertFalse(overlay.activate_input())
        self.assertEqual([e.action for e in events], ["cancel"])
        self.assertNotIn(("activate",), api.calls)

    def test_new_input_click_supersedes_older_outside_focus_handoff(self):
        overlay, api, events, _ = self.make_overlay()
        overlay.start()
        overlay._enqueue(OverlayEvent("input", "press", 20, 60))
        api.outside_press(200, 200)
        overlay._enqueue(OverlayEvent("input", "press", 30, 60))
        overlay._pump()
        self.assertEqual([e.action for e in events], ["press"])
        self.assertEqual(events[0].x, 30)
        self.assertFalse(any(c[0] == "end_input" for c in api.calls))
        self.assertTrue(overlay.activate_input())

    def test_other_window_click_suspend_and_expired_outside_event_do_not_restore_focus(self):
        overlay, api, events, _ = self.make_overlay()
        overlay.start()
        api.outside_press(200, 200)  # No input session.
        self.assertFalse(any(c[0] == "clicked" for c in api.calls))
        overlay._enqueue(OverlayEvent("input", "press", 20, 60))
        api.outside_press(100, 200)  # Different target window.
        self.assertIsNotNone(overlay.input_session)
        api.outside_press(200, 200)
        _, session, x, y = overlay.pending_focus_release
        overlay.pending_focus_release = (time.monotonic() - 2, session, x, y)
        overlay._pump()
        self.assertFalse(any(c[0] == "end_input" for c in api.calls))
        overlay._enqueue(OverlayEvent("input", "press", 20, 60))
        overlay.set_suspended(True)
        api.outside_press(200, 200)
        overlay._pump()
        self.assertFalse(any(c[0] == "end_input" for c in api.calls))

    def test_stale_removed_and_suspended_events_do_not_dispatch(self):
        overlay, api, events, _ = self.make_overlay()
        overlay.start()
        overlay.events.put((time.monotonic() - 2, OverlayEvent("input", "press", 20, 60)))
        overlay.events.put((time.monotonic(), OverlayEvent("removed", "press", 20, 60)))
        overlay._pump()
        self.assertEqual(events, [])
        overlay.set_suspended(True)
        self.assertFalse(overlay._wheel(20, 20, 120))
        self.assertFalse(overlay._enqueue(OverlayEvent("input", "press", 20, 60)))
        self.assertFalse(overlay.activate_input())

    def test_region_and_opacity_bounds_reject_invisible_or_unbounded_targets(self):
        overlay, api, _, _ = self.make_overlay()
        for targets in ([OverlayTarget("x", (0, 0, 0, 10))],
                        [OverlayTarget("x", (0, 0, 20, 10), "keyboard")],
                        [OverlayTarget("x", (0, 0, 20, 10))] * 2,
                        [OverlayTarget("x", (0, 0, 20000, 10))]):
            with self.assertRaises(ValueError):
                overlay.update_targets(targets)
        for opacity in (0, 0.44, 1.1, float("nan")):
            with self.assertRaises(ValueError):
                overlay.set_opacity(opacity)
        overlay.start()
        overlay.set_opacity(1.0)
        overlay.move_resize(-500, 40, 300, 400)
        self.assertIn(("opacity", 1.0), api.calls)
        self.assertIn(("move", (-500, 40, 300, 400)), api.calls)

    def test_failure_restores_ordinary_window_and_close_is_idempotent(self):
        overlay, api, _, errors = self.make_overlay()
        api.start = mock.Mock(side_effect=OSError("no hooks"))
        self.assertFalse(overlay.start())
        self.assertEqual(api.calls, [("close",)])
        self.assertEqual(len(errors), 1)
        overlay.close()
        self.assertEqual(api.calls, [("close",)])

    def test_callback_error_closes_backend_instead_of_leaving_dead_hit_windows(self):
        overlay, api, _, errors = self.make_overlay()
        overlay.start()
        overlay.on_event = mock.Mock(side_effect=RuntimeError("broken UI"))
        overlay._enqueue(OverlayEvent("button", "press", 110, 60))
        overlay._pump()
        self.assertFalse(overlay.active)
        self.assertIn(("close",), api.calls)
        self.assertTrue(errors)

    def test_close_from_button_callback_never_schedules_again(self):
        overlay, _, _, _ = self.make_overlay()
        overlay.start()
        overlay.on_event = lambda _: overlay.close()
        overlay._enqueue(OverlayEvent("button", "release", 110, 60))
        scheduled = len(overlay.root.scheduled)
        overlay._pump()
        self.assertEqual(len(overlay.root.scheduled), scheduled)

    def test_hover_is_coalesced_and_leave_cancels_pending_hover(self):
        overlay, _, events, _ = self.make_overlay()
        overlay.start()
        for n in range(1000):
            overlay._enqueue(OverlayEvent("button", "hover", n, 60))
        self.assertEqual(len(overlay.hover_events), 1)
        self.assertEqual(overlay.events.qsize(), 0)
        overlay._enqueue(OverlayEvent("button", "leave", 0, 0))
        overlay._pump()
        self.assertEqual(events, [OverlayEvent("button", "leave", 0, 0)])

    def test_drag_motion_is_coalesced_but_delivered_before_its_release(self):
        overlay, _, events, _ = self.make_overlay()
        overlay.start()
        overlay._enqueue(OverlayEvent("button", "press", 110, 60))
        for x in range(200):
            overlay._enqueue(OverlayEvent("button", "motion", x, 60))
        overlay._enqueue(OverlayEvent("button", "release", 400, 60))
        overlay._pump()
        self.assertEqual([e.action for e in events], ["press", "motion", "release"])
        self.assertEqual(events[1].x, 199)


class NativePolicyTests(unittest.TestCase):
    def native(self):
        # Bypass _Win32.__init__: all native calls below are mocks, even on Windows.
        api = _Win32.__new__(_Win32)
        api.c, api.w = ctypes, wintypes
        api.hwnd, api.handles = 10, {11: "button"}
        api.owner_pid = 1234
        api.pointer_lock = threading.Lock()
        api.pointer_session = None
        api.pointer_position = None
        api.outside_press = None
        api.user = mock.Mock()
        api.user.IsWindowVisible.return_value = True
        api.user.IsIconic.return_value = False
        api.user.IsWindow.return_value = True
        api.user.GetForegroundWindow.return_value = 10
        api.user.SetForegroundWindow.return_value = True
        api.user.GetWindowLongPtrW.return_value = 0
        def rectangle(_hwnd, ptr):
            ptr._obj.left = ptr._obj.top = 0
            ptr._obj.right = ptr._obj.bottom = 500
            return True
        api.user.GetWindowRect.side_effect = rectangle
        api._pid = mock.Mock(return_value=1234)
        return api

    def hook_callback(self, api):
        # Exercise the actual closure without loading any native library,
        # registering a hook, starting a thread, or observing system input.
        api.kernel = mock.Mock()
        api.kernel.GetCurrentThreadId.return_value = 55
        api.hook_type = lambda callback: callback
        api.module, api.stopped, api.pointer_session = 1, False, None
        api.user.SetWindowsHookExW.return_value = 44
        api.user.GetMessageW.return_value = 0
        api.user.CallNextHookEx.return_value = 77
        api._hook_loop(threading.Event())
        api.user.UnhookWindowsHookEx.assert_called_once_with(44)
        return api.hook_callback

    @staticmethod
    def mouse_data(x, y, delta, flags=0):
        class MouseData(ctypes.Structure):
            _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]
        return MouseData(wintypes.POINT(x, y), (delta & 0xFFFF) << 16, flags, 0, 0)

    def test_hook_accepts_driver_wheel_flags_and_signed_partial_deltas(self):
        api = self.native()
        callback = self.hook_callback(api)
        api.wheel = mock.Mock(return_value=True)
        for flags in (0, 1, 2, 3):
            for delta in (120, 30, -40, -120):
                with self.subTest(flags=flags, delta=delta):
                    data = self.mouse_data(-640, -200, delta, flags)
                    self.assertEqual(callback(0, 0x20A, ctypes.addressof(data)), 1)
                    api.wheel.assert_called_once_with(-640, -200, delta)
                    api.wheel.reset_mock()
        api.user.CallNextHookEx.assert_not_called()
        api.user.SetForegroundWindow.assert_not_called()

    def test_hook_rejection_exception_and_unrelated_events_pass_through(self):
        api = self.native()
        callback = self.hook_callback(api)
        data = self.mouse_data(20, 20, 120, 1)
        address = ctypes.addressof(data)
        api.wheel = mock.Mock(return_value=False)
        self.assertEqual(callback(0, 0x20A, address), 77)
        api.wheel.side_effect = RuntimeError("routing unavailable")
        self.assertEqual(callback(0, 0x20A, address), 77)
        api.wheel.reset_mock(side_effect=True)
        zero = self.mouse_data(20, 20, 0)
        self.assertEqual(callback(0, 0x20A, ctypes.addressof(zero)), 77)
        self.assertEqual(callback(-1, 0x20A, 0), 77)
        for message in (0x200, 0x201, 0x202, 0x20E):
            self.assertEqual(callback(0, message, 0), 77)
        api.stopped = True
        self.assertEqual(callback(0, 0x20A, 0), 77)
        api.wheel.assert_not_called()
        self.assertEqual(api.user.CallNextHookEx.call_count, 9)
        api.user.SetForegroundWindow.assert_not_called()

    def test_outside_down_observation_never_consumes_or_replays_click(self):
        api = self.native()
        callback = self.hook_callback(api)
        api.outside_press = mock.Mock(return_value=True)
        for message in (0x201, 0x204, 0x207, 0x20B):
            data = self.mouse_data(-640, -200, 0, 1)
            self.assertEqual(callback(0, message, ctypes.addressof(data)), 77)
            api.outside_press.assert_called_once_with(-640, -200)
            api.outside_press.reset_mock()
        api.outside_press.side_effect = RuntimeError("queue unavailable")
        self.assertEqual(callback(0, 0x201, ctypes.addressof(data)), 77)
        self.assertEqual(api.user.CallNextHookEx.call_count, 5)
        api.user.SetForegroundWindow.assert_not_called()
        api.user.ReleaseCapture.assert_not_called()
        api.user.SetFocus.assert_not_called()

    def test_outside_observer_ignores_hover_up_and_own_control_drag(self):
        api = self.native()
        callback = self.hook_callback(api)
        api.outside_press = mock.Mock()
        for message in (0x200, 0x202):
            self.assertEqual(callback(0, message, 0), 77)
        api.pointer_session = ("button", 11, time.monotonic())
        for message in (0x201, 0x204, 0x207, 0x20B):
            self.assertEqual(callback(0, message, 0), 77)
        api.outside_press.assert_not_called()
        api.user.SetForegroundWindow.assert_not_called()

    def test_native_wheel_fallback_uses_signed_screen_coordinates_without_focus(self):
        api = self.native()
        api.wheel = mock.Mock(return_value=True)
        api.user.DefWindowProcW.return_value = 73
        wp = ((-40 & 0xFFFF) << 16) | 8
        lp = (-640 & 0xFFFF) | ((-200 & 0xFFFF) << 16)
        self.assertEqual(api._window_proc(11, 0x20A, wp, lp), 0)
        api.wheel.assert_called_once_with(-640, -200, -40)
        api.user.DefWindowProcW.assert_not_called()
        api.user.ClientToScreen.assert_not_called()
        api.user.SetForegroundWindow.assert_not_called()
        api.wheel.reset_mock()
        self.assertEqual(api._window_proc(99, 0x20A, wp, lp), 73)
        self.assertEqual(api._window_proc(11, 0x20A, 0, lp), 73)
        api.wheel.assert_not_called()
        api.wheel.return_value = False
        self.assertEqual(api._window_proc(11, 0x20A, wp, lp), 73)
        api.wheel.side_effect = RuntimeError("routing unavailable")
        self.assertEqual(api._window_proc(11, 0x20A, wp, lp), 73)
        self.assertEqual(api.user.DefWindowProcW.call_count, 4)

    def test_hook_and_native_fallback_share_chat_visibility_and_suspend_checks(self):
        api = self.native()
        callback = self.hook_callback(api)
        root, routing_api, events = FakeRoot(), FakeAPI(), []
        overlay = WindowsOverlay(root, events.append, api=routing_api)
        overlay.update_targets([], scroll_rects=[(0, 0, 130, 50)])
        overlay.start()
        api.wheel = overlay._wheel
        api.user.DefWindowProcW.return_value = 73
        cases = ((20, 20, True, False, True), (20, 60, True, False, False),
                 (20, 20, False, False, False), (20, 20, True, True, False))
        for x, y, visible, suspended, accepted in cases:
            with self.subTest(x=x, y=y, visible=visible, suspended=suspended):
                routing_api.visible = visible
                overlay.set_suspended(suspended)
                data = self.mouse_data(x, y, 120, 1)
                self.assertEqual(callback(0, 0x20A, ctypes.addressof(data)), 1 if accepted else 77)
                self.assertEqual(api._window_proc(11, 0x20A, 120 << 16, x | (y << 16)),
                                 0 if accepted else 73)
                overlay._pump()
        # These are two independent input events, one on each delivery path.
        self.assertEqual(events, [OverlayEvent("", "wheel", 20, 20, 120)] * 2)
        self.assertFalse(any(call[0] in ("activate", "restore") for call in routing_api.calls))
        api.user.SetForegroundWindow.assert_not_called()

    def test_focus_restore_rejects_reused_handle_or_new_foreground(self):
        api = self.native()
        self.assertTrue(api.restore_focus((900, 1234)))
        api.user.SetForegroundWindow.assert_called_once_with(900)
        api.user.SetForegroundWindow.reset_mock()
        api._pid.return_value = 8888
        self.assertFalse(api.restore_focus((900, 1234)))
        api._pid.return_value = 1234
        api.user.GetForegroundWindow.return_value = 777
        self.assertFalse(api.restore_focus((900, 1234)))
        api.user.SetForegroundWindow.assert_not_called()

    def focus_native(self):
        api = self.native()
        api._pid.side_effect = lambda hwnd: (1234 if hwnd in (10, 11, 12, 20)
                                             else 5678 if hwnd in (900, 901) else 8888)
        api.user.WindowFromPoint.return_value = 901
        api.user.GetAncestor.side_effect = lambda hwnd, _: {12: 10, 901: 900}.get(hwnd, hwnd)
        api.user.GetCapture.return_value = 12
        api.user.GetFocus.return_value = 12
        api.enqueue = mock.Mock(return_value=True)
        return api

    def test_clicked_previous_requires_actual_window_and_saved_external_identity(self):
        api = self.focus_native()
        self.assertTrue(api.clicked_previous_window((900, 5678), -640, -200))
        point = api.user.WindowFromPoint.call_args.args[0]
        self.assertEqual((point.x, point.y), (-640, -200))
        # Our own controls/settings and an intervening external app are never
        # treated as the old foreground merely because its rectangle overlaps.
        for hit in (0, 10, 11, 12, 20, 777):
            api.user.WindowFromPoint.return_value = hit
            self.assertFalse(api.clicked_previous_window((900, 5678), 20, 20))
        api.user.WindowFromPoint.return_value = 901
        self.assertFalse(api.clicked_previous_window((900, 7777), 20, 20))
        self.assertFalse(api.clicked_previous_window((20, 1234), 20, 20))
        self.assertFalse(api.clicked_previous_window(None, 20, 20))
        for function, bad in (("IsWindow", False), ("IsWindowVisible", False), ("IsIconic", True)):
            with mock.patch.object(api.user, function, return_value=bad):
                self.assertFalse(api.clicked_previous_window((900, 5678), 20, 20))
        api.user.SetForegroundWindow.assert_not_called()

    def test_first_click_clears_only_main_input_and_hands_off_on_gui_thread(self):
        api = self.focus_native()
        self.assertTrue(api.end_input_on_click((900, 5678), 20, 20))
        api.user.ReleaseCapture.assert_called_once_with()
        api.user.SetFocus.assert_called_once_with(None)
        api.user.SetForegroundWindow.assert_called_once_with(900)
        calls = api.user.mock_calls
        self.assertLess(calls.index(mock.call.SetFocus(None)), calls.index(mock.call.SetForegroundWindow(900)))
        self.assertEqual(api.user.WindowFromPoint.call_count, 2)

    def test_natural_first_click_activation_needs_no_second_focus_request(self):
        api = self.focus_native()
        api.user.GetForegroundWindow.return_value = 900
        self.assertTrue(api.end_input_on_click((900, 5678), 20, 20))
        api.user.ReleaseCapture.assert_called_once_with()
        api.user.SetFocus.assert_called_once_with(None)
        api.user.SetForegroundWindow.assert_not_called()

    def test_outside_handoff_preserves_dialog_or_foreign_capture_and_focus(self):
        for captured in (0, 20, 777):
            with self.subTest(captured=captured):
                api = self.focus_native()
                api.user.GetCapture.return_value = captured
                api.user.GetFocus.return_value = captured
                self.assertTrue(api.end_input_on_click((900, 5678), 20, 20))
                api.user.ReleaseCapture.assert_not_called()
                api.user.SetFocus.assert_not_called()

    def test_outside_handoff_rejects_new_foreground_or_reused_target(self):
        api = self.focus_native()
        api.user.GetForegroundWindow.return_value = 777
        self.assertFalse(api.end_input_on_click((900, 5678), 20, 20))
        api.user.ReleaseCapture.assert_not_called()
        api.user.SetFocus.assert_not_called()
        api.user.SetForegroundWindow.assert_not_called()
        api.user.GetForegroundWindow.side_effect = [10, 777]
        self.assertFalse(api.end_input_on_click((900, 5678), 20, 20))
        api.user.SetForegroundWindow.assert_not_called()
        api = self.focus_native()
        api._pid.side_effect = lambda hwnd: 1234 if hwnd in (10, 12) else 8888
        self.assertFalse(api.end_input_on_click((900, 5678), 20, 20))
        api.user.ReleaseCapture.assert_not_called()
        api.user.SetFocus.assert_not_called()
        api.user.SetForegroundWindow.assert_not_called()

    def test_handoff_cancels_stale_own_press_and_rechecks_before_activation(self):
        api = self.focus_native()
        api.pointer_session = ("button", 11, time.monotonic())
        api.pointer_position = (20, 30)
        api.user.WindowFromPoint.side_effect = [901, 777]
        self.assertFalse(api.end_input_on_click((900, 5678), 20, 20))
        self.assertIsNone(api.pointer_session)
        api.enqueue.assert_called_once_with(OverlayEvent("button", "cancel", 20, 30))
        api.user.SetForegroundWindow.assert_not_called()

    def test_occlusion_walk_ignores_owned_islands_and_transparent_layers(self):
        api = self.native()
        order = {10: 11, 11: 20, 20: 0}
        api.user.GetWindow.side_effect = lambda hwnd, _: order[hwnd]
        api.user.GetWindowLongPtrW.return_value = api.LAYERED | api.TRANSPARENT
        self.assertTrue(api.unobscured(20, 20))
        self.assertEqual(api.user.GetWindowRect.call_count, 1)  # Our own bounds only.
        api.user.GetWindowLongPtrW.return_value = 0

        def rect(hwnd, ptr):
            ptr._obj.left = ptr._obj.top = 0
            ptr._obj.right = ptr._obj.bottom = 500 if hwnd == 10 else 100
            return True
        api.user.GetWindowRect.side_effect = rect
        self.assertFalse(api.unobscured(20, 20))
        self.assertTrue(api.unobscured(200, 200))

    def test_occlusion_walk_fails_open_for_game_on_bad_or_looping_metadata(self):
        api = self.native()
        api.user.GetWindow.return_value = 20
        api.user.GetWindowRect.side_effect = None
        api.user.GetWindowRect.return_value = False
        self.assertFalse(api.unobscured(20, 20))
        api.user.GetWindowLongPtrW.return_value = api.LAYERED | api.TRANSPARENT
        self.assertFalse(api.unobscured(20, 20))

    def test_inactive_drag_observes_outside_motion_and_release_only_after_own_press(self):
        api = self.native()
        events = []
        api.enqueue = events.append
        api.pointer_session = None
        api._observe_pointer(0x200, 2000, 2000)
        self.assertEqual(events, [])
        api.pointer_session = ("button", 11, time.monotonic())
        api._observe_pointer(0x200, 2000, 2000)
        api._observe_pointer(0x202, 2000, 2000)
        self.assertEqual([e.action for e in events], ["motion", "release"])
        self.assertIsNone(api.pointer_session)
        api._observe_pointer(0x200, 3000, 3000)
        self.assertEqual(len(events), 2)
        api.pointer_session = ("button", 11, time.monotonic() - 31)
        api._observe_pointer(0x200, 3000, 3000)
        self.assertEqual(events[-1].action, "cancel")
        self.assertIsNone(api.pointer_session)

    def test_drag_sampling_survives_missing_hook_and_deduplicates_release(self):
        api = self.native()
        events = []
        api.enqueue = lambda event: events.append(event) or True
        api.pointer_session = None
        api.poll_pointer()
        api.user.GetCursorPos.assert_not_called()
        api.user.GetAsyncKeyState.assert_not_called()

        def position(pointer):
            pointer._obj.x, pointer._obj.y = -500, 800
            return True
        api.user.GetCursorPos.side_effect = position
        api.user.GetSystemMetrics.return_value = 0
        api.user.GetAsyncKeyState.return_value = 0x8000
        api.pointer_session = ("button", 11, time.monotonic())
        api.pointer_position = (20, 20)
        api.poll_pointer()  # No low-level hook callback involved.
        api.poll_pointer()  # Same location should not trigger repeated moves.
        self.assertEqual(events, [OverlayEvent("button", "motion", -500, 800)])
        api.user.GetAsyncKeyState.return_value = 0
        api.poll_pointer()
        self.assertEqual(events[-1], OverlayEvent("button", "release", -500, 800))
        self.assertIsNone(api.pointer_session)
        self.assertFalse(api._observe_pointer(0x202, -500, 800))
        self.assertEqual(len(events), 2)
        self.assertTrue(all(call.args == (1,) for call in api.user.GetAsyncKeyState.call_args_list))
        api.user.SetForegroundWindow.assert_not_called()

    def test_real_control_message_starts_drag_without_requiring_hook_messages(self):
        api = self.native()
        events = []
        api.enqueue = lambda event: events.append(event) or True
        api.pointer_session = None
        api.handles = {11: "drag"}
        api.user.GetSystemMetrics.return_value = 0
        api.user.GetAsyncKeyState.return_value = 0x8000
        def client_to_screen(_hwnd, pointer):
            pointer._obj.x += 100
            pointer._obj.y += 200
            return True
        def cursor(pointer):
            pointer._obj.x, pointer._obj.y = 300, 400
            return True
        api.user.ClientToScreen.side_effect = client_to_screen
        api.user.GetCursorPos.side_effect = cursor
        self.assertEqual(api._window_proc(11, 0x201, 1, 5 | (6 << 16)), 0)
        self.assertEqual(events[0], OverlayEvent("drag", "press", 105, 206))
        api.poll_pointer()
        api.user.GetAsyncKeyState.return_value = 0
        api.poll_pointer()
        self.assertEqual([event.action for event in events], ["press", "motion", "release"])
        self.assertEqual(events[-1], OverlayEvent("drag", "release", 300, 400))
        api.user.SetForegroundWindow.assert_not_called()

    def test_drag_sampling_handles_swapped_mouse_buttons_and_cancels_on_failure(self):
        api = self.native()
        events = []
        api.enqueue = lambda event: events.append(event) or True
        api.user.GetSystemMetrics.return_value = 1
        api.user.GetCursorPos.return_value = True
        api.user.GetAsyncKeyState.return_value = 0x8000
        api.pointer_session = ("button", 11, time.monotonic())
        api.poll_pointer()
        api.user.GetAsyncKeyState.assert_called_once_with(2)
        api.user.GetCursorPos.return_value = False
        api.poll_pointer()
        self.assertEqual(events[-1].action, "cancel")
        self.assertIsNone(api.pointer_session)

    def test_bounds_are_native_signed_coordinates_and_move_does_not_activate(self):
        api = self.native()
        def rectangle(_hwnd, pointer):
            pointer._obj.left, pointer._obj.top = -640, -200
            pointer._obj.right, pointer._obj.bottom = 0, 560
            return True
        api.user.GetWindowRect.side_effect = rectangle
        self.assertEqual(api.get_bounds(), (-640, -200, 640, 760))
        api.move_resize(-700, -300, 640, 760)
        api.user.SetWindowPos.assert_called_once_with(10, None, -700, -300, 640, 760, 0x14)
        api.user.SetForegroundWindow.assert_not_called()

    def test_only_accepted_release_from_our_control_is_consumed(self):
        api = self.native()
        api.enqueue = mock.Mock(return_value=True)
        api.pointer_session = None
        self.assertFalse(api._observe_pointer(0x202, 2000, 2000))
        api.enqueue.assert_not_called()
        api.pointer_session = ("button", 11, time.monotonic())
        self.assertFalse(api._observe_pointer(0x200, 2000, 2000))
        self.assertTrue(api._observe_pointer(0x202, 2000, 2000))
        self.assertIsNone(api.pointer_session)
        api.pointer_session = ("button", 11, time.monotonic())
        api.enqueue.return_value = False
        self.assertFalse(api._observe_pointer(0x202, 2000, 2000))
        self.assertIsNone(api.pointer_session)

    def test_partial_start_cleanup_destroys_islands_even_before_handle_registration(self):
        api = self.native()
        api.islands = {"button": 11, "failed-alpha": 12}
        api.pointer_session = ("button", 11, time.monotonic())
        api.thread_id, api.thread, api.registered = 0, None, False
        api.original_style = 0
        api._set_style = mock.Mock()
        api.close()
        self.assertEqual(api.user.DestroyWindow.call_args_list, [mock.call(11), mock.call(12)])
        self.assertIsNone(api.pointer_session)


if __name__ == "__main__":
    unittest.main()
