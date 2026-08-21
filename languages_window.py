import threading
import tkinter as tk
from tkinter import ttk

from app_settings import ENGINE_FIREFOX, get_engine_name
from language_detect import language_display_name
from language_packages import (
    ARCHITECTURE_LABELS,
    architecture_from_label,
    architecture_label,
    get_model_architecture,
    set_model_architecture,
)
from packages import (
    download_and_install,
    get_available_pairs,
    get_installed_architectures,
    get_installed_pairs,
    is_package_installed,
    update_remote_index,
)


class LanguagesWindow:
    """Окно установки дополнительных языковых пакетов."""

    def __init__(self, master: tk.Misc, on_packages_changed) -> None:
        self.on_packages_changed = on_packages_changed
        self.is_busy = False
        self.available_packages = []

        self.window = tk.Toplevel(master)
        self.window.title("Языковые пакеты")
        self.window.geometry("560x480")
        self.window.minsize(520, 400)
        self.window.transient(master)

        self._create_widgets()
        self._load_installed_only()
        threading.Thread(target=self._load_remote_index, daemon=True).start()

    def _create_widgets(self) -> None:
        """Создаёт список пакетов, поиск и кнопки."""
        engine = get_engine_name()
        if engine == ENGINE_FIREFOX:
            hint_text = (
                "Нет прямой пары — программа переведёт через английский. "
                "Для китайского нужен размер base."
            )
        else:
            hint_text = (
                "Пакеты Argos Translate. Нет прямой пары — перевод пойдёт через английский."
            )
        hint = tk.Label(
            self.window,
            text=hint_text,
            wraplength=540,
            justify=tk.LEFT,
        )
        hint.pack(fill=tk.X, padx=10, pady=(10, 4))

        self.size_frame = tk.Frame(self.window)
        tk.Label(self.size_frame, text="Модель:").pack(side=tk.LEFT)
        self.size_var = tk.StringVar(value=architecture_label(get_model_architecture()))
        self.size_combo = ttk.Combobox(
            self.size_frame,
            textvariable=self.size_var,
            values=list(ARCHITECTURE_LABELS.values()),
            state="readonly",
            width=22,
        )
        self.size_combo.pack(side=tk.LEFT, padx=(6, 0))
        self.size_combo.bind("<<ComboboxSelected>>", self._on_architecture_changed)
        if engine == ENGINE_FIREFOX:
            self.size_frame.pack(fill=tk.X, padx=10, pady=4)

        search_frame = tk.Frame(self.window)
        search_frame.pack(fill=tk.X, padx=10, pady=4)
        tk.Label(search_frame, text="Поиск:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_args: self._fill_tree())
        search_entry = tk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        list_frame = tk.Frame(self.window)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        columns = ("from_lang", "to_lang", "status")
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("from_lang", text="С языка")
        self.tree.heading("to_lang", text="На язык")
        self.tree.heading("status", text="Статус")
        self.tree.column("from_lang", width=180)
        self.tree.column("to_lang", width=180)
        self.tree.column("status", width=140)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        button_frame = tk.Frame(self.window)
        button_frame.pack(fill=tk.X, padx=10, pady=4)
        self.install_button = tk.Button(
            button_frame,
            text="Установить выбранный",
            command=self._on_install_click,
        )
        self.install_button.pack(side=tk.LEFT)
        tk.Button(button_frame, text="Закрыть", command=self.window.destroy).pack(
            side=tk.RIGHT
        )

        self.progress = ttk.Progressbar(self.window, mode="determinate")
        self.progress.pack(fill=tk.X, padx=10, pady=(4, 2))
        self.status_var = tk.StringVar(value="Загружаю список пакетов...")
        tk.Label(self.window, textvariable=self.status_var, anchor=tk.W).pack(
            fill=tk.X, padx=10, pady=(0, 8)
        )

    def _selected_architecture(self) -> str | None:
        """Размер модели Firefox или None для Argos."""
        if get_engine_name() != ENGINE_FIREFOX:
            return None
        return architecture_from_label(self.size_var.get())

    def _on_architecture_changed(self, _event=None) -> None:
        """Переключает tiny/base и обновляет список пакетов."""
        try:
            architecture = self._selected_architecture()
            set_model_architecture(architecture)
            self.available_packages = sorted(
                get_available_pairs(architecture),
                key=self._package_sort_key,
            )
            self._fill_tree()
            self.status_var.set(
                f"Модель {architecture}: доступно пакетов {len(self.available_packages)}"
            )
            try:
                self.on_packages_changed()
            except Exception:
                pass
        except Exception as error:
            self.status_var.set(f"Ошибка выбора модели: {error}")

    def _package_sort_key(self, language_package) -> tuple:
        """Сортирует: установленные, затем пары с ru/en, затем по имени."""
        from_code = language_package.from_code
        to_code = language_package.to_code
        architecture = getattr(language_package, "architecture", None)
        installed = (
            0 if is_package_installed(from_code, to_code, architecture) else 1
        )
        popular = 0 if {from_code, to_code} & {"ru", "en"} else 1
        return (installed, popular, from_code, to_code)

    def _load_installed_only(self) -> None:
        """Показывает уже установленные пакеты, пока качается индекс."""
        try:
            installed = get_installed_pairs()
            self.available_packages = []
            self._installed_fallback = installed
            self._fill_tree()
            self.status_var.set("Обновляю каталог пакетов из интернета...")
        except Exception as error:
            self.status_var.set(f"Ошибка списка пакетов: {error}")

    def _window_alive(self) -> bool:
        """Проверяет, что окно языков ещё не закрыто."""
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    def _load_remote_index(self) -> None:
        """В фоне обновляет каталог Firefox и передаёт список в интерфейс."""
        try:
            update_remote_index()
            if self._window_alive():
                self.window.after(0, lambda: self._on_remote_loaded(None))
        except Exception as error:
            if self._window_alive():
                self.window.after(0, lambda: self._on_remote_loaded(str(error)))

    def _on_remote_loaded(self, error_message: str | None) -> None:
        """Обновляет таблицу после загрузки каталога."""
        if not self._window_alive():
            return
        architecture = self._selected_architecture()
        self.available_packages = sorted(
            get_available_pairs(architecture),
            key=self._package_sort_key,
        )
        self._fill_tree()
        if error_message:
            self.status_var.set(
                f"Каталог недоступен ({error_message}). Показаны установленные пакеты."
            )
        elif architecture:
            self.status_var.set(
                f"Модель {architecture}: доступно пакетов {len(self.available_packages)}"
            )
        else:
            self.status_var.set(
                f"Доступно пакетов Argos: {len(self.available_packages)}"
            )

    def _package_status(self, from_code: str, to_code: str) -> str:
        """Статус пакета для выбранного размера модели."""
        architecture = self._selected_architecture()
        if is_package_installed(from_code, to_code, architecture):
            return "Установлен"
        if architecture is None:
            return "Не установлен"
        others = [
            item
            for item in get_installed_architectures(from_code, to_code)
            if item != architecture
        ]
        if others:
            return "Есть " + "/".join(others)
        return "Не установлен"

    def _fill_tree(self) -> None:
        """Заполняет таблицу с учётом строки поиска."""
        try:
            for item_id in self.tree.get_children():
                self.tree.delete(item_id)

            search_text = self.search_var.get().strip().lower()
            rows_added = 0

            if self.available_packages:
                for language_package in self.available_packages:
                    from_code = language_package.from_code
                    to_code = language_package.to_code
                    from_name = language_display_name(
                        from_code, language_package.from_name
                    )
                    to_name = language_display_name(to_code, language_package.to_name)
                    if not self._matches_search(
                        search_text, from_code, to_code, from_name, to_name
                    ):
                        continue
                    self.tree.insert(
                        "",
                        tk.END,
                        iid=f"{from_code}->{to_code}",
                        values=(from_name, to_name, self._package_status(from_code, to_code)),
                    )
                    rows_added += 1
            else:
                for from_code, to_code, from_name, to_name in getattr(
                    self, "_installed_fallback", []
                ):
                    display_from = language_display_name(from_code, from_name)
                    display_to = language_display_name(to_code, to_name)
                    if not self._matches_search(
                        search_text, from_code, to_code, display_from, display_to
                    ):
                        continue
                    self.tree.insert(
                        "",
                        tk.END,
                        iid=f"{from_code}->{to_code}",
                        values=(
                            display_from,
                            display_to,
                            self._package_status(from_code, to_code),
                        ),
                    )
                    rows_added += 1

            if rows_added == 0:
                self.tree.insert("", tk.END, values=("Нет пакетов", "", ""))
        except Exception as error:
            self.status_var.set(f"Ошибка отображения списка: {error}")

    def _matches_search(
        self,
        search_text: str,
        from_code: str,
        to_code: str,
        from_name: str,
        to_name: str,
    ) -> bool:
        """Проверяет, подходит ли пакет под строку поиска."""
        if not search_text:
            return True
        haystack = f"{from_code} {to_code} {from_name} {to_name}".lower()
        return search_text in haystack

    def _on_install_click(self) -> None:
        """Запускает установку выбранного пакета."""
        if self.is_busy:
            return
        selection = self.tree.selection()
        if not selection:
            self.status_var.set("Выберите пакет в списке")
            return
        pair_id = selection[0]
        if "->" not in pair_id:
            self.status_var.set("Выберите пакет в списке")
            return
        from_code, to_code = pair_id.split("->", 1)
        architecture = self._selected_architecture()
        if is_package_installed(from_code, to_code, architecture):
            label = architecture or "Argos"
            self.status_var.set(f"Пакет {label} уже установлен")
            return

        language_package = next(
            (
                item
                for item in self.available_packages
                if item.from_code == from_code
                and item.to_code == to_code
                and (
                    architecture is None
                    or item.architecture == architecture
                )
            ),
            None,
        )
        if language_package is None:
            self.status_var.set("Пакет недоступен для скачивания (нет в каталоге)")
            return

        self.is_busy = True
        self.install_button.config(state=tk.DISABLED)
        self.progress["value"] = 0
        worker = threading.Thread(
            target=self._install_package,
            args=(language_package,),
            daemon=True,
        )
        worker.start()

    def _install_package(self, language_package) -> None:
        """Скачивает пакет в фоне."""
        try:
            download_and_install(language_package, self._on_progress)
            if self._window_alive():
                self.window.after(0, lambda: self._on_install_done(None, language_package))
            else:
                # Окно закрыли во время загрузки — всё равно обновим главный экран
                try:
                    self.on_packages_changed()
                except Exception:
                    pass
        except Exception as error:
            if self._window_alive():
                self.window.after(
                    0,
                    lambda message=str(error): self._on_install_done(
                        message, language_package
                    ),
                )

    def _on_progress(self, downloaded: int, total: int, message: str) -> None:
        """Обновляет прогресс из рабочего потока."""
        if not self._window_alive():
            return

        def update() -> None:
            if not self._window_alive():
                return
            try:
                if total:
                    self.progress["value"] = min(100, downloaded * 100 / total)
                self.status_var.set(message)
            except tk.TclError:
                pass

        try:
            self.window.after(0, update)
        except tk.TclError:
            pass

    def _on_install_done(self, error_message: str | None, language_package) -> None:
        """Завершает установку и обновляет главный экран."""
        if not self._window_alive():
            try:
                self.on_packages_changed()
            except Exception:
                pass
            return
        self.is_busy = False
        self.install_button.config(state=tk.NORMAL)
        self.progress["value"] = 100 if error_message is None else 0
        if error_message:
            self.status_var.set(f"Ошибка установки: {error_message}")
            return
        from_name = language_display_name(
            language_package.from_code, language_package.from_name
        )
        to_name = language_display_name(
            language_package.to_code, language_package.to_name
        )
        arch_label = language_package.architecture
        if arch_label == "argos":
            self.status_var.set(f"Установлено: {from_name} → {to_name}")
        else:
            self.status_var.set(
                f"Установлено: {from_name} → {to_name} ({arch_label})"
            )
        self._fill_tree()
        try:
            self.on_packages_changed()
        except Exception:
            pass
