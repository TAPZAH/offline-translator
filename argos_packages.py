from language_detect import language_display_name
from language_packages import LanguagePackage
from translation_route import needed_english_pivot_pairs

_installed_pairs_cache: list[tuple[str, str, str, str]] | None = None
_installed_pair_set: set[tuple[str, str]] | None = None


def invalidate_cache() -> None:
    """Сбрасывает кэш установленных пар Argos."""
    global _installed_pairs_cache, _installed_pair_set
    _installed_pairs_cache = None
    _installed_pair_set = None


def get_installed_pairs() -> list[tuple[str, str, str, str]]:
    """Возвращает установленные пары Argos Translate."""
    global _installed_pairs_cache, _installed_pair_set
    if _installed_pairs_cache is not None:
        return _installed_pairs_cache
    pairs: list[tuple[str, str, str, str]] = []
    try:
        from argostranslate import package

        for item in package.get_installed_packages():
            if getattr(item, "type", "translate") != "translate":
                continue
            from_code = item.from_code
            to_code = item.to_code
            if not from_code or not to_code:
                continue
            pairs.append(
                (
                    from_code,
                    to_code,
                    language_display_name(from_code, item.from_name or from_code),
                    language_display_name(to_code, item.to_name or to_code),
                )
            )
    except Exception:
        _installed_pairs_cache = []
        _installed_pair_set = set()
        return _installed_pairs_cache
    pairs.sort(key=lambda item: (item[0], item[1]))
    _installed_pairs_cache = pairs
    _installed_pair_set = {(from_code, to_code) for from_code, to_code, *_ in pairs}
    return pairs


def is_package_installed(
    from_code: str, to_code: str, architecture: str | None = None
) -> bool:
    """Проверяет, установлен ли пакет Argos."""
    try:
        if _installed_pair_set is None:
            get_installed_pairs()
        return (from_code, to_code) in (_installed_pair_set or ())
    except Exception:
        return False


def needed_pairs_for_path(from_code: str, to_code: str) -> list[tuple[str, str]]:
    """Какие пакеты Argos нужны для прямого или двойного перевода."""
    return needed_english_pivot_pairs(from_code, to_code, is_package_installed)


def get_installed_architectures(from_code: str, to_code: str) -> list[str]:
    """Argos не делит модели на tiny/base."""
    if is_package_installed(from_code, to_code):
        return ["argos"]
    return []


def update_remote_index() -> None:
    """Обновляет индекс пакетов Argos."""
    from argostranslate import package

    package.update_package_index()


def get_available_pairs(architecture: str | None = None) -> list[LanguagePackage]:
    """Список пакетов Argos, которые можно скачать."""
    try:
        from argostranslate import package

        packages: list[LanguagePackage] = []
        for item in package.get_available_packages():
            if getattr(item, "type", "translate") != "translate":
                continue
            from_code = item.from_code
            to_code = item.to_code
            if not from_code or not to_code:
                continue
            packages.append(
                LanguagePackage(
                    from_code=from_code,
                    to_code=to_code,
                    from_name=language_display_name(
                        from_code, item.from_name or from_code
                    ),
                    to_name=language_display_name(to_code, item.to_name or to_code),
                    dirname="",
                    architecture="argos",
                    argos_package=item,
                )
            )
        return packages
    except Exception:
        return []


def download_and_install(language_package, progress_callback=None) -> None:
    """Скачивает и устанавливает пакет Argos Translate."""
    from_code = language_package.from_code
    to_code = language_package.to_code
    if is_package_installed(from_code, to_code):
        if progress_callback:
            progress_callback(1, 1, "Пакет уже установлен")
        return

    argos_package = getattr(language_package, "argos_package", None)
    if argos_package is None:
        for item in get_available_pairs():
            if item.from_code == from_code and item.to_code == to_code:
                argos_package = item.argos_package
                break
    if argos_package is None:
        try:
            update_remote_index()
        except Exception:
            pass
        for item in get_available_pairs():
            if item.from_code == from_code and item.to_code == to_code:
                argos_package = item.argos_package
                break
    if argos_package is None:
        raise RuntimeError("Пакет Argos не найден в каталоге")

    from argostranslate import package
    from argostranslate.translate import get_installed_languages

    if progress_callback:
        progress_callback(0, 1, "Скачиваю пакет Argos...")
    download_path = argos_package.download()
    if progress_callback:
        progress_callback(1, 1, "Устанавливаю пакет Argos...")
    package.install_from_path(download_path)
    try:
        download_path.unlink()
    except Exception:
        pass
    try:
        get_installed_languages.cache_clear()
    except Exception:
        pass
    invalidate_cache()
    if not is_package_installed(from_code, to_code):
        raise RuntimeError("Пакет Argos скачан, но не найден среди установленных")
