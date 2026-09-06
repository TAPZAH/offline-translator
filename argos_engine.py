import re

from pathlib import Path

from argos_packages import (
    get_installed_package,
    is_package_installed,
    needed_pairs_for_path,
)
from sentencepiece_io import ArgosSentencePieceTokenizer, load_sentencepiece_processor
from threaded_engine import ThreadedEngine
from translation_result import TranslationResult
from translation_route import english_pivot_route, translate_with_english_pivot


class ArgosEngine(ThreadedEngine):
    """Оффлайн-переводчик на моделях Argos Translate через CTranslate2.

    Не вызывает argostranslate.translate: тот импортирует Stanza/torch
    и на Windows вместе с tkinter убивает процесс.
    """

    def __init__(self) -> None:
        super().__init__("argos-engine")

    def translation_route(self, source_code: str, target_code: str) -> str | None:
        """Возвращает 'direct', 'en' или None, если пути нет."""
        return english_pivot_route(is_package_installed, source_code, target_code)

    def _create_state(self):
        """Кэш Translator по паре языков — только в рабочем потоке."""
        return {"translators": {}}

    def _worker_invalidate(self, state) -> None:
        """Сбрасывает кэш моделей и список пакетов Argos."""
        translators = state.get("translators")
        if isinstance(translators, dict):
            for key in list(translators):
                translators[key] = None
            translators.clear()
        state["translators"] = {}
        try:
            from argos_packages import invalidate_cache

            invalidate_cache()
        except Exception:
            pass

    def _worker_translate(
        self,
        state,
        text: str,
        source_code: str,
        target_code: str,
    ) -> TranslationResult:
        """Выполняет прямой перевод или двойной через английский."""

        def translate_direct(source_text: str, from_code: str, to_code: str) -> str:
            return self._argos_translate(state, source_text, from_code, to_code)

        return translate_with_english_pivot(
            text,
            source_code,
            target_code,
            is_package_installed,
            translate_direct,
            needed_pairs_for_path,
            engine_title="Argos",
        )

    def _argos_translate(
        self,
        state,
        text: str,
        source_code: str,
        target_code: str,
    ) -> str:
        """Переводит пару языков через CTranslate2 и SentencePiece пакета."""
        pkg = get_installed_package(source_code, target_code)
        if pkg is None:
            raise RuntimeError(f"Нет пакета Argos {source_code} → {target_code}")

        translator, tokenizer = self._load_translator(
            state, pkg, source_code, target_code
        )
        sentences = _split_sentences(text)
        tokenized = [tokenizer.encode(sentence) for sentence in sentences]
        results = translator.translate_batch(
            tokenized,
            beam_size=2,
            replace_unknowns=True,
        )
        parts: list[str] = []
        for result in results:
            hypothesis = result.hypotheses[0] if result.hypotheses else []
            decoded = tokenizer.decode(hypothesis).strip()
            if decoded:
                parts.append(decoded)
        translated = " ".join(parts).strip()
        if not translated:
            raise RuntimeError("Пустой ответ переводчика Argos")
        return translated

    def _load_translator(self, state, pkg, source_code: str, target_code: str):
        """Создаёт CTranslate2 Translator и токенизатор один раз на пару."""
        key = (source_code, target_code)
        cached = state["translators"].get(key)
        if cached is not None:
            return cached
        from app_logging import flush_logs, get_logger

        model_dir = pkg.package_path / "model"
        tokenizer_path = _argos_tokenizer_path(pkg)
        get_logger().info("Загрузка модели Argos %s → %s: %s", source_code, target_code, model_dir)
        flush_logs()
        import ctranslate2

        translator = ctranslate2.Translator(
            str(model_dir),
            device="cpu",
            compute_type="auto",
        )
        tokenizer = ArgosSentencePieceTokenizer(
            load_sentencepiece_processor(tokenizer_path)
        )
        packed = (translator, tokenizer)
        state["translators"][key] = packed
        get_logger().info("Модель Argos %s → %s загружена", source_code, target_code)
        return packed


def _argos_tokenizer_path(pkg) -> Path:
    """Путь к sentencepiece.model пакета, без вызова pkg.tokenizer."""
    model_file = getattr(getattr(pkg, "tokenizer", None), "model_file", None)
    if model_file is not None:
        return Path(model_file)
    return Path(pkg.package_path) / "sentencepiece.model"


def _split_sentences(text: str) -> list[str]:
    """Режет текст на предложения без Stanza/torch."""
    source = (text or "").strip()
    if not source:
        return []
    parts = re.split(r"(?<=[.!?…])(?:\s+)|\n+", source)
    sentences = [part.strip() for part in parts if part.strip()]
    return sentences or [source]


_engine: ArgosEngine | None = None


def get_engine() -> ArgosEngine:
    """Возвращает общий движок Argos."""
    global _engine
    if _engine is None:
        _engine = ArgosEngine()
    return _engine
