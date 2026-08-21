import sys

from app_settings import engine_label, get_engine_name
from packages import download_and_install, get_available_pairs, is_package_installed, update_remote_index

FROM_CODE = "en"
TO_CODE = "ru"


def find_available_package(from_code: str, to_code: str):
    """Ищет пакет в каталоге текущего движка."""
    try:
        update_remote_index()
    except Exception:
        pass
    for language_package in get_available_pairs():
        if (
            language_package.from_code == from_code
            and language_package.to_code == to_code
        ):
            return language_package
    return None


def install_pair(from_code: str, to_code: str, label: str) -> None:
    """Скачивает одну языковую пару, если её ещё нет."""
    if is_package_installed(from_code, to_code):
        print(f"Пакет {label} уже установлен и доступен")
        return

    language_package = find_available_package(from_code, to_code)
    if language_package is None:
        print(f"Пакет {label} не найден в каталоге {engine_label(get_engine_name())}")
        sys.exit(1)

    print(f"Найден пакет: {language_package.from_code} -> {language_package.to_code}")

    def on_progress(downloaded: int, total: int, message: str) -> None:
        if total:
            percent = min(100, downloaded * 100 / total)
            print(f"\r{message} {percent:.0f}%", end="", flush=True)
        else:
            print(f"\r{message}", end="", flush=True)

    download_and_install(language_package, on_progress)
    print()
    if is_package_installed(from_code, to_code):
        print(f"Пакет {label} успешно установлен и доступен")
    else:
        print(f"Пакет {label} скачан, но не найден среди установленных")
        sys.exit(1)


def main() -> None:
    """Скачивает пакеты текущего движка: пары en↔ru или модель NLLB."""
    try:
        from app_settings import ENGINE_NLLB

        if get_engine_name() == ENGINE_NLLB:
            install_pair("nllb", "all", "NLLB-200 Distilled 600M")
            return
        install_pair(FROM_CODE, TO_CODE, "English -> Russian")
        install_pair(TO_CODE, FROM_CODE, "Russian -> English")
    except Exception as error:
        print(f"Ошибка загрузки модели: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
