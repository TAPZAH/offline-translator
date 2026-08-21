import time
import tkinter as tk

from PIL import Image

from selection_button import (
    ICON_SIZE,
    SELECTION_ICON_PATH,
    TRAY_ICON_PATH,
    SelectionPopup,
    _flatten_icon_for_window,
    choose_selection_direction,
    should_capture_selection,
)


def test_recycle_icon_file() -> None:
    """Проверяет, что иконки выделения и трея квадратные."""
    for path in (SELECTION_ICON_PATH, TRAY_ICON_PATH):
        image = Image.open(path)
        width, height = image.size
        assert width == height, (path, width, height)
        assert width >= 32
        print(f"icon: ok {path} {width}x{height}")


def test_icon_center_is_clickable() -> None:
    """Центр знака не должен быть цветом-ключом, иначе клик проваливается."""
    image = Image.open(SELECTION_ICON_PATH).convert("RGBA")
    image = image.resize((ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS)
    flattened = _flatten_icon_for_window(image)
    center = flattened.getpixel((ICON_SIZE // 2, ICON_SIZE // 2))
    if center == (255, 0, 255):
        raise AssertionError("Центр иконки прозрачный — клик провалится")
    print(f"icon-center: ok {center}")


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
    root = tk.Tk()
    root.withdraw()
    popup = SelectionPopup(root, lambda text: ("Привет, мир", "en", "ru"))
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
    popup.stop()
    root.destroy()
    print("close-on-click: ok")


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
    test_direction()
    test_should_capture_selection()
    test_popup_button()
    test_result_closes_on_click()
    test_real_translate()
    print("Все проверки прошли")
