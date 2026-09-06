#include "offline_translator/translation_application.hpp"

#include <iostream>
#include <stdexcept>
#include <string>

namespace {

offline_translator::EngineKind parse_engine(const std::string& name) {
    if (name == "argos") {
        return offline_translator::EngineKind::argos;
    }
    if (name == "nllb") {
        return offline_translator::EngineKind::nllb;
    }
    if (name == "marian") {
        return offline_translator::EngineKind::marian;
    }
    throw std::invalid_argument("Движок должен быть argos, nllb или marian");
}

}  // анонимное пространство имён

int main(int argc, char** argv) {
    if (argc != 6) {
        std::cerr
            << "Использование: translator_cli <argos|nllb|marian> <корень-моделей> "
               "<с языка> <на язык> <текст>\n";
        return 2;
    }

    try {
        offline_translator::TranslationApplication application(
            parse_engine(argv[1]), argv[2]);
        const auto result = application.translate(
            argv[5], argv[3], argv[4]);
        std::cout << result.text << "\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Ошибка перевода: " << error.what() << "\n";
        return 1;
    }
}
