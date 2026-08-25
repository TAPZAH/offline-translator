#include "offline_translator/nllb_model_manager.hpp"

#include <array>
#include <cstdint>
#include <stdexcept>
#include <string_view>
#include <utility>

namespace offline_translator {

namespace {

constexpr std::string_view kModelName = "nllb-200-distilled-600M";
constexpr std::uintmax_t kMinimumModelSize = 500U * 1024U * 1024U;
constexpr std::array<std::string_view, 4> kRequiredFiles{
    "model.bin",
    "shared_vocabulary.json",
    "sentencepiece.bpe.model",
    "config.json",
};

}  // анонимное пространство имён

NllbModelManager::NllbModelManager(std::filesystem::path models_root)
    : models_root_(std::move(models_root)) {
    if (models_root_.empty()) {
        throw std::invalid_argument("Не задан корень моделей NLLB");
    }
}

std::filesystem::path NllbModelManager::model_path() const {
    return models_root_ / kModelName;
}

bool NllbModelManager::is_installed() const {
    try {
        const auto root = model_path();
        const auto model_bin = root / "model.bin";
        if (!std::filesystem::is_regular_file(model_bin) ||
            std::filesystem::file_size(model_bin) < kMinimumModelSize) {
            return false;
        }
        for (const auto file_name : kRequiredFiles) {
            if (!std::filesystem::is_regular_file(root / file_name)) {
                return false;
            }
        }
        return true;
    } catch (const std::filesystem::filesystem_error&) {
        return false;
    }
}

void NllbModelManager::validate() const {
    if (!is_installed()) {
        throw std::runtime_error(
            "Модель NLLB не установлена или повреждена: " +
            model_path().string());
    }
}

}  // пространство имён offline_translator
