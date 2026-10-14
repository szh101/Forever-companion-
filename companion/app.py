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

FOLLOW_CHAT = "跟随聊天"

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
        self.status = tk.StringVar(value="Shift+Enter 发送 · Esc 结束输入" if sys.platform == "win32" else "Shift+Enter 发送 · Enter 换行")
        self.snapshot_label = tk.StringVar()
        self.image_label = tk.StringVar(value="未附图")
        self.is_mac = sys.platform == "darwin"
        self.font = "PingFang SC" if self.is_mac else "Microsoft YaHei UI"
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
            self.drag_handle = self.icon_button(header, "drag", "拖动窗口", lambda: None)
            self.drag_handle.pack(side="left", padx=(0, self.px(2)))
        ttk.Label(header, text="FOREVER", foreground=TEXT, font=(self.font, 9, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self.provider_badge, style="Badge.TLabel").pack(side="left", padx=self.px(5))
        if sys.platform == "win32":
            self.close_button = self.icon_button(header, "remove", "关闭助手", self.root.destroy)
            self.close_button.pack(side="right", padx=(self.px(2), 0))
        self.settings_button = self.icon_button(header, "settings", "设置", self.open_settings)
        self.settings_button.pack(side="right")
        self.fold_button = self.icon_button(header, "collapse", "收起", self.toggle_collapsed)
        self.fold_button.pack(side="right", padx=self.px(2))
        self.pin_button = self.icon_button(header, "pin", "取消置顶", self.toggle_pin, color=ACCENT)
        self.pin_button.pack(side="right")
        self.main_panel = ttk.Frame(outer)
        self.main_panel.pack(fill="both", expand=True)
        ttk.Label(self.main_panel, textvariable=self.snapshot_label, style="Muted.TLabel").pack(
            anchor="w", pady=(self.px(5), self.px(1)))
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
        self.paste_button = self.icon_button(controls, "paste", "粘贴 addon 快照", self.import_snapshot, style="Card.TButton")
        self.paste_button.pack(side="left")
        self.paste_screenshot_button = None
        if sys.platform == "win32":
            self.paste_screenshot_button = self.icon_button(controls, "paste_image", "截图并粘贴 · 仅下一次提问", self.paste_screenshot, style="Card.TButton")
            self.paste_screenshot_button.pack(side="left", padx=(self.px(4), 0))
        if sys.platform == "win32":
            self.resize_handle = self.icon_button(controls, "resize", "拖动调整大小", lambda: None, style="Card.TButton", color=MUTED)
            self.resize_handle.pack(side="right", padx=(self.px(4), 0))
        self.send_button = self.icon_button(controls, "send", "发送 · Shift+Enter", self.send, style="Send.TButton", color="#14212a")
        self.send_button.pack(side="right")
        self.status_widget = ttk.Label(self.main_panel, textvariable=self.status, style="Muted.TLabel",
                                      wraplength=self.px(300))
        self.status_widget.pack(anchor="w", pady=(self.px(5), 0))
        self.interactive_widgets.extend((self.input, self.chat.vbar))
        root.bind("<Configure>", self.resize_status, add="+")
        self.build_settings()
        self.model.trace_add("write", lambda *_: self.describe_model())
        self.update_provider_controls()
        self.append("助手", "粘贴 /fai 的内容，然后直接问我。\n可聊任务、找攻略配图，或画示意图。", "assistant")
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
        self.settings_window.title("Forever AI · 设置")
        self.settings_window.geometry(f"{self.px(420)}x{min(self.px(620), self.root.winfo_screenheight() - self.px(100))}")
        self.settings_window.minsize(self.px(370), self.px(350))
        self.settings_window.configure(bg=BG)
        self.settings_window.protocol("WM_DELETE_WINDOW", self.settings_window.withdraw)
        heading = ttk.Frame(self.settings_window, padding=(self.px(14), self.px(12), self.px(14), self.px(8)))
        heading.pack(fill="x")
        ttk.Label(heading, text="设置", font=(self.font, 14, "bold")).pack(anchor="w")
        ttk.Label(heading, text="按你的习惯，让助手安静地待在游戏旁。", style="Muted.TLabel").pack(anchor="w", pady=(self.px(3), 0))
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
        appearance = card("窗口外观")
        opacity_row = ttk.Frame(appearance, style="Card.TFrame")
        opacity_row.pack(fill="x")
        ttk.Label(opacity_row, text="不透明度", style="Card.TLabel").pack(side="left")
        ttk.Label(opacity_row, textvariable=self.opacity_label, style="Card.TLabel", width=4, anchor="e").pack(side="right")
        self.opacity_slider = ttk.Scale(opacity_row, from_=45, to=100, variable=self.opacity,
                                        command=self.set_opacity, takefocus=False)
        self.opacity_slider.pack(side="left", fill="x", expand=True, padx=self.px(10))
        note(appearance, "45–100% · 仅影响聊天浮窗")

        connection = card("聊天连接")
        settings = form(connection, ("连接方式", "模型", "API key"))
        self.provider_combo = field(ttk.Combobox(settings, textvariable=self.provider, state="readonly",
                                                values=[CODEX_PROVIDER, DEMO_PROVIDER, *MODEL_CHOICES]), 0)
        self.provider_combo.bind("<<ComboboxSelected>>", self.change_provider)
        self.model_combo = field(ttk.Combobox(settings, textvariable=self.model, height=8), 1)
        self.key_entry = field(ttk.Entry(settings, textvariable=self.key, show="•"), 2)
        note(connection, variable=self.model_description, bottom=5)
        codex_bar = ttk.Frame(connection, style="Card.TFrame")
        codex_bar.pack(fill="x", pady=(self.px(3), self.px(4)))
        ttk.Label(codex_bar, text="本机 Codex 登录", style="Card.TLabel").pack(side="left")
        self.icon_button(codex_bar, "check", "检查本机 Codex 登录", self.check_codex).pack(side="right")
        self.search_toggle = ttk.Checkbutton(connection, text="联网查资料", variable=self.search)
        self.search_toggle.pack(anchor="w")
        note(connection, variable=self.search_description)
        note(connection, "Codex 使用官方 CLI 的 ChatGPT 登录。API key 仅保留在本次运行内存中。")

        image_card = card("图片生成", "直接在聊天里描述想画什么。")
        images = form(image_card, ("图片连接", "图片模型", "图片 key"))
        self.image_provider_combo = field(ttk.Combobox(images, textvariable=self.image_provider, state="readonly",
                                                      values=[FOLLOW_CHAT, *IMAGE_MODELS]), 0)
        self.image_provider_combo.bind("<<ComboboxSelected>>", self.change_image_provider)
        self.image_model_combo = field(ttk.Combobox(images, textvariable=self.image_model), 1)
        self.image_key_entry = field(ttk.Entry(images, textvariable=self.image_key, show="•"), 2)
        note(image_card, "Codex 使用自身图片能力；API 按这里的连接生成，每次至多一张，另计费用。附截图时 API 暂不生图。")

        capture_card = card("游戏画面", "点击主窗截图按钮时，未选窗口会自动检测 WoW。" if sys.platform == "win32" else
                            "开启截图后，仅读取你选择的 WoW 窗口。")
        bar = ttk.Frame(capture_card, style="Card.TFrame")
        bar.pack(fill="x", pady=(0, self.px(5)))
        self.window_combo = ttk.Combobox(bar, state="readonly", width=15)
        self.window_combo.pack(side="left", fill="x", expand=True)
        self.icon_button(bar, "refresh", "刷新游戏窗口", self.refresh_windows).pack(side="left", padx=(self.px(5), 0))
        ttk.Checkbutton(capture_card, text="每次发送前截图", variable=self.capture, command=self.toggle_capture).pack(anchor="w")
        if self.is_mac:
            self.icon_button(capture_card, "permission", "授予截图权限", self.grant_capture_permission).pack(anchor="w", pady=self.px(3))
        bar = ttk.Frame(capture_card, style="Card.TFrame")
        bar.pack(fill="x", pady=self.px(4))
        self.preview_button = self.icon_button(bar, "preview", "预览所选窗口", self.preview)
        self.preview_button.pack(side="left")
        self.icon_button(bar, "image", "选择截图文件", self.select_image).pack(side="left", padx=self.px(4))
        self.icon_button(bar, "remove", "移除附图", self.remove_image).pack(side="left")
        note(capture_card, variable=self.image_label)
        note(capture_card, "附图可能包含角色名与聊天。Codex CLI 附图需短暂写入私有临时目录，请求结束删除。")

        session = card("对话与任务")
        bar = ttk.Frame(session, style="Card.TFrame")
        bar.pack(fill="x")
        self.icon_button(bar, "new", "新对话", self.clear_chat).pack(side="left")
        self.icon_button(bar, "clear_snapshot", "移除任务快照", self.remove_snapshot).pack(side="left", padx=self.px(4))
        self.icon_button(bar, "demo", "载入离线示例", self.load_demo).pack(side="left")
        note(session, "游戏内 /fai 复制任务；任务改变后重新粘贴。")

    def resize_status(self, event):
        if event.widget is self.root:
            self.status_widget.configure(wraplength=max(self.px(250), event.width - self.px(16)))

    def toggle_pin(self):
        self.topmost.set(not self.topmost.get())
        self.toggle_topmost()

    def toggle_topmost(self):
        self.root.attributes("-topmost", self.topmost.get())
        self.settings_window.attributes("-topmost", self.topmost.get())
        self.pin_button.configure(image=self.icon("pin", ACCENT if self.topmost.get() else TEXT))
        self.pin_button.tooltip.set_text("取消置顶" if self.topmost.get() else "置顶")

    def toggle_collapsed(self):
        if self.collapsed:
            self.root.minsize(self.px(280), self.px(260))
            self.main_panel.pack(fill="both", expand=True)
            self.root.geometry(self.expanded_size)
            self.fold_button.configure(image=self.icon("collapse"))
            self.fold_button.tooltip.set_text("收起")
        else:
            self.expanded_size = f"{self.root.winfo_width()}x{self.root.winfo_height()}"
            self.main_panel.pack_forget()
            self.root.minsize(self.px(280), self.px(40))
            self.root.geometry(f"{max(self.px(280), self.root.winfo_width())}x{self.px(40)}")
            self.fold_button.configure(image=self.icon("expand"))
            self.fold_button.tooltip.set_text("展开")
        self.collapsed = not self.collapsed

    def open_settings(self):
        self.settings_window.deiconify()
        self.settings_window.attributes("-topmost", self.topmost.get())
        self.settings_window.lift()

    def scroll_settings(self, event):
        delta = int(-event.delta) if self.is_mac else int(-event.delta / 120)
        self.settings_canvas.yview_scroll(delta, "units")

    def describe_model(self):
        self.model_description.set("使用本机 Codex 登录；可手动输入账号支持的模型 ID。" if self.provider.get() == CODEX_PROVIDER
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
        self.status.set("Codex · 使用本机 ChatGPT 登录" if self.active_provider == CODEX_PROVIDER else
                        "已切换连接，请填写对应 API key" if self.active_provider in MODEL_CHOICES else "离线演示 · 不联网")

    def update_provider_controls(self):
        provider = self.provider.get()
        choices = [AUTO_MODEL] if provider == CODEX_PROVIDER else [item[0] for item in MODEL_CHOICES.get(provider, ())]
        self.model_combo.configure(values=choices, state="normal" if choices else "disabled")
        self.model.set(choices[0] if choices else "")
        self.key_entry.configure(state="normal" if provider in MODEL_CHOICES else "disabled")
        self.search.set(self.search_preferences.get(provider, False))
        self.search_toggle.configure(state="normal" if provider in WEB_SEARCH_PROVIDERS or provider == CODEX_PROVIDER else "disabled")
        self.search_description.set("Gemini 暂不支持联网搜索。" if provider == "Gemini" else
                                    "联网需账号与模型支持；查证时请核对 Forever 版本。" if choices else "演示模式不联网。")
        self.provider_badge.set("Codex" if provider == CODEX_PROVIDER else "演示" if provider == DEMO_PROVIDER else provider)
        self.change_image_provider(reset_key=False)

    def change_image_provider(self, _=None, *, reset_key=True):
        if reset_key:
            self.image_key.set("")
        native = self.provider.get() == CODEX_PROVIDER
        self.image_provider_combo.configure(state="disabled" if native or self.provider.get() == DEMO_PROVIDER else "readonly")
        provider = self.provider.get() if native or self.image_provider.get() == FOLLOW_CHAT else self.image_provider.get()
        choices = IMAGE_MODELS.get(provider, ())
        self.image_model_combo.configure(values=choices, state="normal" if choices else "disabled")
        self.image_model.set(choices[0] if choices else "使用聊天模型" if provider == CODEX_PROVIDER else "")
        separate = not native and self.provider.get() != DEMO_PROVIDER and self.image_provider.get() != FOLLOW_CHAT and provider != self.provider.get()
        self.image_key_entry.configure(state="normal" if separate else "disabled")

    def check_codex(self):
        if not self.busy:
            self.status.set("正在检查 Codex 登录…")
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
        self.append("离线示例", "3 个虚构任务：营地补给已完成，森林采集与遗迹探索待完成。")
        self.fill_prompt("根据当前任务列表，建议下一段任务顺序。")
        self.status.set("虚构数据 · 点击发送体验离线流程")

    def accept_snapshot(self, text):
        self.snapshot = parse_snapshot(text)
        self.update_context_label()
        count = len(self.snapshot["quests"])
        self.append("导入成功", f"已收到 {count} 个任务的快照。直接输入问题即可。")
        self.status.set(f"已导入 {count} 个任务 · 继续输入问题")
        if not getattr(self, "game_overlay", None):
            self.input.focus_set()

    def snapshot_error(self, reason):
        shortcut = "⌘C（或 Ctrl+C）" if self.is_mac else "Ctrl+C"
        self.append("没有导入", f"{reason}\n游戏内输入 /fai，按 {shortcut}，再点左下角的粘贴图标。")
        self.status.set("导入未完成 · 复制后重试")

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
            self.snapshot_error("剪贴板没有可读取的文字。")
        except UserError as exc:
            self.snapshot_error(str(exc))

    def remove_snapshot(self):
        self.snapshot = None
        self.update_context_label()

    def update_context_label(self):
        if self.snapshot:
            age = max(0, int(time.time() - self.snapshot["capturedAt"]))
            text = f"{'示例 · ' if self.snapshot.get('demo') else ''}{len(self.snapshot['quests'])} 个任务 · {age // 60} 分钟前"
            text += " · 已过期" if age > 300 else " · 手动快照"
        else:
            text = "无任务快照 · 可直接提问"
        if self.file_shot or self.capture.get():
            text += " · 附图"
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
        self.status.set("新对话 · 任务快照仍保留")

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
            label.bind("<Button-1>", lambda _e, p=picture: self.show_picture(p.png, "AI 示意图" if p.generated else p.caption))
            self.chat.window_create("end", window=label)
            self.chat.insert("end", "\n")
            self.picture_widgets.append(label)
            while len(self.picture_widgets) > 12:
                self.picture_widgets.pop(0).destroy()
        prefix = "AI 示意图 · " if picture.generated else "网页配图 · " if picture.url else "预览图片 · "
        self.chat.insert("end", prefix + picture.caption[:160] + "\n")
        if picture.url:
            self.insert_link("查看图片来源", picture.url)
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
        self.show_picture(shot.png, "截图预览 · 尚未发送")

    def refresh_windows(self):
        try:
            self.windows = list_windows()
            self.window_combo["values"] = [x.label for x in self.windows]
            self.window_combo.set("")
            if len(self.windows) == 1:
                self.window_combo.current(0)
            if not self.windows:
                self.window_combo.set("未发现 WoW 窗口")
        except UserError as exc:
            self.status.set(str(exc))
            self.windows = []
            self.window_combo["values"] = []
            self.window_combo.set("窗口列表暂不可用")

    def selected_window(self):
        index = self.window_combo.current()
        if index < 0 or index >= len(self.windows):
            raise UserError("请先在设置中刷新并选择 WoW 窗口。")
        return self.windows[index]

    def toggle_capture(self):
        self.image_revision += 1
        if self.capture.get():
            self.file_shot = None
        self.image_label.set("发送前捕获所选窗口；建议先预览。" if self.capture.get() else "自动截图已关闭。")
        self.update_context_label()

    def remove_image(self):
        self.image_revision += 1
        self.file_shot = None
        self.capture.set(False)
        self.image_label.set("未附图")
        self.update_context_label()

    def select_image(self):
        path = filedialog.askopenfilename(parent=self.settings_window, title="选择游戏截图", filetypes=[("截图", "*.png *.jpg *.jpeg")])
        if path:
            try:
                shot = load_image(path)
                self.image_revision += 1
                self.file_shot = shot
                self.capture.set(False)
                self.image_label.set("已选截图，仅供下一次提问；原拍摄时间未知。")
                self.update_context_label()
                self.show_image(self.file_shot)
            except (UserError, OSError) as exc:
                self.status.set(str(exc) if isinstance(exc, UserError) else "无法读取所选文件。")

    def paste_screenshot(self):
        if self.busy:
            return
        try:
            window = self.selected_window()
        except UserError:
            self.refresh_windows()
            if not self.windows:
                self.status.set("未发现 WoW 窗口，本次未截图。")
                return
            self.window_combo.current(0)
            window = self.selected_window()
        owner = self.root.winfo_id()
        revision = self.image_revision
        self.status.set("正在截取所选游戏窗口…")
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
                self.jobs.put(("error", "操作失败，请检查所选连接与输入。没有自动重试。"))
        threading.Thread(target=guarded, daemon=True).start()

    def grant_capture_permission(self):
        if not self.busy:
            from .mac_capture import request_permission
            self.status.set("请在系统提示中处理截图权限。")
            self.start_worker(lambda: self.jobs.put(("permission", request_permission())))

    def preview(self):
        if self.busy:
            return
        try:
            window = self.selected_window()
        except UserError as exc:
            self.status.set(str(exc))
            return
        self.status.set("正在预览所选窗口…")
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
            self.status.set("请在设置中填写对应 API key 和模型。")
            return "break"
        image_connection = (ImageConnection(image_provider, image_model, image_key)
                            if provider in MODEL_CHOICES and image_provider in IMAGE_MODELS else None)
        if len(prompt) > 12000:
            self.status.set("问题超过 12000 字。")
            return "break"
        try:
            window = self.selected_window() if self.capture.get() else None
        except UserError as exc:
            self.status.set(str(exc))
            return "break"
        snapshot, shot, history, search = self.snapshot, self.file_shot, list(self.history), self.search.get()
        generation = self.generation
        self.file_shot = None
        self.image_label.set("发送前捕获所选窗口" if window else "未附图")
        self.input.delete("1.0", "end")
        self.append("你", prompt, "user")
        self.status.set("正在回答…")
        def run():
            image = capture_window(window) if window else shot
            if provider == DEMO_PROVIDER:
                from .demo import example_picture
                answer = Answer("离线演示：没有调用 AI，也没有联网。\n" + snapshot_status(snapshot) +
                                "\n真实问答、配图或生图，请在设置中选择 Codex 或 API 连接。",
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
                        if self.status.get() == "正在截取所选游戏窗口…":
                            self.status.set("截图已完成，保留你后续的附图选择。")
                        continue  # A newer attachment choice/removal wins.
                    self.file_shot = shot
                    self.capture.set(False)
                    self.image_label.set("已截取所选游戏窗口，仅供下一次提问。")
                    self.status.set("截图已附加；" + clipboard_error if clipboard_error else
                                    "已截图并复制 · 仅下一次提问 · 自动截图已关闭")
                    self.update_context_label()
                elif kind == "preview":
                    self.show_image(value)
                    self.status.set("预览完成 · 未发送")
                elif kind == "permission":
                    self.status.set("已授权，请刷新窗口并预览。" if value else "请在系统设置中允许屏幕录制后重新打开应用。")
                elif kind == "connection":
                    self.append("连接状态", value)
                    self.status.set("Codex 已登录 · 没有发送模型请求")
                elif kind == "error":
                    self.append("未完成", value)
                    self.status.set("请求未完成 · 没有自动重试")
                else:
                    generation, provider, prompt, answer = value
                    self.append("Codex" if provider == CODEX_PROVIDER else provider, answer.text, "assistant")
                    for picture in answer.images[:3]:
                        self.append_picture(picture)
                    if generation == self.generation and provider == self.provider.get() and provider != DEMO_PROVIDER:
                        self.history.extend([{"role": "user", "content": prompt}, {"role": "assistant", "content": answer.text[:16000]}])
                        self.history = self.history[-8:]
                    if answer.warnings:
                        self.append("核对提示", "\n".join(answer.warnings))
                    self.chat.configure(state="normal")
                    for title, url in answer.sources:
                        self.insert_link("来源：" + title, url)
                        self.chat.insert("end", "\n")
                    self.chat.configure(state="disabled")
                    self.chat.see("end")
                    self.status.set("Shift+Enter 发送 · Esc 结束输入" if self.game_overlay else "Shift+Enter 发送 · Enter 换行")
        except queue.Empty:
            pass
        self.root.after(100, self.pump)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
