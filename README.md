# Оффлайн Переводчик / Offline Translator

Оффлайн-переводчик для Windows с тремя движками: Firefox Translations, Argos Translate и NLLB-200. Работает без интернета после установки языковых моделей. Версия **beta 0.98**.

Offline translator for Windows with Firefox Translations, Argos Translate and NLLB-200. Works without internet after language models are installed. Version **beta 0.98**.

## Возможности

- Перевод в окне программы, из системного трея и по выделенному тексту
- Три оффлайн-движка: Firefox (лёгкие модели Mozilla), Argos (пакеты по парам языков), NLLB-200 Distilled 600M (одна модель на ~200 языков)
- Двойной перевод через английский, если нет прямой языковой пары
- Кнопка у курсора после выделения текста; опционально Ctrl+C+C
- Автозагрузка вместе с Windows
- Портативный запуск без установки Python

## Скачать для Windows 10/11 (64-bit)

Файлы релиза (без языковых моделей; пакеты ставятся из окна «Языки...»):

| Файл | Что внутри |
|------|------------|
| `offline-translator-0.98-beta-setup.exe` | Установщик |
| `offline-translator-0.98-beta-portable.zip` | Портативная папка, Python не нужен |
| `offline-translator-0.98-beta-src.zip` | Исходники |

После распаковки портатива откройте `OfflineTranslator.exe`. Папки `_internal` и `data` удалять нельзя.


## Лицензии моделей

- Firefox Translations — модели Mozilla
- Argos Translate — пакеты Argos Open Tech / LibreTranslate
- NLLB-200 Distilled 600M — модель Meta, конвертация CTranslate2

Сама программа: см. `LICENSE`.
