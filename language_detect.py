try:
    from langdetect import LangDetectException, detect

    HAS_LANGDETECT = True
except ImportError:
    HAS_LANGDETECT = False

# Соответствие кодов langdetect кодам Argos Translate
CODE_ALIASES = {
    "zh-cn": "zh",
    "zh-tw": "zh",
}

_EXTRA_CYRILLIC = frozenset("ЁёІіЇїЄєҐґ")
_UKRAINIAN = frozenset("ІіЇїЄєҐґ")

LANGUAGE_NAMES = {
    "auto": "Авто",
    "en": "Английский",
    "ru": "Русский",
    "de": "Немецкий",
    "fr": "Французский",
    "es": "Испанский",
    "it": "Итальянский",
    "pt": "Португальский",
    "zh": "Китайский",
    "ja": "Японский",
    "ko": "Корейский",
    "ar": "Арабский",
    "uk": "Украинский",
    "pl": "Польский",
    "tr": "Турецкий",
    "nl": "Нидерландский",
    "cs": "Чешский",
    "sv": "Шведский",
    "fi": "Финский",
    "el": "Греческий",
    "he": "Иврит",
    "hi": "Хинди",
    "id": "Индонезийский",
    "az": "Азербайджанский",
    "be": "Белорусский",
    "bg": "Болгарский",
    "bn": "Бенгальский",
    "bs": "Боснийский",
    "ca": "Каталанский",
    "da": "Датский",
    "et": "Эстонский",
    "fa": "Персидский",
    "gu": "Гуджарати",
    "hr": "Хорватский",
    "hu": "Венгерский",
    "is": "Исландский",
    "kn": "Каннада",
    "lt": "Литовский",
    "lv": "Латышский",
    "ml": "Малаялам",
    "ms": "Малайский",
    "mt": "Мальтийский",
    "nb": "Норвежский (букмол)",
    "nn": "Норвежский (нюнорск)",
    "ro": "Румынский",
    "sk": "Словацкий",
    "sl": "Словенский",
    "sq": "Албанский",
    "sr": "Сербский",
    "ta": "Тамильский",
    "te": "Телугу",
    "vi": "Вьетнамский",
    "th": "Тайский",
    "mk": "Македонский",
    "gl": "Галисийский",
    "ur": "Урду",
    "ka": "Грузинский",
    "nllb": "NLLB-200 Distilled 600M",
    "all": "200 языков",
}


def language_display_name(code: str, fallback: str = "") -> str:
    """Возвращает русское название языка по коду."""
    if code in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[code]
    return fallback or code


def detect_language_code(text: str) -> str | None:
    """Определяет язык текста. Возвращает ISO-код или None."""
    sample = text.strip()
    if len(sample) < 2:
        return None

    try:
        cyrillic_count = 0
        latin_count = 0
        cjk_count = 0
        arabic_count = 0
        hangul_count = 0
        japanese_count = 0
        has_ukrainian = False
        for char in sample:
            code = ord(char)
            if 0xAC00 <= code <= 0xD7AF:
                hangul_count += 1
            elif 0x3040 <= code <= 0x30FF:
                japanese_count += 1
            elif 0x4E00 <= code <= 0x9FFF:
                cjk_count += 1
            elif 0x0600 <= code <= 0x06FF:
                arabic_count += 1
            elif "А" <= char <= "я" or char in _EXTRA_CYRILLIC:
                cyrillic_count += 1
                if char in _UKRAINIAN:
                    has_ukrainian = True
            elif (
                "A" <= char <= "Z"
                or "a" <= char <= "z"
                or "À" <= char <= "ÿ"
            ):
                latin_count += 1

        letter_count = (
            cyrillic_count
            + latin_count
            + cjk_count
            + arabic_count
            + hangul_count
            + japanese_count
        )
        if letter_count == 0:
            return None

        if hangul_count > letter_count * 0.2:
            return "ko"
        if japanese_count > letter_count * 0.15:
            return "ja"
        if cjk_count > letter_count * 0.3:
            return "zh"
        if arabic_count > letter_count * 0.3:
            return "ar"
        if cyrillic_count >= latin_count and cyrillic_count > 0:
            return "uk" if has_ukrainian else "ru"

        if HAS_LANGDETECT and len(sample) >= 8:
            try:
                detected_code = detect(sample)
                return CODE_ALIASES.get(detected_code, detected_code)
            except LangDetectException:
                pass
            except Exception:
                pass

        if latin_count > 0:
            return "en"
        return None
    except Exception:
        return None
