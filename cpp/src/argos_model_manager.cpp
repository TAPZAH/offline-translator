#include "offline_translator/argos_model_manager.hpp"

#include <array>
#include <stdexcept>
#include <utility>

namespace offline_translator {

namespace {

constexpr std::string_view kDefaultPackageVersion = "1_9";
constexpr std::array<std::string_view, 4> kRequiredFiles{
    "model/model.bin",
    "model/config.json",
    "model/shared_vocabulary.json",
    "sentencepiece.model",
};

}  // анонимное пространство имён

ArgosModelManager::ArgosModelManager(
    std::filesystem::path packages_root,
    std::string source_code,
    std::string target_code)
    : packages_root_(std::move(packages_root)),
      source_code_(std::move(source_code)),
      target_code_(std::move(target_code)) {
    if (packages_root_.empty() || source_code_.empty() || target_code_.empty()) {
        throw std::invalid_argument("Неполные параметры пакета Argos");
    }
}

std::filesystem::path ArgosModelManager::package_path() const {
    const std::string prefix =
        "translate-" + source_code_ + "_" + target_code_ + "-";
    std::filesystem::path latest_package;
    try {
        if (std::filesystem::is_directory(packages_root_)) {
            for (const auto& entry :
                 std::filesystem::directory_iterator(packages_root_)) {
                if (!entry.is_directory()) {
                    continue;
                }
                const std::string name = entry.path().filename().string();
                if (name.rfind(prefix, 0) == 0 &&
                    name.size() > prefix.size() &&
                    (latest_package.empty() ||
                     name > latest_package.filename().string())) {
                    latest_package = entry.path();
                }
            }
        }
    } catch (const std::filesystem::filesystem_error&) {
        return packages_root_ / (prefix + std::string(kDefaultPackageVersion));
    }
    if (!latest_package.empty()) {
        return latest_package;
    }
    return packages_root_ / (prefix + std::string(kDefaultPackageVersion));
}

std::filesystem::path ArgosModelManager::model_path() const {
    return package_path() / "model";
}

std::filesystem::path ArgosModelManager::tokenizer_path() const {
    return package_path() / "sentencepiece.model";
}

bool ArgosModelManager::is_installed() const {
    try {
        for (const auto file_name : kRequiredFiles) {
            if (!std::filesystem::is_regular_file(package_path() / file_name)) {
                return false;
            }
        }
        return true;
    } catch (const std::filesystem::filesystem_error&) {
        return false;
    }
}

void ArgosModelManager::validate() const {
    if (!is_installed()) {
        throw std::runtime_error(
            "Пакет Argos не установлен или повреждён: " +
            package_path().string());
    }
}

}  // пространство имён offline_translator
