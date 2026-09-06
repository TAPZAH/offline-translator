# C++-ядро Offline Translator

Это ранний этап миграции. Здесь находятся независимые от GUI контракты
переводчика, маршрутизация через английский, потоковый сервис C++20 и
адаптеры CTranslate2/SentencePiece.

## Текущее состояние

- `include/offline_translator/translation_engine.hpp` — базовые типы и
  интерфейс движка;
- `include/offline_translator/route_planner.hpp` — API маршрутизации;
- `src/route_planner.cpp` — прямой маршрут и pivot через `en`;
- `include/offline_translator/translation_service.hpp` и
  `src/translation_service.cpp` — очередь задач на `std::jthread`;
- `ctranslate2_engine.*` — CPU-адаптер CTranslate2;
- `argos_engine.*` — движок Argos с кэшированием переводчиков по парам;
- `nllb_engine.*` — движок NLLB с ленивой загрузкой общей модели;
- `firefox_engine.*` — движок Firefox Translations: нативный Rust-движок
  `fxtranslate` через C-ABI мост `fxbridge.dll` (кэш по парам, pivot en);
- `fxbridge/` — Rust-cdylib мост к fxtranslate (`cargo build --release`);
  экспортирует fxt_engine_create / fxt_translate[_long] / fxt_last_error;
- `compression.*` — gunzip/zstd для скачиваемых моделей Firefox;
- `firefox_model_manager.*` — каталог GitHub/GCS, докачка, staging,
  раскладка `<root>/<arch>/<from>-<to>` как в Python;
- `sentencepiece_tokenizer.*` — RAII-обёртка SentencePiece;
- `nllb_model_manager.*` и `argos_model_manager.*` — обнаружение,
  каталог, staging-загрузка, проверка и удаление моделей;
- `app_settings.*` — чтение/запись `settings.json` (движок, языки, размер окна,
  горячая клавиша, флаги попапа выделения);
- `language_store.*` — единая таблица 56 языков с русскими названиями,
  слияние каталога Argos с установленными пакетами, сортировка
  (установленные → пары с ru/en → коды) и регистронезависимый поиск
  по кодам и названиям;
- `hotkey.*` — разбор строк вроде `Ctrl+Shift+T`;
- `clipboard.*` — захват выделения с восстановлением буфера обмена;
- `autostart.*` — HKCU `\Software\Microsoft\Windows\CurrentVersion\Run`;
- `selection.*` — жесты выделения и направление ru↔en;
- `window_policy.*` — крестик скрывает в трей, «Выход» завершает процесс;
- `tests/core_tests.cpp` — тесты бизнес-логики без моделей и GUI, включая
  каталог Argos из фикстуры `argospm-index` (без сети), fallback en↔ru,
  обнаружение версий пакетов Argos, staging/resume, uninstall, round-trip
  настроек и горячих клавиш, автозагрузку в изолированном значении реестра,
  восстановление буфера обмена и чтение обрезанного/невалидного JSON
  (значения по умолчанию, без исключения);
- `tests/integration_tests.cpp` — повторный перевод и смена движка на
  `TranslationSession`, длинный текст, en↔ru, проверка lite-пакета
  (пропуск, если `cpp/portable-win32-lite` нет).

CTranslate2 собирается отдельно из upstream-исходников в `C:\deps\CTranslate2`.
Менеджеры моделей подключены к движкам, а Win32 GUI использует фасад
`TranslationApplication` и долгоживущую `TranslationSession`. Python-версия
остаётся эталоном для полного попапа выделения; C++ даёт Win32-подмножество.
Известные отличия от Python: [`packaging/PYTHON_DIFF.md`](packaging/PYTHON_DIFF.md).

## Управление моделями

Раскладка на диске совпадает с Python, поэтому уже установленные пакеты
продолжают находиться.

**NLLB**

- каталог: `%USERPROFILE%\.local\share\offline-translator\nllb-200`
  (или переменная `OFFLINE_TRANSLATOR_NLLB`);
- установленная модель: `nllb-200-distilled-600M/` с файлами `model.bin`
  (≥ 500 МБ), `shared_vocabulary.json`, `sentencepiece.bpe.model`,
  `config.json`;
- незавершённая загрузка: `nllb-200/_downloads/nllb-200-distilled-600M/`
  и файлы `*.part`. Такой каталог **не** считается установленным
  (`is_installed() == false`, `has_incomplete_package() == true`).

**Argos**

- каталог: `%USERPROFILE%\.local\share\argos-translate\packages`;
- пакет: `translate-<from>_<to>-<version>/` (как `translate-en_ru-1_9`);
- staging: `packages/_downloads/` (zip `.argosmodel` / `.part` и распакованный
  каталог). `_downloads` никогда не входит в список установленных пакетов.

Загрузка докачивает прерванный файл через HTTP `Range` и суффикс `.part`,
затем проверяет состав файлов и атомарно переименовывает staging в
установленный каталог. Каталог NLLB фиксированный: один пакет
(`mijuanlo/nllb-200-distilled-600M-ct2-int8`). Каталог Argos читается из
кэша `argospm-index` (`%USERPROFILE%\.local\share\argos-translate\index.json`,
как `argostranslate.settings.local_package_index`).
`update_remote_index()` скачивает
`https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json`
(или `ARGOS_PACKAGE_INDEX`) во временный `.new` и подменяет кэш; ошибка сети
или битый JSON не бросаются — `available_packages()` тогда возвращает
встроенные пары `en↔ru`. Окно «Пакеты» показывает записи из этого каталога
и установленные пары, которых нет в индексе.

Удаление сначала выгружает движок (`TranslationApplication::invalidate` /
`uninstall_package`), чтобы `model.bin` не оставался открытым, затем
стирает установленный каталог и leftover `_downloads`.

Прогресс: callback `(downloaded, total, message)` — как в Python.

## Поддерживаемая конфигурация CTranslate2

Рабочий CPU-инференс — сборка **OpenBLAS + oneDNN + OpenMP компилятора**:

- каталог: `C:\deps\CTranslate2\build-openblas-dnnl`
  (`-DWITH_OPENBLAS=ON -DWITH_DNNL=ON -DWITH_MKL=OFF -DOPENMP_RUNTIME=COMP`,
  oneDNN: `C:\deps\oneDNN\install`);
- runtime: `ctranslate2.dll` зависит от `openblas.dll`, `dnnl.dll` и
  `VCOMP140.DLL`;
- NLLB работает в `int8` (как Python); адаптер молча откатывается на
  AUTO, если INT8 недоступен. Скорость smoke: ~1 c вместо ~10-16 c.

Сборка только с OpenBLAS (`build-openblas`) продолжает работать: INT8
заменяется на AUTO, но формулировки NLLB могут отличаться от Python.
Сборка `build-openblas-noomp` (`OPENMP_RUNTIME=NONE`) **не поддерживается**
для NLLB: CTranslate2 тогда использует `BS::thread_pool`
(`src/cpu/parallel.cc`), а OpenBLAS — свой пул потоков. Совместно они
зависают на реальном инференсе: `nllb_smoke` печатает заголовок `model.bin`
и не отвечает (>40 с, процесс приходится убивать). Обход
`intra_threads=1` / `OPENBLAS_NUM_THREADS=1` не оставляем в адаптере: он
либо небезопасен для рабочей OpenMP-сборки, либо не даёт поддерживаемого
пути. Для работы используйте OpenBLAS+OpenMP.

На завершении процесса OpenBLAS иногда печатает
`BLAS : Bad memory unallocation!`. Это предупреждение выгрузки OpenBLAS,
а не ошибка перевода.

## Сборка Windows

Нужны CMake 3.20+, Visual Studio 2022 Build Tools и vcpkg. Для сборки
адаптера дополнительно требуется готовая CPU-сборка CTranslate2.

Только ядро без CTranslate2:

```powershell
cmake -S cpp -B cpp/build -G "Visual Studio 17 2022" -A x64 `
  -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake
cmake --build cpp/build --config Release
ctest --test-dir cpp/build -C Release --output-on-failure
```

Поддерживаемая сборка с CTranslate2 (OpenBLAS+OpenMP). После `cmake --build`
`ctranslate2.dll`, `openblas.dll`, `libprotobuf.dll` и `abseil_dll.dll`
копируются **рядом с exe** — править `PATH` не нужно.
`CTranslate2_BUILD_DIR` записывается в `CTranslate2_DIR` принудительно, чтобы
старый CMake-кэш не подхватил другую сборку (`C:/deps/CTranslate2/build`
без OpenBLAS зависает на NLLB).

```powershell
cmake -S cpp -B cpp/build-ctranslate2 -G "Visual Studio 17 2022" -A x64 `
  -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake `
  -DENABLE_CTRANSLATE2=ON `
  -DCTranslate2_ROOT=C:/deps/CTranslate2 `
  -DCTranslate2_BUILD_DIR=C:/deps/CTranslate2/build-openblas-dnnl/ctranslate2
cmake --build cpp/build-ctranslate2 --config Release
ctest --test-dir cpp/build-ctranslate2 -C Release --output-on-failure
```

`ctest` всегда гоняет `core_tests`, `integration_tests` и
`portable_package_check` (последний тихо пропускается, если нет
`cpp/portable-win32-lite`). Если установлены модели NLLB/Argos, добавляются
`nllb_cli_smoke` и `argos_cli_smoke` (таймаут 30 с). На Windows с GUI
добавляется `win32_gui_smoke` (`offline_translator_win32 --smoke-start`).
`integration_tests` при включённом CTranslate2 гоняет повторный перевод и
смену Argos→NLLB→Argos с таймаутом 180 с; без моделей соответствующие
шаги пропускаются. Формулировки перевода с Python могут не совпадать
(см. `packaging/PYTHON_DIFF.md`).

Проверка DLL и опциональный smoke без правки PATH:

```powershell
.\cpp\check_runtime.ps1 -ExeDir .\cpp\build-ctranslate2\Release
.\cpp\check_runtime.ps1 -ExeDir .\cpp\build-ctranslate2\Release -RunSmoke
```

Ручной CLI (модели из профиля пользователя):

```powershell
.\cpp\build-ctranslate2\Release\nllb_smoke.exe `
  "$HOME\.local\share\offline-translator\nllb-200"
.\cpp\build-ctranslate2\Release\argos_smoke.exe `
  "$HOME\.local\share\argos-translate\packages"
.\cpp\build-ctranslate2\Release\translator_cli.exe nllb `
  "$HOME\.local\share\offline-translator\nllb-200" en ru "Hello world"
```

Smoke-test NLLB проверяет загрузку NLLB-200 Distilled 600M, SentencePiece и
асинхронный перевод `Hello world` через ISO-коды `en` и `ru`.

Менеджер Argos ищет пакет по шаблону
`translate-<язык>-<язык>-<версия>`, поэтому поддерживает разные версии
установленных пакетов, а не только `1_9`.

## Портативная папка и установщик

Скрипт `package_win32.ps1` копирует **только** GUI `offline_translator_win32.exe`,
runtime DLL (CTranslate2/OpenBLAS/protobuf/abseil), распространяемые
`vcruntime140.dll` / `vcruntime140_1.dll` / `msvcp140.dll` /
`msvcp140_atomic_wait.dll` / `vcomp140.dll` (OpenMP), `assets/app.ico`,
лицензии и пустую `data/` (портативные настройки). Кэш `cpp/build-*`,
`.pdb`, CLI-smoke и `vcpkg_installed` в поставку не входят.

Lite (без моделей) — для проверки и для Inno Setup:

```powershell
.\cpp\package_win32.ps1 `
  -BuildDir .\cpp\build-ctranslate2 `
  -OutputDir .\cpp\portable-win32-lite
```

Проверка состава и импортов (`dumpbin /DEPENDENTS`, best-effort):

```powershell
.\cpp\check_package.ps1 -PackageDir .\cpp\portable-win32-lite
cmake -DPACKAGE_DIR=cpp/portable-win32-lite -P cpp/cmake/CheckPortablePackage.cmake
```

Запуск GUI из портативной папки (не из `Release`, PATH не нужен):

```powershell
.\cpp\portable-win32-lite\offline_translator_win32.exe --smoke-start
```

С моделями из профиля пользователя (`data/nllb-200`, `data/argos-packages`).
Каталог не для git (сотни мегабайт). `_downloads` и `stanza` не копируются:

```powershell
.\cpp\package_win32.ps1 `
  -BuildDir .\cpp\build-ctranslate2 `
  -OutputDir .\cpp\portable-win32-full `
  -IncludeModels
```

Перенос `settings.json` из профиля в `data/` (локальная portable-копия):

```powershell
.\cpp\package_win32.ps1 `
  -BuildDir .\cpp\build-ctranslate2 `
  -OutputDir .\cpp\portable-win32-lite `
  -MigrateSettings
```

Установщик Inno Setup 6 (после lite-папки). Компилятор: `ISCC.exe`
из Inno Setup 6 (`%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` или
`C:\Program Files (x86)\Inno Setup 6\ISCC.exe`):

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" .\cpp\OfflineTranslatorCpp.iss
```

Выход: `cpp/installer-output/offline-translator-cpp-0.99-beta-setup.exe`.
Python-упаковка (`build_portable.py`, `OfflineTranslator.iss`) не меняется.
Деинсталлятор C++ удаляет `{app}` и `{app}\data`, но **не**
`%USERPROFILE%\.local\share\offline-translator`. Автозагрузка Run
при установке не включается. Если в профиле уже есть `settings.json`,
он копируется в `{app}\data` при первой установке.

Лицензии: `cpp/packaging/THIRD_PARTY.md` (в zip — `licenses/`).

В portable-режиме GUI сначала использует модели из папки `data` рядом с exe,
а при её отсутствии — пользовательские каталоги моделей.

Win32 GUI показывает полный каталог из 56 языков NLLB-200 с русскими
названиями (`language_store`) для обоих движков.
Для Argos конкретная пара должна быть установлена локально; каталог языков
не означает автоматическую загрузку пакета.

Одно `TranslationApplication` живёт между переводами и пересоздаётся только
при смене движка или корня моделей, и только в фоновом потоке. UI в это
время продолжает качать сообщения Win32; статус («Загрузка модели...»)
приходит через `PostMessage`, а не прямыми вызовами из worker.

## Настройки GUI

Файл совпадает с Python:

- `%OFFLINE_TRANSLATOR_HOME%/settings.json`, если задана переменная;
- иначе `<каталог exe>/data/settings.json` в portable-сборке (есть папка `data`);
- иначе `%USERPROFILE%/.local/share/offline-translator/settings.json`.

Сохраняются `engine` (`argos` / `nllb`), `source_language`, `target_language`,
`window_width`, `window_height`, `popup_requires_ctrl`,
`double_ctrl_c_translation`, `result_window_mode` и `translate_hotkey`
(по умолчанию `Ctrl+Shift+T`). Остальные ключи Python (`architecture` и т.д.)
при записи не затираются.

Окно «Пакеты» показывает NLLB и пары Argos из кэша `argospm-index` (и
уже установленные). При открытии индекс обновляется в фоне; без сети
остаются кэш или встроенные `en↔ru`. Прогресс установки идёт через
`PostMessage`. Удаление NLLB требует подтверждения. Строка «Поиск»
фильтрует список по кодам и русским названиям без учёта регистра
(`ru`, `немецкий`, `600m`...); статус показывает «Показано N из M».

## Трей, выделение, автозапуск

Иконка трея: `assets/app.ico` (ICO-копия `assets/icon-tray.png`). При сборке
файл копируется в `$<TARGET_FILE_DIR>/assets/app.ico`. Поиск при запуске:
`<каталог exe>/assets/app.ico`, затем обход вверх до исходного `assets/`.
Если файла нет, рисуется простая 16×16 иконка.

Крестик и Alt+F4 скрывают главное окно в трей. Пункт «Открыть» и двойной
клик по иконке восстанавливают окно. «Выход» уничтожает окно и завершает
процесс. `--minimized` стартует скрытым в трее (для автозагрузки).
`--smoke-start` не вешает иконку, не включает автозагрузку и после проверки
WM_CLOSE вызывает DestroyWindow.

Выделение: после жеста мыши или горячей клавиши текст копируется через
SendInput Ctrl+C, затем прежний буфер обмена восстанавливается. Перевод
идёт в фоне, результат — маленькое окно у курсора.

Кнопка выделения рисует `assets/icon.png` через GDI+
(`UpdateLayeredWindow`, 40×40, кликабельный диск как в Python,
фолбэк «Aa» без файла). Окно результата: палитра и шрифты Python
(Segoe UI, #f2f2f2/#dedede/#ccc/#333), полупрозрачность 0.97, рамка 1px,
высота под текст (2..12 строк), плоские кнопки с hover, Escape закрывает,
«Копировать» берёт выделение если оно есть; позиция прижимается к экрану.
Проверка без участия пользователя: `--smoke-popup` (ctest
`win32_popup_smoke`).

Автозагрузка текущего пользователя: значение `OfflineTranslator` в
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, команда
`"<exe>" --minimized`. Тесты используют отдельное имя
`OfflineTranslatorCppTest` и всегда удаляют его.

Окно «Настройки» задаёт флаги попапа, режим окна результата, горячую
клавишу и автозагрузку.

Запуск GUI без показа окна (проверка создания контролов и WM_CLOSE→трей):

```powershell
.\cpp\build-ctranslate2\Release\offline_translator_win32.exe --smoke-start
```
