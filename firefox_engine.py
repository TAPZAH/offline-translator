from pathlib import Path

from language_packages import (
    get_installed_pairs,
    get_model_architecture,
    is_package_installed,
    needed_pairs_for_path,
    resolve_model_path,
)
from threaded_engine import ThreadedEngine
from translation_result import TranslationResult
from translation_route import english_pivot_route, translate_with_english_pivot


class FirefoxEngine(ThreadedEngine):
    """Оффлайн-переводчик на моделях Firefox Translations.

    fxtranslate держит нативный указатель и привязан к потоку, в котором создан.
    Поэтому все Translator живут в одном рабочем потоке.
    """

    def __init__(self) -> None:
        super().__init__("firefox-engine")

    def translation_route(self, source_code: str, target_code: str) -> str | None:
        """Возвращает 'direct', 'en' или None, если пути нет."""
        return english_pivot_route(is_package_installed, source_code, target_code)

    def _create_state(self):
        """Кэш Translator по размеру модели и паре языков."""
        return {}

    def _worker_invalidate(self, state) -> None:
        """Сбрасывает загруженные Translator."""
        state.clear()

    def _worker_translate(
        self,
        state,
        text: str,
        source_code: str,
        target_code: str,
    ) -> TranslationResult:
        """Выполняет прямой перевод или двойной через английский."""

        def translate_direct(source_text: str, from_code: str, to_code: str) -> str:
            translator = self._load_translator(state, from_code, to_code)
            return self._run_translate(translator, source_text)

        return translate_with_english_pivot(
            text,
            source_code,
            target_code,
            is_package_installed,
            translate_direct,
            needed_pairs_for_path,
        )

    def _load_translator(
        self,
        translators: dict[tuple[str, str, str], object],
        source_code: str,
        target_code: str,
    ):
        """Читает файлы модели и создаёт Translator в текущем потоке."""
        key = (get_model_architecture(), source_code, target_code)
        cached = translators.get(key)
        if cached is not None:
            return cached

        from fxtranslate import Translator

        model_path = resolve_model_path(source_code, target_code)
        if model_path is None:
            raise FileNotFoundError(
                f"Нет установленной модели {source_code} -> {target_code}"
            )
        model_file = _required_file(model_path, "model.bin")
        src_vocab, trg_vocab = _read_vocabs(model_path)
        shortlist_path = model_path / "lex.bin"
        shortlist = shortlist_path.read_bytes() if shortlist_path.is_file() else None

        translator = Translator(model_file.read_bytes(), src_vocab, trg_vocab, shortlist)
        translators[key] = translator
        return translator

    def _run_translate(self, translator, text: str) -> str:
        """translate_long режет длинный текст на предложения."""
        try:
            translated = translator.translate_long(text)
        except Exception:
            translated = translator.translate(text)
        if not isinstance(translated, str) or not translated.strip():
            raise RuntimeError("Пустой ответ переводчика")
        return translated


def _required_file(model_path: Path, name: str) -> Path:
    """Возвращает обязательный файл модели."""
    file_path = model_path / name
    if not file_path.is_file():
        raise FileNotFoundError(f"В пакете нет файла {name}: {model_path}")
    return file_path


def _read_vocabs(model_path: Path) -> tuple[bytes, bytes]:
    """Читает общий или раздельный словарь SentencePiece."""
    shared = model_path / "vocab.spm"
    if shared.is_file():
        data = shared.read_bytes()
        return data, data
    src_vocab = model_path / "srcvocab.spm"
    trg_vocab = model_path / "trgvocab.spm"
    if src_vocab.is_file() and trg_vocab.is_file():
        return src_vocab.read_bytes(), trg_vocab.read_bytes()
    raise FileNotFoundError(f"В пакете нет словаря: {model_path}")


_engine: FirefoxEngine | None = None


def get_engine() -> FirefoxEngine:
    """Возвращает общий движок приложения."""
    global _engine
    if _engine is None:
        _engine = FirefoxEngine()
    return _engine


def installed_language_codes() -> set[str]:
    """Коды языков из установленных пакетов Firefox."""
    codes: set[str] = set()
    for from_code, to_code, _from_name, _to_name in get_installed_pairs():
        codes.add(from_code)
        codes.add(to_code)
    return codes
