# Копирует CTranslate2 и прочие runtime DLL в каталог исполняемого файла.
# Windows ищет DLL сначала рядом с exe — после этого PATH править не нужно.

function(offline_translator_deploy_win32_runtime target_name)
    if (NOT WIN32)
        return()
    endif()
    if (NOT TARGET "${target_name}")
        message(FATAL_ERROR "Нет цели ${target_name} для копирования runtime DLL")
    endif()
    if (NOT TARGET CTranslate2::ctranslate2)
        message(FATAL_ERROR "CTranslate2::ctranslate2 недоступен")
    endif()
    if (NOT OpenBLAS_DLL)
        message(FATAL_ERROR "OpenBLAS_DLL не задан")
    endif()

    add_custom_command(TARGET "${target_name}" POST_BUILD
        COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "$<TARGET_FILE:CTranslate2::ctranslate2>"
            "${OpenBLAS_DLL}"
            "$<TARGET_FILE_DIR:${target_name}>"
        COMMENT "Копирование ctranslate2.dll и openblas.dll рядом с ${target_name}"
    )

    if (NOT PROTOBUF_DLL OR NOT ABSEIL_DLL)
        message(FATAL_ERROR "PROTOBUF_DLL и ABSEIL_DLL должны быть заданы")
    endif()
    add_custom_command(TARGET "${target_name}" POST_BUILD
        COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${PROTOBUF_DLL}"
            "${ABSEIL_DLL}"
            "$<TARGET_FILE_DIR:${target_name}>"
        COMMENT "Копирование libprotobuf.dll и abseil_dll.dll рядом с ${target_name}"
    )
endfunction()
