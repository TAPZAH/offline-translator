import os
import sys


def is_frozen() -> bool:
    """Проверяет, запущена ли программа как собранный exe."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> str:
    """Папка с exe или с исходниками."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_dir() -> str:
    """Папка ресурсов: у PyInstaller это _MEIPASS, иначе каталог проекта."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", app_dir())
    return os.path.dirname(os.path.abspath(__file__))


def apply() -> None:
    """Для портативной сборки складывает модели Firefox рядом с exe."""
    if not is_frozen():
        return
    data_home = os.path.join(app_dir(), "data")
    os.makedirs(data_home, exist_ok=True)
    os.environ.setdefault("XDG_DATA_HOME", data_home)
    os.environ.setdefault("XDG_CACHE_HOME", os.path.join(data_home, "cache"))
    os.environ.setdefault("XDG_CONFIG_HOME", os.path.join(data_home, "config"))
    os.environ.setdefault(
        "OFFLINE_TRANSLATOR_MODELS",
        os.path.join(data_home, "firefox-models"),
    )
