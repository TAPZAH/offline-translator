import ctypes
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from app_settings import UI_THEME_DARK, get_ui_theme
from selection_button import overlay_theme


def app_theme() -> dict[str, str]:
    """Цвета окон приложения. Попап перевода остаётся в overlay_theme()."""
    if get_ui_theme() == UI_THEME_DARK:
        return {
            "bg": "#121212",
            "surface": "#1c1c1c",
            "sidebar": "#161616",
            "sidebar_active": "#2c2c2c",
            "text": "#f2f2f2",
            "muted": "#b8b8b8",
            "button": "#2a2a2a",
            "button_hover": "#3d3d3d",
            "field_bg": "#242424",
            "border": "#4a4a4a",
            "select_bg": "#3d5a80",
            "select_fg": "#ffffff",
        }
    overlay = overlay_theme()
    return {
        "bg": overlay["bg"],
        "surface": "#f4f4f4",
        "sidebar": "#ececec",
        "sidebar_active": "#d8d8d8",
        "text": overlay["text"],
        "muted": "#555555",
        "button": overlay["button"],
        "button_hover": overlay["button_hover"],
        "field_bg": "#ffffff",
        "border": "#b0b0b0",
        "select_bg": "#cfe4ff",
        "select_fg": "#000000",
    }


def apply_ttk_theme(root: tk.Misc, theme: dict[str, str] | None = None) -> None:
    """Красит ttk-виджеты: иначе Combobox и таблица остаются системными."""
    colors = theme or app_theme()
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        ".",
        background=colors["bg"],
        foreground=colors["text"],
        fieldbackground=colors["field_bg"],
        troughcolor=colors["surface"],
        bordercolor=colors["border"],
        lightcolor=colors["border"],
        darkcolor=colors["border"],
    )
    style.configure("TFrame", background=colors["bg"])
    style.configure(
        "TLabel",
        background=colors["bg"],
        foreground=colors["text"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "TButton",
        background=colors["button"],
        foreground=colors["text"],
        bordercolor=colors["border"],
        focusthickness=0,
        padding=(12, 6),
    )
    style.map(
        "TButton",
        background=[("active", colors["button_hover"]), ("disabled", colors["surface"])],
        foreground=[("disabled", colors["muted"])],
    )
    style.configure(
        "TCombobox",
        fieldbackground=colors["field_bg"],
        background=colors["button"],
        foreground=colors["text"],
        arrowcolor=colors["text"],
        bordercolor=colors["border"],
        lightcolor=colors["border"],
        darkcolor=colors["border"],
        font=("Segoe UI", 10),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", colors["field_bg"])],
        foreground=[("readonly", colors["text"])],
        background=[("readonly", colors["button"]), ("active", colors["button_hover"])],
        arrowcolor=[("readonly", colors["text"])],
    )
    style.configure(
        "Treeview",
        background=colors["field_bg"],
        fieldbackground=colors["field_bg"],
        foreground=colors["text"],
        bordercolor=colors["border"],
        rowheight=26,
        font=("Segoe UI", 10),
    )
    style.configure(
        "Treeview.Heading",
        background=colors["surface"],
        foreground=colors["text"],
        bordercolor=colors["border"],
        relief=tk.FLAT,
    )
    style.map(
        "Treeview",
        background=[("selected", colors["select_bg"])],
        foreground=[("selected", colors["select_fg"])],
    )
    style.map(
        "Treeview.Heading",
        background=[("active", colors["button_hover"])],
    )
    style.configure(
        "TProgressbar",
        background=colors["select_bg"],
        troughcolor=colors["surface"],
        bordercolor=colors["border"],
        lightcolor=colors["select_bg"],
        darkcolor=colors["select_bg"],
    )
    style.configure(
        "Vertical.TScrollbar",
        background=colors["button"],
        troughcolor=colors["surface"],
        bordercolor=colors["border"],
        arrowcolor=colors["text"],
    )
    style.configure(
        "Horizontal.TScrollbar",
        background=colors["button"],
        troughcolor=colors["surface"],
        bordercolor=colors["border"],
        arrowcolor=colors["text"],
    )
    try:
        root.option_add("*TCombobox*Listbox.background", colors["field_bg"])
        root.option_add("*TCombobox*Listbox.foreground", colors["text"])
        root.option_add("*TCombobox*Listbox.selectBackground", colors["select_bg"])
        root.option_add("*TCombobox*Listbox.selectForeground", colors["select_fg"])
    except tk.TclError:
        pass


def style_button(button: tk.Button, theme: dict[str, str] | None = None) -> None:
    """Плоская кнопка в цветах темы вместо системной серой."""
    colors = theme or app_theme()
    button.configure(
        bg=colors["button"],
        fg=colors["text"],
        activebackground=colors["button_hover"],
        activeforeground=colors["text"],
        disabledforeground=colors["muted"],
        relief=tk.FLAT,
        bd=0,
        padx=14,
        pady=6,
        font=("Segoe UI", 10, "bold"),
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=colors["border"],
        highlightcolor=colors["border"],
    )


def style_sidebar_button(
    button: tk.Button,
    active: bool,
    theme: dict[str, str] | None = None,
) -> None:
    """Крупный пункт левого меню настроек."""
    colors = theme or app_theme()
    background = colors["sidebar_active"] if active else colors["sidebar"]
    button.configure(
        bg=background,
        fg=colors["text"],
        activebackground=colors["sidebar_active"],
        activeforeground=colors["text"],
        relief=tk.FLAT,
        bd=0,
        padx=18,
        pady=14,
        font=("Segoe UI", 12, "bold"),
        anchor=tk.W,
        cursor="hand2",
        highlightthickness=0,
    )


def color_widget_tree(widget: tk.Misc, theme: dict[str, str] | None = None) -> None:
    """Рекурсивно красит tk-виджеты. ttk не трогает — его красит apply_ttk_theme."""
    colors = theme or app_theme()
    widget_type = widget.winfo_class()
    if isinstance(widget, ttk.Widget):
        for child in widget.winfo_children():
            color_widget_tree(child, colors)
        return
    try:
        if widget_type in {"Frame", "Toplevel", "Labelframe"}:
            widget.configure(bg=colors["bg"])
            if widget_type == "Labelframe":
                widget.configure(
                    fg=colors["text"],
                    highlightbackground=colors["border"],
                    highlightcolor=colors["border"],
                )
        elif widget_type == "Label":
            widget.configure(bg=colors["bg"], fg=colors["text"], font=("Segoe UI", 10))
        elif widget_type in {"Checkbutton", "Radiobutton"}:
            widget.configure(
                bg=colors["bg"],
                fg=colors["text"],
                activebackground=colors["bg"],
                activeforeground=colors["text"],
                selectcolor=colors["field_bg"],
                highlightthickness=0,
            )
        elif widget_type == "Button":
            style_button(widget, colors)
        elif widget_type == "Entry":
            widget.configure(
                bg=colors["field_bg"],
                fg=colors["text"],
                insertbackground=colors["text"],
                disabledbackground=colors["surface"],
                disabledforeground=colors["muted"],
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground=colors["border"],
                highlightcolor=colors["border"],
            )
        elif widget_type == "Text":
            widget.configure(
                bg=colors["field_bg"],
                fg=colors["text"],
                insertbackground=colors["text"],
                selectbackground=colors["select_bg"],
                selectforeground=colors["select_fg"],
                highlightthickness=1,
                highlightbackground=colors["border"],
                highlightcolor=colors["border"],
                font=("Segoe UI", 11),
            )
        elif widget_type == "Listbox":
            widget.configure(
                bg=colors["field_bg"],
                fg=colors["text"],
                selectbackground=colors["select_bg"],
                selectforeground=colors["select_fg"],
            )
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        color_widget_tree(child, colors)


def apply_window_theme(window: tk.Misc, theme: dict[str, str] | None = None) -> None:
    """Красит окно целиком: фон, ttk, поля и заголовок Windows."""
    colors = theme or app_theme()
    try:
        window.configure(bg=colors["bg"])
    except tk.TclError:
        pass
    apply_ttk_theme(window, colors)
    color_widget_tree(window, colors)
    set_titlebar_theme(window, get_ui_theme() == UI_THEME_DARK)


def enable_windows_dpi() -> None:
    """Рисует окно в нативном DPI: иначе Windows растягивает битмап и шрифты плывут."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def apply_ui_fonts(root: tk.Misc) -> None:
    """Ставит Segoe UI вместо стандартных шрифтов Tk."""
    for name, size in (
        ("TkDefaultFont", 10),
        ("TkTextFont", 11),
        ("TkHeadingFont", 11),
        ("TkMenuFont", 10),
        ("TkCaptionFont", 10),
        ("TkSmallCaptionFont", 9),
        ("TkIconFont", 10),
        ("TkTooltipFont", 9),
        ("TkFixedFont", 10),
    ):
        try:
            tkfont.nametofont(name).configure(family="Segoe UI", size=size)
        except tk.TclError:
            pass


def set_titlebar_theme(window: tk.Misc, dark: bool) -> None:
    """Тёмный или светлый заголовок окна Windows 10/11."""
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()
        value = ctypes.c_int(1 if dark else 0)
        dwmapi = ctypes.windll.dwmapi
        for attribute in (20, 19):
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                attribute,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
    except (AttributeError, OSError, tk.TclError):
        pass
