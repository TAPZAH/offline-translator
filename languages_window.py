import threading
import tkinter as tk
from tkinter import messagebox, ttk

from app_settings import (
    ENGINE_ARGOS,
    ENGINE_FIREFOX,
    ENGINE_MARIAN,
    ENGINE_NLLB,
    get_engine_name,
)
from language_detect import language_display_name
from language_packages import (
    ARCHITECTURE_LABELS,
    DEFAULT_ARCHITECTURE,
    LanguagePackage,
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
    has_incomplete_package,
    is_package_installed,
    redownload_package,
    uninstall_package,
    update_remote_index,
)


class LanguagesWindow:
    """Список языковых пакетов: отдельное окно или страница настроек."""

    def __init__(
        self,
        master: tk.Misc,
        on_packages_changed,
        container: tk.Misc | None = None,
    ) -> None:
        self.on_packages_changed = on_packages_changed
        self.is_busy = False
        self.available_packages = []
        self._embedded = container is not None

        if self._embedded:
            self.window = master.winfo_toplevel()
            self.body = container
        else:
            self.window = tk.Toplevel(master)
            self.window.title("Языковые пакеты")
            self.window.geometry("640x500")
            self.window.minsize(600, 440)
            self.window.transient(master)
            self.body = self.window

        self._create_widgets()
        self._load_installed_only()
        threading.Thread(target=self._load_remote_index, daemon=True).start()

    def refresh_engine_ui(self) -> None:
        """Обновляет подсказку и список после смены движка."""
        if not self._window_alive() or self.is_busy:
            return
        self.hint_label.config(text=self._hint_text())
        if get_engine_name() == ENGINE_FIREFOX:
            if not self.size_frame.winfo_ismapped():
                self.size_frame.pack(
                    fill=tk.X,
                    padx=10,
                    pady=4,
                    before=self.search_frame,
                )
        else:
            self.size_frame.pack_forget()
        self._load_installed_only()
        threading.Thread(target=self._load_remote_index, daemon=True).start()

    def _hint_text(self) -> str:
        """Текст подсказки для текущего движка."""
        engine = get_engine_name()
        if engine == ENGINE_FIREFOX:
            return (
                "Нет прямой пары — программа переведёт через английский. "
                "Для китайского нужен размер base. "
                "Установленный пакет можно удалить или скачать заново."
            )
        if engine == ENGINE_ARGOS:
            return (
                "Пакеты Argos Translate. Нет прямой пары — перевод пойдёт через английский. "
                "Установленный пакет можно удалить или скачать заново."
            )
        if engine == ENGINE_NLLB:
            return (
                "NLLB-200 — одна модель на 200 языков. Скачайте пакет один раз, "
                "после этого доступны все пары. Повреждённую модель удалите "
                "или скачайте заново."
            )
        if engine == ENGINE_MARIAN:
            return (
                "MarianMT — модели Helsinki-NLP OPUS-MT через CTranslate2. "
                "Нет прямой пары — перевод пойдёт через английский. "
                "Установленный пакет можно удалить или скачать заново."
            )
        return "Установите языковые пакеты текущего движка."

    def _create_widgets(self) -> None:
        """Создаёт список пакетов, поиск и кнопки."""
        engine = get_engine_name()
        hint_text = self._hint_text()
        self.hint_label = tk.Label(
            self.body,
            text=hint_text,
            wraplength=640,
            justify=tk.LEFT,
        )
        self.hint_label.pack(fill=tk.X, padx=10, pady=(10, 4))

        self.size_frame = tk.Frame(self.body)
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

        self.search_frame = tk.Frame(self.body)
        self.search_frame.pack(fill=tk.X, padx=10, pady=4)
        tk.Label(self.search_frame, text="Поиск:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_args: self._fill_tree())
        search_entry = tk.Entry(self.search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        list_frame = tk.Frame(self.body)
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
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_action_buttons())

        button_frame = tk.Frame(self.body)
        button_frame.pack(fill=tk.X, padx=10, pady=4)
        self.install_button = tk.Button(
            button_frame,
            text="Установить",
            command=self._on_install_click,
        )
        self.install_button.pack(side=tk.LEFT)
        self.redownload_button = tk.Button(
            button_frame,
            text="Перекачать",
            command=self._on_redownload_click,
        )
        self.redownload_button.pack(side=tk.LEFT, padx=(6, 0))
        self.delete_button = tk.Button(
            button_frame,
            text="Удалить",
            command=self._on_delete_click,
        )
        self.delete_button.pack(side=tk.LEFT, padx=(6, 0))
        if not self._embedded:
            tk.Button(button_frame, text="Закрыть", command=self.window.destroy).pack(
                side=tk.RIGHT
            )

        self.progress = ttk.Progressbar(self.body, mode="determinate")
        self.progress.pack(fill=tk.X, padx=10, pady=(4, 2))
        self.status_var = tk.StringVar(value="Загружаю список пакетов...")
        tk.Label(self.body, textvariable=self.status_var, anchor=tk.W).pack(
            fill=tk.X, padx=10, pady=(0, 8)
        )
        self._refresh_action_buttons()

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
                f"Доступно пакетов: {len(self.available_packages)}"
            )

    def _package_status(self, from_code: str, to_code: str) -> str:
        """Статус пакета для выбранного размера модели."""
        architecture = self._selected_architecture()
        if is_package_installed(from_code, to_code, architecture):
            return "Установлен"
        if has_incomplete_package(from_code, to_code, architecture):
            return "Повреждена"
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
            self._refresh_action_buttons()
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
        language_package = self._selected_language_package()
        if language_package is None:
            return
        architecture = self._selected_architecture()
        if is_package_installed(
            language_package.from_code,
            language_package.to_code,
            architecture,
        ):
            self.status_var.set("Пакет уже установлен. Чтобы заменить — «Перекачать».")
            return
        if get_engine_name() != ENGINE_NLLB:
            matched = any(
                item.from_code == language_package.from_code
                and item.to_code == language_package.to_code
                and (
                    architecture is None
                    or item.architecture == architecture
                )
                for item in self.available_packages
            )
            if not matched:
                self.status_var.set("Пакет недоступен для скачивания (нет в каталоге)")
                return
        self._start_package_job("install", language_package)

    def _on_redownload_click(self) -> None:
        """Удаляет выбранный пакет и скачивает его заново."""
        language_package = self._selected_language_package()
        if language_package is None:
            return
        if not self._can_remove(language_package):
            self.status_var.set("Сначала установите пакет, либо выберите повреждённый")
            return
        if not self._confirm_action(
            "Перекачать пакет",
            self._confirm_message(language_package, redownload=True),
        ):
            return
        self._start_package_job("redownload", language_package)

    def _on_delete_click(self) -> None:
        """Удаляет выбранный пакет с диска."""
        language_package = self._selected_language_package()
        if language_package is None:
            return
        if not self._can_remove(language_package):
            self.status_var.set("Этот пакет не установлен")
            return
        if not self._confirm_action(
            "Удалить пакет",
            self._confirm_message(language_package, redownload=False),
        ):
            return
        self._start_package_job("delete", language_package)

    def _selected_pair(self) -> tuple[str, str] | None:
        """Коды выбранной строки или None."""
        if self.is_busy:
            self.status_var.set("Дождитесь окончания текущей операции")
            return None
        selection = self.tree.selection()
        if not selection:
            self.status_var.set("Выберите пакет в списке")
            return None
        pair_id = selection[0]
        if "->" not in pair_id:
            self.status_var.set("Выберите пакет в списке")
            return None
        from_code, to_code = pair_id.split("->", 1)
        return from_code, to_code

    def _selected_language_package(self):
        """Пакет выбранной строки, в том числе для NLLB целиком."""
        pair = self._selected_pair()
        if pair is None:
            return None
        from_code, to_code = pair
        if get_engine_name() == ENGINE_NLLB:
            return get_available_pairs()[0]
        architecture = self._selected_architecture()
        for item in self.available_packages:
            if item.from_code != from_code or item.to_code != to_code:
                continue
            if architecture is None or item.architecture == architecture:
                return item
        return LanguagePackage(
            from_code=from_code,
            to_code=to_code,
            from_name=language_display_name(from_code, from_code),
            to_name=language_display_name(to_code, to_code),
            dirname=f"{from_code}{to_code}",
            architecture=architecture or DEFAULT_ARCHITECTURE,
        )

    def _can_remove(self, language_package) -> bool:
        """Можно удалить или перекачать, если пакет стоит или повреждён."""
        architecture = getattr(language_package, "architecture", None)
        if architecture in {"argos", "nllb"}:
            architecture = self._selected_architecture()
        return is_package_installed(
            language_package.from_code,
            language_package.to_code,
            architecture,
        ) or has_incomplete_package(
            language_package.from_code,
            language_package.to_code,
            architecture,
        )

    def _confirm_message(self, language_package, redownload: bool) -> str:
        """Текст подтверждения удаления или перекачки."""
        if get_engine_name() == ENGINE_NLLB:
            if redownload:
                return (
                    "Скачать модель NLLB-200 заново? "
                    "Текущие файлы будут удалены (~600 МБ)."
                )
            return "Удалить модель NLLB-200 целиком? Это одна модель на все языки."
        from_name = language_display_name(
            language_package.from_code, language_package.from_name
        )
        to_name = language_display_name(
            language_package.to_code, language_package.to_name
        )
        pair = f"{from_name} → {to_name}"
        if redownload:
            return f"Скачать заново пакет {pair}? Текущие файлы будут удалены."
        return f"Удалить пакет {pair} с диска?"

    def _confirm_action(self, title: str, message: str) -> bool:
        """Спрашивает подтверждение в модальном окне."""
        try:
            return bool(
                messagebox.askyesno(title, message, parent=self.window)
            )
        except tk.TclError:
            return False

    def _refresh_action_buttons(self) -> None:
        """Включает Удалить/Перекачать только для установленных пакетов."""
        if self.is_busy:
            return
        try:
            selection = self.tree.selection()
            enabled = False
            if selection and "->" in selection[0]:
                from_code, to_code = selection[0].split("->", 1)
                if get_engine_name() == ENGINE_NLLB:
                    package = get_available_pairs()[0]
                    enabled = self._can_remove(package)
                else:
                    architecture = self._selected_architecture()
                    enabled = is_package_installed(
                        from_code, to_code, architecture
                    ) or has_incomplete_package(from_code, to_code, architecture)
            state = tk.NORMAL if enabled else tk.DISABLED
            self.redownload_button.config(state=state)
            self.delete_button.config(state=state)
        except Exception:
            pass

    def _set_busy(self, busy: bool) -> None:
        """Блокирует кнопки на время скачивания или удаления."""
        self.is_busy = busy
        install_state = tk.DISABLED if busy else tk.NORMAL
        self.install_button.config(state=install_state)
        if busy:
            self.redownload_button.config(state=tk.DISABLED)
            self.delete_button.config(state=tk.DISABLED)
        else:
            self._refresh_action_buttons()

    def _start_package_job(self, action: str, language_package) -> None:
        """Запускает установку, перекачку или удаление в фоне."""
        self._set_busy(True)
        self.progress["value"] = 0
        worker = threading.Thread(
            target=self._run_package_job,
            args=(action, language_package),
            daemon=True,
        )
        worker.start()

    def _run_package_job(self, action: str, language_package) -> None:
        """Выполняет операцию с пакетом вне UI-потока."""
        try:
            if action == "delete":
                architecture = getattr(language_package, "architecture", None)
                if architecture in {"argos", "nllb"}:
                    architecture = None
                uninstall_package(
                    language_package.from_code,
                    language_package.to_code,
                    architecture,
                )
            elif action == "redownload":
                redownload_package(language_package, self._on_progress)
            else:
                download_and_install(language_package, self._on_progress)
            if self._window_alive():
                self.window.after(
                    0,
                    lambda: self._on_job_done(None, language_package, action),
                )
            else:
                try:
                    self.on_packages_changed()
                except Exception:
                    pass
        except Exception as error:
            if self._window_alive():
                self.window.after(
                    0,
                    lambda message=str(error): self._on_job_done(
                        message, language_package, action
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

    def _on_job_done(
        self,
        error_message: str | None,
        language_package,
        action: str,
    ) -> None:
        """Завершает установку, перекачку или удаление."""
        if not self._window_alive():
            try:
                self.on_packages_changed()
            except Exception:
                pass
            return
        self._set_busy(False)
        self.progress["value"] = 100 if error_message is None else 0
        if error_message:
            labels = {
                "delete": "Ошибка удаления",
                "redownload": "Ошибка перекачки",
                "install": "Ошибка установки",
            }
            self.status_var.set(f"{labels.get(action, 'Ошибка')}: {error_message}")
            return
        from_name = language_display_name(
            language_package.from_code, language_package.from_name
        )
        to_name = language_display_name(
            language_package.to_code, language_package.to_name
        )
        pair = f"{from_name} → {to_name}"
        if action == "delete":
            self.status_var.set(f"Удалено: {pair}")
        elif action == "redownload":
            self.status_var.set(f"Скачано заново: {pair}")
        else:
            arch_label = language_package.architecture
            if arch_label in {"argos", "nllb"}:
                self.status_var.set(f"Установлено: {pair}")
            else:
                self.status_var.set(f"Установлено: {pair} ({arch_label})")
        self._fill_tree()
        try:
            self.on_packages_changed()
        except Exception:
            pass
