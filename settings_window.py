import tkinter as tk
from tkinter import ttk

from autostart import is_autostart_enabled, set_autostart
from app_logging import get_logger, log_exception
from app_settings import (
    ENGINE_ARGOS,
    ENGINE_NLLB,
    ENGINE_LABELS,
    POPUP_MODIFIERS,
    RESULT_WINDOW_CLICK_TO_CLOSE,
    RESULT_WINDOW_SELECTABLE,
    engine_from_label,
    engine_label,
    get_double_ctrl_c_translation,
    get_engine_name,
    get_popup_modifier,
    get_result_window_mode,
    get_selection_popup_enabled,
    set_double_ctrl_c_translation,
    set_engine_name,
    set_popup_modifier,
    set_result_window_mode,
    set_selection_popup_enabled,
)
from selection_button import TRAY_ICON_PATH


class SettingsWindow:
    """Окно выбора движка перевода и поведения приложения."""

    def __init__(self, master: tk.Misc, on_settings_changed) -> None:
        self.on_settings_changed = on_settings_changed
        self.window = tk.Toplevel(master)
        self.window.title("Настройки")
        self._set_window_icon()
        self.window.geometry("520x640")
        self.window.minsize(500, 620)
        self.window.transient(master)
        self.window.grab_set()
        self._create_widgets()

    def _set_window_icon(self) -> None:
        """Устанавливает иконку трея в заголовок окна настроек."""
        self._window_icon = None
        try:
            self._window_icon = tk.PhotoImage(
                file=TRAY_ICON_PATH,
                master=self.window,
            )
            self.window.iconphoto(True, self._window_icon)
        except (tk.TclError, OSError):
            self._window_icon = None

    def _create_widgets(self) -> None:
        """Создаёт выбор движка и параметры приложения."""
        hint = tk.Label(
            self.window,
            text="Argos — пакеты CTranslate2 по парам языков. NLLB-200 — одна модель Meta на 200 языков, качество выше на редких языках.",
            wraplength=380,
            justify=tk.LEFT,
        )
        hint.pack(fill=tk.X, padx=12, pady=(12, 8))

        engine_frame = tk.Frame(self.window)
        engine_frame.pack(fill=tk.X, padx=12, pady=4)
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

        selection_frame = tk.LabelFrame(
            self.window,
            text="Перевод выделенного текста",
            padx=8,
            pady=6,
        )
        selection_frame.pack(fill=tk.X, padx=12, pady=(10, 4))

        modifier_frame = tk.Frame(selection_frame)
        modifier_frame.pack(fill=tk.X, pady=(0, 4))
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

        self.double_ctrl_c_var = tk.BooleanVar(
            value=get_double_ctrl_c_translation()
        )
        tk.Checkbutton(
            selection_frame,
            text="Переводить выделенный текст по Ctrl+C+C",
            variable=self.double_ctrl_c_var,
            anchor=tk.W,
        ).pack(fill=tk.X)
        self.only_ctrl_c_c_var = tk.BooleanVar(
            value=not get_selection_popup_enabled()
        )
        tk.Checkbutton(
            selection_frame,
            text="Только Ctrl+C+C (не показывать кнопку при выделении)",
            variable=self.only_ctrl_c_c_var,
            command=self._on_only_ctrl_c_c_changed,
            anchor=tk.W,
        ).pack(fill=tk.X)
        tk.Label(
            selection_frame,
            text=(
                "Ctrl+C+C: удерживайте Ctrl и дважды нажмите C. "
                "Перевод появится рядом с курсором. "
                "Режим «только Ctrl+C+C» не перехватывает обычные Ctrl+C/Ctrl+V."
            ),
            wraplength=440,
            justify=tk.LEFT,
            fg="#555555",
        ).pack(fill=tk.X, padx=(20, 0), pady=(2, 0))

        tk.Label(
            selection_frame,
            text="Окно результата:",
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(10, 2))
        self.result_window_mode_var = tk.StringVar(
            value=get_result_window_mode()
        )
        tk.Radiobutton(
            selection_frame,
            text="Закрывать нажатием по окну",
            variable=self.result_window_mode_var,
            value=RESULT_WINDOW_CLICK_TO_CLOSE,
            anchor=tk.W,
        ).pack(fill=tk.X, padx=(12, 0))
        tk.Radiobutton(
            selection_frame,
            text="Выделять часть текста; закрывать кнопкой «Закрыть»",
            variable=self.result_window_mode_var,
            value=RESULT_WINDOW_SELECTABLE,
            anchor=tk.W,
        ).pack(fill=tk.X, padx=(12, 0))

        launch_frame = tk.LabelFrame(
            self.window,
            text="Запуск",
            padx=8,
            pady=6,
        )
        launch_frame.pack(fill=tk.X, padx=12, pady=(10, 4))
        self.autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        tk.Checkbutton(
            launch_frame,
            text="Запускать вместе с Windows",
            variable=self.autostart_var,
            anchor=tk.W,
        ).pack(fill=tk.X)

        self.status_var = tk.StringVar(value="")
        tk.Label(self.window, textvariable=self.status_var, anchor=tk.W).pack(
            fill=tk.X, padx=12, pady=(8, 4)
        )

        buttons = tk.Frame(self.window)
        buttons.pack(fill=tk.X, padx=12, pady=(8, 12))
        tk.Button(buttons, text="Сохранить", command=self._on_save).pack(side=tk.LEFT)
        tk.Button(buttons, text="Отмена", command=self.window.destroy).pack(
            side=tk.RIGHT
        )
    def _on_only_ctrl_c_c_changed(self) -> None:
        """Режим «только Ctrl+C+C» всегда включает перевод по двойному C."""
        if self.only_ctrl_c_c_var.get():
            self.double_ctrl_c_var.set(True)

    def _on_engine_changed(self, _event=None) -> None:
        """Обновляет пояснение для выбранного движка."""
        engine = engine_from_label(self.engine_var.get())
        if engine == ENGINE_ARGOS:
            self.status_var.set("Argos использует свои пакеты .argosmodel.")
        elif engine == ENGINE_NLLB:
            self.status_var.set("NLLB ставится одним пакетом в «Языки» (~600 МБ).")
        else:
            self.status_var.set("")

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
            set_autostart(bool(self.autostart_var.get()))
            get_logger().info("Сохранены настройки, движок=%s", engine)
            self.on_settings_changed()
            self.window.destroy()
        except Exception as error:
            log_exception("Ошибка сохранения настроек", error)
            self.status_var.set(f"Ошибка сохранения: {error}")
