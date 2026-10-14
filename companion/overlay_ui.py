"""Map only Forever AI controls to Windows overlay hit regions.

The adapter never starts native windows/hooks for a withdrawn test window.
Physical events received by our own controls are delivered only to Tk widgets
in this process. Background events are left to Windows; no input is replayed
to the game or to any other application.
"""
from __future__ import annotations

import sys
import tkinter as tk


def widget_rect(widget):
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    return x, y, x + widget.winfo_width(), y + widget.winfo_height()


def intersection(a, b):
    result = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return result if result[0] < result[2] and result[1] < result[3] else None


class GameOverlay:
    def __init__(self, app):
        self.app, self.root = app, app.root
        self.native = None
        self.closed = self.failed = False
        self.widgets = {}
        self.hit_rects = {}
        self.pressed = self.drag = self.hovered = None
        self.fallback_drag = None
        self.wheel_remainder = 0
        self.timer = self.root.after(100, self.refresh)
        self.root.bind("<Destroy>", self.destroyed, add="+")
        self.root.bind("<Configure>", self.configured, add="+")
        app.input.bind("<Escape>", self.release_input, add="+")
        for widget in (app.chat, app.chat.vbar):
            widget.bind("<MouseWheel>", self.ordinary_wheel, add="+")
        for widget, kind in ((app.drag_handle, "drag"), (app.resize_handle, "resize")):
            if widget is not None:
                for sequence, action in (("<ButtonPress-1>", "press"),
                                         ("<B1-Motion>", "motion"), ("<ButtonRelease-1>", "release")):
                    widget.bind(sequence, lambda event, k=kind, a=action: self.ordinary_drag(event, k, a), add="+")

    def ordinary_wheel(self, event):
        if self.closed or self.native is not None:
            return None
        self.scroll_history(event.delta)
        return "break"  # Do not also scroll through Tk's default class binding.

    def scroll_history(self, delta):
        self.wheel_remainder += delta
        steps = int(self.wheel_remainder / 120)
        self.wheel_remainder -= steps * 120
        if steps:
            self.app.chat.yview_scroll(-steps * 3, "units")
            if self.native:
                self.update_layout()

    def ordinary_drag(self, event, kind, action):
        """Keep the handles usable when Windows overlay setup is unavailable."""
        if self.closed or self.native is not None:
            return None
        if action == "press":
            self.fallback_drag = (kind, event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y(),
                                  self.root.winfo_width(), self.root.winfo_height())
        elif self.fallback_drag and self.fallback_drag[0] == kind:
            _, x, y, left, top, width, height = self.fallback_drag
            dx, dy = event.x_root - x, event.y_root - y
            if kind == "drag":
                left, top = left + dx, top + dy
            else:
                minimum = self.root.minsize()
                width, height = max(minimum[0], width + dx), max(minimum[1], height + dy)
            # A literal '+' before the signed number means absolute coordinates
            # to Tk, including a monitor left/above the primary screen.
            self.root.geometry(f"{width}x{height}+{left}+{top}")
            if action == "release":
                self.fallback_drag = None
        return "break"

    def configured(self, event):
        # Geometry changes refresh hit windows at idle, before the periodic
        # check, so folding/moving cannot leave old control regions behind.
        if event.widget is self.root and self.native and not self.closed and not self.failed:
            if self.timer is not None:
                self.root.after_cancel(self.timer)
            self.timer = self.root.after_idle(self.refresh)

    def destroyed(self, event):
        if event.widget is self.root:
            self.close()

    def close(self):
        self.closed = True
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        if self.native:
            self.native.close()
            self.native = None

    def fail(self, _reason=None):
        if self.failed or self.closed:
            return
        self.failed = True
        if self.native:
            self.native.close()
            self.native = None
        self.root.overrideredirect(False)
        self.app.status.set("Click-through mode could not start. Restored normal window behavior.")

    def refresh(self):
        self.timer = None
        if self.closed or self.failed:
            return
        try:
            # Tests keep the root withdrawn; no native API or hooks are loaded.
            if sys.platform != "win32" or not self.root.winfo_viewable():
                if self.native:
                    self.native.update_targets([], scroll_rects=())
                return
            if self.native is None:
                if self.fallback_drag is not None:
                    return
                from .windows_overlay import WindowsOverlay
                self.root.overrideredirect(True)
                self.root.update_idletasks()
                self.native = WindowsOverlay(self.root, self.handle, on_error=self.fail)
                if self.native.start() is False:
                    self.fail()
                    return
                self.native.set_opacity(self.app.opacity.get() / 100)
            # Ordinary settings, file dialogs and image viewers remain normal
            # windows. Do not put input islands above these owned dialogs.
            if any(isinstance(w, tk.Toplevel) and w.winfo_viewable()
                   for w in self.root.winfo_children()):
                self.native.set_suspended(True)
                return
            self.native.set_suspended(False)
            self.update_layout()
        except (tk.TclError, OSError, RuntimeError, ValueError):
            self.fail()
        finally:
            if not self.closed and not self.failed:
                self.timer = self.root.after(80, self.refresh)

    def update_layout(self):
        from .windows_overlay import OverlayTarget
        app = self.app
        bounds = widget_rect(self.root)
        targets, widgets = [], {}
        for widget in app.interactive_widgets:
            if not widget.winfo_viewable():
                continue
            rect = intersection(widget_rect(widget), bounds)
            if rect is None:
                continue
            kind = ("input" if widget is app.input else
                    "scrollbar" if widget is app.chat.vbar else
                    "drag" if widget is app.drag_handle else
                    "resize" if widget is app.resize_handle else "button")
            key = str(widget)
            targets.append(OverlayTarget(key, rect, kind))
            widgets[key] = (widget, kind)
        scroll = ()
        if not app.collapsed and app.chat.winfo_viewable():
            chat_rect = intersection(widget_rect(app.chat), bounds)
            if chat_rect:
                scroll = (chat_rect,)
                if app.chat.vbar.winfo_viewable():
                    bar_rect = intersection(widget_rect(app.chat.vbar), bounds)
                    if bar_rect:
                        scroll += (bar_rect,)
                # Embedded picture controls keep their actual visible bounds.
                for widget in app.chat.winfo_children():
                    if not widget.winfo_viewable():
                        continue
                    rect = intersection(widget_rect(widget), chat_rect)
                    if rect:
                        key = str(widget)
                        targets.append(OverlayTarget(key, rect, "link"))
                        widgets[key] = (widget, "link")
                self.link_targets(targets, widgets, chat_rect)
        if self.hovered is not None and self.hovered not in widgets:
            self.hover(None)
        self.widgets = widgets
        self.hit_rects = {target.key: target.rect for target in targets}
        self.native.update_targets(targets, scroll_rects=scroll)

    def link_targets(self, targets, widgets, bounds):
        """Use only on-screen text link fragments; plain text stays pass-through."""
        from .windows_overlay import OverlayTarget
        chat = self.app.chat
        first = chat.index("@0,0")
        last = chat.index(f"@{chat.winfo_width()},{chat.winfo_height()}")
        x, y = chat.winfo_rootx(), chat.winfo_rooty()
        for tag in chat.tag_names():
            if len(targets) >= 128:
                break
            if not tag.startswith("link-"):
                continue
            ranges = chat.tag_ranges(tag)
            for start, end in zip(ranges[::2], ranges[1::2]):
                if chat.compare(end, "<=", first) or chat.compare(start, ">", last):
                    continue
                index = str(first if chat.compare(start, "<", first) else start)
                for fragment in range(80):
                    if len(targets) >= 128:
                        break
                    if chat.compare(index, ">=", end) or chat.compare(index, ">", last):
                        break
                    line_end = chat.index(f"{index} display lineend")
                    segment_last = (chat.index(f"{end} - 1 chars") if chat.compare(end, "<=", line_end)
                                    else line_end)
                    a = chat.bbox(index)
                    b = chat.bbox(segment_last)
                    if a and b:
                        rect = intersection((x + a[0], y + a[1], x + b[0] + b[2], y + a[1] + a[3]), bounds)
                        if rect:
                            key = f"{tag}:{start}:{fragment}"
                            targets.append(OverlayTarget(key, rect, "link"))
                            widgets[key] = (chat, "link")
                    next_index = chat.index(f"{line_end} + 1 chars")
                    if chat.compare(next_index, "<=", index):
                        break
                    index = next_index

    def hover(self, key):
        if key == self.hovered:
            return
        previous = self.widgets.get(self.hovered)
        if previous and hasattr(previous[0], "tooltip"):
            previous[0].tooltip.hide()
            previous[0].state(["!active"])
        self.hovered = key
        current = self.widgets.get(key)
        if current and hasattr(current[0], "tooltip"):
            current[0].tooltip.schedule()
            current[0].state(["active"])

    def handle(self, event):
        if self.closed:
            return
        if event.action == "wheel":
            self.scroll_history(event.delta)
            return
        key = event.target
        if event.action == "leave":
            if self.hovered == key:
                self.hover(None)
            return
        current = self.widgets.get(key)
        if current is None:
            return
        widget, kind = current
        if event.action == "cancel":
            if self.pressed == key:
                self.pressed = self.drag = None
                if hasattr(widget, "state"):
                    widget.state(["!pressed"])
                if kind in ("input", "scrollbar"):
                    widget.event_generate("<ButtonRelease-1>", x=event.x - widget.winfo_rootx(),
                                          y=event.y - widget.winfo_rooty(), state=0x100, when="now")
            return
        if event.action == "hover" or (event.action == "motion" and self.pressed is None):
            self.hover(key)
            return
        if event.action == "press":
            self.hover(None)
            if hasattr(widget, "instate") and widget.instate(["disabled"]):
                return
            self.pressed = key
            if kind == "input":
                if not self.native.activate_input():
                    self.app.status.set("Click the input box again to start typing.")
                    self.pressed = None
                    return
                widget.focus_set()
            else:
                # Clicking a control ends typing, without ever activating the
                # assistant from the game. Ordinary settings may then activate.
                self.native.release_input()
            if kind in ("drag", "resize"):
                left, top, width, height = self.native.get_bounds()
                self.drag = (event.x, event.y, left, top, width, height)
            elif kind == "button":
                widget.state(["pressed"])
        if kind in ("drag", "resize"):
            if event.action in ("motion", "release") and self.pressed == key and self.drag:
                x, y, left, top, width, height = self.drag
                dx, dy = event.x - x, event.y - y
                if kind == "drag":
                    self.native.move_resize(left + dx, top + dy, width, height)
                else:
                    minimum = self.root.minsize()
                    self.native.move_resize(left, top, max(minimum[0], width + dx), max(minimum[1], height + dy))
            if event.action == "release":
                self.pressed = self.drag = None
            return
        if kind == "button":
            if event.action == "release":
                armed = self.pressed == key
                self.pressed = None
                widget.state(["!pressed"])
                left, top, right, bottom = widget_rect(widget)
                if armed and left <= event.x < right and top <= event.y < bottom:
                    widget.invoke()
            return
        if kind == "link":
            if event.action == "release":
                armed = self.pressed == key
                self.pressed = None
                rect = self.hit_rects.get(key)
                if armed and rect and rect[0] <= event.x < rect[2] and rect[1] <= event.y < rect[3]:
                    if widget is self.app.chat:
                        self.app.open_source(key.split(":", 1)[0])
                    else:
                        widget.event_generate("<ButtonPress-1>", x=event.x-widget.winfo_rootx(),
                                              y=event.y-widget.winfo_rooty(), when="now")
            return
        # Deliver only to this process's concrete control, never another HWND.
        sequences = {"press": "<ButtonPress-1>", "release": "<ButtonRelease-1>", "motion": "<B1-Motion>"}
        if event.action in sequences and (self.pressed == key or event.action == "release"):
            # Tk's last-button release/grab bookkeeping requires Button1Mask.
            state = {} if event.action == "press" else {"state": 0x100}
            widget.event_generate(sequences[event.action], x=event.x - widget.winfo_rootx(),
                                  y=event.y - widget.winfo_rooty(), when="now", **state)
        if event.action == "release":
            self.pressed = None

    def release_input(self, _event=None):
        if self.native:
            self.native.release_input()
        return "break"

    def set_opacity(self, amount):
        if self.native:
            self.native.set_opacity(amount)
