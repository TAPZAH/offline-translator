from dataclasses import dataclass


@dataclass
class TranslationResult:
    """Результат перевода: итоговый текст и необязательный промежуточный английский."""

    text: str
    intermediate: str | None = None
    pivot_code: str | None = None
