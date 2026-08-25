#include "offline_translator/app_settings.hpp"
#include "offline_translator/argos_model_manager.hpp"
#include "offline_translator/autostart.hpp"
#include "offline_translator/clipboard.hpp"
#include "offline_translator/hotkey.hpp"
#include "offline_translator/nllb_language.hpp"
#include "offline_translator/nllb_model_manager.hpp"
#include "offline_translator/selection.hpp"
#include "offline_translator/text_split.hpp"
#include "offline_translator/translation_service.hpp"
#include "offline_translator/window_policy.hpp"
#include "file_transfer.hpp"
#include "fs_utils.hpp"
#include "zip_archive.hpp"

#include <cassert>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

using namespace offline_translator;

namespace {

void write_dummy_file(const std::filesystem::path& path, std::size_t size = 1) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    const std::string payload(size, 'x');
    out.write(payload.data(), static_cast<std::streamsize>(payload.size()));
}

void write_argos_package_files(const std::filesystem::path& package) {
    std::filesystem::create_directories(package / "model");
    for (const auto file_name : {
             "model/model.bin",
             "model/config.json",
             "model/shared_vocabulary.json",
             "sentencepiece.model",
         }) {
        write_dummy_file(package / file_name);
    }
}

void write_nllb_files(const std::filesystem::path& root, std::size_t model_size) {
    write_dummy_file(root / "model.bin", model_size);
    write_dummy_file(root / "shared_vocabulary.json");
    write_dummy_file(root / "sentencepiece.bpe.model");
}

void require(bool ok, const std::string& message) {
    if (!ok) {
        throw std::runtime_error("FAIL: " + message);
    }
}

constexpr std::string_view kArgosIndexFixtureJson = R"JSON(
[
  {
    "package_version": "1.9",
    "argos_version": "1.9.0",
    "from_code": "en",
    "from_name": "English",
    "to_code": "ru",
    "to_name": "Russian",
    "links": ["https://argos-net.com/v1/translate-en_ru-1_9.argosmodel"],
    "code": "translate-en_ru"
  },
  {
    "package_version": "1.9",
    "argos_version": "1.9.0",
    "from_code": "ru",
    "from_name": "Russian",
    "to_code": "en",
    "to_name": "English",
    "links": ["https://argos-net.com/v1/translate-ru_en-1_9.argosmodel"],
    "code": "translate-ru_en"
  },
  {
    "package_version": "1.3",
    "argos_version": "1.3",
    "from_code": "de",
    "from_name": "German",
    "to_code": "en",
    "to_name": "English",
    "links": ["https://argos-net.com/v1/translate-de_en-1_3.argosmodel"],
    "code": "translate-de_en"
  },
  {
    "package_version": "1.5",
    "argos_version": "1.5",
    "from_code": "fr",
    "from_name": "French",
    "to_code": "en",
    "to_name": "English",
    "links": [
      "https://argos-net.com/v1/translate-fr_en-1_5.argosmodel",
      "ipfs://QmFixtureOnly"
    ],
    "code": "translate-fr_en"
  },
  {
    "type": "sbd",
    "from_code": "en",
    "from_name": "English",
    "to_code": "en",
    "to_name": "English",
    "links": ["https://example.invalid/sbd-en.argosmodel"],
    "code": "sbd-en"
  },
  {
    "package_version": "1.0",
    "from_code": "xx",
    "from_name": "Unused",
    "to_code": "yy",
    "to_name": "Unused",
    "links": ["ipfs://QmNoHttpLink"],
    "code": "translate-xx_yy"
  }
]
)JSON";

bool catalog_has_pair(
    const std::vector<PackageInfo>& catalog,
    std::string_view from_code,
    std::string_view to_code) {
    for (const auto& item : catalog) {
        if (item.from_code == from_code && item.to_code == to_code) {
            return true;
        }
    }
    return false;
}

class ArgosIndexGuard {
public:
    explicit ArgosIndexGuard(
        std::filesystem::path cache_path,
        std::string url = {}) {
        ArgosModelManager::set_index_cache_path(std::move(cache_path));
        ArgosModelManager::set_index_url(std::move(url));
    }
    ~ArgosIndexGuard() {
        ArgosModelManager::set_index_cache_path({});
        ArgosModelManager::set_index_url({});
    }
    ArgosIndexGuard(const ArgosIndexGuard&) = delete;
    ArgosIndexGuard& operator=(const ArgosIndexGuard&) = delete;
};

}  // анонимное пространство имён

using namespace offline_translator;

int main() {
    try {
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

    {
        require(split_sentences("").empty(), "пустой текст без предложений");
        const auto one = split_sentences("Hello world");
        require(one.size() == 1 && one[0] == "Hello world", "одно предложение без точки");
        const auto two = split_sentences("Hello. World.");
        require(two.size() == 2, "два предложения по точке");
        require(two[0] == "Hello." && two[1] == "World.", "границы предложений");
        const auto lines = split_sentences("A\n\nB");
        require(lines.size() == 2 && lines[0] == "A" && lines[1] == "B", "разрез по переводам строк");
        const auto ellipsis = split_sentences("Ждём… Потом.");
        require(
            ellipsis.size() == 2 && ellipsis[0] == "Ждём…" && ellipsis[1] == "Потом.",
            "разрез после многоточия");
    }

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

    const auto nllb_root =
        std::filesystem::temp_directory_path() / "offline-translator-nllb-mgmt";
    std::filesystem::remove_all(nllb_root);
    {
        NllbModelManager missing(nllb_root, 1);
        require(!missing.is_installed(), "пустой корень NLLB не установлен");
        require(
            !missing.has_incomplete_package(),
            "пустой корень NLLB без обломков");
        const auto catalog = missing.available_packages();
        require(catalog.size() == 1, "каталог NLLB содержит один пакет");
        require(catalog[0].from_code == "nllb", "код пакета NLLB");
        missing.update_remote_index();
    }
    {
        NllbModelManager incomplete(nllb_root, 1);
        write_dummy_file(incomplete.staging_path() / "model.bin", 32);
        write_dummy_file(incomplete.staging_path() / "model.bin.part", 8);
        require(
            !incomplete.is_installed(),
            "остатки _downloads NLLB не считаются установленными");
        require(
            incomplete.has_incomplete_package(),
            "остатки _downloads NLLB — незавершённый пакет");
    }
    {
        NllbModelManager manager(nllb_root, 8);
        write_nllb_files(manager.staging_path(), 16);
        int progress_calls = 0;
        std::string last_message;
        manager.install_from_staging(
            [&](std::uint64_t, std::uint64_t, std::string_view message) {
                ++progress_calls;
                last_message = std::string(message);
            });
        require(manager.is_installed(), "NLLB установлен из staging");
        require(progress_calls > 0, "callback прогресса NLLB вызван");
        require(
            !manager.has_incomplete_package(),
            "после установки NLLB нет незавершённого пакета");
        require(
            !std::filesystem::exists(manager.downloads_path()),
            "пустой _downloads NLLB убран");
        bool unloaded = false;
        manager.uninstall([&] { unloaded = true; });
        require(unloaded, "uninstall NLLB вызывает выгрузку");
        require(!manager.is_installed(), "NLLB удалён");
        require(
            !std::filesystem::exists(manager.model_path()),
            "каталог модели NLLB удалён");
    }
    {
        const auto sources =
            std::filesystem::temp_directory_path() / "offline-translator-nllb-src";
        std::filesystem::remove_all(sources);
        write_nllb_files(sources, 64);
        NllbModelManager manager(nllb_root, 32);
        manager.set_source_url("model.bin", (sources / "model.bin").string());
        manager.set_source_url(
            "shared_vocabulary.json",
            (sources / "shared_vocabulary.json").string());
        manager.set_source_url(
            "sentencepiece.bpe.model",
            (sources / "sentencepiece.bpe.model").string());
        const auto part = std::filesystem::path(
            manager.staging_path() / "model.bin.part");
        std::filesystem::create_directories(part.parent_path());
        {
            std::ifstream in(sources / "model.bin", std::ios::binary);
            std::string prefix(20, '\0');
            in.read(prefix.data(), 20);
            std::ofstream(part, std::ios::binary)
                .write(prefix.data(), in.gcount());
        }
        int progress_calls = 0;
        manager.download_and_install(
            [&](std::uint64_t, std::uint64_t, std::string_view) {
                ++progress_calls;
            });
        require(manager.is_installed(), "NLLB установлен после докачки");
        require(progress_calls > 0, "докачка NLLB вызывает прогресс");
        require(
            std::filesystem::file_size(manager.model_path() / "model.bin") == 64,
            "докачанный model.bin полного размера");
        manager.uninstall();
        std::filesystem::remove_all(sources);
    }

    const auto argos_mgmt_root =
        std::filesystem::temp_directory_path() / "offline-translator-argos-mgmt";
    std::filesystem::remove_all(argos_mgmt_root);
    const auto argos_index_root =
        std::filesystem::temp_directory_path() / "offline-translator-argos-index";
    std::filesystem::remove_all(argos_index_root);
    std::filesystem::create_directories(argos_index_root);
    const auto isolated_index = argos_index_root / "index.json";
    const auto missing_index_source = argos_index_root / "missing-source.json";
    const auto fixture_path = argos_index_root / "argospm_index.json";
    fs_utils::write_text_file(fixture_path, kArgosIndexFixtureJson);
    ArgosIndexGuard argos_index_guard(isolated_index, missing_index_source.string());
    {
        ArgosModelManager missing(argos_mgmt_root, "en", "ru");
        require(!missing.is_installed(), "пустой корень Argos не установлен");
        require(
            !missing.has_incomplete_package(),
            "пустой корень Argos без обломков");
        require(
            ArgosModelManager::available_packages().size() == 2,
            "нет кэша → встроенный каталог Argos en↔ru");
        ArgosModelManager::update_remote_index();
        require(
            ArgosModelManager::available_packages().size() == 2,
            "неудачное обновление индекса не роняет каталог");
        require(
            !std::filesystem::exists(isolated_index),
            "при ошибке загрузки кэш индекса не создаётся");
    }
    {
        std::filesystem::copy_file(
            fixture_path,
            isolated_index,
            std::filesystem::copy_options::overwrite_existing);
        const auto catalog = ArgosModelManager::available_packages();
        require(
            catalog.size() > 2,
            "фикстура индекса Argos даёт больше двух пар");
        require(catalog_has_pair(catalog, "en", "ru"), "фикстура содержит en→ru");
        require(catalog_has_pair(catalog, "de", "en"), "фикстура содержит de→en");
        require(catalog_has_pair(catalog, "fr", "en"), "фикстура содержит fr→en");
        require(
            !catalog_has_pair(catalog, "xx", "yy"),
            "пакет только с ipfs:// не попадает в каталог");
        bool de_en_has_url = false;
        for (const auto& item : catalog) {
            if (item.from_code == "de" && item.to_code == "en") {
                de_en_has_url = !item.download_url.empty() &&
                    item.dirname.find("translate-de_en") == 0;
            }
        }
        require(de_en_has_url, "у de→en есть URL и dirname пакета");
        static_cast<void>(
            ArgosModelManager(argos_mgmt_root, "de", "en").has_incomplete_package());
    }
    {
        fs_utils::write_text_file(isolated_index, "{это не индекс Argos");
        const auto catalog = ArgosModelManager::available_packages();
        require(
            catalog.size() == 2,
            "битый индекс → встроенные en↔ru");
        require(catalog_has_pair(catalog, "en", "ru"), "fallback en→ru");
        require(catalog_has_pair(catalog, "ru", "en"), "fallback ru→en");
    }
    {
        std::filesystem::remove(isolated_index);
        ArgosModelManager::set_index_url(fixture_path.string());
        ArgosModelManager::update_remote_index();
        require(
            std::filesystem::is_regular_file(
                ArgosModelManager::index_cache_path()),
            "update_remote_index пишет кэш из локального файла");
        const auto catalog = ArgosModelManager::available_packages();
        require(
            catalog.size() > 2,
            "кэш после update_remote_index читается как каталог");
        require(catalog_has_pair(catalog, "de", "en"), "кэш содержит de→en");
        ArgosModelManager::set_index_url(missing_index_source.string());
    }
    {
        const auto live_cache = argos_index_root / "live-index.json";
        ArgosModelManager::set_index_cache_path(live_cache);
        ArgosModelManager::set_index_url({});
        ArgosModelManager::update_remote_index();
        const auto live = ArgosModelManager::available_packages();
        if (live.size() > 2 && std::filesystem::is_regular_file(live_cache)) {
            std::cout << "live argos index: " << live.size() << " packages\n";
        } else {
            std::cout << "skip live argos index: сеть недоступна, fallback\n";
        }
        ArgosModelManager::set_index_cache_path(isolated_index);
        ArgosModelManager::set_index_url(missing_index_source.string());
        std::filesystem::remove(isolated_index);
    }
    {
        ArgosModelManager incomplete(argos_mgmt_root, "en", "ru");
        write_argos_package_files(
            incomplete.downloads_path() / "translate-en_ru-1_9");
        require(
            !incomplete.is_installed(),
            "staging Argos в _downloads не считается установленным");
        require(
            incomplete.has_incomplete_package(),
            "staging Argos — незавершённый пакет");
        int progress_calls = 0;
        incomplete.install_from_staging(
            [&](std::uint64_t, std::uint64_t, std::string_view) {
                ++progress_calls;
            });
        require(incomplete.is_installed(), "Argos установлен из staging");
        require(progress_calls > 0, "callback прогресса Argos вызван");
        require(
            incomplete.package_path().filename() == "translate-en_ru-1_9",
            "имя установленного пакета Argos");
        bool unloaded = false;
        incomplete.uninstall([&] { unloaded = true; });
        require(unloaded, "uninstall Argos вызывает выгрузку");
        require(!incomplete.is_installed(), "Argos удалён");
    }
    {
        const auto source_pkg =
            std::filesystem::temp_directory_path() / "offline-translator-argos-src" /
            "translate-en_ru-1_9";
        std::filesystem::remove_all(source_pkg.parent_path());
        write_argos_package_files(source_pkg);
        const auto zip_path = source_pkg.parent_path() / "en_ru.argosmodel";
        write_store_zip(
            zip_path,
            {
                {"translate-en_ru-1_9/model/model.bin",
                 source_pkg / "model" / "model.bin"},
                {"translate-en_ru-1_9/model/config.json",
                 source_pkg / "model" / "config.json"},
                {"translate-en_ru-1_9/model/shared_vocabulary.json",
                 source_pkg / "model" / "shared_vocabulary.json"},
                {"translate-en_ru-1_9/sentencepiece.model",
                 source_pkg / "sentencepiece.model"},
            });
        ArgosModelManager manager(argos_mgmt_root, "en", "ru");
        manager.set_package_url(zip_path.string());
        int progress_calls = 0;
        manager.download_and_install(
            [&](std::uint64_t, std::uint64_t, std::string_view) {
                ++progress_calls;
            });
        require(manager.is_installed(), "Argos установлен из локального zip");
        require(progress_calls > 0, "установка Argos из zip вызывает прогресс");
        const auto installed = ArgosModelManager::installed_packages(argos_mgmt_root);
        require(!installed.empty(), "список установленных Argos не пуст");
        manager.uninstall();
        std::filesystem::remove_all(source_pkg.parent_path());
    }
    {
        const unsigned char deflate_zip[] = {
            0x50,0x4b,0x03,0x04,0x14,0x00,0x00,0x00,0x08,0x00,0x53,0xaa,0x19,0x5d,
            0xf0,0x2c,0x10,0x7f,0x0f,0x00,0x00,0x00,0x0d,0x00,0x00,0x00,0x0d,0x00,
            0x00,0x00,0x64,0x69,0x72,0x2f,0x68,0x65,0x6c,0x6c,0x6f,0x2e,0x74,0x78,
            0x74,0xcb,0x48,0xcd,0xc9,0xc9,0x57,0x48,0x49,0x4d,0xcb,0x49,0x2c,0x49,
            0x05,0x00,0x50,0x4b,0x01,0x02,0x14,0x00,0x14,0x00,0x00,0x00,0x08,0x00,
            0x53,0xaa,0x19,0x5d,0xf0,0x2c,0x10,0x7f,0x0f,0x00,0x00,0x00,0x0d,0x00,
            0x00,0x00,0x0d,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x80,0x01,0x00,0x00,0x00,0x00,0x64,0x69,0x72,0x2f,0x68,0x65,0x6c,0x6c,
            0x6f,0x2e,0x74,0x78,0x74,0x50,0x4b,0x05,0x06,0x00,0x00,0x00,0x00,0x01,
            0x00,0x01,0x00,0x3b,0x00,0x00,0x00,0x3a,0x00,0x00,0x00,0x00,0x00};
        const auto zip_root =
            std::filesystem::temp_directory_path() / "offline-translator-deflate-zip";
        std::filesystem::remove_all(zip_root);
        const auto zip_path = zip_root / "tiny.argosmodel";
        std::filesystem::create_directories(zip_root);
        {
            std::ofstream out(zip_path, std::ios::binary);
            out.write(
                reinterpret_cast<const char*>(deflate_zip),
                sizeof(deflate_zip));
        }
        extract_zip(zip_path, zip_root / "out");
        {
            std::ifstream in(zip_root / "out" / "dir" / "hello.txt");
            std::string text;
            std::getline(in, text);
            require(text == "hello deflate", "распаковка DEFLATE ZIP");
        }
        std::filesystem::remove_all(zip_root);
    }

    {
        const auto settings_dir =
            std::filesystem::temp_directory_path() /
            "offline-translator-settings-test";
        std::filesystem::remove_all(settings_dir);
        std::filesystem::create_directories(settings_dir);
        const auto path = settings_dir / "settings.json";
        const auto missing = load_settings(settings_dir / "missing.json");
        require(missing.engine == "argos", "engine по умолчанию");
        require(missing.source_language == "en", "язык источника по умолчанию");
        require(missing.target_language == "ru", "язык перевода по умолчанию");
        fs_utils::write_text_file(
            path,
            "{\n  \"engine\": \"argos\",\n  \"architecture\": \"tiny\",\n"
            "  \"popup_requires_ctrl\": true\n}\n");
        auto loaded = load_settings(path);
        require(loaded.engine == "argos", "чтение engine из JSON");
        loaded.engine = "nllb";
        loaded.source_language = "de";
        loaded.target_language = "fr";
        loaded.window_width = 640;
        loaded.window_height = 480;
        save_settings(path, loaded);
        const auto roundtrip = load_settings(path);
        require(roundtrip.engine == "nllb", "engine сохраняется");
        require(
            roundtrip.source_language == "de",
            "source_language сохраняется");
        require(
            roundtrip.target_language == "fr",
            "target_language сохраняется");
        require(roundtrip.window_width == 640, "window_width сохраняется");
        require(roundtrip.window_height == 480, "window_height сохраняется");
        std::string raw;
        {
            std::ifstream in(path);
            raw.assign(
                (std::istreambuf_iterator<char>(in)),
                std::istreambuf_iterator<char>());
        }
        require(
            raw.find("architecture") != std::string::npos,
            "ключ architecture Python сохраняется");
        require(
            raw.find("popup_requires_ctrl") != std::string::npos,
            "ключ popup_requires_ctrl сохраняется");
        require(
            raw.find("\"nllb\"") != std::string::npos,
            "в файле записан движок nllb");
        require(
            default_settings_path().filename() == "settings.json",
            "файл настроек называется settings.json");
        loaded.translate_hotkey = "Alt+F9";
        loaded.popup_requires_ctrl = true;
        loaded.double_ctrl_c_translation = true;
        loaded.result_window_mode = std::string{kResultWindowSelectable};
        save_settings(path, loaded);
        const auto hotkey_roundtrip = load_settings(path);
        require(
            hotkey_roundtrip.translate_hotkey == "Alt+F9",
            "translate_hotkey сохраняется");
        require(
            hotkey_roundtrip.popup_requires_ctrl,
            "popup_requires_ctrl читается");
        require(
            hotkey_roundtrip.double_ctrl_c_translation,
            "double_ctrl_c_translation читается");
        require(
            hotkey_roundtrip.result_window_mode == kResultWindowSelectable,
            "result_window_mode сохраняется");
        {
            std::ifstream in(path);
            raw.assign(
                (std::istreambuf_iterator<char>(in)),
                std::istreambuf_iterator<char>());
        }
        require(
            raw.find("translate_hotkey") != std::string::npos,
            "ключ translate_hotkey записан");
        require(
            raw.find("architecture") != std::string::npos,
            "ключ architecture Python сохраняется после hotkey");
        std::filesystem::remove_all(settings_dir);
    }

    {
        const auto recover_dir =
            std::filesystem::temp_directory_path() /
            "offline-translator-settings-recover";
        std::filesystem::remove_all(recover_dir);
        std::filesystem::create_directories(recover_dir);
        const auto path = recover_dir / "settings.json";
        fs_utils::write_text_file(path, "{\n  \"engine\": \"nllb\",\n");
        auto recovered = load_settings(path);
        require(
            recovered.engine == "argos" && recovered.source_language == "en" &&
                recovered.target_language == "ru",
            "обрезанный JSON не падает и даёт значения по умолчанию");
        fs_utils::write_text_file(path, "это не json {");
        recovered = load_settings(path);
        require(
            recovered.engine == "argos" &&
                recovered.translate_hotkey == "Ctrl+Shift+T",
            "невалидный JSON не падает и даёт значения по умолчанию");
        fs_utils::write_text_file(path, "");
        recovered = load_settings(path);
        require(
            recovered.engine == "argos",
            "пустой файл настроек не падает");
        fs_utils::write_text_file(path, "[1, 2, 3]");
        recovered = load_settings(path);
        require(
            recovered.engine == "argos" && recovered.window_width == 0,
            "JSON-массив не падает и даёт значения по умолчанию");
        fs_utils::write_text_file(
            path,
            "{\n  \"engine\": 1,\n  \"source_language\": false,\n"
            "  \"window_width\": \"wide\",\n  \"popup_requires_ctrl\": \"yes\"\n}\n");
        recovered = load_settings(path);
        require(
            recovered.engine == "argos" && recovered.source_language == "en" &&
                recovered.window_width == 0 && !recovered.popup_requires_ctrl,
            "неверные типы полей JSON не падают и дают значения по умолчанию");
        std::filesystem::remove_all(recover_dir);
    }

    {
        const auto parsed = parse_hotkey("Ctrl+Shift+T");
        require(parsed.has_value(), "разбор Ctrl+Shift+T");
        require(parsed->control && parsed->shift && !parsed->alt, "модификаторы");
        require(parsed->vk == static_cast<unsigned>('T'), "клавиша T");
        require(
            format_hotkey(*parsed) == "Ctrl+Shift+T",
            "каноническая запись Ctrl+Shift+T");
        require(
            hotkey_win32_modifiers(*parsed) == (0x0002u | 0x0004u),
            "маска MOD_CONTROL|MOD_SHIFT");
        const auto f9 = parse_hotkey("alt+f9");
        require(f9.has_value() && f9->alt && f9->vk == 0x78u, "Alt+F9");
        require(!parse_hotkey("Ctrl+").has_value(), "неполная комбинация");
        require(!parse_hotkey("").has_value(), "пустая комбинация");
    }

    {
        require(
            effect_for(UiCommand::window_close) == UiEffect::hide_to_tray,
            "крестик скрывает в трей");
        require(
            effect_for(UiCommand::tray_open) == UiEffect::restore_window,
            "Открыть восстанавливает окно");
        require(
            effect_for(UiCommand::tray_exit) == UiEffect::destroy_and_quit,
            "Выход завершает процесс");
        require(
            effect_for(UiCommand::start_minimized) ==
                UiEffect::start_hidden_in_tray,
            "--minimized стартует скрытым");
        require(
            effect_for(UiCommand::smoke_start) ==
                UiEffect::run_smoke_then_destroy,
            "smoke не прячет окно навсегда");
        require(!smoke_hides_forever(), "smoke_hides_forever == false");
        require(
            !smoke_may_enable_autostart(),
            "smoke не включает автозагрузку");
        require(tray_menu_has(TrayMenuItem::open), "меню трея: Открыть");
        require(tray_menu_has(TrayMenuItem::exit), "меню трея: Выход");
    }

    {
        require(should_show_selection_button(false, false), "кнопка без Ctrl");
        require(should_show_selection_button(true, true), "кнопка с Ctrl");
        require(
            !should_show_selection_button(true, false),
            "кнопка скрыта без Ctrl");
        require(
            should_trigger_double_ctrl_c(10.0, 10.5, true, true),
            "Ctrl+C+C в окне 0.7с");
        require(
            !should_trigger_double_ctrl_c(10.0, 10.8, true, true),
            "слишком долгий интервал");
        require(
            should_capture_selection(true, false, 30, 0.25, false),
            "жест выделения");
        require(
            !should_capture_selection(false, false, 80, 0.5, false),
            "не клиентская область");
        const auto hello = choose_selection_direction("Hello world");
        require(hello.first == "en" && hello.second == "ru", "en→ru");
        const auto russian = choose_selection_direction(
            "Привет мир, это проверка");
        require(russian.first == "ru" && russian.second == "en", "ru→en");
    }

    {
        MemoryClipboard clipboard;
        clipboard.set_text(L"user clipboard");
        const auto captured = capture_selected_text(
            clipboard,
            [&clipboard]() { clipboard.set_text(L"selected text"); },
            L"__ot_sel_test__");
        require(captured == L"selected text", "захват выделения");
        require(
            clipboard.get_text() == L"user clipboard",
            "буфер пользователя восстановлен");
        const auto empty = capture_selected_text(
            clipboard,
            []() {},
            L"__ot_sel_test__");
        require(empty.empty(), "пустое выделение");
        require(
            clipboard.get_text() == L"user clipboard",
            "буфер восстановлен при пустом выделении");
        ClipboardRestorer restorer(clipboard);
        clipboard.set_text(L"temporary");
        require(clipboard.get_text() == L"temporary", "временная запись");
        // restorer восстановит при выходе из блока
    }
    {
        MemoryClipboard clipboard;
        clipboard.set_text(L"keep me");
        {
            ClipboardRestorer restorer(clipboard);
            clipboard.set_text(L"overwrite");
        }
        require(
            clipboard.get_text() == L"keep me",
            "RAII восстанавливает буфер");
    }

#ifdef _WIN32
    {
        const auto real_before = get_run_value(kAutostartValueName);
        struct TestAutostartGuard {
            ~TestAutostartGuard() {
                try {
                    delete_run_value(kAutostartTestValueName);
                } catch (...) {
                }
            }
        } guard;
        delete_run_value(kAutostartTestValueName);
        const std::wstring command =
            autostart_command_for_exe(
                std::filesystem::path(L"C:\\fake\\offline_translator_win32.exe"));
        require(
            command.find(L"--minimized") != std::wstring::npos,
            "команда автозапуска содержит --minimized");
        require(
            command.find(L"offline_translator_win32.exe") != std::wstring::npos,
            "команда автозапуска содержит exe");
        set_autostart(true, kAutostartTestValueName, command);
        require(
            is_autostart_enabled(kAutostartTestValueName),
            "тестовая автозагрузка включена");
        const auto stored = get_run_value(kAutostartTestValueName);
        require(stored.has_value() && *stored == command, "значение Run совпадает");
        set_autostart(false, kAutostartTestValueName, command);
        require(
            !is_autostart_enabled(kAutostartTestValueName),
            "тестовая автозагрузка выключена");
        delete_run_value(kAutostartTestValueName);
        const auto real_after = get_run_value(kAutostartValueName);
        require(
            real_before == real_after,
            "тест не должен менять значение OfflineTranslator");
    }
#endif

    const auto user_nllb = NllbModelManager::default_models_root();
    NllbModelManager real_nllb(user_nllb);
    require(
        real_nllb.is_installed(),
        "Python-установленная NLLB должна определяться как установленная: " +
            real_nllb.model_path().string());
    std::cout << "user NLLB: installed\n";
    const auto user_argos = ArgosModelManager::default_packages_root();
    ArgosModelManager real_argos(user_argos, "en", "ru");
    require(
        real_argos.is_installed(),
        "Python-установленный Argos en→ru должен определяться как установленный: " +
            real_argos.package_path().string());
    std::cout << "user Argos en-ru: installed\n";

    std::filesystem::remove_all(nllb_root);
    std::filesystem::remove_all(argos_mgmt_root);
    std::filesystem::remove_all(argos_index_root);

    std::cout << "core_tests: ok\n";
    return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
