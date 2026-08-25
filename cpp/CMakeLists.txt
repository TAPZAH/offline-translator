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
        set(CTranslate2_BUILD_DIR "${CTranslate2_ROOT}/build/ctranslate2")
    endif()
    find_package(CTranslate2 CONFIG REQUIRED
        PATHS "${CTranslate2_BUILD_DIR}"
        NO_DEFAULT_PATH
    )
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
    src/argos_engine.cpp
    src/argos_model_manager.cpp
    src/nllb_model_manager.cpp
    src/nllb_language.cpp
    src/nllb_engine.cpp
    src/translation_application.cpp
    src/route_planner.cpp
    src/translation_service.cpp
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
        )
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

if (ENABLE_CTRANSLATE2)
    target_link_libraries(offline_translator_core
        PUBLIC
            CTranslate2::ctranslate2
            sentencepiece_compat
    )
endif()

if (MSVC)
    target_compile_options(offline_translator_core PRIVATE /W4 /EHsc /permissive-)
    if (ENABLE_CTRANSLATE2)
        target_compile_options(nllb_smoke PRIVATE /EHsc /permissive-)
    endif()
else()
    target_compile_options(offline_translator_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(core_tests
    tests/core_tests.cpp
)

target_link_libraries(core_tests PRIVATE offline_translator_core)

enable_testing()
add_test(NAME core_tests COMMAND core_tests)
