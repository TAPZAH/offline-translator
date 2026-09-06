from pathlib import Path


def load_sentencepiece_processor(model_path: str | Path):
    """Читает модель через Python и отдаёт протобуф в SentencePiece.

    Нативный LoadFromFile на Windows не открывает пути с не-ASCII символами
    (у портативной сборки это каталог С_offline_translator).
    """
    import sentencepiece as spm

    path = Path(model_path)
    try:
        model_proto = path.read_bytes()
    except OSError as error:
        raise RuntimeError(f"Не удалось прочитать SentencePiece: {path}") from error
    if not model_proto:
        raise RuntimeError(f"Пустой файл SentencePiece: {path}")
    try:
        processor = spm.SentencePieceProcessor(model_proto=model_proto)
    except Exception as error:
        raise RuntimeError(f"Не удалось загрузить SentencePiece: {path}") from error
    return processor


class ArgosSentencePieceTokenizer:
    """Совместим с argostranslate.tokenizer.SentencePieceTokenizer."""

    def __init__(self, processor) -> None:
        self._processor = processor

    def encode(self, sentence: str) -> list[str]:
        """Кодирует предложение в куски SentencePiece."""
        return list(self._processor.encode(sentence, out_type=str))

    def decode(self, tokens: list[str]) -> str:
        """Собирает куски обратно в текст, как это делает Argos."""
        return (
            self._processor.decode_pieces(tokens)
            .replace("\u2581", " ")
            .replace("_", " ")
        )
