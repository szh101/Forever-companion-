"""Small rasterized line icons and in-window, focus-free hover labels."""
from __future__ import annotations

import math
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk


def draw_icon(name, size=16, color="#d8e5ec"):
    """Draw at high resolution so icons stay crisp at each display scale."""
    factor = 4
    image = Image.new("RGBA", (size * factor, size * factor))
    draw = ImageDraw.Draw(image)
    unit = size * factor / 24
    width = max(1, round(1.7 * unit))

    def points(values):
        return [(round(x * unit), round(y * unit)) for x, y in values]

    def line(values):
        draw.line(points(values), fill=color, width=width, joint="curve")

    def rect(box, radius=1):
        draw.rounded_rectangle(tuple(round(v * unit) for v in box), radius=round(radius * unit), outline=color, width=width)

    def circle(box):
        draw.ellipse(tuple(round(v * unit) for v in box), outline=color, width=width)

    if name == "settings":
        circle((7, 7, 17, 17))
        circle((10, 10, 14, 14))
        for index in range(8):
            angle = index * math.pi / 4
            line([(12 + math.cos(angle) * 6, 12 + math.sin(angle) * 6),
                  (12 + math.cos(angle) * 9, 12 + math.sin(angle) * 9)])
    elif name in ("collapse", "expand"):
        line([(5, 15 if name == "collapse" else 9), (12, 8 if name == "collapse" else 16),
              (19, 15 if name == "collapse" else 9)])
    elif name == "pin":
        line([(8, 3), (16, 3), (15, 10), (19, 15), (5, 15), (9, 10), (8, 3)])
        line([(12, 15), (12, 22)])
    elif name == "paste":
        rect((5, 5, 19, 21), 2)
        rect((9, 2, 15, 7), 1)
        line([(8, 11), (16, 11)])
        line([(8, 15), (14, 15)])
    elif name == "paste_image":
        rect((4, 5, 21, 22), 2)
        rect((8, 2, 16, 7), 1)
        circle((7, 9, 10, 12))
        line([(6, 19), (11, 14), (14, 17), (17, 12), (20, 17)])
    elif name == "send":
        line([(3, 3), (22, 12), (3, 21), (6, 12), (3, 3)])
        line([(6, 12), (16, 12)])
    elif name in ("check", "permission"):
        circle((3, 3, 21, 21))
        line([(7, 12), (10, 15), (17, 8)])
    elif name == "refresh":
        draw.arc(tuple(round(v * unit) for v in (4, 4, 20, 20)), 35, 315, fill=color, width=width)
        line([(20, 3), (20, 9), (14, 9)])
    elif name == "preview":
        line([(2, 12), (6, 7), (12, 5), (18, 7), (22, 12), (18, 17), (12, 19), (6, 17), (2, 12)])
        circle((9, 9, 15, 15))
    elif name == "image":
        rect((3, 3, 21, 21), 2)
        circle((6, 6, 10, 10))
        line([(4, 18), (10, 12), (14, 16), (17, 11), (21, 15)])
    elif name == "remove":
        line([(5, 5), (19, 19)])
        line([(19, 5), (5, 19)])
    elif name == "new":
        line([(12, 4), (12, 20)])
        line([(4, 12), (20, 12)])
    elif name == "clear_snapshot":
        rect((4, 3, 17, 21), 1)
        line([(8, 7), (13, 7)])
        line([(8, 11), (13, 11)])
        line([(14, 15), (22, 23)])
        line([(22, 15), (14, 23)])
    elif name == "demo":
        line([(8, 4), (8, 20), (20, 12), (8, 4)])
    elif name == "drag":
        for x in (8, 16):
            for y in (5, 12, 19):
                draw.ellipse(tuple(round(v * unit) for v in (x - 1, y - 1, x + 1, y + 1)), fill=color)
    elif name == "resize":
        line([(6, 20), (20, 6)])
        line([(13, 20), (20, 13)])
    else:
        raise ValueError("Unknown icon: " + name)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def make_icon(master, name, size=16, color="#d8e5ec"):
    return ImageTk.PhotoImage(draw_icon(name, size, color), master=master)


class Tooltip:
    """A label inside its existing window; never creates or activates a window."""

    def __init__(self, widget, text, font):
        self.widget, self.text, self.font = widget, text, font
        self.window = widget.winfo_toplevel()
        self.pending = self.label = None
        widget.tooltip_text = text
        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def set_text(self, text):
        self.text = self.widget.tooltip_text = text
        self.hide()

    def schedule(self, _=None):
        self.hide()
        self.pending = self.widget.after(500, self.show)

    def show(self):
        self.pending = None
        if not self.widget.winfo_exists() or not self.widget.winfo_viewable():
            return
        self.label = tk.Label(self.window, text=self.text, font=self.font, bg="#263542", fg="#e7edf2",
                              padx=7, pady=4, borderwidth=0, highlightthickness=1,
                              highlightbackground="#405467", takefocus=False)
        self.label.update_idletasks()
        width, height = self.label.winfo_reqwidth(), self.label.winfo_reqheight()
        x = self.widget.winfo_rootx() - self.window.winfo_rootx()
        y = self.widget.winfo_rooty() - self.window.winfo_rooty() + self.widget.winfo_height() + 3
        x = max(0, min(x, self.window.winfo_width() - width))
        if y + height > self.window.winfo_height():
            y -= self.widget.winfo_height() + height + 6
        self.label.place(x=x, y=max(0, y))
        self.label.lift()

    def hide(self, _=None):
        if self.pending is not None:
            self.widget.after_cancel(self.pending)
            self.pending = None
        if self.label is not None:
            self.label.destroy()
            self.label = None
