import queue
import threading
from pathlib import Path

from language_packages import (
    get_installed_pairs,
    get_model_architecture,
    is_package_installed,
    needed_pairs_for_path,
    resolve_model_path,
)
from translation_result import TranslationResult



class FirefoxEngine:
    """Оффлайн-переводчик на моделях Firefox Translations.

    fxtranslate держит нативный указатель и привязан к потоку, в котором создан.
    Поэтому все Translator живут в одном рабочем потоке.
    """

    def __init__(self) -> None:
        self._requests: queue.Queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._run_worker,
            name="firefox-engine",
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
        """Загружает модель заранее, чтобы первая кнопка не тормозила."""
        self._call("warmup", source_code, target_code)

    def invalidate(self) -> None:
        """Сбрасывает кэш моделей после установки новых пакетов."""
        self._call("invalidate")

    def has_translation_path(self, source_code: str, target_code: str) -> bool:
        """Проверяет прямую модель или связку через английский."""
        if source_code == target_code:
            return False
        if is_package_installed(source_code, target_code):
            return True
        if source_code != "en" and target_code != "en":
            return is_package_installed(source_code, "en") and is_package_installed(
                "en", target_code
            )
        return False

    def _call(self, action: str, *args):
        """Отправляет задачу в рабочий поток и ждёт ответ."""
        reply: queue.Queue = queue.Queue()
        self._requests.put((action, args, reply))
        result = reply.get()
        if isinstance(result, Exception):
            raise result
        return result

    def _run_worker(self) -> None:
        """Обрабатывает перевод в одном потоке."""
        translators: dict[tuple[str, str, str], object] = {}
        while True:
            action, args, reply = self._requests.get()
            try:
                if action == "invalidate":
                    translators.clear()
                    reply.put(None)
                elif action == "warmup":
                    source_code, target_code = args
                    self._ensure_path(translators, source_code, target_code)
                    reply.put(None)
                elif action == "translate":
                    text, source_code, target_code = args
                    translated = self._translate_on_thread(
                        translators, text, source_code, target_code
                    )
                    reply.put(translated)
                else:
                    reply.put(RuntimeError(f"Неизвестное действие: {action}"))
            except Exception as error:
                reply.put(error)

    def _translate_on_thread(
        self,
        translators: dict[tuple[str, str, str], object],
        text: str,
        source_code: str,
        target_code: str,
    ) -> TranslationResult:
        """Выполняет прямой перевод или двойной через английский."""
        source_text = (text or "").strip()
        if not source_text:
            return TranslationResult(text=text)

        if is_package_installed(source_code, target_code):
            translator = self._load_translator(translators, source_code, target_code)
            return TranslationResult(text=self._run_translate(translator, source_text))

        if (
            source_code != "en"
            and target_code != "en"
            and is_package_installed(source_code, "en")
            and is_package_installed("en", target_code)
        ):
            to_english = self._load_translator(translators, source_code, "en")
            english_text = self._run_translate(to_english, source_text)
            from_english = self._load_translator(translators, "en", target_code)
            final_text = self._run_translate(from_english, english_text)
            return TranslationResult(
                text=final_text,
                intermediate=english_text,
                pivot_code="en",
            )

        missing = needed_pairs_for_path(source_code, target_code)
        if missing:
            legs = ", ".join(f"{src}->{trg}" for src, trg in missing)
            raise RuntimeError(
                f"Нет модели {source_code} → {target_code}. Установите: {legs}"
            )
        raise RuntimeError(f"Нет модели {source_code} → {target_code}")

    def _ensure_path(
        self,
        translators: dict[tuple[str, str, str], object],
        source_code: str,
        target_code: str,
    ) -> None:
        """Прогревает нужные Translator."""
        if is_package_installed(source_code, target_code):
            self._load_translator(translators, source_code, target_code)
            return
        if source_code != "en" and target_code != "en":
            self._load_translator(translators, source_code, "en")
            self._load_translator(translators, "en", target_code)

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
