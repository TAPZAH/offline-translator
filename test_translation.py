from packages import is_package_installed
from translation_engine import get_engine


def main() -> None:
    """Переводит тестовую фразу с английского на русский."""
    try:
        if not is_package_installed("en", "ru"):
            print("Нет пакета en→ru. Сначала запустите download_model.py")
            return
        original_text = "Hello world"
        translated_text = get_engine().translate(original_text, "en", "ru")
        print(f"Оригинал: {original_text} -> Перевод: {translated_text}")
    except Exception as error:
        print(f"Ошибка перевода: {error}")


if __name__ == "__main__":
    main()
