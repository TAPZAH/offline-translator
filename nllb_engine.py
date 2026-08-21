import queue
import threading

from nllb_packages import (
    is_model_installed,
    is_package_installed,
    model_path,
    needed_pairs_for_path,
    to_nllb_code,
)
from translation_result import TranslationResult


class NllbEngine:
    """Оффлайн-переводчик NLLB-200 Distilled 600M через CTranslate2."""

    def __init__(self) -> None:
        self._requests: queue.Queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._run_worker,
            name="nllb-engine",
            daemon=True,
        )
        self._thread.start()

    def translate(self, text: str, source_code: str, target_code: str) -> str:
        """Переводит текст напрямую между любыми языками модели."""
        return self.translate_result(text, source_code, target_code).text

    def translate_result(
        self, text: str, source_code: str, target_code: str
    ) -> TranslationResult:
        """NLLB переводит напрямую, без промежуточного английского."""
        return self._call("translate", text, source_code, target_code)

    def translation_route(self, source_code: str, target_code: str) -> str | None:
        """NLLB всегда идёт напрямую, если оба языка есть в модели."""
        if source_code == target_code:
            return None
        if is_package_installed(source_code, target_code):
            return "direct"
        return None

    def warmup(self, source_code: str, target_code: str) -> None:
        """Загружает модель заранее."""
        self._call("warmup", source_code, target_code)

    def invalidate(self) -> None:
        """Сбрасывает загруженную модель после переустановки."""
        self._call("invalidate")

    def has_translation_path(self, source_code: str, target_code: str) -> bool:
        """Проверяет, что модель стоит и оба языка ей известны."""
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
        """Держит Translator в одном потоке."""
        state: dict = {"translator": None, "sp": None}
        while True:
            action, args, reply = self._requests.get()
            try:
                if action == "invalidate":
                    state["translator"] = None
                    state["sp"] = None
                    reply.put(None)
                elif action == "warmup":
                    source_code, target_code = args
                    try:
                        self._translate_on_thread(
                            state, "Hello", source_code, target_code
                        )
                    except Exception:
                        pass
                    reply.put(None)
                elif action == "translate":
                    text, source_code, target_code = args
                    reply.put(
                        self._translate_on_thread(
                            state, text, source_code, target_code
                        )
                    )
                else:
                    reply.put(RuntimeError(f"Неизвестное действие: {action}"))
            except Exception as error:
                reply.put(error)

    def _ensure_loaded(self, state: dict) -> None:
        """Загружает CTranslate2 и SentencePiece при первом вызове."""
        if state["translator"] is not None and state["sp"] is not None:
            return
        if not is_model_installed():
            raise RuntimeError("Модель NLLB не установлена. Откройте «Языки».")
        import ctranslate2
        import sentencepiece as spm

        root = model_path()
        state["translator"] = ctranslate2.Translator(
            str(root),
            device="cpu",
            compute_type="int8",
        )
        processor = spm.SentencePieceProcessor()
        processor.load(str(root / "sentencepiece.bpe.model"))
        state["sp"] = processor

    def _translate_on_thread(
        self,
        state: dict,
        text: str,
        source_code: str,
        target_code: str,
    ) -> TranslationResult:
        """Токенизирует, переводит и собирает текст обратно."""
        source_text = (text or "").strip()
        if not source_text:
            return TranslationResult(text=text)
        if not is_package_installed(source_code, target_code):
            missing = needed_pairs_for_path(source_code, target_code)
            if missing:
                raise RuntimeError(
                    "Нет модели NLLB. Установите NLLB-200 Distilled 600M в «Языки»."
                )
            raise RuntimeError(f"NLLB не переводит {source_code} → {target_code}")

        self._ensure_loaded(state)
        src_lang = to_nllb_code(source_code)
        tgt_lang = to_nllb_code(target_code)
        pieces = state["sp"].encode_as_pieces(source_text)
        source_tokens = [src_lang] + pieces + ["</s>"]
        results = state["translator"].translate_batch(
            [source_tokens],
            target_prefix=[[tgt_lang]],
            beam_size=2,
            max_decoding_length=512,
        )
        hypothesis = results[0].hypotheses[0]
        if hypothesis and hypothesis[0] == tgt_lang:
            hypothesis = hypothesis[1:]
        hypothesis = [token for token in hypothesis if token not in {"</s>", "<s>"}]
        translated = state["sp"].decode(hypothesis).strip()
        if not translated:
            raise RuntimeError("Пустой ответ переводчика NLLB")
        return TranslationResult(text=translated)


_engine: NllbEngine | None = None


def get_engine() -> NllbEngine:
    """Возвращает общий движок NLLB."""
    global _engine
    if _engine is None:
        _engine = NllbEngine()
    return _engine
