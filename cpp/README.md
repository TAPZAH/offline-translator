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
- `sentencepiece_tokenizer.*` — RAII-обёртка SentencePiece;
- `nllb_model_manager.*` и `argos_model_manager.*` — проверка установленных
  моделей;
- `tests/core_tests.cpp` — тесты бизнес-логики без моделей и GUI, включая
  обнаружение версий пакетов Argos.

CTranslate2 собирается отдельно из upstream-исходников в `C:\deps\CTranslate2`.
Менеджеры моделей подключены к движкам, а Win32 GUI использует фасад
`TranslationApplication`. Python-версия остаётся рабочим эталоном поведения
для ещё не перенесённых функций управления настройками и загрузки моделей.

## Сборка Windows

Нужны CMake 3.20+, Visual Studio 2022 Build Tools и vcpkg. Для сборки
адаптера дополнительно требуется готовая CPU-сборка CTranslate2.

```powershell
cmake -S cpp -B cpp/build -G "Visual Studio 17 2022" -A x64 `
  -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake
cmake --build cpp/build --config Release
ctest --test-dir cpp/build -C Release --output-on-failure
```

Для включения CTranslate2 используйте:

```powershell
cmake -S cpp -B cpp/build-ctranslate2 -G "Visual Studio 17 2022" -A x64 `
  -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake `
  -DENABLE_CTRANSLATE2=ON `
  -DCTranslate2_ROOT=C:/deps/CTranslate2 `
  -DCTranslate2_BUILD_DIR=C:/deps/CTranslate2/build-openblas/ctranslate2
```

Для CPU-инференса используется сборка CTranslate2 с OpenBLAS. После сборки
проверить реальную модель можно командой:

```powershell
$env:PATH="C:\deps\CTranslate2\build-openblas\Release;C:\vcpkg\installed\x64-windows\bin;$env:PATH"
.\cpp\build-ctranslate2\Release\nllb_smoke.exe `
  "$HOME\.local\share\offline-translator\nllb-200"
```

Smoke-test проверяет загрузку NLLB-200 Distilled 600M, SentencePiece и
асинхронный перевод `Hello world` через ISO-коды `en` и `ru`.

Проверить установленный пакет Argos `en→ru` через асинхронный сервис:

```powershell
.\cpp\build-ctranslate2\Release\argos_smoke.exe `
  "$HOME\.local\share\argos-translate\packages"
```

Менеджер Argos ищет пакет по шаблону
`translate-<язык>-<язык>-<версия>`, поэтому поддерживает разные версии
установленных пакетов, а не только `1_9`.

Собрать portable lite-папку с Win32 GUI и DLL:

```powershell
.\cpp\package_win32.ps1 `
  -BuildDir .\cpp\build-win32 `
  -OutputDir .\cpp\portable-win32-lite
```

В portable-режиме GUI сначала использует модели из папки `data` рядом с exe,
а при её отсутствии — пользовательские каталоги моделей.

Win32 GUI показывает полный каталог из 56 языков NLLB-200 для обоих движков.
Для Argos конкретная пара должна быть установлена локально; каталог языков
не означает автоматическую загрузку пакета.
