#include "offline_translator/argos_model_manager.hpp"
#include "offline_translator/nllb_language.hpp"
#include "offline_translator/nllb_model_manager.hpp"
#include "offline_translator/translation_service.hpp"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>

using namespace offline_translator;

int main() {
    const NllbModelManager model_manager("C:/offline-translator-test-models");
    assert(model_manager.model_path().filename() == "nllb-200-distilled-600M");
    assert(!model_manager.is_installed());
    bool model_validation_thrown = false;
    try {
        model_manager.validate();
    } catch (const std::runtime_error&) {
        model_validation_thrown = true;
    }
    assert(model_validation_thrown);

    assert(nllb_language_code("en") == "eng_Latn");
    assert(nllb_language_code("ru") == "rus_Cyrl");
    assert(nllb_language_code("rus_Cyrl") == "rus_Cyrl");
    bool unknown_language_thrown = false;
    try {
        static_cast<void>(nllb_language_code("xx"));
    } catch (const std::runtime_error&) {
        unknown_language_thrown = true;
    }
    assert(unknown_language_thrown);

    const std::set<LanguagePair> installed{
        {"ru", "en"},
        {"en", "ru"},
        {"en", "fr"},
    };
    const IsInstalled is_installed =
        [&installed](std::string_view source, std::string_view target) {
            return installed.contains(
                LanguagePair{std::string(source), std::string(target)});
        };
    const DirectTranslate direct_translate =
        [](std::string_view text, std::string_view source, std::string_view target) {
            return "[" + std::string(source) + ">" + std::string(target) +
                   "] " + std::string(text);
        };

    assert(english_pivot_route(is_installed, "ru", "en") == "direct");
    assert(!english_pivot_route(is_installed, "ru", "ru").has_value());
    assert(!english_pivot_route(is_installed, "de", "fr").has_value());

    const auto needed = needed_english_pivot_pairs("de", "fr", is_installed);
    assert(needed.size() == 2);
    assert((needed[0] == LanguagePair{"de", "en"}));
    assert((needed[1] == LanguagePair{"en", "fr"}));

    const auto argos_test_root =
        std::filesystem::temp_directory_path() / "offline-translator-argos-test";
    std::filesystem::remove_all(argos_test_root);
    const auto argos_package =
        argos_test_root / "translate-en_ru-2_0";
    std::filesystem::create_directories(argos_package / "model");
    for (const auto file_name : {
             "model/model.bin",
             "model/config.json",
             "model/shared_vocabulary.json",
             "sentencepiece.model",
         }) {
        std::ofstream(argos_package / file_name).put('\0');
    }
    const ArgosModelManager argos_manager(argos_test_root, "en", "ru");
    assert(argos_manager.package_path() == argos_package);
    assert(argos_manager.is_installed());
    std::filesystem::remove_all(argos_test_root);

    TranslationService service(is_installed, direct_translate, "Test");
    const auto direct = service.translate(" hello ", "ru", "en");
    assert(direct.text == "[ru>en] hello");
    assert(!direct.intermediate.has_value());

    const auto pivot = service.translate(" привет ", "ru", "fr");
    assert(pivot.text == "[en>fr] [ru>en] привет");
    assert(pivot.intermediate == "[ru>en] привет");
    assert(pivot.pivot_code == "en");

    const auto empty = service.translate("   ", "ru", "fr");
    assert(empty.text == "   ");
    assert(!empty.intermediate.has_value());

    bool missing_thrown = false;
    try {
        static_cast<void>(service.translate("text", "de", "fr"));
    } catch (const std::runtime_error& error) {
        missing_thrown = std::string(error.what()).find("de->en") !=
                         std::string::npos;
    }
    assert(missing_thrown);

    service.stop();
    bool stopped_thrown = false;
    try {
        static_cast<void>(service.translate("text", "ru", "en"));
    } catch (const std::runtime_error&) {
        stopped_thrown = true;
    }
    assert(stopped_thrown);

    std::cout << "core_tests: ok\n";
    return 0;
}
