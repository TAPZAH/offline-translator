// Smoke-проверка движка Firefox Translations: перевод en→ru через
// fxbridge.dll по установленной в профиле модели (base/en-ru).
#include "offline_translator/firefox_engine.hpp"
#include "offline_translator/firefox_model_manager.hpp"

#include <iostream>
#include <stdexcept>

int main(int argc, char** argv) {
    try {
        std::filesystem::path root;
        if (argc > 1) {
            root = argv[1];
        } else {
            root = offline_translator::FirefoxModelManager::default_models_root();
        }
        offline_translator::FirefoxModelManager manager(
            root, "base", "en", "ru");
        if (!manager.is_installed()) {
            std::cout << "skip firefox smoke: модель base/en-ru не установлена\n";
            return 0;
        }
        offline_translator::FirefoxEngine engine(root, "base");
        const auto route = engine.translation_route("en", "ru");
        if (!route || *route != "direct") {
            std::cerr << "FAIL: маршрут en->ru должен быть прямым\n";
            return 1;
        }
        const auto result = engine.translate(
            "Hello world. The weather is nice today.", "en", "ru");
        const auto contains_cyrillic = [](
                                           const std::string& text) {
            for (const unsigned char ch : text) {
                if (ch >= 0xD0 && ch <= 0xD1) {
                    // Первый байт двухбайтовой кириллицы UTF-8.
                    return true;
                }
            }
            return false;
        };
        std::cout << "firefox: " << result.text << "\n";
        if (!contains_cyrillic(result.text)) {
            std::cerr << "FAIL: перевод не содержит кириллицы\n";
            return 1;
        }
        std::cout << "firefox_smoke: ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << "\n";
        return 1;
    }
}
