"""Собирает портативные zip, исходники и (если есть Inno Setup) установщик."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from PIL import Image

from app_version import APP_NAME, APP_VERSION, APP_VERSION_DISPLAY

ROOT = Path(__file__).resolve().parent
DIST_NAME = "OfflineTranslator"
DIST_DIR = ROOT / "dist" / DIST_NAME
LITE_DIR = ROOT / "dist" / "offline-translator-portable-lite"
FULL_DIR = ROOT / "dist" / "offline-translator-portable-full"
RELEASE_DIR = ROOT / "release"
ARGOS_PACKAGES = Path.home() / ".local" / "share" / "argos-translate" / "packages"
NLLB_MODELS = (
    Path.home() / ".local" / "share" / "offline-translator" / "nllb-200"
)
NLLB_MODEL_BIN = NLLB_MODELS / "nllb-200-distilled-600M" / "model.bin"
ISCC_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
)
SOURCE_EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "release",
    "installer-dist",
    ".cursor",
    ".pytest_cache",
    "installer-output",
    "target",
    "vcpkg_installed",
}

SOURCE_EXCLUDE_PREFIXES = (
    "build-",
    "portable-win32",
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


def _has_model_bin(root: Path) -> bool:
    """Проверяет, что в каталоге есть хотя бы одна model.bin."""
    return root.is_dir() and any(root.rglob("model.bin"))


def _copy_tree(source: Path, target: Path, ignore=None) -> None:
    """Копирует каталог моделей, затирая предыдущую копию."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=ignore)


def _reset_dir(target: Path) -> None:
    """Удаляет папку и копирует в неё свежий вывод PyInstaller."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(DIST_DIR, target)


def copy_language_packages(portable_dir: Path) -> dict[str, bool]:
    """Кладёт оффлайн-модели рядом с exe."""
    bundled = {"argos": False, "nllb": False}
    data_dir = portable_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    if _has_model_bin(ARGOS_PACKAGES):
        _copy_tree(
            ARGOS_PACKAGES,
            data_dir / "argos-packages",
            ignore=shutil.ignore_patterns("stanza"),
        )
        bundled["argos"] = True
        print("Скопированы пакеты Argos")
    else:
        print(f"Нет пакетов Argos: {ARGOS_PACKAGES}")

    if NLLB_MODEL_BIN.is_file():
        _copy_tree(
            NLLB_MODELS,
            data_dir / "nllb-200",
            ignore=shutil.ignore_patterns("_downloads"),
        )
        bundled["nllb"] = True
        print("Скопирована модель NLLB-200")
    else:
        print("Модель NLLB-200 не установлена, в сборку с моделями не входит")

    return bundled


def write_portable_settings(portable_dir: Path, bundled: dict[str, bool] | None) -> None:
    """Пишет настройки для портативной копии."""
    data_dir = portable_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    if bundled:
        if bundled.get("argos"):
            engine = "argos"
        elif bundled.get("nllb"):
            engine = "nllb"
        else:
            engine = "argos"
        architecture = "base"
    else:
        engine = "argos"
        architecture = "tiny"
    settings = {
        "engine": engine,
        "architecture": architecture,
    }
    (data_dir / "settings.json").write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_readme(portable_dir: Path, with_models: bool) -> None:
    """Краткая инструкция внутри архива."""
    if with_models:
        extra = (
            "В папке data уже лежат языковые модели (Argos"
            + (", NLLB-200" if NLLB_MODEL_BIN.is_file() else "")
            + "). Интернет для первого перевода не нужен.\n"
        )
    else:
        extra = (
            "Языковые модели в эту сборку не входят. "
            "Откройте «Языки...» и скачайте нужные пакеты (нужен интернет).\n"
        )
    text = (
        f"{APP_NAME} — портативная версия {APP_VERSION_DISPLAY}\n"
        "\n"
        "Распакуйте архив в любую папку и откройте OfflineTranslator.exe.\n"
        "Python для запуска не нужен. Подходят Windows 10 и 11, 64-bit.\n"
        "\n"
        f"{extra}"
        "Не удаляйте папки _internal и data.\n"
        "Движок (Argos или NLLB-200) переключается в «Настройки...».\n"
        "Автозагрузка включается в «Настройки...».\n"
        "\n"
        "Ошибки пишутся в data\\error.log\n"
    )
    (portable_dir / "Прочитайте.txt").write_text(text, encoding="utf-8")


def zip_directory(source_dir: Path, archive_path: Path) -> None:
    """Упаковывает папку в zip с именем верхнего каталога внутри архива."""
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()
    parent = source_dir.parent
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(parent))
    size_mb = archive_path.stat().st_size / 1024 / 1024
    print(f"Архив: {archive_path} ({size_mb:.1f} МБ)")


def pack_sources(archive_path: Path) -> None:
    """Упаковывает исходники без сборок и кэша."""
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()
    prefix = f"offline-translator-{APP_VERSION}"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in ROOT.rglob("*"):
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(ROOT)
            if any(part in SOURCE_EXCLUDE_DIRS for part in relative.parts):
                continue
            if any(
                part.startswith(prefix)
                for part in relative.parts
                for prefix in SOURCE_EXCLUDE_PREFIXES
            ):
                continue
            if relative.suffix.lower() in {".zip", ".pyc"}:
                continue
            archive.write(file_path, Path(prefix) / relative)
    size_mb = archive_path.stat().st_size / 1024 / 1024
    print(f"Исходники: {archive_path} ({size_mb:.1f} МБ)")


def find_iscc() -> Path | None:
    """Ищет компилятор Inno Setup."""
    for path in ISCC_CANDIDATES:
        if path.is_file():
            return path
    found = shutil.which("iscc")
    if found:
        return Path(found)
    return None


def build_installer() -> None:
    """Собирает установщик из облегчённой портативной папки."""
    iscc = find_iscc()
    if iscc is None:
        print(
            "Inno Setup не найден. Установщик не собран. "
            "Установите Inno Setup 6 и повторите: py -3.13 build_portable.py --skip-pyinstaller"
        )
        return
    subprocess.run(
        [str(iscc), str(ROOT / "OfflineTranslator.iss")],
        check=True,
        cwd=str(ROOT),
    )
    setup = RELEASE_DIR / f"offline-translator-{APP_VERSION}-setup.exe"
    if setup.is_file():
        size_mb = setup.stat().st_size / 1024 / 1024
        print(f"Установщик: {setup} ({size_mb:.1f} МБ)")


def parse_args() -> argparse.Namespace:
    """Разбирает флаги сборки."""
    parser = argparse.ArgumentParser(description="Сборка портативных поставок")
    parser.add_argument(
        "--skip-pyinstaller",
        action="store_true",
        help="Не пересобирать exe, только упаковать уже готовый dist",
    )
    parser.add_argument(
        "--skip-full",
        action="store_true",
        help="Не собирать архив с языковыми моделями",
    )
    return parser.parse_args()


def main() -> None:
    """Собирает поставки для GitHub и полный портатив с моделями."""
    args = parse_args()
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    create_app_icon()
    if not args.skip_pyinstaller:
        run_pyinstaller()
    if not DIST_DIR.is_dir():
        raise RuntimeError(f"PyInstaller не создал {DIST_DIR}")

    print("=== Сборка без моделей (GitHub) ===")
    _reset_dir(LITE_DIR)
    write_portable_settings(LITE_DIR, bundled=None)
    write_readme(LITE_DIR, with_models=False)
    zip_directory(
        LITE_DIR,
        RELEASE_DIR / f"offline-translator-{APP_VERSION}-portable.zip",
    )

    if not args.skip_full:
        print("=== Сборка с языковыми моделями ===")
        _reset_dir(FULL_DIR)
        bundled = copy_language_packages(FULL_DIR)
        write_portable_settings(FULL_DIR, bundled)
        write_readme(FULL_DIR, with_models=True)
        zip_directory(
            FULL_DIR,
            RELEASE_DIR / f"offline-translator-{APP_VERSION}-portable-with-models.zip",
        )

    print("=== Исходники ===")
    pack_sources(RELEASE_DIR / f"offline-translator-{APP_VERSION}-src.zip")

    print("=== Установщик ===")
    build_installer()
    print(f"Готово. Версия {APP_NAME} {APP_VERSION_DISPLAY}. Файлы в {RELEASE_DIR}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Ошибка сборки: {error}", file=sys.stderr)
        sys.exit(1)
