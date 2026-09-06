import time
import tkinter as tk

import pyperclip
from PIL import Image

import selection_button
from app_settings import RESULT_WINDOW_CLICK_TO_CLOSE, RESULT_WINDOW_SELECTABLE
from selection_button import (
    ICON_DARK_PATH,
    ICON_LIGHT_PATH,
    ICON_SIZE,
    SELECTION_ICON_PATH,
    SelectionPopup,
    overlay_theme,
    theme_icon_path,
    _flatten_icon_for_window,
    _style_overlay_window,
    choose_selection_direction,
    should_capture_selection,
    should_show_selection_button,
    should_skip_selection_copy,
    should_trigger_double_ctrl_c,
)


def test_recycle_icon_file() -> None:
    """Проверяет, что иконки светлой и тёмной темы квадратные и общие."""
    for path in (ICON_LIGHT_PATH, ICON_DARK_PATH, theme_icon_path(), SELECTION_ICON_PATH):
        image = Image.open(path)
        width, height = image.size
        assert width == height, (path, width, height)
        assert width >= 32
        print(f"icon: ok {path} {width}x{height}")


def test_icon_center_is_clickable() -> None:
    """Центр знака не должен быть цветом-ключом, иначе клик проваливается."""
    image = Image.open(theme_icon_path()).convert("RGBA")
    image = image.resize((ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS)
    flattened = _flatten_icon_for_window(image)
    center = flattened.getpixel((ICON_SIZE // 2, ICON_SIZE // 2))
    if center == (255, 0, 255):
        raise AssertionError("Центр иконки прозрачный — клик провалится")
    print(f"icon-center: ok {center}")


def test_overlay_theme_opaque() -> None:
    """Светлая и тёмная темы дают непрозрачное окно с контрастной рамкой."""
    original = selection_button.get_ui_theme
    root = tk.Tk()
    root.withdraw()
    try:
        selection_button.get_ui_theme = lambda: "light"
        light = overlay_theme()
        assert light["bg"] == "#ffffff" and light["border"] == "#000000"
        assert light["text"] == "#000000"
        selection_button.get_ui_theme = lambda: "dark"
        dark = overlay_theme()
        assert dark["bg"] == "#000000" and dark["border"] == "#ffffff"
        assert dark["text"] == "#ffffff"
        window = tk.Toplevel(root)
        _style_overlay_window(window)
        assert float(window.attributes("-alpha")) == 1.0
        window.destroy()
    finally:
        selection_button.get_ui_theme = original
        root.destroy()
    print("overlay-theme: ok")


def test_direction() -> None:
    """Проверяет выбор направления перевода по языку текста."""
    source, target = choose_selection_direction("Hello world", {"en", "ru"})
    assert (source, target) == ("en", "ru"), (source, target)
    source, target = choose_selection_direction("Привет мир, это проверка")
    assert (source, target) == ("ru", "en"), (source, target)
    print("direction: ok")


def test_should_capture_selection() -> None:
    """Клики фокуса и перетаскивание окна не считаются выделением."""
    if should_capture_selection(True, False, 4, 0.05, False):
        raise AssertionError("Клик для фокуса сработал как выделение")
    if should_capture_selection(False, False, 80, 0.5, False):
        raise AssertionError("Перетаскивание за заголовок сработало как выделение")
    if should_capture_selection(True, True, 80, 0.5, False):
        raise AssertionError("Движение окна сработало как выделение")
    if not should_capture_selection(True, False, 30, 0.25, False):
        raise AssertionError("Настоящее выделение не распознано")
    if not should_capture_selection(True, False, 2, 0.05, True):
        raise AssertionError("Двойной клик по слову не распознан")
    print("gesture: ok")


def test_ctrl_activation_rules() -> None:
    """Проверяет режим кнопки с Ctrl и распознавание Ctrl+C+C."""
    assert should_show_selection_button(False, False)
    assert should_show_selection_button(True, True)
    assert not should_show_selection_button(True, False)
    assert should_show_selection_button(False, False, "none")
    assert should_show_selection_button(False, False, "alt", alt_pressed=True)
    assert not should_show_selection_button(
        False, True, "alt", alt_pressed=False
    )
    assert should_show_selection_button(
        False, False, "shift", shift_pressed=True
    )
    assert should_skip_selection_copy(True, False)
    assert should_skip_selection_copy(False, True)
    assert not should_skip_selection_copy(False, False)

    assert should_trigger_double_ctrl_c(10.0, 10.5, True, True)
    assert not should_trigger_double_ctrl_c(10.0, 10.8, True, True)
    assert not should_trigger_double_ctrl_c(10.0, 10.5, False, True)
    assert not should_trigger_double_ctrl_c(10.0, 10.5, True, False)
    assert not should_trigger_double_ctrl_c(0.0, 10.5, True, True)
    print("ctrl-activation: ok")


def test_clipboard_shortcut_translation() -> None:
    """Ctrl+C+C берёт выделение из буфера и сразу запускает перевод."""
    previous_clipboard = pyperclip.paste() or ""
    root = tk.Tk()
    root.withdraw()
    popup = SelectionPopup(root, lambda text: (f"Перевод: {text}", "en", "ru"))
    try:
        pyperclip.copy("Hello shortcut")
        popup._translate_clipboard_selection()
        deadline = time.time() + 5
        while time.time() < deadline:
            root.update()
            if popup._result_window is not None:
                break
            time.sleep(0.05)
        if popup._result_window is None:
            raise AssertionError("Ctrl+C+C не запустил перевод из буфера")
        assert popup._selected_text == "Hello shortcut"
    finally:
        popup.stop()
        root.destroy()
        pyperclip.copy(previous_clipboard)
    print("clipboard-shortcut: ok")


def test_popup_button() -> None:
    """Проверяет, что кнопка появляется и показывает результат."""
    root = tk.Tk()
    root.withdraw()
    popup = SelectionPopup(root, lambda text: ("Привет, мир", "en", "ru"))
    popup.show_button("Hello world", 80, 80)
    root.update()
    geometry = popup._button_window.geometry()
    if not geometry.endswith("+60+60"):
        raise AssertionError(f"Иконка не под курсором: {geometry}")
    if popup._translate_button is None:
        raise AssertionError("Иконка Recycling не появилась")
    if not str(popup._translate_button.cget("image")):
        raise AssertionError("На кнопке нет картинки Recycling")
    popup._on_translate_click()
    deadline = time.time() + 5
    while time.time() < deadline:
        root.update()
        if popup._result_window is not None:
            break
        time.sleep(0.05)
    if popup._result_window is None:
        raise AssertionError("Окно результата не появилось")
    popup.stop()
    root.destroy()
    print("popup: ok")


def test_result_closes_on_click() -> None:
    """Окно перевода закрывается по клику, кнопка «Копировать» его не закрывает."""
    original_get_mode = selection_button.get_result_window_mode
    selection_button.get_result_window_mode = lambda: RESULT_WINDOW_CLICK_TO_CLOSE
    root = tk.Tk()
    root.withdraw()
    popup = SelectionPopup(root, lambda text: ("Привет, мир", "en", "ru"))
    try:
        popup.show_button("Hello world", 80, 80)
        root.update()
        popup._on_translate_click()
        deadline = time.time() + 5
        while time.time() < deadline:
            root.update()
            if popup._result_window is not None:
                break
            time.sleep(0.05)
        if popup._result_window is None:
            raise AssertionError("Окно результата не появилось")

        copy_button = popup._copy_button
        if copy_button is None:
            raise AssertionError("Кнопка «Копировать» не найдена")
        copy_button.invoke()
        root.update()
        if popup._result_window is None:
            raise AssertionError("Окно закрылось по кнопке «Копировать»")

        popup._result_window.event_generate("<Button-1>")
        root.update()
        if popup._result_window is not None:
            raise AssertionError("Окно не закрылось по клику")
    finally:
        selection_button.get_result_window_mode = original_get_mode
        popup.stop()
        root.destroy()
    print("close-on-click: ok")


def test_selectable_result_mode() -> None:
    """В режиме выделения копируется фрагмент, а окно закрывается кнопкой."""
    original_get_mode = selection_button.get_result_window_mode
    previous_clipboard = pyperclip.paste() or ""
    selection_button.get_result_window_mode = lambda: RESULT_WINDOW_SELECTABLE
    root = tk.Tk()
    root.withdraw()
    popup = SelectionPopup(root, lambda text: ("Привет, мир", "en", "ru"))
    try:
        popup._show_result("Первое второе третье", "ru", "en")
        root.update()
        if popup._result_text is None or popup._close_button is None:
            raise AssertionError("Режим выделения не создал текст и кнопку закрытия")

        popup._result_window.event_generate("<Button-1>")
        root.update()
        if popup._result_window is None:
            raise AssertionError("Окно закрылось по клику в режиме выделения")

        popup._result_text.tag_add("sel", "1.7", "1.13")
        popup._copy_button.invoke()
        assert pyperclip.paste() == "второе"

        popup._close_button.invoke()
        root.update()
        if popup._result_window is not None:
            raise AssertionError("Кнопка «Закрыть» не закрыла окно")
    finally:
        selection_button.get_result_window_mode = original_get_mode
        popup.stop()
        root.destroy()
        pyperclip.copy(previous_clipboard)
    print("selectable-result: ok")


def test_real_translate() -> None:
    """Проверяет оффлайн-перевод выделенного текста."""
    from packages import get_installed_pairs, is_package_installed
    from translation_engine import get_engine

    pairs = get_installed_pairs()
    codes = sorted({code for pair in pairs for code in pair[:2]})
    print("installed language codes:", codes)
    if "en" not in codes or "ru" not in codes:
        print("translate: нет en/ru, пропуск")
        return

    engine = get_engine()
    hello = "Hello world"
    source, target = choose_selection_direction(hello, {"en", "ru"})
    translated = engine.translate(hello, source, target)
    print(f"en: {hello!r} -> {translated!r}")
    lowered = translated.lower()
    if "привет" not in lowered and "здравствуй" not in lowered:
        raise AssertionError(f"Неожиданный перевод EN: {translated}")

    russian = "Привет мир"
    source, target = choose_selection_direction(russian)
    if not is_package_installed("ru", "en"):
        print("ru->en: пакет не установлен, пропуск")
        return
    translated = engine.translate(russian, source, target)
    print(f"ru: {russian!r} -> {translated!r}")
    if not translated.strip():
        raise AssertionError("Пустой перевод RU")
    print("translate: ok")


if __name__ == "__main__":
    test_recycle_icon_file()
    test_icon_center_is_clickable()
    test_overlay_theme_opaque()
    test_direction()
    test_should_capture_selection()
    test_ctrl_activation_rules()
    test_clipboard_shortcut_translation()
    test_popup_button()
    test_result_closes_on_click()
    test_selectable_result_mode()
    test_real_translate()
    print("Все проверки прошли")
