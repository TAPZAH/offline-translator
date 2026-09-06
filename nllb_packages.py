import json
import os
import shutil
from pathlib import Path

import requests
from language_detect import language_display_name
from language_packages import LanguagePackage

PACKAGE_FROM = "nllb"
PACKAGE_TO = "all"
MODEL_ID = "nllb-200-distilled-600M"
HF_REPO = "mijuanlo/nllb-200-distilled-600M-ct2-int8"
HF_FILES = ("model.bin", "shared_vocabulary.json", "sentencepiece.bpe.model")
CHUNK_SIZE = 64 * 1024
REQUEST_TIMEOUT = (15, 300)
REQUEST_HEADERS = {"User-Agent": "offline-translator/0.99-beta (nllb-200)"}
# Distilled 600M int8 весит около 622 МБ; меньше — обрезанная или битая загрузка
MIN_MODEL_BIN_BYTES = 500 * 1024 * 1024

# ISO-639 → коды FLORES-200, которые принимает NLLB
NLLB_LANG_CODES = {
    "en": "eng_Latn",
    "ru": "rus_Cyrl",
    "de": "deu_Latn",
    "fr": "fra_Latn",
    "es": "spa_Latn",
    "it": "ita_Latn",
    "pt": "por_Latn",
    "zh": "zho_Hans",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "ar": "arb_Arab",
    "uk": "ukr_Cyrl",
    "pl": "pol_Latn",
    "tr": "tur_Latn",
    "nl": "nld_Latn",
    "cs": "ces_Latn",
    "sv": "swe_Latn",
    "fi": "fin_Latn",
    "el": "ell_Grek",
    "he": "heb_Hebr",
    "hi": "hin_Deva",
    "id": "ind_Latn",
    "az": "azj_Latn",
    "be": "bel_Cyrl",
    "bg": "bul_Cyrl",
    "bn": "ben_Beng",
    "bs": "bos_Latn",
    "ca": "cat_Latn",
    "da": "dan_Latn",
    "et": "est_Latn",
    "fa": "pes_Arab",
    "gu": "guj_Gujr",
    "hr": "hrv_Latn",
    "hu": "hun_Latn",
    "is": "isl_Latn",
    "kn": "kan_Knda",
    "lt": "lit_Latn",
    "lv": "lvs_Latn",
    "ml": "mal_Mlym",
    "ms": "zsm_Latn",
    "mt": "mlt_Latn",
    "nb": "nob_Latn",
    "nn": "nno_Latn",
    "ro": "ron_Latn",
    "sk": "slk_Latn",
    "sl": "slv_Latn",
    "sq": "als_Latn",
    "sr": "srp_Cyrl",
    "ta": "tam_Taml",
    "te": "tel_Telu",
    "th": "tha_Thai",
    "vi": "vie_Latn",
    "mk": "mkd_Cyrl",
    "gl": "glg_Latn",
    "ur": "urd_Arab",
    "ka": "kat_Geor",
}

CT2_CONFIG = {
    "add_source_bos": False,
    "add_source_eos": False,
    "bos_token": "<s>",
    "decoder_start_token": "</s>",
    "eos_token": "</s>",
    "layer_norm_epsilon": None,
    "unk_token": "<unk>",
}


_model_installed_cache: bool | None = None
_installed_pairs_cache: list[tuple[str, str, str, str]] | None = None


def models_dir() -> Path:
    """Папка установленной модели NLLB."""
    env_dir = os.environ.get("OFFLINE_TRANSLATOR_NLLB")
    if env_dir:
        path = Path(env_dir)
    else:
        from app_settings import data_root

        path = data_root() / "nllb-200"
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_path() -> Path:
    """Каталог CTranslate2-модели distilled 600M."""
    return models_dir() / MODEL_ID


def invalidate_cache() -> None:
    """Сбрасывает кэш установленной модели NLLB."""
    global _model_installed_cache, _installed_pairs_cache
    _model_installed_cache = None
    _installed_pairs_cache = None


def is_model_installed() -> bool:
    """Проверяет, что файлы NLLB на месте."""
    global _model_installed_cache
    if _model_installed_cache is not None:
        return _model_installed_cache
    root = model_path()
    model_bin = root / "model.bin"
    installed = (
        model_bin.is_file()
        and model_bin.stat().st_size >= MIN_MODEL_BIN_BYTES
        and (root / "shared_vocabulary.json").is_file()
        and (root / "sentencepiece.bpe.model").is_file()
        and (root / "config.json").is_file()
    )
    _model_installed_cache = installed
    return installed


def to_nllb_code(iso_code: str) -> str:
    """Преобразует код языка приложения в код FLORES-200."""
    mapped = NLLB_LANG_CODES.get(iso_code)
    if not mapped:
        raise RuntimeError(f"NLLB не знает язык {iso_code}")
    return mapped


def supported_codes() -> list[str]:
    """Коды языков, которые показываем в интерфейсе."""
    return list(NLLB_LANG_CODES.keys())


def get_installed_pairs() -> list[tuple[str, str, str, str]]:
    """Если модель стоит — все поддерживаемые языки доступны сразу."""
    global _installed_pairs_cache
    if _installed_pairs_cache is not None:
        return _installed_pairs_cache
    if not is_model_installed():
        _installed_pairs_cache = []
        return _installed_pairs_cache
    pairs: list[tuple[str, str, str, str]] = []
    for code in supported_codes():
        other = "en" if code != "en" else "ru"
        pairs.append(
            (
                code,
                other,
                language_display_name(code, code),
                language_display_name(other, other),
            )
        )
    _installed_pairs_cache = pairs
    return pairs


def is_package_installed(
    from_code: str, to_code: str, architecture: str | None = None
) -> bool:
    """Для NLLB «пакет» — сама модель; любая пара из списка доступна."""
    if not is_model_installed():
        return False
    if from_code == PACKAGE_FROM and to_code == PACKAGE_TO:
        return True
    return (
        from_code in NLLB_LANG_CODES
        and to_code in NLLB_LANG_CODES
        and from_code != to_code
    )


def get_installed_architectures(from_code: str, to_code: str) -> list[str]:
    """NLLB не делится на tiny/base."""
    if is_package_installed(from_code, to_code):
        return ["nllb"]
    return []


def needed_pairs_for_path(from_code: str, to_code: str) -> list[tuple[str, str]]:
    """Если модели нет — нужно скачать один пакет NLLB."""
    if from_code == to_code:
        return []
    if is_package_installed(from_code, to_code):
        return []
    return [(PACKAGE_FROM, PACKAGE_TO)]


def update_remote_index() -> None:
    """Каталог NLLB фиксированный, индекс не качаем."""
    return


def get_available_pairs(architecture: str | None = None) -> list[LanguagePackage]:
    """Один пакет: модель NLLB-200 Distilled 600M на все языки."""
    return [
        LanguagePackage(
            from_code=PACKAGE_FROM,
            to_code=PACKAGE_TO,
            from_name="NLLB-200 Distilled 600M",
            to_name="200 языков",
            dirname=MODEL_ID,
            architecture="nllb",
        )
    ]


def has_incomplete_package(
    from_code: str, to_code: str, architecture: str | None = None
) -> bool:
    """True, если файлы NLLB есть, но модель нельзя считать установленной."""
    del from_code, to_code, architecture
    if is_model_installed():
        return False
    if model_path().exists():
        return True
    downloads = models_dir() / "_downloads"
    try:
        return downloads.is_dir() and any(downloads.iterdir())
    except OSError:
        return False


def uninstall_package(
    from_code: str, to_code: str, architecture: str | None = None
) -> None:
    """Удаляет модель NLLB и незавершённые загрузки."""
    del from_code, to_code, architecture
    for path in (model_path(), models_dir() / "_downloads"):
        if path.exists():
            try:
                shutil.rmtree(path)
            except OSError as error:
                raise RuntimeError(f"Не удалось удалить модель NLLB: {error}") from error
    invalidate_cache()


def download_and_install(language_package, progress_callback=None) -> None:
    """Скачивает CTranslate2-модель NLLB с Hugging Face."""
    if is_model_installed():
        if progress_callback:
            progress_callback(1, 1, "Модель NLLB уже установлена")
        return

    staging = models_dir() / "_downloads" / MODEL_ID
    staging.mkdir(parents=True, exist_ok=True)

    for file_name in HF_FILES:
        _download_hf_file(file_name, staging / file_name, progress_callback)

    (staging / "config.json").write_text(
        json.dumps(CT2_CONFIG, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if progress_callback:
        progress_callback(1, 1, "Устанавливаю модель NLLB...")

    installed = model_path()
    if installed.exists():
        shutil.rmtree(installed, ignore_errors=True)
    staging.replace(installed)

    downloads = models_dir() / "_downloads"
    if downloads.is_dir() and not any(downloads.iterdir()):
        shutil.rmtree(downloads, ignore_errors=True)

    invalidate_cache()
    if not is_model_installed():
        raise RuntimeError("Модель NLLB скачана, но файлы не найдены")


def _download_hf_file(file_name: str, destination: Path, progress_callback) -> None:
    """Качает один файл модели, докачивая прерванную загрузку при наличии .part."""
    if destination.is_file() and destination.stat().st_size > 0:
        if file_name != "model.bin" or destination.stat().st_size >= MIN_MODEL_BIN_BYTES:
            if progress_callback:
                progress_callback(1, 1, f"{file_name} уже скачан")
            return

    urls = [
        f"https://huggingface.co/{HF_REPO}/resolve/main/{file_name}?download=true",
        f"https://hf-mirror.com/{HF_REPO}/resolve/main/{file_name}?download=true",
    ]
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
                                f"Скачиваю {file_name}",
                            )
            tmp_path.replace(destination)
            return
        except Exception as error:
            last_error = error
    raise RuntimeError(f"Не удалось скачать {file_name}: {last_error}")
