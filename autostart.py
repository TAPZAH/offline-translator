import os
import shutil
import sys
import winreg

import portable_env

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_VALUE_NAME = "OfflineTranslator"


def get_main_script_path() -> str:
    """Возвращает абсолютный путь к главному скрипту или exe."""
    if portable_env.is_frozen():
        return os.path.abspath(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))


def get_launcher_path() -> str:
    """Ищет pyw, чтобы при входе в Windows не мелькало консольное окно."""
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    pyw_in_windows = os.path.join(system_root, "pyw.exe")
    if os.path.isfile(pyw_in_windows):
        return pyw_in_windows
    found_pyw = shutil.which("pyw")
    if found_pyw:
        return found_pyw
    found_py = shutil.which("py")
    if found_py:
        return found_py
    raise RuntimeError("Не найден запускатель pyw.exe / py.exe")


def get_autostart_command() -> str:
    """Собирает команду автозапуска для исходников или портативного exe."""
    if portable_env.is_frozen():
        return f'"{get_main_script_path()}" --minimized'
    launcher = get_launcher_path()
    script = get_main_script_path()
    return f'"{launcher}" -3.13 "{script}" --minimized'


def get_autostart_value() -> str | None:
    """Читает команду автозагрузки из реестра или None, если записи нет."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_VALUE_NAME)
            if isinstance(value, str) and value.strip():
                return value
            return None
    except FileNotFoundError:
        return None
    except OSError:
        return None


def is_autostart_enabled() -> bool:
    """Проверяет, стоит ли программа в автозагрузке текущего пользователя."""
    return get_autostart_value() is not None


def set_autostart(enabled: bool) -> None:
    """Включает или выключает автозагрузку в реестре текущего пользователя."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key,
                    APP_VALUE_NAME,
                    0,
                    winreg.REG_SZ,
                    get_autostart_command(),
                )
                return
            try:
                winreg.DeleteValue(key, APP_VALUE_NAME)
            except FileNotFoundError:
                pass
    except OSError as error:
        raise RuntimeError(f"Не удалось изменить автозагрузку: {error}") from error
