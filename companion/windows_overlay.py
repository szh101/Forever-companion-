"""Windows input islands over a permanently click-through chat surface.

No keyboard hook, input synthesis, window content, or screen capture
is used here. Small owned windows receive real pointer events over our controls;
the main layered HWND always passes other clicks directly to Windows. Wheel
events over the unobscured chat rectangle are intercepted; a user's own control
drag is observed until release so inactive windows do not lose it. During typing,
a click back on the previous window queues a focus handoff without consuming the click. Tk work is
queued out of native callbacks. Importing this module and hidden GUI checks
create no hooks.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import os
import queue
import sys
import threading
import time


KINDS = frozenset({"input", "button", "scrollbar", "drag", "resize", "link"})


def contains(rect, x, y):
    return rect[0] <= x < rect[2] and rect[1] <= y < rect[3]


def valid_rect(rect):
    return (len(rect) == 4 and all(type(n) is int for n in rect)
            and all(-100000 <= n <= 100000 for n in rect)
            and 0 < rect[2] - rect[0] <= 8192 and 0 < rect[3] - rect[1] <= 8192)


@dataclass(frozen=True)
class OverlayTarget:
    key: str
    rect: tuple[int, int, int, int]
    kind: str = "button"


@dataclass(frozen=True)
class OverlayEvent:
    target: str
    action: str
    x: int
    y: int
    delta: int = 0
    epoch: int = 0


class WindowsOverlay:
    """Own-window adapter. Call start only after normal visible startup.

    update_targets may run before start. on_event runs on Tk's thread, never the
    mouse-hook thread. activate_input/release_input require explicit user actions.
    """

    def __init__(self, root, on_event, on_error=None, *, api=None):
        self.root, self.on_event, self.on_error = root, on_event, on_error
        self.api = api
        self.targets = ()
        self.scroll_rects = ()
        self.events = queue.Queue(maxsize=128)
        self.hover_events = {}
        self.motion_events = {}
        self.event_lock = threading.Lock()
        self.active = self.suspended = self.closed = False
        self.previous_focus = None
        self.input_epoch = 0
        self.input_session = None
        self.pending_focus_release = None
        self.opacity = 0.92
        self._after = None

    def update_targets(self, targets, scroll_rects=()):
        targets, scroll_rects = tuple(targets), tuple(scroll_rects)
        if (len(targets) > 128 or len(scroll_rects) > 8
                or any(not isinstance(t, OverlayTarget) or not t.key or t.kind not in KINDS
                       or not valid_rect(t.rect) for t in targets)
                or len({t.key for t in targets}) != len(targets)
                or any(not valid_rect(r) for r in scroll_rects)):
            raise ValueError("Invalid overlay regions")
        self.targets, self.scroll_rects = targets, scroll_rects
        if self.active:
            try:
                self.api.update_targets(targets, self.suspended)
            except Exception:
                self._fail("窗口交互初始化失败，已恢复普通窗口。")

    def start(self):
        if self.closed or self.active:
            return self.active
        # This check precedes native initialization, including every hidden test.
        if not self.root.winfo_ismapped() or (self.api is None and sys.platform != "win32"):
            return False
        try:
            if self.api is None:
                self.api = _Win32()
            self.api.start(self.root.winfo_id(), self._enqueue, self._wheel,
                           self.targets, self.opacity, outside_press=self._outside_press)
            self.active = True
            self._after = self.root.after(16, self._pump)
            return True
        except Exception:
            self._fail("窗口交互初始化失败，已恢复普通窗口。")
            return False

    def _enqueue(self, event):
        if self.closed or self.suspended:
            return False
        try:
            # Record the foreground identity before our explicit input activation.
            target = next((t for t in self.targets if t.key == event.target), None)
            if target is None and event.action != "wheel":
                return False
            if (target and target.kind == "input" and event.action == "press"
                    and not contains(target.rect, event.x, event.y)):
                return False  # A stale mouse capture cannot turn a game click into typing.
            previous = (self.api.foreground_identity() if target and target.kind == "input"
                        and event.action == "press" else None)
            with self.event_lock:
                if target and target.kind == "input":
                    if event.action == "press":
                        if previous and previous[0] != self.api.hwnd:
                            self.previous_focus = previous
                        self.input_epoch += 1
                        # Arm at the physical press, before Tk's queued activation.
                        self.input_session = (self.input_epoch, event.target, self.previous_focus)
                    event = replace(event, epoch=self.input_epoch)
                if event.action in ("hover", "leave", "motion"):
                    # Pointer movement can arrive faster than Tk renders.
                    pending = self.motion_events if event.action == "motion" else self.hover_events
                    pending[event.target] = (time.monotonic(), event)
                    return True
                if event.action == "release":
                    motion = self.motion_events.pop(event.target, None)
                    if motion:
                        self.events.put_nowait(motion)
                self.events.put_nowait((time.monotonic(), event))
            return True
        except (queue.Full, OSError):
            return False

    def _outside_press(self, x, y):
        """Observe a click back on the prior window; never consume its input."""
        session = self.input_session
        if not self.active or self.closed or self.suspended or not session or not session[2]:
            return
        try:
            if not self.api.clicked_previous_window(session[2], x, y):
                return
            with self.event_lock:
                if self.input_session != session:
                    return
                self.input_session = None  # Old queued presses cannot retake focus.
                self.pending_focus_release = (time.monotonic(), session, x, y)
        except OSError:
            pass

    def _wheel(self, x, y, delta):
        if (not self.active or self.closed or self.suspended
                or not any(contains(rect, x, y) for rect in self.scroll_rects)):
            return False
        try:
            if not self.api.unobscured(x, y):
                return False
            return self._enqueue(OverlayEvent("", "wheel", x, y, delta))
        except Exception:
            return False  # Never swallow unrelated input when inspection fails.

    def _pump(self):
        self._after = None
        if not self.active or self.closed:
            return
        try:
            # An own-control press starts bounded tracking. Cursor sampling is
            # independent of WH_MOUSE_LL (which Windows can silently remove).
            # It does not change hit-testing or inspect any keyboard key.
            if not self.suspended:
                self.api.poll_pointer()
            with self.event_lock:
                focus_release, self.pending_focus_release = self.pending_focus_release, None
                pending = []
                for _ in range(128):
                    try:
                        pending.append(self.events.get_nowait())
                    except queue.Empty:
                        break
                pending.extend(self.motion_events.values())
                self.motion_events.clear()
                pending.extend(self.hover_events.values())
                self.hover_events.clear()
            if focus_release and not self.suspended:
                created, session, x, y = focus_release
                if session[0] == self.input_epoch and time.monotonic() - created <= 1.0:
                    if self.api.end_input_on_click(session[2], x, y):
                        self.previous_focus = None
                    self.on_event(OverlayEvent(session[1], "cancel", x, y, epoch=session[0]))
            for created, event in pending:
                if not self.active or self.closed:
                    return
                if self.suspended or time.monotonic() - created > 1.0:
                    continue
                if event.action != "wheel" and not any(t.key == event.target for t in self.targets):
                    continue
                if event.epoch and (not self.input_session or event.epoch != self.input_session[0]):
                    continue
                self.on_event(event)
        except Exception:
            self._fail("窗口交互失败，已恢复普通窗口。")
            return
        if self.active and not self.closed:
            self._after = self.root.after(16, self._pump)

    def activate_input(self):
        """Called only from a physical input-island click handled by the UI."""
        return bool(self.active and not self.suspended and self.input_session and self.api.activate_input())

    def release_input(self):
        """Escape/send: return to the exact still-valid prior foreground HWND."""
        self.input_epoch += 1
        self.input_session = self.pending_focus_release = None
        if not self.active or not self.previous_focus:
            return False
        restored = self.api.restore_focus(self.previous_focus)
        if restored:
            self.previous_focus = None
        return bool(restored)

    def set_suspended(self, suspended):
        self.suspended = bool(suspended)
        if self.suspended:
            self.input_epoch += 1
            self.input_session = self.pending_focus_release = None
        if self.active:
            self.api.update_targets(self.targets, self.suspended)

    def move_resize(self, x, y, width, height):
        """Move our own wrapper after a physical drag; never activate it."""
        rect = (x, y, x + width, y + height)
        if not valid_rect(rect):
            raise ValueError("Invalid overlay bounds")
        if self.active:
            self.api.move_resize(x, y, width, height)

    def get_bounds(self):
        return self.api.get_bounds() if self.active else None

    def set_opacity(self, value):
        value = float(value)
        if not 0.45 <= value <= 1.0:
            raise ValueError("Opacity must be between 0.45 and 1.0")
        self.opacity = value
        if self.active:
            self.api.set_opacity(value)

    def _fail(self, message):
        self.close()
        if self.on_error:
            self.on_error(message)

    def close(self):
        if self.closed:
            return
        self.closed, self.active = True, False
        if self._after is not None:
            try:
                self.root.after_cancel(self._after)
            except Exception:
                pass
            self._after = None
        if self.api:
            self.api.close()


class _Win32:
    """ctypes is initialized only by the mapped, visible application's start."""

    LAYERED, TRANSPARENT, NOACTIVATE = 0x80000, 0x20, 0x08000000

    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        self.c, self.w = c, w
        self.user = u = c.WinDLL("user32", use_last_error=True)
        self.kernel = k = c.WinDLL("kernel32", use_last_error=True)
        self.result = c.c_ssize_t
        self.proc_type = c.WINFUNCTYPE(self.result, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        self.hook_type = c.WINFUNCTYPE(self.result, c.c_int, w.WPARAM, w.LPARAM)
        signatures = {
            "GetAncestor": ([w.HWND, w.UINT], w.HWND),
            "GetWindowLongPtrW": ([w.HWND, c.c_int], c.c_ssize_t),
            "SetWindowLongPtrW": ([w.HWND, c.c_int, c.c_ssize_t], c.c_ssize_t),
            "GetWindowThreadProcessId": ([w.HWND, c.POINTER(w.DWORD)], w.DWORD),
            "SetLayeredWindowAttributes": ([w.HWND, w.DWORD, w.BYTE, w.DWORD], w.BOOL),
            "CreateWindowExW": ([w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, c.c_int, c.c_int,
                                 c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID], w.HWND),
            "DefWindowProcW": ([w.HWND, w.UINT, w.WPARAM, w.LPARAM], self.result),
            "DestroyWindow": ([w.HWND], w.BOOL),
            "SetWindowPos": ([w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT], w.BOOL),
            "ShowWindow": ([w.HWND, c.c_int], w.BOOL),
            "GetForegroundWindow": ([], w.HWND),
            "SetForegroundWindow": ([w.HWND], w.BOOL),
            "WindowFromPoint": ([w.POINT], w.HWND),
            "GetCapture": ([], w.HWND),
            "ReleaseCapture": ([], w.BOOL),
            "GetFocus": ([], w.HWND),
            "SetFocus": ([w.HWND], w.HWND),
            "IsWindow": ([w.HWND], w.BOOL),
            "IsWindowVisible": ([w.HWND], w.BOOL),
            "IsIconic": ([w.HWND], w.BOOL),
            "GetWindow": ([w.HWND, w.UINT], w.HWND),
            "GetWindowRect": ([w.HWND, c.POINTER(w.RECT)], w.BOOL),
            "ClientToScreen": ([w.HWND, c.POINTER(w.POINT)], w.BOOL),
            "GetCursorPos": ([c.POINTER(w.POINT)], w.BOOL),
            "GetAsyncKeyState": ([c.c_int], w.SHORT),
            "GetSystemMetrics": ([c.c_int], c.c_int),
            "SetWindowsHookExW": ([c.c_int, self.hook_type, w.HINSTANCE, w.DWORD], w.HANDLE),
            "CallNextHookEx": ([w.HANDLE, c.c_int, w.WPARAM, w.LPARAM], self.result),
            "UnhookWindowsHookEx": ([w.HANDLE], w.BOOL),
            "GetMessageW": ([c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT], w.BOOL),
            "PeekMessageW": ([c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT], w.BOOL),
            "PostThreadMessageW": ([w.DWORD, w.UINT, w.WPARAM, w.LPARAM], w.BOOL),
            "UnregisterClassW": ([w.LPCWSTR, w.HINSTANCE], w.BOOL),
            "LoadCursorW": ([w.HINSTANCE, w.LPCWSTR], w.HANDLE),
            "SetCursor": ([w.HANDLE], w.HANDLE),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(u, name)
            fn.argtypes, fn.restype = args, result
        k.GetModuleHandleW.argtypes, k.GetModuleHandleW.restype = [w.LPCWSTR], w.HMODULE
        k.GetCurrentThreadId.argtypes, k.GetCurrentThreadId.restype = [], w.DWORD
        self.hwnd = self.original_style = self.hook = self.thread_id = 0
        self.owner_pid = os.getpid()
        self.islands, self.handles = {}, {}
        self.tracking = set()
        self.target_kinds = {}
        self.pointer_session = None
        self.pointer_position = None
        self.pointer_lock = threading.Lock()
        self._layout = None
        self.callback = self.hook_callback = self.thread = None
        self.outside_press = None
        self.class_name = "ForeverAIInputIsland_" + str(os.getpid()) + "_" + str(id(self))
        self.module = k.GetModuleHandleW(None)
        self.registered = self.stopped = False
        class TrackMouse(c.Structure):
            _fields_ = [("cbSize", w.DWORD), ("dwFlags", w.DWORD),
                        ("hwndTrack", w.HWND), ("dwHoverTime", w.DWORD)]
        self.track_type = TrackMouse
        u.TrackMouseEvent.argtypes, u.TrackMouseEvent.restype = [c.POINTER(TrackMouse)], w.BOOL

    def _require(self, result):
        if not result:
            raise OSError(self.c.get_last_error(), "Windows overlay unavailable")
        return result

    def _set_style(self, hwnd, value):
        self.c.set_last_error(0)
        previous = self.user.SetWindowLongPtrW(hwnd, -20, value)
        if not previous and self.c.get_last_error():
            self._require(False)

    def _pid(self, hwnd):
        pid = self.w.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, self.c.byref(pid))
        return pid.value

    def start(self, tk_hwnd, enqueue, wheel, targets, opacity, *, outside_press=None):
        c, w, u = self.c, self.w, self.user
        self.enqueue, self.wheel = enqueue, wheel
        self.outside_press = outside_press
        owner = self._require(u.GetAncestor(tk_hwnd, 2))
        if self._pid(owner) != self.owner_pid:
            raise OSError("Overlay owner must belong to this process")
        self.hwnd = owner
        self.original_style = u.GetWindowLongPtrW(self.hwnd, -20)

        class WindowClass(c.Structure):
            _fields_ = [("cbSize", w.UINT), ("style", w.UINT), ("lpfnWndProc", self.proc_type),
                        ("cbClsExtra", c.c_int), ("cbWndExtra", c.c_int), ("hInstance", w.HINSTANCE),
                        ("hIcon", w.HICON), ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH),
                        ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR), ("hIconSm", w.HICON)]
        self.callback = self.proc_type(self._window_proc)
        wc = WindowClass()
        wc.cbSize, wc.lpfnWndProc, wc.hInstance = c.sizeof(wc), self.callback, self.module
        wc.lpszClassName, wc.hbrBackground = self.class_name, 6  # COLOR_WINDOW + 1
        u.RegisterClassExW.argtypes, u.RegisterClassExW.restype = [c.POINTER(WindowClass)], w.ATOM
        self._require(u.RegisterClassExW(c.byref(wc)))
        self.registered = True
        self.update_targets(targets, False)
        self._set_style(self.hwnd, self.original_style | self.LAYERED | self.TRANSPARENT | self.NOACTIVATE)
        self.set_opacity(opacity)
        ready = threading.Event()
        self.thread = threading.Thread(target=self._hook_loop, args=(ready,), daemon=True,
                                       name="ForeverAI-wheel")
        self.thread.start()
        if not ready.wait(0.8) or not self.hook:
            raise OSError("Hover wheel hook unavailable")

    def update_targets(self, targets, suspended):
        u = self.user
        layout = (tuple(targets), bool(suspended))
        if layout == self._layout:
            return
        owner_rect = self.w.RECT()
        self._require(u.GetWindowRect(self.hwnd, self.c.byref(owner_rect)))
        keep = {t.key for t in targets}
        for key in tuple(self.islands):
            if key not in keep:
                hwnd = self.islands.pop(key)
                self.handles.pop(hwnd, None)
                self.target_kinds.pop(key, None)
                self.tracking.discard(hwnd)
                if self.pointer_session and self.pointer_session[0] == key:
                    self.pointer_session = None
                u.DestroyWindow(hwnd)
        for target in targets:
            left, top, right, bottom = target.rect
            # A stale layout must never leave invisible hit windows elsewhere.
            left, top = max(left, owner_rect.left), max(top, owner_rect.top)
            right, bottom = min(right, owner_rect.right), min(bottom, owner_rect.bottom)
            hwnd = self.islands.get(target.key)
            if right <= left or bottom <= top:
                if hwnd:
                    u.ShowWindow(hwnd, 0)
                continue
            if not hwnd:
                hwnd = self._require(u.CreateWindowExW(self.LAYERED | self.NOACTIVATE | 0x80,
                            self.class_name, "", 0x80000000, left, top, right-left, bottom-top,
                            self.hwnd, None, self.module, None))
                self.islands[target.key] = hwnd
                self._require(u.SetLayeredWindowAttributes(hwnd, 0, 1, 2))
            self.handles[hwnd] = target.key
            self.target_kinds[target.key] = target.kind
            if suspended:
                u.ShowWindow(hwnd, 0)
            else:
                # HWND_TOP raises only our owned island within the owner's band;
                # SWP_NOACTIVATE never takes keyboard focus.
                self._require(u.SetWindowPos(hwnd, 0, left, top, right-left, bottom-top, 0x10 | 0x40))
        self._layout = layout
        if suspended:
            self.pointer_session = None

    def move_resize(self, x, y, width, height):
        self._require(self.user.SetWindowPos(self.hwnd, None, x, y, width, height, 0x10 | 0x4))
        self._layout = None

    def get_bounds(self):
        if self._pid(self.hwnd) != self.owner_pid:
            raise OSError("Overlay owner changed")
        rect = self.w.RECT()
        self._require(self.user.GetWindowRect(self.hwnd, self.c.byref(rect)))
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top

    def poll_pointer(self):
        """Read mouse position/state only during an actual own-control press."""
        session = self.pointer_session
        if not session:
            return
        if time.monotonic() - session[2] > 30:
            self._cancel_pointer()
            return
        point = self.w.POINT()
        if not self.user.GetCursorPos(self.c.byref(point)):
            self._cancel_pointer()
            return
        # GetAsyncKeyState reports physical buttons, unlike WM_LBUTTONDOWN.
        button = 2 if self.user.GetSystemMetrics(23) else 1  # SM_SWAPBUTTON
        held = bool(self.user.GetAsyncKeyState(button) & 0x8000)
        self._observe_pointer(0x200 if held else 0x202, point.x, point.y)

    def _cancel_pointer(self):
        with self.pointer_lock:
            session, position = self.pointer_session, self.pointer_position or (0, 0)
            self.pointer_session = self.pointer_position = None
        if session:
            self.enqueue(OverlayEvent(session[0], "cancel", *position))

    def _window_proc(self, hwnd, msg, wp, lp):
        try:
            if msg == 0x21:  # WM_MOUSEACTIVATE: clicks work, foreground stays put.
                return 3  # MA_NOACTIVATE
            key = self.handles.get(hwnd)
            if key and msg == 0x20:  # WM_SETCURSOR for our invisible control island.
                cursor = {"input": 32513, "drag": 32646, "resize": 32642,
                          "button": 32649, "link": 32649}.get(self.target_kinds.get(key), 32512)
                resource = self.c.cast(self.c.c_void_p(cursor), self.w.LPCWSTR)
                self.user.SetCursor(self.user.LoadCursorW(None, resource))
                return 1
            if key and msg == 0x2A3:  # WM_MOUSELEAVE
                self.tracking.discard(hwnd)
                self.enqueue(OverlayEvent(key, "leave", 0, 0))
                return 0
            if key and msg == 0x20A:  # WM_MOUSEWHEEL already uses screen coordinates.
                x = self.c.c_short(lp & 0xFFFF).value
                y = self.c.c_short((lp >> 16) & 0xFFFF).value
                delta = self.c.c_short((wp >> 16) & 0xFFFF).value
                # A wheel consumed by the hook is not delivered here. Native
                # delivery is a fallback, with the same chat/visibility checks.
                if delta and self.wheel(x, y, delta):
                    return 0
            if key and msg in (0x200, 0x201, 0x202):
                x = self.c.c_short(lp & 0xFFFF).value
                y = self.c.c_short((lp >> 16) & 0xFFFF).value
                point = self.w.POINT(x, y)
                self._require(self.user.ClientToScreen(hwnd, self.c.byref(point)))
                if msg == 0x200 and self.pointer_session:
                    self._observe_pointer(msg, point.x, point.y)
                    return 0  # Also works if the low-level hook stops reporting.
                action = {0x200: "motion", 0x201: "press", 0x202: "release"}[msg]
                if msg == 0x200:
                    action = "hover"
                    if hwnd not in self.tracking:
                        track = self.track_type(self.c.sizeof(self.track_type), 2, hwnd, 0)
                        if self.user.TrackMouseEvent(self.c.byref(track)):
                            self.tracking.add(hwnd)
                if msg == 0x201:
                    with self.pointer_lock:
                        self.pointer_session = (key, hwnd, time.monotonic())
                        self.pointer_position = (point.x, point.y)
                elif msg == 0x202:
                    self._observe_pointer(msg, point.x, point.y)
                    return 0  # The observer deduplicates hook/poll/native release.
                self.enqueue(OverlayEvent(key, action, point.x, point.y))
                return 0
        except Exception:
            # Keep Windows input dispatch alive; no callback exception crosses C.
            self.pointer_session = None
        return self.user.DefWindowProcW(hwnd, msg, wp, lp)

    def _hook_loop(self, ready):
        c, w, u = self.c, self.w, self.user

        class MouseData(c.Structure):
            _fields_ = [("pt", w.POINT), ("mouseData", w.DWORD), ("flags", w.DWORD),
                        ("time", w.DWORD), ("dwExtraInfo", c.c_size_t)]

        def callback(code, msg, pointer):
            try:
                outside = getattr(self, "outside_press", None)
                down = (msg in (0x201, 0x204, 0x207, 0x20B)
                        and outside is not None and not self.pointer_session)
                if (code >= 0 and not self.stopped
                        and (down or msg == 0x20A
                             or (msg in (0x200, 0x202) and self.pointer_session))):
                    data = c.cast(pointer, c.POINTER(MouseData)).contents
                    if down:
                        # Merely queue an explicitly requested end to typing.
                        # The original click always continues unchanged; all
                        # focus/capture changes run later on the Tk thread.
                        outside(data.pt.x, data.pt.y)
                    elif msg == 0x20A:
                        # Mouse utilities and accessibility drivers can mark
                        # real user scrolling injected. Scope by our visible
                        # chat rectangle rather than rejecting that flag.
                        delta = c.c_short(data.mouseData >> 16).value
                        if delta and self.wheel(data.pt.x, data.pt.y, delta):
                            return 1
                    elif self._observe_pointer(msg, data.pt.x, data.pt.y):
                        # Some user mouse/accessibility drivers mark movement
                        # injected. Once our control received an actual press,
                        # those moves still belong to that explicit session.
                        return 1
            except Exception:
                pass
            return u.CallNextHookEx(None, code, msg, pointer)

        try:
            self.thread_id = self.kernel.GetCurrentThreadId()
            message = w.MSG()
            u.PeekMessageW(c.byref(message), None, 0, 0, 0)  # Create this thread's queue.
            self.hook_callback = self.hook_type(callback)
            self.hook = u.SetWindowsHookExW(14, self.hook_callback, self.module, 0)
            ready.set()
            if self.hook:
                while not self.stopped and u.GetMessageW(c.byref(message), None, 0, 0) > 0:
                    pass  # The sent hook callback is delivered inside GetMessage.
        finally:
            ready.set()
            if self.hook:
                u.UnhookWindowsHookEx(self.hook)
                self.hook = 0

    def _observe_pointer(self, message, x, y):
        """Observe our explicit drag; only its queued release may be consumed.

        Physical movement always continues so Windows keeps moving the pointer.
        A release after an own-control press must not click the game underneath.
        """
        with self.pointer_lock:
            session = self.pointer_session
            if not session or message not in (0x200, 0x202):
                return False
            if (time.monotonic() - session[2] > 30
                    or self.handles.get(session[1]) != session[0]):
                self.pointer_session = self.pointer_position = None
                action = "cancel"
            elif message == 0x202:
                self.pointer_session = self.pointer_position = None
                action = "release"
            else:
                if self.pointer_position == (x, y):
                    return False
                self.pointer_position = (x, y)
                action = "motion"
        accepted = self.enqueue(OverlayEvent(session[0], action, x, y))
        return bool(message == 0x202 and action == "release" and accepted)

    def foreground_identity(self):
        hwnd = self.user.GetForegroundWindow()
        return (hwnd, self._pid(hwnd)) if hwnd else None

    def activate_input(self):
        return self._pid(self.hwnd) == self.owner_pid and self.user.SetForegroundWindow(self.hwnd)

    def clicked_previous_window(self, previous, x, y):
        """Match the actual clicked window to our saved foreground identity."""
        if not previous:
            return False
        hwnd, pid = previous
        u = self.user
        if (not hwnd or pid == self.owner_pid or self._pid(self.hwnd) != self.owner_pid
                or not u.IsWindow(hwnd) or self._pid(hwnd) != pid
                or not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd)):
            return False
        hit = u.WindowFromPoint(self.w.POINT(x, y))
        return bool(hit and u.GetAncestor(hit, 2) == hwnd)

    def end_input_on_click(self, previous, x, y):
        """Tk-thread handoff after a real click on the exact previous window.

        GetCapture/GetFocus are thread-local. Never clear capture or focus from
        settings/dialogs, and never activate a window after the user has already
        moved the foreground elsewhere.
        """
        if not self.clicked_previous_window(previous, x, y):
            return False
        hwnd, _pid = previous
        u = self.user
        if u.GetForegroundWindow() not in (self.hwnd, hwnd):
            return False
        captured = u.GetCapture()
        if (captured and self._pid(captured) == self.owner_pid
                and u.GetAncestor(captured, 2) == self.hwnd):
            u.ReleaseCapture()
        focused = u.GetFocus()
        if (focused and self._pid(focused) == self.owner_pid
                and u.GetAncestor(focused, 2) == self.hwnd):
            u.SetFocus(None)
        if self.pointer_session:
            self._cancel_pointer()
        foreground = u.GetForegroundWindow()
        if foreground == hwnd:
            return True
        if foreground != self.hwnd or not self.clicked_previous_window(previous, x, y):
            return False
        return bool(u.SetForegroundWindow(hwnd))

    def restore_focus(self, previous):
        hwnd, pid = previous
        if (self._pid(self.hwnd) != self.owner_pid
                or self.user.GetForegroundWindow() != self.hwnd or not self.user.IsWindow(hwnd)
                or self._pid(hwnd) != pid or not self.user.IsWindowVisible(hwnd)
                or self.user.IsIconic(hwnd)):
            return False
        return self.user.SetForegroundWindow(hwnd)

    def set_opacity(self, value):
        style = self.user.GetWindowLongPtrW(self.hwnd, -20)
        self._set_style(self.hwnd, style | self.LAYERED | self.TRANSPARENT | self.NOACTIVATE)
        self._require(self.user.SetLayeredWindowAttributes(self.hwnd, 0, round(value * 255), 2))

    def unobscured(self, x, y):
        u, c, w = self.user, self.c, self.w
        if not u.IsWindowVisible(self.hwnd) or u.IsIconic(self.hwnd):
            return False
        owner = w.RECT()
        if not u.GetWindowRect(self.hwnd, c.byref(owner)):
            return False
        if not contains((owner.left, owner.top, owner.right, owner.bottom), x, y):
            return False
        # Only bounding boxes and style flags are inspected, never titles/content.
        # Conservative rectangles can decline a wheel at transparent corners.
        previous, seen = u.GetWindow(self.hwnd, 3), set()  # GW_HWNDPREV
        for _ in range(128):
            if not previous:
                return True
            if previous in seen:
                return False
            seen.add(previous)
            if previous not in self.handles and u.IsWindowVisible(previous) and not u.IsIconic(previous):
                style = u.GetWindowLongPtrW(previous, -20)
                if (style & (self.LAYERED | self.TRANSPARENT)) != (self.LAYERED | self.TRANSPARENT):
                    rect = w.RECT()
                    if not u.GetWindowRect(previous, c.byref(rect)):
                        return False
                    if contains((rect.left, rect.top, rect.right, rect.bottom), x, y):
                        return False
            previous = u.GetWindow(previous, 3)
        return False

    def close(self):
        self.stopped = True
        self.pointer_session = None
        if self.thread_id:
            self.user.PostThreadMessageW(self.thread_id, 0x12, 0, 0)  # WM_QUIT, own hook thread only.
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=1)
        # A partially initialized island may not yet be in handles.
        for hwnd in tuple(self.islands.values()):
            self.user.DestroyWindow(hwnd)
        self.islands.clear()
        self.handles.clear()
        if self.hwnd and self.user.IsWindow(self.hwnd) and self._pid(self.hwnd) == self.owner_pid:
            # Preserve later Tk/topmost changes; remove only bits added by us.
            style = self.user.GetWindowLongPtrW(self.hwnd, -20)
            bits = self.LAYERED | self.TRANSPARENT | self.NOACTIVATE
            self._set_style(self.hwnd, (style & ~bits) | (self.original_style & bits))
        if self.registered:
            self.user.UnregisterClassW(self.class_name, self.module)
            self.registered = False
