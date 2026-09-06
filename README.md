# Оффлайн Переводчик / Offline Translator

Оффлайн-переводчик для Windows. Работает без интернета после установки языковых моделей. Версия **beta 0.99**. Автор: **Gelezyaka**.

Offline translator for Windows. Works without internet after language models are installed. Version **beta 0.99**. Author: **Gelezyaka**.

## Возможности

- Перевод в окне программы, из системного трея и по выделенному тексту
- Четыре оффлайн-движка:
  - **Argos Translate** — пакеты CTranslate2 по парам языков
  - **NLLB-200 Distilled 600M** — одна модель Meta на ~200 языков
  - **Firefox Translations** — лёгкие модели Mozilla (tiny/base)
  - **MarianMT** — модели Helsinki-NLP OPUS-MT через CTranslate2
- Двойной перевод через английский, если нет прямой языковой пары
- Кнопка у курсора после выделения текста; опционально Ctrl+C+C
- Светлая и тёмная темы
- Автозагрузка вместе с Windows
- Портативный запуск без установки Python

## Скачать для Windows 10/11 (64-bit)

Файлы релиза (без языковых моделей; пакеты ставятся из окна «Пакеты» / «Языки...»):

| Файл | Что внутри |
|------|------------|
| `offline-translator-0.99-beta-setup.exe` | Установщик |
| `offline-translator-0.99-beta-portable.zip` | Портативная папка, Python не нужен |
| `offline-translator-0.99-beta-src.zip` | Исходники |

После распаковки портатива откройте `OfflineTranslator.exe` или `offline_translator_win32.exe`. Папки `_internal` / `assets`, `data` и `licenses` удалять нельзя.

## Лицензии моделей

- Firefox Translations — модели Mozilla
- Argos Translate — пакеты Argos Open Tech / LibreTranslate
- NLLB-200 Distilled 600M — модель Meta, конвертация CTranslate2
- MarianMT — модели Helsinki-NLP OPUS-MT, конвертация CTranslate2

Сама программа: MIT, см. `LICENSE`. Автор — Gelezyaka.
