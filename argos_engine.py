from argos_packages import is_package_installed, needed_pairs_for_path
from threaded_engine import ThreadedEngine
from translation_result import TranslationResult
from translation_route import english_pivot_route, translate_with_english_pivot


class ArgosEngine(ThreadedEngine):
    """Оффлайн-переводчик на моделях Argos Translate."""

    def __init__(self) -> None:
        super().__init__("argos-engine")

    def translation_route(self, source_code: str, target_code: str) -> str | None:
        """Возвращает 'direct', 'en' или None, если пути нет."""
        return english_pivot_route(is_package_installed, source_code, target_code)

    def _worker_invalidate(self, state) -> None:
        """Сбрасывает кэш установленных языков Argos."""
        try:
            from argostranslate.translate import get_installed_languages

            get_installed_languages.cache_clear()
        except Exception:
            pass
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
        return translate_with_english_pivot(
            text,
            source_code,
            target_code,
            is_package_installed,
            self._argos_translate,
            needed_pairs_for_path,
            engine_title="Argos",
        )

    def _argos_translate(self, text: str, source_code: str, target_code: str) -> str:
        """Прямой вызов Argos Translate."""
        from argostranslate.translate import translate

        translated = translate(text, source_code, target_code)
        if not isinstance(translated, str) or not translated.strip():
            raise RuntimeError("Пустой ответ переводчика Argos")
        return translated


_engine: ArgosEngine | None = None


def get_engine() -> ArgosEngine:
    """Возвращает общий движок Argos."""
    global _engine
    if _engine is None:
        _engine = ArgosEngine()
    return _engine
