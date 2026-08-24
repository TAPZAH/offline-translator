from nllb_packages import (
    is_model_installed,
    is_package_installed,
    model_path,
    needed_pairs_for_path,
    to_nllb_code,
)
from threaded_engine import ThreadedEngine
from translation_result import TranslationResult


class NllbEngine(ThreadedEngine):
    """Оффлайн-переводчик NLLB-200 Distilled 600M через CTranslate2."""

    def __init__(self) -> None:
        super().__init__("nllb-engine")

    def translation_route(self, source_code: str, target_code: str) -> str | None:
        """NLLB всегда идёт напрямую, если оба языка есть в модели."""
        if source_code == target_code:
            return None
        if is_package_installed(source_code, target_code):
            return "direct"
        return None

    def _create_state(self):
        """Translator и SentencePiece живут только в рабочем потоке."""
        return {"translator": None, "sp": None}

    def _worker_invalidate(self, state) -> None:
        """Сбрасывает загруженную модель после переустановки."""
        translator = state.get("translator")
        processor = state.get("sp")
        state["translator"] = None
        state["sp"] = None
        del translator
        del processor
        try:
            from nllb_packages import invalidate_cache

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


_engine: NllbEngine | None = None


def get_engine() -> NllbEngine:
    """Возвращает общий движок NLLB."""
    global _engine
    if _engine is None:
        _engine = NllbEngine()
    return _engine
