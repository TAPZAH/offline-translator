#include "offline_translator/nllb_engine.hpp"
#include "offline_translator/nllb_model_manager.hpp"
#include "offline_translator/translation_service.hpp"

#include <fstream>
#include <array>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Использование: nllb_smoke <корень-моделей>\n";
        return 2;
    }

    try {
        const offline_translator::NllbModelManager model_manager(argv[1]);
        model_manager.validate();
        const auto model_path = model_manager.model_path();
        const auto model_bin = model_path / "model.bin";
        std::ifstream model_file(model_bin, std::ios::binary);
        if (!model_file) {
            throw std::runtime_error("Не удалось открыть " + model_bin.string());
        }
        std::array<unsigned char, 8> header{};
        model_file.read(
            reinterpret_cast<char*>(header.data()),
            static_cast<std::streamsize>(header.size()));
        std::cout << "model.bin: " << std::filesystem::file_size(model_bin)
                  << " байт, заголовок:";
        for (const auto byte : header) {
            std::cout << " " << std::hex << std::setw(2) << std::setfill('0')
                      << static_cast<int>(byte);
        }
        std::cout << std::dec << "\n" << std::flush;

        offline_translator::NllbEngine engine(argv[1]);

        const std::string input = "Hello world";
        offline_translator::TranslationService service(
            [](std::string_view, std::string_view) { return true; },
            [&engine](
                std::string_view text,
                std::string_view source,
                std::string_view target) {
                return engine.translate(text, source, target).text;
            },
            "NLLB");
        const auto result = service.translate(input, "en", "ru");
        std::cout << input << " -> " << result.text << "\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Ошибка NLLB smoke-test: " << error.what() << "\n";
        return 1;
    }
}
