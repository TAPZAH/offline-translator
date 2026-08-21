from translation_result import TranslationResult


def english_pivot_route(
    is_installed, source_code: str, target_code: str
) -> str | None:
    """Возвращает 'direct', 'en' или None для движков с английским мостом."""
    if source_code == target_code:
        return None
    if is_installed(source_code, target_code):
        return "direct"
    if (
        source_code != "en"
        and target_code != "en"
        and is_installed(source_code, "en")
        and is_installed("en", target_code)
    ):
        return "en"
    return None


def needed_english_pivot_pairs(
    from_code: str, to_code: str, is_installed
) -> list[tuple[str, str]]:
    """Какие пакеты нужны для прямого или двойного перевода через английский."""
    if from_code == to_code:
        return []
    if is_installed(from_code, to_code):
        return []
    if from_code == "en" or to_code == "en":
        return [(from_code, to_code)]
    needed: list[tuple[str, str]] = []
    if not is_installed(from_code, "en"):
        needed.append((from_code, "en"))
    if not is_installed("en", to_code):
        needed.append(("en", to_code))
    return needed


def translate_with_english_pivot(
    text: str,
    source_code: str,
    target_code: str,
    is_installed,
    translate_direct,
    needed_pairs,
    engine_title: str = "",
) -> TranslationResult:
    """Прямой перевод или два шага через английский."""
    source_text = (text or "").strip()
    if not source_text:
        return TranslationResult(text=text)

    if is_installed(source_code, target_code):
        return TranslationResult(
            text=translate_direct(source_text, source_code, target_code)
        )

    if (
        source_code != "en"
        and target_code != "en"
        and is_installed(source_code, "en")
        and is_installed("en", target_code)
    ):
        english_text = translate_direct(source_text, source_code, "en")
        final_text = translate_direct(english_text, "en", target_code)
        return TranslationResult(
            text=final_text,
            intermediate=english_text,
            pivot_code="en",
        )

    missing = needed_pairs(source_code, target_code)
    prefix = f"{engine_title} " if engine_title else ""
    if missing:
        legs = ", ".join(f"{src}->{trg}" for src, trg in missing)
        raise RuntimeError(
            f"Нет модели {prefix}{source_code} → {target_code}. Установите: {legs}"
        )
    raise RuntimeError(f"Нет модели {prefix}{source_code} → {target_code}")
