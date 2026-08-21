from language_packages import LanguagePackage
from translation_route import needed_english_pivot_pairs

_cached_backend = None
_cached_engine_name = None


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
    invalidate_caches()


def needed_pairs_for_path(from_code: str, to_code: str) -> list[tuple[str, str]]:
    """Какие пакеты нужны для прямого или двойного перевода."""
    backend = _backend()
    custom = getattr(backend, "needed_pairs_for_path", None)
    if callable(custom):
        return custom(from_code, to_code)
    return needed_english_pivot_pairs(from_code, to_code, is_package_installed)


def invalidate_caches() -> None:
    """Сбрасывает кэш списков пакетов всех движков."""
    for module_name in ("language_packages", "argos_packages", "nllb_packages"):
        try:
            module = __import__(module_name)
            invalidate = getattr(module, "invalidate_cache", None)
            if callable(invalidate):
                invalidate()
        except Exception:
            pass


def _backend():
    """Модуль пакетов выбранного движка."""
    global _cached_backend, _cached_engine_name
    from app_settings import ENGINE_ARGOS, ENGINE_NLLB, get_engine_name

    engine = get_engine_name()
    if _cached_backend is not None and _cached_engine_name == engine:
        return _cached_backend
    if engine == ENGINE_ARGOS:
        import argos_packages as backend
    elif engine == ENGINE_NLLB:
        import nllb_packages as backend
    else:
        import language_packages as backend
    _cached_backend = backend
    _cached_engine_name = engine
    return backend
