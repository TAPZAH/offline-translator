import json
import os
from pathlib import Path

import portable_env

ENGINE_FIREFOX = "firefox"
ENGINE_ARGOS = "argos"
ENGINE_NLLB = "nllb"
ENGINE_LABELS = {
    ENGINE_ARGOS: "Argos Translate",
    ENGINE_NLLB: "NLLB-200",
    ENGINE_FIREFOX: "Firefox Translations",
}
ENGINES = (ENGINE_ARGOS, ENGINE_NLLB, ENGINE_FIREFOX)
DEFAULT_ENGINE = ENGINE_ARGOS
ARCHITECTURES = ("tiny", "base")
DEFAULT_ARCHITECTURE = "tiny"
DEFAULT_POPUP_REQUIRES_CTRL = False
DEFAULT_DOUBLE_CTRL_C_TRANSLATION = False
RESULT_WINDOW_CLICK_TO_CLOSE = "click_to_close"
RESULT_WINDOW_SELECTABLE = "selectable"
RESULT_WINDOW_MODES = (
    RESULT_WINDOW_CLICK_TO_CLOSE,
    RESULT_WINDOW_SELECTABLE,
)
DEFAULT_RESULT_WINDOW_MODE = RESULT_WINDOW_CLICK_TO_CLOSE

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


def boot_marker_path() -> Path:
    """Маркер незавершённой загрузки движка — для восстановления после краша."""
    return data_root() / "boot.json"


def mark_engine_loading(engine: str) -> None:
    """Помечает, что сейчас грузится движок. Если процесс умрёт — следующий запуск это увидит."""
    try:
        boot_marker_path().write_text(
            json.dumps({"engine": engine, "status": "loading"}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def mark_engine_ready() -> None:
    """Снимает маркер загрузки: процесс не упал нативно."""
    try:
        boot_marker_path().write_text(
            json.dumps({"status": "ready"}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def recover_if_previous_boot_crashed() -> str | None:
    """Если прошлый запуск умер при загрузке движка, сбрасывает его на Firefox.

    Нативный краш (torch/OpenMP) Python не ловит, поэтому в settings.json
    остаётся Argos, и программа больше не стартует.
    """
    path = boot_marker_path()
    try:
        if not path.is_file():
            return None
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or loaded.get("status") != "loading":
            return None
        crashed = loaded.get("engine")
        if crashed not in ENGINES:
            mark_engine_ready()
            return None
        if get_engine_name() == crashed:
            set_engine_name(DEFAULT_ENGINE)
        mark_engine_ready()
        return crashed
    except Exception:
        return None


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


def get_popup_requires_ctrl() -> bool:
    """Нужно ли удерживать Ctrl для появления кнопки после выделения."""
    value = _load_settings().get(
        "popup_requires_ctrl",
        DEFAULT_POPUP_REQUIRES_CTRL,
    )
    return value if isinstance(value, bool) else DEFAULT_POPUP_REQUIRES_CTRL


def set_popup_requires_ctrl(enabled: bool) -> None:
    """Сохраняет требование удерживать Ctrl при выделении."""
    data = dict(_load_settings())
    data["popup_requires_ctrl"] = bool(enabled)
    _save_settings(data)


def get_double_ctrl_c_translation() -> bool:
    """Включён ли перевод по двойному C при удерживаемом Ctrl."""
    value = _load_settings().get(
        "double_ctrl_c_translation",
        DEFAULT_DOUBLE_CTRL_C_TRANSLATION,
    )
    return value if isinstance(value, bool) else DEFAULT_DOUBLE_CTRL_C_TRANSLATION


def set_double_ctrl_c_translation(enabled: bool) -> None:
    """Сохраняет перевод выделения по Ctrl+C+C."""
    data = dict(_load_settings())
    data["double_ctrl_c_translation"] = bool(enabled)
    _save_settings(data)


def get_result_window_mode() -> str:
    """Возвращает режим взаимодействия с окном результата."""
    mode = _load_settings().get("result_window_mode")
    if mode in RESULT_WINDOW_MODES:
        return mode
    return DEFAULT_RESULT_WINDOW_MODE


def set_result_window_mode(mode: str) -> None:
    """Сохраняет режим взаимодействия с окном результата."""
    if mode not in RESULT_WINDOW_MODES:
        raise ValueError(f"Неизвестный режим окна результата: {mode}")
    data = dict(_load_settings())
    data["result_window_mode"] = mode
    _save_settings(data)
