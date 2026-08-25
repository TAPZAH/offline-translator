# Отличия C++-сборки от Python-эталона

Сводка по коду, не по маркетингу. Python (`main.py`, tkinter) остаётся
эталоном полного UX. C++ — Win32-подмножество с теми же каталогами моделей.

## Движки

- **Firefox Translations отложен.** В Python `firefox_engine.py` и
  `ENGINE_FIREFOX` ещё есть, но `app_settings.ENGINES` уже только
  `argos` / `nllb`; `translation_engine.get_engine()` Firefox не создаёт.
  В C++ движка Firefox нет (нет fxtranslate / Bergamot).
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
- **Параметры CTranslate2 не совпадают**, поэтому формулировки перевода
  могут отличаться, и это не регресс сам по себе:
  - Python Argos: `beam_size=2`, резка на предложения (`_split_sentences`).
  - Python NLLB: `beam_size=2`, `max_decoding_length=512`, `compute_type="int8"`.
  - C++: `beam_size=2`; NLLB `max_decoding_length=512`. `ComputeType::AUTO`
    (INT8 на этой OpenBLAS-сборке CTranslate2 недоступен:
    «target device or backend do not support efficient int8 computation»).
    Argos режет предложения как Python и переводит пакетом.

## GUI и выделение

- Python: tkinter, попап выделения с PNG `assets/icon.png` (PIL), полное
  окно «Языки» с поиском и удалённым индексом.
- C++: Win32. Кнопка выделения — попап 40×40 с текстом `Aa`, без PNG.
  Окно результата у курсора: копирование / закрытие, режимы
  `click_to_close` и `selectable`. Жесты (порог драга 16 px, 0.18 с,
  double Ctrl+C 0.7 с) совпадают по константам с Python.
- Комбо языков C++ показывает **56 ISO-кодов NLLB** для обоих движков.
  Для Argos это не значит, что пакет скачан: нужна локальная пара, иначе
  перевод падает с ошибкой маршрута. Окно «Пакеты» C++ перечисляет пары
  из кэша `argospm-index` (как Python `get_available_packages`) плюс
  установленные. Python в «Языках» ещё даёт поиск по каталогу Firefox.
- `language_display_name` в C++ — короткий словарь; в Python —
  `LANGUAGE_NAMES` на десятки языков.

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

- Полноценный попап выделения Python (иконка, стили overlay).
- Firefox / Bergamot.
- `langdetect`.
- Нарезка предложений Argos в C++ совпадает по правилам с Python.
  Длинный NLLB-выход ограничен 512 токенами, как в Python.

## Наблюдения qa-parity (`Hello world` en→ru)

Запуск 2026-08-25, те же пользовательские модели. Этап **не** считает
расхождение формулировок провалом.

| Источник | Текст |
|---|---|
| Python Argos | Привет, мир |
| Python NLLB | Здравствуйте , мирно . |
| C++ `argos_smoke` | Привет, мир |
| C++ `translator_cli` Argos | Привет, мир (повтор: Адский мир) |
| C++ `nllb_smoke` | Здравствуйте, мир |
| C++ `translator_cli` NLLB | Привет, мир. |

C++ Argos на одном и том же входе иногда даёт другой greedy-выход
(`beam_size=1`, OpenBLAS). Python NLLB ближе к `nllb_smoke`, не к
`translator_cli`. При выходе Argos-процесса бывает
`BLAS : Bad memory unallocation!`.
