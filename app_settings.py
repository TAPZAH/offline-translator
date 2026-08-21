import json
import os
from pathlib import Path

import portable_env

ENGINE_FIREFOX = "firefox"
ENGINE_ARGOS = "argos"
ENGINE_NLLB = "nllb"
ENGINES = (ENGINE_FIREFOX, ENGINE_ARGOS, ENGINE_NLLB)
ENGINE_LABELS = {
    ENGINE_FIREFOX: "Firefox Translations",
    ENGINE_ARGOS: "Argos Translate",
    ENGINE_NLLB: "NLLB-200",
}
DEFAULT_ENGINE = ENGINE_FIREFOX
ARCHITECTURES = ("tiny", "base")
DEFAULT_ARCHITECTURE = "tiny"

_settings_cache: dict | None = None


def data_root() -> Path:
    """Общая папка данных приложения."""
    env_dir = os.environ.get("OFFLINE_TRANSLATOR_HOME")
    if env_dir:
        path = Path(env_dir)
    elif portable_env.is_frozen():
        path = Path(portable_env.app_dir()) / "data"
    else:
        path = Path.home() / ".local" / "share" / "offline-translator"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    """Файл настроек движка и размера Firefox."""
    return data_root() / "settings.json"


def _legacy_architecture_path() -> Path:
    """Старый файл размера модели рядом с пакетами Firefox."""
    return data_root() / "firefox-models" / "settings.json"


def _load_settings() -> dict:
    """Читает настройки с диска один раз."""
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache
    data: dict = {}
    try:
        if settings_path().is_file():
            loaded = json.loads(settings_path().read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
    except Exception:
        data = {}
    if "architecture" not in data:
        try:
            legacy = _legacy_architecture_path()
            if legacy.is_file():
                loaded = json.loads(legacy.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and loaded.get("architecture"):
                    data["architecture"] = loaded["architecture"]
        except Exception:
            pass
    _settings_cache = data
    return data


def _save_settings(data: dict) -> None:
    """Пишет настройки на диск."""
    global _settings_cache
    _settings_cache = data
    settings_path().write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_engine_name() -> str:
    """Возвращает выбранный движок: firefox, argos или nllb."""
    engine = _load_settings().get("engine")
    if engine in ENGINES:
        return engine
    return DEFAULT_ENGINE


def set_engine_name(engine: str) -> None:
    """Сохраняет выбранный движок перевода."""
    if engine not in ENGINES:
        raise ValueError(f"Неизвестный движок: {engine}")
    data = dict(_load_settings())
    data["engine"] = engine
    _save_settings(data)


def engine_label(engine: str) -> str:
    """Подпись движка для интерфейса."""
    return ENGINE_LABELS.get(engine, engine)


def engine_from_label(label: str) -> str:
    """Код движка по подписи комбобокса."""
    for engine, text in ENGINE_LABELS.items():
        if text == label:
            return engine
    if label in ENGINES:
        return label
    return DEFAULT_ENGINE


def get_firefox_architecture() -> str:
    """Размер моделей Firefox: tiny или base."""
    architecture = _load_settings().get("architecture")
    if architecture in ARCHITECTURES:
        return architecture
    return DEFAULT_ARCHITECTURE


def set_firefox_architecture(architecture: str) -> None:
    """Сохраняет размер моделей Firefox."""
    if architecture not in ARCHITECTURES:
        raise ValueError(f"Неизвестный размер модели: {architecture}")
    data = dict(_load_settings())
    data["architecture"] = architecture
    _save_settings(data)
