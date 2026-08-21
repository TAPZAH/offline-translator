import queue
import threading

from argos_packages import is_package_installed
from translation_result import TranslationResult


class ArgosEngine:
    """Оффлайн-переводчик на моделях Argos Translate."""

    def __init__(self) -> None:
        self._requests: queue.Queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._run_worker,
            name="argos-engine",
            daemon=True,
        )
        self._thread.start()

    def translate(self, text: str, source_code: str, target_code: str) -> str:
        """Переводит текст, при необходимости через английский."""
        return self.translate_result(text, source_code, target_code).text

    def translate_result(
        self, text: str, source_code: str, target_code: str
    ) -> TranslationResult:
        """Переводит текст и возвращает промежуточный шаг, если он был."""
        return self._call("translate", text, source_code, target_code)

    def translation_route(self, source_code: str, target_code: str) -> str | None:
        """Возвращает 'direct', 'en' или None, если пути нет."""
        if source_code == target_code:
            return None
        if is_package_installed(source_code, target_code):
            return "direct"
        if (
            source_code != "en"
            and target_code != "en"
            and is_package_installed(source_code, "en")
            and is_package_installed("en", target_code)
        ):
            return "en"
        return None

    def warmup(self, source_code: str, target_code: str) -> None:
        """Прогревает модели Argos."""
        self._call("warmup", source_code, target_code)

    def invalidate(self) -> None:
        """Сбрасывает кэш языков Argos после установки пакетов."""
        self._call("invalidate")

    def has_translation_path(self, source_code: str, target_code: str) -> bool:
        """Проверяет прямую модель или связку через английский."""
        return self.translation_route(source_code, target_code) is not None

    def _call(self, action: str, *args):
        """Отправляет задачу в рабочий поток и ждёт ответ."""
        reply: queue.Queue = queue.Queue()
        self._requests.put((action, args, reply))
        result = reply.get()
        if isinstance(result, Exception):
            raise result
        return result

    def _run_worker(self) -> None:
        """Переводит в одном потоке, чтобы не конфликтовать с интерфейсом."""
        while True:
            action, args, reply = self._requests.get()
            try:
                if action == "invalidate":
                    self._clear_language_cache()
                    reply.put(None)
                elif action == "warmup":
                    source_code, target_code = args
                    try:
                        self._translate_on_thread("Hello", source_code, target_code)
                    except Exception:
                        pass
                    reply.put(None)
                elif action == "translate":
                    text, source_code, target_code = args
                    reply.put(self._translate_on_thread(text, source_code, target_code))
                else:
                    reply.put(RuntimeError(f"Неизвестное действие: {action}"))
            except Exception as error:
                reply.put(error)

    def _clear_language_cache(self) -> None:
        """Сбрасывает кэш установленных языков Argos."""
        try:
            from argostranslate.translate import get_installed_languages

            get_installed_languages.cache_clear()
        except Exception:
            pass

    def _argos_translate(self, text: str, source_code: str, target_code: str) -> str:
        """Прямой вызов Argos Translate."""
        from argostranslate.translate import translate

        translated = translate(text, source_code, target_code)
        if not isinstance(translated, str) or not translated.strip():
            raise RuntimeError("Пустой ответ переводчика Argos")
        return translated

    def _translate_on_thread(
        self,
        text: str,
        source_code: str,
        target_code: str,
    ) -> TranslationResult:
        """Выполняет прямой перевод или двойной через английский."""
        source_text = (text or "").strip()
        if not source_text:
            return TranslationResult(text=text)

        if is_package_installed(source_code, target_code):
            return TranslationResult(
                text=self._argos_translate(source_text, source_code, target_code)
            )

        if (
            source_code != "en"
            and target_code != "en"
            and is_package_installed(source_code, "en")
            and is_package_installed("en", target_code)
        ):
            english_text = self._argos_translate(source_text, source_code, "en")
            final_text = self._argos_translate(english_text, "en", target_code)
            return TranslationResult(
                text=final_text,
                intermediate=english_text,
                pivot_code="en",
            )

        missing: list[tuple[str, str]] = []
        if source_code != "en" and not is_package_installed(source_code, "en"):
            missing.append((source_code, "en"))
        if target_code != "en" and not is_package_installed("en", target_code):
            missing.append(("en", target_code))
        if source_code == "en" or target_code == "en":
            missing = [(source_code, target_code)]
        if missing:
            legs = ", ".join(f"{src}->{trg}" for src, trg in missing)
            raise RuntimeError(
                f"Нет модели Argos {source_code} → {target_code}. Установите: {legs}"
            )
        raise RuntimeError(f"Нет модели Argos {source_code} → {target_code}")


_engine: ArgosEngine | None = None


def get_engine() -> ArgosEngine:
    """Возвращает общий движок Argos."""
    global _engine
    if _engine is None:
        _engine = ArgosEngine()
    return _engine
