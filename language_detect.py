import re

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

CYRILLIC_RE = re.compile(r"[А-Яа-яЁёІіЇїЄєҐґ]")
LATIN_RE = re.compile(r"[A-Za-zÀ-ÿ]")
UKRAINIAN_RE = re.compile(r"[ІіЇїЄєҐґ]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
HANGUL_RE = re.compile(r"[\uac00-\ud7af]")
HIRAGANA_KATAKANA_RE = re.compile(r"[\u3040-\u30ff]")

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
        cyrillic_count = len(CYRILLIC_RE.findall(sample))
        latin_count = len(LATIN_RE.findall(sample))
        cjk_count = len(CJK_RE.findall(sample))
        arabic_count = len(ARABIC_RE.findall(sample))
        hangul_count = len(HANGUL_RE.findall(sample))
        japanese_count = len(HIRAGANA_KATAKANA_RE.findall(sample))
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
            if UKRAINIAN_RE.search(sample):
                return "uk"
            return "ru"

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
