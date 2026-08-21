from autostart import (
    APP_VALUE_NAME,
    get_autostart_command,
    get_autostart_value,
    is_autostart_enabled,
    set_autostart,
)


def test_autostart_command() -> None:
    """Команда автозапуска должна вызывать py -3.13 и main.py."""
    command = get_autostart_command()
    assert "-3.13" in command, command
    assert "main.py" in command, command
    print(f"command: {command}")


def test_autostart_registry() -> None:
    """Проверяет запись и удаление ключа автозагрузки, затем восстанавливает его."""
    previous = get_autostart_value()
    try:
        set_autostart(True)
        if not is_autostart_enabled():
            raise AssertionError("Автозагрузка не включилась")
        value = get_autostart_value()
        if value != get_autostart_command():
            raise AssertionError(f"Неверная команда в реестре: {value}")
        set_autostart(False)
        if is_autostart_enabled():
            raise AssertionError("Автозагрузка не выключилась")
        print("registry: ok")
    finally:
        if previous is None:
            set_autostart(False)
        else:
            import winreg

            from autostart import RUN_KEY

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(key, APP_VALUE_NAME, 0, winreg.REG_SZ, previous)


if __name__ == "__main__":
    test_autostart_command()
    test_autostart_registry()
    print("Все проверки прошли")
