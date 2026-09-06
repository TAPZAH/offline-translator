import tkinter as tk
from tkinter import ttk

from app_version import APP_PUBLISHER, APP_VERSION_DISPLAY
from autostart import is_autostart_enabled, set_autostart
from app_logging import get_logger, log_exception
from app_settings import (
    ENGINE_ARGOS,
    ENGINE_MARIAN,
    ENGINE_NLLB,
    ENGINE_LABELS,
    POPUP_MODIFIERS,
    RESULT_WINDOW_CLICK_TO_CLOSE,
    RESULT_WINDOW_SELECTABLE,
    UI_THEME_DARK,
    UI_THEME_LIGHT,
    engine_from_label,
    engine_label,
    get_double_ctrl_c_translation,
    get_engine_name,
    get_popup_modifier,
    get_result_window_mode,
    get_selection_popup_enabled,
    get_ui_theme,
    set_double_ctrl_c_translation,
    set_engine_name,
    set_popup_modifier,
    set_result_window_mode,
    set_selection_popup_enabled,
    set_ui_theme,
)
from languages_window import LanguagesWindow
from selection_button import theme_icon_path
from ui_theme import apply_window_theme, app_theme, style_button, style_sidebar_button


PAGES = (
    ("languages", "Языки"),
    ("behavior", "Поведение"),
    ("themes", "Темы"),
    ("about", "О программе"),
)


class SettingsWindow:
    """Настройки с левым меню: языки, поведение, темы, о программе."""

    def __init__(
        self,
        master: tk.Misc,
        on_settings_changed,
        on_packages_changed=None,
        initial_page: str = "behavior",
    ) -> None:
        self.on_settings_changed = on_settings_changed
        self.on_packages_changed = on_packages_changed
        self._pages: dict[str, tk.Frame] = {}
        self._nav_buttons: dict[str, tk.Button] = {}
        self._current_page = initial_page if initial_page in dict(PAGES) else "behavior"
        self._languages_panel = None
        self._original_engine = get_engine_name()
        self._original_theme = get_ui_theme()
        self._saved = False

        self.window = tk.Toplevel(master)
        self.window.title("Настройки")
        self._set_window_icon()
        self.window.geometry("920x640")
        self.window.minsize(820, 560)
        self.window.transient(master)
        self.window.grab_set()
        self._create_widgets()
        self._show_page(self._current_page)
        self._apply_theme()

    def _set_window_icon(self) -> None:
        """Устанавливает ту же иконку, что у трея и окна перевода."""
        self._window_icon = None
        try:
            self._window_icon = tk.PhotoImage(
                file=theme_icon_path(),
                master=self.window,
            )
            self.window.iconphoto(True, self._window_icon)
        except (tk.TclError, OSError):
            self._window_icon = None

    def _apply_theme(self) -> None:
        """Красит окно настроек и пункты бокового меню."""
        theme = app_theme()
        apply_window_theme(self.window, theme)
        self.sidebar.configure(bg=theme["sidebar"])
        self.detail.configure(bg=theme["bg"])
        if hasattr(self, "behavior_summary_frame"):
            self.behavior_summary_frame.configure(
                bg=theme["surface"],
                fg=theme["text"],
                highlightbackground=theme["border"],
            )
            self.behavior_summary_label.configure(
                bg=theme["surface"],
                fg=theme["text"],
            )
        for page in self._pages.values():
            page.configure(bg=theme["bg"])
        for key, button in self._nav_buttons.items():
            style_sidebar_button(button, key == self._current_page, theme)
        for button in (self.save_button, self.cancel_button):
            style_button(button, theme)

    def _create_widgets(self) -> None:
        """Собирает боковое меню и страницы справа."""
        shell = tk.Frame(self.window)
        shell.pack(fill=tk.BOTH, expand=True)

        self.sidebar = tk.Frame(shell, width=200)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        self.detail = tk.Frame(shell)
        self.detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.status_var = tk.StringVar(value="")

        for key, title in PAGES:
            button = tk.Button(
                self.sidebar,
                text=title,
                command=lambda page=key: self._show_page(page),
            )
            button.pack(fill=tk.X, padx=8, pady=(8, 0))
            self._nav_buttons[key] = button

        self._pages["languages"] = self._build_languages_page(self.detail)
        self._pages["behavior"] = self._build_behavior_page(self.detail)
        self._pages["themes"] = self._build_themes_page(self.detail)
        self._pages["about"] = self._build_about_page(self.detail)

        footer = tk.Frame(self.window)
        footer.pack(fill=tk.X, padx=12, pady=(4, 12))
        tk.Label(footer, textvariable=self.status_var, anchor=tk.W).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        self.cancel_button = tk.Button(
            footer, text="Отмена", command=self._on_cancel
        )
        self.window.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.cancel_button.pack(side=tk.RIGHT)
        self.save_button = tk.Button(footer, text="Сохранить", command=self._on_save)
        self.save_button.pack(side=tk.RIGHT, padx=(0, 8))

    def _show_page(self, page_key: str) -> None:
        """Показывает выбранную страницу справа."""
        self._current_page = page_key
        for key, frame in self._pages.items():
            if key == page_key:
                frame.pack(fill=tk.BOTH, expand=True)
            else:
                frame.pack_forget()
        theme = app_theme()
        for key, button in self._nav_buttons.items():
            style_sidebar_button(button, key == page_key, theme)

    def _build_languages_page(self, parent: tk.Misc) -> tk.Frame:
        """Движок и установка языковых пакетов."""
        page = tk.Frame(parent)
        engine_frame = tk.Frame(page)
        engine_frame.pack(fill=tk.X, padx=12, pady=(12, 4))
        tk.Label(engine_frame, text="Движок:").pack(side=tk.LEFT)
        self.engine_var = tk.StringVar(value=engine_label(get_engine_name()))
        self.engine_combo = ttk.Combobox(
            engine_frame,
            textvariable=self.engine_var,
            values=list(ENGINE_LABELS.values()),
            state="readonly",
            width=28,
        )
        self.engine_combo.pack(side=tk.LEFT, padx=(8, 0))
        self.engine_combo.bind("<<ComboboxSelected>>", self._on_engine_changed)

        packages = tk.Frame(page)
        packages.pack(fill=tk.BOTH, expand=True)
        self._languages_panel = LanguagesWindow(
            self.window,
            on_packages_changed=self._notify_packages_changed,
            container=packages,
        )
        self._on_engine_changed()
        return page

    def _build_behavior_page(self, parent: tk.Misc) -> tk.Frame:
        """Перевод выделения и автозапуск."""
        page = tk.Frame(parent)
        heading = tk.Label(
            page,
            text="Перевод выделенного текста",
            font=("Segoe UI", 12, "bold"),
            anchor=tk.W,
        )
        heading.pack(fill=tk.X, padx=16, pady=(16, 8))

        self.behavior_summary_frame = tk.LabelFrame(
            page,
            text="Сейчас работает",
            padx=10,
            pady=8,
        )
        self.behavior_summary_frame.pack(fill=tk.X, padx=16, pady=(0, 12))
        self.behavior_summary_var = tk.StringVar(value="")
        self.behavior_summary_label = tk.Label(
            self.behavior_summary_frame,
            textvariable=self.behavior_summary_var,
            justify=tk.LEFT,
            anchor=tk.NW,
            wraplength=560,
        )
        self.behavior_summary_label.pack(fill=tk.X)

        modifier_frame = tk.Frame(page)
        modifier_frame.pack(fill=tk.X, padx=16, pady=(0, 4))
        tk.Label(modifier_frame, text="Клавиша удержания для кнопки:").pack(
            side=tk.LEFT
        )
        modifier_labels = {
            "none": "Не требуется",
            "ctrl": "Ctrl",
            "alt": "Alt",
            "shift": "Shift",
        }
        self._modifier_by_label = {label: code for code, label in modifier_labels.items()}
        current_modifier = get_popup_modifier()
        self.popup_modifier_var = tk.StringVar(
            value=modifier_labels.get(current_modifier, "Не требуется")
        )
        self.popup_modifier_combo = ttk.Combobox(
            modifier_frame,
            textvariable=self.popup_modifier_var,
            values=[modifier_labels[code] for code in POPUP_MODIFIERS],
            state="readonly",
            width=16,
        )
        self.popup_modifier_combo.pack(side=tk.LEFT, padx=(8, 0))
        self.popup_modifier_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._refresh_behavior_summary(),
        )

        self.double_ctrl_c_var = tk.BooleanVar(value=get_double_ctrl_c_translation())
        tk.Checkbutton(
            page,
            text="Переводить выделенный текст по Ctrl+C+C",
            variable=self.double_ctrl_c_var,
            command=self._refresh_behavior_summary,
            anchor=tk.W,
        ).pack(fill=tk.X, padx=16)
        self.only_ctrl_c_c_var = tk.BooleanVar(value=not get_selection_popup_enabled())
        tk.Checkbutton(
            page,
            text="Только Ctrl+C+C (не показывать кнопку при выделении)",
            variable=self.only_ctrl_c_c_var,
            command=self._on_only_ctrl_c_c_changed,
            anchor=tk.W,
        ).pack(fill=tk.X, padx=16)
        tk.Label(
            page,
            text=(
                "Ctrl+C+C: удерживайте Ctrl и дважды нажмите C. "
                "Перевод появится рядом с курсором. "
                "Режим «только Ctrl+C+C» не перехватывает обычные Ctrl+C/Ctrl+V."
            ),
            wraplength=560,
            justify=tk.LEFT,
        ).pack(fill=tk.X, padx=(36, 16), pady=(2, 8))

        tk.Label(page, text="Окно результата:", anchor=tk.W).pack(
            fill=tk.X, padx=16, pady=(8, 2)
        )
        self.result_window_mode_var = tk.StringVar(value=get_result_window_mode())
        tk.Radiobutton(
            page,
            text="Закрывать нажатием по окну",
            variable=self.result_window_mode_var,
            value=RESULT_WINDOW_CLICK_TO_CLOSE,
            command=self._refresh_behavior_summary,
            anchor=tk.W,
        ).pack(fill=tk.X, padx=32)
        tk.Radiobutton(
            page,
            text="Выделять часть текста; закрывать кнопкой «Закрыть»",
            variable=self.result_window_mode_var,
            value=RESULT_WINDOW_SELECTABLE,
            command=self._refresh_behavior_summary,
            anchor=tk.W,
        ).pack(fill=tk.X, padx=32)

        tk.Label(
            page,
            text="Запуск",
            font=("Segoe UI", 12, "bold"),
            anchor=tk.W,
        ).pack(fill=tk.X, padx=16, pady=(20, 8))
        self.autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        tk.Checkbutton(
            page,
            text="Запускать вместе с Windows",
            variable=self.autostart_var,
            command=self._refresh_behavior_summary,
            anchor=tk.W,
        ).pack(fill=tk.X, padx=16)
        self._refresh_behavior_summary()
        return page

    def _build_themes_page(self, parent: tk.Misc) -> tk.Frame:
        """Светлая и тёмная тема."""
        page = tk.Frame(parent)
        tk.Label(
            page,
            text="Тема оформления",
            font=("Segoe UI", 12, "bold"),
            anchor=tk.W,
        ).pack(fill=tk.X, padx=16, pady=(16, 8))
        self.ui_theme_var = tk.StringVar(value=get_ui_theme())
        tk.Radiobutton(
            page,
            text="Светлая",
            variable=self.ui_theme_var,
            value=UI_THEME_LIGHT,
            command=self._preview_theme,
            anchor=tk.W,
        ).pack(fill=tk.X, padx=32)
        tk.Radiobutton(
            page,
            text="Тёмная",
            variable=self.ui_theme_var,
            value=UI_THEME_DARK,
            command=self._preview_theme,
            anchor=tk.W,
        ).pack(fill=tk.X, padx=32)
        tk.Label(
            page,
            text="Тема применяется ко главному окну, настройкам и кнопке у курсора.",
            wraplength=560,
            justify=tk.LEFT,
        ).pack(fill=tk.X, padx=16, pady=(12, 0))
        return page

    def _build_about_page(self, parent: tk.Misc) -> tk.Frame:
        """Версия и автор."""
        page = tk.Frame(parent)
        tk.Label(
            page,
            text="О программе",
            font=("Segoe UI", 12, "bold"),
            anchor=tk.W,
        ).pack(fill=tk.X, padx=16, pady=(16, 8))
        tk.Label(
            page,
            text=f"Версия: {APP_VERSION_DISPLAY}",
            anchor=tk.W,
        ).pack(fill=tk.X, padx=16, pady=2)
        tk.Label(
            page,
            text=f"Автор: {APP_PUBLISHER}",
            anchor=tk.W,
        ).pack(fill=tk.X, padx=16, pady=2)
        return page

    def _preview_theme(self) -> None:
        """Сразу красит это окно, чтобы было видно системные цвета."""
        try:
            set_ui_theme(self.ui_theme_var.get())
            self._set_window_icon()
            self._apply_theme()
        except Exception as error:
            self.status_var.set(f"Ошибка темы: {error}")

    def _notify_packages_changed(self) -> None:
        """Сообщает главному окну, что пакеты изменились."""
        if self.on_packages_changed is None:
            return
        try:
            self.on_packages_changed()
        except Exception:
            pass

    def _on_only_ctrl_c_c_changed(self) -> None:
        """Режим «только Ctrl+C+C» всегда включает перевод по двойному C."""
        if self.only_ctrl_c_c_var.get():
            self.double_ctrl_c_var.set(True)
        self._refresh_behavior_summary()

    def _refresh_behavior_summary(self) -> None:
        """Обновляет рамку с активными способами перевода."""
        if not hasattr(self, "behavior_summary_var"):
            return
        only_hotkey = bool(self.only_ctrl_c_c_var.get())
        hotkey_on = bool(self.double_ctrl_c_var.get() or only_hotkey)
        modifier = self._modifier_by_label.get(self.popup_modifier_var.get(), "none")
        hold = {
            "none": "без клавиши удержания",
            "ctrl": "если удерживать Ctrl",
            "alt": "если удерживать Alt",
            "shift": "если удерживать Shift",
        }.get(modifier, "без клавиши удержания")
        lines: list[str] = []
        if only_hotkey:
            lines.append("• Кнопка у курсора после выделения выключена")
            lines.append("• Перевод запускается только по Ctrl+C+C")
        else:
            lines.append(f"• Кнопка у курсора после выделения: {hold}")
            if hotkey_on:
                lines.append("• Дополнительно работает перевод по Ctrl+C+C")
            else:
                lines.append("• Перевод по Ctrl+C+C выключен")
        if self.result_window_mode_var.get() == RESULT_WINDOW_SELECTABLE:
            lines.append("• Окно результата: можно выделить текст, закрыть кнопкой")
        else:
            lines.append("• Окно результата: закрывается нажатием по окну")
        if self.autostart_var.get():
            lines.append("• Запуск вместе с Windows включён")
        else:
            lines.append("• Запуск вместе с Windows выключен")
        self.behavior_summary_var.set("\n".join(lines))

    def _on_engine_changed(self, _event=None) -> None:
        """Обновляет пояснение и список пакетов для выбранного движка."""
        engine = engine_from_label(self.engine_var.get())
        if engine == ENGINE_ARGOS:
            self.status_var.set("Argos использует свои пакеты .argosmodel.")
        elif engine == ENGINE_NLLB:
            self.status_var.set("NLLB ставится одним пакетом (~600 МБ).")
        elif engine == ENGINE_MARIAN:
            self.status_var.set(
                "MarianMT — модели Helsinki-NLP OPUS-MT, пакет на каждую пару."
            )
        else:
            self.status_var.set("")
        if get_engine_name() != engine:
            set_engine_name(engine)
            if self._languages_panel is not None:
                self._languages_panel.refresh_engine_ui()
            self._notify_packages_changed()
            self._apply_theme()

    def _on_save(self) -> None:
        """Сохраняет настройки и сообщает главному окну."""
        try:
            engine = engine_from_label(self.engine_var.get())
            set_engine_name(engine)
            modifier = self._modifier_by_label.get(
                self.popup_modifier_var.get(),
                "none",
            )
            set_popup_modifier(modifier)
            set_selection_popup_enabled(not self.only_ctrl_c_c_var.get())
            set_double_ctrl_c_translation(self.double_ctrl_c_var.get())
            set_result_window_mode(self.result_window_mode_var.get())
            set_ui_theme(self.ui_theme_var.get())
            set_autostart(bool(self.autostart_var.get()))
            get_logger().info("Сохранены настройки, движок=%s", engine)
            self._saved = True
            self.on_settings_changed()
            self.window.destroy()
        except Exception as error:
            log_exception("Ошибка сохранения настроек", error)
            self.status_var.set(f"Ошибка сохранения: {error}")

    def _on_cancel(self) -> None:
        """Закрывает окно и откатывает движок и тему, если не сохранили."""
        try:
            if not self._saved:
                changed = False
                if get_engine_name() != self._original_engine:
                    set_engine_name(self._original_engine)
                    changed = True
                if get_ui_theme() != self._original_theme:
                    set_ui_theme(self._original_theme)
                    changed = True
                if changed:
                    self.on_settings_changed()
        except Exception as error:
            log_exception("Ошибка отмены настроек", error)
        self.window.destroy()
