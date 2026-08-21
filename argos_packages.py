from language_detect import language_display_name
from language_packages import LanguagePackage


def get_installed_pairs() -> list[tuple[str, str, str, str]]:
    """Возвращает установленные пары Argos Translate."""
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
        return []
    return sorted(pairs, key=lambda item: (item[0], item[1]))


def is_package_installed(
    from_code: str, to_code: str, architecture: str | None = None
) -> bool:
    """Проверяет, установлен ли пакет Argos."""
    try:
        for installed_from, installed_to, *_rest in get_installed_pairs():
            if installed_from == from_code and installed_to == to_code:
                return True
    except Exception:
        return False
    return False


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
    if not is_package_installed(from_code, to_code):
        raise RuntimeError("Пакет Argos скачан, но не найден среди установленных")
