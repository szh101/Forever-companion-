"""Compact, always-on-top chat; settings and picture previews open separately."""
from __future__ import annotations

import io
import queue
import re
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, scrolledtext, ttk

from .capture import capture_window, list_windows, load_image
from .clipboard_image import copy_screenshot_to_clipboard
from .core import Answer, UserError, ask, parse_snapshot, safe_source, snapshot_status
from .local_codex import AUTO_MODEL, CODEX_PROVIDER, ask_codex, find_codex, probe_codex, write_probe_diagnostic
from .image_tools import ImageConnection
from .providers import DEMO_PROVIDER, MODEL_CHOICES, WEB_SEARCH_PROVIDERS, model_hint
from .reply_images import IMAGE_MODELS, resolve_images
from .ui_icons import Tooltip, make_icon
from .windows_ui import layout_scale

FOLLOW_CHAT = "Same as chat"

# Shared surfaces keep the compact chat and the separate settings visually related.
BG = "#111820"
SURFACE = "#19232d"
FIELD = "#202d39"
BORDER = "#30404f"
TEXT = "#e7edf2"
MUTED = "#99aab9"
ACCENT = "#e4c68e"


class App:
    def __init__(self, root):
        self.root = root
        self.jobs = queue.Queue()
        self.snapshot = self.file_shot = None
        self.image_revision = 0
        self.history, self.windows, self.picture_widgets = [], [], []
        self.busy = self.collapsed = False
        self.link_number = self.generation = 0
        self.link_urls = {}
        self.ui_scale = layout_scale(root)
        self.px = lambda size: round(size * self.ui_scale)
        self.expanded_size = f"{self.px(320)}x{self.px(380)}"
        self.icons, self.tooltips, self.interactive_widgets = {}, [], []
        try:
            find_codex()
            initial = CODEX_PROVIDER
        except UserError:
            initial = DEMO_PROVIDER
        self.provider = tk.StringVar(value=initial)
        self.active_provider = initial
        self.provider_badge = tk.StringVar()
        self.search_preferences = {name: True for name in (*WEB_SEARCH_PROVIDERS, CODEX_PROVIDER)}
        self.model = tk.StringVar()
        self.model_description = tk.StringVar()
        self.search_description = tk.StringVar()
        self.key = tk.StringVar()
        self.image_provider = tk.StringVar(value=FOLLOW_CHAT)
        self.image_model = tk.StringVar()
        self.image_key = tk.StringVar()
        self.search = tk.BooleanVar(value=False)
        self.capture = tk.BooleanVar(value=False)
        self.topmost = tk.BooleanVar(value=True)
        self.opacity = tk.DoubleVar(value=92.0)
        self.opacity_label = tk.StringVar(value="92%")
        self.status = tk.StringVar(value="Shift+Enter sends · Esc exits input" if sys.platform == "win32" else "Shift+Enter sends · Enter adds a line")
        self.snapshot_label = tk.StringVar()
        self.image_label = tk.StringVar(value="No image attached")
        self.is_mac = sys.platform == "darwin"
        self.font = "Helvetica Neue" if self.is_mac else "Segoe UI"
        root.title("Forever AI")
        root.geometry(self.expanded_size)
        root.minsize(self.px(280), self.px(260))
        root.configure(bg=BG)
        root.attributes("-topmost", True)
        self.set_opacity()
        self.configure_style()
        outer = ttk.Frame(root, padding=self.px(7))
        outer.pack(fill="both", expand=True)
        header = self.main_header = ttk.Frame(outer)
        header.pack(fill="x")
        self.drag_handle = self.close_button = self.resize_handle = None
        if sys.platform == "win32":
            self.drag_handle = self.icon_button(header, "drag", "Drag to move", lambda: None)
            self.drag_handle.pack(side="left", padx=(0, self.px(2)))
        ttk.Label(header, text="FOREVER", foreground=TEXT, font=(self.font, 9, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self.provider_badge, style="Badge.TLabel").pack(side="left", padx=self.px(5))
        if sys.platform == "win32":
            self.close_button = self.icon_button(header, "remove", "Close Forever AI", self.root.destroy)
            self.close_button.pack(side="right", padx=(self.px(2), 0))
        self.settings_button = self.icon_button(header, "settings", "Settings", self.open_settings)
        self.settings_button.pack(side="right")
        self.fold_button = self.icon_button(header, "collapse", "Collapse", self.toggle_collapsed)
        self.fold_button.pack(side="right", padx=self.px(2))
        self.pin_button = self.icon_button(header, "pin", "Unpin window", self.toggle_pin, color=ACCENT)
        self.pin_button.pack(side="right")
        self.main_panel = ttk.Frame(outer)
        self.main_panel.pack(fill="both", expand=True)
        self.snapshot_widget = ttk.Label(self.main_panel, textvariable=self.snapshot_label, style="Muted.TLabel",
                                        wraplength=self.px(300))
        self.snapshot_widget.pack(anchor="w", pady=(self.px(5), self.px(1)))
        self.chat = scrolledtext.ScrolledText(self.main_panel, wrap="word", bg=BG, fg=TEXT,
                                             insertbackground="white", relief="flat", font=(self.font, 10),
                                             width=1, height=1, padx=self.px(3), pady=self.px(7), spacing3=self.px(4),
                                             highlightthickness=0, borderwidth=0, takefocus=False)
        self.chat.frame.configure(background=BG)
        self.chat.vbar.configure(background=BORDER, troughcolor=BG, activebackground="#465968",
                                 relief="flat", borderwidth=0, highlightthickness=0,
                                 width=self.px(7), elementborderwidth=0)
        for tag, color in (("user", "#a4ced7"), ("assistant", ACCENT), ("note", MUTED)):
            self.chat.tag_configure(tag, foreground=color, font=(self.font, 9, "bold"))
        self.chat.configure(state="disabled")
        self.chat.pack(fill="both", expand=True, pady=(0, self.px(5)))
        composer = tk.Frame(self.main_panel, bg=SURFACE, highlightthickness=1,
                            highlightbackground=BORDER, borderwidth=0)
        composer.pack(fill="x")
        self.input = tk.Text(composer, width=1, height=2, wrap="word", bg=SURFACE, fg=TEXT,
                             insertbackground=ACCENT, relief="flat", font=(self.font, 10),
                             padx=self.px(8), pady=self.px(7), borderwidth=0,
                             selectbackground="#405467", selectforeground=TEXT,
                             highlightthickness=0)
        self.input.bind("<FocusIn>", lambda _: composer.configure(highlightbackground=ACCENT), add="+")
        self.input.bind("<FocusOut>", lambda _: composer.configure(highlightbackground=BORDER), add="+")
        self.input.bind("<Shift-Return>", self.send)
        self.input.bind("<<Paste>>", self.paste_input)
        self.input.pack(fill="x")
        controls = self.controls = ttk.Frame(composer, style="Card.TFrame")
        controls.pack(fill="x", padx=self.px(4), pady=(0, self.px(4)))
        self.paste_button = self.icon_button(controls, "paste", "Paste AddOn snapshot", self.import_snapshot, style="Card.TButton")
        self.paste_button.pack(side="left")
        self.paste_screenshot_button = None
        if sys.platform in ("win32", "darwin"):
            self.paste_screenshot_button = self.icon_button(controls, "paste_image", "Capture & paste · next message", self.paste_screenshot, style="Card.TButton")
            self.paste_screenshot_button.pack(side="left", padx=(self.px(4), 0))
        if sys.platform == "win32":
            self.resize_handle = self.icon_button(controls, "resize", "Drag to resize", lambda: None, style="Card.TButton", color=MUTED)
            self.resize_handle.pack(side="right", padx=(self.px(4), 0))
        self.send_button = self.icon_button(controls, "send", "Send · Shift+Enter", self.send, style="Send.TButton", color="#14212a")
        self.send_button.pack(side="right")
        self.status_widget = ttk.Label(self.main_panel, textvariable=self.status, style="Muted.TLabel",
                                      wraplength=self.px(300))
        self.status_widget.pack(anchor="w", pady=(self.px(5), 0))
        self.interactive_widgets.extend((self.input, self.chat.vbar))
        root.bind("<Configure>", self.resize_status, add="+")
        self.build_settings()
        self.model.trace_add("write", lambda *_: self.describe_model())
        self.update_provider_controls()
        self.append("Assistant", "Paste your /fai snapshot, then ask a question.\nPlan quests, find guide images, or create a diagram.", "assistant")
        self.tick()
        root.after(100, self.pump)
        self.game_overlay = None
        if sys.platform == "win32":
            from .overlay_ui import GameOverlay
            self.game_overlay = GameOverlay(self)

    def configure_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=SURFACE)
        style.configure("TLabel", background=BG, foreground=TEXT, font=(self.font, 9))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Card.TLabel", background=SURFACE)
        style.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED)
        style.configure("CardTitle.TLabel", background=SURFACE, foreground=TEXT, font=(self.font, 10, "bold"))
        style.configure("Badge.TLabel", background=SURFACE, foreground=ACCENT,
                        padding=(self.px(4), self.px(1)))
        style.configure("TCheckbutton", background=SURFACE, foreground=TEXT, font=(self.font, 9),
                        indicatorbackground=FIELD, indicatorforeground=ACCENT,
                        bordercolor=BORDER, padding=(0, self.px(3)))
        style.map("TCheckbutton", background=[("active", SURFACE)],
                  foreground=[("disabled", "#647585")],
                  indicatorbackground=[("selected", ACCENT), ("disabled", SURFACE)])
        style.configure("TButton", font=(self.font, 9), padding=(self.px(5), self.px(4)),
                        background=BG, foreground=TEXT, bordercolor=BG, lightcolor=BG,
                        darkcolor=BG, borderwidth=0, relief="flat", width=-1, focusthickness=0)
        style.configure("Small.TButton", padding=(self.px(4), self.px(3)))
        style.configure("Card.TButton", background=SURFACE, bordercolor=SURFACE,
                        lightcolor=SURFACE, darkcolor=SURFACE, padding=(self.px(5), self.px(4)))
        style.map("TButton", background=[("pressed", "#354655"), ("active", "#263542")],
                  foreground=[("disabled", "#647585")])
        style.configure("Send.TButton", background=ACCENT, foreground=BG,
                        bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT,
                        padding=(self.px(10), self.px(4)))
        style.map("Send.TButton", background=[("disabled", "#716b5d"), ("pressed", "#c7a96f"), ("active", "#f0d9ab")])
        for name in ("TEntry", "TCombobox"):
            style.configure(name, fieldbackground=FIELD, background=FIELD, foreground=TEXT,
                            insertcolor=TEXT, arrowcolor=MUTED, bordercolor=BORDER,
                            lightcolor=BORDER, darkcolor=BORDER, font=(self.font, 9),
                            padding=(self.px(6), self.px(5)), borderwidth=1)
            style.map(name, fieldbackground=[("disabled", SURFACE), ("readonly", FIELD)],
                      foreground=[("disabled", "#647585"), ("readonly", TEXT)],
                      bordercolor=[("focus", ACCENT)], arrowcolor=[("disabled", "#647585")])
        style.configure("Vertical.TScrollbar", background=BORDER, troughcolor=BG,
                        bordercolor=BG, lightcolor=BORDER, darkcolor=BORDER,
                        arrowcolor=MUTED, arrowsize=self.px(8), borderwidth=0)
        style.map("Vertical.TScrollbar", background=[("active", "#465968")])
        style.configure("Horizontal.TScale", background=SURFACE, troughcolor=FIELD,
                        bordercolor=SURFACE, lightcolor=ACCENT, darkcolor=ACCENT,
                        sliderlength=self.px(16))
        for key, value in (("background", FIELD), ("foreground", TEXT),
                           ("selectBackground", "#405467"), ("selectForeground", TEXT), ("font", (self.font, 9))):
            self.root.option_add("*TCombobox*Listbox." + key, value)

    def icon(self, name, color="#d8e5ec"):
        key = (name, color)
        if key not in self.icons:
            self.icons[key] = make_icon(self.root, name, self.px(16), color)
        return self.icons[key]

    def icon_button(self, parent, name, label, command, *, style="Small.TButton", color="#d8e5ec"):
        if style == "Small.TButton" and parent.winfo_toplevel() is not self.root:
            style = "Card.TButton"
        button = ttk.Button(parent, image=self.icon(name, color), command=command, style=style, takefocus=False)
        button.tooltip = Tooltip(button, label, (self.font, 9))
        self.tooltips.append(button.tooltip)
        if parent.winfo_toplevel() is self.root:
            self.interactive_widgets.append(button)
        return button

    def set_opacity(self, value=None):
        amount = max(45.0, min(100.0, float(self.opacity.get() if value is None else value)))
        self.opacity.set(amount)
        self.opacity_label.set(f"{amount:.0f}%")
        self.root.attributes("-alpha", amount / 100.0)
        if getattr(self, "game_overlay", None):
            self.game_overlay.set_opacity(amount / 100.0)

    def build_settings(self):
        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.withdraw()
        self.settings_window.title("Forever AI · Settings")
        self.settings_window.geometry(f"{self.px(420)}x{min(self.px(620), self.root.winfo_screenheight() - self.px(100))}")
        self.settings_window.minsize(self.px(370), self.px(350))
        self.settings_window.configure(bg=BG)
        self.settings_window.protocol("WM_DELETE_WINDOW", self.settings_window.withdraw)
        heading = ttk.Frame(self.settings_window, padding=(self.px(14), self.px(12), self.px(14), self.px(8)))
        heading.pack(fill="x")
        ttk.Label(heading, text="Settings", font=(self.font, 14, "bold")).pack(anchor="w")
        ttk.Label(heading, text="Make room for your game.", style="Muted.TLabel").pack(anchor="w", pady=(self.px(3), 0))
        self.settings_canvas = tk.Canvas(self.settings_window, bg=BG, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(self.settings_window, orient="vertical", command=self.settings_canvas.yview)
        self.settings_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", padx=(0, self.px(3)))
        self.settings_canvas.pack(side="left", fill="both", expand=True)
        page = ttk.Frame(self.settings_canvas, padding=(self.px(12), self.px(2), self.px(8), self.px(12)))
        item = self.settings_canvas.create_window((0, 0), window=page, anchor="nw")
        page.bind("<Configure>", lambda _: self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all")))
        self.settings_window.bind("<MouseWheel>", self.scroll_settings, add="+")
        self.settings_notes = []

        def card(title, subtitle=None):
            outline = tk.Frame(page, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER, borderwidth=0)
            outline.pack(fill="x", pady=(0, self.px(9)))
            body = ttk.Frame(outline, style="Card.TFrame", padding=self.px(11))
            body.pack(fill="x")
            ttk.Label(body, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, self.px(7)))
            if subtitle:
                note(body, subtitle, bottom=8)
            return body

        def note(parent, text=None, *, variable=None, bottom=0):
            label = ttk.Label(parent, text=text, textvariable=variable, style="CardMuted.TLabel",
                              wraplength=self.px(350), justify="left")
            label.pack(anchor="w", fill="x", pady=(self.px(3), self.px(bottom)))
            self.settings_notes.append(label)
            return label

        def form(parent, labels):
            grid = ttk.Frame(parent, style="Card.TFrame")
            grid.pack(fill="x")
            grid.columnconfigure(1, weight=1)
            for row, label in enumerate(labels):
                ttk.Label(grid, text=label, style="Card.TLabel").grid(
                    row=row, column=0, sticky="w", padx=(0, self.px(10)), pady=self.px(4))
            return grid

        def field(widget, row):
            widget.grid(row=row, column=1, sticky="ew", pady=self.px(4))
            return widget

        def resize_notes(event):
            self.settings_canvas.itemconfigure(item, width=event.width)
            width = max(self.px(240), event.width - self.px(46))
            for label in self.settings_notes:
                label.configure(wraplength=width)

        self.settings_canvas.bind("<Configure>", resize_notes)
        appearance = card("Appearance")
        opacity_row = ttk.Frame(appearance, style="Card.TFrame")
        opacity_row.pack(fill="x")
        ttk.Label(opacity_row, text="Opacity", style="Card.TLabel").pack(side="left")
        ttk.Label(opacity_row, textvariable=self.opacity_label, style="Card.TLabel", width=4, anchor="e").pack(side="right")
        self.opacity_slider = ttk.Scale(opacity_row, from_=45, to=100, variable=self.opacity,
                                        command=self.set_opacity, takefocus=False)
        self.opacity_slider.pack(side="left", fill="x", expand=True, padx=self.px(10))
        note(appearance, "45–100% · Chat window only")

        connection = card("Chat connection")
        settings = form(connection, ("Provider", "Model", "API key"))
        self.provider_combo = field(ttk.Combobox(settings, textvariable=self.provider, state="readonly",
                                                values=[CODEX_PROVIDER, DEMO_PROVIDER, *MODEL_CHOICES]), 0)
        self.provider_combo.bind("<<ComboboxSelected>>", self.change_provider)
        self.model_combo = field(ttk.Combobox(settings, textvariable=self.model, height=8), 1)
        self.key_entry = field(ttk.Entry(settings, textvariable=self.key, show="•"), 2)
        note(connection, variable=self.model_description, bottom=5)
        codex_bar = ttk.Frame(connection, style="Card.TFrame")
        codex_bar.pack(fill="x", pady=(self.px(3), self.px(4)))
        ttk.Label(codex_bar, text="Codex sign-in", style="Card.TLabel").pack(side="left")
        self.icon_button(codex_bar, "check", "Check Codex sign-in", self.check_codex).pack(side="right")
        self.search_toggle = ttk.Checkbutton(connection, text="Search the web", variable=self.search)
        self.search_toggle.pack(anchor="w")
        note(connection, variable=self.search_description)
        note(connection, "Codex uses your ChatGPT sign-in in the official CLI. API keys stay in memory until you close the app.")

        image_card = card("Image generation", "Describe the image you want in chat.")
        images = form(image_card, ("Provider", "Model", "API key"))
        self.image_provider_combo = field(ttk.Combobox(images, textvariable=self.image_provider, state="readonly",
                                                      values=[FOLLOW_CHAT, *IMAGE_MODELS]), 0)
        self.image_provider_combo.bind("<<ComboboxSelected>>", self.change_image_provider)
        self.image_model_combo = field(ttk.Combobox(images, textvariable=self.image_model), 1)
        self.image_key_entry = field(ttk.Entry(images, textvariable=self.image_key, show="•"), 2)
        note(image_card, "Codex uses its own image tools. API chat uses this connection for up to one image per message, billed separately. API image generation is unavailable with an attached screenshot.")

        capture_card = card("Game screenshots", "The chat capture button finds a WoW window if none is selected." if sys.platform in ("win32", "darwin") else
                            "Capture reads only the WoW window you select.")
        bar = ttk.Frame(capture_card, style="Card.TFrame")
        bar.pack(fill="x", pady=(0, self.px(5)))
        self.window_combo = ttk.Combobox(bar, state="readonly", width=15)
        self.window_combo.pack(side="left", fill="x", expand=True)
        self.icon_button(bar, "refresh", "Refresh game windows", self.refresh_windows).pack(side="left", padx=(self.px(5), 0))
        ttk.Checkbutton(capture_card, text="Capture before each message", variable=self.capture, command=self.toggle_capture).pack(anchor="w")
        if self.is_mac:
            self.icon_button(capture_card, "permission", "Allow screen recording", self.grant_capture_permission).pack(anchor="w", pady=self.px(3))
        bar = ttk.Frame(capture_card, style="Card.TFrame")
        bar.pack(fill="x", pady=self.px(4))
        self.preview_button = self.icon_button(bar, "preview", "Preview selected window", self.preview)
        self.preview_button.pack(side="left")
        self.icon_button(bar, "image", "Choose screenshot file", self.select_image).pack(side="left", padx=self.px(4))
        self.icon_button(bar, "remove", "Remove image", self.remove_image).pack(side="left")
        note(capture_card, variable=self.image_label)
        note(capture_card, "Images may include character names and chat. Codex CLI attachments use a private temporary folder, deleted when the request ends.")

        session = card("Chat and quests")
        bar = ttk.Frame(session, style="Card.TFrame")
        bar.pack(fill="x")
        self.icon_button(bar, "new", "New chat", self.clear_chat).pack(side="left")
        self.icon_button(bar, "clear_snapshot", "Remove quest snapshot", self.remove_snapshot).pack(side="left", padx=self.px(4))
        self.icon_button(bar, "demo", "Load offline demo", self.load_demo).pack(side="left")
        note(session, "Use /fai in game to copy a snapshot. Paste a new one when your quests change.")

    def resize_status(self, event):
        if event.widget is self.root:
            width = max(self.px(250), event.width - self.px(16))
            self.status_widget.configure(wraplength=width)
            self.snapshot_widget.configure(wraplength=width)

    def toggle_pin(self):
        self.topmost.set(not self.topmost.get())
        self.toggle_topmost()

    def toggle_topmost(self):
        self.root.attributes("-topmost", self.topmost.get())
        self.settings_window.attributes("-topmost", self.topmost.get())
        self.pin_button.configure(image=self.icon("pin", ACCENT if self.topmost.get() else TEXT))
        self.pin_button.tooltip.set_text("Unpin window" if self.topmost.get() else "Keep on top")

    def toggle_collapsed(self):
        if self.collapsed:
            self.root.minsize(self.px(280), self.px(260))
            self.main_panel.pack(fill="both", expand=True)
            self.root.geometry(self.expanded_size)
            self.fold_button.configure(image=self.icon("collapse"))
            self.fold_button.tooltip.set_text("Collapse")
        else:
            self.expanded_size = f"{self.root.winfo_width()}x{self.root.winfo_height()}"
            self.main_panel.pack_forget()
            self.root.minsize(self.px(280), self.px(40))
            self.root.geometry(f"{max(self.px(280), self.root.winfo_width())}x{self.px(40)}")
            self.fold_button.configure(image=self.icon("expand"))
            self.fold_button.tooltip.set_text("Expand")
        self.collapsed = not self.collapsed

    def open_settings(self):
        self.settings_window.deiconify()
        self.settings_window.attributes("-topmost", self.topmost.get())
        self.settings_window.lift()

    def scroll_settings(self, event):
        delta = int(-event.delta) if self.is_mac else int(-event.delta / 120)
        self.settings_canvas.yview_scroll(delta, "units")

    def describe_model(self):
        self.model_description.set("Uses your local Codex sign-in. You can enter a model ID available to your account." if self.provider.get() == CODEX_PROVIDER
                                   else model_hint(self.provider.get(), self.model.get()))

    def change_provider(self, _=None):
        if self.provider.get() == self.active_provider:
            return
        self.search_preferences[self.active_provider] = self.search.get()
        self.active_provider = self.provider.get()
        self.key.set("")
        self.update_provider_controls()
        self.history.clear()
        self.generation += 1
        if self.snapshot and self.snapshot.get("demo"):
            self.remove_snapshot()
        self.status.set("Codex · Uses your ChatGPT sign-in" if self.active_provider == CODEX_PROVIDER else
                        "Provider changed · Enter its API key" if self.active_provider in MODEL_CHOICES else "Offline demo · No network")

    def update_provider_controls(self):
        provider = self.provider.get()
        choices = [AUTO_MODEL] if provider == CODEX_PROVIDER else [item[0] for item in MODEL_CHOICES.get(provider, ())]
        self.model_combo.configure(values=choices, state="normal" if choices else "disabled")
        self.model.set(choices[0] if choices else "")
        self.key_entry.configure(state="normal" if provider in MODEL_CHOICES else "disabled")
        self.search.set(self.search_preferences.get(provider, False))
        self.search_toggle.configure(state="normal" if provider in WEB_SEARCH_PROVIDERS or provider == CODEX_PROVIDER else "disabled")
        self.search_description.set("Web search is not available for Gemini here." if provider == "Gemini" else
                                    "Web search requires account and model support." if choices else "The demo stays offline.")
        self.provider_badge.set("Codex" if provider == CODEX_PROVIDER else "Demo" if provider == DEMO_PROVIDER else provider)
        self.change_image_provider(reset_key=False)

    def change_image_provider(self, _=None, *, reset_key=True):
        if reset_key:
            self.image_key.set("")
        native = self.provider.get() == CODEX_PROVIDER
        self.image_provider_combo.configure(state="disabled" if native or self.provider.get() == DEMO_PROVIDER else "readonly")
        provider = self.provider.get() if native or self.image_provider.get() == FOLLOW_CHAT else self.image_provider.get()
        choices = IMAGE_MODELS.get(provider, ())
        self.image_model_combo.configure(values=choices, state="normal" if choices else "disabled")
        self.image_model.set(choices[0] if choices else "Chat model" if provider == CODEX_PROVIDER else "")
        separate = not native and self.provider.get() != DEMO_PROVIDER and self.image_provider.get() != FOLLOW_CHAT and provider != self.provider.get()
        self.image_key_entry.configure(state="normal" if separate else "disabled")

    def check_codex(self):
        if not self.busy:
            self.status.set("Checking Codex sign-in…")
            self.start_worker(lambda: self.jobs.put(("connection", probe_codex())))

    def fill_prompt(self, prompt):
        if not self.busy:
            self.input.delete("1.0", "end")
            self.input.insert("1.0", prompt)
            if not getattr(self, "game_overlay", None):
                self.input.focus_set()

    def load_demo(self):
        if self.busy:
            return
        self.provider.set(DEMO_PROVIDER)
        self.change_provider()
        from .demo import snapshot
        self.snapshot = snapshot()
        self.update_context_label()
        self.append("Offline demo", "Three fictional quests: Camp Supplies is complete; Forest Gathering and Explore the Ruins are still in progress.")
        self.fill_prompt("Suggest what to do next based on my current quest list.")
        self.status.set("Fictional data · Send to try the demo")

    def accept_snapshot(self, text):
        self.snapshot = parse_snapshot(text)
        self.update_context_label()
        count = len(self.snapshot["quests"])
        self.append("Import successful", f"Snapshot received: {count} quests. You can now ask a question.")
        self.status.set(f"Imported {count} quests · Ask a question")
        if not getattr(self, "game_overlay", None):
            self.input.focus_set()

    def snapshot_error(self, reason):
        shortcut = "⌘C (or Ctrl+C)" if self.is_mac else "Ctrl+C"
        self.append("Import failed", f"{reason}\nType /fai in game, press {shortcut}, then click the paste icon at the bottom left.")
        self.status.set("Import failed · Copy and try again")

    def paste_input(self, _=None):
        try:
            text = self.root.clipboard_get()
            if text.lstrip().startswith("{") and "forever-ai-snapshot" in text[:200000]:
                self.accept_snapshot(text)
                return "break"
        except tk.TclError:
            pass
        except UserError as exc:
            self.snapshot_error(str(exc))
            return "break"
        return None

    def import_snapshot(self):
        try:
            self.accept_snapshot(self.root.clipboard_get())
        except tk.TclError:
            self.snapshot_error("No readable text on the clipboard.")
        except UserError as exc:
            self.snapshot_error(str(exc))

    def remove_snapshot(self):
        self.snapshot = None
        self.update_context_label()

    def update_context_label(self):
        if self.snapshot:
            age = max(0, int(time.time() - self.snapshot["capturedAt"]))
            text = f"{'Demo · ' if self.snapshot.get('demo') else ''}{len(self.snapshot['quests'])} quests · {age // 60}m ago"
            text += " · Stale" if age > 300 else " · Snapshot"
        else:
            text = "No snapshot · Ask anything"
        if self.file_shot or self.capture.get():
            text += " · Image"
        self.snapshot_label.set(text)

    def tick(self):
        self.update_context_label()
        self.root.after(1000, self.tick)

    def clear_chat(self):
        if self.busy:
            return
        self.history.clear()
        self.generation += 1
        for widget in self.picture_widgets:
            widget.destroy()
        self.picture_widgets.clear()
        self.link_urls.clear()
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.status.set("New chat · Quest snapshot kept")

    def insert_link(self, label, url):
        if not safe_source(label, url):
            self.chat.insert("end", label)
            return
        self.link_number += 1
        tag = f"link-{self.link_number}"
        self.link_urls[tag] = url
        self.chat.insert("end", label, tag)
        self.chat.tag_configure(tag, foreground="#8dccdb", underline=True)
        self.chat.tag_bind(tag, "<Button-1>", lambda _e, u=url: webbrowser.open(u))

    def open_source(self, tag):
        if tag in self.link_urls:
            webbrowser.open(self.link_urls[tag])

    def append(self, name, text, tag="note"):
        self.chat.configure(state="normal")
        self.chat.insert("end", name + "\n", tag)
        start = 0
        for match in re.finditer(r"(?<!!)\[([^\]\n]+)\]\((https?://[^\s)]+)\)", text):
            self.chat.insert("end", text[start:match.start()])
            self.insert_link(match[1], match[2])
            start = match.end()
        self.chat.insert("end", text[start:] + "\n\n")
        if len(self.chat.get("1.0", "end")) > 120000:
            self.chat.delete("1.0", "end-100000c")
        # Text deletion removes link ranges but not tag bindings/URL closures.
        for old in self.chat.tag_names():
            if old.startswith("link-") and not self.chat.tag_ranges(old):
                self.chat.tag_delete(old)
                self.link_urls.pop(old, None)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def append_picture(self, picture):
        self.chat.configure(state="normal")
        if picture.png:
            from PIL import Image, ImageTk
            preview = Image.open(io.BytesIO(picture.png))
            preview.thumbnail((min(self.px(280), max(self.px(230), self.root.winfo_width() - self.px(65))), self.px(200)))
            photo = ImageTk.PhotoImage(preview)
            label = tk.Label(self.chat, image=photo, bg=BG, cursor="hand2", borderwidth=0)
            label.image = photo
            label.bind("<Button-1>", lambda _e, p=picture: self.show_picture(p.png, "AI illustration" if p.generated else p.caption))
            self.chat.window_create("end", window=label)
            self.chat.insert("end", "\n")
            self.picture_widgets.append(label)
            while len(self.picture_widgets) > 12:
                self.picture_widgets.pop(0).destroy()
        prefix = "AI illustration · " if picture.generated else "Web image · " if picture.url else "Image preview · "
        self.chat.insert("end", prefix + picture.caption[:160] + "\n")
        if picture.url:
            self.insert_link("View image source", picture.url)
            self.chat.insert("end", "\n")
        self.chat.insert("end", "\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def show_picture(self, png, title):
        from PIL import Image, ImageTk
        popup = tk.Toplevel(self.root)
        popup.title(title[:100])
        popup.attributes("-topmost", self.topmost.get())
        picture = Image.open(io.BytesIO(png))
        picture.thumbnail((min(960, self.root.winfo_screenwidth() - 80), min(720, self.root.winfo_screenheight() - 120)))
        image = ImageTk.PhotoImage(picture)
        label = tk.Label(popup, image=image, bg=BG)
        label.image = image
        label.pack()
        popup.bind("<Escape>", lambda _: popup.destroy())

    def show_image(self, shot):
        self.show_picture(shot.png, "Screenshot preview · Not sent")

    def refresh_windows(self):
        try:
            self.windows = list_windows()
            self.window_combo["values"] = [x.label for x in self.windows]
            self.window_combo.set("")
            if len(self.windows) == 1:
                self.window_combo.current(0)
            if not self.windows:
                self.window_combo.set("No WoW window found")
            return True
        except UserError as exc:
            self.status.set(str(exc))
            self.windows = []
            self.window_combo["values"] = []
            self.window_combo.set("Window list unavailable")
            return False

    def selected_window(self):
        index = self.window_combo.current()
        if index < 0 or index >= len(self.windows):
            raise UserError("Refresh and select a WoW window in Settings first.")
        return self.windows[index]

    def toggle_capture(self):
        self.image_revision += 1
        if self.capture.get():
            self.file_shot = None
        self.image_label.set("Captures the selected window before sending. Preview it first." if self.capture.get() else "Automatic capture is off.")
        self.update_context_label()

    def remove_image(self):
        self.image_revision += 1
        self.file_shot = None
        self.capture.set(False)
        self.image_label.set("No image attached")
        self.update_context_label()

    def select_image(self):
        path = filedialog.askopenfilename(parent=self.settings_window, title="Choose game screenshot", filetypes=[("Screenshots", "*.png *.jpg *.jpeg")])
        if path:
            try:
                shot = load_image(path)
                self.image_revision += 1
                self.file_shot = shot
                self.capture.set(False)
                self.image_label.set("Screenshot attached for the next message. Original capture time is unknown.")
                self.update_context_label()
                self.show_image(self.file_shot)
            except (UserError, OSError) as exc:
                self.status.set(str(exc) if isinstance(exc, UserError) else "Could not read the selected file.")

    def paste_screenshot(self):
        if self.busy:
            return
        try:
            window = self.selected_window()
        except UserError:
            if not self.refresh_windows():
                return  # Preserve the specific enumeration/permission error.
            if not self.windows:
                self.status.set("No WoW window found · Nothing captured")
                return
            self.window_combo.current(0)
            window = self.selected_window()
        owner = self.root.winfo_id()
        revision = self.image_revision
        self.status.set("Capturing the selected game window…")
        def run():
            shot = capture_window(window)
            clipboard_error = None
            try:
                copy_screenshot_to_clipboard(shot.png, owner)
            except UserError as exc:
                clipboard_error = str(exc)
            self.jobs.put(("manual_screenshot", (shot, clipboard_error, revision)))
        self.start_worker(run)

    def start_worker(self, fn):
        self.busy = True
        self.send_button.configure(state="disabled")
        self.preview_button.configure(state="disabled")
        if self.paste_screenshot_button:
            self.paste_screenshot_button.configure(state="disabled")
        def guarded():
            try:
                fn()
            except UserError as exc:
                write_probe_diagnostic(exc)
                self.jobs.put(("error", str(exc)))
            except Exception:
                self.jobs.put(("error", "Something went wrong. Check your connection settings and input. No automatic retry was made."))
        threading.Thread(target=guarded, daemon=True).start()

    def grant_capture_permission(self):
        if not self.busy:
            from .mac_capture import request_permission
            self.status.set("Respond to the system's screen recording prompt.")
            self.start_worker(lambda: self.jobs.put(("permission", request_permission())))

    def preview(self):
        if self.busy:
            return
        try:
            window = self.selected_window()
        except UserError as exc:
            self.status.set(str(exc))
            return
        self.status.set("Previewing the selected window…")
        self.start_worker(lambda: self.jobs.put(("preview", capture_window(window))))

    def send(self, _=None):
        if self.busy:
            return "break"
        prompt = self.input.get("1.0", "end").strip()
        if not prompt:
            return "break"
        if prompt.startswith("{") and "forever-ai-snapshot" in prompt[:200000]:
            try:
                self.accept_snapshot(prompt)
                self.input.delete("1.0", "end")
            except UserError as exc:
                self.snapshot_error(str(exc))
            return "break"
        provider, model, key = self.provider.get(), self.model.get().strip(), self.key.get()
        image_provider = provider if self.image_provider.get() == FOLLOW_CHAT else self.image_provider.get()
        image_key = key if image_provider == provider else self.image_key.get()
        image_model = self.image_model.get().strip()
        if provider in MODEL_CHOICES and (not key.strip() or not model):
            self.status.set("Enter an API key and model in Settings.")
            return "break"
        image_connection = (ImageConnection(image_provider, image_model, image_key)
                            if provider in MODEL_CHOICES and image_provider in IMAGE_MODELS else None)
        if len(prompt) > 12000:
            self.status.set("Your message exceeds 12,000 characters.")
            return "break"
        try:
            window = self.selected_window() if self.capture.get() else None
        except UserError as exc:
            self.status.set(str(exc))
            return "break"
        snapshot, shot, history, search = self.snapshot, self.file_shot, list(self.history), self.search.get()
        generation = self.generation
        self.file_shot = None
        self.image_label.set("Captures the selected window before sending" if window else "No image attached")
        self.input.delete("1.0", "end")
        self.append("You", prompt, "user")
        self.status.set("Thinking…")
        def run():
            image = capture_window(window) if window else shot
            if provider == DEMO_PROVIDER:
                from .demo import example_picture
                answer = Answer("Offline demo: no AI request or network connection was made.\n" + snapshot_status(snapshot) +
                                "\nChoose Codex or an API connection in Settings for answers, guide images, or image generation.",
                                images=[example_picture()])
            elif provider == CODEX_PROVIDER:
                answer = ask_codex(model, prompt, snapshot=snapshot, screenshot=image, history=history, search=search)
            else:
                answer = ask(provider, key, model, prompt, snapshot=snapshot, screenshot=image, history=history,
                             search=search, image_connection=image_connection)
            resolve_images(answer)
            self.jobs.put(("answer", (generation, provider, prompt, answer)))
        self.start_worker(run)
        if self.game_overlay:
            self.game_overlay.release_input()
        return "break"

    def pump(self):
        try:
            while True:
                kind, value = self.jobs.get_nowait()
                self.busy = False
                self.send_button.configure(state="normal")
                self.preview_button.configure(state="normal")
                if self.paste_screenshot_button:
                    self.paste_screenshot_button.configure(state="normal")
                if kind == "manual_screenshot":
                    shot, clipboard_error, revision = value
                    if revision != self.image_revision:
                        if self.status.get() == "Capturing the selected game window…":
                            self.status.set("Capture complete · Your newer image selection was kept")
                        continue  # A newer attachment choice/removal wins.
                    self.file_shot = shot
                    self.capture.set(False)
                    self.image_label.set("Game screenshot attached for the next message.")
                    self.status.set("Screenshot attached; " + clipboard_error if clipboard_error else
                                    "Captured & copied · Next message only · Auto-capture off")
                    self.update_context_label()
                elif kind == "preview":
                    self.show_image(value)
                    self.status.set("Preview ready · Not sent")
                elif kind == "permission":
                    self.status.set("Permission granted · Refresh windows and preview" if value else "Allow screen recording in System Settings, then reopen the app.")
                elif kind == "connection":
                    self.append("Connection status", value)
                    self.status.set("Codex signed in · No model request sent")
                elif kind == "error":
                    self.append("Request incomplete", value)
                    self.status.set("Request incomplete · No automatic retry")
                else:
                    generation, provider, prompt, answer = value
                    self.append("Codex" if provider == CODEX_PROVIDER else provider, answer.text, "assistant")
                    for picture in answer.images[:3]:
                        self.append_picture(picture)
                    if generation == self.generation and provider == self.provider.get() and provider != DEMO_PROVIDER:
                        self.history.extend([{"role": "user", "content": prompt}, {"role": "assistant", "content": answer.text[:16000]}])
                        self.history = self.history[-8:]
                    if answer.warnings:
                        self.append("Note", "\n".join(answer.warnings))
                    self.chat.configure(state="normal")
                    for title, url in answer.sources:
                        self.insert_link("Source: " + title, url)
                        self.chat.insert("end", "\n")
                    self.chat.configure(state="disabled")
                    self.chat.see("end")
                    self.status.set("Shift+Enter sends · Esc exits input" if self.game_overlay else "Shift+Enter sends · Enter adds a line")
        except queue.Empty:
            pass
        self.root.after(100, self.pump)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
