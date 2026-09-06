import shutil
from pathlib import Path

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


def _iter_installed_packages():
    """Обходит установленные пакеты Argos, пропуская служебные каталоги.

    argostranslate.package.get_installed_packages() падает целиком, если
    рядом лежит _downloads или любая папка без metadata.json.
    """
    from argostranslate import package, settings

    roots = list(getattr(settings, "package_dirs", None) or [])
    if not roots:
        package_dir = getattr(settings, "package_data_dir", None)
        if package_dir is not None:
            roots = [package_dir]
    for root in roots:
        directory = Path(root)
        if not directory.is_dir():
            continue
        try:
            children = list(directory.iterdir())
        except OSError:
            continue
        for path in children:
            if not path.is_dir() or path.name == "_downloads":
                continue
            try:
                item = package.Package(path)
            except Exception:
                continue
            if getattr(item, "type", "translate") != "translate":
                continue
            yield item


def get_installed_pairs() -> list[tuple[str, str, str, str]]:
    """Возвращает установленные пары Argos Translate."""
    global _installed_pairs_cache, _installed_pair_set
    if _installed_pairs_cache is not None:
        return _installed_pairs_cache
    pairs: list[tuple[str, str, str, str]] = []
    try:
        for item in _iter_installed_packages():
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
    except Exception as error:
        from app_logging import log_exception

        log_exception("Не удалось прочитать пакеты Argos", error)
        _installed_pairs_cache = []
        _installed_pair_set = set()
        return _installed_pairs_cache
    pairs.sort(key=lambda item: (item[0], item[1]))
    _installed_pairs_cache = pairs
    _installed_pair_set = {(from_code, to_code) for from_code, to_code, *_ in pairs}
    return pairs


def get_installed_package(from_code: str, to_code: str):
    """Возвращает установленный пакет Argos для пары языков."""
    try:
        for item in _iter_installed_packages():
            if item.from_code == from_code and item.to_code == to_code:
                return item
    except Exception as error:
        from app_logging import log_exception

        log_exception("Не удалось найти пакет Argos", error)
    return None


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
    except Exception as error:
        from app_logging import log_exception

        log_exception("Не удалось получить каталог пакетов Argos", error)
        return []


def has_incomplete_package(
    from_code: str, to_code: str, architecture: str | None = None
) -> bool:
    """Argos либо установлен целиком, либо его нет."""
    del from_code, to_code, architecture
    return False


def uninstall_package(
    from_code: str, to_code: str, architecture: str | None = None
) -> None:
    """Удаляет каталог пакета Argos без вызова argostranslate.translate."""
    del architecture
    pkg = get_installed_package(from_code, to_code)
    if pkg is None:
        invalidate_cache()
        return
    package_path = getattr(pkg, "package_path", None)
    if package_path is None:
        raise RuntimeError(f"У пакета Argos {from_code} → {to_code} нет пути на диске")
    try:
        shutil.rmtree(package_path)
    except OSError as error:
        raise RuntimeError(
            f"Не удалось удалить пакет Argos {from_code} → {to_code}: {error}"
        ) from error
    invalidate_cache()
    if is_package_installed(from_code, to_code):
        raise RuntimeError(f"Пакет Argos {from_code} → {to_code} не удалось удалить")


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

    import zipfile

    from argostranslate import package, settings

    if progress_callback:
        progress_callback(0, 1, "Скачиваю пакет Argos...")
    # argos-net.com часто недоступен; добавляем зеркало data.argosopentech.com.
    links = list(getattr(argos_package, "links", None) or [])
    code = getattr(argos_package, "code", None) or f"translate-{from_code}_{to_code}"
    version = str(getattr(argos_package, "package_version", "1.9") or "1.9")
    dirname = f"{code}-{version.replace('.', '_')}"
    mirror = f"https://data.argosopentech.com/argospm/v1/{dirname}.argosmodel"
    if mirror not in links:
        links.append(mirror)
    try:
        argos_package.links = links
    except Exception:
        pass
    download_path = argos_package.download()
    if progress_callback:
        progress_callback(1, 1, "Устанавливаю пакет Argos...")
    # Не вызываем package.install_from_path: он импортирует translate → Stanza/torch.
    with package.package_lock:
        if not zipfile.is_zipfile(download_path):
            raise RuntimeError("Скачанный файл — не пакет Argos")
        with zipfile.ZipFile(download_path, "r") as zipf:
            zipf.extractall(path=settings.package_data_dir)
    try:
        download_path.unlink()
    except Exception:
        pass
    invalidate_cache()
    if not is_package_installed(from_code, to_code):
        raise RuntimeError("Пакет Argos скачан, но не найден среди установленных")
