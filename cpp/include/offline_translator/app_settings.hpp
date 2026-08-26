#pragma once

#include "offline_translator/translation_application.hpp"

#include <filesystem>
#include <string>
#include <string_view>

namespace offline_translator {

// Настройки главного окна. Файл — JSON, совместимый с Python
// (`engine` и прочие ключи сохраняются при записи).
// Путь по умолчанию:
//   %OFFLINE_TRANSLATOR_HOME%/settings.json
//   или <каталог exe>/data/settings.json  (portable, если есть папка data)
//   иначе %USERPROFILE%/.local/share/offline-translator/settings.json
struct AppSettings {
    std::string engine{"argos"};
    std::string source_language{"en"};
    std::string target_language{"ru"};
    int window_width{0};
    int window_height{0};
    bool popup_requires_ctrl{false};
    bool double_ctrl_c_translation{false};
    std::string result_window_mode{"click_to_close"};
    std::string translate_hotkey{"Ctrl+Shift+T"};
    // Размер моделей Firefox Translations: tiny | base (как в Python).
    std::string architecture{"tiny"};
};

std::filesystem::path default_data_root();
std::filesystem::path default_settings_path();

AppSettings load_settings();
AppSettings load_settings(const std::filesystem::path& path);
void save_settings(const AppSettings& settings);
void save_settings(const std::filesystem::path& path, const AppSettings& settings);

EngineKind engine_kind_from_settings(std::string_view engine);
std::string settings_engine_name(EngineKind engine_kind);

}  // пространство имён offline_translator
