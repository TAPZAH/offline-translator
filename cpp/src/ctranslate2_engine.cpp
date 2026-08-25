#include "offline_translator/ctranslate2_engine.hpp"

#include "offline_translator/nllb_language.hpp"
#include "offline_translator/route_planner.hpp"

#include <ctranslate2/translator.h>

#include <algorithm>
#include <stdexcept>
#include <utility>

namespace offline_translator {

class CTranslate2State {
public:
    CTranslate2State(const std::string& model_path, bool nllb_model)
        : translator(
              model_path,
              ctranslate2::Device::CPU,
              nllb_model
                  ? ctranslate2::ComputeType::FLOAT32
                  : ctranslate2::ComputeType::AUTO) {}

    ctranslate2::Translator translator;
};

CTranslate2Engine::CTranslate2Engine(
    std::string model_path,
    IsInstalled is_installed,
    Tokenize tokenize,
    Detokenize detokenize,
    bool nllb_model)
    : model_path_(std::move(model_path)),
      is_installed_(std::move(is_installed)),
      tokenize_(std::move(tokenize)),
      detokenize_(std::move(detokenize)),
      nllb_model_(nllb_model) {
    if (!is_installed_ || !tokenize_ || !detokenize_) {
        throw std::invalid_argument("Неполный набор callback-ов CTranslate2");
    }
}

CTranslate2Engine::~CTranslate2Engine() {
    stop();
}

TranslationResult CTranslate2Engine::translate(
    std::string_view text,
    std::string_view source_code,
    std::string_view target_code) {
    if (stopped_) {
        throw std::runtime_error("Движок CTranslate2 остановлен");
    }
    return translate_with_english_pivot(
        text,
        source_code,
        target_code,
        is_installed_,
        [this](std::string_view direct_text,
               std::string_view direct_source,
               std::string_view direct_target) {
            return translate_direct(direct_text, direct_source, direct_target);
        },
        "CTranslate2");
}

void CTranslate2Engine::warmup(
    std::string_view source_code,
    std::string_view target_code) {
    static_cast<void>(translate("Hello", source_code, target_code));
}

void CTranslate2Engine::invalidate() {
    if (!stopped_) {
        state_.reset();
    }
}

void CTranslate2Engine::stop() {
    if (stopped_) {
        return;
    }
    stopped_ = true;
    state_.reset();
}

std::optional<std::string> CTranslate2Engine::translation_route(
    std::string_view source_code,
    std::string_view target_code) const {
    return english_pivot_route(is_installed_, source_code, target_code);
}

void CTranslate2Engine::ensure_loaded() {
    if (!state_) {
        state_ = std::make_unique<CTranslate2State>(model_path_, nllb_model_);
    }
}

std::string CTranslate2Engine::translate_direct(
    std::string_view text,
    std::string_view source_code,
    std::string_view target_code) {
    ensure_loaded();

    auto tokens = tokenize_(text);
    if (tokens.empty()) {
        throw std::runtime_error("Токенизатор вернул пустой результат");
    }

    const std::string nllb_source =
        nllb_model_ ? nllb_language_code(source_code) : std::string(source_code);
    const std::string nllb_target =
        nllb_model_ ? nllb_language_code(target_code) : std::string(target_code);
    std::vector<std::string> target_prefix;
    if (nllb_model_) {
        tokens.insert(tokens.begin(), nllb_source);
        tokens.emplace_back("</s>");
        target_prefix.emplace_back(nllb_target);
    }

    ctranslate2::TranslationOptions options;
    options.beam_size = 1;
    options.max_decoding_length = 32;
    options.replace_unknowns = true;
    const auto results = state_->translator.translate_batch(
        {tokens},
        target_prefix.empty()
            ? std::vector<std::vector<std::string>>{}
            : std::vector<std::vector<std::string>>{target_prefix},
        options);
    if (results.empty() || results.front().hypotheses.empty()) {
        throw std::runtime_error("CTranslate2 вернул пустой результат");
    }

    auto hypothesis = results.front().hypotheses.front();
    if (nllb_model_) {
        hypothesis.erase(
            std::remove(
                hypothesis.begin(),
                hypothesis.end(),
                nllb_target),
            hypothesis.end());
        while (!hypothesis.empty() &&
               (hypothesis.back() == "</s>" || hypothesis.back() == "<s>")) {
            hypothesis.pop_back();
        }
    }
    const std::string translated = detokenize_(hypothesis);
    if (translated.empty()) {
        throw std::runtime_error("Детокенизатор вернул пустой результат");
    }
    return translated;
}

}  // пространство имён offline_translator
