import re

from marian_packages import (
    is_package_installed,
    pair_path,
    source_tokenizer_path,
    target_tokenizer_path,
)
from threaded_engine import ThreadedEngine
from translation_result import TranslationResult
from translation_route import (
    english_pivot_route,
    needed_english_pivot_pairs,
    translate_with_english_pivot,
)


class MarianEngine(ThreadedEngine):
    """Оффлайн-переводчик Helsinki-NLP MarianMT через CTranslate2."""

    def __init__(self) -> None:
        super().__init__("marian-engine")

    def translation_route(self, source_code: str, target_code: str) -> str | None:
        """Возвращает 'direct', 'en' или None, если пути нет."""
        return english_pivot_route(is_package_installed, source_code, target_code)

    def _create_state(self):
        """Кэш Translator и SentencePiece по паре языков."""
        return {"translators": {}}

    def _worker_invalidate(self, state) -> None:
        """Сбрасывает кэш моделей MarianMT."""
        translators = state.get("translators")
        if isinstance(translators, dict):
            translators.clear()
        state["translators"] = {}
        try:
            from marian_packages import invalidate_cache

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
        """Прямой перевод или через английский, как у Argos."""

        def translate_direct(source_text: str, from_code: str, to_code: str) -> str:
            return self._marian_translate(state, source_text, from_code, to_code)

        return translate_with_english_pivot(
            text,
            source_code,
            target_code,
            is_package_installed,
            translate_direct,
            lambda source, target: needed_english_pivot_pairs(
                source, target, is_package_installed
            ),
            engine_title="MarianMT",
        )

    def _marian_translate(
        self,
        state,
        text: str,
        source_code: str,
        target_code: str,
    ) -> str:
        """Переводит пару через CTranslate2 и два SentencePiece."""
        if not is_package_installed(source_code, target_code):
            raise RuntimeError(f"Нет модели MarianMT {source_code} → {target_code}")
        translator, source_sp, target_sp = self._load_pair(
            state, source_code, target_code
        )
        sentences = _split_sentences(text)
        batch = []
        for sentence in sentences:
            pieces = list(source_sp.encode_as_pieces(sentence))
            if not pieces:
                continue
            if pieces[-1] != "</s>":
                pieces.append("</s>")
            batch.append(pieces)
        if not batch:
            raise RuntimeError("Токенизатор MarianMT вернул пустой результат")
        results = translator.translate_batch(
            batch,
            beam_size=2,
            replace_unknowns=True,
        )
        parts: list[str] = []
        for result in results:
            hypothesis = result.hypotheses[0] if result.hypotheses else []
            cleaned = [
                token for token in hypothesis if token not in {"</s>", "<s>"}
            ]
            if not cleaned:
                continue
            decoded = target_sp.decode_pieces(cleaned).strip()
            if decoded:
                parts.append(decoded)
        translated = " ".join(parts).strip()
        if not translated:
            raise RuntimeError("Пустой ответ переводчика MarianMT")
        return translated

    def _load_pair(self, state, source_code: str, target_code: str):
        """Создаёт Translator и процессоры SentencePiece один раз на пару."""
        key = (source_code, target_code)
        cached = state["translators"].get(key)
        if cached is not None:
            return cached
        from app_logging import flush_logs, get_logger

        import ctranslate2

        from sentencepiece_io import load_sentencepiece_processor

        model_dir = pair_path(source_code, target_code)
        get_logger().info(
            "Загрузка модели MarianMT %s → %s: %s",
            source_code,
            target_code,
            model_dir,
        )
        flush_logs()
        translator = ctranslate2.Translator(
            str(model_dir),
            device="cpu",
            compute_type="auto",
        )
        source_sp = load_sentencepiece_processor(
            source_tokenizer_path(source_code, target_code)
        )
        target_sp = load_sentencepiece_processor(
            target_tokenizer_path(source_code, target_code)
        )
        packed = (translator, source_sp, target_sp)
        state["translators"][key] = packed
        get_logger().info("Модель MarianMT %s → %s загружена", source_code, target_code)
        return packed


def _split_sentences(text: str) -> list[str]:
    """Режет текст на предложения без Stanza/torch."""
    source = (text or "").strip()
    if not source:
        return []
    parts = re.split(r"(?<=[.!?…])(?:\s+)|\n+", source)
    sentences = [part.strip() for part in parts if part.strip()]
    return sentences or [source]


_engine: MarianEngine | None = None


def get_engine() -> MarianEngine:
    """Возвращает общий движок MarianMT."""
    global _engine
    if _engine is None:
        _engine = MarianEngine()
    return _engine
