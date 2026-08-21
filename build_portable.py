"""Собирает портативную папку и zip-архив для Windows 10/11."""

import os
import shutil
import sys
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
DIST_NAME = "OfflineTranslator"
DIST_DIR = ROOT / "dist" / DIST_NAME
PORTABLE_DIR = ROOT / "dist" / "offline-translator-portable"
ARCHIVE_PATH = ROOT / "offline-translator-portable.zip"
FIREFOX_MODELS = (
    Path.home() / ".local" / "share" / "offline-translator" / "firefox-models"
)


def create_app_icon() -> None:
    """Делает .ico для ярлыка exe."""
    source = ROOT / "assets" / "icon-tray.png"
    target = ROOT / "assets" / "app.ico"
    image = Image.open(source).convert("RGBA")
    image.save(target, format="ICO", sizes=[(16, 16), (32, 32), (64, 64), (256, 256)])


def run_pyinstaller() -> None:
    """Запускает PyInstaller по spec-файлу."""
    import PyInstaller.__main__

    PyInstaller.__main__.run(
        [
            str(ROOT / "OfflineTranslator.spec"),
            "--noconfirm",
            "--clean",
        ]
    )


def copy_language_packages() -> None:
    """Кладёт оффлайн-модели Firefox рядом с exe."""
    if not FIREFOX_MODELS.is_dir():
        raise RuntimeError(f"Нет языковых пакетов: {FIREFOX_MODELS}")
    target = PORTABLE_DIR / "data" / "firefox-models"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        FIREFOX_MODELS,
        target,
        ignore=shutil.ignore_patterns("_downloads"),
    )


def write_readme() -> None:
    """Краткая инструкция внутри архива."""
    text = (
        "Оффлайн Переводчик — портативная версия\n"
        "\n"
        "Запуск: откройте OfflineTranslator.exe\n"
        "Программа стартует в системном трее. Python устанавливать не нужно.\n"
        "Нужны Windows 10 или 11, 64-bit.\n"
        "\n"
        "Не удаляйте папки _internal и data — в них движок и языковые модели.\n"
        "Дополнительные языки можно скачать в окне «Языки...».\n"
    )
    (PORTABLE_DIR / "Прочитайте.txt").write_text(text, encoding="utf-8")


def make_archive() -> None:
    """Упаковывает папку в zip."""
    if ARCHIVE_PATH.exists():
        ARCHIVE_PATH.unlink()
    with zipfile.ZipFile(ARCHIVE_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in PORTABLE_DIR.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(PORTABLE_DIR.parent))


def main() -> None:
    """Собирает портативную поставку."""
    create_app_icon()
    run_pyinstaller()
    if not DIST_DIR.is_dir():
        raise RuntimeError(f"PyInstaller не создал {DIST_DIR}")
    if PORTABLE_DIR.exists():
        shutil.rmtree(PORTABLE_DIR)
    shutil.copytree(DIST_DIR, PORTABLE_DIR)
    copy_language_packages()
    write_readme()
    make_archive()
    size_mb = ARCHIVE_PATH.stat().st_size / 1024 / 1024
    print(f"Готово: {ARCHIVE_PATH} ({size_mb:.1f} МБ)")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Ошибка сборки: {error}", file=sys.stderr)
        sys.exit(1)
