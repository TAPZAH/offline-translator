import gzip
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path

import portable_env
import requests
from language_detect import language_display_name

try:
    import zstandard as zstd
except ImportError:
    zstd = None

CHUNK_SIZE = 64 * 1024
REQUEST_TIMEOUT = (15, 120)
REQUEST_HEADERS = {
    "User-Agent": "offline-translator/1.0 (firefox-translations-models)"
}
FIREFOX_CDN = "https://firefox-settings-attachments.cdn.mozilla.net/"
GITHUB_CONTENTS = (
    "https://api.github.com/repos/mozilla/firefox-translations-models/"
    "contents/models/{architecture}"
)
GITHUB_RAW = (
    "https://raw.githubusercontent.com/mozilla/firefox-translations-models/"
    "main/models/{architecture}"
)
GITHUB_LFS = (
    "https://media.githubusercontent.com/media/mozilla/firefox-translations-models/"
    "main/models/{architecture}"
)
GCS_MODELS = (
    "https://storage.googleapis.com/"
    "moz-fx-translations-data--303e-prod-translations-data/"
    "firefox-ci/models/{architecture}"
)

ARCHITECTURES = ("tiny", "base")
DEFAULT_ARCHITECTURE = "tiny"
ARCHITECTURE_LABELS = {
    "tiny": "tiny (быстрее)",
    "base": "base (качественнее)",
}

# Каталог tiny с GitHub, если API недоступен
FALLBACK_TINY_DIRS = [
    "azen", "been", "bgen", "bnen", "bsen", "caen", "csen", "daen", "deen",
    "elen", "enaz", "enbg", "enbn", "enca", "encs", "enda", "ende", "enel",
    "enes", "enet", "enfa", "enfi", "enfr", "engu", "enhe", "enhi", "enhr",
    "enhu", "enid", "enit", "enkn", "enlt", "enlv", "enml", "enms", "ennl",
    "enpl", "enpt", "enro", "enru", "ensk", "ensl", "ensq", "ensv", "enta",
    "ente", "entr", "enuk", "esen", "eten", "faen", "fien", "fren", "guen",
    "heen", "hien", "hren", "huen", "iden", "isen", "iten", "knen", "lten",
    "lven", "mlen", "msen", "mten", "nben", "nlen", "nnen", "plen", "pten",
    "roen", "ruen", "sken", "slen", "sqen", "sren", "sven", "taen", "teen",
    "tren", "uken", "vien",
]
FALLBACK_BASE_DIRS = [
    "aren", "deen", "enar", "encs", "enja", "enko", "enru", "enzh",
    "jaen", "koen", "zhen",
]
FALLBACK_DIRS = {
    "tiny": FALLBACK_TINY_DIRS,
    "base": FALLBACK_BASE_DIRS,
}

_records_cache = None
_architecture_cache = None


@dataclass
class LanguagePackage:
    """Языковая пара Firefox Translations."""

    from_code: str
    to_code: str
    from_name: str
    to_name: str
    dirname: str
    architecture: str = DEFAULT_ARCHITECTURE


def models_dir() -> Path:
    """Папка установленных моделей Firefox."""
    env_dir = os.environ.get("OFFLINE_TRANSLATOR_MODELS")
    if env_dir:
        path = Path(env_dir)
    elif portable_env.is_frozen():
        path = Path(portable_env.app_dir()) / "data" / "firefox-models"
    else:
        path = (
            Path.home()
            / ".local"
            / "share"
            / "offline-translator"
            / "firefox-models"
        )
    path.mkdir(parents=True, exist_ok=True)
    return path


def downloads_dir() -> Path:
    """Временная папка загрузок."""
    path = models_dir() / "_downloads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def catalog_path() -> Path:
    """Кэш списка доступных пар."""
    return models_dir() / "catalog.json"


def settings_path() -> Path:
    """Файл настроек: выбранный размер модели."""
    return models_dir() / "settings.json"


def get_model_architecture() -> str:
    """Возвращает выбранный размер модели: tiny или base."""
    global _architecture_cache
    if _architecture_cache in ARCHITECTURES:
        return _architecture_cache
    try:
        if settings_path().is_file():
            data = json.loads(settings_path().read_text(encoding="utf-8"))
            architecture = data.get("architecture")
            if architecture in ARCHITECTURES:
                _architecture_cache = architecture
                return architecture
    except Exception:
        pass
    _architecture_cache = DEFAULT_ARCHITECTURE
    return DEFAULT_ARCHITECTURE


def set_model_architecture(architecture: str) -> None:
    """Сохраняет выбранный размер модели."""
    global _architecture_cache
    if architecture not in ARCHITECTURES:
        raise ValueError(f"Неизвестный размер модели: {architecture}")
    _architecture_cache = architecture
    data = {}
    try:
        if settings_path().is_file():
            data = json.loads(settings_path().read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
    except Exception:
        data = {}
    data["architecture"] = architecture
    settings_path().write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def architecture_label(architecture: str) -> str:
    """Подпись размера модели для интерфейса."""
    return ARCHITECTURE_LABELS.get(architecture, architecture)


def architecture_from_label(label: str) -> str:
    """Код размера модели по подписи комбобокса."""
    for architecture, text in ARCHITECTURE_LABELS.items():
        if text == label:
            return architecture
    if label in ARCHITECTURES:
        return label
    return DEFAULT_ARCHITECTURE


def pair_dir(from_code: str, to_code: str, architecture: str | None = None) -> Path:
    """Папка установки пары языков для выбранного размера."""
    chosen = architecture or get_model_architecture()
    return models_dir() / chosen / f"{from_code}-{to_code}"


def resolve_model_path(
    from_code: str, to_code: str, architecture: str | None = None
) -> Path | None:
    """Находит установленную модель: сначала выбранный размер, потом запасной."""
    preferred = architecture or get_model_architecture()
    path = pair_dir(from_code, to_code, preferred)
    if _model_ready(path):
        return path
    legacy = models_dir() / f"{from_code}-{to_code}"
    if preferred == "tiny" and _model_ready(legacy):
        return legacy
    for chosen in ARCHITECTURES:
        if chosen == preferred:
            continue
        path = pair_dir(from_code, to_code, chosen)
        if _model_ready(path):
            return path
    if preferred != "tiny" and _model_ready(legacy):
        return legacy
    return None


def pair_from_dirname(name: str) -> tuple[str, str] | None:
    """Разбирает имя каталога GitHub вида enru → (en, ru)."""
    if len(name) == 4 and name.isalpha():
        return name[:2].lower(), name[2:].lower()
    return None


def is_package_installed(
    from_code: str, to_code: str, architecture: str | None = None
) -> bool:
    """Проверяет, установлен ли пакет перевода."""
    try:
        if architecture:
            if _model_ready(pair_dir(from_code, to_code, architecture)):
                return True
            if architecture == "tiny":
                return _model_ready(models_dir() / f"{from_code}-{to_code}")
            return False
        return resolve_model_path(from_code, to_code) is not None
    except Exception:
        return False


def get_installed_architectures(from_code: str, to_code: str) -> list[str]:
    """Какие размеры модели стоят для этой пары."""
    found: list[str] = []
    for architecture in ARCHITECTURES:
        if is_package_installed(from_code, to_code, architecture):
            found.append(architecture)
    return found


def get_installed_pairs() -> list[tuple[str, str, str, str]]:
    """Возвращает установленные пары (from_code, to_code, from_name, to_name)."""
    pairs: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    try:
        for child in _installed_pair_dirs():
            from_code, to_code = _codes_from_installed(child)
            if not from_code or not to_code:
                continue
            key = (from_code, to_code)
            if key in seen:
                continue
            seen.add(key)
            pairs.append(
                (
                    from_code,
                    to_code,
                    language_display_name(from_code, from_code),
                    language_display_name(to_code, to_code),
                )
            )
    except Exception:
        return []
    return sorted(pairs, key=lambda item: (item[0], item[1]))


def update_remote_index() -> None:
    """Обновляет каталог пар tiny и base с GitHub."""
    packages: list[LanguagePackage] = []
    last_error: Exception | None = None
    for architecture in ARCHITECTURES:
        try:
            packages.extend(_fetch_github_pairs(architecture))
        except Exception as error:
            last_error = error
            packages.extend(_fallback_packages(architecture))
    if not packages and last_error is not None:
        raise last_error
    catalog_path().write_text(
        json.dumps(
            [
                {
                    "from_code": item.from_code,
                    "to_code": item.to_code,
                    "dirname": item.dirname,
                    "architecture": item.architecture,
                }
                for item in packages
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def get_available_pairs(architecture: str | None = None) -> list[LanguagePackage]:
    """Возвращает доступные для скачивания пакеты перевода."""
    packages = _load_catalog_packages()
    if not packages:
        try:
            update_remote_index()
            packages = _load_catalog_packages()
        except Exception:
            packages = []
    if not packages:
        packages = [
            item
            for chosen in ARCHITECTURES
            for item in _fallback_packages(chosen)
        ]
    if architecture:
        filtered = [item for item in packages if item.architecture == architecture]
        if filtered:
            return filtered
        return _fallback_packages(architecture)
    return packages


def download_and_install(language_package, progress_callback=None) -> None:
    """Скачивает и устанавливает языковую пару Firefox.

    progress_callback(downloaded: int, total: int, message: str) вызывается из рабочего потока.
    """
    from_code = language_package.from_code
    to_code = language_package.to_code
    dirname = getattr(language_package, "dirname", f"{from_code}{to_code}")
    architecture = getattr(language_package, "architecture", DEFAULT_ARCHITECTURE)
    if architecture not in ARCHITECTURES:
        architecture = DEFAULT_ARCHITECTURE

    if is_package_installed(from_code, to_code, architecture):
        if progress_callback:
            progress_callback(1, 1, "Пакет уже установлен")
        return

    if progress_callback:
        progress_callback(0, 1, f"Скачиваю модель Firefox ({architecture})...")

    file_names = _list_remote_files(dirname, from_code, to_code, architecture)
    if not file_names:
        raise RuntimeError("Не найдены файлы модели на GitHub/GCS")

    staging = downloads_dir() / f"{architecture}-{from_code}-{to_code}"
    if staging.exists():
        _remove_tree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    downloaded_total = 0
    for file_name in file_names:
        if file_name == "metadata.json":
            _download_metadata(
                dirname, architecture, staging / "metadata.json", progress_callback
            )
            continue
        target_name = _normalized_name(file_name)
        if target_name is None:
            continue
        destination = staging / target_name
        try:
            size = _download_model_file(
                dirname,
                from_code,
                to_code,
                file_name,
                destination,
                progress_callback,
                architecture,
            )
            downloaded_total += size
        except Exception as error:
            # Короткий список (lex) ускоряет перевод, но без него модель работает
            if target_name == "lex.bin":
                if progress_callback:
                    progress_callback(0, 1, f"Пропускаю lex: {error}")
                continue
            raise

    if not (staging / "model.bin").is_file():
        raise RuntimeError("Не удалось скачать файл модели")
    if not (staging / "vocab.spm").is_file() and not (
        (staging / "srcvocab.spm").is_file() and (staging / "trgvocab.spm").is_file()
    ):
        raise RuntimeError("Не удалось скачать словарь модели")

    _write_architecture_metadata(staging, from_code, to_code, architecture)

    if progress_callback:
        progress_callback(1, 1, "Устанавливаю пакет...")

    installed = pair_dir(from_code, to_code, architecture)
    installed.parent.mkdir(parents=True, exist_ok=True)
    if installed.exists():
        _remove_tree(installed)
    staging.replace(installed)

    if not is_package_installed(from_code, to_code, architecture):
        raise RuntimeError("Пакет скачан, но не найден среди установленных")


def _installed_pair_dirs() -> list[Path]:
    """Папки установленных моделей: tiny/base и старый плоский каталог."""
    root = models_dir()
    found: list[Path] = []
    for architecture in ARCHITECTURES:
        arch_root = root / architecture
        if not arch_root.is_dir():
            continue
        for child in sorted(arch_root.iterdir()):
            if child.is_dir() and _model_ready(child):
                found.append(child)
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if child.name in ARCHITECTURES:
            continue
        if _model_ready(child):
            found.append(child)
    return found


def _model_ready(model_path: Path) -> bool:
    """Проверяет, что в папке есть модель и словарь."""
    if not (model_path / "model.bin").is_file():
        return False
    if (model_path / "vocab.spm").is_file():
        return True
    return (model_path / "srcvocab.spm").is_file() and (
        model_path / "trgvocab.spm"
    ).is_file()


def _codes_from_installed(model_path: Path) -> tuple[str, str]:
    """Читает коды языков из metadata.json или имени папки."""
    metadata_file = model_path / "metadata.json"
    try:
        if metadata_file.is_file():
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            from_code = metadata.get("sourceLanguage") or metadata.get("from")
            to_code = metadata.get("targetLanguage") or metadata.get("to")
            if from_code and to_code:
                return _normalize_lang(str(from_code)), _normalize_lang(str(to_code))
    except Exception:
        pass
    parts = model_path.name.split("-", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    parsed = pair_from_dirname(model_path.name)
    if parsed:
        return parsed
    return "", ""


def _make_package(
    from_code: str, to_code: str, dirname: str, architecture: str
) -> LanguagePackage:
    """Собирает описание пакета для окна языков."""
    return LanguagePackage(
        from_code=from_code,
        to_code=to_code,
        from_name=language_display_name(from_code, from_code),
        to_name=language_display_name(to_code, to_code),
        dirname=dirname,
        architecture=architecture,
    )


def _package_from_catalog(item: dict) -> LanguagePackage | None:
    """Превращает запись кэша в LanguagePackage."""
    try:
        from_code = item["from_code"]
        to_code = item["to_code"]
        dirname = item.get("dirname") or f"{from_code}{to_code}"
        architecture = item.get("architecture") or DEFAULT_ARCHITECTURE
        if architecture not in ARCHITECTURES:
            architecture = DEFAULT_ARCHITECTURE
        return _make_package(from_code, to_code, dirname, architecture)
    except Exception:
        return None


def _load_catalog_packages() -> list[LanguagePackage]:
    """Читает кэш каталога, если он есть."""
    try:
        if not catalog_path().is_file():
            return []
        raw = json.loads(catalog_path().read_text(encoding="utf-8"))
        packages = [_package_from_catalog(item) for item in raw]
        return [item for item in packages if item is not None]
    except Exception:
        return []


def _fallback_packages(architecture: str) -> list[LanguagePackage]:
    """Локальный список пар, если GitHub недоступен."""
    packages: list[LanguagePackage] = []
    for dirname in FALLBACK_DIRS.get(architecture, ()):
        parsed = pair_from_dirname(dirname)
        if parsed is None:
            continue
        from_code, to_code = parsed
        packages.append(_make_package(from_code, to_code, dirname, architecture))
    return packages


def _fetch_github_pairs(architecture: str) -> list[LanguagePackage]:
    """Читает список папок models/tiny или models/base с GitHub."""
    response = requests.get(
        GITHUB_CONTENTS.format(architecture=architecture),
        timeout=REQUEST_TIMEOUT,
        headers=REQUEST_HEADERS,
    )
    response.raise_for_status()
    entries = response.json()
    packages: list[LanguagePackage] = []
    if not isinstance(entries, list):
        raise RuntimeError("Неожиданный ответ GitHub API")
    for entry in entries:
        if entry.get("type") != "dir":
            continue
        dirname = entry.get("name") or ""
        parsed = pair_from_dirname(dirname)
        if parsed is None:
            continue
        from_code, to_code = parsed
        packages.append(_make_package(from_code, to_code, dirname, architecture))
    if not packages:
        raise RuntimeError(f"GitHub не вернул языковые пары ({architecture})")
    return packages


def _list_remote_files(
    dirname: str, from_code: str, to_code: str, architecture: str
) -> list[str]:
    """Список файлов пары: GitHub API, иначе стандартные имена модели."""
    try:
        response = requests.get(
            f"{GITHUB_CONTENTS.format(architecture=architecture)}/{dirname}",
            timeout=REQUEST_TIMEOUT,
            headers=REQUEST_HEADERS,
        )
        response.raise_for_status()
        entries = response.json()
        names = []
        for entry in entries:
            if entry.get("type") != "file":
                continue
            name = entry.get("name") or ""
            if name:
                names.append(name)
        if names:
            return names
    except Exception:
        pass
    pair = f"{from_code}{to_code}"
    return [
        f"model.{pair}.intgemm.alphas.bin.gz",
        f"vocab.{pair}.spm.gz",
        f"lex.50.50.{pair}.s2t.bin.gz",
        "metadata.json",
    ]


def _normalized_name(remote_name: str) -> str | None:
    """Приводит имя файла GitHub к model.bin / vocab.spm / lex.bin."""
    name = remote_name.lower()
    if name.endswith(".gz"):
        name = name[:-3]
    if name == "metadata.json":
        return "metadata.json"
    if name.startswith("model.") and name.endswith(".bin"):
        return "model.bin"
    if name.startswith("vocab.") and name.endswith(".spm"):
        return "vocab.spm"
    if name.startswith("srcvocab.") and name.endswith(".spm"):
        return "srcvocab.spm"
    if name.startswith("trgvocab.") and name.endswith(".spm"):
        return "trgvocab.spm"
    if name.startswith("lex.") and name.endswith(".bin"):
        return "lex.bin"
    return None


def _download_metadata(
    dirname: str, architecture: str, destination: Path, progress_callback
) -> None:
    """Скачивает metadata.json (обычный файл, не Git LFS)."""
    url = f"{GITHUB_RAW.format(architecture=architecture)}/{dirname}/metadata.json"
    try:
        if progress_callback:
            progress_callback(0, 1, "Скачиваю metadata.json")
        with requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers=REQUEST_HEADERS,
        ) as response:
            response.raise_for_status()
            destination.write_bytes(response.content)
    except Exception:
        # metadata не обязателен для перевода
        pass


def _write_architecture_metadata(
    model_path: Path, from_code: str, to_code: str, architecture: str
) -> None:
    """Дописывает размер модели в metadata.json."""
    metadata_file = model_path / "metadata.json"
    data = {}
    try:
        if metadata_file.is_file():
            loaded = json.loads(metadata_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
    except Exception:
        data = {}
    data.setdefault("sourceLanguage", from_code)
    data.setdefault("targetLanguage", to_code)
    data["architecture"] = architecture
    metadata_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _firefox_records() -> list[dict]:
    """Кэширует каталог моделей, которые Firefox отдаёт через Remote Settings."""
    global _records_cache
    if _records_cache is not None:
        return _records_cache
    try:
        from fxtranslate import discovery

        body = discovery.fetch_records_body()
        _records_cache = list(discovery.parse_records(body))
    except Exception:
        _records_cache = []
    return _records_cache


def _normalize_lang(code: str) -> str:
    """Приводит zh-Hans / zh-Hant к zh для сопоставления пар."""
    normalized = (code or "").lower().replace("_", "-")
    if normalized.startswith("zh"):
        return "zh"
    return normalized.split("-", 1)[0]


def _cdn_candidates(
    from_code: str, to_code: str, stem: str, architecture: str
) -> list[tuple[str, str, str | None]]:
    """Ссылки Firefox CDN на модель нужного размера."""
    matches: list[dict] = []
    for record in _firefox_records():
        if _normalize_lang(record.get("sourceLanguage") or "") != _normalize_lang(
            from_code
        ):
            continue
        if _normalize_lang(record.get("targetLanguage") or "") != _normalize_lang(
            to_code
        ):
            continue
        if (record.get("architecture") or "") != architecture:
            continue
        name = record.get("name") or ""
        location = record.get("location") or ""
        if not location or name != stem:
            continue
        matches.append(record)
    urls = []
    for record in matches:
        urls.append(
            (
                FIREFOX_CDN + record["location"].lstrip("/"),
                "zst",
                record.get("decompressedHash"),
            )
        )
    return urls


def _download_model_file(
    dirname: str,
    from_code: str,
    to_code: str,
    remote_name: str,
    destination: Path,
    progress_callback,
    architecture: str,
) -> int:
    """Скачивает файл модели: GCS, затем CDN Firefox, затем GitHub LFS."""
    stem = remote_name[:-3] if remote_name.endswith(".gz") else remote_name
    gcs_root = GCS_MODELS.format(architecture=architecture)
    github_lfs = GITHUB_LFS.format(architecture=architecture)
    github_raw = GITHUB_RAW.format(architecture=architecture)
    urls: list[tuple[str, str, str | None]] = [
        (f"{gcs_root}/{from_code}-{to_code}/{stem}.zst", "zst", None),
        *_cdn_candidates(from_code, to_code, stem, architecture),
        (f"{github_lfs}/{dirname}/{remote_name}", "gz", None),
        (f"{github_raw}/{dirname}/{remote_name}", "gz", None),
    ]
    last_error: Exception | None = None
    for url, encoding, expected_hash in urls:
        try:
            return _download_and_decompress(
                url, encoding, destination, progress_callback, expected_hash
            )
        except Exception as error:
            last_error = error
            if destination.exists():
                destination.unlink()
    raise RuntimeError(f"Загрузка {remote_name} не удалась: {last_error}")


def _download_and_decompress(
    url: str,
    encoding: str,
    destination: Path,
    progress_callback,
    expected_hash: str | None = None,
) -> int:
    """Скачивает сжатый файл и распаковывает на диск."""
    if encoding == "zst" and zstd is None:
        raise RuntimeError("Нужен пакет zstandard для распаковки моделей")

    if progress_callback:
        progress_callback(0, 1, f"Скачиваю: {url}")

    with requests.get(
        url,
        stream=True,
        timeout=REQUEST_TIMEOUT,
        headers=REQUEST_HEADERS,
    ) as response:
        response.raise_for_status()
        # Git LFS-указатель весит около 130 байт — это не модель
        total_size = int(response.headers.get("content-length", 0))
        if 0 < total_size < 500 and "github" in url:
            raise RuntimeError("GitHub вернул указатель LFS вместо файла")

        compressed = io.BytesIO()
        downloaded = 0
        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            if not chunk:
                continue
            compressed.write(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total_size, "Скачиваю модель...")

        payload = compressed.getvalue()
        if len(payload) < 500:
            raise RuntimeError("Скачан слишком маленький файл")

        if encoding == "zst":
            if expected_hash:
                from fxtranslate import discovery

                data = discovery.verify_and_decompress(payload, expected_hash)
            else:
                data = _decompress_zstd(payload)
        else:
            data = gzip.decompress(payload)

        if len(data) < 500:
            raise RuntimeError("После распаковки файл слишком маленький")
        destination.write_bytes(data)
        return len(data)


def _decompress_zstd(payload: bytes) -> bytes:
    """Распаковывает zstd, в том числе кадры без размера в заголовке."""
    decompressor = zstd.ZstdDecompressor()
    try:
        return decompressor.decompress(payload)
    except Exception:
        with decompressor.stream_reader(io.BytesIO(payload)) as reader:
            return reader.read()


def _remove_tree(path: Path) -> None:
    """Удаляет папку с файлами."""
    for child in path.iterdir():
        if child.is_dir():
            _remove_tree(child)
        else:
            child.unlink()
    path.rmdir()
