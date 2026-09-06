#include "offline_translator/marian_engine.hpp"
#include "offline_translator/marian_model_manager.hpp"
#include "offline_translator/translation_service.hpp"

#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Использование: marian_smoke <корень-моделей>\n";
        return 2;
    }

    try {
        offline_translator::MarianModelManager model_manager(
            argv[1], "en", "ru");
        model_manager.validate();
        offline_translator::MarianEngine engine(argv[1]);
        offline_translator::TranslationService service(
            [](std::string_view source, std::string_view target) {
                return source == "en" && target == "ru";
            },
            [&engine](
                std::string_view text,
                std::string_view source,
                std::string_view target) {
                return engine.translate(text, source, target).text;
            },
            "MarianMT");
        const auto result = service.translate("Hello world", "en", "ru");
        std::cout << "Hello world -> " << result.text << "\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Ошибка MarianMT smoke-test: " << error.what() << "\n";
        return 1;
    }
}
