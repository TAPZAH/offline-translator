"""Версия приложения для окна, установщика и GitHub."""

APP_NAME = "Оффлайн Переводчик"
APP_VERSION = "0.995-beta"
APP_VERSION_DISPLAY = "beta 0.995"
APP_VERSION_INFO = "0.995.0.0"
APP_PUBLISHER = "TAP3AH"


def window_title() -> str:
    """Заголовок главного окна с номером версии."""
    return f"{APP_NAME} {APP_VERSION_DISPLAY}"
