# Отличия C++-сборки от Python-эталона

Сводка по коду, не по маркетингу. Python (`main.py`, tkinter) остаётся
эталоном полного UX. C++ — Win32-подмножество с теми же каталогами моделей.

## Движки

- **Firefox Translations включён.** C++ использует тот же нативный Rust-
  движок `fxtranslate`, что и Python-пакет: тонкий мост `cpp/fxbridge`
  (cdylib, C-ABI) собирается в `fxbridge.dll` и загружается через
  LoadLibrary рядом с exe. Раскладка моделей совпадает с Python
  (`firefox-models/<arch>/<from>-<to>`, legacy-плоский tiny). Переводы
  байт-в-байт совпадают с Python (`translate_long`). Мост привязывает
  движок к рабочему потоку — как Python FirefoxEngine.
  Пересборка моста: `cargo build --release` в `cpp/fxbridge`
  (нужен Rust toolchain).
- **Argos: удалённый индекс.** Python читает `argostranslate.package`
  (`update_package_index` → `get_available_packages`). C++
  `ArgosModelManager::available_packages()` разбирает тот же JSON
  `argospm-index` из кэша `%USERPROFILE%\.local\share\argos-translate\index.json`;
  `update_remote_index()` качает индекс через WinHTTP. Нет кэша, сеть
  недоступна или JSON битый — встроенные `en↔ru`. Установленные пары на
  диске (`translate-<from>_<to>-<версия>/`) находятся по шаблону,
  даже если версии не `1_9`.
- **NLLB: один пакет.** И Python, и C++ ждут
  `nllb-200-distilled-600M` в `%USERPROFILE%\.local\share\offline-translator\nllb-200`
  (или `OFFLINE_TRANSLATOR_NLLB` / portable `data/nllb-200`). Каталог NLLB
  в C++ фиксированный, индекс не качается.
- **Параметры CTranslate2 совпадают.** Argos: `beam_size=2`, резка на
  предложения; NLLB: `beam_size=2`, `max_decoding_length=512`,
  `compute_type=int8` — сборка CTranslate2 с oneDNN
  (`build-openblas-dnnl`) поддержала INT8; без неё адаптер молча
  откатывается на AUTO. NLLB-вывод совпал с Python байт-в-байт
  («Здравствуйте , мирно .» для `Hello world`).

## GUI и выделение

- Python: tkinter, попап выделения с PNG `assets/icon.png` (PIL), полное
  окно «Языки» с поиском и удалённым индексом.
- C++: Win32. Кнопка выделения теперь рисует тот же `assets/icon.png`
  через GDI+ (`UpdateLayeredWindow`, premultiplied ARGB), повторяет
  `_fill_clickable_disk` (клик в центр знака не проваливается) и
  масштабирует 40×40 как Python LANCZOS ≈ HighQualityBicubic. Без файла
  иконки — фолбэк «Aa». Окно результата у курсора: копирование /
  закрытие, режимы `click_to_close` и `selectable`; палитра #f2f2f2 /
  #dedede / #ccc / #333, Segoe UI 8/9/11, полупрозрачность 0.97,
  рамка 1px, плоские кнопки с hover, высота под текст 2..12 строк,
  Escape закрывает, копируется выделение текста если оно есть.
  Жесты (порог драга 16 px, 0.18 с, double Ctrl+C 0.7 с) совпадают
  по константам с Python.
- Отличие от Python (намеренное): позиция попапа прижимается к рабочей
  области монитора, чтобы окно не уходило за край экрана.
- Комбо языков C++ показывает **те же 56 языков**, что и NLLB, но с
  русскими названиями из единой таблицы `language_store` (как
  `LANGUAGE_NAMES` в Python). Для Argos это не значит, что пакет скачан:
  нужна локальная пара, иначе перевод падает с ошибкой маршрута. Окно
  «Пакеты» C++ перечисляет пары из кэша `argospm-index` (как Python
  `get_available_packages`) плюс установленные, сортирует как Python
  (установленные → пары с ru/en → по кодам) и даёт **поиск** по кодам и
  русским названиям — аналог поиска в «Языках» Python.
- Названия языков: единая таблица `supported_languages()` в
  `language_store` покрывает все 56 кодов; словарь `language_display_name`
  в selection.cpp остаётся только для заголовков попапа.

## Определение языка

- Python `detect_language_code`: эвристика по письму (кириллица/латиница/CJK/…)
  плюс `langdetect` для латиницы длиной ≥ 8, если пакет установлен.
- C++ `detect_script_language`: та же эвристика по письму, **без langdetect**.
  Латиница всегда → `en`. Украинские буквы → `uk`. Попап выделения
  для `ru` выбирает ru→en, иначе source→ru.

## Автозагрузка

- Python (не frozen): `"pyw.exe" -3.13 "<main.py>" --minimized`.
  Frozen / портативный exe: `"<exe>" --minimized`.
- C++ **всегда** `"<exe>" --minimized` (`autostart_command_for_exe`).
- Боевое значение реестра: `HKCU\...\Run\OfflineTranslator`.
  Тесты пишут только `OfflineTranslatorCppTest` и удаляют его; ключ
  `OfflineTranslator` не включают.

## Настройки

- Путь файла тот же (`OFFLINE_TRANSLATOR_HOME`, portable `data/`, иначе
  профиль). C++ читает/пишет `engine`, языки, размер окна, флаги попапа,
  `result_window_mode`, `translate_hotkey`. Прочие ключи Python
  (например `architecture`) при записи **не затираются**.
- Обрезанный, пустой или не-объектный JSON, а также неверные типы полей:
  C++ возвращает значения по умолчанию и не бросает исключение
  (`load_settings`). Как в Python `_load_settings` с `except Exception`.

## Сборка CTranslate2

- Рабочая: OpenBLAS + `OPENMP_RUNTIME=COMP` (`C:\deps\CTranslate2\build-openblas`).
- Сборка без OpenMP (`OPENMP_RUNTIME=NONE`) **не поддерживается**: NLLB
  зависает (пул CTranslate2 + пул OpenBLAS). Обход `intra_threads=1` в
  адаптере не оставляли.
- При выходе процесса OpenBLAS иногда печатает
  `BLAS : Bad memory unallocation!` — предупреждение выгрузки, не ошибка
  перевода.

## Упаковка

- C++ lite (`package_win32.ps1` без `-IncludeModels`): exe GUI, runtime DLL,
  VC-redist, `vcomp140.dll`, иконка, лицензии, пустая `data/`. Модели NLLB
  (~600 МБ) в git и в lite не копируются.
- Python-упаковка (`build_portable.py`, `OfflineTranslator.iss`) не заменяется.
- Inno Setup C++ не включает Run-ключ при установке.

## Что C++ не повторяет

- `langdetect` (эвристика по письму — как Python без пакета).
- Нарезка предложений Argos в C++ совпадает по правилам с Python.
  Длинный NLLB-выход ограничен 512 токенами, как в Python.

## Наблюдения qa-parity (`Hello world` en→ru)

Запуск 2026-08-25/26, те же пользовательские модели. Этап **не** считает
расхождение формулировок провалом; после INT8-сборки NLLB совпал с Python.

| Источник | Текст |
|---|---|
| Python Argos | Привет, мир |
| Python NLLB (int8) | Здравствуйте , мирно . |
| Python Firefox (base) | привет, мир. сегодня погода хорошая. (длинный вход) |
| C++ `argos_smoke` | Привет, мир |
| C++ `translator_cli` Argos | Привет, мир |
| C++ `nllb_smoke` (int8+oneDNN) | Здравствуйте , мирно . |
| C++ `firefox_smoke` | привет, мир. сегодня погода хорошая. |

NLLB и Firefox теперь совпадают с Python байт-в-байт.
