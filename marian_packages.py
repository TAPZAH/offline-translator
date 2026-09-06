import json
import os
import re
import shutil
from pathlib import Path

import requests
from language_detect import language_display_name
from language_packages import LanguagePackage

CHUNK_SIZE = 64 * 1024
REQUEST_TIMEOUT = (15, 300)
REQUEST_HEADERS = {"User-Agent": "offline-translator/0.995-beta (marian-mt)"}
MIN_MODEL_BIN_BYTES = 10 * 1024 * 1024
CT2_CONFIG = {
    "add_source_bos": False,
    "add_source_eos": False,
    "bos_token": "<s>",
    "decoder_start_token": "</s>",
    "eos_token": "</s>",
    "unk_token": "<unk>",
}
BUILTIN_PAIRS = (
    ("en", "ru"),
    ("ru", "en"),
    ("en", "de"),
    ("de", "en"),
    ("en", "fr"),
    ("fr", "en"),
    ("en", "es"),
    ("es", "en"),
    ("en", "it"),
    ("it", "en"),
    ("en", "pt"),
    ("pt", "en"),
    ("en", "zh"),
    ("zh", "en"),
    ("en", "uk"),
    ("uk", "en"),
    ("en", "pl"),
    ("pl", "en"),
    ("en", "tr"),
    ("tr", "en"),
    ("en", "ja"),
    ("ja", "en"),
    ("en", "ko"),
    ("ko", "en"),
    ("en", "ar"),
    ("ar", "en"),
    ("en", "nl"),
    ("nl", "en"),
    ("en", "cs"),
    ("cs", "en"),
    ("en", "sv"),
    ("sv", "en"),
    ("en", "fi"),
    ("fi", "en"),
    ("en", "el"),
    ("el", "en"),
    ("en", "he"),
    ("he", "en"),
    ("en", "hu"),
    ("hu", "en"),
    ("en", "ro"),
    ("ro", "en"),
    ("en", "bg"),
    ("bg", "en"),
    ("en", "da"),
    ("da", "en"),
    ("en", "id"),
    ("id", "en"),
    ("en", "vi"),
    ("vi", "en"),
    ("en", "th"),
    ("th", "en"),
    ("en", "hi"),
    ("hi", "en"),
    ("uk", "ru"),
    ("ru", "uk"),
    ("de", "ru"),
    ("ru", "de"),
    ("fr", "ru"),
    ("ru", "fr"),
    ("pl", "ru"),
    ("ru", "pl"),
)
_PAIR_RE = re.compile(r"opus-mt-([a-z]{2,3})-([a-z]{2,3})(?:-ctranslate2.*)?$")

_installed_pairs_cache: list[tuple[str, str, str, str]] | None = None
_catalog_cache: list[LanguagePackage] | None = None


def models_dir() -> Path:
    """Папка установленных моделей MarianMT."""
    env_dir = os.environ.get("OFFLINE_TRANSLATOR_MARIAN")
    if env_dir:
        path = Path(env_dir)
    else:
        from app_settings import data_root

        path = data_root() / "marian-models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pair_path(from_code: str, to_code: str) -> Path:
    """Каталог CTranslate2-модели пары языков."""
    return models_dir() / f"{from_code}-{to_code}"


def catalog_path() -> Path:
    """Кэш удалённого каталога Hugging Face."""
    from app_settings import data_root

    return data_root() / "marian-catalog.json"


def invalidate_cache() -> None:
    """Сбрасывает кэш установленных пар и каталога."""
    global _installed_pairs_cache, _catalog_cache
    _installed_pairs_cache = None
    _catalog_cache = None


def _files_ready(directory: Path) -> bool:
    model_bin = directory / "model.bin"
    if not model_bin.is_file() or model_bin.stat().st_size < MIN_MODEL_BIN_BYTES:
        return False
    has_vocab = (directory / "shared_vocabulary.json").is_file() or (
        (directory / "source_vocabulary.json").is_file()
        and (directory / "target_vocabulary.json").is_file()
    )
    has_spm = (directory / "source.spm").is_file() or (
        directory / "sentencepiece.model"
    ).is_file()
    return has_vocab and has_spm and (directory / "config.json").is_file()


def is_package_installed(
    from_code: str, to_code: str, architecture: str | None = None
) -> bool:
    """Проверяет, установлена ли модель MarianMT для пары."""
    del architecture
    return _files_ready(pair_path(from_code, to_code))


def has_incomplete_package(
    from_code: str, to_code: str, architecture: str | None = None
) -> bool:
    """True, если остались обломки загрузки пары."""
    del architecture
    if is_package_installed(from_code, to_code):
        return False
    installed = pair_path(from_code, to_code)
    staging = models_dir() / "_downloads" / f"{from_code}-{to_code}"
    return installed.exists() or (staging.is_dir() and any(staging.iterdir()))


def get_installed_pairs() -> list[tuple[str, str, str, str]]:
    """Установленные пары MarianMT."""
    global _installed_pairs_cache
    if _installed_pairs_cache is not None:
        return _installed_pairs_cache
    pairs: list[tuple[str, str, str, str]] = []
    root = models_dir()
    try:
        for item in root.iterdir():
            if not item.is_dir() or "-" not in item.name or item.name.startswith("_"):
                continue
            from_code, to_code = item.name.split("-", 1)
            if not from_code or not to_code:
                continue
            if is_package_installed(from_code, to_code):
                pairs.append(
                    (
                        from_code,
                        to_code,
                        language_display_name(from_code, from_code),
                        language_display_name(to_code, to_code),
                    )
                )
    except OSError:
        pairs = []
    pairs.sort(key=lambda item: (item[0], item[1]))
    _installed_pairs_cache = pairs
    return pairs


def get_installed_architectures(from_code: str, to_code: str) -> list[str]:
    """MarianMT не делится на tiny/base."""
    if is_package_installed(from_code, to_code):
        return ["marian"]
    return []


def _package_for_pair(from_code: str, to_code: str, repo: str = "") -> LanguagePackage:
    return LanguagePackage(
        from_code=from_code,
        to_code=to_code,
        from_name=language_display_name(from_code, from_code),
        to_name=language_display_name(to_code, to_code),
        dirname=f"{from_code}-{to_code}",
        architecture="marian",
        argos_package=repo or None,
    )


def _read_remote_catalog() -> list[LanguagePackage]:
    path = catalog_path()
    if not path.is_file():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    packages: list[LanguagePackage] = []
    if not isinstance(loaded, list):
        return packages
    for item in loaded:
        if not isinstance(item, dict):
            continue
        from_code = str(item.get("from") or "")
        to_code = str(item.get("to") or "")
        if len(from_code) < 2 or len(to_code) < 2 or from_code == to_code:
            continue
        packages.append(
            _package_for_pair(from_code, to_code, str(item.get("repo") or ""))
        )
    return packages


def get_available_pairs(architecture: str | None = None) -> list[LanguagePackage]:
    """Каталог пар MarianMT: встроенный список плюс кэш Hugging Face."""
    del architecture
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    seen: set[tuple[str, str]] = set()
    packages: list[LanguagePackage] = []
    for from_code, to_code in BUILTIN_PAIRS:
        seen.add((from_code, to_code))
        packages.append(_package_for_pair(from_code, to_code))
    for item in _read_remote_catalog():
        key = (item.from_code, item.to_code)
        if key in seen:
            continue
        seen.add(key)
        packages.append(item)
    _catalog_cache = packages
    return packages


def update_remote_index() -> None:
    """Обновляет каталог пар с Hugging Face. Ошибка сети не бросается."""
    urls = (
        "https://huggingface.co/api/models?search=opus-mt-ctranslate2&limit=300",
        "https://hf-mirror.com/api/models?search=opus-mt-ctranslate2&limit=300",
    )
    last_error: Exception | None = None
    for url in urls:
        try:
            response = requests.get(
                url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            payload = response.json()
            rows = []
            if isinstance(payload, list):
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    model_id = str(item.get("id") or "")
                    name = model_id.rsplit("/", 1)[-1]
                    match = _PAIR_RE.match(name)
                    if not match:
                        continue
                    rows.append(
                        {
                            "from": match.group(1),
                            "to": match.group(2),
                            "repo": model_id,
                        }
                    )
            catalog_path().write_text(
                json.dumps(rows, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            invalidate_cache()
            return
        except Exception as error:
            last_error = error
    from app_logging import log_exception

    log_exception("Не удалось обновить каталог MarianMT", last_error)


def _candidate_repos(from_code: str, to_code: str, preferred: str = "") -> list[str]:
    repos: list[str] = []
    if preferred:
        repos.append(preferred)
    for item in get_available_pairs():
        if (
            item.from_code == from_code
            and item.to_code == to_code
            and isinstance(item.argos_package, str)
            and item.argos_package
        ):
            repos.append(item.argos_package)
            break
    repos.append(f"Sams200/opus-mt-{from_code}-{to_code}")
    repos.append(f"gaudi/opus-mt-{from_code}-{to_code}-ctranslate2")
    unique: list[str] = []
    for repo in repos:
        if repo not in unique:
            unique.append(repo)
    return unique


def _hf_urls(repo: str, file_name: str) -> list[str]:
    return [
        f"https://huggingface.co/{repo}/resolve/main/{file_name}?download=true",
        f"https://hf-mirror.com/{repo}/resolve/main/{file_name}?download=true",
    ]


def _download_file(
    urls: list[str],
    destination: Path,
    progress_callback,
    message: str,
    min_size: int = 1,
) -> None:
    if destination.is_file() and destination.stat().st_size >= min_size:
        if progress_callback:
            progress_callback(1, 1, f"{message} — уже скачан")
        return
    tmp_path = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None
    for url in urls:
        try:
            existing = tmp_path.stat().st_size if tmp_path.is_file() else 0
            headers = dict(REQUEST_HEADERS)
            if existing:
                headers["Range"] = f"bytes={existing}-"
            with requests.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                stream=True,
            ) as response:
                if response.status_code == 416 and existing:
                    tmp_path.replace(destination)
                    return
                response.raise_for_status()
                if existing and response.status_code == 200:
                    existing = 0
                    write_mode = "wb"
                else:
                    write_mode = "ab" if existing else "wb"
                content_range = response.headers.get("Content-Range") or ""
                if "/" in content_range:
                    total = int(content_range.rsplit("/", 1)[1])
                else:
                    total = existing + int(response.headers.get("Content-Length") or 0)
                downloaded = existing
                last_report = downloaded - CHUNK_SIZE
                destination.parent.mkdir(parents=True, exist_ok=True)
                with open(tmp_path, write_mode) as handle:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and (
                            downloaded - last_report >= 1024 * 1024
                            or (total and downloaded >= total)
                        ):
                            last_report = downloaded
                            progress_callback(
                                downloaded,
                                total or downloaded,
                                message,
                            )
            tmp_path.replace(destination)
            return
        except Exception as error:
            last_error = error
    raise RuntimeError(f"Не удалось скачать {destination.name}: {last_error}")


def _download_repo(repo: str, staging: Path, progress_callback) -> None:
    staging.mkdir(parents=True, exist_ok=True)
    _download_file(
        _hf_urls(repo, "model.bin"),
        staging / "model.bin",
        progress_callback,
        "Скачиваю model.bin",
        MIN_MODEL_BIN_BYTES,
    )
    optional = (
        "shared_vocabulary.json",
        "source_vocabulary.json",
        "target_vocabulary.json",
        "source.spm",
        "target.spm",
        "config.json",
    )
    for file_name in optional:
        try:
            _download_file(
                _hf_urls(repo, file_name),
                staging / file_name,
                progress_callback,
                f"Скачиваю {file_name}",
            )
        except Exception:
            if file_name == "source.spm":
                _download_file(
                    _hf_urls(repo, "sentencepiece.model"),
                    staging / "sentencepiece.model",
                    progress_callback,
                    "Скачиваю sentencepiece.model",
                )
    if not (staging / "config.json").is_file():
        (staging / "config.json").write_text(
            json.dumps(CT2_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def download_and_install(language_package, progress_callback=None) -> None:
    """Скачивает CTranslate2-модель MarianMT с Hugging Face."""
    from_code = language_package.from_code
    to_code = language_package.to_code
    if is_package_installed(from_code, to_code):
        if progress_callback:
            progress_callback(1, 1, "Модель MarianMT уже установлена")
        return
    preferred = ""
    if isinstance(getattr(language_package, "argos_package", None), str):
        preferred = language_package.argos_package
    staging = models_dir() / "_downloads" / f"{from_code}-{to_code}"
    last_error: Exception | None = None
    for repo in _candidate_repos(from_code, to_code, preferred):
        try:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            _download_repo(repo, staging, progress_callback)
            if not _files_ready(staging):
                raise RuntimeError("файлы модели неполные")
            if progress_callback:
                progress_callback(1, 1, "Устанавливаю модель MarianMT...")
            installed = pair_path(from_code, to_code)
            if installed.exists():
                shutil.rmtree(installed, ignore_errors=True)
            staging.replace(installed)
            downloads = models_dir() / "_downloads"
            if downloads.is_dir() and not any(downloads.iterdir()):
                shutil.rmtree(downloads, ignore_errors=True)
            invalidate_cache()
            if not is_package_installed(from_code, to_code):
                raise RuntimeError("Модель MarianMT скачана, но файлы не найдены")
            return
        except Exception as error:
            last_error = error
    raise RuntimeError(
        f"Не удалось скачать MarianMT {from_code} → {to_code}: {last_error}"
    )


def uninstall_package(
    from_code: str, to_code: str, architecture: str | None = None
) -> None:
    """Удаляет модель MarianMT и незавершённые загрузки пары."""
    del architecture
    for path in (
        pair_path(from_code, to_code),
        models_dir() / "_downloads" / f"{from_code}-{to_code}",
    ):
        if path.exists():
            try:
                shutil.rmtree(path)
            except OSError as error:
                raise RuntimeError(
                    f"Не удалось удалить модель MarianMT: {error}"
                ) from error
    downloads = models_dir() / "_downloads"
    if downloads.is_dir() and not any(downloads.iterdir()):
        shutil.rmtree(downloads, ignore_errors=True)
    invalidate_cache()


def source_tokenizer_path(from_code: str, to_code: str) -> Path:
    """source.spm или общий sentencepiece.model."""
    root = pair_path(from_code, to_code)
    dedicated = root / "source.spm"
    if dedicated.is_file():
        return dedicated
    return root / "sentencepiece.model"


def target_tokenizer_path(from_code: str, to_code: str) -> Path:
    """target.spm или тот же файл, что и исходный токенизатор."""
    dedicated = pair_path(from_code, to_code) / "target.spm"
    if dedicated.is_file():
        return dedicated
    return source_tokenizer_path(from_code, to_code)
