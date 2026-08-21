import pyperclip
from language_packages import get_installed_pairs
import keyboard


def test_pyperclip() -> None:
    """Проверяет копирование и чтение текста из буфера обмена."""
    try:
        test_text = "Тест"
        pyperclip.copy(test_text)
        clipboard_text = pyperclip.paste()
        print(f"pyperclip: скопировано и прочитано — {clipboard_text!r}")
    except Exception as error:
        print(f"pyperclip: ошибка — {error}")


def test_firefox_models() -> None:
    """Выводит список установленных языковых пакетов Firefox."""
    try:
        packages = get_installed_pairs()
        if not packages:
            print("firefox: языковые пакеты не установлены")
            return

        print("firefox: доступные языковые пакеты:")
        for from_code, to_code, _from_name, _to_name in packages:
            print(f"  {from_code} -> {to_code}")
    except Exception as error:
        print(f"firefox: ошибка — {error}")


def test_keyboard() -> None:
    """Проверяет, что библиотека горячих клавиш импортируется."""
    try:
        if keyboard:
            print("Горячие клавиши доступны")
    except Exception as error:
        print(f"keyboard: ошибка — {error}")


def main() -> None:
    """Запускает проверки библиотек."""
    test_pyperclip()
    test_firefox_models()
    test_keyboard()


if __name__ == "__main__":
    main()
