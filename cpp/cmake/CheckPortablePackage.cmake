# Проверяет состав lite-портативной папки (без dumpbin).
# cmake -DPACKAGE_DIR=<папка> -P cpp/cmake/CheckPortablePackage.cmake

if (NOT PACKAGE_DIR)
    message(FATAL_ERROR "Задайте PACKAGE_DIR — каталог portable-сборки")
endif()

if (NOT IS_DIRECTORY "${PACKAGE_DIR}")
    message(FATAL_ERROR "Нет каталога поставки: ${PACKAGE_DIR}")
endif()

set(_required_files
    offline_translator_win32.exe
    ctranslate2.dll
    openblas.dll
    libprotobuf.dll
    abseil_dll.dll
    vcruntime140.dll
    vcruntime140_1.dll
    msvcp140.dll
    msvcp140_atomic_wait.dll
    vcomp140.dll
    assets/app.ico
    assets/icon-light.png
    assets/icon-dark.png
    licenses/THIRD_PARTY.md
    README.txt
)

set(_missing "")
foreach (_file IN LISTS _required_files)
    if (NOT EXISTS "${PACKAGE_DIR}/${_file}")
        list(APPEND _missing "${_file}")
    endif()
endforeach()

if (NOT IS_DIRECTORY "${PACKAGE_DIR}/data")
    list(APPEND _missing "data/")
endif()

if (_missing)
    message(FATAL_ERROR
        "В поставке нет обязательных файлов: ${_missing} (каталог: ${PACKAGE_DIR})")
endif()

foreach (_forbidden IN ITEMS
    CMakeCache.txt
    CMakeFiles
    vcpkg_installed
    ALL_BUILD.vcxproj
)
    if (EXISTS "${PACKAGE_DIR}/${_forbidden}")
        message(FATAL_ERROR
            "В поставке не должно быть кэша сборки: ${PACKAGE_DIR}/${_forbidden}")
    endif()
endforeach()

file(GLOB_RECURSE _pdbs "${PACKAGE_DIR}/*.pdb")
if (_pdbs)
    message(FATAL_ERROR
        "В поставке не должно быть .pdb (отладочные символы): ${_pdbs}")
endif()

message(STATUS "Портативная папка выглядит целой: ${PACKAGE_DIR}")
