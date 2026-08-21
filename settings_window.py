import tkinter as tk
from tkinter import ttk

from app_settings import (
    ENGINE_FIREFOX,
    ENGINE_LABELS,
    engine_from_label,
    engine_label,
    get_engine_name,
    get_firefox_architecture,
    set_engine_name,
    set_firefox_architecture,
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
        self.window.geometry("420x240")
        self.window.minsize(400, 220)
        self.window.transient(master)
        self.window.grab_set()
        self._create_widgets()

    def _create_widgets(self) -> None:
        """Создаёт выбор движка и размера модели."""
        hint = tk.Label(
            self.window,
            text="Firefox — лёгкие модели Mozilla. Argos — прежние модели CTranslate2, обычно точнее на европейских языках.",
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
        else:
            self.size_combo.config(state="disabled")
            self.status_var.set("Argos использует свои пакеты .argosmodel.")

    def _on_save(self) -> None:
        """Сохраняет настройки и сообщает главному окну."""
        try:
            engine = engine_from_label(self.engine_var.get())
            set_engine_name(engine)
            if engine == ENGINE_FIREFOX:
                set_firefox_architecture(architecture_from_label(self.size_var.get()))
            self.on_settings_changed()
            self.window.destroy()
        except Exception as error:
            self.status_var.set(f"Ошибка сохранения: {error}")
