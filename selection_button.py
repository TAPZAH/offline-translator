import ctypes
import os
import queue
import threading
import time
import tkinter as tk
from ctypes import wintypes

import pyperclip
from PIL import Image, ImageTk

import portable_env
from app_settings import (
    RESULT_WINDOW_CLICK_TO_CLOSE,
    get_double_ctrl_c_translation,
    get_popup_requires_ctrl,
    get_result_window_mode,
)
from language_detect import detect_language_code, language_display_name

VK_LBUTTON = 0x01
VK_CONTROL = 0x11
VK_C = 0x43
KEYEVENTF_KEYUP = 0x0002
DRAG_THRESHOLD_PX = 16
MIN_DRAG_DURATION_S = 0.18
WINDOW_MOVE_PX = 4
DOUBLE_CLICK_S = 0.35
DOUBLE_CLICK_PX = 6
HTCLIENT = 1
GA_ROOT = 2
WM_NCHITTEST = 0x0084
GUI_INMOVESIZE = 0x00000002
BUTTON_HIDE_MS = 8000
POLL_MS = 40
COPY_WAIT_MS = 80
CLIPBOARD_WAIT_S = 0.08
DOUBLE_CTRL_C_S = 0.7
ICON_SIZE = 40
ASSETS_DIR = os.path.join(portable_env.resource_dir(), "assets")
SELECTION_ICON_PATH = os.path.join(ASSETS_DIR, "icon.png")
TRAY_ICON_PATH = os.path.join(ASSETS_DIR, "icon-tray.png")
ICON_TRANSPARENT = "#ff00ff"
OVERLAY_BG = "#f2f2f2"
OVERLAY_BORDER = "#000000"
OVERLAY_TEXT = "#000000"
OVERLAY_MUTED = "#333333"
OVERLAY_COPY_BG = "#dedede"
OVERLAY_COPY_HOVER = "#cccccc"
OVERLAY_FONT = ("Segoe UI", 11)
OVERLAY_FONT_SMALL = ("Segoe UI", 8)
OVERLAY_FONT_BUTTON = ("Segoe UI", 9)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", RECT),
    ]


def choose_selection_direction(
    text: str,
    installed_codes: set[str] | None = None,
) -> tuple[str, str]:
    """Русский текст переводим на английский, любой другой — на русский."""
    detected_code = detect_language_code(text)
    if detected_code == "ru":
        return "ru", "en"
    source_code = detected_code or "en"
    if installed_codes and source_code not in installed_codes:
        source_code = "en"
    return source_code, "ru"


def _mouse_pressed() -> bool:
    """Проверяет, зажата ли левая кнопка мыши."""
    return bool(ctypes.windll.user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)


def _key_pressed(key_code: int) -> bool:
    """Проверяет, удерживается ли клавиша с указанным Windows-кодом."""
    return bool(ctypes.windll.user32.GetAsyncKeyState(key_code) & 0x8000)


def _control_pressed() -> bool:
    """Проверяет, удерживается ли Ctrl."""
    return _key_pressed(VK_CONTROL)


def should_trigger_double_ctrl_c(
    previous_press_time: float,
    current_press_time: float,
    ctrl_pressed: bool,
    enabled: bool,
) -> bool:
    """Проверяет второй C при непрерывно удерживаемом Ctrl."""
    if not enabled or not ctrl_pressed or previous_press_time <= 0:
        return False
    elapsed = current_press_time - previous_press_time
    return 0 < elapsed <= DOUBLE_CTRL_C_S


def should_show_selection_button(
    requires_ctrl: bool,
    ctrl_pressed: bool,
) -> bool:
    """Разрешает кнопку всегда или только при удерживаемом Ctrl."""
    return not requires_ctrl or ctrl_pressed


def _cursor_position() -> tuple[int, int]:
    """Возвращает экранные координаты курсора."""
    point = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def _hwnd_from_point(x: int, y: int) -> int:
    """Окно под курсором."""
    hwnd = ctypes.windll.user32.WindowFromPoint(POINT(x, y))
    return int(hwnd) if hwnd else 0


def _root_hwnd(hwnd: int) -> int:
    """Корневое окно приложения."""
    if not hwnd:
        return 0
    root = ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT)
    return int(root) if root else hwnd


def _window_origin(hwnd: int) -> tuple[int, int] | None:
    """Левый верхний угол окна на экране."""
    if not hwnd:
        return None
    rect = RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return rect.left, rect.top


def _is_client_hit(x: int, y: int, hwnd: int) -> bool:
    """Проверяет, что клик попал в клиентскую область, а не в заголовок."""
    if not hwnd:
        return False
    packed = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
    hit = ctypes.windll.user32.SendMessageW(hwnd, WM_NCHITTEST, 0, packed)
    return int(hit) == HTCLIENT


def _is_window_being_moved() -> bool:
    """Определяет, перетаскивает ли пользователь окно за заголовок."""
    user32 = ctypes.windll.user32
    foreground = user32.GetForegroundWindow()
    if not foreground:
        return False
    thread_id = user32.GetWindowThreadProcessId(foreground, None)
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    if not user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
        return False
    return bool(info.flags & GUI_INMOVESIZE) or bool(info.hwndMoveSize)


def should_capture_selection(
    press_is_client: bool,
    window_moved: bool,
    drag_distance: float,
    drag_duration: float,
    is_double_click: bool,
) -> bool:
    """Отсекает перетаскивание окна и клик для смены фокуса."""
    if not press_is_client or window_moved:
        return False
    if drag_distance >= DRAG_THRESHOLD_PX and drag_duration >= MIN_DRAG_DURATION_S:
        return True
    return is_double_click


def _send_ctrl_c() -> None:
    """Отправляет Ctrl+C, чтобы скопировать текущее выделение."""
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_C, 0, 0, 0)
    user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def capture_selected_text() -> str:
    """Читает выделенный текст через буфер, затем восстанавливает буфер."""
    previous = ""
    try:
        previous = pyperclip.paste() or ""
    except Exception:
        previous = ""
    sentinel = f"__ot_sel_{time.time_ns()}__"
    try:
        pyperclip.copy(sentinel)
        _send_ctrl_c()
        time.sleep(CLIPBOARD_WAIT_S)
        selected = pyperclip.paste() or ""
    except Exception:
        selected = ""
    try:
        pyperclip.copy(previous)
    except Exception:
        pass
    selected = selected.strip()
    if not selected or selected == sentinel:
        return ""
    return selected


def _style_overlay_window(window: tk.Toplevel) -> None:
    """Делает окно поверх всех, без рамки и слегка прозрачным."""
    window.overrideredirect(True)
    window.attributes("-topmost", True)
    window.configure(bg=OVERLAY_BORDER)
    try:
        window.attributes("-alpha", 0.97)
    except tk.TclError:
        pass


def _fill_clickable_disk(image: Image.Image, alpha_limit: int = 80) -> Image.Image:
    """Делает внутренность знака непрозрачной, чтобы клик в центр не проваливался.

    Дырка Recycling связана с внешним фоном, поэтому заливаем круг по контуру стрелок.
    """
    image = image.convert("RGBA")
    width, height = image.size
    pixels = image.load()
    center_x = (width - 1) / 2
    center_y = (height - 1) / 2
    radius_sq = 0.0
    for y in range(height):
        for x in range(width):
            if pixels[x, y][3] < alpha_limit:
                continue
            delta_x = x - center_x
            delta_y = y - center_y
            radius_sq = max(radius_sq, delta_x * delta_x + delta_y * delta_y)
    for y in range(height):
        for x in range(width):
            if pixels[x, y][3] >= alpha_limit:
                continue
            delta_x = x - center_x
            delta_y = y - center_y
            if delta_x * delta_x + delta_y * delta_y <= radius_sq:
                pixels[x, y] = (255, 255, 255, 255)
    return image


def _flatten_icon_for_window(
    image: Image.Image,
    key_rgb: tuple[int, int, int] = (255, 0, 255),
) -> Image.Image:
    """Готовит иконку для прозрачного окна без розовой каймы.

    Внешний фон вырезается ключом, внутренность знака остаётся непрозрачной,
    чтобы клик в центр не проваливался сквозь окно.
    """
    image = _fill_clickable_disk(image.convert("RGBA"))
    result = Image.new("RGB", image.size, key_rgb)
    source_pixels = image.load()
    result_pixels = result.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = source_pixels[x, y]
            if alpha < 80:
                result_pixels[x, y] = key_rgb
            else:
                result_pixels[x, y] = (red, green, blue)
    return result


class SelectionPopup:
    """Плавающая кнопка перевода после выделения текста."""

    def __init__(self, root: tk.Tk, translate_func, installed_codes_func=None) -> None:
        self.root = root
        self.translate_func = translate_func
        self.installed_codes_func = installed_codes_func
        self._press_x = 0
        self._press_y = 0
        self._press_hwnd = 0
        self._press_origin = (0, 0)
        self._press_time = 0.0
        self._press_is_client = False
        self._gesture_invalid = False
        self._press_active = False
        self._last_up_hwnd = 0
        self._last_up_x = 0
        self._last_up_y = 0
        self._was_pressed = False
        self._was_c_pressed = False
        self._last_up_time = 0.0
        self._last_ctrl_c_time = 0.0
        self._selected_text = ""
        self._button_window: tk.Toplevel | None = None
        self._result_window: tk.Toplevel | None = None
        self._translate_button: tk.Label | None = None
        self._copy_button: tk.Button | None = None
        self._close_button: tk.Button | None = None
        self._result_text: tk.Text | None = None
        self._icon_photo: ImageTk.PhotoImage | None = None
        self._is_translating = False
        self._hide_job = None
        self._capture_job = None
        self._shortcut_job = None
        self._stopped = False
        self._ui_jobs: queue.Queue = queue.Queue()
        self._poll()

    def stop(self) -> None:
        """Останавливает опрос мыши и закрывает всплывающие окна."""
        self._stopped = True
        for job_name in ("_hide_job", "_capture_job", "_shortcut_job"):
            job = getattr(self, job_name)
            if job is None:
                continue
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
            setattr(self, job_name, None)
        try:
            self._hide_button()
            self._hide_result()
        except Exception:
            pass

    def _installed_codes(self) -> set[str] | None:
        """Возвращает коды установленных языков, если callback задан."""
        if self.installed_codes_func is None:
            return None
        try:
            return self.installed_codes_func()
        except Exception:
            return None

    def _load_recycle_icon(self) -> ImageTk.PhotoImage:
        """Загружает иконку выделения без фона для прозрачного окна."""
        if self._icon_photo is not None:
            return self._icon_photo
        with Image.open(SELECTION_ICON_PATH) as opened:
            image = opened.convert("RGBA")
        image = image.resize((ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS)
        flattened = _flatten_icon_for_window(image)
        self._icon_photo = ImageTk.PhotoImage(flattened, master=self.root)
        return self._icon_photo

    def _drain_ui_jobs(self) -> None:
        """Выполняет отложенные UI-задачи в главном потоке."""
        while True:
            try:
                job = self._ui_jobs.get_nowait()
            except queue.Empty:
                break
            try:
                job()
            except Exception:
                pass

    def _poll(self) -> None:
        """Отслеживает выделение текста по перетаскиванию мыши."""
        try:
            if self._stopped or not self.root.winfo_exists():
                return
            self._drain_ui_jobs()
            self._poll_double_ctrl_c()
            pressed = _mouse_pressed()
            cursor_x, cursor_y = _cursor_position()
            if pressed and not self._was_pressed:
                if self._is_over_our_popup(cursor_x, cursor_y):
                    self._press_active = False
                else:
                    self._begin_press(cursor_x, cursor_y)
            elif pressed and self._was_pressed:
                if self._press_active:
                    self._update_press_gesture()
            elif not pressed and self._was_pressed:
                if self._press_active:
                    self._finish_press(cursor_x, cursor_y)
                self._press_active = False
            self._was_pressed = pressed
        except tk.TclError:
            return
        except Exception:
            pass
        try:
            if self._stopped:
                return
            self.root.after(POLL_MS, self._poll)
        except tk.TclError:
            return

    def _poll_double_ctrl_c(self) -> None:
        """Распознаёт два нажатия C при удерживаемом Ctrl."""
        enabled = get_double_ctrl_c_translation()
        ctrl_pressed = _control_pressed()
        c_pressed = _key_pressed(VK_C)

        if not enabled:
            self._last_ctrl_c_time = 0.0
            self._was_c_pressed = c_pressed
            return
        if not ctrl_pressed:
            self._last_ctrl_c_time = 0.0

        if c_pressed and not self._was_c_pressed and ctrl_pressed:
            now = time.monotonic()
            if should_trigger_double_ctrl_c(
                self._last_ctrl_c_time,
                now,
                ctrl_pressed,
                enabled,
            ):
                self._last_ctrl_c_time = 0.0
                if self._shortcut_job is not None:
                    try:
                        self.root.after_cancel(self._shortcut_job)
                    except tk.TclError:
                        pass
                self._shortcut_job = self.root.after(
                    COPY_WAIT_MS,
                    self._translate_clipboard_selection,
                )
            else:
                self._last_ctrl_c_time = now
        self._was_c_pressed = c_pressed

    def _begin_press(self, cursor_x: int, cursor_y: int) -> None:
        """Запоминает начало жеста мыши."""
        hwnd = _hwnd_from_point(cursor_x, cursor_y)
        self._press_x = cursor_x
        self._press_y = cursor_y
        self._press_time = time.time()
        self._press_hwnd = _root_hwnd(hwnd)
        self._press_origin = _window_origin(self._press_hwnd) or (cursor_x, cursor_y)
        self._press_is_client = _is_client_hit(cursor_x, cursor_y, hwnd)
        self._gesture_invalid = not self._press_is_client
        self._press_active = True

    def _update_press_gesture(self) -> None:
        """Помечает жест как ложный, если окно двигают или растягивают."""
        if self._gesture_invalid:
            return
        try:
            if _is_window_being_moved():
                self._gesture_invalid = True
                return
            origin = _window_origin(self._press_hwnd)
            if origin is None:
                return
            if (
                abs(origin[0] - self._press_origin[0]) >= WINDOW_MOVE_PX
                or abs(origin[1] - self._press_origin[1]) >= WINDOW_MOVE_PX
            ):
                self._gesture_invalid = True
        except Exception:
            pass

    def _finish_press(self, cursor_x: int, cursor_y: int) -> None:
        """Решает, похож ли жест на выделение текста."""
        now = time.time()
        self._update_press_gesture()
        drag_distance = max(
            abs(cursor_x - self._press_x),
            abs(cursor_y - self._press_y),
        )
        drag_duration = now - self._press_time
        origin = _window_origin(self._press_hwnd)
        window_moved = False
        if origin is not None:
            window_moved = (
                abs(origin[0] - self._press_origin[0]) >= WINDOW_MOVE_PX
                or abs(origin[1] - self._press_origin[1]) >= WINDOW_MOVE_PX
            )
        is_double_click = (
            (now - self._last_up_time) < DOUBLE_CLICK_S
            and self._press_hwnd != 0
            and self._press_hwnd == self._last_up_hwnd
            and abs(cursor_x - self._last_up_x) <= DOUBLE_CLICK_PX
            and abs(cursor_y - self._last_up_y) <= DOUBLE_CLICK_PX
            and self._press_is_client
        )
        self._last_up_time = now
        self._last_up_hwnd = self._press_hwnd
        self._last_up_x = cursor_x
        self._last_up_y = cursor_y
        if self._gesture_invalid or self._is_over_our_popup(cursor_x, cursor_y):
            return
        if not should_capture_selection(
            self._press_is_client,
            window_moved,
            drag_distance,
            drag_duration,
            is_double_click,
        ):
            return
        if not should_show_selection_button(
            get_popup_requires_ctrl(),
            _control_pressed(),
        ):
            return
        if self._capture_job is not None:
            self.root.after_cancel(self._capture_job)
        self._capture_job = self.root.after(
            COPY_WAIT_MS,
            lambda x=cursor_x, y=cursor_y: self._capture_and_show(x, y),
        )

    def _is_over_our_popup(self, cursor_x: int, cursor_y: int) -> bool:
        """Не перехватывает клики по своим всплывающим окнам."""
        for window in (self._button_window, self._result_window):
            if window is None:
                continue
            try:
                if not window.winfo_exists() or not window.winfo_viewable():
                    continue
                x = window.winfo_rootx()
                y = window.winfo_rooty()
                width = window.winfo_width()
                height = window.winfo_height()
                if x <= cursor_x <= x + width and y <= cursor_y <= y + height:
                    return True
            except tk.TclError:
                continue
        return False

    def _capture_and_show(self, cursor_x: int, cursor_y: int) -> None:
        """Копирует выделение и показывает кнопку рядом с курсором."""
        self._capture_job = None
        if self._stopped:
            return
        try:
            selected = capture_selected_text()
            if len(selected) < 2:
                return
            self._selected_text = selected
            self.show_button(selected, cursor_x, cursor_y)
        except Exception:
            pass

    def _translate_clipboard_selection(self) -> None:
        """Переводит текст, скопированный вторым нажатием Ctrl+C."""
        self._shortcut_job = None
        if self._stopped:
            return
        try:
            selected = (pyperclip.paste() or "").strip()
            if len(selected) < 2:
                return
            self._selected_text = selected
            self._hide_button()
            self._on_translate_click()
        except Exception as error:
            self._show_error(str(error))

    def show_button(self, text: str, cursor_x: int, cursor_y: int) -> None:
        """Показывает квадратную иконку Recycling у курсора."""
        self._selected_text = text
        self._is_translating = False
        self._hide_result()
        self._hide_button()
        button_window = tk.Toplevel(self.root)
        button_window.overrideredirect(True)
        button_window.attributes("-topmost", True)
        button_window.configure(bg=ICON_TRANSPARENT)
        try:
            button_window.attributes("-transparentcolor", ICON_TRANSPARENT)
        except tk.TclError:
            button_window.configure(bg="#ffffff")
        icon_x = cursor_x - ICON_SIZE // 2
        icon_y = cursor_y - ICON_SIZE // 2
        button_window.geometry(f"+{icon_x}+{icon_y}")
        icon = tk.Label(
            button_window,
            image=self._load_recycle_icon(),
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            bg=ICON_TRANSPARENT,
        )
        icon.pack()
        icon.bind("<Button-1>", lambda _event: self._on_translate_click())
        self._translate_button = icon
        self._button_window = button_window
        if self._hide_job is not None:
            try:
                self.root.after_cancel(self._hide_job)
            except tk.TclError:
                pass
        self._hide_job = self.root.after(BUTTON_HIDE_MS, self._hide_button)

    def _on_translate_click(self) -> None:
        """Запускает перевод сохранённого выделения."""
        if self._stopped:
            return
        text = self._selected_text.strip()
        if not text or self._is_translating:
            return
        self._is_translating = True
        worker = threading.Thread(
            target=self._translate_in_background,
            args=(text,),
            daemon=True,
        )
        worker.start()

    def _translate_in_background(self, text: str) -> None:
        """Выполняет перевод вне UI-потока."""
        try:
            if self._stopped:
                return
            translated, source_code, target_code = self.translate_func(text)
            if self._stopped:
                return
            self._ui_jobs.put(
                lambda: self._show_result(translated, source_code, target_code)
            )
        except Exception as error:
            if self._stopped:
                return
            self._ui_jobs.put(lambda message=str(error): self._show_error(message))

    def _show_result(self, translated: str, source_code: str, target_code: str) -> None:
        """Показывает светлое окно с переводом."""
        self._is_translating = False
        self._hide_button()
        self._hide_result()
        result_mode = get_result_window_mode()
        result_window = tk.Toplevel(self.root)
        _style_overlay_window(result_window)
        cursor_x, cursor_y = _cursor_position()
        result_window.geometry(f"+{cursor_x + 12}+{cursor_y + 12}")

        inner = tk.Frame(result_window, bg=OVERLAY_BG, padx=16, pady=14)
        inner.pack(padx=1, pady=1)
        header = tk.Label(
            inner,
            text=(
                f"{language_display_name(source_code)} → "
                f"{language_display_name(target_code)}"
            ),
            anchor=tk.W,
            bg=OVERLAY_BG,
            fg=OVERLAY_MUTED,
            font=OVERLAY_FONT_SMALL,
        )
        header.pack(fill=tk.X, pady=(0, 6))
        visual_lines = sum(
            max(1, (len(line) + 39) // 40)
            for line in (translated.splitlines() or [""])
        )
        output = tk.Text(
            inner,
            width=40,
            height=min(12, max(2, visual_lines)),
            wrap=tk.WORD,
            bg=OVERLAY_BG,
            fg=OVERLAY_TEXT,
            font=OVERLAY_FONT,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
        )
        output.pack(fill=tk.BOTH, expand=True)
        output.insert("1.0", translated)
        output.config(state=tk.DISABLED)

        def copy_result() -> None:
            try:
                try:
                    copied_text = output.get("sel.first", "sel.last")
                except tk.TclError:
                    copied_text = translated
                pyperclip.copy(copied_text)
            except Exception:
                pass

        buttons = tk.Frame(inner, bg=OVERLAY_BG)
        buttons.pack(fill=tk.X, pady=(12, 0))
        copy_button = tk.Button(
            buttons,
            text="Копировать",
            command=copy_result,
            cursor="hand2",
            bg=OVERLAY_COPY_BG,
            fg=OVERLAY_TEXT,
            activebackground=OVERLAY_COPY_HOVER,
            activeforeground=OVERLAY_TEXT,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=3,
            font=OVERLAY_FONT_BUTTON,
        )
        copy_button.pack(side=tk.RIGHT)
        copy_button.bind(
            "<Enter>",
            lambda _event: copy_button.config(bg=OVERLAY_COPY_HOVER),
        )
        copy_button.bind(
            "<Leave>",
            lambda _event: copy_button.config(bg=OVERLAY_COPY_BG),
        )
        close_button = None
        if result_mode != RESULT_WINDOW_CLICK_TO_CLOSE:
            close_button = tk.Button(
                buttons,
                text="Закрыть",
                command=self._hide_result,
                cursor="hand2",
                bg=OVERLAY_COPY_BG,
                fg=OVERLAY_TEXT,
                activebackground=OVERLAY_COPY_HOVER,
                activeforeground=OVERLAY_TEXT,
                relief=tk.FLAT,
                bd=0,
                highlightthickness=0,
                padx=10,
                pady=3,
                font=OVERLAY_FONT_BUTTON,
            )
            close_button.pack(side=tk.RIGHT, padx=(0, 8))
            close_button.bind(
                "<Enter>",
                lambda _event: close_button.config(bg=OVERLAY_COPY_HOVER),
            )
            close_button.bind(
                "<Leave>",
                lambda _event: close_button.config(bg=OVERLAY_COPY_BG),
            )
        result_window.bind("<Escape>", lambda _event: self._hide_result())
        self._copy_button = copy_button
        self._close_button = close_button
        self._result_text = output
        if result_mode == RESULT_WINDOW_CLICK_TO_CLOSE:
            self._bind_result_click_to_close(result_window, copy_button)
        self._result_window = result_window

    def _bind_result_click_to_close(self, widget, copy_button) -> None:
        """Закрывает окно по клику в любом месте, кроме кнопки «Копировать»."""
        if widget is copy_button:
            return
        widget.bind("<Button-1>", lambda _event: self._hide_result())
        for child in widget.winfo_children():
            self._bind_result_click_to_close(child, copy_button)
        # Canvas держит содержимое через create_window — его тоже обходим
        try:
            for item_id in widget.find_all():
                inner_widget = widget.itemcget(item_id, "window")
                if inner_widget:
                    self._bind_result_click_to_close(
                        widget.nametowidget(inner_widget),
                        copy_button,
                    )
        except (tk.TclError, AttributeError):
            pass

    def _show_error(self, message: str) -> None:
        """Показывает ошибку перевода в затенённом окне."""
        self._is_translating = False
        self._show_result(f"Ошибка: {message}", "auto", "auto")

    def _hide_button(self) -> None:
        """Скрывает кнопку перевода."""
        if self._hide_job is not None:
            try:
                self.root.after_cancel(self._hide_job)
            except tk.TclError:
                pass
            self._hide_job = None
        if self._button_window is None:
            return
        try:
            self._button_window.destroy()
        except tk.TclError:
            pass
        self._button_window = None
        self._translate_button = None

    def _hide_result(self) -> None:
        """Скрывает окно результата."""
        if self._result_window is None:
            return
        try:
            self._result_window.destroy()
        except tk.TclError:
            pass
        self._result_window = None
        self._copy_button = None
        self._close_button = None
        self._result_text = None
