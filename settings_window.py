import tkinter as tk
from tkinter import ttk

from app_settings import (
    ENGINE_ARGOS,
    ENGINE_FIREFOX,
    ENGINE_NLLB,
    ENGINE_LABELS,
    engine_from_label,
    engine_label,
    get_double_ctrl_c_translation,
    get_engine_name,
    get_firefox_architecture,
    get_popup_requires_ctrl,
    set_double_ctrl_c_translation,
    set_engine_name,
    set_firefox_architecture,
    set_popup_requires_ctrl,
)
from language_packages import (
    ARCHITECTURE_LABELS,
    architecture_from_label,
    architecture_label,
)


class SettingsWindow:
    """Окно выбора движка перевода и размера Firefox."""

    def __init__(self, master: tk.Misc, on_settings_changed) -> None:
        self.on_settings_changed = on_settings_changed
        self.window = tk.Toplevel(master)
        self.window.title("Настройки")
        self.window.geometry("500x420")
        self.window.minsize(480, 400)
        self.window.transient(master)
        self.window.grab_set()
        self._create_widgets()

    def _create_widgets(self) -> None:
        """Создаёт выбор движка и размера модели."""
        hint = tk.Label(
            self.window,
            text="Firefox — лёгкие модели Mozilla. Argos — пакеты CTranslate2 по парам языков. NLLB-200 — одна модель Meta на 200 языков, качество выше на редких языках.",
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

        size_frame = tk.Frame(self.window)
        size_frame.pack(fill=tk.X, padx=12, pady=4)
        tk.Label(size_frame, text="Firefox:").pack(side=tk.LEFT)
        self.size_var = tk.StringVar(
            value=architecture_label(get_firefox_architecture())
        )
        self.size_combo = ttk.Combobox(
            size_frame,
            textvariable=self.size_var,
            values=list(ARCHITECTURE_LABELS.values()),
            state="readonly",
            width=28,
        )
        self.size_combo.pack(side=tk.LEFT, padx=(8, 0))

        selection_frame = tk.LabelFrame(
            self.window,
            text="Перевод выделенного текста",
            padx=8,
            pady=6,
        )
        selection_frame.pack(fill=tk.X, padx=12, pady=(10, 4))

        self.popup_requires_ctrl_var = tk.BooleanVar(
            value=get_popup_requires_ctrl()
        )
        tk.Checkbutton(
            selection_frame,
            text="Показывать кнопку только при удержании Ctrl",
            variable=self.popup_requires_ctrl_var,
            anchor=tk.W,
        ).pack(fill=tk.X)

        self.double_ctrl_c_var = tk.BooleanVar(
            value=get_double_ctrl_c_translation()
        )
        tk.Checkbutton(
            selection_frame,
            text="Переводить выделенный текст по Ctrl+C+C",
            variable=self.double_ctrl_c_var,
            anchor=tk.W,
        ).pack(fill=tk.X)
        tk.Label(
            selection_frame,
            text=(
                "Ctrl+C+C: удерживайте Ctrl и дважды нажмите C. "
                "Перевод появится рядом с курсором."
            ),
            wraplength=440,
            justify=tk.LEFT,
            fg="#555555",
        ).pack(fill=tk.X, padx=(20, 0), pady=(2, 0))

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
        self._refresh_size_state()

    def _on_engine_changed(self, _event=None) -> None:
        """Включает размер Firefox только для движка Mozilla."""
        self._refresh_size_state()

    def _refresh_size_state(self) -> None:
        """Размер tiny/base нужен только Firefox."""
        engine = engine_from_label(self.engine_var.get())
        if engine == ENGINE_FIREFOX:
            self.size_combo.config(state="readonly")
            self.status_var.set("Для китайского и части языков нужен размер base.")
        elif engine == ENGINE_ARGOS:
            self.size_combo.config(state="disabled")
            self.status_var.set("Argos использует свои пакеты .argosmodel.")
        elif engine == ENGINE_NLLB:
            self.size_combo.config(state="disabled")
            self.status_var.set("NLLB ставится одним пакетом в «Языки» (~600 МБ).")
        else:
            self.size_combo.config(state="disabled")
            self.status_var.set("")

    def _on_save(self) -> None:
        """Сохраняет настройки и сообщает главному окну."""
        try:
            engine = engine_from_label(self.engine_var.get())
            set_engine_name(engine)
            if engine == ENGINE_FIREFOX:
                set_firefox_architecture(architecture_from_label(self.size_var.get()))
            set_popup_requires_ctrl(self.popup_requires_ctrl_var.get())
            set_double_ctrl_c_translation(self.double_ctrl_c_var.get())
            self.on_settings_changed()
            self.window.destroy()
        except Exception as error:
            self.status_var.set(f"Ошибка сохранения: {error}")
