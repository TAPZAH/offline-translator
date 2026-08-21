import sys

if sys.version_info[:2] != (3, 13):
    raise SystemExit(
        "Нужен Python 3.13. Запуск: py -3.13 main.py\n"
        f"Сейчас выбран: {sys.version}"
    )

import portable_env

portable_env.apply()

import ctypes
import os
import tempfile
import threading
import tkinter as tk
from tkinter import ttk
from ctypes import wintypes

import pystray
import pystray._util.win32 as win32_util
from PIL import Image

from autostart import is_autostart_enabled, set_autostart
from language_detect import detect_language_code, language_display_name
from firefox_engine import get_engine
from language_packages import (
    ARCHITECTURE_LABELS,
    architecture_from_label,
    architecture_label,
    get_installed_pairs,
    get_model_architecture,
    set_model_architecture,
)
from languages_window import LanguagesWindow
from selection_button import TRAY_ICON_PATH, SelectionPopup, choose_selection_direction


def patch_pystray_win32() -> None:
    """Исправляет ctypes-сигнатуры pystray для 64-bit Python 3.13.

    Без этого CreateWindowEx зависает, и иконка трея так и не появляется.
    """
    win32_util.CreateWindowEx.argtypes = (
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.INT,
        wintypes.INT,
        wintypes.INT,
        wintypes.INT,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    )
    win32_util.DefWindowProc.restype = ctypes.c_ssize_t


class TranslatorApp:
    """Главное окно оффлайн-переводчика."""

    def __init__(self, root: tk.Tk) -> None:
        # Скрытый корень держит приложение живым, когда окно спрятано в трей
        self.root = root
        self.root.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        self.window = tk.Toplevel(self.root)
        self.window.withdraw()
        self.translation = None
        self.engine = None
        self.installed_pairs: list[tuple[str, str, str, str]] = []
        self.is_translating = False
        self.tray_icon = None
        self.icon_path = None
        self._is_exiting = False
        self._tray_ready = False
        self._detect_job = None
        self._languages_dialog = None
        self.selection_popup = None

        self._setup_window()
        self._create_widgets()
        # Крестик обрабатывается на стороне Tcl: только скрыть окно
        self._apply_close_protocol()
        self.window.bind("<Map>", lambda _event: self._apply_close_protocol())
        self.window.bind("<Alt-F4>", self._on_alt_f4)
        # Запускаем загрузку модели и иконку трея после отрисовки окна
        self.window.after(100, self._start_model_loading)
        self.window.after(100, self._start_tray)
        self.selection_popup = SelectionPopup(
            self.root,
            self._translate_selection,
            self._installed_language_codes,
        )

    def _setup_window(self) -> None:
        """Настраивает размер и заголовок окна."""
        self.window.title("Оффлайн Переводчик")
        self.window.geometry("720x460")
        self.window.minsize(720, 460)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)
        self.window.rowconfigure(3, weight=1)

    def _apply_close_protocol(self) -> None:
        """Вешает на крестик Tcl-команду wm withdraw — без Python и без Win32."""
        if self._is_exiting:
            return
        try:
            widget_path = self.window._w
            # Чистый Tcl не даёт крестику уничтожить окно
            self.window.tk.call(
                "wm",
                "protocol",
                widget_path,
                "WM_DELETE_WINDOW",
                f"wm withdraw {widget_path}",
            )
        except tk.TclError as error:
            self._set_status(f"Ошибка протокола закрытия: {error}")

    def _create_widgets(self) -> None:
        """Создаёт выбор языков, поля ввода, кнопку и строку статуса."""
        toolbar = tk.Frame(self.window)
        toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))

        tk.Label(toolbar, text="С языка:").pack(side=tk.LEFT)
        self.source_var = tk.StringVar(value="Авто")
        self.source_combo = ttk.Combobox(
            toolbar,
            textvariable=self.source_var,
            state="readonly",
            width=16,
        )
        self.source_combo.pack(side=tk.LEFT, padx=(4, 10))
        self.source_combo.bind("<<ComboboxSelected>>", self._on_language_choice_changed)

        tk.Label(toolbar, text="На язык:").pack(side=tk.LEFT)
        self.target_var = tk.StringVar(value="Авто")
        self.target_combo = ttk.Combobox(
            toolbar,
            textvariable=self.target_var,
            state="readonly",
            width=16,
        )
        self.target_combo.pack(side=tk.LEFT, padx=(4, 10))
        self.target_combo.bind("<<ComboboxSelected>>", self._on_language_choice_changed)

        tk.Label(toolbar, text="Модель:").pack(side=tk.LEFT)
        self.architecture_var = tk.StringVar(
            value=architecture_label(get_model_architecture())
        )
        self.architecture_combo = ttk.Combobox(
            toolbar,
            textvariable=self.architecture_var,
            values=list(ARCHITECTURE_LABELS.values()),
            state="readonly",
            width=20,
        )
        self.architecture_combo.pack(side=tk.LEFT, padx=(4, 10))
        self.architecture_combo.bind(
            "<<ComboboxSelected>>", self._on_architecture_changed
        )

        self.languages_button = tk.Button(
            toolbar,
            text="Языки...",
            command=self._open_languages_window,
        )
        self.languages_button.pack(side=tk.RIGHT)

        self.autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        self.autostart_check = tk.Checkbutton(
            toolbar,
            text="Автозагрузка",
            variable=self.autostart_var,
            command=self._on_autostart_toggle,
        )
        self.autostart_check.pack(side=tk.RIGHT, padx=(0, 8))

        self.detected_var = tk.StringVar(value="Язык: —")
        tk.Label(toolbar, textvariable=self.detected_var, fg="#333333").pack(
            side=tk.RIGHT,
            padx=(0, 10),
        )

        self._code_by_label = {"Авто": "auto"}
        self._rebuild_language_combos()

        self.input_text = tk.Text(self.window, wrap=tk.WORD, height=8, undo=True)
        self.input_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 5))
        self.input_text.bind("<KeyRelease>", self._schedule_language_detect)
        self._bind_text_editing(self.input_text, allow_edit=True)

        self.translate_button = tk.Button(
            self.window,
            text="Перевести",
            command=self._on_translate_click,
            state=tk.DISABLED,
        )
        self.translate_button.grid(row=2, column=0, pady=5)

        self.output_text = tk.Text(self.window, wrap=tk.WORD, height=8, state=tk.DISABLED)
        self.output_text.grid(row=3, column=0, sticky="nsew", padx=10, pady=(5, 5))
        self._bind_text_editing(self.output_text, allow_edit=False)

        self.status_var = tk.StringVar(value="Загрузка модели...")
        self.status_label = tk.Label(
            self.window,
            textvariable=self.status_var,
            anchor=tk.W,
            relief=tk.SUNKEN,
            padx=8,
        )
        self.status_label.grid(row=4, column=0, sticky="ew")

    def _set_status(self, message: str) -> None:
        """Обновляет текст строки статуса."""
        self.status_var.set(message)

    def _set_output_text(self, text: str) -> None:
        """Записывает перевод в поле результата."""
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", text)
        self.output_text.config(state=tk.DISABLED)

    def _bind_text_editing(self, widget: tk.Text, allow_edit: bool) -> None:
        """Вешает Ctrl+C/V/X/A по коду клавиши — работает и на русской раскладке."""
        widget.bind(
            "<Control-KeyPress>",
            lambda event, edit=allow_edit: self._on_control_key(event, widget, edit),
        )
        widget.bind(
            "<Button-3>",
            lambda event, edit=allow_edit: self._show_text_menu(event, widget, edit),
        )
        if allow_edit:
            widget.bind("<Shift-Insert>", lambda _event: self._paste_text(widget))

    def _on_control_key(self, event, widget: tk.Text, allow_edit: bool):
        """Обрабатывает горячие клавиши буфера обмена по Windows-коду клавиши."""
        try:
            keycode = event.keycode
            if keycode == 65:
                self._select_all_text(widget)
                return "break"
            if keycode == 67:
                self._copy_text(widget)
                return "break"
            if keycode == 86 and allow_edit:
                self._paste_text(widget)
                return "break"
            if keycode == 88 and allow_edit:
                self._cut_text(widget)
                return "break"
        except Exception as error:
            self._set_status(f"Ошибка буфера обмена: {error}")
        return None

    def _select_all_text(self, widget: tk.Text) -> None:
        """Выделяет весь текст в поле."""
        was_disabled = str(widget.cget("state")) == tk.DISABLED
        try:
            if was_disabled:
                widget.config(state=tk.NORMAL)
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set(tk.INSERT, "end-1c")
            widget.see(tk.INSERT)
        finally:
            if was_disabled:
                widget.config(state=tk.DISABLED)

    def _copy_text(self, widget: tk.Text) -> None:
        """Копирует выделенный текст или всё поле результата."""
        try:
            text = widget.get("sel.first", "sel.last")
        except tk.TclError:
            text = widget.get("1.0", "end-1c") if widget is self.output_text else ""
        if not text:
            return
        try:
            self.window.clipboard_clear()
            self.window.clipboard_append(text)
        except tk.TclError:
            pass
        try:
            import pyperclip

            pyperclip.copy(text)
        except Exception:
            pass

    def _paste_text(self, widget: tk.Text) -> str:
        """Вставляет текст из буфера обмена в поле ввода."""
        clipboard_text = ""
        try:
            clipboard_text = self.window.clipboard_get()
        except tk.TclError:
            try:
                import pyperclip

                clipboard_text = pyperclip.paste() or ""
            except Exception:
                clipboard_text = ""
        if not clipboard_text:
            self._set_status("Буфер обмена пуст")
            return "break"
        try:
            try:
                widget.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
            widget.insert(tk.INSERT, clipboard_text)
            self._schedule_language_detect()
        except Exception as error:
            self._set_status(f"Не удалось вставить текст: {error}")
        return "break"

    def _cut_text(self, widget: tk.Text) -> None:
        """Вырезает выделенный текст в буфер."""
        try:
            self._copy_text(widget)
            widget.delete("sel.first", "sel.last")
            self._schedule_language_detect()
        except tk.TclError:
            pass

    def _show_text_menu(self, event, widget: tk.Text, allow_edit: bool) -> str:
        """Показывает контекстное меню копирования и вставки."""
        try:
            menu = tk.Menu(widget, tearoff=0)
            if allow_edit:
                menu.add_command(label="Вставить", command=lambda: self._paste_text(widget))
                menu.add_command(label="Вырезать", command=lambda: self._cut_text(widget))
            menu.add_command(label="Копировать", command=lambda: self._copy_text(widget))
            menu.add_command(label="Выделить всё", command=lambda: self._select_all_text(widget))
            menu.tk_popup(event.x_root, event.y_root)
        except Exception as error:
            self._set_status(f"Ошибка меню: {error}")
        return "break"

    def _rebuild_language_combos(self) -> None:
        """Обновляет списки языков по установленным пакетам."""
        labels = ["Авто"]
        self._code_by_label = {"Авто": "auto"}
        unique_codes: dict[str, str] = {}
        for from_code, to_code, from_name, to_name in self.installed_pairs:
            unique_codes.setdefault(from_code, from_name)
            unique_codes.setdefault(to_code, to_name)
        for code, fallback_name in sorted(
            unique_codes.items(),
            key=lambda item: language_display_name(item[0], item[1]),
        ):
            label = language_display_name(code, fallback_name)
            labels.append(label)
            self._code_by_label[label] = code

        current_source = self.source_var.get()
        current_target = self.target_var.get()
        self.source_combo["values"] = labels
        self.target_combo["values"] = labels
        if current_source not in labels:
            self.source_var.set("Авто")
        if current_target not in labels:
            # По умолчанию переводим на русский, если пакет есть
            russian_label = language_display_name("ru", "Русский")
            self.target_var.set(russian_label if russian_label in labels else "Авто")

    def _combo_code(self, combo_value: str) -> str:
        """Преобразует подпись комбобокса в код языка."""
        return self._code_by_label.get(combo_value, "auto")

    def _schedule_language_detect(self, event=None) -> None:
        """Откладывает определение языка, чтобы не дергать его на каждую букву."""
        try:
            if self._detect_job is not None:
                self.window.after_cancel(self._detect_job)
            self._detect_job = self.window.after(400, self._update_detected_label)
        except tk.TclError:
            pass

    def _on_language_choice_changed(self, event=None) -> None:
        """Обновляет подпись языка после ручного выбора."""
        self._update_detected_label()

    def _on_architecture_changed(self, _event=None) -> None:
        """Переключает tiny/base и сбрасывает кэш переводчика."""
        try:
            architecture = architecture_from_label(self.architecture_var.get())
            set_model_architecture(architecture)
            if self.engine is not None:
                self.engine.invalidate()
            self._set_status(
                f"Выбрана модель {architecture}. Если её нет, будет использована другая."
            )
        except Exception as error:
            self._set_status(f"Ошибка выбора модели: {error}")

    def _sync_architecture_combo(self) -> None:
        """Синхронизирует комбобокс с сохранённым размером модели."""
        try:
            self.architecture_var.set(architecture_label(get_model_architecture()))
        except Exception:
            pass

    def _update_detected_label(self) -> None:
        """Показывает определённый или выбранный язык ввода."""
        try:
            source_code = self._combo_code(self.source_var.get())
            if source_code != "auto":
                self.detected_var.set(f"Язык: {language_display_name(source_code)}")
                return
            text = self.input_text.get("1.0", "end-1c")
            detected_code = detect_language_code(text)
            if detected_code:
                self.detected_var.set(
                    f"Язык: {language_display_name(detected_code, detected_code)}"
                )
            else:
                self.detected_var.set("Язык: —")
        except Exception:
            self.detected_var.set("Язык: —")

    def _installed_language_codes(self) -> set[str]:
        """Коды языков из установленных пакетов."""
        codes: set[str] = set()
        for from_code, to_code, _from_name, _to_name in self.installed_pairs:
            codes.add(from_code)
            codes.add(to_code)
        return codes

    def _pick_auto_target(self, source_code: str) -> str | None:
        """Выбирает язык назначения: русский, иначе английский, иначе любой другой."""
        installed_codes = self._installed_language_codes()
        for preferred_code in ("ru", "en"):
            if preferred_code != source_code and preferred_code in installed_codes:
                return preferred_code
        for language_code in installed_codes:
            if language_code != source_code:
                return language_code
        return None

    def _open_languages_window(self) -> None:
        """Открывает окно установки языковых пакетов."""
        try:
            if self._languages_dialog is not None and self._languages_dialog.window.winfo_exists():
                self._languages_dialog.window.lift()
                self._languages_dialog.window.focus_force()
                return
            self._languages_dialog = LanguagesWindow(
                self.window,
                on_packages_changed=self._reload_languages_from_ui,
            )
        except Exception as error:
            self._set_status(f"Не удалось открыть окно языков: {error}")

    def _reload_languages_from_ui(self) -> None:
        """Перечитывает пакеты после установки из окна языков."""
        try:
            self.installed_pairs = get_installed_pairs()
            if self.engine is not None:
                self.engine.invalidate()
            self._sync_architecture_combo()
            self._rebuild_language_combos()
            if self.installed_pairs:
                self.translate_button.config(state=tk.NORMAL)
                self._set_status("Языковые пакеты обновлены")
            else:
                self.translate_button.config(state=tk.DISABLED)
                self._set_status("Нет установленных пакетов. Откройте «Языки».")
        except Exception as error:
            self._set_status(f"Ошибка обновления языков: {error}")

    def _start_model_loading(self) -> None:
        """Запускает загрузку установленных языковых пакетов в фоне."""
        self._set_status("Загрузка модели...")
        self.translate_button.config(state=tk.DISABLED)
        loader = threading.Thread(target=self._load_model, daemon=True)
        loader.start()

    def _load_model(self) -> None:
        """Читает установленные пакеты Firefox и прогревает переводчик."""
        try:
            self.engine = get_engine()
            pairs = get_installed_pairs()
            if not pairs:
                self.root.after(
                    0,
                    lambda: self._on_model_error(
                        "Нет установленных пакетов. Откройте «Языки»."
                    ),
                )
                return

            # Прогрев en→ru, если пакет есть — первая кнопка не будет тормозить
            has_en_ru = any(
                from_code == "en" and to_code == "ru" for from_code, to_code, *_ in pairs
            )
            if has_en_ru:
                self.engine.warmup("en", "ru")
                self.engine.translate("Hello", "en", "ru")

            self.root.after(0, lambda: self._on_languages_loaded(pairs))
        except Exception as error:
            self.root.after(0, lambda message=str(error): self._on_model_error(message))

    def _on_languages_loaded(self, pairs: list[tuple[str, str, str, str]]) -> None:
        """Включает перевод после загрузки списка пакетов."""
        self.installed_pairs = pairs
        self._rebuild_language_combos()
        self.translate_button.config(state=tk.NORMAL)
        if self._tray_ready:
            self._set_status("Модель загружена. Иконка в трее.")
        else:
            self._set_status("Модель загружена")

    def _on_model_loaded(self) -> None:
        """Совместимость со старым статусом трея."""
        if self.installed_pairs:
            self._on_languages_loaded(self.installed_pairs)

    def _on_model_error(self, message: str) -> None:
        """Показывает ошибку загрузки модели в строке статуса."""
        self._set_status(f"Ошибка загрузки модели: {message}")
        if self.installed_pairs:
            self.translate_button.config(state=tk.NORMAL)
        else:
            self.translate_button.config(state=tk.DISABLED)

    def _on_translate_click(self) -> None:
        """Берёт текст, определяет язык и запускает перевод."""
        try:
            source_text = self.input_text.get("1.0", "end-1c").strip()
            if not source_text:
                self._set_status("Введите текст для перевода")
                return
            if self.engine is None:
                self._set_status("Модель ещё не загружена")
                return
            if self.is_translating:
                return

            direction = self._resolve_direction(source_text)
            if direction is None:
                return
            source_code, target_code = direction

            self.is_translating = True
            self.translate_button.config(state=tk.DISABLED)
            source_name = language_display_name(source_code, source_code)
            target_name = language_display_name(target_code, target_code)
            self._set_status(f"Перевожу {source_name} → {target_name}...")
            worker = threading.Thread(
                target=self._translate_text,
                args=(source_text, source_code, target_code),
                daemon=True,
            )
            worker.start()
        except Exception as error:
            self.is_translating = False
            self.translate_button.config(state=tk.NORMAL)
            self._set_status(f"Ошибка: {error}")

    def _resolve_direction(self, text: str) -> tuple[str, str] | None:
        """Определяет пару языков для перевода."""
        source_choice = self._combo_code(self.source_var.get())
        target_choice = self._combo_code(self.target_var.get())

        if source_choice == "auto":
            source_code = detect_language_code(text)
            if source_code is None:
                self._set_status("Не удалось определить язык. Выберите его вручную.")
                return None
        else:
            source_code = source_choice

        if target_choice == "auto":
            target_code = self._pick_auto_target(source_code)
            if target_code is None:
                self._set_status("Нет языка назначения. Установите пакеты в «Языки».")
                return None
        else:
            target_code = target_choice

        if source_code == target_code:
            self._set_status("Язык ввода совпадает с языком перевода")
            return None

        if not self._has_translation_path(source_code, target_code):
            self._set_status(
                f"Нет модели {language_display_name(source_code)} → "
                f"{language_display_name(target_code)}. Откройте «Языки»."
            )
            return None
        return source_code, target_code

    def _has_translation_path(self, source_code: str, target_code: str) -> bool:
        """Проверяет, есть ли прямая модель или связка через английский."""
        try:
            if self.engine is None:
                return False
            return self.engine.has_translation_path(source_code, target_code)
        except Exception:
            return False

    def _translate_selection(self, text: str) -> tuple[str, str, str]:
        """Переводит выделенный текст: ru→en или другой язык→ru."""
        if self.engine is None:
            raise RuntimeError("Модель ещё не загружена")
        source_code, target_code = choose_selection_direction(
            text,
            self._installed_language_codes(),
        )
        if not self._has_translation_path(source_code, target_code):
            raise RuntimeError(
                f"Нет модели {language_display_name(source_code)} → "
                f"{language_display_name(target_code)}. Откройте «Языки»."
            )
        translated_text = self.engine.translate(
            text,
            source_code,
            target_code,
        )
        if not translated_text:
            raise RuntimeError("Пустой ответ переводчика")
        return translated_text, source_code, target_code

    def _translate_text(
        self,
        source_text: str,
        source_code: str,
        target_code: str,
    ) -> None:
        """Выполняет перевод в фоне и передаёт результат в интерфейс."""
        try:
            translated_text = self.engine.translate(
                source_text,
                source_code,
                target_code,
            )
            self.root.after(
                0,
                lambda: self._on_translation_done(
                    translated_text,
                    source_code,
                    target_code,
                ),
            )
        except Exception as error:
            self.root.after(
                0,
                lambda message=str(error): self._on_translation_error(message),
            )

    def _on_translation_done(
        self,
        translated_text: str,
        source_code: str,
        target_code: str,
    ) -> None:
        """Показывает готовый перевод и восстанавливает кнопку."""
        self._set_output_text(translated_text)
        source_name = language_display_name(source_code, source_code)
        target_name = language_display_name(target_code, target_code)
        self._set_status(f"{source_name} → {target_name}")
        self.is_translating = False
        self.translate_button.config(state=tk.NORMAL)

    def _on_translation_error(self, message: str) -> None:
        """Показывает ошибку перевода, не закрывая окно."""
        self._set_status(f"Ошибка перевода: {message}")
        self.is_translating = False
        self.translate_button.config(state=tk.NORMAL)

    def _create_tray_image_file(self) -> str:
        """Готовит иконку трея из файла icon-tray.png."""
        image = Image.open(TRAY_ICON_PATH).convert("RGBA")
        image = image.resize((64, 64), Image.Resampling.LANCZOS)

        file_handle, file_path = tempfile.mkstemp(suffix=".ico")
        os.close(file_handle)
        image.save(file_path, format="ICO", sizes=[(16, 16), (32, 32), (64, 64)])
        return file_path

    def _start_tray(self) -> None:
        """Запускает иконку системного трея в отдельном потоке."""
        # Icon и run() должны создаваться в одном потоке
        tray_thread = threading.Thread(target=self._run_tray, daemon=True)
        tray_thread.start()

    def _on_tray_setup(self, icon) -> None:
        """Показывает иконку после готовности цикла pystray."""
        try:
            icon.visible = True
            icon.notify("Программа работает в трее", "Оффлайн Переводчик")
        except Exception:
            icon.visible = True
        self.root.after(0, self._on_tray_ready)

    def _on_tray_ready(self) -> None:
        """Сообщает в статусе, что трей запущен."""
        self._tray_ready = True
        if self.installed_pairs:
            self._set_status("Модель загружена. Иконка в трее.")
        else:
            self._set_status("Загрузка модели... Иконка в трее.")

    def _run_tray(self) -> None:
        """Создаёт меню трея и запускает цикл pystray."""
        try:
            self.icon_path = self._create_tray_image_file()
            with Image.open(self.icon_path) as opened:
                icon_image = opened.convert("RGBA")
            icon_image.load()
            menu = pystray.Menu(
                pystray.MenuItem(
                    "Открыть",
                    self._on_tray_open,
                    default=True,
                ),
                pystray.MenuItem(
                    "Запускать вместе с Windows",
                    self._on_tray_autostart,
                    checked=lambda _item: is_autostart_enabled(),
                ),
                pystray.MenuItem("Выход", self._on_tray_exit),
            )
            # Создаём Icon в этом же потоке, где вызовем run()
            self.tray_icon = pystray.Icon(
                "offline_translator",
                icon_image,
                "Оффлайн Переводчик",
                menu,
            )
            # run() блокирует поток, пока не будет вызван stop()
            self.tray_icon.run(setup=self._on_tray_setup)
        except Exception as error:
            self.root.after(
                0,
                lambda message=str(error): self._set_status(
                    f"Ошибка трея: {message}"
                ),
            )

    def _on_alt_f4(self, event) -> str:
        """Alt+F4 тоже скрывает окно в трей."""
        self._hide_to_tray()
        return "break"

    def _hide_to_tray(self) -> None:
        """Скрывает окно, программа остаётся в трее."""
        if self._is_exiting:
            return
        try:
            self.window.withdraw()
        except tk.TclError as error:
            self._set_status(f"Ошибка скрытия окна: {error}")

    def _restore_window(self) -> None:
        """Показывает главное окно поверх других."""
        try:
            if not self.window.winfo_exists():
                return
            self.window.deiconify()
            self.window.state("normal")
            self.window.lift()
            self.window.attributes("-topmost", True)
            self.window.after(
                0,
                lambda: self.window.attributes("-topmost", False),
            )
            self.window.focus_force()
        except tk.TclError:
            pass

    def _on_autostart_toggle(self) -> None:
        """Включает или выключает автозагрузку из главного окна."""
        enabled = bool(self.autostart_var.get())
        self._apply_autostart(enabled)

    def _on_tray_autostart(self, icon, item) -> None:
        """Переключает автозагрузку из меню трея."""
        enabled = not is_autostart_enabled()
        self.root.after(0, lambda: self._apply_autostart(enabled))

    def _apply_autostart(self, enabled: bool) -> None:
        """Сохраняет настройку автозагрузки и обновляет интерфейс."""
        try:
            set_autostart(enabled)
            self.autostart_var.set(enabled)
            if enabled:
                self._set_status("Программа будет запускаться вместе с Windows")
            else:
                self._set_status("Программа убрана из автозагрузки")
        except Exception as error:
            self.autostart_var.set(is_autostart_enabled())
            self._set_status(f"Ошибка автозагрузки: {error}")

    def _on_tray_open(self, icon, item) -> None:
        """Пункт меню и двойной клик по иконке — открыть окно."""
        self.root.after(0, self._restore_window)

    def _on_tray_exit(self, icon, item) -> None:
        """Полностью закрывает иконку трея и главное окно."""
        try:
            icon.stop()
        except Exception:
            pass
        self.root.after(0, self._shutdown)

    def _shutdown(self) -> None:
        """Корректно уничтожает окно и удаляет временную иконку."""
        self._is_exiting = True
        try:
            if self.selection_popup is not None:
                self.selection_popup.stop()
        except Exception:
            pass
        try:
            if self.tray_icon is not None:
                self.tray_icon.stop()
        except Exception:
            pass
        try:
            if self.icon_path and os.path.exists(self.icon_path):
                os.remove(self.icon_path)
        except OSError:
            pass
        try:
            self.window.destroy()
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def main() -> None:
    """Запускает графический интерфейс переводчика."""
    try:
        patch_pystray_win32()
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "gelezyaka.OfflineTranslator"
        )
        root = tk.Tk()
        root.withdraw()
        # Ссылка на приложение нужна, чтобы обработчики окна не уничтожил GC
        app = TranslatorApp(root)
        root.mainloop()
        _ = app
    except tk.TclError as error:
        print(f"Ошибка интерфейса: {error}")
    except Exception as error:
        print(f"Неожиданная ошибка: {error}")


if __name__ == "__main__":
    main()
