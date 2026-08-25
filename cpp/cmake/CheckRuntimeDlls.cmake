# Проверяет, что обязательные runtime DLL лежат рядом с собранным exe.
# Запуск: cmake -DEXE_DIR=<каталог Release> -P cmake/CheckRuntimeDlls.cmake

if (NOT EXE_DIR)
    message(FATAL_ERROR "Задайте EXE_DIR — каталог с исполняемыми файлами")
endif()

set(_required_dlls
    ctranslate2.dll
    openblas.dll
    libprotobuf.dll
    abseil_dll.dll
)

set(_missing "")
foreach (_dll IN LISTS _required_dlls)
    if (NOT EXISTS "${EXE_DIR}/${_dll}")
        list(APPEND _missing "${_dll}")
    endif()
endforeach()

if (_missing)
    message(FATAL_ERROR
        "Рядом с exe нет обязательных DLL: ${_missing} (каталог: ${EXE_DIR})")
endif()

# Поддерживаемая сборка CTranslate2 обязана ссылаться на OpenBLAS
# (ловит устаревший CTranslate2_DIR на C:/deps/CTranslate2/build).
file(READ "${EXE_DIR}/ctranslate2.dll" _ct2_hex HEX)
string(FIND "${_ct2_hex}" "6f70656e626c61732e646c6c" _openblas_import)
if (_openblas_import LESS 0)
    message(FATAL_ERROR
        "ctranslate2.dll рядом с exe не содержит импорт openblas.dll. "
        "Проверьте CTranslate2_BUILD_DIR (нужен build-openblas). "
        "Каталог: ${EXE_DIR}")
endif()

message(STATUS "Runtime DLL на месте: ${_required_dlls} в ${EXE_DIR}")
