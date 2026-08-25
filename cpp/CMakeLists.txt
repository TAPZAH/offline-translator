cmake_minimum_required(VERSION 3.20)
project(offline_translator_core LANGUAGES CXX)

if (POLICY CMP0144)
    cmake_policy(SET CMP0144 NEW)
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(nlohmann_json CONFIG REQUIRED)
option(ENABLE_CTRANSLATE2 "Подключить собранный CTranslate2" OFF)
set(CTranslate2_ROOT "" CACHE PATH "Корень исходников и сборки CTranslate2")
set(CTranslate2_BUILD_DIR "" CACHE PATH "Каталог CMake-сборки CTranslate2")

if (ENABLE_CTRANSLATE2)
    if (NOT CTranslate2_ROOT)
        message(FATAL_ERROR "Для ENABLE_CTRANSLATE2 укажите CTranslate2_ROOT")
    endif()
    if (NOT CTranslate2_BUILD_DIR)
        set(CTranslate2_BUILD_DIR
            "${CTranslate2_ROOT}/build-openblas/ctranslate2")
    endif()
    # find_package иначе может взять закэшированный CTranslate2_DIR
    # от другой сборки (например C:/deps/CTranslate2/build без OpenBLAS).
    set(CTranslate2_DIR "${CTranslate2_BUILD_DIR}" CACHE PATH
        "Каталог CTranslate2Config.cmake" FORCE)
    find_package(CTranslate2 CONFIG REQUIRED
        PATHS "${CTranslate2_BUILD_DIR}"
        NO_DEFAULT_PATH
    )
    get_target_property(_ctranslate2_dll
        CTranslate2::ctranslate2 IMPORTED_LOCATION_RELEASE)
    message(STATUS "CTranslate2 DLL: ${_ctranslate2_dll}")
    set_property(TARGET CTranslate2::ctranslate2
        PROPERTY MAP_IMPORTED_CONFIG_DEBUG Release
    )
    find_path(SENTENCEPIECE_INCLUDE_DIR sentencepiece_processor.h REQUIRED)
    get_filename_component(SENTENCEPIECE_ROOT
        "${SENTENCEPIECE_INCLUDE_DIR}" DIRECTORY
    )
    find_library(SENTENCEPIECE_RELEASE_LIBRARY
        NAMES sentencepiece
        PATHS "${SENTENCEPIECE_ROOT}/lib"
        NO_DEFAULT_PATH
        REQUIRED
    )
    find_library(SENTENCEPIECE_DEBUG_LIBRARY
        NAMES sentencepiece
        PATHS "${SENTENCEPIECE_ROOT}/debug/lib"
        NO_DEFAULT_PATH
        REQUIRED
    )
    add_library(sentencepiece_compat STATIC IMPORTED GLOBAL)
    set_target_properties(sentencepiece_compat PROPERTIES
        IMPORTED_LOCATION_RELEASE "${SENTENCEPIECE_RELEASE_LIBRARY}"
        IMPORTED_LOCATION_DEBUG "${SENTENCEPIECE_DEBUG_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${SENTENCEPIECE_INCLUDE_DIR}"
    )
    find_package(absl CONFIG REQUIRED)
    find_package(protobuf CONFIG REQUIRED)
endif()

add_library(offline_translator_core
    src/app_settings.cpp
    src/argos_engine.cpp
    src/argos_model_manager.cpp
    src/autostart.cpp
    src/clipboard.cpp
    src/file_transfer.cpp
    src/fs_utils.cpp
    src/hotkey.cpp
    src/nllb_model_manager.cpp
    src/nllb_language.cpp
    src/nllb_engine.cpp
    src/selection.cpp
    src/translation_application.cpp
    src/route_planner.cpp
    src/translation_service.cpp
    src/window_policy.cpp
    src/zip_archive.cpp
)

if (ENABLE_CTRANSLATE2)
    target_sources(offline_translator_core
        PRIVATE
            src/ctranslate2_engine.cpp
            src/sentencepiece_tokenizer.cpp
    )
    target_include_directories(offline_translator_core
        PRIVATE
            ${SENTENCEPIECE_INCLUDE_DIR}
    )

    add_executable(nllb_smoke
        tools/nllb_smoke.cpp
    )
    add_executable(argos_smoke
        tools/argos_smoke.cpp
    )
    add_executable(translator_cli
        tools/translator_cli.cpp
    )
    if (WIN32)
        add_executable(offline_translator_win32 WIN32
            app/win32_main.cpp
        )
    endif()
    target_include_directories(nllb_smoke
        PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/include
            ${SENTENCEPIECE_INCLUDE_DIR}
    )
    target_include_directories(argos_smoke
        PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/include
            ${SENTENCEPIECE_INCLUDE_DIR}
    )
    target_include_directories(translator_cli
        PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/include
    )
    if (WIN32)
        target_include_directories(offline_translator_win32
            PRIVATE
                ${CMAKE_CURRENT_SOURCE_DIR}/include
        )
    endif()
    target_link_libraries(nllb_smoke
        PRIVATE
            offline_translator_core
            CTranslate2::ctranslate2
            sentencepiece_compat
            protobuf::libprotobuf
            absl::base
            absl::strings
            absl::raw_hash_set
            absl::synchronization
            absl::log
            absl::flags
    )
    target_link_libraries(argos_smoke
        PRIVATE
            offline_translator_core
            CTranslate2::ctranslate2
            sentencepiece_compat
            protobuf::libprotobuf
            absl::base
            absl::strings
            absl::raw_hash_set
            absl::synchronization
            absl::log
            absl::flags
    )
    target_link_libraries(translator_cli
        PRIVATE
            offline_translator_core
            CTranslate2::ctranslate2
            sentencepiece_compat
            protobuf::libprotobuf
            absl::base
            absl::strings
            absl::raw_hash_set
            absl::synchronization
            absl::log
            absl::flags
    )
    if (WIN32)
        target_link_libraries(offline_translator_win32
            PRIVATE
                offline_translator_core
                CTranslate2::ctranslate2
                sentencepiece_compat
                protobuf::libprotobuf
                absl::base
                absl::strings
                absl::raw_hash_set
                absl::synchronization
                absl::log
                absl::flags
                user32
                shell32
                gdi32
                comctl32
        )
        set(_app_ico "${CMAKE_CURRENT_SOURCE_DIR}/../assets/app.ico")
        if (EXISTS "${_app_ico}")
            add_custom_command(TARGET offline_translator_win32 POST_BUILD
                COMMAND "${CMAKE_COMMAND}" -E make_directory
                    "$<TARGET_FILE_DIR:offline_translator_win32>/assets"
                COMMAND "${CMAKE_COMMAND}" -E copy_if_different
                    "${_app_ico}"
                    "$<TARGET_FILE_DIR:offline_translator_win32>/assets/app.ico"
                COMMENT "Копирование assets/app.ico рядом с GUI"
            )
        endif()
    endif()
endif()

target_include_directories(offline_translator_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(offline_translator_core
    PUBLIC
        nlohmann_json::nlohmann_json
)

if (WIN32)
    target_link_libraries(offline_translator_core PUBLIC winhttp advapi32 user32)
endif()

if (ENABLE_CTRANSLATE2)
    target_link_libraries(offline_translator_core
        PUBLIC
            CTranslate2::ctranslate2
            sentencepiece_compat
    )
    if (WIN32)
        find_file(OpenBLAS_DLL
            NAMES openblas.dll
            PATHS
                "C:/vcpkg/installed/x64-windows/bin"
                "$ENV{VCPKG_ROOT}/installed/x64-windows/bin"
                "${CMAKE_BINARY_DIR}/vcpkg_installed/x64-windows/bin"
            NO_DEFAULT_PATH
        )
        if (NOT OpenBLAS_DLL)
            find_file(OpenBLAS_DLL NAMES openblas.dll)
        endif()
        if (NOT OpenBLAS_DLL)
            message(FATAL_ERROR
                "Не найден openblas.dll. Укажите OpenBLAS_DLL или установите OpenBLAS в vcpkg.")
        endif()
        set(_vcpkg_bin_search
            "${CMAKE_BINARY_DIR}/vcpkg_installed/x64-windows/bin"
            "C:/vcpkg/installed/x64-windows/bin"
            "$ENV{VCPKG_ROOT}/installed/x64-windows/bin"
        )
        find_file(ABSEIL_DLL
            NAMES abseil_dll.dll
            PATHS ${_vcpkg_bin_search}
            NO_DEFAULT_PATH
        )
        find_file(PROTOBUF_DLL
            NAMES libprotobuf.dll
            PATHS ${_vcpkg_bin_search}
            NO_DEFAULT_PATH
        )
        if (NOT ABSEIL_DLL OR NOT PROTOBUF_DLL)
            message(FATAL_ERROR
                "Не найдены abseil_dll.dll и/или libprotobuf.dll в vcpkg bin.")
        endif()
        include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/DeployWin32Runtime.cmake")
    endif()
endif()

if (MSVC)
    target_compile_options(offline_translator_core PRIVATE /W4 /EHsc /permissive- /utf-8)
    if (ENABLE_CTRANSLATE2)
        target_compile_options(nllb_smoke PRIVATE /EHsc /permissive- /utf-8)
        target_compile_options(argos_smoke PRIVATE /EHsc /permissive- /utf-8)
        target_compile_options(translator_cli PRIVATE /EHsc /permissive- /utf-8)
        if (TARGET offline_translator_win32)
            target_compile_options(offline_translator_win32 PRIVATE /EHsc /permissive- /utf-8)
        endif()
    endif()
else()
    target_compile_options(offline_translator_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(core_tests
    tests/core_tests.cpp
)
add_executable(integration_tests
    tests/integration_tests.cpp
)

target_link_libraries(core_tests PRIVATE offline_translator_core)
target_link_libraries(integration_tests PRIVATE offline_translator_core)
target_include_directories(core_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_include_directories(integration_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
if (MSVC)
    target_compile_options(core_tests PRIVATE /EHsc /permissive- /utf-8)
    target_compile_options(integration_tests PRIVATE /EHsc /permissive- /utf-8)
endif()
if (ENABLE_CTRANSLATE2)
    target_compile_definitions(integration_tests PRIVATE ENABLE_CTRANSLATE2)
    target_link_libraries(integration_tests PRIVATE
        CTranslate2::ctranslate2
        sentencepiece_compat
        protobuf::libprotobuf
        absl::base
        absl::strings
        absl::raw_hash_set
        absl::synchronization
        absl::log
        absl::flags
    )
endif()

if (ENABLE_CTRANSLATE2 AND WIN32)
    foreach (_runtime_target IN ITEMS
        nllb_smoke
        argos_smoke
        translator_cli
        offline_translator_win32
        core_tests
        integration_tests
    )
        if (TARGET "${_runtime_target}")
            offline_translator_deploy_win32_runtime("${_runtime_target}")
        endif()
    endforeach()
endif()

enable_testing()
add_test(NAME core_tests COMMAND core_tests)
add_test(NAME integration_tests COMMAND integration_tests)
set_tests_properties(integration_tests PROPERTIES TIMEOUT 180)
add_test(
    NAME portable_package_check
    COMMAND "${CMAKE_COMMAND}"
        -DPACKAGE_DIR=${CMAKE_CURRENT_SOURCE_DIR}/portable-win32-lite
        -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/CheckPortablePackageOrSkip.cmake"
)

if (ENABLE_CTRANSLATE2 AND WIN32 AND TARGET nllb_smoke)
    add_test(
        NAME check_runtime_dlls
        COMMAND "${CMAKE_COMMAND}"
            -DEXE_DIR=$<TARGET_FILE_DIR:nllb_smoke>
            -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/CheckRuntimeDlls.cmake"
    )
    set(NLLB_MODELS_ROOT
        "$ENV{USERPROFILE}/.local/share/offline-translator/nllb-200")
    set(ARGOS_PACKAGES_ROOT
        "$ENV{USERPROFILE}/.local/share/argos-translate/packages")
    if (EXISTS "${NLLB_MODELS_ROOT}/nllb-200-distilled-600M/model.bin")
        add_test(
            NAME nllb_cli_smoke
            COMMAND nllb_smoke "${NLLB_MODELS_ROOT}"
        )
        set_tests_properties(nllb_cli_smoke PROPERTIES TIMEOUT 30)
    endif()
    if (EXISTS "${ARGOS_PACKAGES_ROOT}")
        file(GLOB _argos_en_ru "${ARGOS_PACKAGES_ROOT}/translate-en_ru-*")
        if (_argos_en_ru)
            add_test(
                NAME argos_cli_smoke
                COMMAND argos_smoke "${ARGOS_PACKAGES_ROOT}"
            )
            set_tests_properties(argos_cli_smoke PROPERTIES TIMEOUT 30)
        endif()
    endif()
    if (TARGET offline_translator_win32)
        add_test(
            NAME win32_gui_smoke
            COMMAND offline_translator_win32 --smoke-start
        )
        set_tests_properties(win32_gui_smoke PROPERTIES TIMEOUT 15)
    endif()
endif()
