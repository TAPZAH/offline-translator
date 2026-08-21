from language_packages import LanguagePackage


def get_installed_pairs() -> list[tuple[str, str, str, str]]:
    """Установленные пары текущего движка."""
    return _backend().get_installed_pairs()


def get_available_pairs(architecture: str | None = None) -> list[LanguagePackage]:
    """Пакеты, доступные для скачивания в текущем движке."""
    return _backend().get_available_pairs(architecture)


def is_package_installed(
    from_code: str, to_code: str, architecture: str | None = None
) -> bool:
    """Проверяет, установлен ли пакет в текущем движке."""
    return _backend().is_package_installed(from_code, to_code, architecture)


def get_installed_architectures(from_code: str, to_code: str) -> list[str]:
    """Какие варианты модели стоят для пары в текущем движке."""
    return _backend().get_installed_architectures(from_code, to_code)


def update_remote_index() -> None:
    """Обновляет каталог пакетов текущего движка."""
    _backend().update_remote_index()


def download_and_install(language_package, progress_callback=None) -> None:
    """Скачивает языковой пакет текущего движка."""
    _backend().download_and_install(language_package, progress_callback)


def needed_pairs_for_path(from_code: str, to_code: str) -> list[tuple[str, str]]:
    """Какие пакеты нужны для прямого или двойного перевода."""
    backend = _backend()
    custom = getattr(backend, "needed_pairs_for_path", None)
    if callable(custom):
        return custom(from_code, to_code)
    if from_code == to_code:
        return []
    if is_package_installed(from_code, to_code):
        return []
    if from_code == "en" or to_code == "en":
        return [(from_code, to_code)]
    needed: list[tuple[str, str]] = []
    if not is_package_installed(from_code, "en"):
        needed.append((from_code, "en"))
    if not is_package_installed("en", to_code):
        needed.append(("en", to_code))
    return needed


def _backend():
    """Модуль пакетов выбранного движка."""
    from app_settings import ENGINE_ARGOS, ENGINE_NLLB, get_engine_name

    engine = get_engine_name()
    if engine == ENGINE_ARGOS:
        import argos_packages as backend
    elif engine == ENGINE_NLLB:
        import nllb_packages as backend
    else:
        import language_packages as backend
    return backend
